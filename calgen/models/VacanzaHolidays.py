from datetime import datetime
import hashlib

from calgen.models.Calendar import Calendar, CalendarTypes


class VacanzaHoliday(Calendar):
    def __init__(
        self,
        country: str,
        holiday_date: datetime,
        holiday_name: str,
        all_subdivs: list[str],
        map_subdiv_to_name: dict[str, str],
    ):
        super(VacanzaHoliday, self).__init__({}, holiday_date.year)

        # holiday information
        self._country = country
        self._date = holiday_date
        self._name = holiday_name

        # maps a subdiv e.g. Alaska to AK
        self._map_subdiv_to_name: dict[str, str] = map_subdiv_to_name
        self._all_subdivs: list[str] = all_subdivs

        self._subdivs: list[str] = []

    def add_subdiv(self, subdiv: str):
        if not subdiv:
            return

        self._subdivs.append(subdiv)

    def get_calendar_type(self) -> CalendarTypes:
        if len(self._all_subdivs) == len(self._subdivs) or len(self._subdivs) == 0:
            return CalendarTypes.NATIONAL

        return CalendarTypes.LOCAL

    def regional_label(self):
        """Handle regional naming for holidays that fall under the CalendarTypes.LOCAL"""

        # national holiday -> just the name
        if self.get_calendar_type() == CalendarTypes.NATIONAL:
            return self._name

        # keep track of our subdivs, needed when we use the excluded (except text)
        subdivs = self._subdivs
        excluded_text: str = ""

        # check if we can shorten the list, e.g. the length
        # of subdivs is bigger than half of the TOTAL subdivs
        if len(subdivs) >= len(self._all_subdivs) / 2:
            excluded_subdivs: list[str] = []
            for subdiv in self._all_subdivs:
                if subdiv in subdivs:
                    continue

                excluded_subdivs.append(subdiv)

            # insert the excluded text here
            # it should be done in a better way than this...
            excluded_text = "All except "
            subdivs = excluded_subdivs

        # only one subdiv, use the real name, not alias
        if len(subdivs) == 1:
            subdiv = subdivs[0]
            subdivs = [self._map_subdiv_to_name.get(subdiv, subdiv)]

        # concat and return
        concat_subdivs = ", ".join(subdivs)
        return f"{self._name} ({excluded_text}{concat_subdivs})"

    def from_api(self, data: dict):
        # generate unique_id. There could be a better way, but this should suffice
        subdivs_hash_concat = ", ".join([v for v in self._subdivs])
        unique_str = (
            self._country
            + str(self._date)
            + self._name
            + str(self.year)
            + subdivs_hash_concat
        )
        self.unique_id = hashlib.sha1(unique_str.encode("utf8")).hexdigest()

        # rest of data
        self.iso_date = self._date
        self.name = self.regional_label()
        self.description = self.name
        self.calendar_type = self.get_calendar_type()
