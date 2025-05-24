from calgen.models.Calendar import Calendar, CalendarTypes
from calgen.models.VacanzaHolidays import VacanzaHolidays

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
            print(f"no calendar available for {country} with language {language}")
            return []

        # all subdivisions for this country
        subdivs = cal.subdivisions

        # get the names for all the subdivisions
        subdiv_to_name = {v: k for k, v in cal.subdivisions_aliases.items()}

        # handle cases with no subdivs
        if len(subdivs) == 0:
            subdivs = [False]
            subdiv_to_name[False] = ""

        # hold all holidays, including which divisions has it
        holidays_with_subdivs: dict = {}
        for subdiv in subdivs:
            tcal = holidays.country_holidays(
                country,
                years=year,
                language=language,
                subdiv=subdiv,
                categories=cal.supported_categories,
            )
            for d, n in tcal.items():
                k = hash(str(d) + n)
                if k not in holidays_with_subdivs:
                    holidays_with_subdivs[k] = {
                        "country": country,
                        "date": d,
                        "name": n,
                        "subdivs_except": False,
                        "subdivs": [],
                        "calendar_type": CalendarTypes.LOCAL,
                    }
                holidays_with_subdivs[k]["subdivs"].append(
                    (subdiv, subdiv_to_name.get(subdiv, subdiv))
                )

        # if a holidays has ALL the subdivs, then it is a national holiday,
        # and we remove ALL subdivs from it, otherwise it is local.
        # if it as a local holiday, then we try to figure out if we can
        # shorten it by saying "everywhere, EXCEPT these regions"
        for k, holiday_with_subdivs in holidays_with_subdivs.items():
            subdivs = holiday_with_subdivs["subdivs"]
            if len(subdivs) == len(cal.subdivisions):
                holidays_with_subdivs[k]["calendar_type"] = CalendarTypes.NATIONAL
                holidays_with_subdivs[k]["subdivs"] = []
                continue

            # unable to shorten it, just give up
            if not len(subdivs) >= len(cal.subdivisions) / 2:
                continue

            # take out only teh aliases, so that we can filter it
            subdivs_only_aliases = [v[0] for v in subdivs]
            # filter out based on ALL the subdivisions available
            except_subdiv_aliases = list(
                filter(
                    lambda subdiv: subdiv not in subdivs_only_aliases, cal.subdivisions
                )
            )

            # generate the subdivs again, and say this is everywhere EXCEPT these
            holidays_with_subdivs[k]["subdivs"] = [
                (v, subdiv_to_name.get(v, v)) for v in except_subdiv_aliases
            ]
            holidays_with_subdivs[k]["subdivs_except"] = True

        return list(
            filter(
                lambda x: x["calendar_type"].value == calendar_type,
                holidays_with_subdivs.values(),
            )
        )

    def build(self, country: str, year: int, additional_options: dict):
        """Utilises Holidays, builds, and returns a list of VacanzaHolidays models from the resulting data."""
        holidays = self.query(country, year, additional_options)

        return [VacanzaHolidays(holiday, year) for holiday in holidays]
