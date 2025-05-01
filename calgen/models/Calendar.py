from datetime import datetime, timedelta
from enum import Enum
import icalendar


class CalendarTypes(Enum):
    """ Note: National sets the calendary `transp` property to opaque. Every other type is transparent. """
    NATIONAL = 'national'
    LOCAL = 'local'
    RELIGIOUS = 'religious'
    OBSERVANCE = 'observance'


class Calendar(object):
    """
    Calendar Model

    Base class for API / package implementations
    Extend and implement from_api to standardize data.

    Note: `self.rrule` is mainly used for mixins.
    """

    def __init__(self, data: dict = None, year: int = None):
        self.unique_id = 0
        self.name = ''
        self.description = ''
        self.iso_date = datetime(1970, 1, 1)
        self.calendar_type = ''
        if year is None:
            year = datetime.now().year
        self.year = year
        self.rrule = None

    # By default, we'll just initialize ourselves
    def from_api(self, data: dict):
        self.unique_id = data.get('unique_id')
        self.name = data.get('name')
        self.description = data.get('description')
        self.iso_date = data.get('iso_date')
        self.calendar_type = data.get('calendar_type')
        self.rrule = data.get('rrule')

    def to_ics(self):
        ievt = icalendar.Event()

        data = {
            'uid': self.unique_id,
            'last-modified': datetime.now(),
            'dtstart': self.iso_date.date(),
            'dtend': self.iso_date.date() + timedelta(days=1),
            'summary': self.name,
            'description': self.description,
            'dtstamp': datetime.now(),
            'class': 'public',
            'transp': 'OPAQUE' if self.calendar_type == CalendarTypes.NATIONAL else 'TRANSPARENT',
            'categories': ['Holidays'],
            'rrule': self.rrule
        }

        for key, value in data.items():
            if value is None:
                continue
            ievt.add(key, value)

        return ievt
