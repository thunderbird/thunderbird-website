from calgen.models.Calendar import Calendar, CalendarTypes

from calgen.providers.Provider import Provider

import holidays


class VacanzaHolidaysProvider(Provider):
    def __init__(self, auth_options: dict):
        super().__init__("VacanzaHolidays", {})

    def query(self, country: str, year: int, additional_options: dict) -> list:
        if country == "US":
            print(country, year, additional_options)
        """Queries Calendarific, will return either the response data, or None if the api returns garbage data."""
        if country is None:
            raise RuntimeError("Country parameter is missing")
        if year is None:
            raise RuntimeError("Year parameter is missing")

        language = additional_options.get("language")


        calendar_type = additional_options.get("calendar_type")
        language = additional_options.get("language")

        if calendar_type is None:
            raise RuntimeError("Calendar Type additional option is missing")


        try:
            cal = holidays.country_holidays(country, years=year, language=language)
        except NotImplementedError:
            print(f"no calendar available for {country} with language {language}")
            return []

        return cal.items()

    def build(self, country: str, year: int, additional_options: dict):
        """Queries Calendarific, builds, and returns a list of Calendarific models from the queried data."""
        holidays = self.query(country, year, additional_options)

        holidayModels: list[Calendar] = []
        for d, n in holidays:
            c = Calendar()
            c.unique_id = hash(str(d) + n)
            c.year = year
            c.iso_date = d
            c.name = n
            c.description = n
            c.calendar_type = CalendarTypes.NATIONAL

            holidayModels.append(c)

        return holidayModels
