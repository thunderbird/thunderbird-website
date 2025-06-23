import pytest
import helper
import settings


class TestFRU:
    def test_get_fru_language(self):
        """Ensure that our language map function returns the correct outputs for FRU."""
        languages_io = {
            'nonexistent': 'en-US',
            'en-NL': 'en-US',
            'en-CA': 'en-CA',
            'nn-NO': 'nb',
            'ga-IE': 'en-US',
            'sv-SE': 'sv-SE',
            'pt-BR': 'pt-BR',
            'pt-PT': 'pt-PT',
            'nb-NO': 'nb',
            'fr': 'fr',
            'fi': 'fi',
            'da': 'da',
            'ja': 'ja'
        }

        for actual_input, expected_output in languages_io.items():
            fake_context = {
                'LANG': actual_input
            }
            actual_output = helper.get_fru_language(fake_context)
            assert actual_output == expected_output


class TestUrl:
    def test_url_forms_relative_url_when_appropriate(self):
        """If we're the target build site (env=SITE) it should be a relative url
        and if it's not the website it should be an absolute url

        Note: There's no start urls defined"""
        for site_code in settings.SITE_CODES.values():
            is_website = site_code == settings.SITE_CODES['WEBSITE']
            is_updates = site_code == settings.SITE_CODES['UPDATES']
            context = {
                'LANG': 'en-US',
                'SITE': site_code
            }
            url = helper.url(context, 'thunderbird.download')
            if is_website:
                assert settings.CANONICAL_URL not in url
            else:
                assert settings.CANONICAL_URL in url

            url = helper.url(context, 'updates.140.whatsnew')
            if is_updates:
                assert settings.CANONICAL_UPDATES_URL not in url
            else:
                assert settings.CANONICAL_UPDATES_URL in url

            # Non `thunderbird.` or `updates.` key urls should never prefix the canonical url
            url = helper.url(context, 'mozorg.home')
            assert settings.CANONICAL_URL not in url

    def test_redirect_donate_url(self):
        """Ensure the start page donate url generator doesn't break"""
        context = {
            'LANG': 'en-US',
            'SITE': settings.SITE_CODES['START']
        }
        url = helper.redirect_donate_url(context, location='thunderbird.donate', content='example',
                                         source='example.com', medium='example',
                                         campaign='example', show_donation_modal=False)
        assert url == 'https://www.thunderbird.net/en-US/donate?utm_content=example&utm_source=example.com&utm_medium=example&utm_campaign=example'
