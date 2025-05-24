#!/usr/bin/python
import json
import sys
from datetime import datetime, UTC
import os
import time

import icalendar
import requests

import helper
import settings

from calgen.mixins import GlobalHolidays
from calgen.models.Calendar import CalendarTypes
from calgen.providers.Provider import Provider


def mixin_events(ical, locale: str):
    """ Mixes in additional events that would be missed by a provider. Currently, we only account for global mixins. """
    # Global mix ins
    for event in GlobalHolidays.MIXINS:
        ical.add_component(event.to_ics())

    # Locale specific mix ins
    # ...


def build_ical(provider: Provider, locale: str, language: str, years_to_generate: int):
    """ Queries provider, and generates an iCalendar object which it returns. """
    ical = icalendar.Calendar()
    ical.add('prodid', '-//Mozilla.org/NONSGML Mozilla Calendar V1.1//EN')
    ical.add('version', '2.0')

    mixin_events(ical, locale)

    current_year = datetime.now().year
    for i in range(0, years_to_generate):
        year = current_year + i

        unique_holidays = {}
        for calendar_type in [CalendarTypes.NATIONAL, CalendarTypes.LOCAL]:
            try:
                holidays = provider.build(locale, year, {'calendar_type': calendar_type.value, 'language': language})

                # Sometimes we can have dupes due to varying calendar types containing the same holiday
                for holiday in holidays:
                    if holiday.unique_id not in unique_holidays:
                        unique_holidays[holiday.unique_id] = holiday
                        ical.add_component(holiday.to_ics())

            except requests.HTTPError as err:
                print(f"Err: Locale: {locale} / Calendar Type: {calendar_type}")
                if err.response.status_code == 500:
                    print('Err: 500 Internal Server Error encountered, skipping.')
                    continue

                try:
                    response = err.response.json()
                except requests.exceptions.JSONDecodeError as json_err:
                    print(f'Err: Could not decode json, using response.text. {json_err}')
                    response = {'meta': {'error_detail': err.response.text}}

                # Generic error message
                error_response = "{}: {}. ".format(err.response.status_code, err.response.reason)

                # If we have the error_detail key, append that.
                if response['meta'].get('error_detail'):
                    error_response += response['meta'].get('error_detail')

                # Known errors:
                # Too many requests, upgrade required are API limit reached.
                # Unauthorized is malformed or bad API key.
                sys.exit(error_response)

    return ical


def build_calendars(provider: Provider, locales: dict):
    """
    Entry function for build_calendar.py script, will query the provider passed, and build the actual .ics file.
    While this has been cleaned up to not specifically call out Calendarific, there are still data / assumptions made on function calls that will require a small touch up if you happen to use a different Provider.
    """
    if len(locales.items()) == 0:
        sys.exit("No locales specified, skipping calendar generation.")

    is_free_tier = helper.is_calendarific_free_tier()

    years_to_generate = settings.CALDATA_YEARS_TO_GENERATE
    current_year = datetime.now().year
    date_span = "{}-{}".format(current_year, current_year + years_to_generate)

    calendar_metadata = []

    now_utc = datetime.now(UTC)

    # Check if the folders exist
    if not os.path.exists(settings.CALDATA_AUTOGEN_URL):
        os.mkdir(settings.CALDATA_AUTOGEN_URL)

    print("Querying calendar data from {}".format(provider.name))

    for locale, country_info_list in locales.items():
        if not isinstance(country_info_list, list):
            country_info_list = [country_info_list]

        for country_name, language_code in country_info_list:

            # Wait 1 second due to free api restrictions
            # if is_free_tier:
            #     time.sleep(1)

            ical = build_ical(provider, locale, language_code, years_to_generate)

            calendar_name_parts = [country_name.replace(' ', ''), 'Holidays']
            if country_name in settings.CALENDAR_REMAP:
                new_name = settings.CALENDAR_REMAP[country_name]
                if isinstance(new_name, tuple) and len(new_name) > 1:
                    calendar_name_parts = [new_name[0], 'Holidays', new_name[1]]
                else:
                    calendar_name_parts = [new_name, 'Holidays']

            calendar_name = f"{''.join(calendar_name_parts)}.ics"
            calendar_metadata.append({
                'country': country_name,
                'locale': locale,
                'language': language_code,
                'filename': "autogen/{}".format(calendar_name),
                'datespan': date_span,
                'authors': settings.CALDATA_AUTOGEN_AUTHOR,
                'updated': str(now_utc.replace(microsecond=0).isoformat())
            })

            with open('{}{}'.format(settings.CALDATA_AUTOGEN_URL, calendar_name), 'wb') as fh:
                fh.write(ical.to_ical())

    print("Re-building calendars.json")
    with open('{}/calendars.json'.format(settings.CALDATA_AUTOGEN_URL), 'w') as fh:
        fh.write(json.dumps(calendar_metadata, indent=2))
