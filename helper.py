from __future__ import unicode_literals

import inspect
import os
from urllib.parse import urlparse
from collections import OrderedDict

import jinja2
import json
import markdown
import markupsafe
import re
import settings
import sys
import translate

from babel.core import Locale, UnknownLocaleError
from babel.dates import format_date
from datetime import datetime
from os import path
from os.path import splitext
from product_details import thunderbird_desktop, thunderbird_mobile
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
def video(ctx, file_path, alt_text=None, alt_formats=(), mime_types=None, poster_path=None, auto_play=False, loop=False, controls=False, disable_pip=True):
    """Add a video element to the page with some additional file formats.
    :param file_path: relative path to the main video file.
    :param alt_text: The text if all video sources are unsupported.
    :param alt_formats: A tuple of alternate video extensions.
    :param mime_types: A tuple of mime types for the videos (these can include codecs.) These should match up with the [main ext + *alt_formats]. If None then the extension is just bolted onto 'video/'
    :param poster_path: A static image to display while the video loads.
    :param auto_play: Adds autoplay and muted attribute to the video element.
    :param loop: Adds the loop attribute to the video element.
    :param controls: Adds the controls attribute to the video element.
    :param disable_pip: Adds the disablepictureinpicture and playsinline attribute to the video element.
    """
    file_name, ext = splitext(file_path)
    ext = ext.replace('.', '')

    attributes = []
    if auto_play:
        attributes.append('autoplay="true"')
        attributes.append('muted="true"')
    if loop:
        attributes.append('loop="true"')
    if controls:
        attributes.append('controls="true"')
    if disable_pip:
        attributes.append('disablepictureinpicture="true"')
        attributes.append('playsinline="true"')
    if poster_path:
        attributes.append(f'poster="{static(poster_path)}"')

    # If we've specified some alternate formats we need to use the <picture> tag instead
    tags = [f'<video {" ".join(attributes)}>']

    for index, format in enumerate([ext, *alt_formats]):
        path = f"{file_name}.{format}"

        if mime_types:
            mime_type = mime_types[index]
        else:
            mime_type = f'video/{format}'

        tags.append(
            f'<source src="{static(path)}" type="{mime_type}"/>'
        )

    if alt_text:
        tags.append(f'<p>{alt_text}</p>')

    tags.append('</video>')

    return markupsafe.Markup("\n".join(tags))


@jinja2.pass_context
def svg(ctx, file_name):
    """Returns an inlined svg element, optionally (and by default) wraps a span around it to allow screen readers to ignore it."""
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
def download_url(ctx, platform_os, version=None, channel=settings.DEFAULT_RELEASE_VERSION, locale=None):
    """Return a specific download url for a given version, platform, channel and optionally force a locale"""
    if locale is None:
        locale = ctx.get('LANG')

    if channel == 'mobile' or channel == 'mobile-beta':
        return thunderbird_mobile.get_download_url(
            channel, version, platform_os, locale
        )

    if version is None:
        l_version = thunderbird_desktop.latest_builds(locale, channel)
        if l_version:
            version, platforms = l_version
        else:
            locale = 'en-US'
            version, platforms = thunderbird_desktop.latest_builds('en-US', channel)

    return thunderbird_desktop.get_download_url(
        channel, version, platform_os, locale,
    )


@jinja2.pass_context
def has_localized_download(ctx, locale, channel=settings.DEFAULT_RELEASE_VERSION):
    """Determine if a locale has a localized download link (or if it just defaults to en-US)"""
    return bool(thunderbird_desktop.latest_builds(locale, channel))


@jinja2.pass_context
def get_platform_icon(ctx, platform):
    windows_icon = 'base/icons/download/windows-dark'
    mac_icon = 'base/icons/download/apple-dark'
    linux_icon = 'base/icons/download/linux-dark'
    android_icon = 'base/icons/download/android-dark'

    platform_icons = {
        'win64': windows_icon,
        'msi': windows_icon,
        'win': windows_icon,
        'linux64': linux_icon,
        'linux': linux_icon,
        'osx': mac_icon,
        'android': android_icon
    }

    return platform_icons.get(platform, None)


@jinja2.pass_context
def get_platforms(ctx, include_mobile=False):
    """Returns a list of dict of available platforms per os. Includes mobile by default."""
    return thunderbird_desktop.grouped_platform_labels


@jinja2.pass_context
def get_mobile_platforms(ctx):
    return thunderbird_mobile.grouped_platform_labels


@jinja2.pass_context
def is_os_mobile(ctx, os):
    """Simple helper to determine if a given os is mobile. JavaScript friendly."""
    return 'true' if os == 'Android' else 'false'


@jinja2.pass_context
def get_channels(ctx):
    """Returns a dict of available channels. Includes mobile channels by default."""
    return thunderbird_desktop.channel_labels


@jinja2.pass_context
def get_mobile_channels(ctx):
    return thunderbird_mobile.channel_labels


@jinja2.pass_context
def get_latest_desktop_builds(ctx, channel=settings.DEFAULT_RELEASE_VERSION):
    """ Output the version and latest builds of Thunderbird Desktop
    :param ctx: context from calling template.
    :param channel: name of channel: 'esr', 'release', 'beta' or 'daily'. 'alpha' has been retired.
    :return: The button html.
    """
    locale = ctx.get('LANG', None)
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
        )

        builds.append({'os': plat_os,
                       'os_pretty': plat_os_pretty,
                       'download_link': download_link,
                       'download_link_direct': download_link})

    return version, builds


@jinja2.pass_context
def download_thunderbird(ctx, channel=settings.DEFAULT_RELEASE_VERSION, dom_id=None,
                         locale=None, force_direct=False,
                         alt_copy=None, button_class=None,
                         section='header', flex_class=None,
                         hide_footer_links=False):
    """
    Note: This is deprecated; use the 'includes/download/macros/download-smart.html' macro instead!
    Output a "Download Thunderbird" button.

    :param ctx: context from calling template.
    :param channel: name of channel: 'esr', 'release', 'beta' or 'daily'. 'alpha' has been retired.
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
    print("[Warning] Deprecated function 'download_thunderbird' in use!")
    alt_channel = '' if channel == settings.DEFAULT_RELEASE_VERSION else channel
    locale = ctx.get('LANG', None)
    dom_id = dom_id or 'download-button-desktop-%s' % channel

    version, builds = get_latest_desktop_builds(ctx, channel)

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
    template = env.get_template('includes/download/download-button.html')

    html = template.render(data)
    return markupsafe.Markup(html)


def thunderbird_url(page, channel=None):
    """
    Return a product-related URL like /thunderbird/all/ or /thunderbird/beta/60.0/releasenotes/.
    page = ('system-requirements', 'all', 'releasenotes')
    channel = ('beta', 'release')
    Examples:
        {{ thunderbird_url('all', 'beta') }}
        {{ thunderbird_url('system-requirements', channel) }}
    """

    channel = channel or settings.DEFAULT_RELEASE_VERSION
    version = thunderbird_desktop.latest_version(channel)
    # replace 'b1', 'b2' etc in beta version with just 'beta', since we don't generate
    # new notes for each beta iteration.
    version = re.sub(r"b[1-9][0-9]?", "beta", version)

    url = '/en-US/thunderbird/{0}/{1}/'.format(version, page)

    if page == 'all':
        url = '/en-US/thunderbird/{0}/{1}/'.format(channel, page)
        if channel in ['release', 'esr']:
            url = '/en-US/thunderbird/{0}/'.format(page)

    return url


@jinja2.pass_context
def donate_url(ctx, content='', source='thunderbird.net', medium='fru', campaign='donation_2023', show_donation_modal=True, download=None, download_channel=None, form_id=settings.FRU_FORM_IDS['support'], base_url=None):
    """Forms a donation url with the given parameters. If you pass in None for any of the fields they will be excluded from the url
    :param ctx: Jinja context
    :param content: UTM Content tag
    :param source: UTM Source tag
    :param medium: UTM Medium tag
    :param campaign: UTM Campaign tag
    :param show_donation_modal: Whether we want to append form=support that will automatically load the FRU modal
    :param download: Whether we have already downloaded Thunderbird (Download button specific.) Boolean or None.
    :param download_channel: What download channel to append to the url (Download button specific.) String or None.
    :param form_id: The id code that opens a specific form. Defaults to 'support'
    """
    form = None
    if show_donation_modal:
        form = form_id

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

    if base_url is None:
        base_url = ''

    return f'{base_url}?{urlencode(filtered_query)}'


@jinja2.pass_context
def redirect_donate_url(ctx, location='thunderbird.download.thank-you', make_full_url=False, **kwargs):
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
def get_locale_name(ctx, locale=None):
    locale = locale or ctx.get('LANG')
    if not locale:
        return None

    langs = thunderbird_desktop.languages
    return langs[locale]['native'] if locale in langs else locale


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
def get_latest_mobile_build(ctx, channel):
    return thunderbird_mobile.latest_version(channel)


@jinja2.pass_context
def get_form_assembly_localization_url(ctx):
    """Returns a formatted url with the correct locale for form assembly localization js"""
    locale = ctx.get('LANG', settings.LANGUAGE_CODE)
    fa_locale = settings.FA_LANGUAGES.get(locale, 'en_US')

    return "https://mozillafoundation.tfaforms.net/wForms/3.11/js/localization-{locale}.js?v=7e0d7c68797132abc85b3b6c57cdba52a4d73afd".format(locale=fa_locale)


@jinja2.pass_context
def is_system_requirements_dict(ctx) -> bool:
    release_notes: dict = ctx.get('release')
    system_requirements = release_notes.get('system_requirements')
    return isinstance(system_requirements, dict)


@jinja2.pass_context
def get_system_requirements_for_release_notes(ctx):
    """For release notes, we have the entire object in ctx"""
    release_notes: dict = ctx.get('release')
    system_requirements = release_notes.get('system_requirements')

    if isinstance(system_requirements, str):
        return None

    return system_requirements


@jinja2.pass_context
def get_domain_from_link(ctx, link):
    if not link:
        return ''
    return urlparse(link).hostname


def is_calendarific_free_tier():
    """Returns if we're expecting to use the Calendarific free tier"""
    try:
        return os.environ['CALENDARIFIC_IS_FREE_TIER'].lower() == 'true'
    except KeyError:
        return True


@jinja2.pass_context
def split_keep_delimiter(ctx, string: str, split: str):
    lines = string.split(split)
    return [f"{line}," for line in string.split(split)[:-1]] + lines[-1:]


def f(s, *args, **kwargs):
    return s.format(*args, **kwargs)


contextfunctions = dict(inspect.getmembers(sys.modules[__name__], inspect.isfunction))
