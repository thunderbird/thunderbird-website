# updates.thunderbird.net (UTN)

What's New and Donation Appeal pages are hosted on `updates.thunderbird.net`.

## Setup

### Install the dependencies

Follow the basic setup instructions for thunderbird-website found in the main [README.md](../README.md##Dependencies).

There are extra dependencies for [creating compressed image assets](#creating-compressed-image-assets). Install them by running:

```bash
pip install -r requirements-image.txt
```

### Run the dev server

When you finish installing the dependencies, start the UTN dev server with:

```bash
python build-site.py --watch --updates --debug --devmode --enus
```

This command builds the site for a single locale (English US) and rebuilds the site when you make changes to the site files.

The output should look like this:

```
Rendering updates in en-US only.
Building pages for en-US...
Updating website when templates, CSS, or JS are modified. Press Ctrl-C to end.
HTTP Server running on: http://localhost:8000
```

The last line of the output shows you the address where you can view the site locally.

The default address is `http://localhost:8000`, though you can specify a different port with the `--port` option.


## A Donations Appeal Page

Let's look at the [December 2024 Donation Appeal](https://updates-stage.thunderbird.net/en-US/thunderbird/128.0/dec24/) page as an example.

The source for this page is `/sites/updates.thunderbird.net/thunderbird/128.0/dec24/index.html`.

It is built from the following:
- a [Jinja](https://jinja.palletsprojects.com/en/stable/templates/) template
- styles from one or more compiled [LESS](https://lesscss.org/) files
- high and normal resolution images in multiple formats: SVG, png, jpg, webp, and avif

If you are new to Jinja, read the ["Template Designer Documentation"](https://jinja.palletsprojects.com/en/stable/templates/) and keep it handy as you look through some of the existing whats-new and appeal pages.

### Where to put files

For an appeal page whose URL path will be `/en-US/thunderbird/128.0/dec24/`, the files are organized as follows:

The Jinja template is `/sites/updates.thunderbird.net/thunderbird/128.0/dec24/index.html`

The LESS file is at `/assets/less/appeals/dec24.less`

SVGs and raster images (e.g, `.png`, `.jpg`) go in different directories:
- SVGs go in `/media/svg/appeal/dec24`
- Raster images go in `/media/img/thunderbird/appeal/dec24`

(If this were a "what's new" page, those paths would have been something like `/media/svg/whatsnew/dec24` and `/media/img/thunderbird/whatsnew/dec24`.)

To generalize, we created the following directory paths:
- `/sites/updates.thunderbird.net/thunderbird/<release>/<appeal-date>/`
- `/media/svg/<page-type>/<appeal-date>`
- `/media/img/thunderbird/<page-type>/<appeal-date>`

In addition to following these conventions, some files (such as `.less` styles) require configuration. We'll take a look at each file type in the remainder of this section.

#### Templates

Generally, Jinja templates will go somewhere inside the `thunderbird` or `thunderbird-android` folders. These are the folders that get rendered by our custom static site generator.

Each appeal or what's new page will either be associated with a particular release or a particular project.

For example, if you were making a what's new page for Thunderbird 400.0 ESR you would create your `index.html` at `sites/updates.thunderbird.net/thunderbird/400.0esr/whats-new/index.html`.

Appeals are associated with the most recent ESR; the December 2024 appeal is associated with the `128.0` ESR, which gives us the file path `/sites/updates.thunderbird.net/thunderbird/128.0/dec24/index.html`

Lastly, an appeal may be attached to a specific project. For example, the donation appeal for Thunderbird for Android goes in `sites/updates.thunderbird.net/thunderbird-android/40.0/appeal`.

##### Creating A New Page

A copy-and-pastable template is included in [sites/updates.thunderbird.net/includes/_templates/basic-page.html](../sites/updates.thunderbird.net/includes/_template/basic-page.html).

Simply copy and paste that template to its new home. Once resettled, change the `active_page` Jinja variable at the top of the template to match your page name in kebab-case. For the December 2024 appeal, we specified the following:

```jinja
{% set active_page = "appeal-dec24" %}
```

This will namespace your page for styling by giving you the class `page-<active_page>`. Additionally, the `page_title` and `page_desc` variables controls the rendered HTML page title and page description respectively.

##### The `includes` folder

The `includes` folder is used for jinja includes, extends, and macros.

The `donation_button` macro is one that we'll look at more closely in a later section.

#### LESS files

Working with `.less` files involves two steps:
- Creating the `.less` file in the appropriate directory
- Telling the build tool about the new `.less` file.

Just like with templates and images, we follow a pattern. The December 2024 appeal `.less` file path is `/assets/less/appeals/dec24.less`

Once you've created this file, add an entry for it to the `UPDATES_CSS` dict in the `settings.py` file. This configures the build tool to compile your new `.less` file.

There should be several entries in `UPDATES_CSS`. Follow the established naming convention when adding a key; the value is the path to the new less file you've just created.

```py
'appeal-dec24-style': ['less/appeals/dec24.less'],
```

After making changes to `settings.py`, **you must restart the dev server.**

#### Images

When exporting an asset from a tool like Figma or Zeplin, make sure to export two versions: one at 1x resolution and another at 2x resolution.

Follow the following naming convention:
- 1x: `forest-roc.png`
- 2x: `forest-roc-high-res.png`

Note: The high resolution naming convention deviates from the industry standard "@2x".

Save both to the appropriate directory. For the December 2024 appeal, that's `/media/img/thunderbird/appeal/dec24`.

The December 2024 appeal did not use any SVGs. However, they would have been placed in this directory: `/media/svg/appeal/dec24`.


#### Creating compressed image assets

Unfortunately we don't compress assets automatically, you'll have to use the [tools/compress_assets.py](../tools/compress_assets.py) at least once.

You've already installed the dependencies. Now all you need to do is run the command:

```bash
cd ../
python tools/compress_assets.py -r -o media/img/thunderbird/appeal/mycoolappeal/
```

This will search recursively (`-r`) and overwrite (`-o`) previously compressed files.

This step is only necessary for raster images. Run the tool any time you add or update `.png` and `.jpg` files.

## Working in with Jinja templates

### Linking the compiled `.css`

The compiled `.css` filename will be based on the key you put in the `UPDATES_CSS` dict in `settings.py`.

For example, the entry for the December 2024 appeal is:
```py
'appeal-dec24-style': ['less/appeals/dec24.less'],
```

This tells the build tool to compile the styles to `css/appeal-dec24-style.css`.

To use the compiled CSS file:
- Declare a `base_css` block in your template.
- Create a `<link>` tag.
- In the `href`, call the `static()` helper, passing it the path to your compiled `.css` file.


Here's the result:

```jinja
{% block base_css %}
  <link href="{{ static('css/appeal-dec24-style.css') }}" rel="stylesheet" type="text/css"/>
{% endblock %}
```

### Using the `high_res_img()` helper

The `high_res_img()` helper renders a `<picture>` element that displays the image at the best resolution for the user's device.

Pass it the path to the *low resolution* version of your image. The helper function will automatically include the `-high-res` variant of your image in a `srcset` attribute.

```jinja
{{ high_res_img('thunderbird/appeal/dec24/forest-roc.png', {'alt': _('')}) }}
```

To reiterate, we have two versions of this image:
- 1x: `forest-roc.png`
- 2x: `forest-roc-high-res.png`

But we pass the 1x version to `high_res_img()`.

#### Specifying alternate image formats

In an earlier step, you produced compressed/optimized versions of your image assets.

You should allow the browser to use one of these alternate formats when possible.

Update the call to `high_res_img()`, passing the compressed file extensions in the `alt_formats` list:

```jinja
{{ high_res_img('thunderbird/appeal/dec24/forest-roc.png', {'alt': _('')}, alt_formats=('webp', 'avif')) }}
```

### Donation Button

A reusable donation button is defined in `includes/macros/donate-button.html`.

There are three steps to using it:

1. Import the macro
2. Define the variables for URL generation
3. Call the macro

#### Import the macro

First add the following to your template, after the `extends`:

```jinja
{% from 'includes/macros/donate-button.html' import donate_button with context %}
```

#### Define the variables for URL generation

Near the top of your Jinja template, declare the following variables:

```jinja
{% set fru_form_id = fru_form_id|default('eoy2024') %}
{% set utm_campaign = utm_campaign|default('dec24_appeal') %}
{% set donation_base_url = donation_base_url|default(url('updates.128.appeal.dec24.donate')) %}
```

Confirm the values for `fru_form_id` and `utm_campaign` with the Marketing and Communications team.

The `donation_base_url` variable comes from the `URL_MAPPINGS` dict in `settings.py`. You'll need to add to this dict each time you use the donate_button macro.

Here is the entry for the December 2024 appeal:

```py
'updates.128.appeal.dec24.donate': '/thunderbird/128.0/dec24/donate/',
```

***Make sure to restart the build tool after editing the `settings.py` file.***

#### Call the macro

Finally, call the macro where you'd like to display it:

```jinja
<section id="donate-button-container">
  {{ donate_button(form_id=fru_form_id, campaign=utm_campaign, base_url=donation_base_url) }}
</section>
```

After restarting the build tool and refreshing your browser, you should see the donation button on the page.

### Localization

All text in the Jinja template should be translated into the user's local language.

#### Specifying translatable strings

There are two ways to specify that a string should be translated.
You can wrap the string in one of the following:

- The `_()` function is used for shorter pieces of text.
- A `{% trans %}` block wraps longer strings.

Use `_()` for simple strings:

 ```jinja
 <p class="closing-text">{{ _('The Thunderbird Team') }}</p>
 ```

HTML tags are allowed inside a translatable string:

```jinja
<h1>
    {{ _('Help Keep <span>Thunderbird Alive</span>') }}
</h1>
```
When possible, avoid putting HTML tags inside a translatable string. One of our volunteer translators may accidentally change the tags, causing an error when building the site.

`aria-label` (and `alt` text) should be translated:

```jinja
<h1 id="appeal-heading" aria-label="{{ _('Help Keep Thunderbird Alive!') }}">
  {{ _('Help Keep <span>Thunderbird Alive</span>') }}
</h1>
```

The December 2024 appeal does not use `{% trans %}` blocks, but here is an example from the main `index.html`:

```jinja
{% trans trimmed %}
  Meet Thunderbird, the <strong>email and productivity</strong> app that maximizes your freedoms.
{% endtrans %}
```

#### Extracting strings for translation

Follow the instructions located in [l10n_tools/readme.md](../l10n_tools/readme.md) to compile and extract strings.

### Accessibility

Provide a label using the `aria-label` for interactive elements that assistive software may not understand (such as a close button).

This is an example from the November 2024 appeal page:

```jinja
<a id="donate-footer"
   class="btn btn-no-bg"
   aria-label="{{ _('Donate') }}"
   href="{{ donate_url(content='bottom_cta', campaign=utm_campaign, form_id=fru_form_id, base_url=donation_base_url, source=utm_source) }}">
  <span aria-hidden="true" class="heart-svg">{{ svg('donate-heart') }}</span>
  {{ _('Donate') }}
</a>
```


Use `aria-hidden="true"` for purely decorative content that should be ignored by assistive software:

```jinja
<aside id="illustration" aria-hidden="true">
  <div id="roc">
    {{ high_res_img('thunderbird/appeal/dec24/forest-roc.png', {'alt': _('')}, alt_formats=('webp', 'avif')) }}
  </div>
</aside>
```

Add `alt` text to images, except when the information is redundant or the image is purely decorative.

#### Using a Screen Reader

It's helpful to test the page using a screen reader.

On macOS, use the built-in `VoiceOver` screen reader.

For Linux, the [Orca](https://wiki.mozilla.org/Screen_Reader_-_Orca) screen reader is recommended by the Mozilla Wiki.

In particular, you may find that a screen reader does not pause adequately between sentences. Add a period (`.`) to remedy this.
