import builder
import settings


# path to search for templates
searchpath = 'start-page'
# static file/media path
staticpath = 'start-page/_media'
# path to render the finished site to
renderpath = 'site'

css_bundles = {'start-style': ['less/sandstone/fonts.less', 'less/thunderbird/start.less']}

site = builder.Site(settings.PROD_LANGUAGES, searchpath, renderpath, staticpath, css_bundles)
site.build_site()
