from staticjinja import make_site
import jinja2
import os
import shutil
import settings
import translate

extensions = ['jinja2.ext.i18n']

# path to search for templates
searchpath = 'website'
# static file/media path
staticpath = 'website/_media'
# path to render the finished site to
renderpath = 'thunderbird.net'

def text_dir(lang):
    textdir = 'ltr'
    if lang in settings.LANGUAGES_BIDI:
        textdir = 'rtl'
    return textdir

def static(path):
    return '/media/' + path

def url(key):
    return ''

@jinja2.contextfunction
def high_res_img(ctx, url, optional_attributes=None):
    return static(url)

@jinja2.contextfunction
def platform_img(ctx, url, optional_attributes=None):
    return static(url)

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

    translator = translate.Translation(lang, ['thunderbird/start/release', 'main'])
    site._env.install_gettext_translations(translator)

    def l10n_has_tag(tag):
        return tag in translator.lang_file_tag_set('thunderbird/start/release', lang)

    # Add l10n_css function to context
    site._env.globals.update(l10n_css=translator.l10n_css, l10n_has_tag=l10n_has_tag,
                           static=static, url=url, high_res_img=high_res_img, platform_img=platform_img,
                           download_thunderbird=download_thunderbird, settings=settings)
    site.render(use_reloader=False)
    shutil.rmtree(renderpath+'/media', ignore_errors=True)
    shutil.copytree(staticpath, renderpath+'/media')

build_site('en-US')

#for lang in settings.PROD_LANGUAGES:
#      build_site(lang)
