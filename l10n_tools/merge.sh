find ../locale -name \*.po -printf '%h\n' -execdir msgmerge -U --backup=off messages.po ../../templates/LC_MESSAGES/messages.pot \;
