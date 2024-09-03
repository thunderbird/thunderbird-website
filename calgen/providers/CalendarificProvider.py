import requests

import helper
import settings
from calgen.models.Calendarific import Calendarific

from calgen.providers.Provider import Provider


class CalendarificProvider(Provider):
    def __init__(self, auth_options: dict):
        super().__init__('Calendarific', auth_options)
        self.api_key = self.auth_options.get('api_key')
        self.is_free_tier = helper.is_calendarific_free_tier()

    def query(self, country: str, year: int, additional_options: dict) -> list:
        """ Queries Calendarific, will return either the response data, or None if the api returns garbage data. """
        if country is None:
            raise RuntimeError("Country parameter is missing")
        if year is None:
            raise RuntimeError("Year parameter is missing")

        calendar_type = additional_options.get('calendar_type')
        language = additional_options.get('language')

        if calendar_type is None:
            raise RuntimeError("Calendar Type additional option is missing")

        payload = {
            'api_key': self.api_key,
            'country': country,
            'year': year,
            'type': calendar_type,
        }

        if not self.is_free_tier:
            payload['language'] = language
            payload['uuid'] = True

        response = requests.get(settings.CALENDARIFIC_API_URL, params=payload)
        response.raise_for_status()

        try:
            # Response is something like { 'meta': { 'code': 200 }, 'response': { 'holidays': [ ... ] } }
            # Sometimes holidays is empty, sometimes response is an empty list...
            data = response.json().get('response', {})
            return data.get('holidays', [])
        except Exception as e:
            print(f"Malformed response for {country} on year {year} with type {calendar_type}")
            print("Response -> ", response.json())
            print("Exception", e)
            return []

    def build(self, country: str, year: int, additional_options: dict):
        """ Queries Calendarific, builds, and returns a list of Calendarific models from the queried data. """
        holidays = self.query(country, year, additional_options)
        return [Calendarific(holiday, year, additional_options.get('calendar_type')) for holiday in holidays]
