"""Tests for wiring resolved Paddle prices into tb.pro builds and the subscription-plan macro."""

import json
import os
import runpy
import sys
import tempfile
from unittest import mock

import pytest
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader
from jinja2.exceptions import UndefinedError

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

TBPRO_PAGE_TEMPLATES = (
    'index.html',
    'appointment/index.html',
    'send/index.html',
    'waitlist/index.html',
)
API_KEY_SENTINEL = 'pdl_test_api_key_sentinel'
LABEL_SENTINEL = 'TBPRO_LABEL_SENTINEL'
DANGEROUS_LABEL = f'{LABEL_SENTINEL}</script>{LABEL_SENTINEL}'
PRICE_SENTINEL = '$6<price>'
PREVIEW_NOTE = (
    'Pricing is a preview. Final price is calculated at checkout using your billing country.'
)
PREVIEW_LABEL = 'Select your country or region'
ABSENT_PREVIEW_TOKENS = (
    'monthly_minor',
    'currency_code',
    'request_id',
    API_KEY_SENTINEL,
)
PRICE_PREVIEW_JS = os.path.join(
    os.path.dirname(__file__), '..', 'assets', 'js', 'tbpro', 'price-preview.js',
)
PRICE_PREVIEW_SCRIPT = (
    '<script type="text/javascript" '
    "src=\"{{ static('js/tbpro-price-preview.js') }}\" "
    'charset="utf-8" defer></script>'
)
PRICE_PREVIEW_SCRIPT_SRC = '/media/js/tbpro-price-preview.js'
FORBIDDEN_PREVIEW_SOURCE_TOKENS = (
    'fetch',
    'XMLHttpRequest',
    'sendBeacon',
    'WebSocket',
    'innerHTML',
    'outerHTML',
    'insertAdjacentHTML',
    'localStorage',
    'sessionStorage',
    'document.cookie',
    'navigator.language',
    'navigator.languages',
    'geolocation',
    'paddle',
    'Intl.NumberFormat',
    'toLocaleString',
    'focus(',
    'blur(',
    'scrollIntoView',
    'window.location',
    'document.location',
    'location.assign',
    'location.replace',
    'pushState',
    'replaceState',
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


def _parse_html(html):
    return BeautifulSoup(html, 'html.parser')


def _price_preview(default_country='US', countries=None):
    """Return a public preview whose default is not the first country."""
    if countries is None:
        countries = [
            {'code': 'CA', 'label': 'Canada', 'price': 'CA$10'},
            {'code': 'US', 'label': 'United States', 'price': '$6'},
        ]
    return {
        'defaultCountry': default_country,
        'countries': countries,
    }


def _json_island_source(html):
    """Return the raw JSON island so escaping checks see the page source."""
    open_tag = '<script type="application/json" class="subscription-price-data">'
    start = html.index(open_tag) + len(open_tag)
    return html[start:html.index('</script>', start)]


def _render_tbpro_pages(preview, templates=TBPRO_PAGE_TEMPLATES):
    """Render complete en-US tb.pro pages with one locale_data callback."""
    plan = _controlled_plan()
    plan['price'] = '$6'
    pages = {}

    def locale_data(lang):
        assert lang == 'en-US'
        return {'tbpro_price_preview': preview}

    with tempfile.TemporaryDirectory() as renderpath:
        site = builder.Site(
            ['en-US'],
            settings.TBPRO_PATH,
            renderpath,
            {},
            data={'current_year': 2026, 'default_plan': plan},
            extra_searchpaths=[settings.COMMON_SEARCHPATH],
            locale_data=locale_data,
        )
        # build_tbpro() publishes plan data before switching language. Do that
        # here without running its 99-language loop.
        site._env.globals.update(site.data)
        site._switch_lang('en-US')
        for template in templates:
            output = os.path.join(renderpath, template)
            os.makedirs(os.path.dirname(output), exist_ok=True)
            site._render_template(template, output)
            with open(output, encoding='utf-8') as handle:
                pages[template] = handle.read()
    return pages


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
        soup = _parse_html(html)
        assert soup.select('.subscription-price-preview') == []
        assert soup.select('#tbpro-price-country') == []
        assert soup.select('#tbpro-price-note') == []
        assert soup.select('.subscription-price-data') == []


def _assert_page_language(soup, html, template):
    assert soup.select_one('html').get('lang') == 'en', template
    assert soup.select_one('html').get('dir') == 'ltr', template
    assert 'window.siteLocale = "en-US"' in html, template


def _assert_period_break(soup, template):
    span = soup.select_one('.subscription-callout h4 span')
    assert span.find('br') is not None, template


def _assert_cta(soup, template):
    buttons = soup.select('.subscription-callout button.button-brand-outline-label')
    expected = 0 if template == 'waitlist/index.html' else 1
    assert len(buttons) == expected, template


def _assert_absent_tokens(html, template):
    for token in ABSENT_PREVIEW_TOKENS:
        assert token not in html, template


def _assert_preview_script(soup, template):
    tags = [
        tag for tag in soup.select('script[src]')
        if tag.get('src') == PRICE_PREVIEW_SCRIPT_SRC
    ]
    assert len(tags) == 1, template
    tag = tags[0]
    assert tag.has_attr('defer'), template
    assert tag.get('type') == 'text/javascript', template
    assert tag.get('charset') == 'utf-8', template
    assert '://' not in tag.get('src'), template


def _price_preview_source():
    with open(PRICE_PREVIEW_JS, encoding='utf-8') as handle:
        return handle.read()


class TestSubscriptionPlanPages:
    def test_configured_pages_render_the_default_country_preview(self):
        preview = _price_preview()
        for template, html in _render_tbpro_pages(preview).items():
            soup = _parse_html(html)
            assert len(soup.select('.subscription-price-preview')) == 1, template
            assert len(soup.select('#tbpro-price-country')) == 1, template
            assert len(soup.select('#tbpro-price-note')) == 1, template
            assert len(soup.select('.subscription-price-data')) == 1, template

            control = soup.select_one('.subscription-price-control')
            assert control.has_attr('hidden'), template
            select = soup.select_one('#tbpro-price-country')
            label = soup.select_one('label[for="tbpro-price-country"]')
            assert label is not None and label.get_text() == PREVIEW_LABEL, template
            assert not select.has_attr('name'), template
            assert select.get('aria-describedby') == 'tbpro-price-note', template
            note = soup.select_one('#tbpro-price-note')
            assert note.get_text() == PREVIEW_NOTE, template
            assert note.find_parent(class_='subscription-price-control') is None, template
            assert control.select_one('#tbpro-price-note') is None, template

            options = select.select('option')
            assert [option.get('value') for option in options] == ['CA', 'US'], template
            selected = select.select('option[selected]')
            assert len(selected) == 1, template
            assert selected[0].has_attr('selected'), template
            assert not options[0].has_attr('selected'), template
            assert selected[0].get('value') == 'US', template
            assert selected[0].get_text() == 'United States', template

            price = soup.select_one('.subscription-price')
            assert price.get('aria-live') == 'polite', template
            assert price.get('aria-atomic') == 'true', template
            assert price.get_text() == '$6', template

            payload = json.loads(soup.select_one('script.subscription-price-data').string)
            assert set(payload) == {'defaultCountry', 'countries'}, template
            assert payload['defaultCountry'] == 'US', template
            assert payload['countries'][0]['code'] == 'CA', template
            for country in payload['countries']:
                assert set(country) == {'code', 'label', 'price'}, template

            _assert_period_break(soup, template)
            _assert_cta(soup, template)
            _assert_page_language(soup, html, template)
            _assert_absent_tokens(html, template)
            _assert_preview_script(soup, template)

            if template == 'waitlist/index.html':
                mailchimp = soup.select_one('#mce-COUNTRY')
                assert mailchimp.get('name') == 'COUNTRY', template
                assert mailchimp.find_parent('form').get('id') == 'mc-embedded-subscribe-form'
                assert select.find_parent('form') is None, template
                assert mailchimp.get('id') != select.get('id'), template
                assert soup.select_one('label[for="mce-COUNTRY"]') is not None, template
            else:
                assert soup.select('#mce-COUNTRY') == [], template

    def test_fallback_pages_omit_the_preview(self):
        for template, html in _render_tbpro_pages(None).items():
            soup = _parse_html(html)
            assert soup.select('.subscription-price-preview') == [], template
            assert soup.select('#tbpro-price-country') == [], template
            assert soup.select('#tbpro-price-note') == [], template
            assert soup.select('.subscription-price-data') == [], template
            assert soup.select('.subscription-price') == [], template
            assert PREVIEW_NOTE not in html, template
            assert PREVIEW_LABEL not in html, template
            price = soup.select_one('.subscription-callout h4 b')
            assert price.get_text() == '$6', template
            _assert_period_break(soup, template)
            _assert_cta(soup, template)
            _assert_page_language(soup, html, template)
            _assert_absent_tokens(html, template)
            _assert_preview_script(soup, template)
            if template == 'waitlist/index.html':
                mailchimp = soup.select_one('#mce-COUNTRY')
                assert mailchimp.get('name') == 'COUNTRY', template
                assert mailchimp.find_parent('form') is not None, template

    def test_configured_pages_escape_label_and_price_sentinels(self):
        countries = [
            {'code': 'CA', 'label': 'Canada', 'price': 'CA$10'},
            {'code': 'US', 'label': DANGEROUS_LABEL, 'price': PRICE_SENTINEL},
        ]
        preview = _price_preview(countries=countries)
        for template, html in _render_tbpro_pages(preview).items():
            island = _json_island_source(html)
            assert f'{LABEL_SENTINEL}</script>' not in html, template
            assert f'{LABEL_SENTINEL}\\u003c/script\\u003e{LABEL_SENTINEL}' in island, template
            assert f'{LABEL_SENTINEL}&lt;/script&gt;{LABEL_SENTINEL}' in html, template
            assert '$6&lt;price&gt;' in html, template
            assert API_KEY_SENTINEL not in html, template

            soup = _parse_html(html)
            payload = json.loads(soup.select_one('script.subscription-price-data').string)
            united_states = payload['countries'][1]
            assert united_states['label'] == DANGEROUS_LABEL, template
            assert united_states['price'] == PRICE_SENTINEL, template
            selected = soup.select_one('#tbpro-price-country option[selected]')
            assert selected.get_text() == DANGEROUS_LABEL, template
            assert soup.select_one('.subscription-price').get_text() == PRICE_SENTINEL, template

    def test_missing_default_country_raises(self):
        preview = _price_preview(default_country='GB')
        with pytest.raises(UndefinedError, match='list object has no element 0'):
            _render_tbpro_pages(preview, templates=('index.html',))

    def test_privacy_page_loads_the_script_without_a_preview(self):
        html = _render_tbpro_pages(None, templates=('privacy/index.html',))['privacy/index.html']
        soup = _parse_html(html)
        assert soup.select('.subscription-price-preview') == []
        _assert_preview_script(soup, 'privacy/index.html')


class TestPricePreviewScript:
    """Source and bundle checks. They do not execute the script.

    Malformed JSON and price changes still require manual browser QA.
    """

    def test_bundle_registration_points_at_the_source_file(self):
        assert settings.TBPRO_JS == {
            'tbpro-price-preview': ['js/tbpro/price-preview.js'],
        }
        assert os.path.isfile(PRICE_PREVIEW_JS)

    def test_base_template_places_the_deferred_tag_outside_blocks(self):
        base_path = os.path.join(settings.TBPRO_PATH, 'includes', 'base', 'base.html')
        with open(base_path, encoding='utf-8') as handle:
            base = handle.read()
        marker = '{% block additional_page_js %}{% endblock %}'
        head, separator, tail = base.partition(marker)
        assert separator == marker
        assert PRICE_PREVIEW_SCRIPT not in head
        assert PRICE_PREVIEW_SCRIPT in tail
        assert tail.index(PRICE_PREVIEW_SCRIPT) < tail.index('</body>')

    def test_concat_writes_the_source_into_the_media_bundle(self):
        source = _price_preview_source()
        with tempfile.TemporaryDirectory() as renderpath:
            site = builder.Site(
                ['en-US'],
                settings.TBPRO_PATH,
                renderpath,
                {},
                js_bundles=settings.TBPRO_JS,
            )
            os.makedirs(site.jsout, exist_ok=True)
            site._concat_js()
            bundle_path = os.path.join(site.jsout, 'tbpro-price-preview.js')
            assert bundle_path.endswith('/media/js/tbpro-price-preview.js')
            with open(bundle_path, encoding='utf-8') as handle:
                bundle = handle.read()
        assert bundle == source

    def test_source_scopes_queries_and_reveals_only_after_the_listener(self):
        source = _price_preview_source()
        assert "document.querySelectorAll('.subscription-price-preview')" in source
        assert source.count('document.querySelectorAll') == 1
        assert 'document.getElementById' not in source
        assert "root.querySelectorAll('script.subscription-price-data')" in source
        assert "root.querySelectorAll('.subscription-price-control')" in source
        assert "control.querySelectorAll('select')" in source
        assert "root.querySelectorAll('.subscription-price')" in source
        assert 'JSON.parse(dataNode.textContent)' in source
        handler = source.index('function onCountryChange()')
        assignment = source.index('.textContent =')
        listener = source.index("addEventListener('change', onCountryChange)")
        reveal = source.index("removeAttribute('hidden')")
        assert source.count('.textContent =') == 1
        assert handler < assignment < listener < reveal

    def test_source_omits_network_storage_and_navigation_apis(self):
        source = _price_preview_source()
        folded = source.lower()
        for token in FORBIDDEN_PREVIEW_SOURCE_TOKENS:
            assert token not in source, token
            if token == 'paddle':
                assert token not in folded
