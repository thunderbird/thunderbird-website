# thunderbird-website

This repo contains the Thunderbird in-client Start page and (eventually) the website and release notes.   
* https://start.thunderbird.net is automatically pushed from the `prod` branch, using the `site` directory as docroot.   
* https://start-stage.thunderbird.net is pushed from `master`.   

Pushes occur automatically with each commit to github on either branch.   

# Build Instructions

`pip install requirements.txt`   
`git clone https://github.com/mozilla-l10n/bedrock-l10n locale`   
`python build.py`   

This will build all the templates into individual directories in the `site` dir, one directory for each language. The templates and static files are in the `start-page` directory.
