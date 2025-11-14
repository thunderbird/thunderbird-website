"""
Build script for Thunderbird websites and related resources.

This script handles building various Thunderbird web properties including:
- Main website (www.thunderbird.net)
- Start page
- Updates site (updates.thunderbird.net)
- Calendar files
- tb.pro site

It also provides utilities for downloading legal documents and watching for changes.
"""

import argparse
import sys
import os.path
from datetime import date

import build_calendar
import builder

import helper
import settings

from calgen.providers.CalendarificProvider import CalendarificProvider

def setup_argument_parser():
    """Configure and return the argument parser for command line options."""
    parser = argparse.ArgumentParser(description='Build Thunderbird websites and resources')
    parser.add_argument('--enus', help='Only build the en-US language.', action='store_true')
    parser.add_argument('--debug', help='Log output with more detailed build information.', action='store_true')
    parser.add_argument('--updates', help='Build the updates directory for updates.thunderbird.net.',
                        action='store_true')
    parser.add_argument('--startpage', help='Build the start page instead of the main thunderbird.net website.',
                        action='store_true')
    parser.add_argument('--buildcalendars', help='Builds the ics calendar files, instead of the websites.',
                        action='store_true')
    parser.add_argument('--downloadlegal', help='Download the Thunderbird privacy policy document.', action='store_true')
    parser.add_argument('--tbpro', help='Build the tb.pro site.', action='store_true')
    parser.add_argument('--watch', help='Rebuild when template and asset dirs are changed, and run a server on localhost.',
                        action='store_true')
    parser.add_argument('--port', const=8000, default=8000, type=int,
                        help='Port for the server that runs with --watch.', nargs='?')
    return parser

parser = setup_argument_parser()
args = parser.parse_args()

def get_language_settings(enus_only=False):
    """Return language settings based on whether we're building for en-US only or all languages."""
    if enus_only:
        langmsg = 'in en-US only.'
        languages = ['en-US']
        calendar_locales = {'US': settings.CALENDAR_LOCALES.get('US')}
    else:
        langmsg = 'in all languages.'
        languages = settings.PROD_LANGUAGES
        calendar_locales = settings.CALENDAR_LOCALES

    return langmsg, languages, calendar_locales

langmsg, languages, calendar_locales = get_language_settings(args.enus)

def build_startpage():
    """Build the Thunderbird start page."""
    print(f'Rendering start page {langmsg}')
    site = builder.Site(languages, settings.START_PATH, settings.START_RENDERPATH,
                       settings.START_CSS, debug=args.debug, dev_mode=args.watch)
    site.build_startpage()
    return site

def build_updates():
    """Build the updates.thunderbird.net site."""
    print(f'Rendering updates {langmsg}')

    default_channel = settings.DEFAULT_RELEASE_VERSION
    version = helper.thunderbird_desktop.latest_version(default_channel)
    beta_version = helper.thunderbird_desktop.latest_version('beta')

    context = {
        'current_year': date.today().year,
        'matomo_site_id': settings.MATOMO_SITE_IDS.get('utn'),
    }

    site = builder.Site(languages, settings.UPDATES_PATH, settings.UPDATES_RENDERPATH,
                       settings.UPDATES_CSS, js_bundles=settings.UPDATES_JS,
                       data=context, debug=args.debug, dev_mode=args.watch,
                       common_searchpath=settings.COMMON_SEARCHPATH)
    site.build_updates()
    return site

def build_calendars():
    """Build the calendar files."""
    print("Building calendar files")
    try:
        api_key = os.environ['CALENDARIFIC_API_KEY']
    except KeyError:
        sys.exit("No `CALENDARIFIC_API_KEY` defined.")
    build_calendar.build_calendars(CalendarificProvider({'api_key': api_key}), calendar_locales)

def download_legal():
    """Download legal documents."""
    print("Downloading legal documents")
    legal = builder.Legal(settings.WEBSITE_PATH)
    legal.download()

def build_tbpro():
    """Build the tb.pro site."""
    print("Building tb.pro site")

    context = {
        'current_year': date.today().year,
        'default_plan': settings.TBPRO_DEFAULT_PLAN,
    }
    site = builder.Site(languages, settings.TBPRO_PATH, settings.TBPRO_RENDERPATH,
                       settings.TBPRO_CSS, js_bundles=settings.TBPRO_JS,
                       data=context, debug=args.debug, dev_mode=args.watch,
                       common_searchpath=settings.COMMON_SEARCHPATH)
    site.build_tbpro()
    return site

def build_main_website():
    """Build the main www.thunderbird.net website."""
    print(f'Rendering www.thunderbird.net {langmsg}')
    default_channel = settings.DEFAULT_RELEASE_VERSION
    version = helper.thunderbird_desktop.latest_version(default_channel)
    beta_version = helper.thunderbird_desktop.latest_version('beta')

    if os.path.exists('media/caldata/autogen/calendars.json'):
        caldata = helper.load_calendar_json('media/caldata/autogen/calendars.json')
    else:
        caldata = helper.load_calendar_json('media/caldata/calendars.json')

    context = {
        'current_year': date.today().year,
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
                       settings.WEBSITE_CSS, js_bundles=settings.WEBSITE_JS,
                       data=context, debug=args.debug, dev_mode=args.watch,
                       common_searchpath=settings.COMMON_SEARCHPATH)
    site.build_website()
    return site

site = None

if args.startpage:
    site = build_startpage()
elif args.updates:
    site = build_updates()
elif args.tbpro:
    site = build_tbpro()
elif args.buildcalendars:
    build_calendars()
elif args.downloadlegal:
    download_legal()
else:
    site = build_main_website()

# Set up file watcher if requested.
if args.watch and site:
    builder.setup_observer(site, args.port)
