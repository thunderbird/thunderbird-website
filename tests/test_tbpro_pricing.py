"""Tests for wiring resolved Paddle prices into tb.pro builds and the subscription-plan macro."""

import os
import runpy
import sys
from unittest import mock

import pytest
from jinja2 import Environment, FileSystemLoader

import settings


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
        patches.append(mock.patch('paddle_pricing.resolve_monthly_price', resolve))
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
        mock_resolve = mock.Mock(return_value=RESOLVED_PRICE)

        mock_site_cls, mock_site, patched_plan = _run_tbpro_site_import(resolve=mock_resolve)

        mock_resolve.assert_called_once_with('$6')
        context_plan = mock_site_cls.call_args.kwargs['data']['default_plan']
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

        context_plan = mock_site_cls.call_args.kwargs['data']['default_plan']
        assert context_plan['price'] == '$6'
        mock_post.assert_not_called()
        mock_site.build_tbpro.assert_called_once()


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
