import os
import polib
import sys
os.chdir('..')
sys.path.append('.')
import settings
import translate


for lang in settings.PROD_LANGUAGES:
    if lang != 'en-US':
        popath = 'locale/{0}/LC_MESSAGES/messages.po'.format(lang.replace('-', '_'))
        po = polib.pofile(popath)
        translator = translate.Translation(lang, ['thunderbird/start/release'])
        for entry in po:
            if entry.msgid == 'Contribute' or entry.msgid == 'Need Support?':
                translation = translator.gettext(entry.msgid)
                if entry.msgid == translation:
                    entry.msgstr = ''
                else:
                    entry.msgstr = translator.gettext(entry.msgid)
        print "{0} language po file edited.\n".format(lang)
        po.save()
