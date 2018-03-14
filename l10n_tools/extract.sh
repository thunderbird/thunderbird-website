#!/bin/bash

cd ../website/_includes
mv -t .. base-resp.html download-button.html lang_switcher.html site-footer.html
mv -t . ../organizations/index.html
cd ../..
pybabel extract -F babel.cfg -o messages.pot .
cd website
mv -t _includes base-resp.html download-button.html lang_switcher.html site-footer.html
mv -t organizations _includes/index.html

