"""Parse Paddle pricing configuration and retrieve formatted monthly prices.

Callers may supply already-decoded preview payloads, a configured
PaddlePricingConfig used to POST /pricing-preview, or environment
settings resolved through resolve_monthly_price() with a local fallback.
"""

import logging
import math
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import requests
from babel.core import Locale
from babel.numbers import format_currency, get_currency_precision, list_currencies

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


def formatted_price_from_preview(payload, price_id):
    """Return a formatted monthly price from a Paddle pricing-preview payload."""
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

    currency = data.get('currency_code')
    try:
        monthly_minor = annual_to_monthly_minor(annual_minor)
        return format_monthly_price(monthly_minor, currency)
    except PaddlePricingError as exc:
        raise PaddlePricingError(str(exc), request_id=request_id) from exc


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


def fetch_monthly_price(config):
    """POST /pricing-preview and return a formatted monthly price.

    Requires a fully configured PaddlePricingConfig. Every request, HTTP,
    JSON, or payload failure raises PaddlePricingError. Local fallback is
    not applied here.
    """
    if not isinstance(config, PaddlePricingConfig) or not config.is_configured:
        raise PaddlePricingError('Paddle pricing is not fully configured.')

    url = '{0}/pricing-preview'.format(paddle_api_base_url(config.environment))
    headers = {
        'Authorization': 'Bearer {0}'.format(config.api_key),
        'Paddle-Version': PADDLE_API_VERSION,
        'Content-Type': 'application/json',
    }
    body = {
        'items': [{'price_id': config.price_id, 'quantity': 1}],
        'address': {'country_code': config.country},
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
            return formatted_price_from_preview(payload, config.price_id)

        last_error = _http_error(response.status_code, request_id=request_id)
        if not _is_retryable_status(response.status_code) or attempt + 1 >= PADDLE_MAX_ATTEMPTS:
            raise last_error
        delay = _delay_after_failure(attempt, response, response.status_code)
        if delay is None:
            raise last_error
        time.sleep(delay)

    raise last_error


def resolve_monthly_price(fallback_price, environ=None, secret_path=PADDLE_SECRET_FILE):
    """Resolve a monthly display price from Paddle or a local fallback.

    fallback_price must already be a complete formatted string such as "$6".
    It is returned unchanged when fallback is allowed. Completely unset
    optional configuration is silent; a configured fetch failure in
    optional mode logs one warning.
    """
    if not isinstance(fallback_price, str) or not fallback_price.strip():
        raise PaddlePricingError(
            'fallback_price must be a non-empty formatted price string.'
        )

    if environ is None:
        environ = os.environ

    config = parse_config(environ, secret_path=secret_path)
    if not config.is_configured:
        if config.required:
            raise PaddlePricingError(
                'Paddle pricing is required but not fully configured.'
            )
        return fallback_price

    try:
        return fetch_monthly_price(config)
    except PaddlePricingError as exc:
        if config.required:
            raise
        logger.warning(
            'Paddle pricing preview failed; using fallback price. %s',
            exc,
        )
        return fallback_price
