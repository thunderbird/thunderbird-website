import argparse
import builder
import feedparser
import helper
import settings

from datetime import date

parser = argparse.ArgumentParser()
parser.add_argument('--enus', help='Only build the en-US language.', action='store_true')
parser.add_argument('--debug', help='Log output with more detailed build information.', action='store_true')
parser.add_argument('--startpage', help='Build the start page instead of the main thunderbird.net website.',
                    action='store_true')
parser.add_argument('--watch', help='Rebuild when template and asset dirs are changed, and run a server on localhost.',
                    action='store_true')
parser.add_argument('--watch-only', help='Rebuild when template and asset dirs are changed, does not run a server on localhost.',
                    action='store_true')
parser.add_argument('--docker', help='Adjusts the render directory.', action='store_true')
parser.add_argument('--port', const=8000, default=8000, type=int,
                    help='Port for the server that runs with --watch.', nargs='?')
args = parser.parse_args()


if args.enus:
    langmsg = 'in en-US only.'
    languages = ['en-US']
else:
    langmsg = 'in all languages.'
    languages = settings.PROD_LANGUAGES

if not args.docker:
    site_render_path = settings.START_RENDERPATH
    website_render_path = settings.WEBSITE_RENDERPATH
else:
    site_render_path = "/srv/www/{}".format(settings.START_RENDERPATH)
    website_render_path = "/srv/www/{}".format(settings.WEBSITE_RENDERPATH)

if args.startpage:
    print('Rendering start page ' + langmsg)
    site = builder.Site(languages, settings.START_PATH, site_render_path, settings.START_CSS, debug=args.debug)
    site.build_startpage()
else:
    print('Rendering www.thunderbird.net ' + langmsg)
    # Prepare data and build main website.
    version = helper.thunderbird_desktop.latest_version('release')
    beta_version = helper.thunderbird_desktop.latest_version('beta')
    caldata = helper.load_calendar_json('media/caldata/calendars.json')
    context = {'current_year': date.today().year,
               'platform': 'desktop',
               'query': '',
               'platforms': helper.thunderbird_desktop.platforms('release'),
               'full_builds_version': version.split('.', 1)[0],
               'full_builds': helper.thunderbird_desktop.get_filtered_full_builds('release', version),
               'full_builds_beta': helper.thunderbird_desktop.get_filtered_full_builds('beta', beta_version),
               'channel_label': 'Thunderbird',
               'releases': helper.thunderbird_desktop.list_releases(),
               'calendars': caldata['calendars'],
               'letters': caldata['letters'],
               'CALDATA_URL': settings.CALDATA_URL,
               'latest_thunderbird_version': version,
               'latest_thunderbird_beta_version': beta_version,
               'blog_data': feedparser.parse(settings.BLOG_FEED_URL)
              }

    site = builder.Site(languages, settings.WEBSITE_PATH, website_render_path,
        settings.WEBSITE_CSS, js_bundles=settings.WEBSITE_JS, data=context, debug=args.debug)
    site.build_website()

if args.watch:
    builder.setup_local_watch(site, args.port)
elif args.watch_only:
    builder.setup_docker_watch(site)