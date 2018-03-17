import os
import sys
os.chdir('..')
sys.path.append('.')

import polib
import settings
import translate

for lang in settings.PROD_LANGUAGES:
    if lang != 'en-US' and lang != 'it' and lang != 'pl':
        popath = 'locale/{0}/LC_MESSAGES/messages.po'.format(lang.replace('-','_'))
        po = polib.pofile(popath)
        translator = translate.Translation(lang, ['thunderbird/start/release'])
        for entry in po:
            if entry.msgid=='Welcome to <span>Thunderbird</span>' or entry.msgid=='Donate to Thunderbird' or entry.msgid=='Contribute to Thunderbird':
                if entry.msgstr==entry.msgid:
                    entry.msgstr=''
        print "{0} language po file edited.\n".format(lang)
        po.save()
