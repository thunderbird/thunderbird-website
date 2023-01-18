import pytest
import helper


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
