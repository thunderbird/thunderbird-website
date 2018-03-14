find ../locale -name \*.po -printf '%h\n' -execdir msgmerge -U --backup=off messages.po ~/thunderbird-website/messages.pot \;
