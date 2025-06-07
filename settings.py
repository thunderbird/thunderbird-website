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
    'bn-BD': 'bn',  # https://github.com/thunderbird/thunderbird.net-l10n/issues/1
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

ENUS_ONLY = [
    # Atom feed is only generated on en-US
    'thunderbird.releases.atom',
    'thunderbird.privacy'
]

# Most pages under /thunderbird/ are en-US only, except these.
# The What's New page is not here because TB picks the locale.
ALWAYS_LOCALIZE = [
    '/appeal',
    '/eoy',
    '/beta-appeal',
    '/holidayeoy',
    '/spring24',
    '/all',
]

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
WEBSITE_PATH = 'sites/www.thunderbird.net/'

# path to the start page templates
START_PATH = 'sites/start.thunderbird.net/'

UPDATES_PATH = 'sites/updates.thunderbird.net/'

# path for the finished website artifacts.
WEBSITE_RENDERPATH = 'dist/www.thunderbird.net'

# path for the finished start page artifacts.
START_RENDERPATH = 'dist/start.thunderbird.net'

UPDATES_RENDERPATH = 'dist/updates.thunderbird.net'

LOCALE_PATH = 'libs/locale'

CALDATA_URL = MEDIA_URL + '/caldata/'

CALDATA_AUTOGEN_URL = 'media/caldata/autogen/'

CALDATA_AUTOGEN_AUTHOR = 'Thunderbird'

CALDATA_YEARS_TO_GENERATE = 3

# Apple uses this to verify the domain every time the SSL cert expires, disabling will break Apple Pay donations.
USE_APPLE_PAY_DOMAIN_VERIFICATION = True

# path to product-details json files
JSON_PATH = 'libs/product-details/public/1.0'

ALL_PLATFORMS = ('windows', 'linux', 'mac')

# Mappings for the helper.url function.
# 'thunderbird.sysreq' and 'wiki.moz' have special behaviour.
URL_MAPPINGS = {
    'atn': 'https://addons.thunderbird.net/',
    'blog': 'https://blog.thunderbird.net/',
    'calendar': '/calendar',
    'contribute': 'https://github.com/thunderbird/thunderbird-website',
    'download.android.gplay': 'https://play.google.com/store/apps/details?id=net.thunderbird.android&referrer=utm_campaign%3Dandroid_website_appeal%26utm_medium%3Dweb%26utm_source%3Dthunderbird.net%26utm_content%3Dlink',
    'download.android.gplay-beta': 'https://play.google.com/store/apps/details?id=net.thunderbird.android.beta&referrer=utm_campaign%3Dandroid_website_appeal%26utm_medium%3Dweb%26utm_source%3Dthunderbird.net%26utm_content%3Dlink',
    'download.android.fdroid': 'https://f-droid.org/packages/net.thunderbird.android',
    'download.android.fdroid-beta': 'https://f-droid.org/packages/net.thunderbird.android.beta',
    'download.android.binary': 'https://github.com/thunderbird/thunderbird-android/releases',
    'download.android.compatibility': 'https://github.com/thunderbird/thunderbird-android/wiki/ReleaseNotes#minimum-android-version-compatibility',
    'download.android.changelog': 'https://github.com/thunderbird/thunderbird-android/releases?q=prerelease:false',
    'download.desktop.flathub': 'https://flathub.org/apps/org.mozilla.Thunderbird',
    'download.desktop.msstore': 'https://apps.microsoft.com/detail/9pm5vm1s3vmq',
    'download.desktop.snap': 'https://snapcraft.io/thunderbird',
    'firefox.dnt': 'https://www.mozilla.org/firefox/dnt/',
    'firefox.enterprise': 'https://www.mozilla.org/firefox/enterprise/',
    'firefox.release-calendar': 'https://wiki.mozilla.org/Release_Management/Calendar',
    'foundation.licensing.website-content': 'https://www.mozilla.org/foundation/licensing/website-content/',
    'foundation.about': 'https://foundation.mozilla.org/about/',
    'guidelines': 'https://www.mozilla.org/en-US/about/governance/policies/participation/',
    'legal.fraud-report': 'https://www.mozilla.org/about/legal/fraud-report/',
    'legal.index': 'https://www.mozilla.org/en-US/about/legal/terms/mozilla/',
    'legal.infringement': 'https://www.mozilla.org/en-US/about/legal/report-infringement/',
    'legal.trademark': 'https://www.mozilla.org/about/legal/defend-mozilla-trademarks/',
    'mozorg.home': 'https://www.mozilla.org/',
    'mozorg.careers.tb': 'https://www.mozilla.org/careers/listings/?team=MZLA%2FThunderbird',
    'mozorg.connect': 'https://connect.mozilla.org/',
    'mozorg.connect.tb': 'https://connect.mozilla.org/t5/ideas/idb-p/ideas/label-name/thunderbird',
    'mozorg.mpl2': 'https://www.mozilla.org/MPL/',
    'mozwiki.support-languages': 'https://wiki.mozilla.org/Thunderbird/Support/Community_support_based_on_languages',
    'mzla.blog-post': 'https://blog.thunderbird.net/2020/01/thunderbirds-new-home/',
    'participate.desktop.docs': 'https://developer.thunderbird.net/',
    'participate.desktop.repo': 'https://developer.thunderbird.net/thunderbird-development/getting-started',
    'participate.desktop.matrix': 'https://matrix.to/#/#maildev:mozilla.org',
    'participate.android.docs': 'https://github.com/thunderbird/thunderbird-android/tree/main/docs',
    'participate.android.repo': 'https://github.com/thunderbird/thunderbird-android',
    'participate.android.matrix': 'https://matrix.to/#/#tb-android:mozilla.org',
    'participate.website.docs': 'https://github.com/thunderbird/thunderbird-website/blob/master/README.md',
    'participate.website.repo': 'https://github.com/thunderbird/thunderbird-website',
    'participate.website.matrix': 'https://matrix.to/#/#tb-infrastructure:mozilla.org',
    'participate.design.topicbox': 'https://thunderbird.topicbox.com/groups/ux',
    'participate.design.matrix': 'https://matrix.to/#/#tb-design:mozilla.org',
    'participate.test.desktop.beta': 'https://support.mozilla.org/kb/thunderbird-beta',
    'participate.test.desktop.bugs': 'https://bugzilla.mozilla.org/describecomponents.cgi?product=Thunderbird',
    'participate.test.android.beta': 'https://blog.thunderbird.net/2024/09/help-us-test-the-thunderbird-for-android-beta/',
    'participate.test.android.bugs': 'https://github.com/thunderbird/thunderbird-android/issues',
    'participate.translate.desktop.docs': 'https://source-docs.thunderbird.net/en/latest/l10n/index.html',
    'participate.translate.desktop.pontoon': 'https://pontoon.mozilla.org/projects/thunderbird/',
    'participate.translate.android.docs': 'https://docs.weblate.org/en/latest/user/translating.html',
    'participate.translate.android.weblate': 'https://hosted.weblate.org/projects/tb-android/',
    'participate.document.desktop.user': 'https://support.mozilla.org/products/thunderbird',
    'participate.document.desktop.dev': 'https://developer.thunderbird.net/',
    'participate.document.desktop.code': 'https://source-docs.thunderbird.net',
    'participate.document.android.user': 'https://support.mozilla.org/products/thunderbird-android',
    'participate.promote.tilvids': 'https://tilvids.com/a/thunderbird',
    'participate.promote.android.review': 'https://play.google.com/store/apps/details?id=net.thunderbird.android.beta',
    'participate.support.desktop.matrix': 'https://matrix.to/#/#thunderbird:mozilla.org',
    'participate.support.android.matrix': 'https://matrix.to/#/#tb-android:mozilla.org',
    'privacy': 'https://www.mozilla.org/privacy/websites/',
    'privacy.notices.websites': 'https://www.mozilla.org/privacy/websites/#data-tools',
    'privacy.notices.donations': 'https://www.mozilla.org/privacy/websites/#donations',
    'privacy.notices.thunderbird': '/privacy',
    'support': 'https://support.mozilla.org/products/thunderbird/',
    'support.mobile': 'https://support.mozilla.org/products/thunderbird-android/',
    'support.question': 'https://support.mozilla.org/questions/new/thunderbird',
    'thunderbird.about': '/about',
    'thunderbird.about.our-mission-statement': '/about/mission-statement',
    'thunderbird.android.announcement': 'https://blog.thunderbird.net/2024/10/thunderbird-for-android-8-0-takes-flight/',
    'thunderbird.bugzilla.new-bug': 'https://bugzilla.mozilla.org/enter_bug.cgi?product=Thunderbird',
    'thunderbird.calendar.holiday': '/calendar/holidays',
    'thunderbird.careers': '/careers',
    'thunderbird.channel': '/channel',
    'thunderbird.contact': '/contact',
    'thunderbird.contribute': '/contribute',
    'thunderbird.donate': '/donate',
    'thunderbird.donate.form': '/donate?form=support',
    'thunderbird.donate.faq': '/donate#faq',
    'thunderbird.donate.modify': 'https://supporter.thunderbird.net/',
    'thunderbird.donate.ways-to-give': '/donate#ways-to-give',
    'thunderbird.donate.ways-to-give.check': '/donate#ways-to-give-check',
    'thunderbird.donate.contact': '/donate/help',
    'thunderbird.download': '/download',
    'thunderbird.download-beta': '/download/beta',
    'thunderbird.download.thank-you': '/thank-you',
    'thunderbird.enterprise': 'https://wiki.mozilla.org/Thunderbird/Enterprise',
    'thunderbird.enterprise.documentation': 'https://enterprise.thunderbird.net/',
    'thunderbird.features': '/features',
    'thunderbird.get-involved': '/get-involved',
    'thunderbird.index': '/',
    'thunderbird.latest.all': '/thunderbird/all/',
    'thunderbird.latest.beta': '/thunderbird/all/?release=beta',
    'thunderbird.lists.enterprise': 'https://thunderbird.topicbox.com/groups/enterprise',
    'thunderbird.organizations': '/organizations',
    'thunderbird.participate': '/participate',
    'thunderbird.privacy': '/privacy',
    'thunderbird.products.desktop': '/desktop',
    'thunderbird.products.mobile': '/mobile',
    'thunderbird.releases.index': '/thunderbird/releases',
    'thunderbird.releases.atom': '/thunderbird/releases/atom.xml',
    'thunderbird.style': 'https://style.thunderbird.net',
    'thunderbird.site.bug-report': 'https://github.com/thunderbird/thunderbird-website/issues',
    'thunderbird.social.facebook': 'https://www.facebook.com/Thunderbird/',
    'thunderbird.social.youtube': 'https://www.youtube.com/@ThunderbirdProject',
    'thunderbird.social.linkedin': 'https://www.linkedin.com/company/thunderbird-email/',
    'thunderbird.social.mastodon': 'https://mastodon.online/@thunderbird',
    'thunderbird.social.bluesky': 'https://bsky.app/profile/thunderbird.net',
    'thunderbird.115.whatsnew': '/thunderbird/115.0/whatsnew',
    'thunderbird.128.whatsnew': '/thunderbird/128.0/whatsnew',
    'thunderbird.128esr.releasenotes': '/thunderbird/128.0esr/releasenotes',
    'updates.115.appeal.nov24.donate': '/thunderbird/115.0/nov24/donate/',
    'updates.128.appeal.nov24.donate': '/thunderbird/128.0/nov24/donate/',
    'updates.115.appeal.dec24.donate': '/thunderbird/115.0/dec24/donate/',
    'updates.128.appeal.dec24.donate': '/thunderbird/128.0/dec24/donate/',
    'updates.128.appeal.apr25': '/thunderbird/128.0/apr25/',
    'updates.128.appeal.apr25.donate': '/thunderbird/128.0/apr25/donate/',
}

BLOG_FEED_URL = 'https://blog.thunderbird.net/feed/atom/'

SHOW_BETA_NOTES_IN_RSS_FEED = False

ACTIVE_SURVEY_URL = 'https://www.surveymonkey.com/r/69C9LSH'

THUNDERBIRD_DESKTOP_PRIVACY_POLICY_URL = 'https://raw.githubusercontent.com/mozilla/legal-docs/main/en/thunderbird_privacy_policy.md'

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
    # 2024 Redesign
    'base-style': ['less/base-style.less'],
    'whatsnew-128': ['less/whatsnew-128.less'],
    'appeal-128': ['less/appeal-128.less'],
    'monthly-style': ['less/monthly.less'],
}

WEBSITE_JS = {
    'common-bundle': [
        'js/common/jquery-3.6.0.min.js', 'js/common/spin.min.js', 'js/common/mozilla-utils.js',
        'js/common/form.js', 'js/common/mozilla-client.js', 'js/common/mozilla-image-helper.js',
        'js/common/class-list-polyfill.js', 'js/common/mozilla-global-nav.js',
        'js/common/base-page-init.js', 'js/common/core-datalayer.js', 'js/common/core-datalayer-init.js',
        'js/common/autodownload.js', 'js/common/donations.js', 'js/common/ab-testing.js', 'js/common/beta-appeal.js',
        'js/common/download.js', 'js/common/donation-notice.js'
    ],
    'site-bundle': [
        'js/base/site.js', 'js/base/dnt-helper.js', 'js/base/mozilla-cookie-helper.js',
        'js/base/core-datalayer-page-id.js', 'js/app.js'
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

UPDATES_CSS = {
    "updates-style": ["less/updates-style.less"],
    "base-style": ["less/base-style.less"],
    "appeal-nov24-style": ["less/appeals/nov24.less"],
    "appeal-dec24-style": ["less/appeals/dec24.less"],
    "appeal-apr25-style": ["less/appeals/apr25.less"],
    "monthly-style": ["less/monthly.less"],
}

UPDATES_JS = {
    'common-bundle': [
        # Load bearing order..Donation must come before AB testing.
        'js/common/donations.js', 'js/common/ab-testing.js', 'js/common/donation-notice.js'
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
    'NL': [('Netherlands (Dutch)', 'nl'), ('Netherlands (English)', 'en'), ('Netherlands (German)', 'de'), ('Netherlands (French)', 'fr')],
    'EE': ('Estonia', 'et'),
    'FI': [('Finland (Finnish)', 'fi'), ('Finland (Swedish)', 'sv')],
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

# Used to normalize filenames for calendar generation
# This is the first part of the filename, 'Holidays' is bolted on in code.
# So 'Belgian (Dutch)' will become 'BelgianHoldays.ics'
# If the value is a tuple, the first part is before 'Holidays' and the second part is after.
CALENDAR_REMAP = {
    'Algeria (French)': 'Algeria',
    'Algeria (Arabic)': ('Algeria', 'Arabic'),
    'Belgian (Dutch)': 'Belgian',
    'Belgian (French)': ('Belgian', 'French'),
    'Bulgaria': 'Bulgarian',
    'Canada (English)': 'Canada',
    'Canada (French)': ('Canada', 'French'),
    'Colombia': 'Colombian',
    'Finland (Finnish)': 'Finland',
    'Finland (Swedish)': ('Finland', 'Swedish'),
    'France': 'French',
    'Germany': 'German',
    'Hungary': 'Hungarian',
    'Ireland (English)': 'Ireland',
    'Ireland (Irish)': ('Ireland', 'Irish'),
    'Italy': 'Italian',
    'Kazakhstan': ('Kazakhstan', 'English'),
    'Lithuania': 'Lithuanian',
    'Luxembourg (French)': ('Luxembourg', 'French'),
    'Luxembourg (German)': ('Luxembourg', 'German'),
    'Netherlands (Dutch)': 'Dutch',
    'Netherlands (English)': ('Dutch', 'English'),
    'Netherlands (German)': ('Dutch', 'German'),
    'Netherlands (French)': ('Dutch', 'French'),
    'Norway': 'Norwegian',
    'Poland': 'Polish',
    'Slovenia': 'Slovenian',
    'Slovakia': 'Slovak',
    'Switzerland': 'Swiss',
    'United Kingdom': 'UK',
    'United States': 'US'
}

# Filter out specific versions for the release notes page
VERSIONS_TO_FILTER = []

# Old path (excluding locale) -> helper.url key
WEBSITE_REDIRECTS = {
    'download': 'thunderbird.latest.all',
    ('download', 'beta'): 'thunderbird.latest.beta',
    'get-involved': 'thunderbird.participate',
    'contribute': 'thunderbird.participate',
    'features': 'thunderbird.index',
    ('thunderbird', '128.0esr', 'whatsnew'): 'thunderbird.128.whatsnew',
    ('thunderbird', '128.0', 'releasenotes'): 'thunderbird.128esr.releasenotes',
}

# Similar to website redirects but for UTN
UPDATES_REDIRECTS = {
    ('thunderbird', 'appeal'): 'updates.128.appeal.apr25'
}

# The default release channel to use when various function defaults are used
# This will change the channel of the main download button.
DEFAULT_RELEASE_VERSION = 'release'

MATOMO_SITE_IDS = {
    'website': 1,
    'utn': 3,
}

FRU_FORM_IDS = {
    # General
    'support': 'support',
    'tfa': 'tfa',

    # Appeals
    '20years': '20years',
}

# Flip to True to display a "Response times may be slower than usual" warning on the donor help form.
DONOR_HELP_SLOW_WARNING = False

# Turning this value to True will enable a thunderbird.net site-wide announcement banner
# Make sure to edit it in includes/announcement.html !
SITE_ANNOUNCEMENT = True

# Shows a dialog element with information on how to donate if their browser or browser addons have blocked FRU
# In reality this can trigger for slow internet users, but we don't have a perfect way to detect this.
SHOW_DONATION_BLOCKED_NOTICE = True
