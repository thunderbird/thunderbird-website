import argparse
import builder
import errno
import helper
import os
import shutil
import settings

from datetime import date


# Path to search for templates.
searchpath = 'website'
# Static file/media path.
staticpath = 'website/_media'
# Path to render the finished site to.
renderpath = 'thunderbird.net'

css_bundles = {
                'calendar-bundle': ['less/thunderbird/calendar.less', 'less/base/menu-resp.less'],
                'responsive-bundle': ['less/sandstone/sandstone-resp.less', 'less/base/global-nav.less'],
                'thunderbird-landing': ['less/thunderbird/landing.less', 'less/base/menu-resp.less'],
                'thunderbird-features': ['less/thunderbird/features.less', 'less/base/menu-resp.less'],
                'thunderbird-channel': ['less/thunderbird/channel.less', 'less/base/menu-resp.less'],
                'thunderbird-organizations': ['less/thunderbird/organizations.less', 'less/base/menu-resp.less'],
                'thunderbird-all': ['less/thunderbird/all.less', 'less/base/menu-resp.less'],
                'releasenotes': ['less/firefox/releasenotes.less', 'less/base/menu-resp.less'],
                'releases-index': ['less/firefox/releases-index.less', 'less/base/menu-resp.less'],
            }

js_bundles = { 'common-bundle': ['js/common/jquery-1.11.3.min.js', 'js/common/spin.min.js', 'js/common/mozilla-utils.js',
                'js/common/form.js', 'js/common/mozilla-client.js', 'js/common/mozilla-image-helper.js',
                'js/common/nav-main-resp.js', 'js/common/class-list-polyfill.js', 'js/common/mozilla-global-nav.js',
                'js/common/base-page-init.js', 'js/common/core-datalayer.js', 'js/common/core-datalayer-init.js',
                'js/common/autodownload.js']
             }

# Prepare data.
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

parser = argparse.ArgumentParser()
parser.add_argument('--enus', action='store_true')
parser.add_argument('--debug', action='store_true')
args = parser.parse_args()

if args.enus:
    print 'Rendering en-US locale only.'
    languages = ['en-US']
else:
    languages = settings.PROD_LANGUAGES

site = builder.Site(languages, searchpath, renderpath, staticpath, css_bundles, js_bundles=js_bundles, data=context, debug = args.debug)
site.build_website()
