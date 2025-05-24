import hashlib

from calgen.models.Calendar import Calendar, CalendarTypes


class VacanzaHolidays(Calendar):
    """
    Instantiate this calendar api class to further parse Holidays data
    """

    def __init__(
        self,
        data: dict = None,
        year: int = None,
    ):
        super(VacanzaHolidays, self).__init__(data, year)

        if data:
            self.from_api(data)

    def handle_regional_labelling(
        self,
        name: str,
        subdivs: list[tuple[str, str]],
        subdivs_except: bool = False,
    ):
        """Handle regional naming for holidays that fall under the CalendarTypes.LOCAL"""
        # there is no subdivs -> everywhere
        if not len(subdivs):
            return name

        # this should really be localised, but uncertain how to do this best
        subdivs_except_text = ""
        if subdivs_except:
            subdivs_except_text = "All except "

        if len(subdivs) == 1:
            return f"{name} ({subdivs_except_text}{subdivs[0][1]})"

        subdivs_concat = ", ".join([v[0] for v in subdivs])

        return f"{name} ({subdivs_except_text}{subdivs_concat})"

    def from_api(self, data: dict):
        date = data.get("date")
        name = data.get("name")
        subdivs = data.get("subdivs")
        subdivs_except = data.get("subdivs_except")

        # generate unique_id. There could be a better way, but this should suffice
        subdivs_hash_concat = ", ".join([v[0] for v in subdivs])
        unique_str = data.get("country") + str(date) + name + str(self.year) + subdivs_hash_concat
        self.unique_id = hashlib.sha1(unique_str.encode("utf8")).hexdigest()

        # rest of data
        self.iso_date = date
        self.name = self.handle_regional_labelling(name, subdivs, subdivs_except)
        self.description = self.name
        self.calendar_type = data.get("calendar_type")
