# Localization tools

These tools extract translatable strings from the website, update the locale catalogs, and help catch translations that may have been lost during the update.

The usual entry points are:

- `extract.sh` extracts and merges strings.
- `check_po_clobber.py` reviews the result for translation loss.

`merge.sh` and `linelength.py` are internal helpers called by `extract.sh`; you normally do not need to run them directly.

## Requirements

Run the tools from a configured `thunderbird-website` checkout with:

- `uv` and the project dependencies installed.
- The gettext command-line tools, including `msgmerge`.
- `libs/locale` checked out as its own Git repository.
- `lessc` installed when regenerating the Roadmaps site.

Some older scripts in this directory also require GNU [CoreUtils](https://formulae.brew.sh/formula/coreutils) and [FindUtils](https://formulae.brew.sh/formula/findutils) on macOS.

## Step-by-step guide

Run these commands from the `thunderbird-website` repository root unless a step says otherwise.

### 1. Update and review the source content

Make sure the English copy is final before extracting it. A changed English string usually requires a new translation, even when the change looks small.

If the content comes from another repository, update that checkout first. Roadmaps content, for example, comes from `libs/thunderbird_roadmaps`.

Regenerate source-derived templates before extraction. For Roadmaps:

```sh
uv run build-site.py --roadmaps
git diff -- sites/roadmaps.thunderbird.net
```

Stop if the build fails. Review the generated templates and correct source typos before asking localizers to translate them.

### 2. Check the working trees

Review both repositories before generating locale changes:

```sh
git status --short
git -C libs/locale status --short
```

The website repository should contain only the source changes you intend to localize. The locale repository should have no existing tracked PO or POT changes. Untracked review files are not modified, but be careful not to include them in a later commit.

### 3. Record the locale baseline

The checker needs the exact locale commit from before extraction:

```sh
LOCALE_BASE="$(git -C libs/locale rev-parse HEAD)"
printf 'Locale baseline: %s\n' "$LOCALE_BASE"
```

Keep this variable in the same shell until the review is complete.

### 4. Extract and merge strings

```sh
./l10n_tools/extract.sh
```

This command:

1. Creates `libs/locale/templates/LC_MESSAGES/messages.pot` from the website templates.
2. Merges that template into every locale PO file without fuzzy matching.
3. Normalizes PO wrapping to avoid formatting-only diffs.

The script stops on the first error. Do not continue with a partial extraction.

The formatter processes the PO files that actually exist in `libs/locale`. There is no en-US PO catalog, so the source language is naturally skipped.

### 5. Confirm the expected strings were extracted

Inspect the POT file for a few distinctive new or changed strings:

```sh
rg -F "A distinctive new string" \
  libs/locale/templates/LC_MESSAGES/messages.pot
```

This catches missing `babel.cfg` coverage. A clean PO comparison cannot detect a source file that was never extracted.

### 6. Run the translation-loss checker

```sh
uv run python l10n_tools/check_po_clobber.py \
  --repo libs/locale \
  --base "$LOCALE_BASE"
```

The checker is read-only. It compares parsed PO entries from the baseline commit with the current working files and reports:

- `ERROR`: an existing approved translation became empty without its source string changing.
- `WARNING`: an existing translation became fuzzy, obsolete, disappeared, changed, or may have an empty replacement.
- `INFO`: a genuinely new source string is untranslated.

New strings are expected to be untranslated. Warnings often represent intentional copy changes, but they still need review. Errors should be treated as definite translation loss.

Warnings make the command return a failure status by default so they cannot pass unnoticed.

To list new untranslated strings as well:

```sh
uv run python l10n_tools/check_po_clobber.py \
  --repo libs/locale \
  --base "$LOCALE_BASE" \
  --show-info
```

After reviewing and accepting intentional source changes, rerun with:

```sh
uv run python l10n_tools/check_po_clobber.py \
  --repo libs/locale \
  --base "$LOCALE_BASE" \
  --fail-on error
```

This does not hide warnings or change any files. It only makes definite errors determine the exit status.

### 7. Review the Git diff

Start with the overall size and file list:

```sh
git -C libs/locale diff --stat
git -C libs/locale status --short
```

Then review the complete diff. It is also useful to inspect representative locales such as German, French, Japanese, Polish, and Ukrainian:

```sh
git -C libs/locale diff -- de/LC_MESSAGES/messages.po
git -C libs/locale diff -- fr/LC_MESSAGES/messages.po
git -C libs/locale diff -- ja/LC_MESSAGES/messages.po
```

Expected changes include new blank translations, updated source references, metadata updates, and obsolete entries for intentionally changed copy.

Stop and investigate unexplained mass changes, existing translations becoming empty, or unrelated files appearing in the diff.

### 8. Commit and publish

Commit only the intended PO and POT changes in `libs/locale`. Keep temporary diff files and other review artifacts out of the commit.

Use the localization repository's normal review and publishing process. Record any accepted checker warnings in the commit or PR description so reviewers know they were examined.

After the locale update is accepted, deploy the corresponding website source changes and verify representative languages on the rendered site.

## Starting over safely

If extraction produced a bad result and the locale repository was clean when you began, you can discard only the generated tracked PO and POT changes:

```sh
git -C libs/locale restore --worktree -- '*.po' '*.pot'
```

This is destructive to uncommitted PO and POT changes. Check `git -C libs/locale status --short` first, and do not run it if the locale repository contained work you need to preserve.

## What the checker does not do

The checker does not:

- Copy or repair translations automatically.
- Decide whether an English wording change is semantically safe.
- Prove that every intended source file was included by Babel.
- Replace manual diff review or rendered-page testing.

Translations often need language-specific word order, punctuation, or markup placement. The tool reports suspicious changes and leaves the decision to a human reviewer.
