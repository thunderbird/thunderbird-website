from calgen.models.VacanzaHolidays import VacanzaHoliday

from calgen.providers.Provider import Provider

import holidays

class VacanzaHolidaysProvider(Provider):
    def __init__(self, auth_options: dict):
        super().__init__("VacanzaHolidays", {})

    def query(self, country: str, year: int, additional_options: dict) -> list:
        """Utilises Holidays library, will retun the processed holidays from the library, with regions, etc."""
        if country is None:
            raise RuntimeError("Country parameter is missing")
        if year is None:
            raise RuntimeError("Year parameter is missing")

        calendar_type = additional_options.get("calendar_type")
        language = additional_options.get("language")

        if calendar_type is None:
            raise RuntimeError("Calendar Type additional option is missing")

        # ensure that country, language, year exists + so we can get all subdivisions
        try:
            cal = holidays.country_holidays(country, years=year, language=language)
        except NotImplementedError:
            print(
                f"no calendar available for {country} with language {language} (year {year})"
            )
            return []

        # all subdivisions for this country
        subdivs = cal.subdivisions

        # handle cases with no subdivs
        if len(subdivs) == 0:
            subdivs = [False]

        holidays_hashmap: dict[int, VacanzaHoliday] = {}
        for subdiv in subdivs:
            tcal = holidays.country_holidays(
                country,
                years=year,
                language=language,
                subdiv=subdiv,
                categories=cal.supported_categories,
            )

            map_subdiv_to_name = {v: k for k, v in cal.subdivisions_aliases.items()}

            for holiday_date, holiday_name in tcal.items():
                k = hash(str(holiday_date) + holiday_name)
                if k not in holidays_hashmap:
                    holidays_hashmap[k] = VacanzaHoliday(
                        country,
                        holiday_date,
                        holiday_name,
                        subdivs,
                        # cal.subdivisions_aliases,
                        map_subdiv_to_name,
                        # subdiv_to_name,
                    )

                holidays_hashmap[k].add_subdiv(subdiv)

        return list(
            filter(
                lambda x: x.get_calendar_type() == calendar_type,
                holidays_hashmap.values(),
            )
        )

    def build(self, country: str, year: int, additional_options: dict):
        """Utilises Holidays, builds, and returns a list of VacanzaHolidays models from the resulting data."""
        holidays = self.query(country, year, additional_options)

        for h in holidays:
            # no data, already included
            h.from_api({})

        return holidays
