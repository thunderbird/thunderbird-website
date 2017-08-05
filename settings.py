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

CANONICAL_URL = 'https://stage.thunderbird.net'

# url for the server that serves Thunderbird downloads
BOUNCER_URL = 'https://download.mozilla.org/'

# path for assets that need processing, like LESS and js
ASSETS = 'assets'

# base url for media files
MEDIA_URL = '/media'

# path to the website templates
WEBSITE_PATH = 'website/'

# path to product-details json files
JSON_PATH = 'product-details-json/product-details/'

ALL_PLATFORMS = ('windows', 'linux', 'mac')

URL_MAPPINGS = {
    'firefox.dnt': 'https://www.mozilla.org/firefox/dnt/',
    'firefox.organizations.faq': 'https://www.mozilla.org/firefox/organizations/faq/',
    'foundation.licensing.website-content': 'https://www.mozilla.org/foundation/licensing/website-content/',
    'thunderbird.channel': '/channel',
    'thunderbird.features': '/features',
    'thunderbird.index': '/',
    'thunderbird.organizations': '/organizations',
    'thunderbird.latest.all': '/thunderbird/all/',
    'contribute': 'https://github.com/thundernest/thunderbird-website',
    'mozorg.home': 'https://www.mozilla.org/',
    'mozorg.about': 'https://www.mozilla.org/about/',
    'mozorg.contact.contact-landing': 'https://www.mozilla.org/contact/',
    'legal.fraud-report': 'https://www.mozilla.org/about/legal/fraud-report/',
    'legal.index': 'https://www.mozilla.org/about/legal/',
    'privacy': 'https://www.mozilla.org/privacy/',
    'privacy.notices.websites': 'https://www.mozilla.org/privacy/websites/#cookies',
    'privacy.notices.thunderbird': 'https://www.mozilla.org/privacy/thunderbird/',
    'support': 'https://support.mozilla.org/products/thunderbird/',
}

DONATE_LINK = (
    'https://donate.mozilla.org/{locale}/thunderbird/?presets={presets}'
    '&amount={default}&ref=EOYFR2015&utm_campaign=EOYFR2015'
    '&utm_source=thunderbird.net&utm_medium=referral&utm_content={source}'
    '&currency={currency}'
)

DONATE_PARAMS = {
    'en-US': {
        'currency': 'usd',
        'symbol': '$',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'an': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'as': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'ast': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'bn-IN': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'brx': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'ca': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'cs': {
        'currency': 'czk',
        'symbol': u'Kč',
        'presets': '400,200,100,55',
        'default': '200'
    },
    'cy': {
        'currency': 'gbp',
        'symbol': u'£',
        'presets': '20,10,5,3',
        'default': '10'
    },
    'da': {
        'currency': 'dkk',
        'symbol': 'kr',
        'presets': '160,80,40,20',
        'default': '80'
    },
    'de': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'dsb': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'el': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'en-GB': {
        'currency': 'gbp',
        'symbol': u'£',
        'presets': '20,10,5,3',
        'default': '10'
    },
    'es-AR': {
        'currency': 'ars',
        'symbol': '$',
        'presets': '1600,800,400,200',
        'default': '800'
    },
    'es-CL': {
        'currency': 'clp',
        'symbol': '$',
        'presets': '68000,34000,17000,10200',
        'default': '34000'
    },
    'es-ES': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'es-MX': {
        'currency': 'mxn',
        'symbol': '$',
        'presets': '240,120,60,35',
        'default': '120'
    },
    'eo': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'et': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'eu': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'fi': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'fr': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'fy-NL': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'ga-IE': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'gd': {
        'currency': 'gbp',
        'symbol': u'£',
        'presets': '20,10,5,3',
        'default': '10'
    },
    'gl': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'gu-IN': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'he': {
        'currency': 'ils',
        'symbol': u'₪',
        'presets': '60,30,15,9',
        'default': '30'
    },
    'hi-IN': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'hsb': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'hu': {
        'currency': 'huf',
        'symbol': 'Ft',
        'presets': '4000,2000,1000,600',
        'default': '2000'
    },
    'id': {
        'currency': 'idr',
        'symbol': 'Rp',
        'presets': '270000,140000,70000,40000',
        'default': '140000'
    },
    'in': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'it': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'ja': {
        'currency': 'jpy',
        'symbol': u'¥',
        'presets': '1600,800,400,250',
        'default': '800'
    },
    'ja-JP': {
        'currency': 'jpy',
        'symbol': u'¥',
        'presets': '1600,800,400,250',
        'default': '800'
    },
    'ja-JP-mac': {
        'currency': 'jpy',
        'symbol': u'¥',
        'presets': '1600,800,400,250',
        'default': '800'
    },
    'kn': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'lij': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'lt': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'lv': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'ml': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'mr': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'nb-NO': {
        'currency': 'nok',
        'symbol': 'kr',
        'presets': '160,80,40,20',
        'default': '80'
    },
    'nn-NO': {
        'currency': 'nok',
        'symbol': 'kr',
        'presets': '160,80,40,20',
        'default': '80'
    },
    'nl': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'or': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'pa-IN': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'pl': {
        'currency': 'pln',
        'symbol': u'zł',
        'presets': '80,40,20,10',
        'default': '40'
    },
    'pt-BR': {
        'currency': 'brl',
        'symbol': 'R$',
        'presets': '375,187,90,55',
        'default': '187'
    },
    'pt-PT': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'ru': {
        'currency': 'rub',
        'symbol': u'₽',
        'presets': '1000,500,250,140',
        'default': '500'
    },
    'sat': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'sk': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'sl': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'sv-SE': {
        'currency': 'sek',
        'symbol': 'kr',
        'presets': '160,80,40,20',
        'default': '80'
    },
    'sr': {
        'currency': 'eur',
        'symbol': u'€',
        'presets': '100,50,25,15',
        'default': '50'
    },
    'ta': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'te': {
        'currency': 'inr',
        'symbol': u'₹',
        'presets': '1000,500,250,150',
        'default': '500'
    },
    'th': {
        'currency': 'thb',
        'symbol': u'฿',
        'presets': '500,250,125,75',
        'default': '250'
    },
    'zh-CN': {
        'currency': 'cny',
        'symbol': u'¥',
        'presets': '700,350,175,100',
        'default': '350'
    },
    'zh-TW': {
        'currency': 'twd',
        'symbol': 'NT$',
        'presets': '3200,1600,800,475',
        'default': '1600'
    },
}
