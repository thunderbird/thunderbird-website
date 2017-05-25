from os import path
from os.path import splitext

import inspect
import jinja2
import settings
import sys

def static(filepath):
    return path.join(settings.MEDIA_URL, filepath)


def url(key):
    return ''


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
def platform_img(ctx, url, optional_attributes=None):
    return static(url)


@jinja2.contextfunction
def download_thunderbird(ctx, channel='release', dom_id=None,
                         locale=None, force_direct=False,
                         alt_copy=None, button_color='button-green'):
      return ''


contextfunctions = dict(inspect.getmembers(sys.modules[__name__], inspect.isfunction))
