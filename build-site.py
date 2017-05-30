from staticjinja import make_site

import helper
import jinja2
import os
import shutil
import settings
import translate
import webassets

extensions = ['jinja2.ext.i18n']

# path to search for templates
searchpath = 'website'
# static file/media path
staticpath = 'website/_media'
# path to render the finished site to
renderpath = 'thunderbird.net'
# path to compile CSS to
cssout = renderpath+'/media/css'

def build_assets():
    env = webassets.Environment(load_path=[settings.ASSETS], directory=cssout, url=settings.MEDIA_URL, cache=False, manifest=False)
    sandstone_css = webassets.Bundle('less/sandstone/sandstone-resp.less', 'less/base/global-nav.less', filters='less', output='responsive-bundle.css')
    tb_landing_css = webassets.Bundle('less/thunderbird/landing.less', 'less/base/menu-resp.less', filters='less', output='thunderbird-landing.css')
    tb_features_css = webassets.Bundle('less/thunderbird/features.less', 'less/base/menu-resp.less', filters='less', output='thunderbird-features.css')
    env.register('responsive-bundle', sandstone_css)
    env.register('thunderbird-landing', tb_landing_css)
    env.register('thunderbird-features', tb_features_css)
    env['responsive-bundle'].urls()
    env['thunderbird-landing'].urls()
    env['thunderbird-features'].urls()


def text_dir(lang):
    textdir = 'ltr'
    if lang in settings.LANGUAGES_BIDI:
        textdir = 'rtl'
    return textdir


@jinja2.contextfunction
def download_thunderbird(ctx, channel='release', dom_id=None,
                         locale=None, force_direct=False,
                         alt_copy=None, button_color='button-green'):
      return ''


def build_site(lang):
    context = {'LANG': lang,
               'DIR': text_dir(lang) }

    outpath = os.path.join(renderpath, lang)
    if not os.path.exists(outpath):
        os.makedirs(outpath)
    site = make_site(outpath=outpath, searchpath=searchpath, extensions=extensions, env_globals=context)

    translator = translate.Translation(lang, ['thunderbird/index', 'main'])
    site._env.install_gettext_translations(translator)

    def l10n_has_tag(tag):
        return tag in translator.lang_file_tag_set('thunderbird/index', lang)

    # Add l10n_css function to context
    site._env.globals.update(l10n_css=translator.l10n_css, l10n_has_tag=l10n_has_tag, settings=settings, **helper.contextfunctions)
    site.render(use_reloader=False)


build_site(settings.LANGUAGE_CODE)

for lang in settings.PROD_LANGUAGES:
      build_site(lang)

shutil.rmtree(renderpath+'/media', ignore_errors=True)
shutil.copytree(staticpath, renderpath+'/media')
build_assets()
