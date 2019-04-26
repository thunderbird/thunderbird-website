import helper
import os
import shutil
import settings
import translate
import webassets

from dateutil.parser import parse
from jinja2 import Environment, FileSystemLoader
from thunderbird_notes import releasenotes

extensions = ['jinja2.ext.i18n']

def read_file(file):
    with open(file, 'r') as f:
        return f.read()


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


def delete_contents(dirpath):
    if os.path.exists(dirpath):
        for filename in os.listdir(dirpath):
            filepath = os.path.join(dirpath, filename)
            try:
                shutil.rmtree(filepath)
            except OSError:
                os.remove(filepath)


class Site(object):
    def __init__(self, languages, searchpath, renderpath, staticpath, css_bundles, js_bundles = {}, data = {}):
        self.languages = languages
        self.lang = languages[0]
        self.context = {}
        self.searchpath = searchpath
        self.renderpath = renderpath
        self.staticpath = staticpath
        self.cssout = renderpath+'/media/css'
        self.css_bundles = css_bundles
        self.js_bundles = js_bundles
        self.jsout = renderpath+'/media/js'
        self.data = data
        self._setup_env()
        self._env.globals.update(settings=settings, **helper.contextfunctions)

    @property
    def outpath(self):
        return os.path.join(self.renderpath, self.lang)

    def _text_dir(self):
        textdir = 'ltr'
        if self.lang in settings.LANGUAGES_BIDI:
            textdir = 'rtl'
        return textdir

    def _set_context(self):
        self.context = {'LANG': self.lang,
                        'DIR': self._text_dir() }

    def _setup_env(self):
        load = FileSystemLoader(self.searchpath)
        self._env = Environment(loader=load, extensions=extensions)
        self._env.filters["markdown"] = helper.safe_markdown
        self._env.filters["f"] = helper.f
        self._env.filters["l10n_format_date"] = helper.l10n_format_date

    def _concat_js(self):
        for bundle_name, files in self.js_bundles.iteritems():
            bundle_path = self.jsout+'/'+bundle_name+'.js'

            js_string = '\n'.join(read_file(settings.ASSETS + '/' + file) for file in files)
            with open(bundle_path, 'w') as f:
                f.write(js_string)

    def _switch_lang(self, lang):
        self.lang = lang
        self._set_context()
        self._env.globals.update(self.context)
        translator = translate.gettext_object(lang)
        self._env.install_gettext_translations(translator)
        self._env.globals.update(translations=translator.get_translations(), l10n_css=translator.l10n_css)

    def build_notes(self):
        # Render release notes and system requirements for en-US only.
        if self.lang != 'en-US':
            self._switch_lang('en-US')

        notelist = releasenotes.notes
        note_template = self._env.get_template('_includes/release-notes.html')
        self._env.globals.update(feedback=releasenotes.settings["feedback"], bugzilla=releasenotes.settings["bugzilla"])
        for k, n in notelist.iteritems():
            if 'beta' in k:
                self._env.globals.update(channel='Beta', channel_name='Beta')
            else:
                self._env.globals.update(channel='Release', channel_name='Release')
            n["release"]["release_date"] = n["release"].get("release_date", helper.thunderbird_desktop.get_release_date(k))

            # If there's no data at all, we can't parse an empty string for a date.
            if n["release"]["release_date"]:
                n["release"]["release_date"] = parse(str(n["release"]["release_date"]))
            self._env.globals.update(**n)
            target = os.path.join(self.outpath,'thunderbird', str(k), 'releasenotes')
            mkdir(target)
            # print "Rendering {0}/index.html...".format(target)
            note_template.stream().dump(os.path.join(target, 'index.html'))

            target = os.path.join(self.outpath,'thunderbird', str(k), 'system-requirements')
            mkdir(target)
            sysreq_template = self._env.get_template('_includes/system_requirements.html')
            # print "Rendering {0}/index.html...".format(target)
            sysreq_template.stream().dump(os.path.join(target, 'index.html'))

        # Build htaccess files for sysreq and release notes redirects.
        sysreq_path = os.path.join(self.renderpath, 'system-requirements')
        notes_path = os.path.join(self.renderpath, 'notes')
        write_htaccess(sysreq_path, settings.CANONICAL_URL + helper.thunderbird_url('system-requirements'))
        write_htaccess(notes_path, settings.CANONICAL_URL + helper.thunderbird_url('releasenotes'))

    def build_assets(self):
        shutil.rmtree(self.renderpath+'/media', ignore_errors=True)
        shutil.copytree(self.staticpath, self.renderpath+'/media')
        env = webassets.Environment(load_path=[settings.ASSETS], directory=self.cssout, url=settings.MEDIA_URL, cache=False, manifest=False)
        for k, v in self.css_bundles.iteritems():
            reg = webassets.Bundle(*v, filters='less', output=k+'.css')
            env.register(k, reg)
            env[k].urls()
        if self.js_bundles:
            self._concat_js()

    def render(self):
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
        delete_contents(self.renderpath)
        for lang in self.languages:
            self._switch_lang(lang)
            self.render()

    def build_website(self):
        delete_contents(self.renderpath)
        self._env.globals.update(self.data)
        for lang in self.languages:
            # print "Building pages for {lang}...".format(lang=lang)
            self._switch_lang(lang)
            self.render()
            write_404_htaccess(self.outpath, self.lang)
            if lang == 'en-US':
                # 404 page for root accesses outside lang dirs.
                write_404_htaccess(self.renderpath, self.lang)
                self.build_notes()
        # print "Building assets..."
        self.build_assets()
