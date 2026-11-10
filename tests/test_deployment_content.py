"""Generated-content snapshots from a completed artifact directory."""

import os
import signal
import socket
from contextlib import contextmanager

import pytest

import cache_purge
import deployment_content


_RULES = (
    ("www.example/", ("www.example",)),
    ("www.example/en-US/maintenance/", ("addons.example",)),
    ("wsgi.py", ("www.example", "updates.example")),
)
_TREE = {
    "www.example/index.html": b"home\r\n",
    "www.example/en-US/maintenance/index.html": b"down",
    "www.example/en-US/My File.css": b".particle-star { opacity: calc(61/100); }",
    "www.example/.hidden": b"\xff\xfe\x00",
    "www.example/empty.txt": b"",
    "wsgi.py": b"redirect-a",
    "notes/private.txt": b"secret",
}


def _write(root, files):
    """Create ``files`` under ``root`` using forward-slash relative paths."""
    root.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        destination = root.joinpath(*relative.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    return root


def _snapshot(root, files=None):
    """Write one artifact and read it back."""
    return deployment_content.read_content_snapshot(_write(root, _TREE if files is None else files))


@contextmanager
def _bounded():
    """Stop a read that blocks on a link or special file."""
    def expire(_signum, _frame):
        raise TimeoutError("content read blocked")

    previous = signal.signal(signal.SIGALRM, expire)
    signal.alarm(3)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


class TestReadContentSnapshot:
    """A snapshot is the exact bytes of the regular files in one directory."""

    def test_reads_nested_hidden_binary_and_empty_files(self, tmp_path):
        """Nested, hidden, binary, zero-byte, and unusual names keep their bytes."""
        files = {**_TREE, "a\\b.txt": b"literal-backslash"}
        root = _write(tmp_path / "artifact", files)
        (root / "www.example" / "unused").mkdir()
        (root / "lonely").mkdir()

        assert deployment_content.read_content_snapshot(root) == files

    def test_empty_directories_have_no_records(self, tmp_path):
        """An empty directory, including empty subdirectories, is an empty snapshot."""
        root = tmp_path / "artifact"
        (root / "unused" / "still-empty").mkdir(parents=True)

        assert deployment_content.read_content_snapshot(root) == {}
        assert deployment_content.read_content_snapshot(root / "unused" / "still-empty") == {}

    @pytest.mark.parametrize("root_for", ["missing", "file", "blank", "none", "nul"])
    def test_invalid_roots_fail(self, tmp_path, root_for):
        """A missing path, file, blank value, non-path, or embedded NUL is rejected."""
        if root_for == "missing":
            root = tmp_path / "absent"
        elif root_for == "file":
            root = tmp_path / "page.html"
            root.write_bytes(b"not a directory")
        elif root_for == "blank":
            root = ""
        elif root_for == "nul":
            root = "artifact\x00invalid"
        else:
            root = None

        with pytest.raises(deployment_content.ContentSnapshotError, match="existing directory") as caught:
            deployment_content.read_content_snapshot(root)

        assert type(caught.value) is deployment_content.ContentSnapshotError
        assert str(caught.value) == "content root must be an existing directory"

    @pytest.mark.parametrize("form", ["absolute", "absolute-slash", "relative", "dot"])
    def test_relative_and_absolute_roots_read_the_same_bytes(self, monkeypatch, tmp_path, form):
        """Relative, absolute, and current-directory roots preserve the same keys."""
        root = _write(tmp_path / "artifact", {
            "www.example/index.html": b"same",
            "wsgi.py": b"app",
        })
        expected = {"www.example/index.html": b"same", "wsgi.py": b"app"}
        if form == "absolute":
            chosen = os.path.abspath(root)
        elif form == "absolute-slash":
            chosen = os.path.abspath(root) + "/"
        elif form == "relative":
            monkeypatch.chdir(tmp_path)
            chosen = "artifact"
        else:
            monkeypatch.chdir(root)
            chosen = "."

        assert deployment_content.read_content_snapshot(chosen) == expected

    @pytest.mark.parametrize("kind", [
        "file",
        "nested-file",
        "directory",
        "nested-directory",
        "root",
        "root-slash",
    ])
    def test_symbolic_links_are_rejected(self, tmp_path, kind):
        """File links, directory links, and a symlink root fail without being followed."""
        target = tmp_path / "target"
        target.mkdir()
        (target / "index.html").write_bytes(b"secret-target")
        root = _write(tmp_path / "artifact", {"keep.html": b"keep"})
        if kind == "file":
            (root / "alias.html").symlink_to(target / "index.html")
            chosen = root
        elif kind == "nested-file":
            nested = root / "www.example"
            nested.mkdir()
            (nested / "alias.html").symlink_to(target / "index.html")
            chosen = root
        elif kind == "directory":
            (root / "linked").symlink_to(target, target_is_directory=True)
            chosen = root
        elif kind == "nested-directory":
            nested = root / "www.example"
            nested.mkdir()
            (nested / "linked").symlink_to(target, target_is_directory=True)
            chosen = root
        else:
            chosen = tmp_path / "root-link"
            chosen.symlink_to(root, target_is_directory=True)
            if kind == "root-slash":
                chosen = os.path.abspath(chosen) + "/"

        with _bounded():
            with pytest.raises(deployment_content.ContentSnapshotError, match="symbolic link"):
                deployment_content.read_content_snapshot(chosen)

    @pytest.mark.parametrize("kind", ["fifo", "socket"])
    def test_special_files_are_rejected(self, tmp_path, kind):
        """A fifo or socket fails the snapshot instead of blocking or returning neighbors."""
        root = _write(tmp_path / "artifact", {"index.html": b"page"})
        sock = None
        try:
            if kind == "fifo":
                os.mkfifo(root / "queue")
            else:
                # sun_path is short on macOS, so bind a relative name from the artifact.
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                previous = os.getcwd()
                os.chdir(root)
                try:
                    sock.bind("app.sock")
                finally:
                    os.chdir(previous)
            with _bounded():
                with pytest.raises(deployment_content.ContentSnapshotError, match="special file"):
                    deployment_content.read_content_snapshot(root)
        finally:
            if sock is not None:
                sock.close()

    def test_traversal_failure_does_not_return_a_partial_snapshot(self, monkeypatch, tmp_path):
        """A directory that cannot be listed fails the whole read."""
        root = _write(tmp_path / "artifact", {
            "index.html": b"top",
            "www.example/index.html": b"nested",
        })
        real_scandir = os.scandir

        def fail_nested(path):
            if os.path.basename(os.path.abspath(path)) == "www.example":
                raise PermissionError("unlisted")
            return real_scandir(path)

        monkeypatch.setattr(deployment_content.os, "scandir", fail_nested)
        with pytest.raises(deployment_content.ContentSnapshotError, match="could not be read"):
            deployment_content.read_content_snapshot(root)

    def test_read_failure_does_not_return_a_partial_snapshot(self, monkeypatch, tmp_path):
        """One unreadable file fails the snapshot that already found its neighbors."""
        root = _write(tmp_path / "artifact", {
            "index.html": b"top",
            "www.example/secret.bin": b"\xff",
        })
        real_open = os.open

        def fail_open(path, flags, *args, **kwargs):
            if os.path.basename(path) == "secret.bin":
                raise OSError("unreadable")
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(deployment_content.os, "open", fail_open)
        with pytest.raises(deployment_content.ContentSnapshotError, match="could not be read"):
            deployment_content.read_content_snapshot(root)
        assert (root / "index.html").read_bytes() == b"top"

    def test_file_removed_during_collection_fails(self, monkeypatch, tmp_path):
        """A file that disappears after it is listed does not leave a partial snapshot."""
        root = _write(tmp_path / "artifact", {
            "first.html": b"one",
            "second.html": b"two",
        })
        real_scandir = os.scandir

        def drop_second(path):
            entries = list(real_scandir(path))
            if os.path.abspath(path) == os.path.abspath(root):
                os.unlink(root / "second.html")
            return entries

        monkeypatch.setattr(deployment_content.os, "scandir", drop_second)
        with pytest.raises(deployment_content.ContentSnapshotError, match="could not be read"):
            deployment_content.read_content_snapshot(root)
        assert (root / "first.html").read_bytes() == b"one"
        assert not (root / "second.html").exists()

    @pytest.mark.parametrize(("path", "replacement", "hostnames"), [
        ("www.example/en-US/maintenance/index.html", b"up", {"www.example", "addons.example"}),
        ("wsgi.py", b"redirect-b", {"www.example", "updates.example"}),
        ("www.example/index.html", b"away", {"www.example"}),
        (
            "www.example/en-US/My File.css",
            b".particle-star { opacity: calc(5/100); }",
            {"www.example"},
        ),
        ("www.example/.hidden", b"\xff\xfe\x01", {"www.example"}),
        ("www.example/empty.txt", b"x", {"www.example"}),
        ("notes/private.txt", b"changed", set()),
        ("www.example/index.html", b"home\r\n", set()),
    ])
    def test_snapshot_changes_select_fake_rules(self, tmp_path, path, replacement, hostnames):
        """Overlapping directories, a shared file, and exact bytes select fake hostnames."""
        before = _snapshot(tmp_path / "before")
        after = _snapshot(tmp_path / "after", {**_TREE, path: replacement})

        assert cache_purge.changed_hostnames(before, after, _RULES) == hostnames

    def test_fingerprints_follow_overlapping_directories_and_the_shared_file(self, tmp_path):
        """A nested rule and an exact shared file change only the hostnames they name."""
        before = cache_purge.content_fingerprints(_snapshot(tmp_path / "before"), _RULES)
        maintenance = cache_purge.content_fingerprints(_snapshot(tmp_path / "maintenance", {
            **_TREE,
            "www.example/en-US/maintenance/index.html": b"up",
        }), _RULES)
        shared = cache_purge.content_fingerprints(_snapshot(tmp_path / "shared", {
            **_TREE,
            "wsgi.py": b"redirect-b",
        }), _RULES)

        assert set(before) == {"www.example", "addons.example", "updates.example"}
        assert maintenance["www.example"] != before["www.example"]
        assert maintenance["addons.example"] != before["addons.example"]
        assert maintenance["updates.example"] == before["updates.example"]
        assert shared["www.example"] != before["www.example"]
        assert shared["updates.example"] != before["updates.example"]
        assert shared["addons.example"] == before["addons.example"]
