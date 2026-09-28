"""Tests for wiring resolved Paddle prices into tb.pro builds and the subscription-plan macro."""

import os
import runpy
import sys
from unittest import mock

import pytest
from jinja2 import Environment, FileSystemLoader

import builder
import settings
from paddle_pricing import CountryPricePreviews, MonthlyPrice, ResolvedCountryPrices


BUILD_SITE = os.path.join(os.path.dirname(__file__), '..', 'build-site.py')
RESOLVED_PRICE = '$6.50'
PADDLE_ENV_KEYS = (
    'PADDLE_API_KEY',
    'PADDLE_ENV',
    'TBPRO_PADDLE_PRICE_ID',
    'TBPRO_PADDLE_COUNTRY',
    'TBPRO_PADDLE_REQUIRED',
)

CONTROLLED_PLAN = {
    'name': 'Controlled Plan',
    'description': 'A test-only plan dictionary',
    'price': '6',
    'period': 'per month,<br>paid annually',
    'cta_label': 'Join Waitlist',
    'mail_storage': '11',
    'send_storage': '22',
    'num_domains': '4',
    'num_inboxes': '2',
    'num_email_addresses': '8',
}


def _controlled_plan():
    return CONTROLLED_PLAN.copy()


def _run_tbpro_site_import(*, resolve=None, extra_patches=()):
    """Load build-site.py so its import-time tb.pro build is the assertion target."""
    plan = _controlled_plan()
    mock_site = mock.Mock()
    mock_site_cls = mock.Mock(return_value=mock_site)
    patches = [
        mock.patch.object(sys, 'argv', ['build-site.py', '--tbpro', '--enus']),
        mock.patch.object(settings, 'TBPRO_DEFAULT_PLAN', plan),
        mock.patch('builder.Site', mock_site_cls),
    ]
    if resolve is not None:
        patches.append(mock.patch('paddle_pricing.resolve_country_prices', resolve))
    patches.extend(extra_patches)

    stacked = mock.patch.dict(os.environ)
    stacked.start()
    try:
        for key in PADDLE_ENV_KEYS:
            os.environ.pop(key, None)
        for patch in patches:
            patch.start()
        try:
            runpy.run_path(BUILD_SITE, run_name='build_site_under_test')
        finally:
            for patch in reversed(patches):
                patch.stop()
    finally:
        stacked.stop()

    return mock_site_cls, mock_site, plan


class TestBuildTbproPricing:
    def test_import_time_build_uses_resolved_price_without_mutating_settings(self):
        mock_resolve = mock.Mock(return_value=ResolvedCountryPrices(
            default_price=RESOLVED_PRICE,
            previews=None,
        ))

        mock_site_cls, mock_site, patched_plan = _run_tbpro_site_import(resolve=mock_resolve)

        mock_resolve.assert_called_once_with('$6')
        kwargs = mock_site_cls.call_args.kwargs
        context = kwargs['data']
        assert set(context) == {'current_year', 'default_plan'}
        assert kwargs['locale_data']('de') == {'tbpro_price_preview': None}
        assert kwargs['locale_data']('en-US') == {'tbpro_price_preview': None}
        context_plan = context['default_plan']
        assert context_plan['price'] == RESOLVED_PRICE
        assert context_plan is not patched_plan
        assert patched_plan == CONTROLLED_PLAN
        for key, value in CONTROLLED_PLAN.items():
            if key == 'price':
                continue
            assert context_plan[key] == value
        mock_site.build_tbpro.assert_called_once()

    def test_unconfigured_build_uses_fallback_without_http(self):
        mock_post = mock.Mock()
        extra_patches = (
            mock.patch('paddle_pricing.read_api_key', return_value=None),
            mock.patch('paddle_pricing.requests.post', mock_post),
        )
        mock_site_cls, mock_site, _ = _run_tbpro_site_import(extra_patches=extra_patches)

        kwargs = mock_site_cls.call_args.kwargs
        context = kwargs['data']
        assert set(context) == {'current_year', 'default_plan'}
        assert context['default_plan']['price'] == '$6'
        assert kwargs['locale_data']('de') == {'tbpro_price_preview': None}
        assert kwargs['locale_data']('en-US') == {'tbpro_price_preview': None}
        mock_post.assert_not_called()
        mock_site.build_tbpro.assert_called_once()

    def test_locale_callback_formats_per_language_without_extra_fetch_or_raw_map(self):
        prices = {
            'US': MonthlyPrice(monthly_minor=600, currency_code='USD'),
            'CA': MonthlyPrice(monthly_minor=1000, currency_code='CAD'),
        }
        previews = CountryPricePreviews(default_country='US', prices=prices)
        mock_resolve = mock.Mock(return_value=ResolvedCountryPrices(
            default_price='$6',
            previews=previews,
        ))

        mock_site_cls, _, patched_plan = _run_tbpro_site_import(resolve=mock_resolve)

        mock_resolve.assert_called_once_with('$6')
        kwargs = mock_site_cls.call_args.kwargs
        context = kwargs['data']
        assert set(context) == {'current_year', 'default_plan'}
        assert previews not in context.values()
        assert patched_plan == CONTROLLED_PLAN
        assert settings.TBPRO_DEFAULT_PLAN['price'] == '6'

        german = kwargs['locale_data']('de')
        english = kwargs['locale_data']('en-US')
        assert set(german) == {'tbpro_price_preview'}
        assert set(english) == {'tbpro_price_preview'}
        assert german['tbpro_price_preview']['defaultCountry'] == 'US'
        assert english['tbpro_price_preview']['defaultCountry'] == 'US'
        german_prices = {
            country['code']: country['price']
            for country in german['tbpro_price_preview']['countries']
        }
        english_prices = {
            country['code']: country['price']
            for country in english['tbpro_price_preview']['countries']
        }
        assert german_prices == {'CA': '10\xa0CA$', 'US': '6\xa0$'}
        assert english_prices == {'CA': 'CA$10', 'US': '$6'}
        assert 'monthly_minor' not in str(german)
        assert prices['US'].monthly_minor == 600


class TestLocaleDataHook:
    def _site(self, locale_data, data=None):
        return builder.Site(
            ['en-US'],
            settings.TBPRO_PATH,
            os.path.join(os.path.dirname(__file__), '..', 'dist', 'tbpro-locale-data-test'),
            {},
            data=data if data is not None else {},
            locale_data=locale_data,
        )

    def test_successive_languages_replace_preview_and_keep_lang_context(self):
        def locale_data(lang):
            return {'tbpro_price_preview': {'defaultCountry': lang}}

        site = self._site(locale_data, data={'current_year': 2026})
        site._switch_lang('de')
        assert site._env.globals['LANG'] == 'de'
        assert site._env.globals['DIR'] == 'ltr'
        german = site._env.globals['tbpro_price_preview']
        assert german == {'defaultCountry': 'de'}

        site._switch_lang('en-US')
        assert site._env.globals['LANG'] == 'en-US'
        assert site._env.globals['DIR'] == 'ltr'
        assert site._env.globals['tbpro_price_preview'] == {'defaultCountry': 'en-US'}
        assert site._env.globals['tbpro_price_preview'] is not german
        assert set(locale_data('en-US')) == {'tbpro_price_preview'}
        assert site.data == {'current_year': 2026}
        assert 'tbpro_price_preview' not in site.data

    def test_fallback_callback_stays_none_across_languages(self):
        def locale_data(lang):
            return {'tbpro_price_preview': None}

        site = self._site(locale_data)
        site._switch_lang('de')
        assert site._env.globals['LANG'] == 'de'
        assert site._env.globals['tbpro_price_preview'] is None
        site._switch_lang('en-US')
        assert site._env.globals['LANG'] == 'en-US'
        assert site._env.globals['DIR'] == 'ltr'
        assert site._env.globals['tbpro_price_preview'] is None

    def test_omitted_callback_does_not_add_preview_global(self):
        site = self._site(None)
        site._switch_lang('en-US')
        assert site._env.globals['LANG'] == 'en-US'
        assert 'tbpro_price_preview' not in site._env.globals


class TestSubscriptionPlanMacro:
    def _render(self, plan_price):
        env = Environment(
            loader=FileSystemLoader(settings.TBPRO_PATH),
            extensions=['jinja2.ext.i18n'],
        )
        env.install_null_translations()
        template = env.from_string(
            "{% from 'includes/macros/subscription-plan.html' import subscription_plan %}"
            "{{ subscription_plan('Plan', 'Description', price, 'per month', 'Join', "
            "'/waitlist', '30', '60', '3', '1', '15', show_cta=False) }}"
        )
        return template.render(price=plan_price)

    @pytest.mark.parametrize('plan_price', ['$6.50', 'CA$10'])
    def test_macro_renders_atomic_price_without_extra_markup(self, plan_price):
        html = self._render(plan_price)
        assert f'<h4><b>{plan_price}</b><span>' in html
        assert html.count('$') == plan_price.count('$')
        assert '<sup' not in html
