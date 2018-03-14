import os
import sys
os.chdir('..')
sys.path.append('.')

import polib
import settings
import translate

for lang in settings.PROD_LANGUAGES:
    popath = 'newlocale/{0}/LC_MESSAGES/messages.po'.format(lang)
    po = polib.pofile(popath)
    translator = translate.Translation(lang, ['thunderbird/start/release', 'thunderbird/index', 'thunderbird/features', 'thunderbird/channel', 'main', 'download_button'])
    for entry in po:
        translation = translator.gettext(entry.msgid)
        if translation not in entry.msgid:
            entry.msgstr=translation
    print "{0} language po file edited.\n".format(lang)
    po.save()
