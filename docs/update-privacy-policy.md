
# Updating the Legal Documents

The following pages are automatically generated and should not be edited by hand:

* The [Thunderbird Privacy Policy](https://www.thunderbird.net/en-US/privacy/), from [mozilla/legal-docs](https://github.com/mozilla/legal-docs).
* The [Thunderbird Pro Privacy Policy](https://tb.pro/privacy) and [Terms of Service](https://tb.pro/terms), from [thunderbird/thunderbird-accounts](https://github.com/thunderbird/thunderbird-accounts).

The documents that are downloaded are listed in `builder.Legal.DOCUMENTS`.

Here is the workflow for updating them.

## Pull the latest and create a new branch

```bash
git checkout master
git pull
git checkout -b chore/update-legal
```

## Confirm latest version number for Thundermail policies

Go to https://github.com/thunderbird/thunderbird-accounts/tree/main/assets/legal and determine if the latest version in `settings.py` is still correct.

## Download the latest legal documents

Run the following:

```bash
python build-site.py  --downloadlegal
```

This automatically downloads the documents and generates the corresponding HTML files.

## Commit and push

You do not have to include the date of the update, but you can find it at the top of each generated file
(`sites/www.thunderbird.net/includes/privacy/privacy-desktop.html`, `sites/tb.pro/includes/legal/privacy.html`,
`sites/tb.pro/includes/legal/terms.html`).

```bash
git commit -am 'updated legal docs to 2024-12-09'
git push -u origin chore/update-legal
```


## Create a Pull Request

Make sure to tag another member of the Services Team for review.
