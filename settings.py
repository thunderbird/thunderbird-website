# -*- coding: utf-8 -*-

# Languages we build the site in.
PROD_LANGUAGES = (
    'ach', 'af', 'an', 'ar', 'as', 'ast', 'az', 'be', 'bg',
    'bn', 'br', 'bs', 'ca', 'cak', 'cs',
    'cy', 'da', 'de', 'dsb', 'el', 'en-GB', 'en-US',
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

# url for the ftp server where Nightly builds are hosted.
NIGHTLY_URL = 'https://ftp.mozilla.org/pub/thunderbird/nightly/latest-comm-central-l10n/'

# url for the mozilla wiki used for some documentation.
WIKI_URL = 'https://wiki.mozilla.org'

# path for assets that need processing, like LESS and js
ASSETS = 'assets'

# base url for media files
MEDIA_URL = '/media'

# path to the website templates
WEBSITE_PATH = 'website/'

# path to the start page templates
START_PATH = 'start-page/'

# path for the finished website artifacts.
WEBSITE_RENDERPATH = 'thunderbird.net'

# path for the finished start page artifacts.
START_RENDERPATH = 'site'

CALDATA_URL = MEDIA_URL + '/caldata/'

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
    'foundation.licensing.website-content': 'https://www.mozilla.org/foundation/licensing/website-content/',
    'foundation.about': 'https://foundation.mozilla.org/about/',
    'guidelines': 'https://www.mozilla.org/en-US/about/governance/policies/participation/',
    'legal.fraud-report': 'https://www.mozilla.org/about/legal/fraud-report/',
    'legal.index': 'https://www.mozilla.org/en-US/about/legal/terms/mozilla/',
    'mozorg.home': 'https://www.mozilla.org/',
    'mzla.blog-post': 'https://blog.thunderbird.net/2020/01/thunderbirds-new-home/',
    'privacy': 'https://www.mozilla.org/privacy/websites/',
    'privacy.notices.websites': 'https://www.mozilla.org/privacy/websites/#data-tools',
    'privacy.notices.thunderbird': 'https://www.mozilla.org/privacy/thunderbird/',
    'support': 'https://support.mozilla.org/products/thunderbird/',
    'thunderbird.about': '/about',
    'thunderbird.careers': '/careers',
    'thunderbird.channel': '/channel',
    'thunderbird.contact': '/contact',
    'thunderbird.enterprise': 'https://wiki.mozilla.org/Thunderbird/tb-enterprise',
    'thunderbird.features': '/features',
    'thunderbird.get-involved': '/get-involved',
    'thunderbird.index': '/',
    'thunderbird.latest.all': '/thunderbird/all/',
    'thunderbird.organizations': '/organizations',
    'thunderbird.releases.index': '/thunderbird/releases',
    'thunderbird.style': 'https://style.thunderbird.net',
    'thunderbird.site.bug-report': 'https://github.com/thundernest/thunderbird-website/issues',
}

BLOG_FEED_URL = 'https://blog.thunderbird.net/feed/'

ENUS_ONLY = [
    'thunderbird.contact',
    'thunderbird.careers',
    'thunderbird.get-involved',
    'thunderbird.organizations',
]

DONATE_LINK = (
    'https://donate.mozilla.org/thunderbird/'
    '?utm_source={source}&utm_medium=referral&utm_content={content}'
)

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
    'thunderbird-style': ['less/style.less'],
}

WEBSITE_JS = {
    'common-bundle': [
        'js/common/jquery-1.11.3.min.js', 'js/common/spin.min.js', 'js/common/mozilla-utils.js',
        'js/common/form.js', 'js/common/mozilla-client.js', 'js/common/mozilla-image-helper.js',
        'js/common/nav-main-resp.js', 'js/common/class-list-polyfill.js', 'js/common/mozilla-global-nav.js',
        'js/common/base-page-init.js', 'js/common/core-datalayer.js', 'js/common/core-datalayer-init.js',
        'js/common/autodownload.js'
    ],
    'site-bundle': [
        'js/base/site.js', 'js/base/dnt-helper.js', 'js/base/mozilla-cookie-helper.js',
        'js/base/core-datalayer-page-id.js'
    ]
}

START_CSS = {
    'start-style': ['less.old/sandstone/fonts.less', 'less.old/thunderbird/start.less']
}
