import argparse
import builder
import errno
import helper
import os
import shutil
import settings

from datetime import date
from dateutil.parser import parse
from thunderbird_notes import releasenotes

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

def mkdir(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def write_404_htaccess(path, lang):
    with open(os.path.join(path,'.htaccess'), 'w') as f:
        f.write('ErrorDocument 404 /{lang}/404.html\n'.format(lang=lang))


def write_htaccess(path, url):
    mkdir(path)
    with open(os.path.join(path,'.htaccess'), 'w') as f:
        f.write('RewriteEngine On\nRewriteRule .* {url}\n'.format(url=url))


def build_notes(siteobj):
    # Render release notes and system requirements for en-US only.
    lang = 'en-US'
    siteobj._switch_lang(lang)
    e = siteobj._env
    outpath = os.path.join(renderpath, lang)
    notelist = releasenotes.notes
    template = e.get_template('_includes/release-notes.html')
    e.globals.update(feedback=releasenotes.settings["feedback"], bugzilla=releasenotes.settings["bugzilla"])
    for k, n in notelist.iteritems():
        if 'beta' in k:
            e.globals.update(channel='Beta', channel_name='Beta')
        else:
            e.globals.update(channel='Release', channel_name='Release')
        n["release"]["release_date"] = n["release"].get("release_date", helper.thunderbird_desktop.get_release_date(k))

        # If there's no data at all, we can't parse an empty string for a date.
        if n["release"]["release_date"]:
            n["release"]["release_date"] = parse(str(n["release"]["release_date"]))
        e.globals.update(**n)
        target = os.path.join(outpath,'thunderbird', str(k), 'releasenotes')
        mkdir(target)
        print "Rendering {0}/index.html...".format(target)
        template.stream().dump(os.path.join(target, 'index.html'))

        target = os.path.join(outpath,'thunderbird', str(k), 'system-requirements')
        mkdir(target)
        newtemplate = e.get_template('_includes/system_requirements.html')
        print "Rendering {0}/index.html...".format(target)
        newtemplate.stream().dump(os.path.join(target, 'index.html'))

    # Build htaccess files for sysreq and release notes redirects.
    print "Writing sysreq and release notes htaccess files..."
    sysreq_path = os.path.join(renderpath, 'system-requirements')
    notes_path = os.path.join(renderpath, 'notes')
    write_htaccess(sysreq_path, settings.CANONICAL_URL + helper.thunderbird_url('system-requirements'))
    write_htaccess(notes_path, settings.CANONICAL_URL + helper.thunderbird_url('releasenotes'))
    # Default root 404 file.
    write_404_htaccess(renderpath, lang)


# Rebuild whole site from scratch.
shutil.rmtree(renderpath, ignore_errors=True)

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
parser.add_argument('--enus', nargs='?', default='', const='enus')
args = parser.parse_args()

if args.enus:
    print 'en-US output only.\n'
    languages = ['en-US']
else:
    languages = settings.PROD_LANGUAGES

site = builder.Site(languages, searchpath, renderpath, staticpath, css_bundles, js_bundles, context)

site.build_site()

for lang in languages:
    outpath = os.path.join(renderpath, lang)
    write_404_htaccess(outpath, lang)
build_notes(site)
