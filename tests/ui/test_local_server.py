import pytest
import settings
from playwright.sync_api import Page, expect


def test_server_is_working(page: Page):
    """Make sure our test server works correctly"""
    response = page.goto(settings.TEST_URL)
    assert response is not None
    assert response.ok is True

    # Make sure our title is correct, and this isn't an empty 200.
    expect(page).to_have_title('Thunderbird — Make Email Easier. — Thunderbird')

