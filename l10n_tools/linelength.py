import os
import polib
import sys
os.chdir('..')
sys.path.append('.')
import settings


# This is a ridiculous hack to get line lengths back to what Pontoon expects,
# which avoids messy git diffs with unnecessary line length changes all over
# the .po files.

for lang in settings.PROD_LANGUAGES:
    if lang != 'en-US':
        popath = 'locale/{0}/LC_MESSAGES/messages.po'.format(lang.replace('-', '_'))
        po = polib.pofile(popath, wrapwidth=200)
        po.save()
