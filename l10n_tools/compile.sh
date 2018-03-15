find locale -name \*.po -printf '%h\n' -execdir msgfmt messages.po -o messages.mo \;
