"""Conditional Git persistence for purge state, using local repositories only."""

import os
import subprocess
import tempfile

import pytest

import cache_purge
import purge_state_store as store


REF = "refs/heads/purge-state"
DOCUMENT = "prod.json"
_IMAGE_B = (
    "123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod@sha256:"
    + "b" * 64
)
_IMAGE_C = (
    "123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod@sha256:"
    + "c" * 64
)


def _git_env(extra=None):
    """Return an environment that cannot redirect Git outside the test repository."""
    env = os.environ.copy()
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX"):
        env.pop(name, None)
    if extra:
        env.update(extra)
    return env


def _git(repo, *args, input=None, check=True, env=None):
    """Run one Git command in a test repository."""
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=_git_env(env),
    )
    if check and completed.returncode != 0:
        raise AssertionError(completed.stderr.decode())
    return completed


def _init(path, bare=False):
    """Create a repository with a fixed branch name and no advisory output."""
    path.mkdir(parents=True)
    arguments = ["git", "init", "-q", "-b", "master"]
    if bare:
        arguments.append("--bare")
    arguments.append(str(path))
    subprocess.run(arguments, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_git_env())


def _workspace(path):
    """Create a workspace with an identity and a local commit."""
    _init(path)
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "local.txt").write_text("committed\n")
    _git(path, "add", "local.txt")
    _git(path, "commit", "-q", "-m", "local")


def _layout(tmp_path):
    """Return a reader, a writer, and a bare remote under an unprinted path."""
    root = tmp_path / "secret-remote-token"
    remote = root / "remote.git"
    _init(remote, bare=True)
    reader = root / "reader"
    writer = root / "writer"
    _workspace(reader)
    _workspace(writer)
    return reader, writer, remote


def _fingerprints(marker):
    """Return generated hostname fingerprints for one fixture snapshot."""
    return cache_purge.content_fingerprints(
        {
            "www.example/index.html": marker,
            "start.example/index.html": b"start-bytes",
        },
        (
            ("www.example/", ("www.example",)),
            ("start.example/", ("start.example",)),
        ),
    )


def _begin(identity, image, fingerprints, pending=()):
    """Plan a deployment intent from an empty accepted set."""
    return cache_purge.begin_deployment_intent(
        cache_purge.PurgeState({}, frozenset(pending), None),
        identity,
        image,
        fingerprints,
    )


def _read(workspace, remote):
    """Read the fixture ref through the adapter."""
    return store.read_purge_state(str(workspace), str(remote), REF, DOCUMENT)


def _write(workspace, remote, expected, state):
    """Publish a fixture state through the adapter."""
    return store.write_purge_state(str(workspace), str(remote), REF, DOCUMENT, expected, state)


def _remote_revision(remote):
    """Return the bare repository's state ref, or None when it is absent."""
    completed = _git(remote, "rev-parse", "--verify", "-q", REF, check=False)
    if completed.returncode != 0:
        return None
    return completed.stdout.decode().strip()


def _publish(repo, remote, files, parent=None):
    """Commit files directly so a fixture can plant a document the adapter did not write."""
    with tempfile.TemporaryDirectory() as temporary:
        index = os.path.join(temporary, "index")
        env = {"GIT_INDEX_FILE": index}
        if parent is None:
            _git(repo, "read-tree", "--empty", env=env)
        else:
            _git(repo, "read-tree", parent, env=env)
        for path, content in files.items():
            blob = _git(repo, "hash-object", "-w", "--stdin", input=content, env=env).stdout.decode().strip()
            _git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
        tree = _git(repo, "write-tree", env=env).stdout.decode().strip()
    command = ["commit-tree", tree]
    if parent is not None:
        command.extend(["-p", parent])
    revision = _git(repo, *command, input=b"fixture\n").stdout.decode().strip()
    _git(repo, "push", str(remote), f"{revision}:{REF}")
    return revision


def _signature(workspace):
    """Capture the caller-visible Git state, including a saved fetch head."""
    def capture(*args):
        return _git(workspace, *args, check=False).stdout

    fetch_head = workspace / ".git" / "FETCH_HEAD"
    return (
        capture("status", "--porcelain=v1", "-uall"),
        capture("rev-parse", "HEAD"),
        capture("symbolic-ref", "HEAD"),
        capture("config", "--local", "--list"),
        capture("for-each-ref", "--format=%(refname) %(objectname)"),
        capture("diff", "--cached"),
        capture("diff"),
        fetch_head.read_bytes() if fetch_head.exists() else None,
    )


def _assert_hidden(error, remote):
    """Failures must not reveal the remote path or its token-like directory."""
    message = "".join(str(item) for item in error.args)
    assert "secret-remote-token" not in message
    assert str(remote) not in message


def _seed_tracking(workspace):
    """Record an unrelated remote-tracking ref that publication must leave in place."""
    head = _git(workspace, "rev-parse", "HEAD").stdout.decode().strip()
    _git(workspace, "update-ref", "refs/remotes/origin/master", head)


def _stage_dirty(workspace):
    """Change a tracked file in both the index and the work tree."""
    (workspace / "local.txt").write_text("dirty\n")
    _git(workspace, "add", "local.txt")
    (workspace / "extra.txt").write_text("untracked\n")


def _round_trip_origin(monkeypatch, reader, writer):
    """Create, update, and read a named origin from a directory other than the workspace."""
    elsewhere = reader.parent.parent / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    for workspace in (reader, writer):
        _stage_dirty(workspace)
    before = {workspace: _signature(workspace) for workspace in (reader, writer)}
    monkeypatch.chdir(elsewhere)
    state = _begin("intent-a", _IMAGE_B, _fingerprints(b"relative"), pending={"old.example"})
    created = store.write_purge_state(str(writer), "origin", REF, DOCUMENT, None, state)
    created_snapshot = store.read_purge_state(str(reader), "origin", REF, DOCUMENT)
    updated_state = cache_purge.begin_deployment_intent(
        state, "intent-b", _IMAGE_C, _fingerprints(b"relative-next"))
    updated = store.write_purge_state(str(writer), "origin", REF, DOCUMENT, created, updated_state)
    updated_snapshot = store.read_purge_state(str(reader), "origin", REF, DOCUMENT)

    assert created_snapshot.revision == created
    assert created_snapshot.state == state
    assert updated != created
    assert updated_snapshot.revision == updated
    assert updated_snapshot.state == updated_state
    for workspace in (reader, writer):
        assert _signature(workspace) == before[workspace]
        refs = _git(workspace, "for-each-ref", "--format=%(refname)").stdout.decode()
        assert "refs/remotes/origin/purge-state" not in refs
        assert "refs/remotes/origin/master" in refs
    return updated_snapshot


def _auth_recorder(path):
    """Return a command that records how Git invoked it and then fails."""
    path.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$0 $*\" >> \"$AUTH_LOG\"\n"
        "printf 'ask=%s\\n' \"${GIT_ASKPASS-unset}\" >> \"$AUTH_LOG\"\n"
        "printf 'ssh=%s\\n' \"${GIT_SSH_COMMAND-unset}\" >> \"$AUTH_LOG\"\n"
        "printf 'term=%s\\n' \"${GIT_TERMINAL_PROMPT-unset}\" >> \"$AUTH_LOG\"\n"
        "echo secret-auth-token >&2\n"
        "exit 1\n"
    )
    path.chmod(0o755)


class TestPurgeStateStore:
    """The adapter publishes one prepared transition against the exact revision it read."""

    def test_missing_ref_can_be_initialized(self, tmp_path):
        """Confirmed absence is initial state, and an invalid document does not create the ref."""
        _reader, writer, remote = _layout(tmp_path)
        absent = _read(writer, remote)
        bad = _begin("intent-a", _IMAGE_B, {"www.example": "A"})

        assert isinstance(absent, store.PurgeStateAbsent)
        with pytest.raises(ValueError, match="unsupported fingerprint"):
            _write(writer, remote, None, bad)
        assert _remote_revision(remote) is None

        state = _begin("intent-a", _IMAGE_B, _fingerprints(b"first"), pending={"old.example"})
        revision = _write(writer, remote, None, state)

        assert _remote_revision(remote) == revision
        assert _git(remote, "rev-parse", "-q", "--verify", f"{revision}^", check=False).returncode != 0

    def test_round_trip_uses_one_commit_and_still_checks_matching_bytes(self, tmp_path):
        """The snapshot's revision contains its document, and identical bytes do not skip the guard."""
        reader, writer, remote = _layout(tmp_path)
        state = _begin("intent-a", _IMAGE_B, _fingerprints(b"first"))
        revision = _write(writer, remote, None, state)
        snapshot = _read(reader, remote)
        document = _git(remote, "cat-file", "blob", f"{revision}:{DOCUMENT}").stdout
        again = _write(writer, remote, revision, state)

        assert snapshot.revision == revision
        assert snapshot.state == state
        assert cache_purge.decode_purge_state(document.decode()) == snapshot.state
        assert _git(remote, "log", "-1", "--format=%s", revision).stdout == b"chore(cache-purge): update deployment state\n"
        assert again != revision
        assert _git(remote, "rev-parse", f"{again}^").stdout.decode().strip() == revision
        with pytest.raises(store.PurgeStateConflict) as caught:
            _write(writer, remote, revision, state)
        _assert_hidden(caught.value, remote)
        assert _remote_revision(remote) == again

    def test_second_writer_with_the_same_revision_conflicts(self, tmp_path):
        """Two writers that read one revision cannot both publish."""
        reader, writer, remote = _layout(tmp_path)
        other = tmp_path / "secret-remote-token" / "other"
        _workspace(other)
        initial = _begin("intent-a", _IMAGE_B, _fingerprints(b"base"))
        revision = _write(writer, remote, None, initial)
        observed = _read(reader, remote)
        first = cache_purge.begin_deployment_intent(
            observed.state, "intent-b", _IMAGE_B, _fingerprints(b"left"))
        second = cache_purge.begin_deployment_intent(
            observed.state, "intent-c", _IMAGE_C, _fingerprints(b"right"))

        published = _write(writer, remote, observed.revision, first)
        with pytest.raises(store.PurgeStateConflict) as caught:
            _write(other, remote, observed.revision, second)

        current = _read(reader, remote)
        _assert_hidden(caught.value, remote)
        assert observed.revision == revision
        assert published == current.revision
        assert current.state.intent.identity == "intent-b"
        assert current.state != second

    def test_newer_intent_blocks_an_older_acceptance_with_the_same_fingerprints(self, tmp_path):
        """A stale acceptance is not replayed when the newer intent has the same fingerprints."""
        reader, writer, remote = _layout(tmp_path)
        fingerprints = _fingerprints(b"same")
        older = _begin("intent-b", _IMAGE_B, fingerprints)
        revision = _write(writer, remote, None, older)
        current = cache_purge.begin_deployment_intent(older, "intent-c", _IMAGE_C, fingerprints)
        published = _write(writer, remote, revision, current)
        acceptance = cache_purge.record_intent_acceptance(older, "intent-b", fingerprints)

        with pytest.raises(store.PurgeStateConflict):
            _write(writer, remote, revision, acceptance)

        snapshot = _read(reader, remote)
        assert published == snapshot.revision
        assert snapshot.state == current
        assert snapshot.state.intent.identity == "intent-c"
        assert snapshot.state.pending == current.pending

    def test_only_one_initial_creation_succeeds(self, tmp_path):
        """Two creators that both observed an absent ref cannot both create it."""
        _reader, writer, remote = _layout(tmp_path)
        other = tmp_path / "secret-remote-token" / "other"
        _workspace(other)
        assert isinstance(_read(writer, remote), store.PurgeStateAbsent)
        assert isinstance(_read(other, remote), store.PurgeStateAbsent)
        first = _begin("intent-a", _IMAGE_B, _fingerprints(b"first"))
        second = _begin("intent-b", _IMAGE_C, _fingerprints(b"second"))

        revision = _write(writer, remote, None, first)
        with pytest.raises(store.PurgeStateConflict) as caught:
            _write(other, remote, None, second)

        snapshot = _read(writer, remote)
        _assert_hidden(caught.value, remote)
        assert snapshot.revision == revision
        assert snapshot.state == first

    def test_stale_write_cannot_recreate_or_replace_a_moved_ref(self, tmp_path):
        """Deleting or retargeting the ref after a read rejects the old revision."""
        _reader, writer, remote = _layout(tmp_path)
        state = _begin("intent-a", _IMAGE_B, _fingerprints(b"first"))
        revision = _write(writer, remote, None, state)
        replacement = cache_purge.begin_deployment_intent(
            state, "intent-b", _IMAGE_C, _fingerprints(b"next"))
        _git(remote, "update-ref", "-d", REF)

        with pytest.raises(store.PurgeStateConflict):
            _write(writer, remote, revision, replacement)
        assert _remote_revision(remote) is None

        planted = _publish(writer, remote, {DOCUMENT: cache_purge.encode_purge_state(state).encode()})
        unrelated = _git(writer, "rev-parse", "HEAD").stdout.decode().strip()
        _git(writer, "push", str(remote), f"{unrelated}:refs/heads/unrelated")
        _git(remote, "update-ref", REF, unrelated)
        with pytest.raises(store.PurgeStateConflict):
            _write(writer, remote, planted, replacement)
        assert _remote_revision(remote) == unrelated

    def test_missing_or_corrupt_documents_fail_closed(self, tmp_path):
        """An existing ref with no usable document is an error, not a missing ref."""
        reader, writer, remote = _layout(tmp_path)
        _publish(writer, remote, {"notes/readme.txt": b"present\n"})
        with pytest.raises(store.PurgeStateStoreError, match="missing") as missing:
            _read(reader, remote)
        assert type(missing.value) is store.PurgeStateStoreError
        _assert_hidden(missing.value, remote)

        _git(remote, "update-ref", "-d", REF)
        _publish(writer, remote, {DOCUMENT: b'{"secret-state-token":'})
        with pytest.raises(store.PurgeStateStoreError, match="invalid") as malformed:
            _read(reader, remote)
        assert type(malformed.value) is store.PurgeStateStoreError
        assert "secret-state-token" not in str(malformed.value)

        _git(remote, "update-ref", "-d", REF)
        fingerprints = _fingerprints(b"contradiction")
        contradictory = cache_purge.encode_purge_state(
            _begin("intent-a", _IMAGE_B, fingerprints)).encode()
        planted = contradictory.replace(b'"pending":["start.example","www.example"]', b'"pending":[]')
        assert planted != contradictory
        _publish(writer, remote, {DOCUMENT: planted})
        with pytest.raises(store.PurgeStateStoreError, match="invalid") as conflict:
            _read(reader, remote)
        assert type(conflict.value) is store.PurgeStateStoreError
        assert fingerprints["www.example"] not in str(conflict.value)

    def test_unmanaged_pending_work_survives(self, tmp_path):
        """A hostname outside the intent remains pending after a round trip."""
        reader, writer, remote = _layout(tmp_path)
        fingerprints = _fingerprints(b"partial")
        planned = _begin("intent-b", _IMAGE_B, fingerprints, pending={"old.example"})
        partial = cache_purge.record_intent_acceptance(
            planned, "intent-b", {"www.example": fingerprints["www.example"]})
        _write(writer, remote, None, partial)
        snapshot = _read(reader, remote)

        assert snapshot.state.pending == frozenset({"old.example", "start.example"})
        assert snapshot.state.purged == {"www.example": fingerprints["www.example"]}
        assert "old.example" not in snapshot.state.intent.fingerprints

    def test_other_branch_files_survive_updates(self, tmp_path):
        """Publishing a new purge document leaves the rest of the branch tree in place."""
        _reader, writer, remote = _layout(tmp_path)
        initial = _begin("intent-a", _IMAGE_B, _fingerprints(b"first"))
        revision = _publish(writer, remote, {
            DOCUMENT: cache_purge.encode_purge_state(initial).encode(),
            "keep.txt": b"keep-me\n",
            "notes/readme.txt": b"nested\n",
        })
        updated = cache_purge.begin_deployment_intent(
            initial, "intent-b", _IMAGE_C, _fingerprints(b"second"))
        published = _write(writer, remote, revision, updated)

        assert _git(remote, "cat-file", "blob", f"{published}:keep.txt").stdout == b"keep-me\n"
        assert _git(remote, "cat-file", "blob", f"{published}:notes/readme.txt").stdout == b"nested\n"
        assert _read(writer, remote).state == updated

    def test_command_failure_and_timeout_are_not_absence(self, monkeypatch, tmp_path):
        """A bad remote or a non-finite timeout does not look like an absent ref."""
        reader, _writer, remote = _layout(tmp_path)
        missing = remote.parent / "secret-remote-token-missing"
        with pytest.raises(store.PurgeStateStoreError, match="command failed") as failed:
            store.read_purge_state(str(reader), str(missing), REF, DOCUMENT)
        assert type(failed.value) is store.PurgeStateStoreError
        _assert_hidden(failed.value, missing)

        def refuse_popen(*_args, **_kwargs):
            raise AssertionError("Git started for a non-finite timeout")

        monkeypatch.setattr(store.subprocess, "Popen", refuse_popen)
        with pytest.raises(ValueError, match="timeout"):
            store.read_purge_state(str(reader), str(remote), REF, DOCUMENT, timeout=float("nan"))
        with pytest.raises(ValueError, match="timeout"):
            store.write_purge_state(str(reader), str(remote), REF, DOCUMENT, None, _begin(
                "intent-a", _IMAGE_B, _fingerprints(b"finite")), timeout=float("inf"))

    def test_caller_workspace_remains_unchanged(self, tmp_path):
        """Reading and writing do not change the caller's branch, index, worktree, or config."""
        reader, writer, remote = _layout(tmp_path)
        for workspace in (reader, writer):
            (workspace / "local.txt").write_text("staged\n")
            _git(workspace, "add", "local.txt")
            (workspace / "local.txt").write_text("dirty\n")
            (workspace / "extra.txt").write_text("untracked\n")
        before_reader = _signature(reader)
        before_writer = _signature(writer)
        state = _begin("intent-a", _IMAGE_B, _fingerprints(b"first"), pending={"old.example"})

        assert isinstance(_read(reader, remote), store.PurgeStateAbsent)
        revision = _write(writer, remote, None, state)
        assert _read(reader, remote).revision == revision
        assert _signature(reader) == before_reader
        assert _signature(writer) == before_writer

    def test_named_remote_preserves_caller_metadata(self, tmp_path):
        """A configured origin can read and write without tracking refs or FETCH_HEAD."""
        reader, writer, remote = _layout(tmp_path)
        other = tmp_path / "secret-remote-token" / "other"
        _workspace(other)
        for workspace in (reader, writer, other):
            _git(workspace, "remote", "add", "origin", str(remote))
            _git(workspace, "update-ref", "refs/remotes/origin/master", _git(
                workspace, "rev-parse", "HEAD").stdout.decode().strip())
            (workspace / "local.txt").write_text("dirty\n")
        before = {workspace: _signature(workspace) for workspace in (reader, writer, other)}
        state = _begin("intent-a", _IMAGE_B, _fingerprints(b"named"), pending={"old.example"})

        revision = store.write_purge_state(str(writer), "origin", REF, DOCUMENT, None, state)
        snapshot = store.read_purge_state(str(reader), "origin", REF, DOCUMENT)
        with pytest.raises(store.PurgeStateConflict) as rejected:
            store.write_purge_state(str(other), "origin", REF, DOCUMENT, None, _begin(
                "intent-b", _IMAGE_C, _fingerprints(b"loser")))

        assert snapshot.revision == revision
        assert snapshot.state == state
        assert _remote_revision(remote) == revision
        _assert_hidden(rejected.value, remote)
        for workspace in (reader, writer, other):
            assert _signature(workspace) == before[workspace]
            refs = _git(workspace, "for-each-ref", "--format=%(refname)").stdout.decode()
            assert "refs/remotes/origin/purge-state" not in refs
            assert "refs/remotes/origin/master" in refs

        _git(remote, "update-ref", "-d", REF)
        _publish(writer, remote, {DOCUMENT: b'{"secret-state-token":'})
        with pytest.raises(store.PurgeStateStoreError, match="invalid") as invalid:
            store.read_purge_state(str(reader), "origin", REF, DOCUMENT)
        assert type(invalid.value) is store.PurgeStateStoreError
        assert "secret-state-token" not in str(invalid.value)
        assert _signature(reader) == before[reader]

    def test_hook_rejection_is_not_a_revision_conflict(self, tmp_path):
        """A pre-receive hook failure stays a store error and publishes nothing."""
        _reader, writer, remote = _layout(tmp_path)
        hook = remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\necho secret-hook-token >&2\nexit 1\n")
        hook.chmod(0o755)

        with pytest.raises(store.PurgeStateStoreError, match="command failed") as caught:
            _write(writer, remote, None, _begin("intent-a", _IMAGE_B, _fingerprints(b"hook")))

        assert type(caught.value) is store.PurgeStateStoreError
        assert "secret-hook-token" not in str(caught.value)
        assert _remote_revision(remote) is None

    def test_launch_and_timeout_failures_are_sanitized(self, monkeypatch, tmp_path):
        """Process launch and timeout failures use the store error and hide their cause."""
        reader, _writer, remote = _layout(tmp_path)

        def explode(*_args, **_kwargs):
            raise OSError("secret-launch-token")

        monkeypatch.setattr(store.subprocess, "Popen", explode)
        with pytest.raises(store.PurgeStateStoreError, match="command failed") as launched:
            store.read_purge_state(str(reader), str(remote), REF, DOCUMENT)
        assert type(launched.value) is store.PurgeStateStoreError
        assert "secret-launch-token" not in str(launched.value)
        monkeypatch.undo()

        real_popen = subprocess.Popen

        def timeout_popen(*args, **kwargs):
            process = real_popen(*args, **kwargs)

            def communicate(_input=None, timeout=None):
                raise subprocess.TimeoutExpired(args, timeout or 0)

            process.communicate = communicate
            return process

        monkeypatch.setattr(store.subprocess, "Popen", timeout_popen)
        with pytest.raises(store.PurgeStateStoreError, match="timed out") as timed:
            store.read_purge_state(str(reader), str(remote), REF, DOCUMENT)
        assert type(timed.value) is store.PurgeStateStoreError

    def test_publication_races_preserve_the_other_writer(self, monkeypatch, tmp_path):
        """The push itself rejects a ref that moved after the preliminary checks."""
        reader, writer, remote = _layout(tmp_path)
        other = tmp_path / "secret-remote-token" / "other"
        _workspace(other)
        root_state = _begin("intent-root", _IMAGE_B, _fingerprints(b"root"))
        root = _write(writer, remote, None, root_state)
        current_state = cache_purge.begin_deployment_intent(
            root_state, "intent-current", _IMAGE_C, _fingerprints(b"current"))
        current = _write(writer, remote, root, current_state)

        def during(mutate):
            original = store._push

            def barrier(*args, **kwargs):
                store._push = original
                mutate()
                return original(*args, **kwargs)

            monkeypatch.setattr(store, "_push", barrier)

        winner = cache_purge.begin_deployment_intent(
            current_state, "intent-winner", _IMAGE_B, _fingerprints(b"winner"))
        loser = cache_purge.begin_deployment_intent(
            current_state, "intent-loser", _IMAGE_C, _fingerprints(b"loser"))
        during(lambda: store.write_purge_state(str(other), str(remote), REF, DOCUMENT, current, winner))
        with pytest.raises(store.PurgeStateConflict):
            store.write_purge_state(str(writer), str(remote), REF, DOCUMENT, current, loser)
        assert _read(reader, remote).state == winner

        deleted = cache_purge.begin_deployment_intent(
            winner, "intent-deleted", _IMAGE_C, _fingerprints(b"deleted"))
        during(lambda: _git(remote, "update-ref", "-d", REF))
        with pytest.raises(store.PurgeStateConflict):
            _write(writer, remote, _remote_revision(remote), deleted)
        assert _remote_revision(remote) is None

        restored = _write(writer, remote, None, root_state)
        child_state = cache_purge.begin_deployment_intent(
            root_state, "intent-child", _IMAGE_C, _fingerprints(b"child"))
        child = _write(writer, remote, restored, child_state)
        grandchild = cache_purge.begin_deployment_intent(
            child_state, "intent-grand", _IMAGE_B, _fingerprints(b"grand"))
        during(lambda: _git(remote, "update-ref", REF, restored))
        with pytest.raises(store.PurgeStateConflict):
            _write(writer, remote, child, grandchild)
        assert _read(reader, remote).state == root_state

        creator = _begin("intent-creator", _IMAGE_B, _fingerprints(b"creator"))
        late = _begin("intent-late", _IMAGE_C, _fingerprints(b"late"))
        _git(remote, "update-ref", "-d", REF)
        during(lambda: store.write_purge_state(str(other), str(remote), REF, DOCUMENT, None, creator))
        with pytest.raises(store.PurgeStateConflict):
            store.write_purge_state(str(writer), str(remote), REF, DOCUMENT, None, late)
        assert _read(reader, remote).state == creator

    def test_relative_remote_url_resolves_from_the_workspace(self, monkeypatch, tmp_path):
        """A relative origin URL works when the process is not in the workspace."""
        reader, writer, _remote = _layout(tmp_path)
        for workspace in (reader, writer):
            _git(workspace, "remote", "add", "origin", "../remote.git")
            assert _git(workspace, "config", "--get", "remote.origin.url").stdout == b"../remote.git\n"
            _seed_tracking(workspace)
        _round_trip_origin(monkeypatch, reader, writer)
        for workspace in (reader, writer):
            assert _git(workspace, "config", "--get", "remote.origin.url").stdout == b"../remote.git\n"

    def test_relative_include_path_resolves_beside_the_caller_config(self, monkeypatch, tmp_path):
        """A remote declared through a relative include stays beside the caller's config."""
        reader, writer, _remote = _layout(tmp_path)
        for workspace in (reader, writer):
            (workspace / "remotes.gitconfig").write_text(
                "[remote \"origin\"]\n"
                "\turl = ../remote.git\n"
                "\tfetch = +refs/heads/*:refs/remotes/origin/*\n"
            )
            _git(workspace, "config", "include.path", "../remotes.gitconfig")
            assert _git(workspace, "config", "--get", "remote.origin.url").stdout == b"../remote.git\n"
            _seed_tracking(workspace)
        _round_trip_origin(monkeypatch, reader, writer)
        for workspace in (reader, writer):
            assert _git(workspace, "config", "--get", "include.path").stdout == b"../remotes.gitconfig\n"
            assert _git(workspace, "config", "--get", "remote.origin.url").stdout == b"../remote.git\n"

    @pytest.mark.parametrize("workspace", [".", "writer"])
    def test_relative_workspace_path_refers_to_that_repository(self, monkeypatch, tmp_path, workspace):
        """``.`` and a child directory name both publish through the supplied repository."""
        _reader, writer, _remote = _layout(tmp_path)
        _git(writer, "remote", "add", "origin", "../remote.git")
        _seed_tracking(writer)
        _stage_dirty(writer)
        before = _signature(writer)
        monkeypatch.chdir(writer if workspace == "." else writer.parent)
        directory = os.getcwd()
        state = _begin("intent-a", _IMAGE_B, _fingerprints(b"workspace"), pending={"old.example"})

        created = store.write_purge_state(workspace, "origin", REF, DOCUMENT, None, state)
        created_snapshot = store.read_purge_state(workspace, "origin", REF, DOCUMENT)
        updated_state = cache_purge.begin_deployment_intent(
            state, "intent-b", _IMAGE_C, _fingerprints(b"workspace-next"))
        updated = store.write_purge_state(workspace, "origin", REF, DOCUMENT, created, updated_state)
        updated_snapshot = store.read_purge_state(workspace, "origin", REF, DOCUMENT)

        assert os.getcwd() == directory
        assert created_snapshot.revision == created
        assert created_snapshot.state == state
        assert updated != created
        assert updated_snapshot.revision == updated
        assert updated_snapshot.state == updated_state
        assert _signature(writer) == before
        refs = _git(writer, "for-each-ref", "--format=%(refname)").stdout.decode()
        assert "refs/remotes/origin/purge-state" not in refs
        assert "refs/remotes/origin/master" in refs

    def test_supplied_authentication_commands_reach_git(self, monkeypatch, tmp_path):
        """Caller-supplied askpass and ssh commands are the ones Git executes."""
        reader, _writer, _remote = _layout(tmp_path)
        log = tmp_path / "auth.log"
        command = tmp_path / "ssh-command"
        askpass = tmp_path / "ask-pass"
        decoy = tmp_path / "decoy-command"
        _auth_recorder(command)
        _auth_recorder(decoy)
        askpass.write_text("#!/bin/sh\nexit 1\n")
        askpass.chmod(0o755)
        _git(reader, "remote", "add", "auth", "ssh://local.test/repo.git")
        _git(reader, "config", "core.sshCommand", str(decoy))
        monkeypatch.setenv("AUTH_LOG", str(log))
        supplied = f"{command} --marker secret-auth-token"
        monkeypatch.setenv("GIT_SSH_COMMAND", supplied)
        monkeypatch.setenv("GIT_ASKPASS", str(askpass))
        before = _signature(reader)

        with pytest.raises(store.PurgeStateStoreError, match="command failed") as failed:
            store.read_purge_state(str(reader), "auth", REF, DOCUMENT)
        with pytest.raises(store.PurgeStateStoreError, match="command failed") as write_failed:
            store.write_purge_state(str(reader), "auth", REF, DOCUMENT, None, _begin(
                "intent-a", _IMAGE_B, _fingerprints(b"auth")))

        recorded = log.read_text()
        assert supplied in recorded
        assert f"{command} --marker secret-auth-token" in recorded
        assert f"ask={askpass}" in recorded
        assert "term=0" in recorded
        assert str(decoy) not in recorded
        assert "secret-auth-token" not in str(failed.value)
        assert "secret-auth-token" not in str(write_failed.value)
        assert type(failed.value) is store.PurgeStateStoreError
        assert _signature(reader) == before

    def test_configured_authentication_is_used_when_unset(self, monkeypatch, tmp_path):
        """Without supplied commands, Git uses the repository's configured ssh command."""
        reader, _writer, _remote = _layout(tmp_path)
        log = tmp_path / "auth.log"
        command = tmp_path / "configured-ssh"
        _auth_recorder(command)
        _git(reader, "remote", "add", "auth", "ssh://local.test/repo.git")
        _git(reader, "config", "core.sshCommand", str(command))
        _git(reader, "config", "core.askPass", str(tmp_path / "configured-ask"))
        monkeypatch.setenv("AUTH_LOG", str(log))
        monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
        monkeypatch.delenv("GIT_ASKPASS", raising=False)
        before = _signature(reader)

        with pytest.raises(store.PurgeStateStoreError, match="command failed") as failed:
            store.read_purge_state(str(reader), "auth", REF, DOCUMENT)

        recorded = log.read_text()
        assert str(command) in recorded
        assert "ask=unset" in recorded
        assert "ssh=unset" in recorded
        assert "BatchMode" not in recorded
        assert "/usr/bin/true" not in recorded
        assert "term=0" in recorded
        assert "secret-auth-token" not in str(failed.value)
        assert type(failed.value) is store.PurgeStateStoreError
        assert _signature(reader) == before
