"""Unit tests for Paddle pricing configuration, preview parsing, HTTP fetch, and fallback."""

import json
import logging
import os
from unittest import mock

import pytest
import requests
from babel.core import Locale
from babel.numbers import format_currency, parse_pattern

import settings
from paddle_pricing import (
    PADDLE_API_VERSION,
    PADDLE_MAX_ATTEMPTS,
    PADDLE_MAX_BUILD_RETRY_DELAY_SECONDS,
    PADDLE_PRODUCTION_API_BASE,
    PADDLE_REQUEST_TIMEOUT,
    PADDLE_RETRY_DELAY_SECONDS,
    PADDLE_SANDBOX_API_BASE,
    CountryPricePreviews,
    MonthlyPrice,
    PaddlePricingConfig,
    PaddlePricingError,
    ResolvedCountryPrices,
    _integer_currency_pattern,
    annual_to_monthly_minor,
    fetch_monthly_price,
    fetch_monthly_price_data,
    find_line_item,
    format_monthly_price,
    formatted_price_from_preview,
    monthly_price_from_preview,
    paddle_api_base_url,
    parse_config,
    public_price_preview,
    read_api_key,
    resolve_country_prices,
    resolve_monthly_price,
)

PRICE_ID = 'pri_01tbpropriceid000000000001'
OTHER_PRICE_ID = 'pri_01tbpropriceid000000000002'


def preview_payload(
    *,
    price_id=PRICE_ID,
    total='7200',
    subtotal='9999',
    currency='USD',
    interval='year',
    frequency=1,
    status='active',
    extra_first=False,
    request_id='req-123',
):
    """Build a pricing-preview payload for parser tests.

    `subtotal` is intentionally different from `total` so tests fail if the
    parser reads the wrong totals field. `extra_first=True` inserts a
    nonmatching line item first to verify selection by price ID.
    """
    price = {
        'id': price_id,
        'billing_cycle': {
            'interval': interval,
            'frequency': frequency,
        },
    }
    if status is not None:
        price['status'] = status
    matching_item = {
        'price': price,
        'totals': {
            'subtotal': subtotal,
            'total': total,
        },
    }
    other_item = {
        'price': {
            'id': OTHER_PRICE_ID,
            'status': 'active',
            'billing_cycle': {'interval': 'year', 'frequency': 1},
        },
        'totals': {
            'subtotal': '100',
            'total': '100',
        },
    }
    line_items = [other_item, matching_item] if extra_first else [matching_item]
    data = {
        'details': {
            'line_items': line_items,
        },
    }
    if currency is not None:
        data['currency_code'] = currency
    return {
        'data': data,
        'meta': {
            'request_id': request_id,
        },
    }


API_KEY = 'super-secret-key'
MISSING_SECRET = '/definitely/missing/paddle_api_key'
FALLBACK_PRICE = '$6'


def configured_environ(required='0'):
    return {
        'PADDLE_API_KEY': API_KEY,
        'PADDLE_ENV': 'sandbox',
        'TBPRO_PADDLE_PRICE_ID': PRICE_ID,
        'TBPRO_PADDLE_COUNTRY': 'US',
        'TBPRO_PADDLE_REQUIRED': required,
    }


def configured_config(environment='sandbox'):
    return PaddlePricingConfig(
        api_key=API_KEY,
        environment=environment,
        price_id=PRICE_ID,
        country='US',
        required=True,
    )


def posted_countries(mock_post):
    return [
        call.kwargs['json']['address']['country_code']
        for call in mock_post.call_args_list
    ]


def fake_response(status_code=200, payload=None, headers=None, json_error=False):
    response = mock.Mock()
    response.status_code = status_code
    response.headers = headers or {}
    if json_error:
        response.json.side_effect = ValueError('No JSON object could be decoded')
    else:
        response.json.return_value = payload
    return response


class TestParseConfig:
    def test_unconfigured_is_valid(self):
        config = parse_config({}, secret_path='/definitely/missing/paddle_api_key')
        assert config.is_configured is False
        assert config.required is False
        assert config.api_key is None

    def test_partial_configuration_raises(self):
        with pytest.raises(PaddlePricingError, match='Partial Paddle configuration'):
            parse_config({
                'PADDLE_ENV': 'sandbox',
                'TBPRO_PADDLE_PRICE_ID': PRICE_ID,
            }, secret_path='/definitely/missing/paddle_api_key')

    def test_invalid_environment_raises(self):
        with pytest.raises(PaddlePricingError, match='sandbox'):
            parse_config({
                'PADDLE_API_KEY': 'pdl_sdbx_test',
                'PADDLE_ENV': 'live',
                'TBPRO_PADDLE_PRICE_ID': PRICE_ID,
                'TBPRO_PADDLE_COUNTRY': 'US',
            }, secret_path='/definitely/missing/paddle_api_key')

    def test_fully_configured_from_environ(self):
        config = parse_config({
            'PADDLE_API_KEY': 'pdl_sdbx_test',
            'PADDLE_ENV': 'sandbox',
            'TBPRO_PADDLE_PRICE_ID': PRICE_ID,
            'TBPRO_PADDLE_COUNTRY': 'US',
            'TBPRO_PADDLE_REQUIRED': '1',
        }, secret_path='/definitely/missing/paddle_api_key')
        assert config.is_configured is True
        assert config.required is True
        assert config.api_key == 'pdl_sdbx_test'
        assert config.environment == 'sandbox'
        assert config.price_id == PRICE_ID
        assert config.country == 'US'

    def test_fully_configured_production(self):
        config = parse_config({
            'PADDLE_API_KEY': 'pdl_live_test',
            'PADDLE_ENV': 'production',
            'TBPRO_PADDLE_PRICE_ID': PRICE_ID,
            'TBPRO_PADDLE_COUNTRY': 'US',
            'TBPRO_PADDLE_REQUIRED': '1',
        }, secret_path='/definitely/missing/paddle_api_key')
        assert config.is_configured is True
        assert config.environment == 'production'
        assert config.required is True

    def test_required_false_value(self):
        config = parse_config({
            'PADDLE_API_KEY': 'pdl_sdbx_test',
            'PADDLE_ENV': 'sandbox',
            'TBPRO_PADDLE_PRICE_ID': PRICE_ID,
            'TBPRO_PADDLE_COUNTRY': 'US',
            'TBPRO_PADDLE_REQUIRED': '0',
        }, secret_path='/definitely/missing/paddle_api_key')
        assert config.required is False

    def test_required_invalid_value_raises(self):
        with pytest.raises(PaddlePricingError, match='TBPRO_PADDLE_REQUIRED'):
            parse_config({
                'PADDLE_API_KEY': 'pdl_sdbx_test',
                'PADDLE_ENV': 'sandbox',
                'TBPRO_PADDLE_PRICE_ID': PRICE_ID,
                'TBPRO_PADDLE_COUNTRY': 'US',
                'TBPRO_PADDLE_REQUIRED': 'required',
            }, secret_path='/definitely/missing/paddle_api_key')

    def test_repr_does_not_include_api_key(self):
        config = parse_config({
            'PADDLE_API_KEY': 'super-secret-key',
            'PADDLE_ENV': 'production',
            'TBPRO_PADDLE_PRICE_ID': PRICE_ID,
            'TBPRO_PADDLE_COUNTRY': 'US',
        }, secret_path='/definitely/missing/paddle_api_key')
        rendered = repr(config)
        assert 'super-secret-key' not in rendered
        assert 'api_key=set' in rendered


class TestReadApiKey:
    def test_reads_environment_key(self):
        key = read_api_key(
            {'PADDLE_API_KEY': 'env-secret'},
            secret_path='/definitely/missing/paddle_api_key',
        )
        assert key == 'env-secret'

    def test_reads_secret_file(self, tmp_path):
        secret = tmp_path / 'paddle_api_key'
        secret.write_text('file-secret\n')
        key = read_api_key({}, secret_path=str(secret))
        assert key == 'file-secret'

    def test_prefers_secret_file_over_environment(self, tmp_path):
        secret = tmp_path / 'paddle_api_key'
        secret.write_text('file-secret')
        key = read_api_key(
            {'PADDLE_API_KEY': 'env-secret'},
            secret_path=str(secret),
        )
        assert key == 'file-secret'


class TestPaddleApiBaseUrl:
    def test_sandbox(self):
        assert paddle_api_base_url('sandbox') == PADDLE_SANDBOX_API_BASE

    def test_production(self):
        assert paddle_api_base_url('production') == PADDLE_PRODUCTION_API_BASE

    def test_rejects_live(self):
        with pytest.raises(PaddlePricingError):
            paddle_api_base_url('live')


class TestFindLineItem:
    def test_matches_price_id_not_first_item(self):
        payload = preview_payload(extra_first=True)
        item = find_line_item(payload, PRICE_ID)
        assert item['price']['id'] == PRICE_ID
        assert item['totals']['total'] == '7200'

    def test_missing_price_id_includes_request_id(self):
        payload = preview_payload()
        with pytest.raises(PaddlePricingError, match='request_id=req-123'):
            find_line_item(payload, 'pri_missing')


class TestAnnualToMonthlyMinor:
    def test_exact_division(self):
        assert annual_to_monthly_minor(7200) == 600

    def test_half_dollar(self):
        assert annual_to_monthly_minor(7800) == 650

    def test_remainder_goes_to_first_share(self):
        assert annual_to_monthly_minor(7201) == 601


class TestFormatMonthlyPrice:
    def test_usd_integer_strips_zeros(self):
        assert format_monthly_price(600, 'USD') == '$6'

    def test_usd_half_keeps_two_decimals(self):
        assert format_monthly_price(650, 'USD') == '$6.50'

    def test_usd_remainder_cents(self):
        assert format_monthly_price(601, 'USD') == '$6.01'

    def test_cad_prefix(self):
        assert format_monthly_price(1000, 'CAD') == 'CA$10'

    def test_jpy_zero_decimals(self):
        assert format_monthly_price(975, 'JPY') == '¥975'

    def test_german_suffix_integer_and_fraction(self):
        assert format_monthly_price(600, 'USD', locale='de') == '6\xa0$'
        assert format_monthly_price(650, 'USD', locale='de') == '6,50\xa0$'
        assert format_monthly_price(1000, 'CAD', locale='de') == '10\xa0CA$'

    def test_french_suffix(self):
        assert format_monthly_price(600, 'USD', locale='fr') == '6\xa0$US'

    def test_arabic_rtl_marks(self):
        assert format_monthly_price(600, 'USD', locale='ar') == '\u200f6\xa0US$'

    def test_bhd_three_decimals(self):
        assert format_monthly_price(1000, 'BHD') == 'BHD1'
        assert format_monthly_price(1500, 'BHD') == 'BHD1.500'
        assert format_monthly_price(1001, 'BHD') == 'BHD1.001'

    def test_integer_pattern_does_not_mutate_locale_pattern(self):
        standard = Locale.parse('en_US').currency_formats['standard']
        before = standard.frac_prec
        assert format_monthly_price(600, 'USD') == '$6'
        assert standard.frac_prec == before == (2, 2)

    def test_quoted_literal_is_preserved(self):
        parsed = parse_pattern("¤#,##0.00' (#,##0.00)'")
        copied = _integer_currency_pattern(parsed)
        assert copied is not parsed
        assert parsed.frac_prec == (2, 2)
        assert copied.frac_prec == (0, 0)
        for field in (
            'pattern', 'prefix', 'suffix', 'grouping', 'int_prec',
            'exp_prec', 'exp_plus', 'number_pattern',
        ):
            assert getattr(copied, field) == getattr(parsed, field)
        assert format_currency(
            6, 'USD', format=copied, locale='en_US', currency_digits=False,
        ) == '$6 (#,##0.00)'

    def test_explicit_negative_subpattern_is_copied(self):
        synthesized = parse_pattern('¤#,##0.00')
        explicit = parse_pattern('¤#,##0.00;¤-#,##0.00')
        assert explicit.prefix[1] != synthesized.prefix[1]
        copied = _integer_currency_pattern(explicit)
        assert copied.prefix == explicit.prefix
        assert copied.suffix == explicit.suffix
        assert explicit.frac_prec == (2, 2)
        assert format_currency(
            -6, 'USD', format=copied, locale='en_US', currency_digits=False,
        ) == '$-6'


class TestPublicPricePreview:
    def _previews(self, default_country='US'):
        return CountryPricePreviews(
            default_country=default_country,
            prices={
                'US': MonthlyPrice(monthly_minor=600, currency_code='USD'),
                'CA': MonthlyPrice(monthly_minor=1000, currency_code='CAD'),
            },
        )

    def test_en_us_exact_result_and_keys(self):
        previews = self._previews()
        result = public_price_preview(previews, Locale.parse('en_US'))
        assert result == {
            'defaultCountry': 'US',
            'countries': [
                {'code': 'CA', 'label': 'Canada', 'price': 'CA$10'},
                {'code': 'US', 'label': 'United States', 'price': '$6'},
            ],
        }
        assert set(result) == {'defaultCountry', 'countries'}
        for country in result['countries']:
            assert set(country) == {'code', 'label', 'price'}

    def test_page_locale_formatting_and_order(self):
        german = public_price_preview(self._previews(), Locale.parse('de'))
        assert [country['code'] for country in german['countries']] == ['CA', 'US']
        prices = {country['code']: country['price'] for country in german['countries']}
        assert prices == {'CA': '10\xa0CA$', 'US': '6\xa0$'}

        arabic = public_price_preview(self._previews(), Locale.parse('ar'))
        assert [country['code'] for country in arabic['countries']] == ['US', 'CA']

        canada_default = public_price_preview(self._previews('CA'), Locale.parse('de'))
        assert canada_default['defaultCountry'] == 'CA'

    def test_english_fallback_keeps_every_country(self):
        latgalian = public_price_preview(self._previews(), Locale.parse('ltg'))
        labels = {country['code']: country['label'] for country in latgalian['countries']}
        assert labels == {'CA': 'Canada', 'US': 'United States'}

        guarani = public_price_preview(self._previews(), Locale.parse('gn'))
        labels = {country['code']: country['label'] for country in guarani['countries']}
        assert labels['US'] == 'Estados Unidos'
        assert labels['CA'] == 'Canada'
        assert {country['code'] for country in guarani['countries']} == {'US', 'CA'}

    def test_duplicate_label_raises(self):
        class FakeLocale:
            territories = {'US': 'Canada', 'CA': 'Canada'}

            def __str__(self):
                return 'zz'

        with pytest.raises(PaddlePricingError, match='zz') as exc_info:
            public_price_preview(self._previews(), FakeLocale())
        message = str(exc_info.value)
        assert 'US' in message
        assert 'CA' in message
        assert 'Canada' in message

    def test_result_omits_internal_fields_and_does_not_mutate_previews(self):
        prices = {
            'US': MonthlyPrice(monthly_minor=600, currency_code='USD'),
            'CA': MonthlyPrice(monthly_minor=1000, currency_code='CAD'),
        }
        previews = CountryPricePreviews(default_country='US', prices=prices)
        result = public_price_preview(previews, Locale.parse('en_US'))
        encoded = json.dumps(result)
        for hidden in ('monthly_minor', 'currency_code', 'request_id', 'formatted_totals'):
            assert hidden not in encoded
        assert previews.prices is prices
        assert previews.default_country == 'US'
        assert prices['US'] == MonthlyPrice(monthly_minor=600, currency_code='USD')
        assert prices['CA'] == MonthlyPrice(monthly_minor=1000, currency_code='CAD')


class TestFormattedPriceFromPreview:
    def test_uses_matching_totals_total(self):
        payload = preview_payload(total='7200', subtotal='9999', extra_first=True)
        assert formatted_price_from_preview(payload, PRICE_ID) == '$6'

    def test_usd_six_fifty(self):
        payload = preview_payload(total='7800')
        assert formatted_price_from_preview(payload, PRICE_ID) == '$6.50'

    def test_usd_remainder_allocation(self):
        payload = preview_payload(total='7201')
        assert formatted_price_from_preview(payload, PRICE_ID) == '$6.01'

    def test_cad(self):
        payload = preview_payload(total='12000', currency='CAD')
        assert formatted_price_from_preview(payload, PRICE_ID) == 'CA$10'

    def test_jpy(self):
        payload = preview_payload(total='11700', currency='JPY')
        assert formatted_price_from_preview(payload, PRICE_ID) == '¥975'

    def test_non_year_cycle_raises(self):
        payload = preview_payload(interval='month')
        with pytest.raises(PaddlePricingError, match='yearly'):
            formatted_price_from_preview(payload, PRICE_ID)

    def test_yearly_frequency_two_raises(self):
        payload = preview_payload(interval='year', frequency=2)
        with pytest.raises(PaddlePricingError, match='frequency 1'):
            formatted_price_from_preview(payload, PRICE_ID)

    @pytest.mark.parametrize('total', ['abc', '72.00', '7200.5', ''])
    def test_non_integer_total_raises(self, total):
        payload = preview_payload(total=total)
        with pytest.raises(PaddlePricingError, match='request_id=req-123') as exc_info:
            formatted_price_from_preview(payload, PRICE_ID)
        assert 'integer string' in str(exc_info.value)

    def test_integer_total_is_rejected(self):
        payload = preview_payload(total=7200)
        with pytest.raises(PaddlePricingError, match='request_id=req-123') as exc_info:
            formatted_price_from_preview(payload, PRICE_ID)
        assert 'integer string' in str(exc_info.value)

    def test_missing_currency_code_raises(self):
        payload = preview_payload(currency=None)
        with pytest.raises(PaddlePricingError, match='currency'):
            formatted_price_from_preview(payload, PRICE_ID)

    def test_missing_totals_includes_request_id(self):
        payload = preview_payload()
        del payload['data']['details']['line_items'][0]['totals']
        with pytest.raises(PaddlePricingError, match='request_id=req-123'):
            formatted_price_from_preview(payload, PRICE_ID)

    def test_archived_price_raises(self):
        payload = preview_payload(status='archived')
        with pytest.raises(PaddlePricingError, match='request_id=req-123') as exc_info:
            formatted_price_from_preview(payload, PRICE_ID)
        assert 'active' in str(exc_info.value)

    def test_missing_price_status_raises(self):
        payload = preview_payload(status=None)
        with pytest.raises(PaddlePricingError, match='request_id=req-123') as exc_info:
            formatted_price_from_preview(payload, PRICE_ID)
        assert 'active' in str(exc_info.value)

    def test_unexpected_price_status_raises(self):
        payload = preview_payload(status='custom')
        with pytest.raises(PaddlePricingError, match='request_id=req-123') as exc_info:
            formatted_price_from_preview(payload, PRICE_ID)
        assert 'active' in str(exc_info.value)

    def test_unsupported_currency_raises(self):
        payload = preview_payload(currency='NOTACURRENCY')
        with pytest.raises(PaddlePricingError, match='currency'):
            formatted_price_from_preview(payload, PRICE_ID)


class TestFetchMonthlyPrice:
    def _assert_request(self, mock_post, base_url):
        mock_post.assert_called()
        args, kwargs = mock_post.call_args
        assert args == ('{0}/pricing-preview'.format(base_url),)
        assert kwargs['headers']['Authorization'] == 'Bearer {0}'.format(API_KEY)
        assert kwargs['headers']['Paddle-Version'] == PADDLE_API_VERSION
        assert kwargs['timeout'] == PADDLE_REQUEST_TIMEOUT
        assert kwargs['json'] == {
            'items': [{'price_id': PRICE_ID, 'quantity': 1}],
            'address': {'country_code': 'US'},
        }

    def test_sandbox_url_headers_body_and_timeout(self):
        mock_post = mock.Mock(return_value=fake_response(payload=preview_payload()))
        with mock.patch('paddle_pricing.requests.post', mock_post):
            price = fetch_monthly_price(configured_config('sandbox'))
        assert price == '$6'
        assert mock_post.call_count == 1
        self._assert_request(mock_post, PADDLE_SANDBOX_API_BASE)

    def test_production_url(self):
        mock_post = mock.Mock(return_value=fake_response(payload=preview_payload()))
        with mock.patch('paddle_pricing.requests.post', mock_post):
            price = fetch_monthly_price(configured_config('production'))
        assert price == '$6'
        self._assert_request(mock_post, PADDLE_PRODUCTION_API_BASE)

    def test_matches_price_that_is_not_first_line_item(self):
        mock_post = mock.Mock(
            return_value=fake_response(payload=preview_payload(extra_first=True))
        )
        with mock.patch('paddle_pricing.requests.post', mock_post):
            assert fetch_monthly_price(configured_config()) == '$6'

    def test_unconfigured_config_makes_no_request(self):
        mock_post = mock.Mock()
        with mock.patch('paddle_pricing.requests.post', mock_post):
            with pytest.raises(PaddlePricingError, match='not fully configured'):
                fetch_monthly_price(PaddlePricingConfig(
                    api_key=None,
                    environment=None,
                    price_id=None,
                    country=None,
                    required=False,
                ))
        mock_post.assert_not_called()

    @pytest.mark.parametrize('country_code', ['', 'us', 'USA', 'ÜS', None])
    def test_malformed_country_code_raises_without_request(self, country_code):
        mock_post = mock.Mock()
        with mock.patch('paddle_pricing.requests.post', mock_post):
            with pytest.raises(PaddlePricingError, match='uppercase ASCII') as exc_info:
                fetch_monthly_price_data(configured_config(), country_code)
        mock_post.assert_not_called()
        assert API_KEY not in str(exc_info.value)

    def test_http_400_is_not_retried(self):
        error_payload = {
            'error': {'code': 'bad_request', 'detail': 'invalid'},
            'meta': {'request_id': 'req-400'},
        }
        mock_post = mock.Mock(return_value=fake_response(status_code=400, payload=error_payload))
        with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
            with mock.patch('paddle_pricing.requests.post', mock_post):
                with pytest.raises(PaddlePricingError, match='HTTP 400') as exc_info:
                    fetch_monthly_price(configured_config())
        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()
        assert 'request_id=req-400' in str(exc_info.value)
        assert API_KEY not in str(exc_info.value)

    def test_http_429_short_retry_after_sleeps_exactly_then_succeeds(self):
        retry_after = PADDLE_MAX_BUILD_RETRY_DELAY_SECONDS
        mock_post = mock.Mock(side_effect=[
            fake_response(
                status_code=429,
                payload={'meta': {'request_id': 'req-429'}},
                headers={'Retry-After': str(retry_after)},
            ),
            fake_response(payload=preview_payload()),
        ])
        with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
            with mock.patch('paddle_pricing.requests.post', mock_post):
                assert fetch_monthly_price(configured_config()) == '$6'
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once_with(retry_after)

    def test_http_429_long_retry_after_is_not_retried(self):
        mock_post = mock.Mock(return_value=fake_response(
            status_code=429,
            payload={'meta': {'request_id': 'req-429-long'}},
            headers={'Retry-After': '60'},
        ))
        with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
            with mock.patch('paddle_pricing.requests.post', mock_post):
                with pytest.raises(PaddlePricingError, match='HTTP 429') as exc_info:
                    fetch_monthly_price(configured_config())
        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()
        assert 'request_id=req-429-long' in str(exc_info.value)
        assert API_KEY not in str(exc_info.value)

    @pytest.mark.parametrize('headers', [
        {},
        {'Retry-After': 'abc'},
        {'Retry-After': '-1'},
        {'Retry-After': 'nan'},
        {'Retry-After': 'inf'},
        {'Retry-After': '-inf'},
    ])
    def test_http_429_missing_or_malformed_retry_after_uses_backoff(self, headers):
        mock_post = mock.Mock(side_effect=[
            fake_response(
                status_code=429,
                payload={'meta': {'request_id': 'req-429'}},
                headers=headers,
            ),
            fake_response(payload=preview_payload()),
        ])
        with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
            with mock.patch('paddle_pricing.requests.post', mock_post):
                assert fetch_monthly_price(configured_config()) == '$6'
        mock_sleep.assert_called_once_with(PADDLE_RETRY_DELAY_SECONDS)

    def test_http_500_is_retried_then_succeeds(self):
        mock_post = mock.Mock(side_effect=[
            fake_response(status_code=500, payload={'meta': {'request_id': 'req-500'}}),
            fake_response(payload=preview_payload()),
        ])
        with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
            with mock.patch('paddle_pricing.requests.post', mock_post):
                assert fetch_monthly_price(configured_config()) == '$6'
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once_with(PADDLE_RETRY_DELAY_SECONDS)

    def test_timeout_retries_use_increasing_bounded_delays(self):
        mock_post = mock.Mock(side_effect=requests.Timeout())
        with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
            with mock.patch('paddle_pricing.requests.post', mock_post):
                with pytest.raises(PaddlePricingError, match='timed out') as exc_info:
                    fetch_monthly_price(configured_config())
        assert mock_post.call_count == PADDLE_MAX_ATTEMPTS
        assert mock_sleep.call_args_list == [
            mock.call(PADDLE_RETRY_DELAY_SECONDS),
            mock.call(PADDLE_RETRY_DELAY_SECONDS * 2),
        ]
        assert API_KEY not in str(exc_info.value)

    def test_connection_failure_retries_use_increasing_bounded_delays(self):
        mock_post = mock.Mock(side_effect=requests.ConnectionError())
        with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
            with mock.patch('paddle_pricing.requests.post', mock_post):
                with pytest.raises(PaddlePricingError, match='connection failed') as exc_info:
                    fetch_monthly_price(configured_config())
        assert mock_post.call_count == PADDLE_MAX_ATTEMPTS
        assert mock_sleep.call_args_list == [
            mock.call(PADDLE_RETRY_DELAY_SECONDS),
            mock.call(PADDLE_RETRY_DELAY_SECONDS * 2),
        ]
        assert API_KEY not in str(exc_info.value)

    def test_generic_request_exception_is_not_retried(self):
        mock_post = mock.Mock(side_effect=requests.RequestException('upstream failed'))
        with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
            with mock.patch('paddle_pricing.requests.post', mock_post):
                with pytest.raises(PaddlePricingError, match='request failed') as exc_info:
                    fetch_monthly_price(configured_config())
        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()
        assert API_KEY not in str(exc_info.value)

    def test_exhausted_transient_http_failures_raise(self):
        mock_post = mock.Mock(return_value=fake_response(
            status_code=503,
            payload={'meta': {'request_id': 'req-503'}},
        ))
        with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
            with mock.patch('paddle_pricing.requests.post', mock_post):
                with pytest.raises(PaddlePricingError, match='HTTP 503') as exc_info:
                    fetch_monthly_price(configured_config())
        assert mock_post.call_count == PADDLE_MAX_ATTEMPTS
        assert mock_sleep.call_args_list == [
            mock.call(PADDLE_RETRY_DELAY_SECONDS),
            mock.call(PADDLE_RETRY_DELAY_SECONDS * 2),
        ]
        assert 'request_id=req-503' in str(exc_info.value)
        assert API_KEY not in str(exc_info.value)

    def test_invalid_json_raises(self):
        mock_post = mock.Mock(return_value=fake_response(json_error=True))
        with mock.patch('paddle_pricing.requests.post', mock_post):
            with pytest.raises(PaddlePricingError, match='invalid JSON') as exc_info:
                fetch_monthly_price(configured_config())
        assert API_KEY not in str(exc_info.value)

    def test_invalid_successful_payload_raises(self):
        mock_post = mock.Mock(return_value=fake_response(payload={'data': {}, 'meta': {'request_id': 'req-bad'}}))
        with mock.patch('paddle_pricing.requests.post', mock_post):
            with pytest.raises(PaddlePricingError, match='request_id=req-bad') as exc_info:
                fetch_monthly_price(configured_config())
        assert API_KEY not in str(exc_info.value)


class TestResolveMonthlyPrice:
    def test_valid_fallback_is_returned_unchanged(self):
        fallback = FALLBACK_PRICE
        assert resolve_monthly_price(
            fallback,
            environ={},
            secret_path=MISSING_SECRET,
        ) == fallback

    @pytest.mark.parametrize('fallback', [None, '', '   ', 6, True, ['$6']])
    def test_empty_missing_or_non_string_fallback_is_rejected(self, fallback):
        mock_post = mock.Mock()
        with mock.patch('paddle_pricing.requests.post', mock_post):
            with pytest.raises(PaddlePricingError, match='fallback_price'):
                resolve_monthly_price(fallback, environ={}, secret_path=MISSING_SECRET)
        mock_post.assert_not_called()

    def test_unconfigured_optional_returns_fallback_and_makes_no_request(self):
        mock_post = mock.Mock()
        with mock.patch('paddle_pricing.requests.post', mock_post):
            price = resolve_monthly_price(
                FALLBACK_PRICE,
                environ={},
                secret_path=MISSING_SECRET,
            )
        assert price == FALLBACK_PRICE
        mock_post.assert_not_called()

    def test_unconfigured_required_raises_and_makes_no_request(self):
        mock_post = mock.Mock()
        with mock.patch('paddle_pricing.requests.post', mock_post):
            with pytest.raises(PaddlePricingError, match='required') as exc_info:
                resolve_monthly_price(
                    FALLBACK_PRICE,
                    environ={'TBPRO_PADDLE_REQUIRED': '1'},
                    secret_path=MISSING_SECRET,
                )
        mock_post.assert_not_called()
        assert API_KEY not in str(exc_info.value)

    def test_partial_configuration_raises_and_makes_no_request(self):
        mock_post = mock.Mock()
        with mock.patch('paddle_pricing.requests.post', mock_post):
            with pytest.raises(PaddlePricingError, match='Partial Paddle configuration') as exc_info:
                resolve_monthly_price(
                    FALLBACK_PRICE,
                    environ={
                        'PADDLE_ENV': 'sandbox',
                        'TBPRO_PADDLE_PRICE_ID': PRICE_ID,
                    },
                    secret_path=MISSING_SECRET,
                )
        mock_post.assert_not_called()
        assert API_KEY not in str(exc_info.value)

    def test_configured_fetch_returns_paddle_price(self):
        price_data = MonthlyPrice(monthly_minor=650, currency_code='USD')
        with mock.patch('paddle_pricing.fetch_monthly_price_data', return_value=price_data) as mock_fetch:
            price = resolve_monthly_price(
                FALLBACK_PRICE,
                environ=configured_environ(),
                secret_path=MISSING_SECRET,
            )
        assert price == '$6.50'
        assert [call.args[1] for call in mock_fetch.call_args_list] == ['US', 'CA']

    def test_successful_fetch_emits_no_warning(self, caplog):
        price_data = MonthlyPrice(monthly_minor=650, currency_code='USD')
        with caplog.at_level(logging.WARNING, logger='paddle_pricing'):
            with mock.patch('paddle_pricing.fetch_monthly_price_data', return_value=price_data):
                price = resolve_monthly_price(
                    FALLBACK_PRICE,
                    environ=configured_environ(),
                    secret_path=MISSING_SECRET,
                )
        assert price == '$6.50'
        assert caplog.records == []

    def test_optional_configured_fetch_failure_returns_fallback(self):
        fallback = FALLBACK_PRICE
        with mock.patch(
            'paddle_pricing.fetch_monthly_price_data',
            side_effect=PaddlePricingError('HTTP 503', request_id='req-503'),
        ):
            price = resolve_monthly_price(
                fallback,
                environ=configured_environ('0'),
                secret_path=MISSING_SECRET,
            )
        assert price == fallback

    def test_optional_configured_fetch_failure_emits_one_safe_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger='paddle_pricing'):
            with mock.patch(
                'paddle_pricing.fetch_monthly_price_data',
                side_effect=PaddlePricingError('HTTP 503', request_id='req-503'),
            ):
                price = resolve_monthly_price(
                    FALLBACK_PRICE,
                    environ=configured_environ('0'),
                    secret_path=MISSING_SECRET,
                )
        assert price == FALLBACK_PRICE
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.WARNING
        message = caplog.records[0].getMessage()
        assert API_KEY not in message
        assert 'Authorization' not in message
        assert 'super-secret-key' not in message

    def test_optional_failure_warning_includes_request_id(self, caplog):
        with caplog.at_level(logging.WARNING, logger='paddle_pricing'):
            with mock.patch(
                'paddle_pricing.fetch_monthly_price_data',
                side_effect=PaddlePricingError('HTTP 503', request_id='req-503'),
            ):
                resolve_monthly_price(
                    FALLBACK_PRICE,
                    environ=configured_environ('0'),
                    secret_path=MISSING_SECRET,
                )
        assert 'request_id=req-503' in caplog.records[0].getMessage()

    def test_required_configured_fetch_failure_is_reraised(self):
        with mock.patch(
            'paddle_pricing.fetch_monthly_price_data',
            side_effect=PaddlePricingError('HTTP 503', request_id='req-503'),
        ):
            with pytest.raises(PaddlePricingError, match='HTTP 503') as exc_info:
                resolve_monthly_price(
                    FALLBACK_PRICE,
                    environ=configured_environ('1'),
                    secret_path=MISSING_SECRET,
                )
        assert 'request_id=req-503' in str(exc_info.value)
        assert API_KEY not in str(exc_info.value)

    def test_required_fetch_failure_does_not_emit_fallback_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger='paddle_pricing'):
            with mock.patch(
                'paddle_pricing.fetch_monthly_price_data',
                side_effect=PaddlePricingError('HTTP 503', request_id='req-503'),
            ):
                with pytest.raises(PaddlePricingError, match='HTTP 503'):
                    resolve_monthly_price(
                        FALLBACK_PRICE,
                        environ=configured_environ('1'),
                        secret_path=MISSING_SECRET,
                    )
        assert caplog.records == []

    def test_unexpected_exception_propagates(self):
        with mock.patch('paddle_pricing.fetch_monthly_price_data', side_effect=RuntimeError('boom')):
            with pytest.raises(RuntimeError, match='boom'):
                resolve_monthly_price(
                    FALLBACK_PRICE,
                    environ=configured_environ('0'),
                    secret_path=MISSING_SECRET,
                )

    def test_default_environ_reads_os_environ(self):
        with mock.patch.dict(os.environ, configured_environ(), clear=True):
            with mock.patch(
                'paddle_pricing.fetch_monthly_price_data',
                return_value=MonthlyPrice(monthly_minor=650, currency_code='USD'),
            ) as mock_fetch:
                price = resolve_monthly_price(FALLBACK_PRICE, secret_path=MISSING_SECRET)
        assert price == '$6.50'
        config = mock_fetch.call_args.args[0]
        assert config.api_key == API_KEY
        assert config.price_id == PRICE_ID

    def test_exceptions_and_logs_do_not_expose_api_key(self, caplog):
        fetch_error = PaddlePricingError('HTTP 503', request_id='req-503')
        with caplog.at_level(logging.WARNING, logger='paddle_pricing'):
            with mock.patch('paddle_pricing.fetch_monthly_price_data', side_effect=fetch_error):
                optional_price = resolve_monthly_price(
                    FALLBACK_PRICE,
                    environ=configured_environ('0'),
                    secret_path=MISSING_SECRET,
                )
                with pytest.raises(PaddlePricingError) as exc_info:
                    resolve_monthly_price(
                        FALLBACK_PRICE,
                        environ=configured_environ('1'),
                        secret_path=MISSING_SECRET,
                    )
        assert optional_price == FALLBACK_PRICE
        logged = ' '.join(record.getMessage() for record in caplog.records)
        assert API_KEY not in logged
        assert API_KEY not in str(exc_info.value)
        assert 'Authorization' not in logged
        assert 'Authorization' not in str(exc_info.value)


class TestMonthlyPriceFromPreview:
    def test_usd_integer(self):
        assert monthly_price_from_preview(preview_payload(total='7200'), PRICE_ID) == MonthlyPrice(
            monthly_minor=600,
            currency_code='USD',
        )

    def test_usd_half(self):
        assert monthly_price_from_preview(preview_payload(total='7800'), PRICE_ID) == MonthlyPrice(
            monthly_minor=650,
            currency_code='USD',
        )

    def test_usd_remainder(self):
        assert monthly_price_from_preview(preview_payload(total='7201'), PRICE_ID) == MonthlyPrice(
            monthly_minor=601,
            currency_code='USD',
        )

    def test_jpy_zero_decimals(self):
        assert monthly_price_from_preview(
            preview_payload(total='11700', currency='JPY'),
            PRICE_ID,
        ) == MonthlyPrice(monthly_minor=975, currency_code='JPY')

    def test_unsupported_currency_preserves_request_id(self):
        payload = preview_payload(currency='NOTACURRENCY')
        with pytest.raises(PaddlePricingError, match='request_id=req-123') as exc_info:
            monthly_price_from_preview(payload, PRICE_ID)
        message = str(exc_info.value)
        assert 'Unsupported Paddle currency NOTACURRENCY.' in message
        assert message.count('request_id=') == 1

    def test_missing_currency_preserves_request_id(self):
        payload = preview_payload(currency=None)
        with pytest.raises(PaddlePricingError, match='request_id=req-123') as exc_info:
            monthly_price_from_preview(payload, PRICE_ID)
        assert str(exc_info.value).count('request_id=') == 1


class TestResolveCountryPrices:
    def test_approved_preview_countries(self):
        assert settings.TBPRO_PADDLE_PREVIEW_COUNTRIES == ('US', 'CA')

    @pytest.mark.parametrize('countries', [
        ['US', 'CA'],
        (),
        ('US', 'US'),
        ('us',),
        ('USA',),
        ('ÜS',),
    ])
    def test_invalid_allowlist_raises_without_request(self, countries):
        mock_post = mock.Mock()
        with mock.patch('paddle_pricing.requests.post', mock_post):
            with mock.patch(
                'paddle_pricing.settings.TBPRO_PADDLE_PREVIEW_COUNTRIES',
                countries,
            ):
                with pytest.raises(PaddlePricingError, match='TBPRO_PADDLE_PREVIEW_COUNTRIES'):
                    resolve_country_prices(
                        FALLBACK_PRICE,
                        environ={},
                        secret_path=MISSING_SECRET,
                    )
        mock_post.assert_not_called()

    def test_unconfigured_optional_has_no_preview_map(self):
        mock_post = mock.Mock()
        with mock.patch('paddle_pricing.requests.post', mock_post):
            result = resolve_country_prices(
                FALLBACK_PRICE,
                environ={},
                secret_path=MISSING_SECRET,
            )
            wrapped = resolve_monthly_price(
                FALLBACK_PRICE,
                environ={},
                secret_path=MISSING_SECRET,
            )
        assert result.default_price == FALLBACK_PRICE
        assert result.previews is None
        assert wrapped == result.default_price
        mock_post.assert_not_called()

    @pytest.mark.parametrize('required', ['0', '1'])
    def test_default_outside_allowlist_raises_before_http(self, required):
        mock_post = mock.Mock()
        environ = configured_environ(required)
        environ['TBPRO_PADDLE_COUNTRY'] = 'GB'
        with mock.patch('paddle_pricing.requests.post', mock_post):
            with pytest.raises(PaddlePricingError, match='approved preview countries') as exc_info:
                resolve_country_prices(
                    FALLBACK_PRICE,
                    environ=environ,
                    secret_path=MISSING_SECRET,
                )
        mock_post.assert_not_called()
        assert API_KEY not in str(exc_info.value)

    def test_successful_preview_map(self):
        mock_post = mock.Mock(side_effect=[
            fake_response(payload=preview_payload(total='7200', currency='USD')),
            fake_response(payload=preview_payload(total='12000', currency='CAD')),
        ])
        with mock.patch('paddle_pricing.requests.post', mock_post):
            result = resolve_country_prices(
                FALLBACK_PRICE,
                environ=configured_environ('1'),
                secret_path=MISSING_SECRET,
            )
        assert posted_countries(mock_post) == ['US', 'CA']
        assert result.default_price == '$6'
        assert result.previews.default_country == 'US'
        assert set(result.previews.prices) == {'US', 'CA'}
        assert result.previews.prices['US'] == MonthlyPrice(monthly_minor=600, currency_code='USD')
        assert result.previews.prices['CA'] == MonthlyPrice(monthly_minor=1000, currency_code='CAD')

    def test_monthly_price_wrapper_returns_default_price(self):
        resolved = ResolvedCountryPrices(default_price='$6.50', previews=None)
        with mock.patch('paddle_pricing.resolve_country_prices', return_value=resolved) as mock_resolve:
            price = resolve_monthly_price(
                FALLBACK_PRICE,
                environ={},
                secret_path=MISSING_SECRET,
            )
        assert price == '$6.50'
        mock_resolve.assert_called_once_with(
            FALLBACK_PRICE,
            environ={},
            secret_path=MISSING_SECRET,
        )

    def test_configured_canada_default_is_formatted_from_canada(self):
        environ = configured_environ('1')
        environ['TBPRO_PADDLE_COUNTRY'] = 'CA'
        mock_post = mock.Mock(side_effect=[
            fake_response(payload=preview_payload(total='12000', currency='CAD')),
            fake_response(payload=preview_payload(total='7200', currency='USD')),
        ])
        with mock.patch('paddle_pricing.requests.post', mock_post):
            result = resolve_country_prices(
                FALLBACK_PRICE,
                environ=environ,
                secret_path=MISSING_SECRET,
            )
        assert posted_countries(mock_post) == ['CA', 'US']
        assert result.previews.default_country == 'CA'
        assert result.previews.prices['CA'] == MonthlyPrice(monthly_minor=1000, currency_code='CAD')
        assert result.previews.prices['US'] == MonthlyPrice(monthly_minor=600, currency_code='USD')
        assert result.default_price == 'CA$10'

    def test_country_context_preserves_request_id(self):
        with mock.patch(
            'paddle_pricing.fetch_monthly_price_data',
            side_effect=PaddlePricingError('HTTP 400', request_id='req-400'),
        ):
            with pytest.raises(PaddlePricingError, match='Country US') as exc_info:
                resolve_country_prices(
                    FALLBACK_PRICE,
                    environ=configured_environ('1'),
                    secret_path=MISSING_SECRET,
                )
        error = exc_info.value
        message = str(error)
        assert error.request_id == 'req-400'
        assert 'Country US pricing preview failed:' in message
        assert message.count('request_id=') == 1
        assert message.endswith('(Paddle request_id=req-400)')

    def test_optional_fetch_failure_has_no_preview_map(self, caplog):
        with caplog.at_level(logging.WARNING, logger='paddle_pricing'):
            with mock.patch(
                'paddle_pricing.fetch_monthly_price_data',
                side_effect=PaddlePricingError('HTTP 400', request_id='req-400'),
            ) as mock_fetch:
                result = resolve_country_prices(
                    FALLBACK_PRICE,
                    environ=configured_environ('0'),
                    secret_path=MISSING_SECRET,
                )
        assert result.default_price == FALLBACK_PRICE
        assert result.previews is None
        assert mock_fetch.call_count == 1
        assert len(caplog.records) == 1
        message = caplog.records[0].getMessage()
        assert 'Country US pricing preview failed:' in message
        assert message.count('request_id=') == 1
        assert API_KEY not in message

    def test_http_400_does_not_request_later_country(self):
        mock_post = mock.Mock(side_effect=[
            fake_response(payload=preview_payload(total='7200', currency='USD')),
            fake_response(status_code=400, payload={'meta': {'request_id': 'req-ca'}}),
        ])
        with mock.patch('paddle_pricing.settings.TBPRO_PADDLE_PREVIEW_COUNTRIES', ('US', 'CA', 'MX')):
            with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
                with mock.patch('paddle_pricing.requests.post', mock_post):
                    with pytest.raises(PaddlePricingError, match='Country CA') as exc_info:
                        resolve_country_prices(
                            FALLBACK_PRICE,
                            environ=configured_environ('1'),
                            secret_path=MISSING_SECRET,
                        )
        assert posted_countries(mock_post) == ['US', 'CA']
        mock_sleep.assert_not_called()
        message = str(exc_info.value)
        assert 'MX' not in message
        assert message.count('request_id=') == 1
        assert API_KEY not in message
        assert 'Authorization' not in message

    def test_http_503_exhausts_retries_before_later_country(self, caplog):
        mock_post = mock.Mock(side_effect=[
            fake_response(payload=preview_payload(total='7200', currency='USD')),
            fake_response(status_code=503, payload={'meta': {'request_id': 'req-ca'}}),
            fake_response(status_code=503, payload={'meta': {'request_id': 'req-ca'}}),
            fake_response(status_code=503, payload={'meta': {'request_id': 'req-ca'}}),
        ])
        with caplog.at_level(logging.WARNING, logger='paddle_pricing'):
            with mock.patch('paddle_pricing.settings.TBPRO_PADDLE_PREVIEW_COUNTRIES', ('US', 'CA', 'MX')):
                with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
                    with mock.patch('paddle_pricing.requests.post', mock_post):
                        result = resolve_country_prices(
                            FALLBACK_PRICE,
                            environ=configured_environ('0'),
                            secret_path=MISSING_SECRET,
                        )
        assert posted_countries(mock_post) == ['US', 'CA', 'CA', 'CA']
        assert mock_sleep.call_args_list == [
            mock.call(PADDLE_RETRY_DELAY_SECONDS),
            mock.call(PADDLE_RETRY_DELAY_SECONDS * 2),
        ]
        assert result.default_price == FALLBACK_PRICE
        assert result.previews is None
        assert len(caplog.records) == 1
        message = caplog.records[0].getMessage()
        assert 'Country CA pricing preview failed:' in message
        assert message.count('request_id=') == 1
        assert API_KEY not in message

    def test_required_http_503_does_not_warn_or_continue(self, caplog):
        mock_post = mock.Mock(side_effect=[
            fake_response(payload=preview_payload(total='7200', currency='USD')),
            fake_response(status_code=503, payload={'meta': {'request_id': 'req-ca'}}),
            fake_response(status_code=503, payload={'meta': {'request_id': 'req-ca'}}),
            fake_response(status_code=503, payload={'meta': {'request_id': 'req-ca'}}),
        ])
        with caplog.at_level(logging.WARNING, logger='paddle_pricing'):
            with mock.patch('paddle_pricing.settings.TBPRO_PADDLE_PREVIEW_COUNTRIES', ('US', 'CA', 'MX')):
                with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
                    with mock.patch('paddle_pricing.requests.post', mock_post):
                        with pytest.raises(PaddlePricingError, match='Country CA'):
                            resolve_country_prices(
                                FALLBACK_PRICE,
                                environ=configured_environ('1'),
                                secret_path=MISSING_SECRET,
                            )
        assert posted_countries(mock_post) == ['US', 'CA', 'CA', 'CA']
        assert mock_sleep.call_args_list == [
            mock.call(PADDLE_RETRY_DELAY_SECONDS),
            mock.call(PADDLE_RETRY_DELAY_SECONDS * 2),
        ]
        assert caplog.records == []

    def test_default_canada_http_400_does_not_request_us(self):
        mock_post = mock.Mock(return_value=fake_response(
            status_code=400,
            payload={'meta': {'request_id': 'req-ca'}},
        ))
        environ = configured_environ('1')
        environ['TBPRO_PADDLE_COUNTRY'] = 'CA'
        with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
            with mock.patch('paddle_pricing.requests.post', mock_post):
                with pytest.raises(PaddlePricingError, match='Country CA') as exc_info:
                    resolve_country_prices(
                        FALLBACK_PRICE,
                        environ=environ,
                        secret_path=MISSING_SECRET,
                    )
        assert posted_countries(mock_post) == ['CA']
        mock_sleep.assert_not_called()
        assert str(exc_info.value).count('request_id=') == 1

    def test_default_canada_http_503_does_not_request_us(self, caplog):
        mock_post = mock.Mock(return_value=fake_response(
            status_code=503,
            payload={'meta': {'request_id': 'req-ca'}},
        ))
        environ = configured_environ('0')
        environ['TBPRO_PADDLE_COUNTRY'] = 'CA'
        with caplog.at_level(logging.WARNING, logger='paddle_pricing'):
            with mock.patch('paddle_pricing.time.sleep') as mock_sleep:
                with mock.patch('paddle_pricing.requests.post', mock_post):
                    result = resolve_country_prices(
                        FALLBACK_PRICE,
                        environ=environ,
                        secret_path=MISSING_SECRET,
                    )
        assert posted_countries(mock_post) == ['CA', 'CA', 'CA']
        assert mock_sleep.call_args_list == [
            mock.call(PADDLE_RETRY_DELAY_SECONDS),
            mock.call(PADDLE_RETRY_DELAY_SECONDS * 2),
        ]
        assert result.default_price == FALLBACK_PRICE
        assert result.previews is None
        assert len(caplog.records) == 1
        assert 'Country CA pricing preview failed:' in caplog.records[0].getMessage()
