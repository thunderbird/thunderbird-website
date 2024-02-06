from __future__ import unicode_literals

import inspect
import os

import jinja2
import json
import markdown
import markupsafe
import re

import product_details
import settings
import sys
import translate

from babel.core import Locale, UnknownLocaleError
from babel.dates import format_date
from datetime import datetime
from os import path
from os.path import splitext
from product_details import thunderbird_desktop
from time import mktime
from urllib.parse import urlencode

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


@jinja2.pass_context
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


@jinja2.pass_context
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


@jinja2.pass_context
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


@jinja2.pass_context
def high_res_img(ctx, url, optional_attributes=None, scale='1.5x', alt_formats=()):
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
              'srcset="{url_high_res} {scale}"'
              '{attrs}>').format(url=url, url_high_res=url_high_res, scale=scale,
                                 attrs=attrs, class_name=class_name)

    # If we've specified some alternate formats we need to use the <picture> tag instead
    if alt_formats:
        tags = ["<picture>"]

        for alt_format in alt_formats:
            alt_url = f"{url.rsplit('.', maxsplit=1)[0]}.{alt_format}"
            alt_high_res_url = f"{url_high_res.rsplit('.', maxsplit=1)[0]}.{alt_format}"

            tags.append(
                '<source src="{url}" srcset="{url_high_res} {scale}"/>'.format(
                    url=alt_url, url_high_res=alt_high_res_url, scale=scale
                )
            )

        tags.append(markup)
        tags.append('</picture>')

        return markupsafe.Markup("\n".join(tags))

    return markupsafe.Markup(markup)


@jinja2.pass_context
def svg(ctx, file_name):
    file = path.join(settings.MEDIA_URL.strip('/'), 'svg/' + file_name + '.svg')
    return open(file).read()


@jinja2.pass_context
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

    return markupsafe.Markup(markup)


@jinja2.pass_context
def download_thunderbird(ctx, channel='release', dom_id=None,
                         locale=None, force_direct=False,
                         alt_copy=None, button_class=None,
                         section='header', flex_class=None,
                         hide_footer_links=False):
    """ Output a "Download Thunderbird" button.

    :param ctx: context from calling template.
    :param channel: name of channel: 'release', 'beta' or 'daily'. 'alpha' has been retired.
    :param dom_id: Use this string as the id attr on the element.
    :param locale: The locale of the download. Default to locale of request.
    :param force_direct: Force the download URL to be direct.
    :param alt_copy: Specifies alternate copy to use for download buttons.
    :param button_class: Class of the button element. Default to `none`, and dynamically picks the class based on the channel.
    :param section: Where the button is rendered in the page. Default to 'header'.
    :param flex_class: Adjust the flexbox positioning class
    :param hide_footer_links: Whether we should hide the footer links (System Requirements, What's New, Privacy Policy) display. Default to 'False'.
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
        'button_class': button_class,
        'section': section,
        'flex_class': flex_class,
        'hide_footer_links': hide_footer_links,
    }
    loader = jinja2.FileSystemLoader(searchpath=settings.WEBSITE_PATH)
    env = jinja2.Environment(loader=loader, extensions=['jinja2.ext.i18n'])
    translator = translate.gettext_object(locale)
    env.install_gettext_translations(translator)
    env.globals.update(**ctx)
    template = env.get_template('includes/download-button.html')

    html = template.render(data)
    return markupsafe.Markup(html)


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


@jinja2.pass_context
def donate_url(ctx, content='', source='thunderbird.net', medium='fru', campaign='donation_2023', show_donation_modal=True, download=None, download_channel=None):
    """Forms a donation url with the given parameters. If you pass in None for any of the fields they will be excluded from the url
    :param ctx: Jinja context
    :param content: UTM Content tag
    :param source: UTM Source tag
    :param medium: UTM Medium tag
    :param campaign: UTM Campaign tag
    :param show_donation_modal: Whether we want to append form=support that will automatically load the FRU modal
    :param download: Whether we have already downloaded Thunderbird (Download button specific.) Boolean or None.
    :param download_channel: What download channel to append to the url (Download button specific.) String or None.
    """
    form = None
    if show_donation_modal:
        form = 'support'

    query = {
        'form': form,
        'utm_content': content,
        'utm_source': source,
        'utm_medium': medium,
        'utm_campaign': campaign,
        'downloaded': download,
        'download_channel': download_channel
    }

    filtered_query = {k: v for k, v in query.items() if v is not None}

    return "?{}".format(urlencode(filtered_query))


@jinja2.pass_context
def redirect_donate_url(ctx, location='thunderbird.download', make_full_url=False, **kwargs):
    """Helper function to piece together the full donation url. Defaults to the settings for our Download button."""
    base_url = ''
    if make_full_url:
        base_url = settings.CANONICAL_URL

    return "{url}{path}{query}".format(url=base_url, path=url(ctx, location), query=donate_url(ctx, **kwargs))


def safe_markdown(text):
    if not text:
        text = ''
    return markupsafe.Markup(markdown.markdown(text))


def get_locale(lang):
    """Return a babel Locale object for lang. defaults to LANGUAGE_CODE."""
    lang = babel_format_locale_map.get(lang) or lang
    try:
        return Locale.parse(lang, sep='-')
    except (UnknownLocaleError, ValueError):
        return Locale(*settings.LANGUAGE_CODE.split('-'))


@jinja2.pass_context
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


@jinja2.filters.pass_context
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


@jinja2.pass_context
def get_blog_data(ctx, entry):
    data = ctx.get('blog_data')
    parsed = {}

    entry = data['entries'][entry]

    parsed['summary'] = markupsafe.Markup(entry['summary_detail']['value'])
    parsed['title'] = entry['title']
    parsed['comments'] = entry.get('thr_total', '0')  # Comment count (atom extension)
    parsed['date'] = datetime.fromtimestamp(mktime(entry['published_parsed'])).strftime('%B %-m, %Y')
    parsed['link'] = entry['links'][0]['href']
    parsed['thumbnail_url'] = None
    parsed['thumbnail_alt'] = None

    # Find our thumbnail
    for link in entry['links']:
        if link['rel'] == 'thumbnail':
            parsed['thumbnail_url'] = link['href']
            parsed['thumbnail_alt'] = link['title']
            break

    return parsed


@jinja2.pass_context
def get_latest_build(ctx, channel):
    """Returns the latest build number for a given channel (e.g. 102.10.0 for release)"""
    return thunderbird_desktop.latest_version(channel)


@jinja2.pass_context
def get_form_assembly_localization_url(ctx):
    """Returns a formatted url with the correct locale for form assembly localization js"""
    locale = ctx.get('LANG', settings.LANGUAGE_CODE)
    fa_locale = settings.FA_LANGUAGES.get(locale, 'en_US')

    return "https://mozillafoundation.tfaforms.net/wForms/3.11/js/localization-{locale}.js?v=75513df1680ccc55e2c889a1b1dff356256982a6".format(locale=fa_locale)


@jinja2.pass_context
def get_outdated_versions(ctx):
    """ Get a JSON str of versions and dates of the last released minor version for outdated versions. """
    versions = product_details.thunderbird_desktop.list_releases()
    last_stable_release = {}
    last_safe_release = float(settings.LAST_SAFE_VERSION)

    for version in versions:
        # major is a float, minor is a string
        major_version = version[0]
        minor_versions = version[1]['minor']

        if len(minor_versions) > 0:
            last_version = minor_versions[-1]
        else:
            last_version = str(major_version)

        # Don't include safe versions
        if major_version >= last_safe_release:
            continue

        release_date = product_details.thunderbird_desktop.get_release_date(last_version)
        last_stable_release[major_version] = release_date

    return json.dumps(last_stable_release)


def is_calendarific_free_tier():
    """Returns if we're expecting to use the Calendarific free tier"""
    try:
        return os.environ['CALENDARIFIC_IS_FREE_TIER'].lower() == 'true'
    except KeyError:
        return True


def f(s, *args, **kwargs):
    return s.format(*args, **kwargs)


contextfunctions = dict(inspect.getmembers(sys.modules[__name__], inspect.isfunction))
