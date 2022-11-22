import datetime

from calgen.models.Calendar import Calendar, CalendarTypes

'''
Unique holidays/observances that are missing from the calendar api source.

These are mixed in before we pull data from the api source, and should use rrules.
'''
MIXINS = [
    # Sample Event
    # Thunderbird's Birthday
    ##Calendar({
    ##    'unique_id': '1254fbcc-762f-46b6-a85d-aa985c7776dc',
    ##    'name': "Thunderbird's Birthday",
    ##    'description': "Thunderbird was first released on July 3rd, 2003.",
    ##    'iso_date': datetime.datetime(2003, 7, 3),
    ##    'calendar_type': CalendarTypes.OBSERVANCE,
    ##    'rrule': {'Freq': 'Yearly'}
    ##}),
    # ... Other mixins
]