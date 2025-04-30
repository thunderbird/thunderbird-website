from datetime import datetime

import helper
from calgen.models.Calendar import Calendar, CalendarTypes


class Calendarific(Calendar):
    """
    API Documentation available at: https://calendarific.com/api-documentation

    Instantiate this calendar api class to parse Calendarific api data
    """

    def __init__(self, data: dict = None, year: int = None, calendar_type: CalendarTypes = CalendarTypes.NATIONAL):
        super(Calendarific, self).__init__(data, year)
        self.calendar_type = calendar_type

        if data:
            self.from_api(data)

    def handle_regional_labelling(self, name: str, all_locations: str, regions: list):
        """Handle regional naming for holidays that fall under the CalendarTypes.LOCAL"""
        if len(regions) > 1:
            return f"{name} ({all_locations})"
        else:
            return f"{name} ({regions[0]['name']})"

    def from_api(self, data: dict):
        date = data.get('date')
        iso_date = None
        if date is not None:
            iso_date = datetime.fromisoformat(date.get('iso'))

        # Location is a single string (which is usually but not always the region code) vs regions which is a list
        regions = data.get('states')
        locations = data.get('locations')

        location_slugs = locations.lower().replace(', ', '-')

        if locations and locations.lower() != 'all' and regions and len(regions) > 0:
            self.name = self.handle_regional_labelling(data.get('name'),
                                                       all_locations=locations,
                                                       regions=data.get('states'))
        else:
            self.name = data.get('name')

        description = data.get('description')
        primary_type = data.get('primary_type')

        if description or primary_type:
            self.description = " - ".join(filter(lambda x: x, [primary_type, description]))
        elif primary_type:
            self.description = primary_type
        else:
            self.description = description

        self.unique_id = data.get('urlid') if helper.is_calendarific_free_tier() else data.get('uuid')
        # Always append calendar year
        self.unique_id = f'{self.unique_id}-{iso_date.year}'
        if location_slugs:
            self.unique_id = f'{self.unique_id}-{location_slugs}'

        self.iso_date = iso_date

        return self
