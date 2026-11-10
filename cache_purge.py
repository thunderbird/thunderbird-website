"""Select hostnames affected by changes between two generated-file snapshots.

Paths in snapshots and rules are canonical repository-relative strings that
already use "/" separators, such as ``start.thunderbird.net/en-US/index.html``
or ``wsgi.py``. Callers normalize paths before passing them in. This module
does not rewrite separators, resolve ``.`` or ``..``, or interpret a path as a
filesystem location.

A rule path ending in "/" is a directory prefix. Any other rule path is an
exact file. Directory rules match only at a path boundary, so
``start.thunderbird.net/`` matches ``start.thunderbird.net/index.html`` and
does not match ``start.thunderbird.net-preview/index.html``. Every matching
rule contributes its hostnames. The function does not contain a production
hostname map.
"""

from collections.abc import Mapping, Sequence


def changed_hostnames(
    before: Mapping[str, bytes],
    after: Mapping[str, bytes],
    rules: Sequence[tuple[str, Sequence[str]]],
) -> set[str]:
    """Return the hostnames affected by paths that differ between snapshots.

    `before` and `after` map repository-relative paths to file bytes. A path
    counts as changed when its bytes differ, when it is only in `before`
    (deletion), or when it is only in `after` (addition). A rename is a
    deletion at the old path plus an addition at the new path.

    `rules` is a sequence of ``(path, hostnames)`` pairs. Identical snapshots,
    an empty rule list, and changed paths that match no rule produce an empty
    set. Hostnames are unique, in no particular order.
    """
    changed = {
        path for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    }
    affected = set()
    for rule_path, hostnames in rules:
        if any(_rule_matches(rule_path, path) for path in changed):
            affected.update(hostnames)
    return affected


def _rule_matches(rule_path, changed_path):
    """Return whether one changed path falls under one supplied rule."""
    if rule_path.endswith("/"):
        return changed_path.startswith(rule_path)
    return changed_path == rule_path
