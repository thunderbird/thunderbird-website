import datetime

import pytest

from calgen.models.Calendarific import Calendarific
from calgen.providers.Provider import Provider
from build_calendar import build_ical


def provider_data():
    return {
        'urlid': '1234',
        'name': 'Test Holiday',
        'description': 'This is a description of a test holiday.',
        'date': {
            'iso': '2003-07-03'
        }
    }


class MockProvider(Provider):
    def query(self, country, year, additional_options):
        return [provider_data()]

    def build(self, country, year, additional_options):
        return [Calendarific(provider_data())]
        pass


@pytest.mark.xfail(reason="Going through a rewrite")
class TestBuildCalendar:
    def test_build_ical(self):
        """ Ensure that the mocked data outputs to an ical object correctly. """
        locale = 'US'

        provider = MockProvider('Mock Provider', {})
        ical = build_ical(provider=provider, locale=locale, language='en', years_to_generate=1)

        current_year = datetime.datetime.now().year

        assert ical is not None
        assert len(ical.subcomponents) > 0
        '''
        Note: Currently build_ical loops twice for calendar_types assuming we're dealing with calendarific data
        '''
        assert ical.subcomponents[0].get('UID') is not None
        assert ical.subcomponents[0].get('UID') == "{}-{}".format(provider_data()['urlid'], current_year)
