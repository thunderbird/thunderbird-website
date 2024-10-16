# Updates.Thunderbird.Net (UTN)

The new home of our what's new and donation appeal pages!

## Getting Started

Follow the basic setup for thunderbird-website located in [README.md](../README.md). 

Don't forget to familiarize yourself with the template language [Jinja](https://jinja.palletsprojects.com/en/3.0.x/)!

Once that's setup and confirmed working you can start the dev server for UTN by running:

```bash
python build-site.py --watch --updates --debug --devmode
```

After running that the dev server will give you an address (usually `http://localhost:8000` unless you've changed the port.) You may also use the `--enus` option to only build English (US) pages.

## Folder Structure

For the most part you'll want to stick to either the `thunderbird` or `thunderbird-android` folders as those are the folders that get rendered by our custom static site generator. The `includes` folder is used for jinja includes, extends, and macros. 

For example, if you were making a what's new page for Thunderbird 400.0 ESR you would create your `index.html` at `sites/updates.thunderbird.net/thunderbird/400.0esr/whats-new/index.html`. 

If you're making an appeal attach it to the most up-to-date ESR unless the appeal is attached to a specific project. i.e. donation appeal for Thunderbird for Android would go `sites/updates.thunderbird.net/thunderbird-android/40.0/appeal`.

In the event we do something new and creative, use common sense and update this document!

For new assets follow the existing convention, any non-l10n images go in `media/img/appeal/<appeal>` or `media/img/whatsnew/<whatsnew>`. Likewise for svgs `media/svg/appeal/<appeal>` or `media/svg/whatsnew/<whatsnew>`. You can locale specific images by placing media in `media/l10n/<locale>/<path similar to img>` and using the `l10n_img` jinja helper function in your page.

## Creating A New Page

A copy-and-pastable template is included in [sites/updates.thunderbird.net/includes/_templates/basic-page.html](../sites/updates.thunderbird.net/includes/_template/basic-page.html).

Simply copy and paste that template to its new home. Once resettled, change the `active_page` jinja variable to match your page name in kebab-case, this will namespace your page for styling by giving you the class `page-<active_page>`. Additionally, the `page_title` and `page_desc` variable controls the rendered HTML page title and page description respectively.

## Compressing Assets

Unfortunately we don't compress assets automatically, you'll have to use the [tools/compress_assets.py](../tools/compress_assets.py) at least once. For that you'll need to install required dependencies in the project root:

```bash
cd ../
pip install -r requirements-image.txt
```

After which you'll be able to run the tool like:

```bash
cd ../
python tools/compress_assets.py -r media/img/thunderbird/appeal/mycoolappeal/
```

Which will compress any images inside `media/img/thunderbird/appeal/mycoolappeal/` recursively. Additionally, there's an overwrite existing converted images option with `-o`.

## L10N

Follow the instructions located in [l10n_tools/readme.md](../l10n_tools/readme.md) to compile and extract strings.