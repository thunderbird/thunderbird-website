from webob import Request
import re
import settings

def get_language_map():
    """
    Return a complete dict of language -> URL mappings, including the canonical
    short locale maps (e.g. es -> es-ES and en -> en-US).
    :return: dict
    """
    LUM = {i.lower(): i for i in settings.PROD_LANGUAGES}
    langs = dict(LUM.items() + settings.CANONICAL_LOCALES.items())
    # Add missing short locales to the list. This will automatically map
    # en to en-GB (not en-US), es to es-AR (not es-ES), etc. in alphabetical
    # order. To override this behavior, explicitly define a preferred locale
    # map with the CANONICAL_LOCALES setting.
    langs.update((k.split('-')[0], v) for k, v in LUM.items() if
                 k.split('-')[0] not in langs)
    return langs


def parse_accept_lang_header(lang_string):
    """
    Parse the lang_string, which is the body of an HTTP Accept-Language
    header, and return a list of (lang, q-value), ordered by 'q' values.
    Return an empty list if there are any format errors in lang_string.
    """

    # Format of Accept-Language header values. From RFC 2616, section 14.4 and 3.9
    # and RFC 3066, section 2.1
    accept_language_re = re.compile(r'''
            ([A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*|\*)      # "en", "en-au", "x-y-z", "es-419", "*"
            (?:\s*;\s*q=(0(?:\.\d{,3})?|1(?:\.0{,3})?))?  # Optional "q=1.00", "q=0.8"
            (?:\s*,\s*|$)                                 # Multiple accepts per header.
            ''', re.VERBOSE)

    result = []
    pieces = accept_language_re.split(lang_string.lower())
    if pieces[-1]:
        return []
    for i in range(0, len(pieces) - 1, 3):
        first, lang, priority = pieces[i:i + 3]
        if first:
            return []
        if priority:
            priority = float(priority)
        else:
            priority = 1.0
        result.append((lang, priority))
    result.sort(key=lambda k: k[1], reverse=True)
    return result


def get_best_language(accept_lang):
    """Given an Accept-Language header, return the best-matching language."""
    ranked = parse_accept_lang_header(accept_lang)
    FULL_LANGUAGE_MAP = get_language_map()

    for lang, _ in ranked:
        lang = lang.lower()
        if lang in FULL_LANGUAGE_MAP:
            return FULL_LANGUAGE_MAP[lang]
        pre = lang.split('-')[0]
        if pre in FULL_LANGUAGE_MAP:
            return FULL_LANGUAGE_MAP[pre]
    return settings.LANGUAGE_CODE


def application(environ, start_response):
    req = Request(environ)

    if 'thunderbird' in req.path_qs:
        # Release notes, system requirements, and 'all' builds pages are only available in English.
        language_code = 'en-US'
    else:
        language_code = get_best_language(environ.get('HTTP_ACCEPT_LANGUAGE', 'en-US'))

    location = "{0}/{1}{2}".format(req.host_url, language_code, req.path_qs)

    start_response('302 Found',
    [('Content-type', 'text/html; charset=utf-8' ),
    ('Cache-Control', 'private, s-maxage=0, max-age=604800'),
    ('Vary', 'Accept-Language'),
    ('Location', location)
    ])

    return ''


if __name__ == '__main__':
    #this runs when script is started directly from commandline
    try:
        #   create a simple WSGI server and run the application
        from wsgiref import simple_server
        print   "Running test   application -   point   your browser at http://localhost:8000/ ..."
        httpd   =   simple_server.WSGIServer(('',   8000), simple_server.WSGIRequestHandler)
        httpd.set_app(application)
        httpd.serve_forever()
    except ImportError:
        #wsgiref not installed, just output html to stdout
        for content in application({}, lambda status, headers: None):
            print content
