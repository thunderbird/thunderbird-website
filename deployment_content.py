"""Read a generated-content directory into a path-to-bytes snapshot."""

import os
import stat


class ContentSnapshotError(Exception):
    """The artifact directory could not be read as one complete snapshot."""


def read_content_snapshot(root):
    """Return ``{relative path: exact bytes}`` for the regular files in ``root``.

    The caller must provide a completed, stable artifact directory. This
    function does not create an atomic filesystem snapshot. Paths are
    relative to ``root`` and use forward slashes. An empty directory
    returns an empty mapping. Empty subdirectories add no records.
    Filenames and bytes are preserved, including hidden files, binary
    content, and zero-byte files. Key order is not significant.

    ``root`` must name an existing directory and must not itself be a
    symbolic link. A symbolic link, a special file, or a traversal or
    read error fails the call. The failure follows neither a file link
    nor a directory link, does not block on a special file, and does not
    return a partial snapshot.
    """
    snapshot = {}
    _collect(_directory(root), "", snapshot)
    return snapshot


def _directory(root):
    """Return the artifact directory path, rejecting a link or non-directory."""
    try:
        path = os.fspath(root)
    except TypeError:
        raise ContentSnapshotError("content root must be an existing directory") from None
    if not isinstance(path, str) or path == "" or "\x00" in path:
        raise ContentSnapshotError("content root must be an existing directory")
    # A trailing slash would make lstat follow a directory link.
    candidate = os.path.normpath(path)
    try:
        mode = os.lstat(candidate).st_mode
    except OSError:
        raise ContentSnapshotError("content root must be an existing directory") from None
    if stat.S_ISLNK(mode):
        raise ContentSnapshotError("content snapshot cannot include a symbolic link")
    if not stat.S_ISDIR(mode):
        raise ContentSnapshotError("content root must be an existing directory")
    return candidate


def _collect(directory, prefix, snapshot):
    """Record regular files below ``directory`` or fail the whole snapshot."""
    try:
        entries = list(os.scandir(directory))
    except OSError:
        raise ContentSnapshotError("content snapshot could not be read") from None
    for entry in entries:
        relative = entry.name if prefix == "" else prefix + "/" + entry.name
        try:
            mode = entry.stat(follow_symlinks=False).st_mode
        except OSError:
            raise ContentSnapshotError("content snapshot could not be read") from None
        if stat.S_ISLNK(mode):
            raise ContentSnapshotError("content snapshot cannot include a symbolic link")
        if stat.S_ISDIR(mode):
            _collect(entry.path, relative, snapshot)
            continue
        if not stat.S_ISREG(mode):
            raise ContentSnapshotError("content snapshot cannot include a special file")
        snapshot[relative] = _read_file(entry.path)


def _read_file(path):
    """Read one regular file without following a link or blocking."""
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ContentSnapshotError("content snapshot cannot include a special file")
        with os.fdopen(fd, "rb") as handle:
            fd = None
            return handle.read()
    except OSError:
        raise ContentSnapshotError("content snapshot could not be read") from None
    finally:
        if fd is not None:
            os.close(fd)
