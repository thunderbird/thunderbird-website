# updates.thunderbird.net (UTN)

What's New and Donation Appeal pages are hosted on `updates.thunderbird.net`.

## Setup

### Install the dependencies

Follow the basic setup instructions in [README.md](../README.md##Dependencies). For [compressed image assets](#creating-compressed-image-assets), also run:

```bash
uv sync --group image
```

### Run the dev server

```bash
uv run build-site.py --watch --updates --debug --enus
```

This builds for en-US only and rebuilds when you change site files. The output should look like:

```
Rendering updates in en-US only.
Building pages for en-US...
Updating website when templates, CSS, or JS are modified. Press Ctrl-C to end.
HTTP Server running on: http://localhost:8000
```

The default address is `http://localhost:8000` (change with `--port`).


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

To generalize, we created the following directory paths for our files:

| Type | Location |
|------|----------|
| Jinja template | `/sites/updates.thunderbird.net/thunderbird/<release>/<appeal-date>/` |
| SVGs | `/media/svg/<page-type>/<appeal-date>` |
| Images | `/media/img/thunderbird/<page-type>/<appeal-date>` |

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
'appeal-jul26-style': ['less/appeals/jul26.less'],
```

**Restart the dev server after editing `settings.py`.**

#### Images

When exporting from Figma or Zeplin, export two versions: 1x and 2x resolution. Name them using the `-high-res` suffix (not the industry-standard `@2x`):

- 1x: `forest-roc.png`
- 2x: `forest-roc-high-res.png`

Save both to the appropriate image directory (see [Where to put files](#where-to-put-files)).

#### Creating compressed image assets

Run [tools/compress_assets.py](../tools/compress_assets.py) whenever you add or update `.png`/`.jpg` raster images. This is not needed for SVGs.

```bash
python tools/compress_assets.py -r -o media/img/thunderbird/appeal/mycoolappeal/
```

The `-r` flag searches recursively and `-o` overwrites previously compressed files.

## Working with Jinja templates

### Linking the compiled CSS

The compiled CSS filename is based on the key you added to the `UPDATES_CSS` dict. For example, a key of `'appeal-jul26-style'` compiles to `css/appeal-jul26-style.css`. Link it in your template via the `base_css` block using the `static()` helper:

```jinja
{% block base_css %}
  <link href="{{ static('css/appeal-jul26-style.css') }}" rel="stylesheet" type="text/css"/>
{% endblock %}
```

### Using the `high_res_img()` helper

The `high_res_img()` helper renders a `<picture>` element with automatic `srcset` for the `-high-res` variant. Pass the path to the **1x** version -- the helper finds the 2x version automatically.

Use the `alt_formats` parameter to let the browser use compressed formats (webp, avif) when available:

```jinja
{{ high_res_img('thunderbird/appeal/dec24/forest-roc.png', {'alt': _('')}, alt_formats=('webp', 'avif')) }}
```

### Donation Button

The reusable donation button macro is in `includes/macros/donate-button.html`. Import it after the `extends`:

```jinja
{% from 'includes/macros/donate-button.html' import donate_button with context %}
```

Define the URL generation variables near the top of your template. Confirm `fru_form_id` and `utm_campaign` values with the Marketing and Communications team:

```jinja
{% set fru_form_id = fru_form_id|default('jul26') %}
{% set utm_campaign = utm_campaign|default('jul26_appeal') %}
{% set donation_base_url = donation_base_url|default(url('updates.140.appeal.jul26a.donate')) %}
```

The `donation_base_url` URL key (e.g. `updates.140.appeal.jul26a.donate`) is generated automatically from your entry in `APPEAL_DONATE_PAGES` -- you don't need to add it to `URL_MAPPINGS` manually.

Call the macro where you want the button:

```jinja
<section id="donate-button-container">
  {{ donate_button(form_id=fru_form_id, campaign=utm_campaign, base_url=donation_base_url) }}
</section>
```

### Localization

All user-facing text must be wrapped for translation using one of two methods:

- **`_()`** for short strings:

```jinja
<p class="closing-text">{{ _('The Thunderbird Team') }}</p>
```

- **`{% trans %}`** blocks for longer text:

```jinja
{% trans trimmed %}
  Meet Thunderbird, the <strong>email and productivity</strong> app that maximizes your freedoms.
{% endtrans %}
```

HTML tags are allowed inside translatable strings but should be minimized -- volunteer translators may accidentally break them. Always translate `aria-label` and `alt` text too:

```jinja
<h1 id="appeal-heading" aria-label="{{ _('Help Keep Thunderbird Alive!') }}">
  {{ _('Help Keep <span>Thunderbird Alive</span>') }}
</h1>
```

See [l10n_tools/readme.md](../l10n_tools/readme.md) for extracting strings for translation.

### Accessibility

Use `aria-label` on interactive elements whose purpose isn't obvious from their text (e.g. icon-only buttons):

```jinja
<a id="donate-footer" class="btn btn-no-bg" aria-label="{{ _('Donate') }}"
   href="{{ donate_url(...) }}">
  <span aria-hidden="true" class="heart-svg">{{ svg('donate-heart') }}</span>
  {{ _('Donate') }}
</a>
```

Use `aria-hidden="true"` and empty `alt` on purely decorative images. Add meaningful `alt` text to all other images.

Test with a screen reader (macOS: VoiceOver; Linux: [Orca](https://wiki.mozilla.org/Screen_Reader_-_Orca)). If the reader doesn't pause between sentences, add a period.

### Updating the baked appeal redirect

Thunderbird uses a static appeal URL at `updates.thunderbird.net/thunderbird/appeal`. This is controlled by `UPDATES_REDIRECTS` in `settings.py`. When your appeal is ready to go live, update the `('thunderbird', 'appeal')` key to point to the new appeal's URL key.

Keys are tuples based on the URL path: `updates.thunderbird.net/thunderbird/release/sep25r` becomes `('thunderbird', 'release', 'sep25r')`. Values are dot-separated URL keys: `updates.release.appeal.sep25r`.

## A/B Testing Appeal Variants

Rather than duplicating templates for each variant, appeal templates use Jinja2 block inheritance. A variant only contains the parts that differ.

### How it works

The base template (typically the "a" variant) wraps variable content in named blocks (`{% block appeal_headline %}`, `{% block appeal_body %}`). Variants `{% extends %}` the base and override only those blocks. Everything else is inherited.

The [starter template](../sites/updates.thunderbird.net/includes/_template/basic-page.html) already has these blocks.

### Creating an A/B variant

Example: campaign `jul26a` exists, you want a `jul26b` variant with a different headline.

#### 1. Ensure the base template has blocks

If you copied from the starter template, the blocks are already there. Otherwise, wrap the relevant sections:

```jinja
{# jul26a/index.html -- the base template #}
{% block content %}
  <section id="appeal-body">
    {% block appeal_headline %}
    <h1 id="appeal-heading" aria-label="{{ _('Original Headline') }}">
      {{ _('Original <span>Headline</span>') }}
    </h1>
    {% endblock %}

    <div id="appeal-letter" class="letter-container font-xl">
      <section id="donate-button-container">
        {{ donate_button(...) }}
      </section>
      <div id="letter-contents">
        {% block appeal_body %}
        <p>{{ _('Body text here.') }}</p>
        {% endblock %}
        {# The heart SVG, closing text, etc. live outside the block -- variants inherit them. #}
        <div class="heart-container">...</div>
        <p class="closing-text">{{ _('The Thunderbird Team') }}</p>
      </div>
    </div>
  </section>
{% endblock %}
```

#### 2. Create the variant file

`jul26b/index.html` only sets its UTM parameters and overrides the blocks that differ:

```jinja
{# jul26b/index.html -- only the headline differs #}
{% set utm_content = utm_content|default('jul26b') %}
{% set donation_base_url = donation_base_url|default(url('updates.140.appeal.jul26b.donate')) %}

{% extends "thunderbird/140.0/jul26a/index.html" %}

{% block page_title %}{{ _('Alternative Headline') }}{% endblock %}
{% block appeal_headline %}
    <h1 id="appeal-heading" aria-label="{{ _('Alternative Headline') }}">
      {{ _('Alternative <span>Headline</span>') }}
    </h1>
{% endblock %}
```

Override `appeal_body` as well if the body copy differs. If only the UTM content changes, the file is even shorter -- just set the variables and extend the base.

#### 3. Register the variant in `settings.py`

Add the template path to `APPEAL_DONATE_PAGES`:

```python
APPEAL_DONATE_PAGES = [
    ...
    'thunderbird/140.0/jul26a/index.html',
    'thunderbird/140.0/jul26b/index.html',  # <-- add this
]
```

This single list drives everything: URL mappings are derived automatically (e.g. `updates.140.appeal.jul26b` and `updates.140.appeal.jul26b.donate`), and the builder auto-generates the `/donate/` subpage. You do not need to create `jul26b/donate/index.html` manually.

Restart the dev server after editing `settings.py`.

#### 4. Pick the winner

Once testing is complete, update `UPDATES_REDIRECTS` in `settings.py` to point the canonical appeal URL at the winning variant:

```python
UPDATES_REDIRECTS = {
    ('thunderbird', 'appeal'): 'updates.140.appeal.jul26b',
    ...
}
```

### Block reference

| Block | Wraps | Override when... |
|-------|-------|-----------------|
| `page_title` | HTML `<title>` | Variant has a different headline |
| `appeal_headline` | The `<h1>` heading | Testing different headlines |
| `appeal_body` | Body paragraphs | Testing different copy |
| `base_css` | CSS `<link>` | Variant uses a different stylesheet |
| `site_header` | Header area (illustration, gradient) | Fundamentally different layout |

Most A/B tests only need `page_title` and `appeal_headline`. If a variant has a completely different layout, make it a standalone template extending `includes/base/base.html` directly.

### How donate subpages work

Every appeal has a companion `/donate/` subpage. The appeal page (loaded inside Thunderbird) links to `/donate/`, which opens in the user's browser with the FundraiseUp modal active.

For every template in `APPEAL_DONATE_PAGES`, the builder auto-generates the donate subpage by re-rendering the appeal template with:

- `donation_base_url = None` -- triggers the FRU modal in-page instead of linking out
- `disable_donation_blocked_notice = False` -- shows the blocked-donation fallback notice

No manual donate files needed. A few pre-2025 legacy appeals (115.0/nov24, 115.0/dec24, 128.0/nov24, 128.0/dec24) still use hand-written donate files.

### Examples

| Variant | Relationship | File |
|---------|-------------|------|
| `dec25-2a` | Base template | `thunderbird/140.0/dec25-2a/index.html` |
| `dec25-2b` | Extends 2a, overrides headline | `thunderbird/140.0/dec25-2b/index.html` |
| `dec25-2c` | Extends 2a, overrides headline + body | `thunderbird/140.0/dec25-2c/index.html` |
| `nov25c` | Extends nov25b, changes only UTM params | `thunderbird/140.0/nov25c/index.html` |
