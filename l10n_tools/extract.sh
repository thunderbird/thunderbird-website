#!/bin/bash

cd ..
pybabel extract -F babel.cfg -o libs/locale/templates/LC_MESSAGES/messages.pot .
cd ./l10n_tools
bash merge.sh
python linelength.py
