import builder
import shutil
import settings
import webassets


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


site = builder.Site(settings.PROD_LANGUAGES, searchpath, renderpath)
site.build_site()
build_assets()
