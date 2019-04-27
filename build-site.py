import argparse
import builder
import errno
import helper
import os
import shutil
import settings

from datetime import date

parser = argparse.ArgumentParser()
parser.add_argument('--enus', action='store_true')
parser.add_argument('--debug', action='store_true')
parser.add_argument('--startpage', action='store_true')
parser.add_argument('--watch', action='store_true')

args = parser.parse_args()

if args.enus:
    langmsg = 'in en-US only.'
    languages = ['en-US']
else:
    langmsg = 'in all languages.'
    languages = settings.PROD_LANGUAGES

if args.startpage:
    print 'Rendering start page ' + langmsg
    site = builder.Site(languages, settings.START_PATH, settings.START_RENDERPATH, settings.START_CSS, debug=args.debug)
    site.build_startpage()
else:
    print 'Rendering www.thunderbird.net ' + langmsg
    # Prepare data and build main website.
    version = helper.thunderbird_desktop.latest_version('release')
    caldata = helper.load_calendar_json('media/caldata/calendars.json')
    context = {'current_year': date.today().year,
               'platform': 'desktop',
               'query': '',
               'platforms': helper.thunderbird_desktop.platforms('release'),
               'full_builds_version': version.split('.', 1)[0],
               'full_builds': helper.thunderbird_desktop.get_filtered_full_builds('release', helper.thunderbird_desktop.latest_version()),
               'full_builds_beta': helper.thunderbird_desktop.get_filtered_full_builds('beta', helper.thunderbird_desktop.latest_version('beta')),
               'channel_label': 'Thunderbird',
               'releases': helper.thunderbird_desktop.list_releases(),
               'calendars': caldata['calendars'],
               'letters': caldata['letters'],
               'CALDATA_URL': settings.CALDATA_URL,
               'latest_thunderbird_version': version,
              }

    site = builder.Site(languages, settings.WEBSITE_PATH, settings.WEBSITE_RENDERPATH,
        settings.WEBSITE_CSS, js_bundles=settings.WEBSITE_JS, data=context, debug=args.debug)
    site.build_website()

if args.watch:
    builder.setup_observer(site)
