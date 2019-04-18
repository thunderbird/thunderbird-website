import errno
import helper
import jinja2
import os
import shutil
import settings
import translate
import webassets

from datetime import date
from dateutil.parser import parse
from thunderbird_notes import releasenotes
from staticjinja import make_site

extensions = ['jinja2.ext.i18n']

# Path to search for templates.
searchpath = 'website'
# Static file/media path.
staticpath = 'website/_media'
# Path to render the finished site to.
renderpath = 'thunderbird.net'
# Paths to compile CSS and concat JS to.
cssout = renderpath+'/media/css'
jsout = renderpath+'/media/js'

css_bundles = [ {'calendar-bundle': ['less/thunderbird/calendar.less', 'less/base/menu-resp.less']},
                {'responsive-bundle': ['less/sandstone/sandstone-resp.less', 'less/base/global-nav.less']},
                {'thunderbird-landing': ['less/thunderbird/landing.less', 'less/base/menu-resp.less']},
                {'thunderbird-features': ['less/thunderbird/features.less', 'less/base/menu-resp.less']},
                {'thunderbird-channel': ['less/thunderbird/channel.less', 'less/base/menu-resp.less']},
                {'thunderbird-organizations': ['less/thunderbird/organizations.less', 'less/base/menu-resp.less']},
                {'thunderbird-all': ['less/thunderbird/all.less', 'less/base/menu-resp.less']},
                {'releasenotes': ['less/firefox/releasenotes.less', 'less/base/menu-resp.less']},
                {'releases-index': ['less/firefox/releases-index.less', 'less/base/menu-resp.less']},
              ]

js_bundles = [ {'common-bundle': ['js/common/jquery-1.11.3.min.js', 'js/common/spin.min.js', 'js/common/mozilla-utils.js',
                                  'js/common/form.js', 'js/common/mozilla-client.js', 'js/common/mozilla-image-helper.js',
                                  'js/common/nav-main-resp.js', 'js/common/class-list-polyfill.js', 'js/common/mozilla-global-nav.js',
                                  'js/common/base-page-init.js', 'js/common/core-datalayer.js', 'js/common/core-datalayer-init.js',
                                  'js/common/autodownload.js']
               }
             ]

def mkdir(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def write_htaccess(path, url):
    mkdir(path)
    with open(os.path.join(path,'.htaccess'), 'w') as f:
        f.write('RewriteEngine On\nRewriteRule .* {url}\n'.format(url=url))


def write_404_htaccess(path, lang):
    with open(os.path.join(path,'.htaccess'), 'w') as f:
        f.write('ErrorDocument 404 /{lang}/404.html\n'.format(lang=lang))


def read_file(file):
    with open(file, 'r') as f:
        return f.read()


def concat_js(bundle):
    bundle_name, files = bundle.popitem()
    bundle_path = jsout+'/'+bundle_name+'.js'

    js_string = '\n'.join(read_file(settings.ASSETS + '/' + file) for file in files)
    with open(bundle_path, 'w') as f:
        f.write(js_string)


def build_assets():
    env = webassets.Environment(load_path=[settings.ASSETS], directory=cssout, url=settings.MEDIA_URL, cache=False, manifest=False)
    for bundle in css_bundles:
        k, v = bundle.popitem()
        reg = webassets.Bundle(*v, filters='less', output=k+'.css')
        env.register(k, reg)
        env[k].urls()

    for bundle in js_bundles:
        concat_js(bundle)


def text_dir(lang):
    textdir = 'ltr'
    if lang in settings.LANGUAGES_BIDI:
        textdir = 'rtl'
    return textdir


def build_site(lang):
    version = helper.thunderbird_desktop.latest_version('release')
    caldata = helper.load_calendar_json('media/caldata/calendars.json')
    context = {'LANG': lang,
               'current_year': date.today().year,
               'DIR': text_dir(lang),
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

    outpath = os.path.join(renderpath, lang)
    if not os.path.exists(outpath):
        os.makedirs(outpath)
    site = make_site(outpath=outpath, searchpath=searchpath, extensions=extensions, env_globals=context)

    translator = translate.gettext_object(lang)
    site._env.install_gettext_translations(translator)

    # Add l10n_css function to context.
    site._env.globals.update(translations=translator.get_translations(), l10n_css=translator.l10n_css, settings=settings, **helper.contextfunctions)
    site._env.filters["markdown"] = helper.safe_markdown
    site._env.filters["f"] = helper.f
    site._env.filters["l10n_format_date"] = helper.l10n_format_date
    write_404_htaccess(outpath, lang)
    site.render(use_reloader=False)

    # Render release notes and system requirements for en-US only.
    if lang == settings.LANGUAGE_CODE:
        notelist = releasenotes.notes
        e = site._env
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
            with open(os.path.join(target, 'index.html'), "wb") as f:
                print "Rendering {0}/index.html...".format(target)
                o = template.render()
                f.write(o.encode('utf8'))

            target = os.path.join(outpath,'thunderbird', str(k), 'system-requirements')
            mkdir(target)
            newtemplate = e.get_template('_includes/system_requirements.html')
            with open(os.path.join(target, 'index.html'), "wb") as f:
                print "Rendering {0}/index.html...".format(target)
                o = newtemplate.render()
                f.write(o.encode('utf8'))

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

# en-US
build_site(settings.LANGUAGE_CODE)

for lang in settings.PROD_LANGUAGES:
    build_site(lang)

print "Copying media files..."
shutil.copytree(staticpath, renderpath+'/media')
print "Building assets..."
build_assets()
