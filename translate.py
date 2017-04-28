# coding=utf-8

import codecs
import os
import re
import requests
import requests_cache
from jinja2 import Markup

def strip_whitespace(message):
    """Collapses all whitespace into single spaces.
    Borrowed from Tower.
    """
    return re.compile(r'\s+', re.UNICODE).sub(' ', message).strip()

FORMAT_IDENTIFIER_RE = re.compile(r"""(%
                                  (?:\((\w+)\))? # Mapping key
                                  s)""", re.VERBOSE)
TAG_REGEX = re.compile(r"^## ([\w-]+) ##")

class Translation(object):


    def __init__(self, language, langfiles):
        self.locale = language
        self.cache = {}
        self.langfiles = langfiles

    def mail_error(self, path, message):
        print "{0} is corrupted: {1}".format(path, message)

    def parse(self, path, skip_untranslated=True, extract_comments=False):
        """
        Parse a dotlang file and return a dict of translations.
        :param path: Absolute path to a lang file.
        :param skip_untranslated: Exclude strings for which the ID and translation
                                  match.
        :param extract_comments: Extract one line comments from template if True
        :return: dict
        """
        trans = {}

        if not os.path.exists(path):
            return trans

        with codecs.open(path, 'r', 'utf-8', errors='replace') as lines:
            source = None
            comment = None

            for line in lines:
                if u'�' in line:
                    mail_error(path, line)

                line = line.strip()
                if not line:
                    continue

                if line[0] == '#':
                    comment = line.lstrip('#').strip()
                    continue

                if line[0] == ';':
                    source = line[1:]
                elif source:
                    for tag in ('{ok}', '{l10n-extra}'):
                        if line.lower().endswith(tag):
                            line = line[:-len(tag)]
                    line = line.strip()
                    if skip_untranslated and source == line:
                        continue
                    if extract_comments:
                        trans[source] = [comment, line]
                        comment = None
                    else:
                        trans[source] = line

        return trans

    def translate(self, text):
        """Search a list of .lang files for a translation"""
        lang = self.locale
        files = self.langfiles
        # don't attempt to translate the default language.
        if lang == 'en-US':
            return Markup(text)

        tweaked_text = strip_whitespace(text)

        for file_ in files:
            key = "dotlang-%s-%s" % (lang, file_)
            rel_path = os.path.join('locale', lang, '%s.lang' % file_)

            trans = self.cache.get(key)
            if trans is None:
                trans = self.parse(rel_path)
                self.cache[key] = trans

            if tweaked_text in trans:
                original = FORMAT_IDENTIFIER_RE.findall(text)
                translated = FORMAT_IDENTIFIER_RE.findall(trans[tweaked_text])
                if set(original) != set(translated):
                    explanation = ('The translation has a different set of '
                                   'replaced text (aka %s)')
                    message = '%s\n\n%s\n%s' % (explanation, text,
                                                trans[tweaked_text])
                    mail_error(rel_path, message)
                    return Markup(text)
                return Markup(trans[tweaked_text])

        return Markup(text)

    def lang_file_tag_set(self, path, lang=None):
        """Return a set of tags for a specific lang file and locale.
        :param path: the relative lang file name
        :param lang: the language code or the lang of the request if omitted
        :return: set of strings
        """
        lang = self.locale
        rel_path = os.path.join('locale', lang, '%s.lang' % path)
        cache_key = 'tag:%s' % rel_path
        tag_set = self.cache.get(cache_key)
        if tag_set is None:
            tag_set = set()
            try:
                with codecs.open(rel_path, 'r', 'utf-8', errors='replace') as lines:
                    for line in lines:
                        # Filter out Byte order Mark
                        line = line.replace(u'\ufeff', '')
                        m = TAG_REGEX.match(line)
                        if m:
                            tag_set.add(m.group(1))
                        else:
                            # Stop at the first non-tag line.
                            break
            except IOError:
                pass

            self.cache[cache_key] = tag_set

        return tag_set

    def get_translations_for_langfile(self, langfile):
        """
        Return the list of available translations for the langfile.
        :param langfile: the path to a lang file, retrieved with get_lang_path()
        :return: dict, like {'en-US': 'English (US)', 'fr': 'Français'}
        """
        cache_key = 'translations:%s' % langfile
        translations = self.cache.get(cache_key, {})

        if translations:
            return translations

        for lang in settings.PROD_LANGUAGES:
            if (lang in product_details.languages and
                    (lang == settings.LANGUAGE_CODE or
                     lang_file_is_active(langfile, lang))):
                translations[lang] = product_details.languages[lang]['native']

        self.cache[cache_key] = translations
        return translations

    def l10n_css(self):
        path = os.path.join('start-page', '_media', 'css', 'l10n', self.locale)
        markup = ''
        if os.path.exists(path):
            url = '/media/css/l10n/{0}/intl.css'.format(self.locale)
            markup = ('<link rel="stylesheet" media="screen,projection,tv" href='
                      '"{0}">'.format(url))

        return Markup(markup)

    def gettext(self, message):
        return self.translate(message)

    ugettext = gettext

    def ngettext(self, singular, plural, n):
        if n > 1:
            return plural
        return singular

    ungettext = gettext
