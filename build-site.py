import argparse
import sys

import build_calendar
import os.path

import builder
import feedparser
import helper
import settings

from datetime import date

from calgen.providers.CalendarificProvider import CalendarificProvider

parser = argparse.ArgumentParser()
parser.add_argument('--enus', help='Only build the en-US language.', action='store_true')
parser.add_argument('--debug', help='Log output with more detailed build information.', action='store_true')
parser.add_argument('--updates', help='Build the updates directory for updates.thunderbird.net.',
                    action='store_true')
parser.add_argument('--startpage', help='Build the start page instead of the main thunderbird.net website.',
                    action='store_true')
parser.add_argument('--buildcalendars', help='Builds the ics calendar files, instead of the websites.',
                    action='store_true')
parser.add_argument('--downloadlegal', help='Download the Thunderbird privacy policy document.', action='store_true')
parser.add_argument('--watch', help='Rebuild when template and asset dirs are changed, and run a server on localhost.',
                    action='store_true')
parser.add_argument('--port', const=8000, default=8000, type=int,
                    help='Port for the server that runs with --watch.', nargs='?')
parser.add_argument('--devmode', help='Enables various behaviours that would be helpful for development. (e.g. not hard crashing on jinja syntax errors.)', action='store_true')
args = parser.parse_args()

if args.enus:
    langmsg = 'in en-US only.'
    languages = ['en-US']
    calendar_locales = {'US': settings.CALENDAR_LOCALES.get('US')}
else:
    langmsg = 'in all languages.'
    languages = settings.PROD_LANGUAGES
    calendar_locales = settings.CALENDAR_LOCALES

if args.startpage:
    print('Rendering start page ' + langmsg)
    site = builder.Site(languages, settings.START_PATH, settings.START_RENDERPATH, settings.START_CSS, debug=args.debug, dev_mode=args.devmode)
    site.build_startpage()
elif args.updates:
    print(f'Rendering updates {langmsg}')

    # Prepare data and build main website.
    default_channel = settings.DEFAULT_RELEASE_VERSION
    version = helper.thunderbird_desktop.latest_version(default_channel)
    beta_version = helper.thunderbird_desktop.latest_version('beta')

    context = {
        'current_year': date.today().year,
        'matomo_site_id': settings.MATOMO_SITE_IDS.get('utn'),
    }

    site = builder.Site(languages, settings.UPDATES_PATH, settings.UPDATES_RENDERPATH, settings.UPDATES_CSS, js_bundles=settings.UPDATES_JS, data=context, debug=args.debug, dev_mode=args.devmode)
    site.build_updates()
elif args.buildcalendars:
    print("Building calendar files")

    try:
        api_key = os.environ['CALENDARIFIC_API_KEY']
    except KeyError:
        sys.exit("No `CALENDARIFIC_API_KEY` defined.")

    build_calendar.build_calendars(CalendarificProvider({'api_key': api_key}), calendar_locales)
elif args.downloadlegal:
    print("Downloading legal documents")
    legal = builder.Legal(settings.WEBSITE_PATH)
    legal.download()
else:
    print('Rendering www.thunderbird.net ' + langmsg)
    # Prepare data and build main website.
    default_channel = settings.DEFAULT_RELEASE_VERSION
    version = helper.thunderbird_desktop.latest_version(default_channel)
    beta_version = helper.thunderbird_desktop.latest_version('beta')

    if os.path.exists('media/caldata/autogen/calendars.json'):
        caldata = helper.load_calendar_json('media/caldata/autogen/calendars.json')
    else:
        caldata = helper.load_calendar_json('media/caldata/calendars.json')

    context = {'current_year': date.today().year,
               'platform': 'desktop',
               'query': '',
               'platforms': helper.thunderbird_desktop.platforms('release'),
               'full_builds_version': version.split('.', 1)[0],
               'full_builds': helper.thunderbird_desktop.get_filtered_full_builds('release', version),
               'full_builds_beta': helper.thunderbird_desktop.get_filtered_full_builds('beta', beta_version),
               'channel_label': 'Thunderbird',
               'releases': helper.thunderbird_desktop.list_releases(),
               'calendars': caldata['calendars'],
               'letters': caldata['letters'],
               'CALDATA_URL': settings.CALDATA_URL,
               'latest_thunderbird_version': version,
               'latest_thunderbird_beta_version': beta_version,
               'blog_data': [],
               'default_channel': default_channel
               }

    site = builder.Site(languages, settings.WEBSITE_PATH, settings.WEBSITE_RENDERPATH,
                        settings.WEBSITE_CSS, js_bundles=settings.WEBSITE_JS, data=context, debug=args.debug, dev_mode=args.devmode)
    site.build_website()

if args.watch:
    builder.setup_observer(site, args.port)
