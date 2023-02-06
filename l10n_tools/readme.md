# l10n Tools
Various tools relating to l10n. 

If you're using Mac we recommend using [CoreUtils](https://formulae.brew.sh/formula/coreutils) and [FindUtils](https://formulae.brew.sh/formula/findutils) to ensure the bash scripts work correctly.

## Extraction
From this directory simply run:
`./extract.sh`

If you receive errors similar to: `mv: illegal option -t` or `find: -printf: unknown primary or operator`, then please see the above disclaimer about CoreUtils/FindUtils. You may need to temporarily modify the script to use `gmv`/`gfind`.  

## Import Wagtail Donation String
This is a temporary import script to seed the localization of the FAQ and Ways to Give page from give.thunderbird.net.

This script will first load the messages.pot template file, pull in the msgid keys, and compare that against each locale's `faq.po` and `django.po` file. If it finds a match it will merge it into thunderbird's locale `messages.po` file.

The localization for give.thunderbird.net is split into two different repos:
- https://github.com/mozilla-l10n/thunderbird-donate-content
- https://github.com/mozilla-l10n/donate-l10n

Pull those down (hint: by default the script looks in thunderbird-website/tmp), then extract the strings of the current thunderbird-website. Once that is done, run `import_wagtail_donation_script.py` from `l10n_tools/`.

To prevent any conflicts, make the Pontoon project private and then push any strings up to Thunderbird's locale repo.