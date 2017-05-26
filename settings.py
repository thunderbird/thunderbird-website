PROD_LANGUAGES = ('ach', 'af', 'an', 'ar', 'as', 'ast', 'az', 'be', 'bg',
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
                  'uz', 'vi', 'xh', 'zh-CN', 'zh-TW', 'zu')

LANGUAGES_BIDI = ('he', 'ar', 'fa', 'ur')

#default language
LANGUAGE_CODE = 'en-US'

PAGE_LINKS = {'thunderbird.channel':'',
              'thunderbird.features':'',
              'thunderbird.index':'',
              'thunderbird.organizations':'',
              'mozorg.home':''}
CANONICAL_URL = 'https://www.thunderbird.net'

# path for assets that need processing, like LESS and js
ASSETS = 'assets'

# base url for media files
MEDIA_URL = '/media'

ALL_PLATFORMS = ('windows', 'linux', 'mac')
