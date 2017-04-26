from staticjinja import make_site
import os
import translate

extensions = ['jinja2.ext.i18n']
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

def text_dir(lang):
      textdir = 'ltr'
      if lang in LANGUAGES_BIDI:
            textdir = 'rtl'
      return textdir

def build_site(lang):
      context = {'LANG': lang,
                 'DIR': text_dir(lang) }

      outpath = os.path.join('site', lang)
      if not os.path.exists(outpath):
            os.makedirs(outpath)
      site = make_site(outpath=outpath, staticpaths=["media/"], extensions=extensions, env_globals=context)
      # Add l10n_css function to context
      translator = translate.Translation(lang)
      site._env.install_gettext_translations(translator)
      site._env.globals.update(l10n_css=translator.l10n_css)

      site.render(use_reloader=False)

build_site('en-US')

for lang in PROD_LANGUAGES:
      build_site(lang)
