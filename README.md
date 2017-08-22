# thunderbird-website

This repo contains the Thunderbird in-client Start page and the www.thunderbird.net website.
* The `prod` branch is used to update https://start.thunderbird.net and https://www.thunderbird.net.
* The `master` branch is used to update https://start-stage.thunderbird.net and https://www-stage.thunderbird.net.

Pushes occur automatically with each commit to github on either branch.

# Build Instructions

## Dependencies
```
pip install requirements.txt
git clone https://github.com/mozilla-l10n/bedrock-l10n locale
git clone https://github.com/thundernest/thunderbird-notes.git thunderbird_notes
git clone https://github.com/mozilla/product-details-json
```

## Run Build
There are two build scripts, one for the [start page](https://start.thunderbird.net/) and one for [www.thunderbird.net](https://www.thunderbird.net/)

* `python build-start.py` for the start page.
** This builds into the `site` directory.
* `python build-site.py` for thunderbird.net.
** This builds into the thunderbird.net directory.

## Automated Builds
In general, you only need to manually build the website for testing and development purposes. Webhooks on each of the repositories trigger
automatic rebuilds when:

* https://github.com/thundernest/thunderbird-notes.git (Release Notes) are updated.
* https://github.com/mozilla/product-details-json (Product Details) are updated. Product details contains data on what versions of Thunderbird exist.
** Currently stage doesn't update automatically from product-details changes.

Both of these update frequently enough(multiple times per week) that independent updates for localization are not necessary. Any triggered
update will always use the most recent data available from all sources. If changes to one of the above repos don't produce any change in the built files, no actual
update of the web server will occur.

# Manual Site Updates

Occasionally you need to update the site manually, for example to move changes made to this repo to stage and production, or because the automation
failed, or any reason like that. You'll need to either login to the control node as described in the https://github.com/thundernest/thundernest-ansible documentation
or check out and setup the thundernest-ansible scripts on your local machine. That is also covered in the documentation for [thundernest-ansible](https://github.com/thundernest/thundernest-ansible).

Assuming you are logged into the control node or have thundernest-ansible set up:

For stage:
```
cd thundernest-ansible
source files/secrets.sh
ansible-playbook plays/website-build.yml
```

For prod:
```
cd thundernest-ansible
source files/secrets.sh
ansible-playbook --extra-vars="branch=prod" plays/website-build.yml
```

The [website-build.yml](https://github.com/thundernest/thundernest-ansible/blob/master/plays/website-build.yml) ansible script performs complete builds of the website, including both the start
page and thunderbird.net itself.

* Completed and pushed builds from automation or the [website-build.yml](https://github.com/thundernest/thundernest-ansible/blob/master/plays/website-build.yml) script are checked into https://github.com/thundernest/tb-website-builds -- the `master` branch represents the files currently on stage, and the `prod` branch represents the files currently on the live version of thunderbird.net.
