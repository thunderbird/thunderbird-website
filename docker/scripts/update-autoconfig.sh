#!/bin/bash
# Autoconfig update script - generates v1.1 XML files from ISPDB data
# Based on thundernest-ansible/files/update.sh

set -e

DEST=/var/www/html/autoconfig.momo
TEMP=/var/www/html/autoconfig-temp
DATA=/var/www/autoconfig.momo/ispdb

# Make sure destination directories exist
mkdir -p $DEST
mkdir -p $TEMP
mkdir -p $TEMP/v1.1

cd $DATA

# Copy webroot files (static assets)
cp -R ../webroot/* $TEMP/

# Activate virtualenv and run conversion
source /var/www/tbservices/bin/activate
python ../tools/convert.py -a -d $TEMP/v1.1 *

# Move generated files into place
rm -rf $DEST/*
mv $TEMP/* $DEST/
rm -rf $TEMP

echo "Autoconfig files generated successfully"

