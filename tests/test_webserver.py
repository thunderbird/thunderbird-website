"""
Integration tests for Thunderbird websites.

These tests verify Apache virtual hosts, redirects, and content serving.
They require Apache to be running on localhost:80.

Run with: pytest tests/test_sites.py -v
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("SITE_URL", "http://localhost")


def apache_running() -> bool:
    """Check if Apache is running and responding."""
    try:
        requests.get(BASE_URL, timeout=2)
        return True
    except requests.exceptions.RequestException:
        return False


# Skip all tests in this module if Apache is not running
pytestmark = pytest.mark.skipif(
    not apache_running(),
    reason="Apache not running"
)


def get(path: str, host: str, accept_language: str = "en-US") -> requests.Response:
    """Make a GET request with a specific Host header, without following redirects.

    Includes X-Forwarded-Proto: https to simulate being behind a load balancer,
    which triggers Apache's SetEnvIf to set HTTPS=on.
    """
    return requests.get(
        f"{BASE_URL}{path}",
        headers={
            "Host": host,
            "Accept-Language": accept_language,
            "X-Forwarded-Proto": "https",
        },
        allow_redirects=False
    )


# (host, path, expected_status, expected_location_contains)
# expected_location_contains can be None for 200 responses
TEST_CASES = [
    # www.thunderbird.net - 200 responses
    ("www.thunderbird.net", "/en-US/", 200, None),

    # www.thunderbird.net - redirects
    ("www.thunderbird.net", "/media/caldata/CroatiaHolidays.ics", 302, "/media/caldata/autogen/CroatiaHolidays.ics"),
    ("www.thunderbird.net", "/ja-JP-mac/", 302, "/ja/"),
    ("www.thunderbird.net", "/get-involved/", 302, "/participate/"),
    ("www.thunderbird.net", "/bn-BD/", 302, "/bn/"),
    ("www.thunderbird.net", "/thunderbird/system-requirements/", 302, "/system-requirements/"),
    ("www.thunderbird.net", "/thunderbird/notes/", 302, "/notes/"),
    ("www.thunderbird.net", "/features/", 302, "www.thunderbird.net/"),

    # start.thunderbird.net
    ("start.thunderbird.net", "/", 302, "/en-US/release/"),
    ("start.thunderbird.net", "/ja-JP-mac/", 302, "/ja/"),

    # updates.thunderbird.net
    ("updates.thunderbird.net", "/en-US/thunderbird/128.0/dec24/", 200, None),
    ("updates.thunderbird.net", "/thunderbird/128.0/dec24/", 302, "/en-US/thunderbird/128.0/dec24/"),
    ("updates.thunderbird.net", "/ja-JP-mac/thunderbird/128.0/dec24/", 302, "/ja/thunderbird/128.0/dec24/"),

    # autoconfig.thunderbird.net
    ("autoconfig.thunderbird.net", "/v1.1/gmail.com", 200, None),
    ("autoconfig.thunderbird.net", "/autoconfig/test.com", 301, "/test.com"),

    # stats.thunderbird.net
    ("stats.thunderbird.net", "/", 200, None),

    # live.thunderbird.net - external redirects
    ("live.thunderbird.net", "/thunderbird/releasenotes/?locale=en-US&version=128.0&channel=release", 302, "www.thunderbird.net/en-US/thunderbird/128.0/releasenotes/"),
    ("live.thunderbird.net", "/thunderbird/start/?locale=en-US&version=130.0&channel=release", 302, "start.thunderbird.net/en-US/monthly/"),
    ("live.thunderbird.net", "/thunderbird/whatsnew/?locale=en-US&version=128.0.1&channel=release", 302, "www.thunderbird.net/en-US/thunderbird/128.0/whatsnew/"),
    ("live.thunderbird.net", "/autoconfig/gmail.com", 302, "autoconfig.thunderbird.net/gmail.com"),
    ("live.thunderbird.net", "/services.addons/test", 302, "services.addons.thunderbird.net/test"),

    # tb.pro
    ("tb.pro", "/ja-JP-mac/", 302, "/ja/"),
    ("tb.pro", "/", 302, "/en-US/"),
    ("tb.pro", "/appointment", 302, "/en-US/appointment"),
    ("tb.pro", "/send", 302, "/en-US/send"),
    ("tb.pro", "/thundermail", 302, "/en-US/thundermail"),
    ("tb.pro", "/waitlist", 302, "/en-US/waitlist"),
]


@pytest.mark.parametrize("host,path,expected_status,expected_location", TEST_CASES)
def test_endpoint(host: str, path: str, expected_status: int, expected_location: str | None):
    """Verify endpoint returns expected status and redirect location."""
    response = get(path, host)
    assert response.status_code == expected_status, f"Expected {expected_status}, got {response.status_code}"

    if expected_location:
        location = response.headers.get("Location", "")
        assert expected_location in location, f"Expected '{expected_location}' in Location header, got '{location}'"


# Filter to only redirect test cases for HTTPS scheme verification
REDIRECT_CASES = [
    case for case in TEST_CASES
    if case[2] in {301, 302}
]


@pytest.mark.parametrize("host,path,expected_status,expected_location", REDIRECT_CASES)
def test_redirects_use_https(host: str, path: str, expected_status: int, expected_location: str | None):
    """
    Verify redirects use https:// scheme, not http://.

    This tests the fix for SSL termination at the load balancer.
    See: https://httpd.apache.org/docs/2.4/mod/core.html#servername
    """
    response = get(path, host)
    location = response.headers.get("Location", "")
    assert not location.startswith("http://"), f"Redirect uses http:// instead of https://: {location}"


# Locale detection tests - verify Accept-Language header is respected
LOCALE_TESTS = [
    ("www.thunderbird.net", "/", "en-US", "/en-US/"),
    ("www.thunderbird.net", "/", "fr", "/fr/"),
    ("www.thunderbird.net", "/", "ja", "/ja/"),
    ("tb.pro", "/waitlist", "en-US", "/en-US/waitlist"),
    ("tb.pro", "/waitlist", "fr", "/fr/waitlist"),
    ("tb.pro", "/waitlist", "ja", "/ja/waitlist"),
]


@pytest.mark.parametrize("host,path,lang,expected_location", LOCALE_TESTS)
def test_locale_detection(host: str, path: str, lang: str, expected_location: str):
    """Verify Accept-Language header triggers correct locale redirect."""
    response = get(path, host, accept_language=lang)
    assert response.status_code == 302
    location = response.headers.get("Location", "")
    assert expected_location in location, f"Expected '{expected_location}' in Location for lang={lang}, got '{location}'"

