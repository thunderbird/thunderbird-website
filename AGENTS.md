# Localization Extraction Instructions for Agents

## Scope

Use these instructions for work under `l10n_tools/` and for locale extraction in `libs/locale`.

Read `l10n_tools/readme.md` before changing the workflow. Use `extract.sh` and `check_po_clobber.py` as the normal entry points. `merge.sh` and `linelength.py` are internal helpers.

## Safety Rules

- Treat `thunderbird-website`, `libs/locale`, and `libs/thunderbird_roadmaps` as separate Git repositories.
- Preserve unrelated changes and untracked files in every repository.
- Do not switch branches, restore files, delete files, or commit unless the user explicitly asks or approves it.
- Never push extraction results. When the extraction has no errors and all warnings are explained, tell the user which repositories and branches are ready for them to push.
- Creating the required local locale backup branch is permitted and does not switch the working branch. Do not push the backup branch.
- Never copy an old translation into a changed source string automatically.
- Never edit generated Roadmaps templates as the source of truth. Edit `libs/thunderbird_roadmaps/docs/`, then rebuild them.
- Stop and ask before extraction if tracked PO or POT changes already exist in `libs/locale` and their ownership is unclear.
- Keep temporary logs and generated review diffs outside the repositories when possible.

## Extraction Workflow

Run commands from the `thunderbird-website` repository root unless noted otherwise.

### 1. Inspect All Working Trees

Run:

```sh
git status --short --branch
git -C libs/locale status --short --branch
git -C libs/thunderbird_roadmaps status --short --branch
```

The website repository may contain the intended source changes. The locale repository must not contain unrelated tracked PO or POT changes. Untracked review files may remain, but do not modify or commit them.

### 2. Update Generated Source Templates

Identify whether the translatable source is generated from another repository.

For Roadmaps, inspect the Markdown source and regenerate the templates:

```sh
git -C libs/thunderbird_roadmaps diff --check
uv run build-site.py --roadmaps
git diff -- sites/roadmaps.thunderbird.net
```

Stop if the build fails. Confirm that the generated Android, Desktop, and iOS templates contain the intended current copy. Fix typos in `libs/thunderbird_roadmaps/docs/`, rebuild, and review again before extraction.

### 3. Verify the Locale Upstream and Create a Backup

Immediately before extraction, fetch the locale remote and verify that the current branch matches its upstream exactly:

```sh
git -C libs/locale fetch origin
git -C libs/locale branch --show-current
git -C libs/locale rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
git -C libs/locale rev-list --left-right --count HEAD...'@{upstream}'
```

The final command must report `0 0`. Stop if:

- The fetch fails.
- The locale repository is in detached HEAD state.
- The current branch has no upstream.
- The branch is ahead of or behind its upstream.

Do not pull, rebase, reset, or otherwise synchronize the locale repository automatically. Tell the user that `libs/locale` is not up to date and let them decide how to resolve it.

After the branch is verified, record the exact locale commit and create a timestamped local backup branch pointing to it:

```sh
LOCALE_BASE="$(git -C libs/locale rev-parse HEAD)"
BACKUP_BRANCH="backup/locales-$(date +%Y%m%d-%H%M%S)"
git -C libs/locale branch "$BACKUP_BRANCH" "$LOCALE_BASE"
git -C libs/locale show-ref --verify "refs/heads/$BACKUP_BRANCH"
printf 'Locale baseline: %s\n' "$LOCALE_BASE"
printf 'Locale backup branch: %s\n' "$BACKUP_BRANCH"
```

Stop if the backup branch cannot be created or verified. Keep both values in the same shell and include them in the final report. Do not switch to or push the backup branch.

### 4. Run Extraction

Capture the complete log outside the repository:

```sh
set -o pipefail
./l10n_tools/extract.sh 2>&1 | tee /tmp/thunderbird-l10n-extract.log
```

`extract.sh` must stop on the first error. Do not inspect or publish a partial extraction as though it succeeded. Review the log for errors and new warnings.

### 5. Confirm Source Coverage

Verify that several distinctive new or changed strings appear in the POT file:

```sh
rg -F "A distinctive new string" \
  libs/locale/templates/LC_MESSAGES/messages.pot
```

The clobber checker cannot detect a source file omitted by `babel.cfg`. Confirm source coverage separately.

### 6. Run the Clobber Checker

Run the default review gate:

```sh
uv run python l10n_tools/check_po_clobber.py \
  --repo libs/locale \
  --base "$LOCALE_BASE"
```

Interpret the output as follows:

- `ERROR` means an existing approved translation was definitely lost. Stop and investigate.
- `WARNING` means an existing translation changed, became fuzzy, disappeared, became obsolete, or may have an empty replacement. Compare it with the intended source changes.
- `INFO` means a genuinely new source string is untranslated. This is normally expected.

Warnings intentionally return exit status 1 by default. Do not report the command as broken merely because reviewed source changes produced warnings.

To inspect new strings too, run:

```sh
uv run python l10n_tools/check_po_clobber.py \
  --repo libs/locale \
  --base "$LOCALE_BASE" \
  --show-info
```

Only after every warning has been explained, run the explicit acceptance check:

```sh
uv run python l10n_tools/check_po_clobber.py \
  --repo libs/locale \
  --base "$LOCALE_BASE" \
  --fail-on error
```

This command must return 0 before recommending publication. It does not modify files or hide warnings.

### 7. Review the Git Diff

Run:

```sh
git -C libs/locale diff --stat
git -C libs/locale status --short
git -C libs/locale diff --check
```

Review the complete POT diff and representative PO files:

```sh
git -C libs/locale diff -- templates/LC_MESSAGES/messages.pot
git -C libs/locale diff -- de/LC_MESSAGES/messages.po
git -C libs/locale diff -- fr/LC_MESSAGES/messages.po
git -C libs/locale diff -- ja/LC_MESSAGES/messages.po
git -C libs/locale diff -- pl/LC_MESSAGES/messages.po
git -C libs/locale diff -- uk/LC_MESSAGES/messages.po
```

Expected changes include new empty translations, source-reference movement, metadata updates, and obsolete entries for intentional source changes.

Investigate existing translations becoming empty under an unchanged message identity, unexplained mass formatting changes, unrelated files, malformed entries, or changes much larger than the source update explains.

### 8. Validate Tooling and Output

If any localization tool changed, run:

```sh
uv run pytest tests/test_check_po_clobber.py
uv run flake8 \
  l10n_tools/check_po_clobber.py \
  l10n_tools/linelength.py \
  tests/test_check_po_clobber.py
bash -n l10n_tools/extract.sh l10n_tools/merge.sh
```

Run the full project test suite when website source generation or shared code changed:

```sh
uv run pytest
```

Do not attribute a pre-existing validation failure to the extraction without comparing the same check against the baseline version.

For Roadmaps, verify that representative rendered locales contain the expected new English fallback or translations and that layout remains usable.

## Starting Over

Do not discard generated locale changes without explicit user approval.

If the user approves and the tracked locale files were clean at the recorded baseline, restore only generated tracked PO and POT files:

```sh
git -C libs/locale restore --worktree -- '*.po' '*.pot'
```

Confirm afterward that unrelated and untracked files remain intact. Rebuild the source templates and perform a fresh extraction from the recorded baseline.

## Reporting Results

Report:

- The locale baseline commit.
- The local locale backup branch.
- The generated source files reviewed.
- The extraction command and whether it completed successfully.
- Checker error, warning, and info counts.
- The reason each warning category is accepted or unresolved.
- Diff size and any formatting anomalies.
- Tests and validation commands run.
- The final status of each nested Git repository.
- Anything intentionally left uncommitted or unpushed.

Do not describe warnings as harmless without tying them to a specific intended source change. Do not recommend publishing while checker errors or unexplained warnings remain.

If the final `--fail-on error` check returns 0 and all warnings are explained, tell the user that the extraction is ready for their final review, commit, and push. Provide concrete push commands using the actual current branch names for each affected repository. Never execute those push commands yourself.
