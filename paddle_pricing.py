"""Parse Paddle pricing configuration and retrieve formatted monthly prices.

Callers may supply already-decoded preview payloads, a configured
PaddlePricingConfig used to POST /pricing-preview, or environment
settings resolved through resolve_country_prices() with a local fallback.
resolve_monthly_price() returns only the default display string.
"""

import logging
import math
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import requests
from babel.core import Locale
from babel.numbers import format_currency, get_currency_precision, list_currencies

import settings

PADDLE_SANDBOX_API_BASE = 'https://sandbox-api.paddle.com'
PADDLE_PRODUCTION_API_BASE = 'https://api.paddle.com'
PADDLE_SECRET_FILE = '/run/secrets/paddle_api_key'
PADDLE_ENVIRONMENTS = {
    'sandbox': PADDLE_SANDBOX_API_BASE,
    'production': PADDLE_PRODUCTION_API_BASE,
}
DISPLAY_LOCALE = 'en-US'
MONTHS_PER_YEAR = 12
PADDLE_API_VERSION = '1'
PADDLE_REQUEST_TIMEOUT = 10
PADDLE_MAX_ATTEMPTS = 3
PADDLE_RETRY_DELAY_SECONDS = 0.5
PADDLE_MAX_BUILD_RETRY_DELAY_SECONDS = 2

logger = logging.getLogger(__name__)


class PaddlePricingError(Exception):
    """Invalid Paddle configuration, request failure, or preview payload."""

    def __init__(self, message, request_id=None):
        self.request_id = request_id
        if request_id:
            message = f'{message} (Paddle request_id={request_id})'
        super().__init__(message)


@dataclass(frozen=True)
class PaddlePricingConfig:
    api_key: str | None
    environment: str | None
    price_id: str | None
    country: str | None
    required: bool

    @property
    def is_configured(self) -> bool:
        return all((self.api_key, self.environment, self.price_id, self.country))

    def __repr__(self) -> str:
        return (
            'PaddlePricingConfig('
            f'api_key={"set" if self.api_key else None}, '
            f'environment={self.environment!r}, '
            f'price_id={self.price_id!r}, '
            f'country={self.country!r}, '
            f'required={self.required})'
        )


@dataclass(frozen=True)
class MonthlyPrice:
    """Monthly-equivalent amount in the currency's minor units."""

    monthly_minor: int
    currency_code: str


@dataclass(frozen=True)
class CountryPricePreviews:
    """Complete approved-country previews.

    prices contains every approved country. Key order is fetch order, not
    display order.
    """

    default_country: str
    prices: Mapping[str, MonthlyPrice]


@dataclass(frozen=True)
class ResolvedCountryPrices:
    """Default display price, with previews only for a complete fetch.

    previews is None when the caller receives the display fallback.
    """

    default_price: str
    previews: CountryPricePreviews | None


def _optional_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_required(value):
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in {'1', 'true', 'yes', 'on'}:
        return True
    if text in {'0', 'false', 'no', 'off'}:
        return False
    raise PaddlePricingError(
        'TBPRO_PADDLE_REQUIRED must be one of: 1, true, yes, on, 0, false, no, off.'
    )


def read_api_key(environ=None, secret_path=PADDLE_SECRET_FILE):
    """Return a Paddle API key from a secret file or environment mapping.

    A readable non-empty secret file is preferred so Docker BuildKit mounts
    work without setting PADDLE_API_KEY. Otherwise PADDLE_API_KEY is used.
    The key is never written back to the environment.
    """
    if secret_path:
        path = Path(secret_path)
        try:
            if path.is_file():
                secret = path.read_text().strip()
                if secret:
                    return secret
        except OSError:
            pass

    if environ is None:
        return None
    return _optional_text(environ.get('PADDLE_API_KEY'))


def parse_config(environ, secret_path=PADDLE_SECRET_FILE):
    """Parse Paddle settings from an environment mapping and optional secret file.

    Completely unset configuration is valid. Any incomplete subset of the
    credential fields is a configuration error. HTTP is not performed.
    """
    api_key = read_api_key(environ, secret_path=secret_path)
    environment = _optional_text(environ.get('PADDLE_ENV'))
    price_id = _optional_text(environ.get('TBPRO_PADDLE_PRICE_ID'))
    country = _optional_text(environ.get('TBPRO_PADDLE_COUNTRY'))
    required = _parse_required(environ.get('TBPRO_PADDLE_REQUIRED'))

    present = [api_key is not None, environment is not None, price_id is not None, country is not None]
    if any(present) and not all(present):
        raise PaddlePricingError(
            'Partial Paddle configuration: PADDLE_API_KEY (or secret file), '
            'PADDLE_ENV, TBPRO_PADDLE_PRICE_ID, and TBPRO_PADDLE_COUNTRY '
            'must all be set together.'
        )

    if environment is not None and environment not in PADDLE_ENVIRONMENTS:
        raise PaddlePricingError(
            'PADDLE_ENV must be "sandbox" or "production".'
        )

    return PaddlePricingConfig(
        api_key=api_key,
        environment=environment,
        price_id=price_id,
        country=country,
        required=required,
    )


def _is_preview_country_code(code):
    """Return whether code is exactly two ASCII letters A-Z."""
    return (
        isinstance(code, str)
        and len(code) == 2
        and all('A' <= character <= 'Z' for character in code)
    )


def _validate_preview_countries(countries):
    """Return the approved country tuple, or raise before any Paddle request."""
    message = (
        'TBPRO_PADDLE_PREVIEW_COUNTRIES must be a non-empty tuple of unique '
        'two-letter uppercase ASCII country codes.'
    )
    if not isinstance(countries, tuple) or not countries:
        raise PaddlePricingError(message)
    seen = set()
    for code in countries:
        if not _is_preview_country_code(code) or code in seen:
            raise PaddlePricingError(message)
        seen.add(code)
    return countries


def _validate_default_country(country, countries):
    """Return country when it is an approved preview country."""
    if country not in countries:
        raise PaddlePricingError(
            'TBPRO_PADDLE_COUNTRY must be one of the approved preview countries.'
        )
    return country


def _country_fetch_order(default_country, countries):
    """Fetch the configured default first, then the remaining approved countries."""
    return (default_country,) + tuple(code for code in countries if code != default_country)


def paddle_api_base_url(environment):
    """Return the Paddle API base URL for a sandbox or production environment."""
    try:
        return PADDLE_ENVIRONMENTS[environment]
    except KeyError:
        raise PaddlePricingError(
            'PADDLE_ENV must be "sandbox" or "production".'
        ) from None


def _request_id(payload):
    meta = payload.get('meta') if isinstance(payload, dict) else None
    if not isinstance(meta, dict):
        return None
    return _optional_text(meta.get('request_id'))


def find_line_item(payload, price_id):
    """Return the preview line item whose price.id matches price_id."""
    request_id = _request_id(payload)
    data = payload.get('data', payload)
    try:
        line_items = data['details']['line_items']
    except (KeyError, TypeError):
        raise PaddlePricingError(
            'Paddle pricing preview is missing details.line_items.',
            request_id=request_id,
        ) from None

    if not isinstance(line_items, list):
        raise PaddlePricingError(
            'Paddle pricing preview details.line_items must be a list.',
            request_id=request_id,
        )

    for item in line_items:
        price = item.get('price') if isinstance(item, dict) else None
        if isinstance(price, dict) and price.get('id') == price_id:
            return item

    raise PaddlePricingError(
        f'Paddle pricing preview has no line item for price_id {price_id}.',
        request_id=request_id,
    )


def annual_to_monthly_minor(annual_minor):
    """Convert a yearly amount in minor units to a monthly equivalent.

    Compatible with Thunderbird Accounts' dinero.js allocate-first-share:
    leftover minor units are applied to the first share.
    """
    if not isinstance(annual_minor, int) or isinstance(annual_minor, bool) or annual_minor < 0:
        raise PaddlePricingError('Paddle totals.total must be a non-negative integer string.')
    remainder = annual_minor % MONTHS_PER_YEAR
    return annual_minor // MONTHS_PER_YEAR + (1 if remainder else 0)


def format_monthly_price(monthly_minor, currency, locale=DISPLAY_LOCALE):
    """Format minor units as a locale-aware currency string.

    Trailing decimal zeros are removed only when the amount is an integer,
    so $6.50 is preserved and $6.00 becomes $6.
    """
    if not currency or not isinstance(currency, str):
        raise PaddlePricingError('Paddle preview is missing a currency code.')
    if not isinstance(monthly_minor, int) or isinstance(monthly_minor, bool) or monthly_minor < 0:
        raise PaddlePricingError('Monthly amount must be a non-negative integer.')

    babel_locale = locale.replace('-', '_')
    if currency not in list_currencies():
        raise PaddlePricingError(f'Unsupported Paddle currency {currency}.')
    precision = get_currency_precision(currency)

    major = Decimal(monthly_minor).scaleb(-precision)
    formatted = format_currency(major, currency, locale=babel_locale)
    if precision == 0 or major != major.to_integral_value():
        return formatted

    decimal_symbol = Locale.parse(babel_locale).number_symbols.get('decimal', '.')
    integer_fraction = decimal_symbol + ('0' * precision)
    if formatted.endswith(integer_fraction):
        return formatted[:-len(integer_fraction)]
    return formatted


def _require_currency_code(currency_code, request_id):
    """Return currency_code, or raise with the preview request ID preserved."""
    if not currency_code or not isinstance(currency_code, str):
        raise PaddlePricingError(
            'Paddle preview is missing a currency code.',
            request_id=request_id,
        )
    if currency_code not in list_currencies():
        raise PaddlePricingError(
            f'Unsupported Paddle currency {currency_code}.',
            request_id=request_id,
        )
    return currency_code


def monthly_price_from_preview(payload, price_id):
    """Return normalized monthly price data from a pricing-preview payload."""
    request_id = _request_id(payload)
    data = payload.get('data', payload) if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise PaddlePricingError(
            'Paddle pricing preview payload is missing data.',
            request_id=request_id,
        )

    item = find_line_item(payload, price_id)
    price = item.get('price') if isinstance(item, dict) else None
    if not isinstance(price, dict):
        raise PaddlePricingError(
            'Paddle line item is missing price details.',
            request_id=request_id,
        )

    if price.get('status') != 'active':
        raise PaddlePricingError(
            f'Paddle price {price_id} must have status "active".',
            request_id=request_id,
        )

    billing_cycle = price.get('billing_cycle')
    if not isinstance(billing_cycle, dict):
        raise PaddlePricingError(
            'Paddle price is missing a billing cycle.',
            request_id=request_id,
        )
    try:
        frequency = int(billing_cycle.get('frequency'))
    except (TypeError, ValueError):
        raise PaddlePricingError(
            'Paddle price billing cycle frequency is invalid.',
            request_id=request_id,
        ) from None
    if billing_cycle.get('interval') != 'year' or frequency != 1:
        raise PaddlePricingError(
            'Paddle price must use a yearly billing cycle with frequency 1.',
            request_id=request_id,
        )

    totals = item.get('totals') if isinstance(item, dict) else None
    raw_total = totals.get('total') if isinstance(totals, dict) else None
    if not isinstance(raw_total, str) or not raw_total.strip().isdigit():
        raise PaddlePricingError(
            'Paddle line item totals.total must be a non-negative integer string.',
            request_id=request_id,
        )
    annual_minor = int(raw_total)

    try:
        monthly_minor = annual_to_monthly_minor(annual_minor)
    except PaddlePricingError as exc:
        raise PaddlePricingError(str(exc), request_id=request_id) from exc
    return MonthlyPrice(
        monthly_minor=monthly_minor,
        currency_code=_require_currency_code(data.get('currency_code'), request_id),
    )


def formatted_price_from_preview(payload, price_id):
    """Return a formatted monthly price from a Paddle pricing-preview payload."""
    price = monthly_price_from_preview(payload, price_id)
    return format_monthly_price(price.monthly_minor, price.currency_code)


def _is_retryable_status(status_code):
    return status_code == 429 or 500 <= status_code <= 599


def _backoff_delay(attempt):
    """Return the bounded exponential delay after a retryable failure."""
    return PADDLE_RETRY_DELAY_SECONDS * (2 ** attempt)


def _parse_retry_after(response):
    """Return a finite non-negative Retry-After in seconds, or None."""
    raw = response.headers.get('Retry-After') if response is not None else None
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def _delay_after_failure(attempt, response=None, status_code=None):
    """Return seconds to wait before the next attempt, or None to stop.

    A valid Retry-After longer than PADDLE_MAX_BUILD_RETRY_DELAY_SECONDS is
    not capped. Retrying sooner would ignore Paddle's rate-limit window, and
    sleeping for a long window would stall the static-site build, so the
    request fails immediately instead.
    """
    if status_code == 429:
        retry_after = _parse_retry_after(response)
        if retry_after is not None:
            if retry_after <= PADDLE_MAX_BUILD_RETRY_DELAY_SECONDS:
                return retry_after
            return None
    return _backoff_delay(attempt)


def _request_id_from_response(response):
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return _request_id(payload)


def _http_error(status_code, request_id=None):
    return PaddlePricingError(
        f'Paddle pricing preview failed (HTTP {status_code}).',
        request_id=request_id,
    )


def fetch_monthly_price_data(config, country_code):
    """POST /pricing-preview and return normalized monthly price data.

    Requires a fully configured PaddlePricingConfig. country_code selects
    the preview address and does not change config.country. Every request,
    HTTP, JSON, or payload failure raises PaddlePricingError. Local fallback
    is not applied here.
    """
    if not isinstance(config, PaddlePricingConfig) or not config.is_configured:
        raise PaddlePricingError('Paddle pricing is not fully configured.')
    if not _is_preview_country_code(country_code):
        raise PaddlePricingError(
            'Paddle pricing preview country_code must be two uppercase ASCII letters.'
        )

    url = '{0}/pricing-preview'.format(paddle_api_base_url(config.environment))
    headers = {
        'Authorization': 'Bearer {0}'.format(config.api_key),
        'Paddle-Version': PADDLE_API_VERSION,
        'Content-Type': 'application/json',
    }
    body = {
        'items': [{'price_id': config.price_id, 'quantity': 1}],
        'address': {'country_code': country_code},
    }

    last_error = None
    for attempt in range(PADDLE_MAX_ATTEMPTS):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=body,
                timeout=PADDLE_REQUEST_TIMEOUT,
            )
        except requests.Timeout as exc:
            last_error = PaddlePricingError('Paddle pricing preview request timed out.')
            if attempt + 1 >= PADDLE_MAX_ATTEMPTS:
                raise last_error from exc
            time.sleep(_backoff_delay(attempt))
            continue
        except requests.ConnectionError as exc:
            last_error = PaddlePricingError('Paddle pricing preview connection failed.')
            if attempt + 1 >= PADDLE_MAX_ATTEMPTS:
                raise last_error from exc
            time.sleep(_backoff_delay(attempt))
            continue
        except requests.RequestException as exc:
            raise PaddlePricingError('Paddle pricing preview request failed.') from exc

        request_id = _request_id_from_response(response)
        if response.status_code == 200:
            try:
                payload = response.json()
            except ValueError:
                raise PaddlePricingError(
                    'Paddle pricing preview returned invalid JSON (HTTP 200).',
                    request_id=request_id,
                ) from None
            if not isinstance(payload, dict):
                raise PaddlePricingError(
                    'Paddle pricing preview returned invalid JSON (HTTP 200).',
                    request_id=request_id,
                )
            return monthly_price_from_preview(payload, config.price_id)

        last_error = _http_error(response.status_code, request_id=request_id)
        if not _is_retryable_status(response.status_code) or attempt + 1 >= PADDLE_MAX_ATTEMPTS:
            raise last_error
        delay = _delay_after_failure(attempt, response, response.status_code)
        if delay is None:
            raise last_error
        time.sleep(delay)

    raise last_error


def fetch_monthly_price(config):
    """POST /pricing-preview and return a formatted monthly price.

    Requires a fully configured PaddlePricingConfig. Every request, HTTP,
    JSON, or payload failure raises PaddlePricingError. Local fallback is
    not applied here.
    """
    if not isinstance(config, PaddlePricingConfig) or not config.is_configured:
        raise PaddlePricingError('Paddle pricing is not fully configured.')
    price_data = fetch_monthly_price_data(config, config.country)
    return format_monthly_price(price_data.monthly_minor, price_data.currency_code)


def _country_pricing_error(country_code, exc):
    """Return a country-scoped error while preserving Paddle's request ID."""
    detail = str(exc)
    request_id = exc.request_id
    if request_id:
        suffix = f' (Paddle request_id={request_id})'
        if detail.endswith(suffix):
            detail = detail[:-len(suffix)]
    return PaddlePricingError(
        f'Country {country_code} pricing preview failed: {detail}',
        request_id=request_id,
    )


def _fetch_country_price_previews(config, countries, default_country):
    """Fetch every approved country, default first.

    Returns only after every country succeeds. A failure discards amounts
    already collected and does not request later countries.
    """
    prices = {}
    for country_code in _country_fetch_order(default_country, countries):
        try:
            prices[country_code] = fetch_monthly_price_data(config, country_code)
        except PaddlePricingError as exc:
            raise _country_pricing_error(country_code, exc) from exc
    return CountryPricePreviews(
        default_country=default_country,
        prices=prices,
    )


def _fallback_prices(fallback_price):
    return ResolvedCountryPrices(
        default_price=fallback_price,
        previews=None,
    )


def resolve_country_prices(fallback_price, environ=None, secret_path=PADDLE_SECRET_FILE):
    """Resolve approved-country previews and the default display price.

    fallback_price must already be a complete formatted string such as "$6".
    A configured fetch returns that default country's formatted price and the
    complete preview map. Unconfigured and optional fetch failures return the
    fallback with previews set to None. Required failures raise. The approved
    country list is validated even when Paddle is not configured.
    """
    if not isinstance(fallback_price, str) or not fallback_price.strip():
        raise PaddlePricingError(
            'fallback_price must be a non-empty formatted price string.'
        )

    countries = _validate_preview_countries(settings.TBPRO_PADDLE_PREVIEW_COUNTRIES)

    if environ is None:
        environ = os.environ

    config = parse_config(environ, secret_path=secret_path)
    if not config.is_configured:
        if config.required:
            raise PaddlePricingError(
                'Paddle pricing is required but not fully configured.'
            )
        return _fallback_prices(fallback_price)

    default_country = _validate_default_country(config.country, countries)
    try:
        previews = _fetch_country_price_previews(config, countries, default_country)
    except PaddlePricingError as exc:
        if config.required:
            raise
        logger.warning(
            'Paddle pricing preview failed; using fallback price. %s',
            exc,
        )
        return _fallback_prices(fallback_price)

    default_price_data = previews.prices[default_country]
    return ResolvedCountryPrices(
        default_price=format_monthly_price(
            default_price_data.monthly_minor,
            default_price_data.currency_code,
        ),
        previews=previews,
    )


def resolve_monthly_price(fallback_price, environ=None, secret_path=PADDLE_SECRET_FILE):
    """Return the default monthly display price from resolve_country_prices()."""
    return resolve_country_prices(
        fallback_price,
        environ=environ,
        secret_path=secret_path,
    ).default_price
