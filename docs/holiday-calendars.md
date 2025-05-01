# Holiday Calendars

We host a variety of holiday calendars for free which can be
found [here](https://www.thunderbird.net/en-CA/calendar/holidays/).

Previously we use to source these from the community, this was a time-consuming process so we moved to sourcing them
from a paid service: Calendarific.

This has the unfortunate effect of removing the community's ability to correct / localize specific holidays or
countries. In the future we hope to move to an open-source repo for calendar generation this is currently tracked
in [#753](https://github.com/thunderbird/thunderbird-website/issues/753).

## Calendars.json

Within `media/caldata/autogen/` is a json file named `calendars.json`. This is meant to be used by third-party services
to pull in calendar files without relying on hard-coded urls. We can't guarantee the url won't change in the future, so
it's best to periodically check this file.

## Generating Calendars

Once a quarter the calendars need to be regenerated to ensure accuracy. You can run the script via:

```shell
python build-site.py --buildcalendar 
```

You'll want to ensure you have the following env vars set:

```shell
PYTHONUNBUFFERED=1 ;CALENDARIFIC_API_KEY=<your key>;CALENDARIFIC_IS_FREE_TIER=false
```

If you are an MZLA employee you can find the api key within the infra vault in 1password.

## Development

The calendar generation script was designed to be modular so that we could slot in a different calendar provider if
needed. This has never been done, and the code may need some tweaks in order to add a new provider.

You'll find the `calgen` folder in the root of this repo. It contains three folders: `mixins`, `models`, and
`providers`.

Mixins were intended to be static holidays or corrections that the community could contribute. However they have never
been used or tested.

Models are used to convert an api response to a standardized class so they can be referenced in the build script.

Providers are essentially the api call to the service or library to retrieve information. They contain a build function
which should return a model instance.

Additionally, we have the actual ics generation script itself: `build_calendar.py`. This script is called from
`build-site.py` which passes in a provider and dict of locales. `build_calendar.py` then uses those parameters to pull from
the provider (which formats and returns the models) and saves the ics files. It also updates the calendars.json file
meant to be used as a reference for each valid calendar file.

There are also tests available in the tests directory, but these are a touch out-of-date. 
