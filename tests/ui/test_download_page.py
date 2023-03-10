import re
import pytest
from playwright.sync_api import Page, expect
from product_details import thunderbird_desktop
import settings

@pytest.fixture
def download_page_download_states(page: Page):
    """Returns a list of tuples, which contains the download page to goto, and the download version the visible download button should be."""
    download_page_url = f"{settings.TEST_URL}/download/"

    download_versions = (
        thunderbird_desktop.latest_version('release'),
        thunderbird_desktop.latest_version('beta'),
        thunderbird_desktop.latest_version('daily')
    )

    return [
        (download_page_url, download_versions[0]),
        (f"{download_page_url}?downloaded=True", download_versions[0]),
        (f"{download_page_url}?downloaded=False", download_versions[0]),
        (f"{download_page_url}?download_channel=esr", download_versions[0]),
        (f"{download_page_url}?download_channel=beta", download_versions[1]),
        (f"{download_page_url}?download_channel=daily", download_versions[2]),
        (f"{download_page_url}?download_channel=nonsense", download_versions[0]),
        (f"{download_page_url}?download_channel=&downloaded=true&download_channel=beta", download_versions[1]),  # Javascript check looks for (esr|beta|daily), empty params are ignored
        (f"{download_page_url}?download_channel=&downloaded=true&download_channel=daily&download_channel=beta", download_versions[2]),  # Javascript check will only use the first instance
    ]


def test_download_links_exist(page: Page, download_page_download_states):
    """Tests the existence of the `Try Again` button on our download thank you page."""
    for state in download_page_download_states:
        page.goto(state[0])
        expect(page.locator('.download-link:visible')).to_have_count(1)


def test_download_links_are_correct(page: Page, download_page_download_states):
    """Tests the validity of our download buttons when different download channels have been requested."""
    for state in download_page_download_states:
        page.goto(state[0])
        expect(page.locator('.download-link:visible')).to_have_attribute("href", re.compile(state[1]))

