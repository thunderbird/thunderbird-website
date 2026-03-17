import os
import tempfile
import textwrap
from unittest import mock

import pytest

import settings
from builder import Site


SIMPLE_APPEAL_TEMPLATE = textwrap.dedent("""\
    donation_base_url={{ donation_base_url }}
    disable_donation_blocked_notice={{ disable_donation_blocked_notice }}
    canonical_path={{ canonical_path }}
""")


@pytest.fixture
def site(tmp_path):
    """Create a minimal Site instance with a simple appeal template for testing."""
    searchpath = str(tmp_path / "templates")
    renderpath = str(tmp_path / "render")
    os.makedirs(searchpath)
    os.makedirs(renderpath)

    appeal_dir = os.path.join(searchpath, "thunderbird", "140.0", "test25a")
    os.makedirs(appeal_dir)
    with open(os.path.join(appeal_dir, "index.html"), "w") as f:
        f.write(SIMPLE_APPEAL_TEMPLATE)

    site = Site(
        languages=["en-US"],
        searchpath=searchpath,
        renderpath=renderpath,
        css_bundles={},
    )
    site._switch_lang("en-US")
    return site


class TestRenderDonateSubpages:
    def test_creates_donate_index_html(self, site):
        """The method should create a donate/index.html file for each entry in APPEAL_DONATE_PAGES."""
        with mock.patch.object(settings, "APPEAL_DONATE_PAGES", [
            "thunderbird/140.0/test25a/index.html",
        ]):
            site.render_donate_subpages()

        donate_page = os.path.join(site.outpath, "thunderbird", "140.0", "test25a", "donate", "index.html")
        assert os.path.isfile(donate_page)

    def test_sets_donation_base_url_to_none(self, site):
        """The donate subpage should be rendered with donation_base_url=None."""
        with mock.patch.object(settings, "APPEAL_DONATE_PAGES", [
            "thunderbird/140.0/test25a/index.html",
        ]):
            site.render_donate_subpages()

        donate_page = os.path.join(site.outpath, "thunderbird", "140.0", "test25a", "donate", "index.html")
        content = open(donate_page).read()
        assert "donation_base_url=None" in content

    def test_sets_disable_donation_blocked_notice_to_false(self, site):
        """The donate subpage should be rendered with disable_donation_blocked_notice=False."""
        with mock.patch.object(settings, "APPEAL_DONATE_PAGES", [
            "thunderbird/140.0/test25a/index.html",
        ]):
            site.render_donate_subpages()

        donate_page = os.path.join(site.outpath, "thunderbird", "140.0", "test25a", "donate", "index.html")
        content = open(donate_page).read()
        assert "disable_donation_blocked_notice=False" in content

    def test_sets_canonical_path(self, site):
        """The donate subpage should have canonical_path set to the /donate/ subdirectory."""
        with mock.patch.object(settings, "APPEAL_DONATE_PAGES", [
            "thunderbird/140.0/test25a/index.html",
        ]):
            site.render_donate_subpages()

        donate_page = os.path.join(site.outpath, "thunderbird", "140.0", "test25a", "donate", "index.html")
        content = open(donate_page).read()
        assert "canonical_path=/thunderbird/140.0/test25a/donate" in content
