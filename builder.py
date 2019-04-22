import helper
import os
import shutil
import settings
import translate
import webassets

from jinja2 import Environment, FileSystemLoader

extensions = ['jinja2.ext.i18n']

class Site(object):
    def __init__(self, languages, searchpath, renderpath, staticpath, css_bundles):
        self.languages = languages
        self.lang = languages[0]
        self.context = {}
        self.searchpath = searchpath
        self.renderpath = renderpath
        self.staticpath = staticpath
        self.cssout = renderpath+'/media/css'
        self.css_bundles = css_bundles

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

    def build_assets(self):
        env = webassets.Environment(load_path=[settings.ASSETS], directory=self.cssout, url=settings.MEDIA_URL, cache=False, manifest=False)
        for k, v in self.css_bundles.iteritems():
            reg = webassets.Bundle(*v, filters='less', output=k+'.css')
            env.register(k, reg)
            env[k].urls()
        shutil.rmtree(self.renderpath+'/media', ignore_errors=True)
        shutil.copytree(self.staticpath, self.renderpath+'/media')

    def render(self):
        outpath = os.path.join(self.renderpath, self.lang)
        # Make sure the output directory exists.
        if not os.path.exists(outpath):
            os.makedirs(outpath)
        for template in self._env.list_templates():
            if not template.startswith("_"):
                filepath = os.path.join(outpath, template)
                t = self._env.get_template(template)
                t.stream().dump(filepath)

    def build_site(self):
        self._setup_env()
        for lang in self.languages:
            self.lang = lang
            self._set_context()
            self._env.globals.update(self.context)
            translator = translate.gettext_object(lang)
            self._env.install_gettext_translations(translator)
            self._env.globals.update(l10n_css=translator.l10n_css, **helper.contextfunctions)
            self.render()
        self.build_assets()
