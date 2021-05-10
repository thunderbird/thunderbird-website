import datetime
import errno
import helper
import logging
import multiprocessing
import ntpath
import os
import shutil
import settings
import sys
import time
import translate
import webassets

if sys.version_info[0] == 3:
    import socketserver
    import http.server
else:
    import SocketServer
    import SimpleHTTPServer

from dateutil.parser import parse
from jinja2 import Environment, FileSystemLoader
from thunderbird_notes import releasenotes
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

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


def write_404_htaccess(path, lang):
    """Write a .htaccess to `path` that points to 404.html for locale `lang`."""
    with open(os.path.join(path, '.htaccess'), 'w') as f:
        f.write('ErrorDocument 404 /{lang}/404.html\n'.format(lang=lang))


def write_htaccess(path, url):
    """Write a .htaccess to `path` that rewrites everything to `url`."""
    mkdir(path)
    with open(os.path.join(path, '.htaccess'), 'w') as f:
        f.write('RewriteEngine On\nRewriteRule .* {url}\n'.format(url=url))


def delete_contents(dirpath):
    """Delete all contents of `dirpath` except the root dir. Workaround for shutil.rmtree."""
    if os.path.exists(dirpath):
        for filename in os.listdir(dirpath):
            filepath = os.path.join(dirpath, filename)
            try:
                shutil.rmtree(filepath)
            except OSError:
                os.remove(filepath)


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
    Attributes:
        `lang`: Current language to build the site in, an element of `languages`.
    """
    def __init__(self, languages, searchpath, renderpath, css_bundles, staticdir='_media', js_bundles={}, data={}, debug=False):
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
            'DIR': self._text_dir()
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
        note_template = self._env.get_template('_includes/release-notes.html')
        self._env.globals.update(feedback=releasenotes.settings["feedback"], bugzilla=releasenotes.settings["bugzilla"])
        for k, n in notelist.items():
            if 'beta' in k:
                self._env.globals.update(channel='Beta', channel_name='Beta')
            else:
                self._env.globals.update(channel='Release', channel_name='Release')
            n["release"]["release_date"] = n["release"].get("release_date", helper.thunderbird_desktop.get_release_date(k))

            # If there's no data at all, we can't parse an empty string for a date.
            if n["release"]["release_date"]:
                n["release"]["release_date"] = parse(str(n["release"]["release_date"]))
            self._env.globals.update(**n)
            target = os.path.join(self.outpath, 'thunderbird', str(k), 'releasenotes')
            mkdir(target)
            logger.info("Rendering {0}/index.html...".format(target))
            note_template.stream().dump(os.path.join(target, 'index.html'))

            target = os.path.join(self.outpath, 'thunderbird', str(k), 'system-requirements')
            mkdir(target)
            sysreq_template = self._env.get_template('_includes/system_requirements.html')
            logger.info("Rendering {0}/index.html...".format(target))
            sysreq_template.stream().dump(os.path.join(target, 'index.html'))

        # Build htaccess files for sysreq and release notes redirects.
        sysreq_path = os.path.join(self.renderpath, 'system-requirements')
        notes_path = os.path.join(self.renderpath, 'notes')
        write_htaccess(sysreq_path, settings.CANONICAL_URL + helper.thunderbird_url('system-requirements'))
        write_htaccess(notes_path, settings.CANONICAL_URL + helper.thunderbird_url('releasenotes'))

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

    def render(self):
        """
        Iterate through the templates loaded into Jinja2 and build them, including any needed directories.
        '_' in front of a template or folder will force those to be skipped by this method.
        """
        for template in self._env.list_templates():
            if not template.startswith("_"):
                filepath = os.path.join(self.outpath, template)
                # Make sure the output directory exists.
                filedir = os.path.dirname(filepath)
                if not os.path.exists(filedir):
                    os.makedirs(filedir)
                t = self._env.get_template(template)
                t.stream().dump(filepath)

    def build_startpage(self):
        """Build the start page for all `languages`."""
        delete_contents(self.renderpath)
        for lang in self.languages:
            logger.info("Building pages for {lang}...".format(lang=lang))
            self._switch_lang(lang)
            self.render()
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
        else:
            # Reduce build time by ignoring release notes when unnecessary.
            if '_includes' in event.src_path:
                self.builder.build_website(assets=False, notes=True)
            else:
                self.builder.build_website(assets=False, notes=False)

    def throttle_updates(self, timestamp, event):
        """Only update once per second, since multiple FileModified events can fire when a file is modified."""
        delta = timestamp - self.updatetime
        if delta.seconds > 0:
            timemsg = timestamp.strftime("%H:%M:%S")
            if settings.ASSETS in event.src_path:
                self.builder.partial_asset_build(event.src_path, timemsg)
            else:
                self.updatesite(event)
                print("{0}: Website rebuilt.".format(timemsg))
            self.updatetime = datetime.datetime.now()

    def on_modified(self, event):
        """This method is called by the watchdog observer by default when a file or directory is modified."""
        self.throttle_updates(datetime.datetime.now(), event)


def setup_httpd(port, path):
    """Setup and start the SimpleHTTPServer for the --watch command."""
    cwd = os.getcwd()
    os.chdir(path)
    if sys.version_info[0] == 3:
        handler = http.server.SimpleHTTPRequestHandler
        httpd = socketserver.TCPServer(("", port), handler)
    else:
        handler = SimpleHTTPServer.SimpleHTTPRequestHandler
        httpd = SocketServer.TCPServer(("", port), handler)
    process = multiprocessing.Process(target=httpd.serve_forever)
    process.daemon = True
    process.start()
    os.chdir(cwd)
    print("HTTP Server running on localhost port {0}.".format(port))
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
