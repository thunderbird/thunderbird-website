
# Updating the Privacy Policy

The [Thunderbird Privacy Policy](https://www.thunderbird.net/en-US/privacy/) is automatically generated and should not be edited by hand.

To update it, you will:
1. Create a new branch.
2. Run the build tool with the `--downloadlegal` option.
3. Commit the changes.
3. Create a Pull Request.


Here is an example workflow.


## Pull the latest and create a new branch

Assuming you have already cloned the `thunderbird-website` repo:

```bash
git checkout master
git pull
git checkout -b chore/update-legal
```

## Download the latest legal documents

In order to run the `build-site.py` script, follow the basic setup instructions for thunderbird-website found in the main [README.md](../README.md##Dependencies).

With the dependencies installed, run the following:

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
