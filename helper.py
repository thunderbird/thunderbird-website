from __future__ import unicode_literals

import inspect
import jinja2
import json
import markdown
import re
import settings
import sys
import translate

from babel.core import Locale, UnknownLocaleError, get_locale_identifier
from babel.dates import format_date
from datetime import datetime
from os import path
from os.path import splitext
from product_details import thunderbird_desktop
from time import mktime

babel_format_locale_map = {
    'hsb': 'de',
    'dsb': 'de',
}


def load_calendar_json(json_file):
    calendars = []

    with open(json_file) as calendar_data:
        calendars = json.load(calendar_data)

    letters = set()
    for calendar in calendars:
        letters.add(calendar['country'][:1])

    data = {
        'calendars': sorted(calendars, key=lambda k: k['country']),
        'letters': sorted(letters),
    }
    return data


def static(filepath):
    return path.join(settings.MEDIA_URL, filepath)


@jinja2.contextfunction
def url(ctx, key, *args):
    target_url = settings.URL_MAPPINGS.get(key, '')
    lang = ctx['LANG']

    if 'http' in target_url:
        return target_url
    if key == 'thunderbird.sysreq':
        return "/{0}{1}{2}{3}".format('en-US', '/thunderbird/', args[0], '/system-requirements/')
    if key == 'wiki.moz':
        return "{0}{1}".format(settings.WIKI_URL, args[0])
    if key in settings.ENUS_ONLY:
        lang = 'en-US'

    return "/{0}{1}".format(lang, target_url)


def _l10n_media_exists(type, locale, url):
    """ checks if a localized media file exists for the locale """
    return path.exists(path.join(settings.MEDIA_URL.strip('/'), type, 'l10n', locale, url))


def add_string_to_image_url(url, addition):
    """Add the platform string to an image url."""
    filename, ext = splitext(url)
    return ''.join([filename, '-', addition, ext])


def convert_to_high_res(url):
    """Convert a file name to the high-resolution version."""
    return add_string_to_image_url(url, 'high-res')


@jinja2.contextfunction
def l10n_img_file_name(ctx, url):
    """Return the filename of the l10n image for use by static()"""
    url = url.lstrip('/')
    locale = ctx.get('LANG', None)
    if not locale:
        locale = settings.LANGUAGE_CODE

    # We use the same localized screenshots for all Spanishes
    if locale.startswith('es') and not _l10n_media_exists('img', locale, url):
        locale = 'es-ES'

    if locale != settings.LANGUAGE_CODE:
        if not _l10n_media_exists('img', locale, url):
            locale = settings.LANGUAGE_CODE

    return path.join('img', 'l10n', locale, url)


@jinja2.contextfunction
def l10n_img(ctx, url):
    """Output the url to a localized image.

    Uses the locale from the current request. Checks to see if the localized
    image exists, and falls back to the image for the default locale if not.

    Examples
    ========

    In Template
    -----------

        {{ l10n_img('firefoxos/screenshot.png') }}

    For en-US this would output:

        {{ static('img/l10n/en-US/firefox/screenshot.png') }}

    For fr this would output:

        {{ static('img/l10n/fr/firefox/screenshot.png') }}

    If that file did not exist it would default to the en-US version (if en-US
    was the default language for this install).

    In the Filesystem
    -----------------

    Put files in folders like the following::

        $ROOT/media/img/l10n/en-US/firefoxos/screenshot.png
        $ROOT/media/img/l10n/fr/firefoxos/screenshot.png

    """
    return static(l10n_img_file_name(ctx, url))


@jinja2.contextfunction
def high_res_img(ctx, url, optional_attributes=None):
    url_high_res = convert_to_high_res(url)
    if optional_attributes and optional_attributes.pop('l10n', False) is True:
        url = l10n_img(ctx, url)
        url_high_res = l10n_img(ctx, url_high_res)
    else:
        url = static(path.join('img', url))
        url_high_res = static(path.join('img', url_high_res))

    if optional_attributes:
        class_name = optional_attributes.pop('class', '')
        attrs = ' ' + ' '.join('%s="%s"' % (attr, val)
                               for attr, val in optional_attributes.items())
    else:
        class_name = ''
        attrs = ''

    # Use native srcset attribute for high res images
    markup = ('<img class="{class_name}" src="{url}" '
              'srcset="{url_high_res} 1.5x"'
              '{attrs}>').format(url=url, url_high_res=url_high_res,
                                 attrs=attrs, class_name=class_name)

    return jinja2.Markup(markup)


@jinja2.contextfunction
def svg(ctx, file_name):
    file = path.join(settings.MEDIA_URL.strip('/'), 'svg/' + file_name + '.svg')
    return open(file).read()


@jinja2.contextfunction
def platform_img(ctx, url, optional_attributes=None):
    optional_attributes = optional_attributes or {}
    img_urls = {}
    platforms = optional_attributes.pop('platforms', settings.ALL_PLATFORMS)
    add_high_res = optional_attributes.pop('high-res', False)
    is_l10n = optional_attributes.pop('l10n', False)

    for platform in platforms:
        img_urls[platform] = add_string_to_image_url(url, platform)
        if add_high_res:
            img_urls[platform + '-high-res'] = convert_to_high_res(img_urls[platform])

    img_attrs = {}
    for platform, image in img_urls.items():
        if is_l10n:
            image = l10n_img_file_name(ctx, image)
        else:
            image = path.join('img', image)

        if path.exists(path.join(settings.MEDIA_URL.strip('/'), image)):
            key = 'data-src-' + platform
            img_attrs[key] = static(image)

    if add_high_res:
        img_attrs['data-high-res'] = 'true'

    img_attrs.update(optional_attributes)
    attrs = ' '.join(u'%s="%s"' % (attr, val)
                     for attr, val in img_attrs.items())

    # Don't download any image until the javascript sets it based on
    # data-src so we can do platform detection. If no js, show the
    # windows version.
    markup = (u'<img class="platform-img w-full h-auto js" src="" data-processed="false" {attrs}>'
              u'<noscript><img class="platform-img w-full h-auto win" src="{win_src}" {attrs}>'
              u'</noscript>').format(attrs=attrs, win_src=img_attrs[u'data-src-windows'])

    return jinja2.Markup(markup)


@jinja2.contextfunction
def download_thunderbird(ctx, channel='release', dom_id=None,
                         locale=None, force_direct=False,
                         alt_copy=None, button_color='button-green',
                         section='header', flex_class=None):
    """ Output a "Download Thunderbird" button.

    :param ctx: context from calling template.
    :param channel: name of channel: 'release', 'beta' or 'daily'. 'alpha' has been retired.
    :param dom_id: Use this string as the id attr on the element.
    :param locale: The locale of the download. Default to locale of request.
    :param force_direct: Force the download URL to be direct.
    :param alt_copy: Specifies alternate copy to use for download buttons.
    :param button_color: color of download button. Default to 'green'.
    :param section: Where the button is rendered in the page. Default to 'header'.
    :return: The button html.
    """
    alt_channel = '' if channel == 'release' else channel
    locale = ctx.get('LANG', None)
    dom_id = dom_id or 'download-button-desktop-%s' % channel

    l_version = thunderbird_desktop.latest_builds(locale, channel)
    if l_version:
        version, platforms = l_version
    else:
        locale = 'en-US'
        version, platforms = thunderbird_desktop.latest_builds('en-US', channel)

    # Gather data about the build for each platform
    builds = []

    for plat_os, plat_os_pretty in thunderbird_desktop.platform_labels.items():
        # And generate all the info
        download_link = thunderbird_desktop.get_download_url(
            channel, version, plat_os, locale,
            force_direct=force_direct,
        )

        # If download_link_direct is False the data-direct-link attr
        # will not be output, and the JS won't attempt the IE popup.
        if force_direct:
            # no need to run get_download_url again with the same args
            download_link_direct = False
        else:
            download_link_direct = thunderbird_desktop.get_download_url(
                channel, version, plat_os, locale,
                force_direct=True,
            )
            if download_link_direct == download_link:
                download_link_direct = False

        builds.append({'os': plat_os,
                       'os_pretty': plat_os_pretty,
                       'download_link': download_link,
                       'download_link_direct': download_link_direct})

    # Get the native name for current locale
    langs = thunderbird_desktop.languages
    locale_name = langs[locale]['native'] if locale in langs else locale

    data = {
        'locale_name': locale_name,
        'version': version,
        'product': 'thunderbird',
        'builds': builds,
        'id': dom_id,
        'channel': alt_channel,
        'alt_copy': alt_copy,
        'button_color': button_color,
        'section': section,
        'flex_class': flex_class
    }
    loader = jinja2.FileSystemLoader(searchpath=settings.WEBSITE_PATH)
    env = jinja2.Environment(loader=loader, extensions=['jinja2.ext.i18n'])
    translator = translate.gettext_object(locale)
    env.install_gettext_translations(translator)
    env.globals.update(**ctx)
    template = env.get_template('includes/download-button.html')

    html = template.render(data)
    return jinja2.Markup(html)


def thunderbird_url(page, channel='None'):
    """
    Return a product-related URL like /thunderbird/all/ or /thunderbird/beta/60.0/releasenotes/.
    page = ('system-requirements', 'all', 'releasenotes')
    channel = ('beta', 'release')
    Examples:
        {{ thunderbird_url('all', 'beta') }}
        {{ thunderbird_url('system-requirements', channel) }}
    """

    channel = channel or 'release'
    version = thunderbird_desktop.latest_version(channel)
    # replace 'b1', 'b2' etc in beta version with just 'beta', since we don't generate
    # new notes for each beta iteration.
    version = re.sub(r"b[1-9][0-9]?", "beta", version)

    url = '/en-US/thunderbird/{0}/{1}/'.format(version, page)

    if page == 'all':
        url = '/en-US/thunderbird/{0}/{1}/'.format(channel, page)
        if channel == 'release':
            url = '/en-US/thunderbird/{0}/'.format(page)

    return url


@jinja2.contextfunction
def donate_url(ctx, content='', source='thunderbird.net', medium='give', campaign='donation_flow_2023', download=False):
    # If this link is from a download button, donate.mozilla.org has thank you text.
    download_string = ''
    if download:
        download_string = '&tbdownload=true'

    # Add utm_campaign if we are using it.
    campaign_string = ''
    if campaign:
        campaign_string = '&utm_campaign={0}'.format(campaign)

    return (settings.DONATE_LINK.format(content=content, source=source, medium=medium)
            + campaign_string + download_string)


def safe_markdown(text):
    if not text:
        text = ''
    return jinja2.Markup(markdown.markdown(text))


def get_locale(lang):
    """Return a babel Locale object for lang. defaults to LANGUAGE_CODE."""
    lang = babel_format_locale_map.get(lang) or lang
    try:
        return Locale.parse(lang, sep='-')
    except (UnknownLocaleError, ValueError):
        return Locale(*settings.LANGUAGE_CODE.split('-'))


@jinja2.contextfunction
def get_fru_language(ctx):
    """
    Returns the current language if supported by FRU.
    Defaults to English if it's not supported.
    """
    language = ctx['LANG']

    try:
        if settings.FRU_LANGUAGES[language]:
            return settings.FRU_LANGUAGES[language]
    except KeyError:
        pass

    # Fallback to our default site language (en-US unless something weird happens)
    return settings.LANGUAGE_CODE


@jinja2.filters.contextfilter
def l10n_format_date(ctx, date, format='long'):
    """
    Formats a date according to the current locale. Wraps around
    babel.dates.format_date.
    """
    lang = get_locale(ctx['LANG'])
    if date:
        return format_date(date, locale=lang, format=format)
    else:
        return ''


@jinja2.contextfunction
def get_blog_data(ctx, entry):
    data = ctx.get('blog_data')
    parsed = {}

    parsed['summary'] = jinja2.Markup(data['entries'][entry]['summary_detail']['value'])
    parsed['title'] = data['entries'][entry]['title']
    parsed['comments'] = data['entries'][entry].get('slash_comments', '0')
    parsed['date'] = datetime.fromtimestamp(mktime(data['entries'][entry]['published_parsed'])).strftime('%B %-m, %Y')
    parsed['link'] = data['entries'][entry]['links'][0]['href']

    return parsed


@jinja2.contextfunction
def get_faq_list(ctx):
    """
    Returns a list of faq dicts: { 'question': '...', 'answer': '...' }
    This list is pre-formatted and localized.
    """
    from faq import get_entries

    entries = get_entries(ctx)

    return map(lambda entry: {'question': entry[0], 'answer': entry[1]}, entries)


def f(s, *args, **kwargs):
    return s.format(*args, **kwargs)


contextfunctions = dict(inspect.getmembers(sys.modules[__name__], inspect.isfunction))
