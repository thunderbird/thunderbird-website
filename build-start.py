from staticjinja import make_site
import helper
import os
import shutil
import settings
import translate
import webassets

extensions = ['jinja2.ext.i18n']
PROD_LANGUAGES = ('ach', 'af', 'an', 'ar', 'as', 'ast', 'az', 'be', 'bg',
                  'bn-BD', 'bn-IN', 'br', 'bs', 'ca', 'cak', 'cs',
                  'cy', 'da', 'de', 'dsb', 'el', 'en-GB', 'en-US',
                  'en-ZA', 'eo', 'es-AR', 'es-CL', 'es-ES', 'es-MX', 'et',
                  'eu', 'fa', 'ff', 'fi', 'fr', 'fy-NL', 'ga-IE', 'gd',
                  'gl', 'gn', 'gu-IN', 'he', 'hi-IN', 'hr', 'hsb',
                  'hu', 'hy-AM', 'id', 'is', 'it', 'ja', 'ja-JP-mac',
                  'ka', 'kab', 'kk', 'km', 'kn', 'ko', 'lij', 'lt', 'ltg', 'lv',
                  'mai', 'mk', 'ml', 'mr', 'ms', 'my', 'nb-NO', 'ne-NP', 'nl',
                  'nn-NO', 'oc', 'or', 'pa-IN', 'pl', 'pt-BR', 'pt-PT',
                  'rm', 'ro', 'ru', 'si', 'sk', 'sl', 'son', 'sq',
                  'sr', 'sv-SE', 'ta', 'te', 'th', 'tr', 'uk', 'ur',
                  'uz', 'vi', 'xh', 'zh-CN', 'zh-TW', 'zu')

LANGUAGES_BIDI = ('he', 'ar', 'fa', 'ur')

# path to search for templates
searchpath = 'start-page'
# static file/media path
staticpath = 'start-page/_media'
# path to render the finished site to
renderpath = 'site'
# path to compile CSS to
cssout = renderpath+'/media/css'

def build_assets():
    env = webassets.Environment(load_path=[settings.ASSETS], directory=cssout, url=settings.MEDIA_URL, cache=False, manifest=False)
    start_css = webassets.Bundle('less/sandstone/fonts.less', 'less/thunderbird/start.less',  filters='less', output='start-style.css')
    env.register('start-style', start_css)
    env['start-style'].urls()

def text_dir(lang):
    textdir = 'ltr'
    if lang in LANGUAGES_BIDI:
        textdir = 'rtl'
    return textdir

def build_site(lang):
    context = {'LANG': lang,
                 'DIR': text_dir(lang) }

    outpath = os.path.join(renderpath, lang)
    if not os.path.exists(outpath):
        os.makedirs(outpath)
    site = make_site(outpath=outpath, searchpath=searchpath, extensions=extensions, env_globals=context)

    translator = translate.Translation(lang, ['thunderbird/start/release', 'main'])
    gettext_translator = translate.gettext_object(lang)
    site._env.install_gettext_translations(gettext_translator)

    # Add l10n_css function to context
    site._env.globals.update(l10n_css=translator.l10n_css, **helper.contextfunctions)
    site.render(use_reloader=False)
    shutil.rmtree(renderpath+'/media', ignore_errors=True)
    shutil.copytree(staticpath, renderpath+'/media')


build_site('en-US')

for lang in PROD_LANGUAGES:
    build_site(lang)

build_assets()
