# coding=utf-8

from product_details import thunderbird_desktop as product_details
from jinja2 import Markup

import gettext
import os
import re
import settings


def strip_whitespace(message):
    """Collapses all whitespace into single spaces.
    Borrowed from Tower.
    """
    return re.compile(r'\s+', re.UNICODE).sub(' ', message).strip()


def get_translations(self):
    """
    Return the list of available translations for the langfile.
    :param langfile: the path to a lang file, retrieved with get_lang_path()
    :return: dict, like {'en-US': 'English (US)', 'fr': 'Français'}
    """
    cache_key = 'translations'
    translations = self.cache.get(cache_key, {})

    if translations:
        return translations

    for lang in settings.PROD_LANGUAGES:
        if lang in product_details.languages:
            translations[lang] = product_details.languages[lang]['native']

    self.cache[cache_key] = translations
    return translations


def l10n_css(self):
    """Return locale-specific css for `self.locale` on the translation object."""
    path = os.path.join(settings.MEDIA_URL.strip('/'), 'css', 'l10n', self.locale)
    markup = ''
    if os.path.exists(path):
        url = settings.MEDIA_URL + '/css/l10n/{0}/intl.css'.format(self.locale)
        markup = ('<link rel="stylesheet" media="screen,projection,tv" href='
                  '"{0}">'.format(url))

    return Markup(markup)


def gettext_object(lang):
    """Setup gettext translation object and add l10n_css and get_translations methods to it."""
    trans = gettext.translation("messages", localedir="locale", languages=[lang.replace('-', '_')], fallback=True)
    trans.cache = {}
    trans.locale = lang
    trans.get_translations = get_translations.__get__(trans)
    trans.l10n_css = l10n_css.__get__(trans)
    return trans
