#!/bin/bash

cd ../website/_includes
mv -t .. base-resp.html download-button.html lang_switcher.html site-footer.html
cd ../..
pybabel extract -F babel.cfg -o locale/templates/LC_MESSAGES/messages.pot .
cd website
mv -t _includes base-resp.html download-button.html lang_switcher.html site-footer.html
cd ../l10n_tools
bash merge.sh
python linelength.py
