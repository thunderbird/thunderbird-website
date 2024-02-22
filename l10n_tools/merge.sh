find ../libs/locale -name \*.po -printf '%h\n' -execdir msgmerge -U --backup=off --no-fuzzy-matching messages.po ../../templates/LC_MESSAGES/messages.pot \;
