# thunderbird-website

This repo contains the Thunderbird in-client Start page and the [www.thunderbird.net](https://www.thunderbird.net/) website.
* The `prod` branch is used to update https://start.thunderbird.net and https://www.thunderbird.net.
* The `master` branch is used to update https://start-stage.thunderbird.net and https://www-stage.thunderbird.net.

# Build Instructions

## Dependencies
On Ubuntu, you would need to use apt-get instead of yum, and similarly for different package managers.

```
pip install -r requirements-dev.txt
git clone https://github.com/thundernest/thunderbird-notes.git thunderbird_notes
git clone -b production https://github.com/mozilla-releng/product-details.git
sudo yum install npm
sudo npm install -g less
```

If you need the localizations to display pages translated from English into other languages:

```
git clone https://github.com/thundernest/thunderbird.net-l10n.git locale
l10n_tools/compile.sh
```

## Docker
As an alternative, you can use [Docker](https://docker.com) for local development. You'll need docker already set-up, and the previously mentioned git repositories.

Once that is done, you'll need to pull down and build a modified apache config (which is done via an automated script), and build the docker containers:
```
python docker/apache/build_apache_config.py
sudo docker build -t thunderbird-website-build . -f website.dockerfile
sudo docker build -t thunderbird-website-apache . -f apache.dockerfile
```

You'll also need to set up some local dns entries in `/etc/hosts`:
```
127.0.0.1 start.thunderbird.test
127.0.0.1 www.thunderbird.test
```

After that, you can simply run `docker-compose up`, and visit [https://www.thunderbird.test](https://www.thunderbird.test). 

Optionally you can do local development against the start page, by running `docker-compose --profile startpage up`, and visiting [https://start.thunderbird.test](https://start.thunderbird.test).

**Note:** The docker container creates and uses a self-signed certificate, which will probably raise a warning on your browser. You can safely ignore this.

## Run Build

A basic build is `python build-site.py`.
It builds [www.thunderbird.net](https://www.thunderbird.net/) into the `thunderbird.net` directory by default.

There are additional arguments:

* `--startpage`
    * This builds the [start page](https://start.thunderbird.net/) into the `site` directory.
* `--enus`
    * This restricts builds to only the 'en-US' locale, for faster testing.
* `--debug`
    * This logs output for each locale built and some of the templates, used to make debugging easier.
* `--watch`
    * This starts an HTTP server on localhost port 8000, and watches the template and assets folders for changes and then does quick rebuilds.
    * Note that this only rebuilds when you modify a file. To add or remove files, you should start a new build.
* `--port`
    * Sets the port to be used for the localhost server. Default is 8000. Format: `--port 8000`.

* thunderbird.net templates are in the `website` directory, and start page in the `start-page` dir. Assets are shared and in the `assets` dir.

## View Website
To view the website for testing purposes, run `python build-site.py --watch`. This also works with the start page.

You can then navigate to: http://127.0.0.1:8000 to view the website. None of the apache redirects work in this mode, so you have to click your
desired locale manually in the browser, but the site should behave normally after that.

## Automated Builds
In general, you only need to manually build the website for testing and development purposes. Webhooks on each of the repositories trigger
automatic rebuilds when:

* https://github.com/thundernest/thunderbird-notes.git (Release Notes) are updated.
* https://github.com/mozilla-releng/product-details.git (Product Details) are updated. Product details contains data on what versions of Thunderbird exist.
    * Currently stage doesn't update automatically from product-details changes.

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

# Localization

You can contribute to content translation of www.thunderbird.net pages using [Pontoon](https://pontoon.mozilla.org/projects/thunderbirdnet/).

# Donation FAQ

The actual questions and answers part of the FAQ can be found in `./faq.py`. Make sure to include the `gettext` call, otherwise we won't be able to extract the strings for localization.