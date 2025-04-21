# Updating the About Us Page

## Adding a new staff member

The list of staff members can be found at [/about](https://www.thunderbird.net/en-US/about/) on the website.

To add a new staff member, you only need to:

- add the headshot image files
- update the markup in the About Us template

### Headshots

When exporting a staff member's headshot from a photo editing tool, make sure to create two versions: one at 1x resolution and another at 2x resolution.

Follow these naming convention:

- 1x: `roc.png`
- 2x: `roc-high-res.png`

Note: The high resolution naming convention deviates from the industry standard "@2x".

Save both to `media/img/thunderbird/staff/`.

#### Generating compressed images

From the root of the `thunderbird-website` repo, create compressed versions of the images with the following command:

```bash
python tools/compress_assets.py -r -o media/img/thunderbird/staff/
```

This will search recursively (`-r`) and overwrite (`-o`) previously compressed files.

### Markup

Edit the file `sites/www.thunderbird.net/about/index.html`

Find the appropriate section

Add the new staff member using the `job_block` macro:

```jinja
{{ job_block(_('Sr. Software Engineer, Desktop Engineering'), 'Roc', high_res_img('thunderbird/staff/roc.png', scale='2x', alt_formats=('webp',))) }}
```

This macro produces the appropriate markup, including the `<picture>` element.
