import pytest

import settings
import wsgi


class TestWSGI:
    def test_get_language_map(self):
        """Test get_language_map to ensure it returns as expected, and does not product a TypeError"""
        try:
            langs = wsgi.get_language_map()
        except TypeError:
            pytest.fail("TypeError occurred when expecting no Errors")

        assert langs
        assert len(langs) > 0
        assert langs.get(settings.LANGUAGE_CODE.lower())

    def test_get_best_language(self):
        """Test get_best_language to ensure the input locales return as expected."""
        langs = {
            'en-US': 'en-US',  # default locale
            'fr': 'fr',  # no diff
            'DE': 'de',  # upper case
            'ja-jp-mac': 'ja',  # canonical locale
            'foo': 'en-US',  # doesn't exist, so fallbacks to default locale
        }

        for lang_in, lang_out in langs.items():
            best_lang = wsgi.get_best_language(lang_in)
            assert best_lang == lang_out
