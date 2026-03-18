# thunderbird-website

This repo contains the Thunderbird in-client Start page, the [www.thunderbird.net](https://www.thunderbird.net/) website, and the updates / donation appeals website.
* The `prod` branch is used to update https://start.thunderbird.net, https://www.thunderbird.net, https://updates.thunderbird.net, and https://tb.pro.
* The `master` branch is used to update https://start-stage.thunderbird.net, https://www-stage.thunderbird.net, https://updates-stage.thunderbird.net, and https://stage.tb.pro.

Additional information can be found in our [readthedocs documentation](https://docs.thunderbird.net/en/latest/).

# Build Instructions

## Dependencies

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and make sure `npm` and `git` are available:

```shell
# Fedora/RHEL/CentOS
sudo dnf install npm git

# Ubuntu/Debian
sudo apt-get install npm git
```

Then run the setup script:

```shell
uv run pull-libs.py
```

This installs Python dependencies, clones the required library repos, and installs the LESS compiler.

If you need the localizations to display pages translated from English into other languages:

```shell
sudo yum install gettext
l10n_tools/compile.sh
```

## Maintenance

You can re-run `uv run pull-libs.py` to keep the library repositories up-to-date. For the locale library you'll need to
manually rerun the compile.sh script anytime you pull.

## Run Build

A basic build is `uv run build-site.py`.
It builds [www.thunderbird.net](https://www.thunderbird.net/) into the `thunderbird.net` directory by default.

There are additional arguments:

* `--all`
    * Builds all sites (main website, start page, updates, tb.pro, roadmaps) in one invocation.
* `--startpage`
    * This builds the [start page](https://start.thunderbird.net/) into the `site` directory.
* `--tbpro`
    * This builds the tbpro site into the `tb.pro` directory.
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
To view the website for testing purposes, run `uv run build-site.py --watch`. This also works with the start page.

You can then navigate to: http://127.0.0.1:8000 to view the website. None of the apache redirects work in this mode, so you have to click your
desired locale manually in the browser, but the site should behave normally after that.

## Automated Builds
In general, you only need to manually build the website for testing and development purposes. GitHub Actions automatically
builds and deploys when:

* This repository (`thunderbird-website`) is pushed to `master` (stage) or `prod` (production).
* https://github.com/thunderbird/thunderbird-notes.git (Release Notes) are updated (`master` triggers stage, `prod` triggers production).
* https://github.com/thunderbird/thunderbird.net-l10n.git (Localizations) are updated (`master` triggers stage).
* https://github.com/mozilla-releng/product-details.git (Product Details) are updated (`production` triggers production).

Any triggered build always uses the most recent data available from all sources. If changes don't produce any difference
in the built files, no commit is made to https://github.com/thunderbird/tb-website-builds (which serves as a record of the
static files that are deployed).

# Deployment

The websites are built inside a Docker container and deployed to AWS Fargate. The "Build and Deploy" workflow handles
the full pipeline: build from source, push to ECR, publish static files to `tb-website-builds`, and deploy via Pulumi + ECS.

**Manual deployment via GitHub UI:**
1. Go to [Actions](https://github.com/thunderbird/thunderbird-website/actions) → "Build and Deploy"
2. Click "Run workflow" and select the environment (`stage` or `prod`)

See the [deployment documentation](https://docs.thunderbird.net/en/latest/deployment.html) for more details.

# Localization

## For Contributors

You can contribute to content translation of www.thunderbird.net pages using [Pontoon](https://pontoon.mozilla.org/projects/thunderbirdnet/).

## For Developers

Most paths under `/thunderbird` path aren't localized. There's an override setting named `ALWAYS_LOCALIZE` that allows specific paths to be forwarded to the users locale.

# Donation FAQ

Donation FAQ entries are found in `sites/www.thunderbird.net/includes/faq.html`.

# Tests

There are several pytests located in `./tests`. To run the full test-suite, simply use `uv run pytest`.

# Calendar Generation

Calendar generation can be manually built by appending the option`--buildcalendar`. This queries our current calendar provider (Calendarific) and generates a `.ics` file per each locale specified in settings.py. For testing, you can limit this to just US by using the option `--enus`.
This option requires setting the `CALENDARIFIC_API_KEY=` environment variable. If you're using a paid plan you can also set `CALENDARIFIC_IS_FREE_TIER=false` to remove the sleep time between calls.
