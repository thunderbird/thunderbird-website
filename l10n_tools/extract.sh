#!/bin/bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

cd "$script_dir/.."
uv run pybabel extract -F babel.cfg -o libs/locale/templates/LC_MESSAGES/messages.pot .
cd "$script_dir"
bash merge.sh
uv run python linelength.py
