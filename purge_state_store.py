"""Store purge state in Git with a compare-and-swap on one ref.

The caller supplies the Git workspace, remote, fully qualified ref, and
document path. This module does not choose a production branch, read
credentials, or decide that a deployment is ready.

``read_purge_state`` returns one snapshot: the ref's commit and the document
stored in that same commit. A command, authentication, or transport failure
is an error. Confirmed absence of the ref is the only initialization result.

``write_purge_state`` encodes the supplied state before it publishes.
Initialization pushes a root commit with an explicit expected-absence
lease. An update pushes a direct child of the expected revision only when
the remote ref still points at that exact commit. A stale revision or a
creation race raises ``PurgeStateConflict`` and is not fetched, rebased,
merged, or replayed. Hook, permission, and transport failures are store
errors. The caller's refs, fetch head, index, branch, working tree, and
configuration are left unchanged.

Publication uses the supplied workspace as its working directory, so a
relative remote URL resolves from that workspace. The temporary repository
used for the push includes the caller's configuration file by absolute
path. Relative ``include.path`` entries therefore stay relative to the
caller's file, and remote-tracking updates stay in the temporary
repository.

``GIT_ASKPASS`` and ``GIT_SSH_COMMAND`` are passed through when the caller
set them. When either is absent, the variable is left unset so Git can
apply the command configured in the repository, such as ``core.askPass``
or ``core.sshCommand``. Terminal prompts are disabled for every command.
"""

import math
import os
import signal
import subprocess
import tempfile
import time
from typing import NamedTuple

from cache_purge import PurgeState, decode_purge_state, encode_purge_state


_DEFAULT_TIMEOUT = 30
_PUSH_FLAG_BYTES = b"*!=+- "


class PurgeStateStoreError(Exception):
    """A purge-state Git command failed or the stored document is unusable."""


class PurgeStateConflict(PurgeStateStoreError):
    """The remote ref was not the expected revision, so nothing was published."""


class PurgeStateAbsent(NamedTuple):
    """The state ref was confirmed not to exist."""


class PurgeStateSnapshot(NamedTuple):
    """A purge state and the commit that contains that exact document."""

    revision: str
    state: PurgeState


def read_purge_state(workspace, remote, ref, path, timeout=_DEFAULT_TIMEOUT):
    """Return the ref's purge state and commit, or confirmed absence.

    The revision and document come from the same fetched commit. A missing,
    malformed, or contradictory document is a store error, as is a command
    failure. None of those is reported as absence.
    """
    _validate_request(workspace, remote, ref, path, timeout)
    current = _remote_revision(workspace, remote, ref, timeout)
    if current is None:
        return PurgeStateAbsent()
    _fetch_commit(workspace, remote, current, timeout)
    payload = _document(workspace, current, path, timeout)
    try:
        state = decode_purge_state(payload)
    except ValueError:
        raise PurgeStateStoreError("purge state document is invalid") from None
    return PurgeStateSnapshot(current, state)


def write_purge_state(workspace, remote, ref, path, expected_revision, state, timeout=_DEFAULT_TIMEOUT):
    """Publish ``state`` only if the remote ref still has ``expected_revision``.

    ``expected_revision`` is None only for the initial commit. Creation uses
    an expected-absence lease, so the ref must still be absent. Any other
    revision must be the full commit named by the caller, and the new commit
    is its direct child. The publish is still attempted when the document
    bytes are unchanged. Returns the new commit. A conflict leaves the remote
    ref where it was.
    """
    _validate_request(workspace, remote, ref, path, timeout)
    if expected_revision is not None:
        _validate_revision(expected_revision)
    payload = encode_purge_state(state).encode("utf-8")
    if expected_revision is None:
        revision = _commit(workspace, None, path, payload, timeout)
        _require_root(workspace, revision, timeout)
        _push(workspace, remote, ref, revision, "", timeout)
        return revision
    if _remote_revision(workspace, remote, ref, timeout) != expected_revision:
        raise PurgeStateConflict("purge state ref is not the expected revision")
    _fetch_commit(workspace, remote, expected_revision, timeout)
    revision = _commit(workspace, expected_revision, path, payload, timeout)
    _require_parent(workspace, revision, expected_revision, timeout)
    _push(workspace, remote, ref, revision, expected_revision, timeout)
    return revision


def _validate_request(workspace, remote, ref, path, timeout):
    """Reject arguments that cannot name one workspace, remote, ref, and path."""
    if not isinstance(workspace, str) or workspace == "":
        raise ValueError("workspace must be a Git directory")
    if (
        not isinstance(remote, str)
        or remote == ""
        or remote.startswith("-")
        or any(character in remote for character in "\n\r\x00")
    ):
        raise ValueError("remote must be a Git remote")
    if (
        not isinstance(ref, str)
        or not ref.startswith("refs/")
        or ref.endswith("/")
        or "//" in ref
        or ".." in ref
        or "@{" in ref
        or any(character in ref for character in " \t\n\r~^:?*[\\")
    ):
        raise ValueError("state ref must be a fully qualified Git ref")
    if not isinstance(path, str) or path.startswith("/") or "\\" in path or "," in path:
        raise ValueError("state path must be a relative repository path")
    if any(part in ("", ".", "..") for part in path.split("/")):
        raise ValueError("state path must be a relative repository path")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout < 0
    ):
        raise ValueError("timeout must be a finite, non-negative number of seconds")


def _validate_revision(revision):
    """Reject anything other than a full Git commit id."""
    if not isinstance(revision, str) or len(revision) not in (40, 64):
        raise ValueError("expected revision must be a full commit id")
    if any(character not in "0123456789abcdef" for character in revision):
        raise ValueError("expected revision must be a full commit id")


def _remote_revision(workspace, remote, ref, timeout):
    """Return the remote ref's commit, or None when that ref is absent."""
    code, stdout, _stderr = _run(workspace, ["ls-remote", remote, ref], timeout)
    if code != 0:
        raise PurgeStateStoreError("purge state command failed")
    found = None
    for line in stdout.splitlines():
        revision, separator, name = line.partition(b"\t")
        if separator != b"\t" or name.decode("utf-8", "replace") != ref:
            continue
        if found is not None:
            raise PurgeStateStoreError("purge state command failed")
        found = revision.decode("utf-8")
        _validate_revision(found)
    return found


def _fetch_commit(workspace, remote, revision, timeout):
    """Fetch one commit without writing FETCH_HEAD or a remote-tracking ref."""
    code, _stdout, _stderr = _run(
        workspace,
        [
            "fetch",
            "--no-write-fetch-head",
            "--no-tags",
            "--no-recurse-submodules",
            "--no-auto-gc",
            "--refmap=",
            remote,
            revision,
        ],
        timeout,
    )
    if code != 0 or _run(workspace, ["cat-file", "-e", revision], timeout)[0] != 0:
        raise PurgeStateStoreError("purge state command failed")


def _document(workspace, revision, path, timeout):
    """Return the document text stored at ``path`` in ``revision``."""
    if _run(workspace, ["cat-file", "-e", revision], timeout)[0] != 0:
        raise PurgeStateStoreError("purge state command failed")
    if _run(workspace, ["cat-file", "-e", f"{revision}:{path}"], timeout)[0] != 0:
        raise PurgeStateStoreError("purge state document is missing")
    code, stdout, _stderr = _run(workspace, ["cat-file", "blob", f"{revision}:{path}"], timeout)
    if code != 0:
        raise PurgeStateStoreError("purge state command failed")
    try:
        return stdout.decode("utf-8")
    except UnicodeDecodeError:
        raise PurgeStateStoreError("purge state document is invalid") from None


def _commit(workspace, parent, path, payload, timeout):
    """Write a commit for ``payload`` without touching the caller's index."""
    with tempfile.TemporaryDirectory(prefix="purge-state-") as temporary:
        index = os.path.join(temporary, "index")
        if parent is None:
            _require_ok(workspace, ["read-tree", "--empty"], timeout, index)
        else:
            _require_ok(workspace, ["read-tree", parent], timeout, index)
        code, stdout, _stderr = _run(workspace, ["hash-object", "-w", "--stdin"], timeout, input_bytes=payload)
        if code != 0:
            raise PurgeStateStoreError("purge state command failed")
        blob = stdout.decode("utf-8").strip()
        _require_ok(
            workspace,
            ["update-index", "--add", "--cacheinfo", f"100644,{blob},{path}"],
            timeout,
            index,
        )
        code, stdout, _stderr = _run(workspace, ["write-tree"], timeout, index=index)
        if code != 0:
            raise PurgeStateStoreError("purge state command failed")
        tree = stdout.decode("utf-8").strip()
        command = ["commit-tree", tree]
        if parent is not None:
            command.extend(["-p", parent])
        message = f"chore(cache-purge): update deployment state\n\n{time.time_ns()}\n".encode("utf-8")
        code, stdout, _stderr = _run(workspace, command, timeout, input_bytes=message)
        if code != 0:
            raise PurgeStateStoreError("purge state command failed")
        revision = stdout.decode("utf-8").strip()
        _validate_revision(revision)
        return revision


def _require_root(workspace, revision, timeout):
    """Reject an initialization commit that already has a parent."""
    if _run(workspace, ["rev-parse", "-q", "--verify", f"{revision}^"], timeout)[0] == 0:
        raise PurgeStateStoreError("purge state command failed")


def _require_parent(workspace, revision, parent, timeout):
    """Reject an update that is not a direct child of the expected revision."""
    code, stdout, _stderr = _run(workspace, ["rev-parse", "-q", "--verify", f"{revision}^"], timeout)
    if code != 0 or stdout.decode("utf-8").strip() != parent:
        raise PurgeStateStoreError("purge state command failed")


def _push(workspace, remote, ref, revision, expected, timeout):
    """Publish ``revision`` only when the remote ref still has ``expected``.

    An empty ``expected`` leases the ref's absence. Any other value leases
    that exact commit. The push runs against a private Git directory that
    includes the caller's configuration, so a named remote cannot update
    the caller's remote-tracking refs.
    """
    command = [
        "-c",
        "gc.auto=0",
        "push",
        "--porcelain",
        "--no-recurse-submodules",
        f"--force-with-lease={ref}:{expected}",
        remote,
        f"{revision}:{ref}",
    ]
    code, stdout, _stderr = _push_in_private_repository(workspace, command, timeout)
    _raise_for_push(code, stdout)


_CONFLICT_REASONS = (b"stale info", b"non-fast-forward", b"fetch first")


def _raise_for_push(code, stdout):
    """Distinguish a compare-and-swap refusal from every other push failure."""
    records = _porcelain(stdout)
    if code == 0 and records and all(flag in {"*", " "} for flag, _reason in records):
        return
    reasons = [reason for flag, reason in records if flag == "!"]
    if reasons and all(reason in _CONFLICT_REASONS for reason in reasons):
        raise PurgeStateConflict("purge state ref is not the expected revision")
    raise PurgeStateStoreError("purge state command failed")


def _porcelain(stdout):
    """Return ``(flag, reason)`` pairs, ignoring the line that names the remote."""
    records = []
    for line in stdout.splitlines():
        if not line or line[0] not in _PUSH_FLAG_BYTES:
            continue
        reason = None
        if b"(" in line and line.endswith(b")"):
            reason = line[line.rfind(b"(") + 1:-1]
        records.append((chr(line[0]), reason))
    return records


def _push_in_private_repository(workspace, args, timeout):
    """Push from ``workspace`` without writing its refs or configuration.

    The private repository includes the caller's config file by absolute
    path, so relative includes keep resolving beside that file. ``-C``
    makes a relative remote URL resolve from the workspace. Remote-tracking
    refs and the work tree used by this command stay in the temporary
    directory. Hooks default to the caller's hook directory, and a
    ``core.hooksPath`` in the included configuration replaces that default.
    """
    with tempfile.TemporaryDirectory(prefix="purge-state-") as temporary:
        git_dir = os.path.join(temporary, "repository.git")
        code, _stdout, _stderr = _run(None, ["init", "-q", "--bare", git_dir], timeout)
        if code != 0:
            raise PurgeStateStoreError("purge state command failed")
        hooks = _git_path(workspace, "hooks", timeout)
        _write_private_config(
            git_dir,
            _git_path(workspace, "config", timeout),
            hooks if os.path.isdir(hooks) else None,
        )
        alternate = os.path.join(git_dir, "objects", "info", "alternates")
        os.makedirs(os.path.dirname(alternate), exist_ok=True)
        with open(alternate, "w", encoding="utf-8") as handle:
            handle.write(_git_path(workspace, "objects", timeout) + "\n")
        return _run(workspace, args, timeout, git_dir=git_dir, work_tree=os.path.join(temporary, "worktree"))


def _write_private_config(git_dir, caller_config, hooks):
    """Point a private repository at the caller's configuration and hooks."""
    lines = []
    if hooks is not None:
        lines.extend(["[core]", f"\thooksPath = {_quote_config(hooks)}"])
    lines.extend([
        "[include]",
        f"\tpath = {_quote_config(caller_config)}",
        "[core]",
        "\tbare = true",
        "",
    ])
    with open(os.path.join(git_dir, "config"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _quote_config(value):
    """Quote one Git configuration value without interpreting it."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _require_ok(workspace, args, timeout, index):
    """Run one index command and hide its output."""
    if _run(workspace, args, timeout, index=index)[0] != 0:
        raise PurgeStateStoreError("purge state command failed")


def _git_path(workspace, name, timeout):
    """Return an absolute path inside the workspace's Git directory.

    ``git rev-parse --git-path`` may print a path relative to the workspace.
    A relative workspace is resolved from the current directory without
    changing that directory.
    """
    code, stdout, _stderr = _run(workspace, ["rev-parse", "--git-path", name], timeout)
    if code != 0:
        raise PurgeStateStoreError("purge state command failed")
    path = stdout.decode("utf-8").strip()
    if not os.path.isabs(path):
        path = os.path.abspath(os.path.join(workspace, path))
    return path


def _run(workspace, args, timeout, index=None, input_bytes=None, git_dir=None, work_tree=None):
    """Run one Git command without a shell, prompt, or inherited Git directory.

    Supplied ``GIT_ASKPASS`` and ``GIT_SSH_COMMAND`` values are kept.
    Omitting either one leaves that variable unset so a configured
    ``core.askPass`` or ``core.sshCommand`` still applies.
    ``GIT_TERMINAL_PROMPT=0`` prevents Git from prompting.
    """
    env = os.environ.copy()
    for name in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_PREFIX",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE",
    ):
        env.pop(name, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LC_ALL"] = "C"
    if index is not None:
        env["GIT_INDEX_FILE"] = index
    if work_tree is not None:
        os.mkdir(work_tree)
        env["GIT_WORK_TREE"] = work_tree
    command = ["git"]
    if workspace is not None:
        command.extend(["-C", workspace])
    if git_dir is not None:
        command.extend(["--git-dir", git_dir])
    command.extend(args)
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
    except OSError:
        raise PurgeStateStoreError("purge state command failed") from None
    try:
        stdout, stderr = process.communicate(input_bytes, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise PurgeStateStoreError("purge state command timed out") from None
    return process.returncode, stdout, stderr
