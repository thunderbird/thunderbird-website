find ../locale -name \*.po -printf '%h\n' -execdir msgattrib --set-obsolete --ignore-file=../../templates/LC_MESSAGES/messages.pot -o messages.po messages.po \;
find ../locale -name \*.po -printf '%h\n' -execdir msgattrib --no-obsolete -o messages.po messages.po \;
python linelength.py
