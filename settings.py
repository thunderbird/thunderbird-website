# -*- coding: utf-8 -*-

# Languages we build the site in.
PROD_LANGUAGES = (
    'ach', 'af', 'an', 'ar', 'as', 'ast', 'az', 'be', 'bg',
    'bn', 'br', 'bs', 'ca', 'cak', 'cs',
    'cy', 'da', 'de', 'dsb', 'el', 'en-CA', 'en-GB', 'en-US',
    'en-ZA', 'eo', 'es-AR', 'es-CL', 'es-ES', 'es-MX', 'et',
    'eu', 'fa', 'ff', 'fi', 'fr', 'fy-NL', 'ga-IE', 'gd',
    'gl', 'gn', 'gu-IN', 'he', 'hi-IN', 'hr', 'hsb',
    'hu', 'hy-AM', 'id', 'is', 'it', 'ja',
    'ka', 'kab', 'kk', 'km', 'kn', 'ko', 'lij', 'lt', 'ltg', 'lv',
    'mai', 'mk', 'ml', 'mr', 'ms', 'my', 'nb-NO', 'ne-NP', 'nl',
    'nn-NO', 'oc', 'or', 'pa-IN', 'pl', 'pt-BR', 'pt-PT',
    'rm', 'ro', 'ru', 'si', 'sk', 'sl', 'son', 'sq',
    'sr', 'sv-SE', 'ta', 'te', 'th', 'tr', 'uk', 'ur',
    'uz', 'vi', 'xh', 'zh-CN', 'zh-TW', 'zu'
)

# Languages that require RTL support.
LANGUAGES_BIDI = ('he', 'ar', 'fa', 'ur')

# Default main site language.
LANGUAGE_CODE = 'en-US'

# Fundraise Up's supported languages
FRU_LANGUAGES = {
    'da': 'da',
    'nl': 'nl',
    'fi': 'fi',
    'fr': 'fr',
    'de': 'de',
    'hu': 'hu',
    'it': 'it',
    'ja': 'ja',
    'nb-NO': 'nb',
    'nn-NO': 'nb',
    'pt-BR': 'pt-BR',
    'pt-PT': 'pt-PT',
    'es-MX': 'es-MX',
    'es-AR': 'es-AR',
    'es-ES': 'es-ES',
    'es-CL': 'es-CL',
    'sv-SE': 'sv-SE',
    'en-CA': 'en-CA',
    'en-GB': 'en-GB',
    'en-US': 'en-US',
}

# List of supported FormAssembly locales, scoped to the dropdown on the donor contact form
# TB Locale -> FA Locale
FA_LANGUAGES = {
        'zh-CN': 'zh_CN',
        'cs': 'cs',
        'da': 'da',
        'nl': 'nl',
        'en-US': 'en_US',
        'de': 'de',
        'fr': 'fr',
        'it': 'it',
        'ja': 'ja',
        'pl': 'pl',
        'pt-BR': 'pt_BR',
        'ru': 'ru',
        'es-MX': 'es',
        'es-AR': 'es',
        'es-ES': 'es',
        'es-CL': 'es',
}

# Map short locale names to long, preferred locale names. This
# will be used in urlresolvers to determine the
# best-matching locale from the user's Accept-Language header.
CANONICAL_LOCALES = {
    'bn-BD': 'bn',  # https://github.com/thundernest/thunderbird.net-l10n/issues/1
    'bn-IN': 'bn',  # These two locales were merged for the above issue.
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

# url for the server that serves Thunderbird downloads.
BOUNCER_URL = 'https://download.mozilla.org/'

# url for the mozilla wiki used for some documentation.
WIKI_URL = 'https://wiki.mozilla.org'

# path for assets that need processing, like LESS and js
ASSETS = 'assets'

# base url for media files
MEDIA_URL = '/media'

# location of the Thunderbird favicon
FAVICON_PATH = '/media/img/thunderbird/favicon.ico'

# path to the website templates
# templates with paths starting with "_" or "includes" are excluded by builder.py
WEBSITE_PATH = 'website/'

# path to the start page templates
START_PATH = 'start-page/'

# path for the finished website artifacts.
WEBSITE_RENDERPATH = 'thunderbird.net'

# path for the finished start page artifacts.
START_RENDERPATH = 'site'

CALDATA_URL = MEDIA_URL + '/caldata/'

CALDATA_AUTOGEN_URL = 'media/caldata/autogen/'

CALDATA_AUTOGEN_AUTHOR = 'Thunderbird'

CALDATA_YEARS_TO_GENERATE = 3

# path to product-details json files
JSON_PATH = 'product-details/public/1.0'

ALL_PLATFORMS = ('windows', 'linux', 'mac')

# Mappings for the helper.url function.
# 'thunderbird.sysreq' and 'wiki.moz' have special behaviour.
URL_MAPPINGS = {
    'blog': 'https://blog.thunderbird.net/',
    'calendar': '/calendar',
    'contribute': 'https://github.com/thundernest/thunderbird-website',
    'firefox.dnt': 'https://www.mozilla.org/firefox/dnt/',
    'firefox.enterprise': 'https://www.mozilla.org/firefox/enterprise/',
    'firefox.release-calendar': 'https://wiki.mozilla.org/Release_Management/Calendar',
    'foundation.licensing.website-content': 'https://www.mozilla.org/foundation/licensing/website-content/',
    'foundation.about': 'https://foundation.mozilla.org/about/',
    'guidelines': 'https://www.mozilla.org/en-US/about/governance/policies/participation/',
    'legal.fraud-report': 'https://www.mozilla.org/about/legal/fraud-report/',
    'legal.index': 'https://www.mozilla.org/en-US/about/legal/terms/mozilla/',
    'legal.infringement': 'https://www.mozilla.org/en-US/about/legal/report-infringement/',
    'mozorg.home': 'https://www.mozilla.org/',
    'mzla.blog-post': 'https://blog.thunderbird.net/2020/01/thunderbirds-new-home/',
    'privacy': 'https://www.mozilla.org/privacy/websites/',
    'privacy.notices.websites': 'https://www.mozilla.org/privacy/websites/#data-tools',
    'privacy.notices.thunderbird': 'https://www.mozilla.org/privacy/thunderbird/',
    'support': 'https://support.mozilla.org/products/thunderbird/',
    'thunderbird.about': '/about',
    'thunderbird.about.our-mission-statement': '/about#our-mission-statement',
    'thunderbird.careers': '/careers',
    'thunderbird.channel': '/channel',
    'thunderbird.contact': '/contact',
    'thunderbird.donate': '/donate',
    'thunderbird.donate.form': '/donate?form=support',
    'thunderbird.donate.faq': '/donate#faq',
    'thunderbird.donate.ways-to-give': '/donate#ways-to-give',
    'thunderbird.donate.ways-to-give.check': '/donate#ways-to-give-check',
    'thunderbird.donate.contact': '/donate/help',
    'thunderbird.download': '/download',
    'thunderbird.download-beta': '/download/beta',
    'thunderbird.enterprise': 'https://wiki.mozilla.org/Thunderbird/tb-enterprise',
    'thunderbird.enterprise.documentation': 'https://enterprise.thunderbird.net/',
    'thunderbird.features': '/features',
    'thunderbird.get-involved': '/get-involved',
    'thunderbird.index': '/',
    'thunderbird.latest.all': '/thunderbird/all/',
    'thunderbird.lists.enterprise': 'https://thunderbird.topicbox.com/groups/enterprise',
    'thunderbird.organizations': '/organizations',
    'thunderbird.releases.index': '/thunderbird/releases',
    'thunderbird.style': 'https://style.thunderbird.net',
    'thunderbird.site.bug-report': 'https://github.com/thundernest/thunderbird-website/issues',
}

BLOG_FEED_URL = 'https://blog.thunderbird.net/feed/atom/'

ENUS_ONLY = [
    'thunderbird.contact',
    'thunderbird.careers',
    'thunderbird.get-involved',
    'thunderbird.organizations',
]

# WEBSITE_CSS = {
#     'calendar-bundle': ['less/thunderbird/calendar.less', 'less/base/menu-resp.less'],
#     'responsive-bundle': ['less/sandstone/sandstone-resp.less', 'less/base/global-nav.less'],
#     'thunderbird-landing': ['less/thunderbird/landing.less', 'less/base/menu-resp.less'],
#     'thunderbird-features': ['less/thunderbird/features.less', 'less/base/menu-resp.less'],
#     'thunderbird-channel': ['less/thunderbird/channel.less', 'less/base/menu-resp.less'],
#     'thunderbird-organizations': ['less/thunderbird/organizations.less', 'less/base/menu-resp.less'],
#     'thunderbird-all': ['less/thunderbird/all.less', 'less/base/menu-resp.less'],
#     'releasenotes': ['less/firefox/releasenotes.less', 'less/base/menu-resp.less'],
#     'releases-index': ['less/firefox/releases-index.less', 'less/base/menu-resp.less'],
# }

WEBSITE_CSS = {
    'thunderbird-style': ['less/style.less'], 'tb-115-style': ['css/115-homepage.css'],
}

WEBSITE_JS = {
    'common-bundle': [
        'js/common/jquery-3.6.0.min.js', 'js/common/spin.min.js', 'js/common/mozilla-utils.js',
        'js/common/form.js', 'js/common/mozilla-client.js', 'js/common/mozilla-image-helper.js',
        'js/common/nav-main-resp.js', 'js/common/class-list-polyfill.js', 'js/common/mozilla-global-nav.js',
        'js/common/base-page-init.js', 'js/common/core-datalayer.js', 'js/common/core-datalayer-init.js',
        'js/common/autodownload.js', 'js/common/donations.js', 'js/common/ab-testing.js', 'js/common/beta-appeal.js'
    ],
    'site-bundle': [
        'js/base/site.js', 'js/base/dnt-helper.js', 'js/base/mozilla-cookie-helper.js',
        'js/base/core-datalayer-page-id.js'
    ]
}

START_CSS = {
    'start-style': ['less/start.less'],
}

START_JS = {
    'common-bundle': [
        # Load bearing order..Donation must come before AB testing.
        'js/common/donations.js', 'js/common/ab-testing.js'
    ]
}

CURRENCIES = {
    # Second value is the default.
    'brl': {'symbol': 'R$', 'presets': ['80', '40', '20', '10'], 'default': '40'},
    'cad': {'symbol': '$', 'presets': ['65', '30', '15', '4'], 'default': '30'},
    'czk': {'symbol': 'Kč', 'presets': ['450', '220', '110', '70'], 'default': '220'},
    'dkk': {'symbol': 'kr', 'presets': ['130', '60', '30', '20'], 'default': '60'},
    'eur': {'symbol': '€', 'presets': ['50', '30', '20', '10'], 'default': '30'},
    'gbp': {'symbol': '£', 'presets': ['40', '25', '15', '8'], 'default': '25'},
    'huf': {'symbol': 'Ft', 'presets': ['5600', '2800', '1400', '850'], 'default': '2800'},
    'inr': {'symbol': '₹', 'presets': ['1000', '500', '250', '150'], 'default': '500'},
    'jpy': {'symbol': '¥', 'presets': ['2240', '1120', '560', '340'], 'default': '1120'},
    'mxn': {'symbol': '$', 'presets': ['400', '200', '100', '60'], 'default': '200'},
    'nok': {'symbol': 'kr', 'presets': ['160', '80', '40', '20'], 'default': '80'},
    'pln': {'symbol': 'zł', 'presets': ['80', '40', '20', '10'], 'default': '40'},
    'rub': {'symbol': '₽', 'presets': ['1300', '800', '500', '200'], 'default': '800'},
    'sek': {'symbol': 'kr', 'presets': ['180', '90', '45', '30'], 'default': '90'},
    'twd': {'symbol': 'NT$', 'presets': ['480', '240', '150', '70'], 'default': '240'},
    'usd': {'symbol': '$', 'presets': ['50', '30', '20', '10'], 'default': '30'}
}

LOCALE_CURRENCIES = {
    'ast': 'eur',
    'ca': 'eur',
    'cs': 'czk',
    'cy': 'gbp',
    'da': 'dkk',
    'de': 'eur',
    'dsb': 'eur',
    'el': 'eur',
    'en-CA': 'cad',
    'en-GB': 'gbp',
    'en-US': 'usd',
    'es-ES': 'eur',
    'es-MX': 'mxn',
    'et': 'eur',
    'fr': 'eur',
    'fy-NL': 'eur',
    'gu-IN': 'inr',
    'hi-IN': 'inr',
    'hsb': 'eur',
    'hu': 'huf',
    'it': 'eur',
    'ja': 'jpy',
    'lv': 'eur',
    'ml': 'inr',
    'mr': 'inr',
    'nb-NO': 'nok',
    'nl': 'eur',
    'nn-NO': 'nok',
    'pa-IN': 'inr',
    'pl': 'pln',
    'pt-BR': 'brl',
    'pt-PT': 'eur',
    'ru': 'rub',
    'sk': 'eur',
    'sl': 'eur',
    'sv-SE': 'sek',
    'ta': 'inr',
    'te': 'inr',
    'zh-TW': 'twd'
 }

CALENDARIFIC_API_URL = "https://calendarific.com/api/v2/holidays"

# Country Code : Calendar Name
CALENDAR_LOCALES = {
    'AL': ('Albania', 'sq'),
    'DZ': [('Algeria (Arabic)', 'ar'), ('Algeria (French)', 'fr')],
    'AR': ('Argentina', 'es'),
    'AM': ('Armenia', 'hy'),
    'AU': ('Australia', 'en'),
    'AT': ('Austrian', 'de'),
    'BE': [('Belgian (French)', 'fr'), ('Belgian (Dutch)', 'nl')],
    'BO': ('Bolivia', 'es'),
    'BR': ('Brazil', 'pt'),
    'BG': ('Bulgaria', 'bg'),
    'CA': [('Canada (English)', 'en'), ('Canada (French)', 'fr')],
    'CL': ('Chile', 'es'),
    'CN': ('China', 'zh'),
    'CO': ('Colombia', 'es'),
    'CR': ('Costa Rica', 'es'),
    'HR': ('Croatia', 'hr'),
    'CZ': ('Czech', 'cs'),
    'DK': ('Denmark', 'da'),
    'DO': ('Dominican Republic', 'es'),
    'NL': ('Netherlands', 'nl'),
    'EE': ('Estonia', 'et'),
    'FI': ('Finland', 'fi'),
    'FR': ('France', 'fr'),
    'DE': ('Germany', 'de'),
    'GR': ('Greece', 'el'),
    'GY': ('Guyana', 'en'),
    'HT': ('Haiti', 'ht'),
    'HK': ('Hong Kong', 'zh'),
    'HU': ('Hungary', 'hu'),
    'IS': ('Iceland', 'is'),
    'IN': ('India', 'hi'),
    'ID': ('Indonesia', 'id'),
    'IE': [('Ireland (Irish)', 'ga'), ('Ireland (English)', 'en')],
    'IL': ('Israel', 'en'),
    'IT': ('Italy', 'it'),
    'JP': ('Japan', 'ja'),
    'KZ': ('Kazakhstan', 'kk'),
    'KE': ('Kenya', 'sw'),
    'LV': ('Latvia', 'lv'),
    'LB': ('Lebanon', 'ar'),
    'LI': ('Liechtenstein', 'de'),
    'LT': ('Lithuania', 'lt'),
    'LU': [('Luxembourg (French)', 'fr'), ('Luxembourg (German)', 'de')],
    'MY': ('Malaysia', 'ms'),
    'MT': ('Malta', 'mt'),
    'MX': ('Mexico', 'es'),
    'MA': ('Morocco', 'ar'),
    'NA': ('Namibia', 'en'),
    'NZ': ('New Zealand', 'en'),
    'NI': ('Nicaragua', 'en'),
    'NO': ('Norway', 'no'),
    'PK': ('Pakistan', 'ur'),
    'PE': ('Peru', 'es'),
    'PH': ('Philippines', 'en'),
    'PL': ('Polish', 'pl'),
    'PT': ('Portugal', 'pt'),
    'PR': ('Puerto Rico', 'en'),
    'RO': ('Romania', 'ro'),
    'RU': ('Russia', 'ru'),
    'SG': ('Singapore', 'ms'),
    'SK': ('Slovakia', 'sk'),
    'SI': ('Slovenia', 'sl'),
    'ZA': ('South Africa', 'en'),
    'KR': ('South Korea', 'ko'),
    'ES': ('Spain', 'es'),
    'LK': ('Sri Lanka', 'en'),
    'SE': ('Swedish', 'sv'),
    'CH': ('Switzerland', 'en'),
    'TW': ('Taiwan', 'zh'),
    'TH': ('Thailand', 'th'),
    'TT': ('Trinidad and Tobago', 'en'),
    'TR': ('Turkey', 'tr'),
    'GB': ('United Kingdom', 'en'),
    'UA': ('Ukraine', 'uk'),
    'UY': ('Uruguay', 'es'),
    'US': ('United States', 'en'),
    'VN': ('Vietnam', 'vi'),
}
