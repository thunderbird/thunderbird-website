from typing import List

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

    def test_always_localize_override(self):
        """Tests our ALWAYS_LOCALIZE check during the wsgi boot process"""
        # Formatted -> (Path, Accepts Custom Locale)
        paths = [
            ('/thunderbird/115.0/eoy', True),
            ('/thunderbird/115.0/appeal', True),
            ('/thunderbird/115.0/beta-appeal', True),
            ('/thunderbird/115.0/holidayeoy', True),
            ('/thunderbird/115.0/whatsnew', False),
            ('/thunderbird', False)
        ]

        locale = 'fr'

        def start_response_test(status, data: List, path):
            """This function is called during the boot process, here we can actually do the assertions"""
            data = dict(data)

            assert 'Location' in data
            assert path[0] in data['Location']
            if path[1]:
                assert locale in data['Location']
            else:
                assert locale not in data['Location']

        for path in paths:
            # Setup the fake env with our path and locale
            env = {
                'PATH_INFO': path[0],
                'HTTP_ACCEPT_LANGUAGE': locale,
                # Required defaults
                'SERVER_NAME': 'localhost',
                'GATEWAY_INTERFACE': 'CGI/1.1',
                'SERVER_PORT': '80',
                'REMOTE_HOST': '',
                'CONTENT_LENGTH': '',
                'SCRIPT_NAME': '',
                'webob.adhoc_attrs': {
                    'url': 'localhost',
                    'path': path[0],
                },
                'wsgi.url_scheme': 'http'
            }

            # We want to also pass the current path info along, so wrap the function in a lambda
            wsgi.application(env, lambda x, y: start_response_test(x, y, path))
