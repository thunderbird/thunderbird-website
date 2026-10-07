from pathlib import Path

import polib


# This is a ridiculous hack to get line lengths back to what Pontoon expects,
# which avoids messy git diffs with unnecessary line length changes all over
# the .po files.

locale_root = Path(__file__).resolve().parents[1] / "libs" / "locale"

for po_path in sorted(locale_root.glob("*/LC_MESSAGES/messages.po")):
    po = polib.pofile(po_path, wrapwidth=200)
    po.save()
