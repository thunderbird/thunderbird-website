# thunderbird-website

This repo contains the Thunderbird in-client Start page, the [www.thunderbird.net](https://www.thunderbird.net/) website, and the updates / donation appeals website.
* The `prod` branch is used to update https://start.thunderbird.net, https://www.thunderbird.net, and https://updates.thunderbird.net.
* The `master` branch is used to update https://start-stage.thunderbird.net, https://www-stage.thunderbird.net, and https://updates-stage.thunderbird.net.

Additional information can be found in our [readthedocs documentation](https://docs.thunderbird.net/en/latest/).

# Build Instructions

## Virtual Environment

Before you can install anything else you must ensure you have a python [virtual environment](https://docs.python.org/3/library/venv.html) setup for this project.

If you do not see a `venv` or `.venv` folder within thunderbird-website run the following commands which will create a 
virtual environment named `.venv`. These folders are local only and are never stored within git. 

The second line will activate the virtual environment within your current shell instance. This allows you to simply 
use `pip` or `python` without worrying about path issues.

```shell
# Install virtual environment
python -m venv .venv

# Activate the virtual environment for bash
source .venv/bin/activate
```

## Dependencies
On Ubuntu, you would need to use apt-get instead of yum, and similarly for different package managers.

```
pip install -r requirements-dev.txt
git clone https://github.com/thunderbird/thunderbird-notes.git libs/thunderbird_notes
git clone -b production https://github.com/mozilla-releng/product-details.git libs/product-details
sudo yum install npm
sudo npm install -g less
```

If you need the localizations to display pages translated from English into other languages:

```
git clone https://github.com/thunderbird/thunderbird.net-l10n.git libs/locale
l10n_tools/compile.sh
```

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
* `--buildcalendar`
    * This builds the holiday calendars. Normally this will build every locale, but you can restrict the build to just US by using the `--enus` options.
* `--downloadlegal`
    * This downloads the latest Thunderbird privacy policy document, renders it into html from markdown and puts it in the includes folder. 
    * You only need to run this when the document updates.

* thunderbird.net templates are in the `sites/www.thunderbird.net` directory, and start page in the `sites/start.thunderbird.net` dir. Assets are shared and in the `assets` dir.

## View Website
To view the website for testing purposes, run `python build-site.py --watch`. This also works with the start page.

You can then navigate to: http://127.0.0.1:8000 to view the website. None of the apache redirects work in this mode, so you have to click your
desired locale manually in the browser, but the site should behave normally after that.

## Automated Builds
In general, you only need to manually build the website for testing and development purposes. Webhooks on each of the repositories trigger
automatic rebuilds when:

* https://github.com/thunderbird/thunderbird-notes.git (Release Notes) are updated.
* https://github.com/mozilla-releng/product-details.git (Product Details) are updated. Product details contains data on what versions of Thunderbird exist.
    * Currently stage doesn't update automatically from product-details changes.

Both of these update frequently enough(multiple times per week) that independent updates for localization are not necessary. Any triggered
update will always use the most recent data available from all sources. If changes to one of the above repos don't produce any change in the built files, no actual
update of the web server will occur.

# Manual Site Updates

Occasionally you need to update the site manually, for example to move changes made to this repo to stage and production, or because the automation
failed, or any reason like that. You'll need to either login to the control node as described in the https://github.com/thunderbird/thundernest-ansible documentation
or check out and setup the thundernest-ansible scripts on your local machine. That is also covered in the documentation for [thundernest-ansible](https://github.com/thunderbird/thundernest-ansible).

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

The [website-build.yml](https://github.com/thunderbird/thundernest-ansible/blob/master/plays/website-build.yml) ansible script performs complete builds of the website, including both the start
page and thunderbird.net itself.

* Completed and pushed builds from automation or the [website-build.yml](https://github.com/thunderbird/thundernest-ansible/blob/master/plays/website-build.yml) script are checked into https://github.com/thunderbird/tb-website-builds -- the `master` branch represents the files currently on stage, and the `prod` branch represents the files currently on the live version of thunderbird.net.

# Localization

## For Contributors

You can contribute to content translation of www.thunderbird.net pages using [Pontoon](https://pontoon.mozilla.org/projects/thunderbirdnet/).

## For Developers

Most paths under `/thunderbird` path aren't localized. There's an override setting named `ALWAYS_LOCALIZE` that allows specific paths to be forwarded to the users locale.

# Donation FAQ

Donation FAQ entries are found in `sites/www.thunderbird.net/includes/faq.html`.

# Tests

There are several pytests located in `./tests`. To run the full test-suite, simply use the command `python3 -m pytest`.

# Calendar Generation

Calendar generation can be manually built by appending the option`--buildcalendar`. This queries our current calendar provider (Calendarific) and generates a `.ics` file per each locale specified in settings.py. For testing, you can limit this to just US by using the option `--enus`. 
This option requires setting the `CALENDARIFIC_API_KEY=` environment variable. If you're using a paid plan you can also set `CALENDARIFIC_IS_FREE_TIER=false` to remove the sleep time between calls.
