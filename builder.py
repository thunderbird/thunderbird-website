import datetime
import errno

import jinja2.exceptions
import markdown
import markupsafe
import requests

import helper
import logging
import multiprocessing
import ntpath
import os
import pathlib
import shutil
import settings
import sys
import time
import translate
import webassets

from socketserver import TCPServer
import http.server

from product_details import thunderbird_desktop

TCPServer.allow_reuse_address = True
SimpleHTTPServer = http.server.HTTPServer
SimpleHTTPRequestHandler = http.server.SimpleHTTPRequestHandler

from dateutil.parser import parse
from jinja2 import Environment, FileSystemLoader
from libs.thunderbird_notes import releasenotes
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import urllib.parse

extensions = ['jinja2.ext.i18n']

# Logging default off unless debug = True.
logger = logging.getLogger(__name__)
sh = logging.StreamHandler(sys.stdout)
logger.addHandler(sh)


def read_file(file):
    """Read `file` and return contents."""
    with open(file, 'r') as f:
        return f.read()


def mkdir(path):
    """Make dirs in a `path`, ignoring errors if it exists."""
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def write_site_htaccess(renderpath: str, lang: str, redirects: dict, redirect_request=False):
    """Writes .htaccess files from a given redirects dictionary for the given language."""
    for path, url_key in redirects.items():
        # Normalize non-tuples
        if type(path) is not tuple:
            path = (path,)
        path = os.path.join(renderpath, lang, *path)
        redirect_path = helper.url({'LANG': lang}, url_key)
        write_htaccess(path, redirect_path, redirect_request)


def write_htaccess_custom(path, rules: str):
    """Write an .htaccess to `path` that rewrites based on custom rules"""
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, '.htaccess'), 'w') as f:
        f.write(rules)


def write_htaccess(path, url, redirect_request=False):
    """Write an .htaccess to `path` that rewrites everything to `url`."""
    tags = ''
    if redirect_request:
        tags = ' [R]'
    write_htaccess_custom(path, 'RewriteEngine On\nRewriteRule .* {url}{tags}\n'.format(url=url, tags=tags))


def write_404_htaccess(path, lang):
    """Write an .htaccess to `path` that points to 404.html for locale `lang`."""
    write_htaccess_custom(path, 'ErrorDocument 404 /{lang}/404.html\n'.format(lang=lang))


def delete_contents(dirpath):
    """Delete all contents of `dirpath` except the root dir. Workaround for shutil.rmtree."""
    if os.path.exists(dirpath):
        for filename in os.listdir(dirpath):
            filepath = os.path.join(dirpath, filename)
            try:
                shutil.rmtree(filepath)
            except OSError:
                os.remove(filepath)


class Legal:
    """
    Legal building class
    This will download the Thunderbird desktop privacy policy and place it in the includes directory.
    Parameters:
        `template_path` (str): Path to search for templates in.
    """
    def __init__(self, template_path: str):
        self.template_path = template_path

    def download(self):
        directory = os.path.join(self.template_path, 'includes', 'privacy')
        os.makedirs(directory, exist_ok=True)

        contents = requests.get(settings.THUNDERBIRD_DESKTOP_PRIVACY_POLICY_URL).text
        html = markupsafe.Markup(markdown.markdown(contents, extensions=['markdown.extensions.attr_list']))

        html = f'{{# THIS PAGE IS AUTOMATICALLY GENERATED, DO NOT EDIT THIS DOCUMENT! #}}\n{html}'

        with open(os.path.join(directory, 'privacy-desktop.html'), 'w') as fh:
            fh.write(html)


class Site(object):
    """
    Main website building class.
    Parameters:
        `languages` (list of str): List of locales to build the website for.
        `searchpath` (str): Path to search for templates in.
        `renderpath` (str): Path to render the finished static files to.
        `css_bundles` (dict): dict containing lists of less files to be compiled into css and copied to `renderpath`.
        `staticdir` (str, optional): directory under the `searchpath` that contains static media files.
        `js_bundles` (dict, optional): dict containing lists of js files to be concatenated together and copied to `renderpath`.
        `data` (dict, optional): dict to be directly added to the Jinja2 global context.
        `debug` (bool, optional): Optionally write log output or not.
        `dev_mode` (bool, optional): Enables various behaviours that would be helpful for develoeprs. Don't use on prod.
    Attributes:
        `lang`: Current language to build the site in, an element of `languages`.
    """
    def __init__(self, languages, searchpath, renderpath, css_bundles, staticdir='_media', js_bundles={}, data={}, debug=False, dev_mode=False):
        self.languages = languages
        self.lang = languages[0]
        self.context = {}
        self.searchpath = searchpath
        self.renderpath = renderpath
        self.staticpath = os.path.join(searchpath, staticdir)
        self.cssout = renderpath + '/media/css'
        self.css_bundles = css_bundles
        self.js_bundles = js_bundles
        self.jsout = renderpath + '/media/js'
        self.data = data
        self._setup_env()
        self._env.globals.update(settings=settings, **helper.contextfunctions)
        self.dev_mode = dev_mode
        if debug:
            logger.setLevel(logging.INFO)

    @property
    def outpath(self):
        """Return path for rendering that includes the current `lang`."""
        return os.path.join(self.renderpath, self.lang)

    def _text_dir(self):
        """Return whether text direction is left-to-right or right-to-left for current `lang`."""
        textdir = 'ltr'
        if self.lang in settings.LANGUAGES_BIDI:
            textdir = 'rtl'
        return textdir

    def _set_context(self):
        """Set dict to add to Jinja2 context to set locale and text direction."""
        self.context = {
            'LANG': self.lang,
            'DIR': self._text_dir(),
            'NOW': datetime.datetime.now(datetime.UTC).replace(microsecond=0)
        }

    def _setup_env(self):
        """Setup the Jinja2 environment, loader, extensions, and filters."""
        load = FileSystemLoader(self.searchpath)
        self._env = Environment(loader=load, extensions=extensions)
        self._env.filters["markdown"] = helper.safe_markdown
        self._env.filters["f"] = helper.f
        self._env.filters["l10n_format_date"] = helper.l10n_format_date

    def _concat_js(self):
        """Concatenate `js_bundles` and write to current `jsout`."""
        for bundle_name, files in self.js_bundles.items():
            bundle_path = self.jsout + '/' + bundle_name + '.js'

            js_string = '\n'.join(read_file(settings.ASSETS + '/' + file) for file in files)
            with open(bundle_path, 'w') as f:
                f.write(js_string)

    def _switch_lang(self, lang):
        """Switch current `lang` for build and update gettext translations accordingly."""
        self.lang = lang
        self._set_context()
        self._env.globals.update(self.context)
        translator = translate.gettext_object(lang)
        self._env.install_gettext_translations(translator)
        self._env.globals.update(translations=translator.get_translations(), l10n_css=translator.l10n_css)

    def _write_favicon_htaccess(self):
        """Write an .htaccess to `self.renderpath` that points to the favicon."""
        htpath = os.path.join(self.renderpath, '.htaccess')
        mode = 'w'
        if os.path.isfile(htpath):
            mode = 'a'
        with open(htpath, mode) as f:
            f.write('RewriteEngine On\nRewriteRule ^favicon.ico$ {path}\n'.format(path=settings.FAVICON_PATH))

    def _copy_apple_pay_domain_verification(self):
        """Copies over FRU's merchantid to `self.renderpath/.well-known` for Apple Pay domain verification purposes"""
        if not settings.USE_APPLE_PAY_DOMAIN_VERIFICATION:
            return

        folder_path = "{0}/.well-known".format(self.renderpath)
        file_name = "apple-developer-merchantid-domain-association"

        mkdir(folder_path)
        shutil.copy("{0}/misc/{1}".format(settings.ASSETS, file_name), "{0}/{1}".format(folder_path, file_name))

    def is_css_bundle(self, path):
        """Check if a path refers to a css file that is in the current `css_bundles` or not."""
        changed_file = ntpath.basename(path).split('.')[0]
        bundle = ''
        for bundle_name, files in self.css_bundles.items():
            for file in files:
                if changed_file in file:
                    bundle = bundle_name
        return bundle

    def partial_asset_build(self, path, timemsg=''):
        """Check if `path` refers to a changed css or js and only build that asset if possible, for improved performance."""
        if 'less' in path:
            bundle = self.is_css_bundle(path)
            if bundle:
                env = webassets.Environment(load_path=[settings.ASSETS],
                    directory=self.cssout, url=settings.MEDIA_URL, cache=False, manifest=False)
                css_files = self.css_bundles[bundle]
                reg = webassets.Bundle(*css_files, filters='less', output=bundle + '.css')
                env.register(bundle, reg)
                env[bundle].urls()
                print("{0}: CSS bundle rebuilt: {1}.".format(timemsg, bundle))
            else:
                print("{0}: All Assets rebuilt.".format(timemsg))
                self.build_assets()
        elif 'js' in path:
            if self.js_bundles:
                self._concat_js()
                print("{0}: JS bundles rebuilt.".format(timemsg))
            else:
                print("{0}: All Assets rebuilt.".format(timemsg))
                self.build_assets()
        # If we can't figure out what to build partially, give up and do a full build.
        else:
            print("{0}: All Assets rebuilt.".format(timemsg))
            self.build_assets()

    def build_notes(self):
        """Build the release notes and system requirements portions of the site in en-US only."""
        if self.lang != 'en-US':
            self._switch_lang('en-US')

        notelist = releasenotes.notes
        note_template = self._env.get_template('includes/_enonly/release-notes.html')
        self._env.globals.update(feedback=releasenotes.settings["feedback"], bugzilla=releasenotes.settings["bugzilla"])
        feed_items = []
        for k, n in notelist.items():
            is_beta = 'beta' in k
            is_115_esr = k.startswith('115.') and k.endswith('esr')

            if is_beta:
                self._env.globals.update(channel='Beta', channel_name='Beta')
            else:
                self._env.globals.update(channel='Release', channel_name='Release')
            n["release"]["release_date"] = n["release"].get("release_date", helper.thunderbird_desktop.get_release_date(k))

            # If there's no data at all, we can't parse an empty string for a date.
            if n["release"]["release_date"]:
                n["release"]["release_date"] = parse(str(n["release"]["release_date"]))
            self._env.globals.update(**n)

            # Render release notes page
            target = os.path.join(self.outpath, 'thunderbird', str(k), 'releasenotes')
            mkdir(target)
            logger.info("Rendering {0}/index.html...".format(target))
            self._env.globals['canonical_path'] = '/' + str(pathlib.Path(*pathlib.Path(target).parts[3:]))
            note_template.stream().dump(os.path.join(target, 'index.html'))

            # Render system requirements page
            target = os.path.join(self.outpath, 'thunderbird', str(k), 'system-requirements')
            mkdir(target)
            sysreq_template = self._env.get_template('includes/_enonly/system_requirements.html')
            self._env.globals['canonical_path'] = '/' + str(pathlib.Path(*pathlib.Path(target).parts[3:]))
            logger.info("Rendering {0}/index.html...".format(target))
            sysreq_template.stream().dump(os.path.join(target, 'index.html'))
            
            # 115 swapped to esr midway through. So add an 115 alias for 115esr builds
            if is_115_esr:
                for path in ['releasenotes', 'system-requirements']:
                    k_noesr = k.replace('esr', '')
                    source = os.path.join(self.outpath, 'thunderbird', str(k_noesr), path)
                    mkdir(source)
                    write_htaccess(source, urllib.parse.urljoin(settings.CANONICAL_URL, f'thunderbird/{str(k)}/{path}'))

            # Add entry to our feed items, optionally filter out beta notes
            if not is_beta or (is_beta and settings.SHOW_BETA_NOTES_IN_RSS_FEED):
                feed_items.append((k, n))

        # Remove this so other rendering functions don't accidentally reuse it.
        del self._env.globals['canonical_path']
        # Build htaccess files for sysreq and release notes redirects.
        sysreq_path = os.path.join(self.renderpath, 'system-requirements')
        notes_path = os.path.join(self.renderpath, 'notes')
        beta_notes_path = os.path.join(self.renderpath, 'notes', 'beta')
        write_htaccess(sysreq_path, settings.CANONICAL_URL + helper.thunderbird_url('system-requirements'))
        write_htaccess(notes_path, settings.CANONICAL_URL + helper.thunderbird_url('releasenotes'))
        write_htaccess(beta_notes_path, settings.CANONICAL_URL + helper.thunderbird_url('releasenotes', channel="beta"))

        self.build_notes_feed(feed_items)

    def build_notes_feed(self, feed_items):
        """ Builds the release notes atom.xml file. Like build_notes, this is en-US only. """
        if len(feed_items) == 0:
            return

        # RSS follows the notes, being only en-us
        if self.lang != 'en-US':
            self._switch_lang('en-US')

        def sort_version_by_release_date(i):
            """ Sort using the note's release date. """
            return i[1]['release'].get('release_date')

        # Sort notes by release date
        feed_items.sort(key=sort_version_by_release_date, reverse=True)

        releases = list(filter(lambda i: 'beta' not in i[0], feed_items))
        betas = list(filter(lambda i: 'beta' in i[0], feed_items))

        # We only want to display the last 10 releases, and the last 5 betas
        feed_items_mixed = releases[:10] + betas[:5]
        # Sort again by release date
        feed_items_mixed.sort(key=sort_version_by_release_date, reverse=True)

        feed_template = self._env.get_template('includes/atom-feed.html')
        content_template = self._env.get_template('includes/release-notes-feed.html')

        self._env.globals.update(feedback=releasenotes.settings["feedback"], bugzilla=releasenotes.settings["bugzilla"])

        fake_context = {'LANG': 'en-US'}
        feed_context = {
            'feed_url': os.path.join(settings.CANONICAL_URL, 'thunderbird', 'releases', 'atom.xml'),
            'feed_icon': f'{settings.CANONICAL_URL}{settings.MEDIA_URL}/img/thunderbird/favicon-196.png',
            'feed_logo': f'{settings.CANONICAL_URL}{settings.MEDIA_URL}/img/thunderbird/thunderbird-256.png',
            'feed_index': f'{settings.CANONICAL_URL}/{helper.url(fake_context, "thunderbird.releases.index")}'
        }

        entries = []
        for item in feed_items_mixed:
            version = item[0]
            note = item[1]

            release_notes = note.get('release')

            if release_notes is None:
                print("Couldn't find release key for version {}, this shouldn't happen.".format(version))
                continue

            title = "Thunderbird {}".format(version)

            self._env.globals.update(channel='Release', channel_name='Release')

            if settings.SHOW_BETA_NOTES_IN_RSS_FEED and 'beta' in version:
                # Remove redundant beta from title
                title = "Thunderbird Beta {}".format(version.replace('beta', ''))
                self._env.globals.update(channel='Beta', channel_name='Beta')

            link = "{}/{}/thunderbird/{}/releasenotes/".format(settings.CANONICAL_URL, self.lang, version)

            # Mix in our notes for the template
            self._env.globals.update(**note)

            # Pull in and minify our template
            content = content_template.render({'version_number': version, 'link': link})

            # Note: Published Date is DateTime, but Updated Date is a string!
            published_date = release_notes.get('release_date')
            updated_date = thunderbird_desktop.get_release_date(version)

            if published_date:
                # Force it to UTC, pubDate checks for tzinfo
                published_date = parse("{}Z".format(published_date.isoformat()))
            if updated_date:
                # Force it to UTC, updated checks for tzinfo
                updated_date = parse("{}T00:00:00Z".format(updated_date))
            else:
                # In case we don't have a date, use the published date
                updated_date = published_date

            entries.append({
                'id': link,
                'title': title,
                'url': link,
                'author': 'Thunderbird',
                'summary': '',
                'content': content,
                'published': published_date.isoformat(),
                'updated': updated_date.isoformat(),
            })

        # Render our atom template and write it to atom.xml
        feed_xml = feed_template.render({'entries': entries, **feed_context})
        with open(os.path.join(self.outpath, 'thunderbird', 'releases', 'atom.xml'), "w") as fh:
            fh.write(feed_xml)

    def build_assets(self):
        """Build assets, that is, bundle and compile the LESS and JS files in `settings.ASSETS`."""
        shutil.rmtree(self.renderpath + '/media', ignore_errors=True)
        shutil.copytree(self.staticpath, self.renderpath + '/media')
        env = webassets.Environment(load_path=[settings.ASSETS], directory=self.cssout, url=settings.MEDIA_URL, cache=False, manifest=False)
        for k, v in self.css_bundles.items():
            reg = webassets.Bundle(*v, filters='less', output=k + '.css')
            env.register(k, reg)
            env[k].urls()
        if self.js_bundles:
            self._concat_js()
        self._write_favicon_htaccess()
        self._copy_apple_pay_domain_verification()

    def render(self):
        """
        Iterate through the templates loaded into Jinja2 and build them, including any needed directories.
        If '_' or 'includes' are in front of a template or folder they will be skipped by this method.
        Non-html files will also be skipped.
        """
        for template in self._env.list_templates():
            filename = os.path.basename(template)
            # Ignore non-html files, or any path that starts with `_` or `includes`.
            if not filename.endswith('.html') or template.startswith("_") or template.startswith("includes"):
                continue

            filepath = os.path.join(self.outpath, template)
            # Make sure the output directory exists.
            filedir = os.path.dirname(filepath)
            if not os.path.exists(filedir):
                os.makedirs(filedir)

            canonical_path = ''
            # Figure out the page path and store it in Jinja globals.
            if '404' not in template:
                dir_part = os.path.dirname(template)
                canonical_path = f'/{dir_part}' if dir_part else '/'
            self._env.globals['canonical_path'] = canonical_path

            try:
                t = self._env.get_template(template)
                t.stream().dump(filepath)
            except jinja2.exceptions.TemplateSyntaxError as ex:
                logger.error(f">> Jinja Syntax Error: \"{ex.message}\"\n>> In file \"{ex.filename}\" on line {ex.lineno}.")

                # This is for dev builds, we want it to crash on production.
                if self.dev_mode:
                    continue

                raise ex
            except jinja2.exceptions.TemplateError as ex:
                logger.error(f">> Jinja Template Error: \"{ex.message}\" in template: \"{template}\".")

                if self.dev_mode:
                    continue

                raise ex
            # Remove this to prevent other template renders from accidentally using the last value.
            del self._env.globals['canonical_path']

    def build_startpage(self):
        """Build the start page for all `languages`."""
        delete_contents(self.renderpath)
        for lang in self.languages:
            logger.info("Building pages for {lang}...".format(lang=lang))
            self._switch_lang(lang)
            self.render()
        self.build_assets()

    def build_updates(self):
        """Build the updates page for all `languages`."""
        self._env.globals.update(self.data)
        delete_contents(self.renderpath)
        for lang in self.languages:
            logger.info("Building pages for {lang}...".format(lang=lang))
            self._switch_lang(lang)
            self.render()
            write_site_htaccess(self.renderpath, self.lang, settings.UPDATES_REDIRECTS, redirect_request=True)
        self.build_assets()

    def build_website(self, assets=True, notes=True):
        """
        Build the website for all `languages.`
        `assets` and `notes` set False allow skipping of build_assets() and build_notes()
        """
        if assets and notes:
            delete_contents(self.renderpath)
        self._env.globals.update(self.data)
        for lang in self.languages:
            logger.info("Building pages for {lang}...".format(lang=lang))
            self._switch_lang(lang)
            self.render()
            write_404_htaccess(self.outpath, self.lang)

            write_site_htaccess(self.renderpath, self.lang, settings.WEBSITE_REDIRECTS)

            if lang == 'en-US':
                # 404 page for root accesses outside lang dirs.
                write_404_htaccess(self.renderpath, self.lang)
                if notes:
                    self.build_notes()
        if assets:
            logger.info("Building assets...")
            self.build_assets()


class UpdateHandler(FileSystemEventHandler):
    """
    Handler for file system events watched by the observer to update the current website build for the --watch command.

    Parameters:
        `builder_instance` (object): An instance of the Site class for building the website.
    """
    def __init__(self, builder_instance):
        self.builder = builder_instance
        self.updatetime = datetime.datetime.fromtimestamp(0)

    def updatesite(self, event):
        """Build the startpage or the website, ignoring assets or notes based on the `event`."""
        if self.builder.searchpath == settings.START_PATH:
            self.builder.build_startpage()
        elif self.builder.searchpath == settings.UPDATES_PATH:
            self.builder.build_updates()
        else:
            # Reduce build time by ignoring release notes when unnecessary.
            if 'includes' in event.src_path:
                self.builder.build_website(assets=False, notes=True)
            else:
                self.builder.build_website(assets=False, notes=False)

    def throttle_updates(self, timestamp, event):
        """Only update once per second, since multiple FileModified events can fire when a file is modified."""
        delta = timestamp - self.updatetime
        if delta.seconds > 0:
            timemsg = timestamp.strftime("%H:%M:%S")
            print("{0}: Starting update...".format(timemsg))
            if settings.ASSETS in event.src_path:
                self.builder.partial_asset_build(event.src_path, timemsg)
            elif settings.MEDIA_URL[1:] in event.src_path:
                self.builder.build_assets()
                print("{0}: All Assets rebuilt.".format(datetime.datetime.now().strftime("%H:%M:%S")))
            else:
                self.updatesite(event)
                print("{0}: Website rebuilt.".format(datetime.datetime.now().strftime("%H:%M:%S")))
            self.updatetime = datetime.datetime.now()

    def on_modified(self, event):
        """This method is called by the watchdog observer by default when a file or directory is modified."""
        from webassets.exceptions import BundleError
        standard_error_msg = 'An error has occurred during rendering !'

        try:
            self.throttle_updates(datetime.datetime.now(), event)
        except IOError as err:
            print(standard_error_msg)
            print("{}: {} ({})\n".format(type(err).__name__, err.strerror, err.filename))
        except BundleError as err:
            print(standard_error_msg)
            print("{}: {}\n".format(type(err).__name__, str(err)))


class RedirectingHTTPRequestHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.translate_path(self.path)
        if path.endswith("/"):
            htaccess = os.path.join(path, ".htaccess")
        else:
            htaccess = os.path.join(os.path.dirname(path), ".htaccesss")
        if os.path.exists(htaccess):
            _htaccess = open(htaccess, "r").readlines()
            for l in _htaccess:
                if l.startswith("RewriteRule"):
                    RR, regex, dest = l.split(" ", 2)
                    if regex == ".*":
                        self.send_response(302)
                        self.send_header("Location", dest)
                        self.end_headers()
                        return None
        return SimpleHTTPRequestHandler.send_head(self)


def setup_httpd(port, path):
    """Setup and start the SimpleHTTPServer for the --watch command."""
    cwd = os.getcwd()
    os.chdir(path)
    handler = RedirectingHTTPRequestHandler
    httpd = TCPServer(("", port), handler)
    multiprocessing.set_start_method("fork")
    process = multiprocessing.Process(target=httpd.serve_forever)
    process.daemon = True
    process.start()
    os.chdir(cwd)
    print(f"HTTP Server running on: http://localhost:{port}")
    return process


def setup_observer(builder_instance, port):
    """Setup and start the watchdog observer for the --watch command."""
    handler = UpdateHandler(builder_instance)
    observer = Observer()
    observer.schedule(handler, path=builder_instance.searchpath, recursive=True)
    observer.schedule(handler, path=settings.ASSETS, recursive=True)
    observer.schedule(handler, path=settings.MEDIA_URL.strip('/'), recursive=True)
    observer.daemon = True
    observer.start()
    print("Updating website when templates, CSS, or JS are modified. Press Ctrl-C to end.")
    server = setup_httpd(port, builder_instance.renderpath)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down watcher and server...")
        server.terminate()
        server.join()
        observer.stop()
        observer.join()
