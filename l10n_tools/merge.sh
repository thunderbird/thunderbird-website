#!/bin/bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
locale_root="$script_dir/../libs/locale"
template="$locale_root/templates/LC_MESSAGES/messages.pot"

shopt -s nullglob
po_files=("$locale_root"/*/LC_MESSAGES/messages.po)

if (( ${#po_files[@]} == 0 )); then
  printf 'No locale catalogs found under %s\n' "$locale_root" >&2
  exit 1
fi

for po_file in "${po_files[@]}"; do
  locale_dir="$(dirname -- "$po_file")"
  printf '%s\n' "$locale_dir"
  (
    cd "$locale_dir"
    msgmerge -U --backup=off --no-fuzzy-matching --width=200 messages.po "$template"
  )
done
