# Updating the About Us Page

## Adding a new staff member

The list of staff members can be found at [/about](https://www.thunderbird.net/en-US/about/) on the website.

To add a new staff member, you only need to:

- add the headshot image files
- update the markup in the About Us template

### Headshots

You can automatically generate cropped and compressed headshot images using the `tools/crop_staff_list.py` script.

To use it, make sure you've installed the image manipulation dependencies:

```bash
pip install -r requirements-image.txt
```

Add each new staff member's photo to `media/img/thunderbird/staff/uncropped/`. (This directory is gitignored.)

Follow this file naming convention: `<whatever> - <First Name> <Last Name>.whatever-extension`
(e.g. 97147377 - Melissa Autumn.jpg)

As necessary, specify origin points for cropping by addding `[Left|Center|Right,Top|Center|Bottom]` to the file name. (e.g. `97147377 - Melissa Autumn[Left,Bottom].jpg`.)

Then:

```bash
cd tools
python ./crop_staff_list.py
```

### Markup

Edit the file `sites/www.thunderbird.net/about/index.html`

Find the appropriate section

Add the new staff member using the `job_block` macro:

```jinja
{{ job_block(_('Sr. Software Engineer, Desktop Engineering'), 'Roc', high_res_img('thunderbird/staff/roc.png', scale='2x', alt_formats=('webp',))) }}
```

This macro produces the appropriate markup, including the `<picture>` element.
