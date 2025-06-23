import pytest
import datetime
from calgen.models.Calendarific import Calendarific


@pytest.fixture
def calendar():
    return Calendarific()


@pytest.fixture
def sample_data():
    return {
        'urlid': '1234',
        'name': 'Test Holiday',
        'description': 'This is a description of a test holiday.',
        'date': {
            'iso': '2003-07-03'
        }
    }


key_map = {
    'urlid': 'unique_id',
    'name': 'name',
    'description': 'description',
    'date': 'iso_date',
}


@pytest.mark.xfail(reason="Going through a rewrite")
class TestCalendarificModel:
    def test_from_api_with_empty(self, calendar):
        """ Ensure an empty object does not crash from_api method """
        calendar.from_api({})

        none_keys = key_map.values()

        for key in none_keys:
            assert calendar.__dict__[key] is None

        # Year is set with the current year by default
        assert calendar.year == datetime.datetime.now().year

    def test_from_api_with_data(self, calendar, sample_data):
        """ Ensure the data is set correctly """
        calendar.from_api(sample_data)

        for key, value in sample_data.items():
            # Date needs a little more work for the comparison
            if key == 'date':
                assert calendar.iso_date == datetime.datetime.fromisoformat(sample_data['date']['iso'])
                continue
            assert calendar.__dict__[key_map[key]] == value
