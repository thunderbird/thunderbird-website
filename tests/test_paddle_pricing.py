"""Unit tests for Paddle pricing configuration, preview parsing, and formatting."""

import pytest

from paddle_pricing import (
    PADDLE_PRODUCTION_API_BASE,
    PADDLE_SANDBOX_API_BASE,
    PaddlePricingError,
    annual_to_monthly_minor,
    find_line_item,
    format_monthly_price,
    formatted_price_from_preview,
    paddle_api_base_url,
    parse_config,
    read_api_key,
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
