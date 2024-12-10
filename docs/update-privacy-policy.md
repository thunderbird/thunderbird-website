
# Updating the Privacy Policy

The [Thunderbird Privacy Policy](https://www.thunderbird.net/en-US/privacy/) is automatically generated and should not be edited by hand.

Here is the workflow for updating it.


## Pull the latest and create a new branch

```bash
git checkout master
git pull
git checkout -b chore/update-legal
```

## Download the latest legal documents

Run the following:

```bash
python build-site.py  --downloadlegal
```

This automatically downloads the Privacy Policy and generates the corresponding HTML file.

## Commit and push

You do not have to include the date of the update, but you can find it at the top of the generated file (`sites/www.thunderbird.net/includes/privacy/privacy-desktop.html`).

```bash
git commit -am 'updated legal docs to 2024-12-09'
git push -u origin chore/update-legal
```


## Create a Pull Request

Make sure to tag another member of the Services Team for review.
