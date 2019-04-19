import helper
import os
import shutil
import settings
import translate
import webassets

extensions = ['jinja2.ext.i18n']

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
    shutil.rmtree(renderpath+'/media', ignore_errors=True)
    shutil.copytree(staticpath, renderpath+'/media')


def text_dir(lang):
    textdir = 'ltr'
    if lang in settings.LANGUAGES_BIDI:
        textdir = 'rtl'
    return textdir


def jinja_env(outpath, searchpath, extensions=[], env_globals=[]):
    from jinja2 import Environment, FileSystemLoader
    load = FileSystemLoader(searchpath)
    env = Environment(loader=load, extensions=extensions)
    env.globals.update(env_globals)
    return env


def render(env, outpath):
    for template in env.list_templates():
        if not template.startswith("_"):
            filepath = os.path.join(outpath, template)
            t = env.get_template(template)
            t.stream().dump(filepath)


def build_site(lang):
    context = {'LANG': lang,
                 'DIR': text_dir(lang) }

    outpath = os.path.join(renderpath, lang)
    if not os.path.exists(outpath):
        os.makedirs(outpath)
    env = jinja_env(outpath=outpath, searchpath=searchpath, extensions=extensions, env_globals=context)

    translator = translate.gettext_object(lang)
    env.install_gettext_translations(translator)
    env.globals.update(l10n_css=translator.l10n_css, **helper.contextfunctions)
    render(env, outpath)


build_site('en-US')

for lang in settings.PROD_LANGUAGES:
    build_site(lang)

build_assets()
