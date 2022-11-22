import pytest
import datetime
from calgen.models.Calendar import Calendar, CalendarTypes


@pytest.fixture
def calendar():
    return Calendar()


@pytest.fixture
def sample_data():
    return {
        'unique_id': '1234',
        'name': 'Test Event',
        'description': 'Test Description',
        'iso_date': datetime.datetime(2003, 7, 3),
        'calendar_type': CalendarTypes.NATIONAL
    }


class TestCalendarModel:
    def test_from_api_with_empty(self, calendar):
        """ Ensure an empty object does not crash from_api method """
        calendar.from_api({})

        none_keys = ['unique_id', 'name', 'description', 'calendar_type', 'iso_date']

        for key in none_keys:
            assert calendar.__dict__[key] is None

        # Year is set with the current year by default
        assert calendar.year == datetime.datetime.now().year

    def test_from_api_with_data(self, calendar, sample_data):
        """ Ensure the data is set correctly """
        calendar.from_api(sample_data)

        for key, value in sample_data.items():
            assert calendar.__dict__[key] == value

    def test_to_ics_transp_property(self, calendar, sample_data):
        """ Ensure the transp property is set properly by CalendarType """
        calendar.from_api(sample_data)
        ievt = calendar.to_ics()
        assert ievt is not None

        # Type is set to National which means we want opaque
        assert ievt.get('transp') == 'opaque'

        # Switch over our calendar type to Observance which makes it transparent
        calendar.calendar_type = CalendarTypes.OBSERVANCE
        ievt2 = calendar.to_ics()

        assert ievt2 is not None
        assert ievt2.get('transp') == 'transparent'

    def test_to_ics(self, calendar, sample_data):
        """ Ensure that some surface level logic behaves as expected """
        calendar.from_api(sample_data)
        ievt = calendar.to_ics()

        assert ievt is not None
        assert ievt.get('uid') == "{}-{}".format(calendar.unique_id, calendar.year)

        assert ievt.get('dtstart').dt == calendar.iso_date.date()
        day_after = sample_data.get('iso_date') + datetime.timedelta(days=1)
        assert ievt.get('dtend').dt == day_after.date()
