# -*- coding: utf-8 -*-

# Languages we build the site in.
PROD_LANGUAGES = (
    'ach', 'af', 'an', 'ar', 'as', 'ast', 'az', 'be', 'bg',
    'bn-BD', 'bn-IN', 'br', 'bs', 'ca', 'cak', 'cs',
    'cy', 'da', 'de', 'dsb', 'el', 'en-GB', 'en-US',
    'en-ZA', 'eo', 'es-AR', 'es-CL', 'es-ES', 'es-MX', 'et',
    'eu', 'fa', 'ff', 'fi', 'fr', 'fy-NL', 'ga-IE', 'gd',
    'gl', 'gn', 'gu-IN', 'he', 'hi-IN', 'hr', 'hsb',
    'hu', 'hy-AM', 'id', 'is', 'it', 'ja', 'ja-JP-mac',
    'ka', 'kab', 'kk', 'km', 'kn', 'ko', 'lij', 'lt', 'ltg', 'lv',
    'mai', 'mk', 'ml', 'mr', 'ms', 'my', 'nb-NO', 'ne-NP', 'nl',
    'nn-NO', 'oc', 'or', 'pa-IN', 'pl', 'pt-BR', 'pt-PT',
    'rm', 'ro', 'ru', 'si', 'sk', 'sl', 'son', 'sq',
    'sr', 'sv-SE', 'ta', 'te', 'th', 'tr', 'uk', 'ur',
    'uz', 'vi', 'xh', 'zh-CN', 'zh-TW', 'zu'
)

# Languages that require RTL support.
LANGUAGES_BIDI = ('he', 'ar', 'fa', 'ur')

#default language
LANGUAGE_CODE = 'en-US'

# Map short locale names to long, preferred locale names. This
# will be used in urlresolvers to determine the
# best-matching locale from the user's Accept-Language header.
CANONICAL_LOCALES = {
    'en': 'en-US',
    'es': 'es-ES',
    'ja-jp-mac': 'ja',
    'no': 'nb-NO',
    'pt': 'pt-BR',
    'sv': 'sv-SE',
    'zh-hant': 'zh-TW',     # Bug 1263193
    'zh-hant-tw': 'zh-TW',  # Bug 1263193
    'zh-hk': 'zh-TW',       # Bug 1338072
    'zh-hant-hk': 'zh-TW',  # Bug 1338072
}

CANONICAL_URL = 'https://www.thunderbird.net'

# url for the server that serves Thunderbird downloads
BOUNCER_URL = 'https://download.mozilla.org/'

# path for assets that need processing, like LESS and js
ASSETS = 'assets'

# base url for media files
MEDIA_URL = '/media'

# path to the website templates
WEBSITE_PATH = 'website/'

CALDATA_URL = MEDIA_URL + '/caldata/'

# path to product-details json files
JSON_PATH = 'product-details-json/product-details/'

ALL_PLATFORMS = ('windows', 'linux', 'mac')

URL_MAPPINGS = {
    'calendar': '/calendar',
    'firefox.dnt': 'https://www.mozilla.org/firefox/dnt/',
    'firefox.organizations.faq': 'https://www.mozilla.org/firefox/organizations/faq/',
    'foundation.licensing.website-content': 'https://www.mozilla.org/foundation/licensing/website-content/',
    'thunderbird.channel': '/channel',
    'thunderbird.enterprise': 'https://wiki.mozilla.org/Thunderbird/tb-enterprise',
    'thunderbird.features': '/features',
    'thunderbird.get-involved': '/get-involved',
    'thunderbird.index': '/',
    'thunderbird.organizations': '/organizations',
    'thunderbird.releases.index': '/thunderbird/releases',
    'thunderbird.latest.all': '/thunderbird/all/',
    'thunderbird.site.bug-report': 'https://github.com/thundernest/thunderbird-website/issues',
    'contribute': 'https://github.com/thundernest/thunderbird-website',
    'mozorg.home': 'https://www.mozilla.org/',
    'mozorg.about': 'https://www.mozilla.org/about/',
    'thunderbird.contact': '/contact',
    'legal.fraud-report': 'https://www.mozilla.org/about/legal/fraud-report/',
    'legal.index': 'https://www.mozilla.org/about/legal/',
    'privacy': 'https://www.mozilla.org/privacy/',
    'privacy.notices.websites': 'https://www.mozilla.org/privacy/websites/#cookies',
    'privacy.notices.thunderbird': 'https://www.mozilla.org/privacy/thunderbird/',
    'support': 'https://support.mozilla.org/products/thunderbird/',
    'blog': 'https://blog.mozilla.org/thunderbird'

}

DONATE_LINK = (
    'https://donate.mozilla.org/thunderbird/'
    '?utm_source={source}&utm_medium=referral&utm_content={content}'
)
