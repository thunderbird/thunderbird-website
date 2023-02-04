#!/bin/bash

cd ..
pybabel extract -F babel.cfg -o locale/templates/LC_MESSAGES/messages.pot .
cd website 
cd ../l10n_tools
bash merge.sh
python linelength.py
