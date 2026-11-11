"""Publish a pinned archive through a local builds checkout."""

import builtins
import os
import signal
import stat
import subprocess
import tempfile
import time
import traceback
from pathlib import Path

import pytest

import cache_purge
import deployment_purge
import deployment_release
import purge_state_store as store
from test_purge_state_store import DOCUMENT, REF, _git, _git_env, _init


_RUN = subprocess.run


IMAGE = (
    "123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod@sha256:"
    + "a" * 64
)
OTHER_IMAGE = (
    "123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod@sha256:"
    + "b" * 64
)
_EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "examples" / "cache-purge.example.json"
_TOKEN = "builds-key-secret"
_EMAIL = "bot@example.com"
_TOKENS = {
    "example": "example-zone-token",
    "example_updates": "updates-zone-token",
}
_SITE = {
    "www.example/index.html": b"home\r\n",
    "www.example/en-US/maintenance/index.html": b"down",
    "wsgi.py": b"redirect-a",
}


class Docker:
    """Return one pinned container and plant the files its copy would write."""

    def __init__(self, plant):
        self.plant = plant
        self.forbid = False

    def run(self, args):
        if self.forbid:
            raise AssertionError("docker started")
        action = args[1]
        if action == "create":
            stdout = f"{'ab' * 32}\n".encode()
            return subprocess.CompletedProcess(args, 0, stdout=stdout)
        if action == "cp":
            self.plant(Path(args[-1]))
            return subprocess.CompletedProcess(args, 0)
        if action in {"rm", "ps"}:
            return subprocess.CompletedProcess(args, 0, stdout=b"")
        return subprocess.CompletedProcess(args, 1)


def _example():
    """Load the checked-in example explicitly. The release code has no default."""
    return cache_purge.load_purge_config(_EXAMPLE.read_text(encoding="utf-8"))


def _plant_files(destination, files):
    """Write one archive tree, including links, without following those links."""
    root = Path(destination)
    for relative, content in files.items():
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, tuple) and content[0] == "exe":
            path.write_bytes(content[1])
            path.chmod(0o755)
        elif isinstance(content, tuple):
            os.symlink(content[1], path)
        else:
            path.write_bytes(content)


def _install(monkeypatch, tmp_path, plant):
    """Stub Docker and remember every command and extraction directory."""
    docker = Docker(plant)
    recorded = []
    created = []
    checked = {"askpass": False, "envs": [], "scripts": []}
    real_run = subprocess.run
    real_popen = subprocess.Popen
    real_mkdtemp = tempfile.mkdtemp
    real_mkstemp = tempfile.mkstemp

    def run(args, **kwargs):
        recorded.append(list(args))
        checked["envs"].append(kwargs.get("env"))
        _check_askpass(kwargs.get("env"), checked)
        if args and args[0] == "docker":
            return docker.run(args)
        return real_run(args, **kwargs)

    def popen(args, **kwargs):
        recorded.append(list(args))
        checked["envs"].append(kwargs.get("env"))
        _check_askpass(kwargs.get("env"), checked)
        return real_popen(args, **kwargs)

    def mkdtemp(*args, **kwargs):
        if kwargs.get("prefix") == "deployment-artifact-" and "dir" not in kwargs:
            kwargs["dir"] = tmp_path
        path = real_mkdtemp(*args, **kwargs)
        if kwargs.get("prefix") == "deployment-artifact-":
            created.append(path)
        return path

    def mkstemp(*args, **kwargs):
        result = real_mkstemp(*args, **kwargs)
        if kwargs.get("prefix") == "tb-builds-askpass-":
            checked["scripts"].append(result[1])
        return result

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp)
    monkeypatch.setattr(tempfile, "mkstemp", mkstemp)
    return docker, recorded, created, checked


def _check_askpass(env, checked):
    """The askpass program reads the builds key and does not store it."""
    if checked["askpass"] or not env or "GIT_ASKPASS" not in env:
        return
    script = Path(env["GIT_ASKPASS"])
    if not script.exists():
        return
    checked["askpass"] = True
    assert _TOKEN not in script.read_text(encoding="utf-8")
    username = _RUN(
        [str(script), "Username for 'https://github.com': "],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    password = _RUN(
        [str(script), "Password for 'https://x-access-token@github.com': "],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    embedded = _RUN(
        [str(script), "Username for 'https://user@github.com': "],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    unknown = _RUN(
        [str(script), "Password for 'https://github.com': "],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    unexpected = _RUN(
        [str(script), "unexpected prompt"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    assert username.returncode == 0
    assert username.stdout == b"x-access-token\n"
    assert password.returncode == 0
    assert password.stdout == _TOKEN.encode() + b"\n"
    assert embedded.returncode != 0
    assert unknown.returncode != 0
    assert unexpected.returncode != 0
    assert _TOKEN.encode() not in embedded.stdout + unknown.stdout + unexpected.stdout


def _secrets(monkeypatch):
    """Install the builds identity without writing either value into Git."""
    monkeypatch.setenv("TB_BUILDS_KEY", _TOKEN)
    monkeypatch.setenv("TB_BUILDS_GIT_EMAIL", _EMAIL)


def _git_identity():
    """Return the caller's Git identity settings."""
    return {key: os.environ.get(key) for key in deployment_release._AUTH_KEYS}


def _restore_identity(saved):
    """Put the process environment back even when a later assertion fails."""
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _checkout(tmp_path, branch, shallow=False):
    """Return a bare builds remote and a clone of one archive branch."""
    bare = tmp_path / "builds.git"
    seed = tmp_path / "seed"
    _init(bare, bare=True)
    _init(seed)
    _git(seed, "config", "user.email", "seed@example.com")
    _git(seed, "config", "user.name", "Seed")
    if branch != "master":
        _git(seed, "checkout", "-q", "-b", branch)
    (seed / "README.md").write_text("readme-sentinel\n")
    (seed / "old.txt").write_text("old\n")
    _git(seed, "add", "README.md", "old.txt")
    _git(seed, "commit", "-q", "-m", "seed")
    _git(seed, "remote", "add", "origin", str(bare))
    _git(seed, "push", "-q", "origin", branch)
    _git(bare, "config", "uploadpack.allowReachableSHA1InWant", "true")
    _git(bare, "config", "uploadpack.allowAnySHA1InWant", "true")
    checkout = tmp_path / "checkout"
    command = ["git", "clone", "-q", "--no-local"]
    if shallow:
        command.extend(["--depth", "1"])
    command.extend(["--branch", branch, str(bare), str(checkout)])
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=_git_env(),
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr.decode())
    _git(checkout, "config", "user.email", "fixture@example.com")
    _git(checkout, "config", "user.name", "Fixture")
    (checkout / ".git" / "marker").write_text("git-marker\n")
    return bare, checkout


def _publish(checkout, bare, deploy_env, plant_files, monkeypatch, tmp_path, **kwargs):
    """Publish one release against the stub and return its observation."""
    docker, recorded, created, checked = _install(
        monkeypatch,
        tmp_path,
        lambda destination: _plant_files(destination, plant_files),
    )
    _secrets(monkeypatch)
    result = deployment_release.publish_pinned_release(
        IMAGE,
        deploy_env,
        checkout,
        str(bare),
        "manual deployment.",
        **kwargs,
    )
    return result, docker, recorded, created, checked


def _clean(repo, *args):
    """Run Git without the redirecting variables a test may have poisoned."""
    env = os.environ.copy()
    for name in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_PREFIX",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE",
    ):
        env.pop(name, None)
    completed = _RUN(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr.decode())
    return completed


def _prod_hook(tmp_path, script):
    """Return a production checkout whose commit hook runs ``script``."""
    bare, checkout = _checkout(tmp_path, "prod")
    before = _git(bare, "rev-parse", "prod").stdout.decode().strip()
    hook = checkout / ".git" / "hooks" / "pre-commit"
    hook.write_text(script, encoding="utf-8")
    hook.chmod(0o755)
    return bare, checkout, before


def _release_prod(checkout, bare, monkeypatch, tmp_path, install=True, observed=None):
    """Publish one production release, optionally installing the Docker stub."""
    if install:
        _secrets(monkeypatch)
        installed = _install(monkeypatch, tmp_path, lambda destination: _plant_files(destination, _SITE))
        if observed is not None:
            observed.append(installed)
    deployment_release.publish_pinned_release(
        IMAGE,
        "prod",
        checkout,
        str(bare),
        "manual deployment.",
        configuration=_example(),
        credentials=_TOKENS,
        identity="run-1.1",
        state_ref=REF,
        state_path=DOCUMENT,
    )


def _assert_pending(checkout, bare, before, error):
    """The archive ref is unchanged and the new intent is still pending."""
    saved = store.read_purge_state(str(checkout), str(bare), REF, DOCUMENT)
    assert _clean(bare, "rev-parse", "prod").stdout.decode().strip() == before
    assert saved.state.intent.identity == "run-1.1"
    assert set(saved.state.pending) == {"www.example", "addons.example", "updates.example"}
    assert _TOKEN not in _visible(error)
    assert "example-zone-token" not in _visible(error)


def _pid_alive(pid, kill=None):
    """Return whether ``pid`` is present on Linux or macOS.

    Signal 0 does not kill the process. A missing ``/proc`` directory is not
    treated as exit. ``kill`` defaults to ``os.kill`` and can be the original
    function when a test has replaced it.
    """
    probe = os.kill if kill is None else kill
    try:
        probe(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _descendant_gone(pid, timeout=2, kill=None):
    """Return whether a process this test does not own has left the process table."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid, kill):
            return True
        time.sleep(0.02)
    return not _pid_alive(pid, kill)


def _reap_owned(process, real_wait, descendants, killpg=None, kill=None):
    """Stop and reap one Popen child, then signal descendants the test does not own."""
    if process is None:
        return
    group_kill = os.killpg if killpg is None else killpg
    direct_kill = os.kill if kill is None else kill
    try:
        group_kill(process.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        direct_kill(process.pid, signal.SIGKILL)
    except OSError:
        pass
    if real_wait is not None:
        try:
            real_wait(timeout=2)
        except (subprocess.TimeoutExpired, OSError):
            pass
    for pid in descendants:
        try:
            direct_kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _marker_pids(marker):
    """Return integer pids written by a test hook, ignoring a partial write."""
    if not marker.exists():
        return []
    pids = []
    for item in marker.read_text(encoding="utf-8").split():
        try:
            pids.append(int(item))
        except ValueError:
            continue
    return pids


def _visible(error):
    """Return diagnostics a caller can see for one exception."""
    notes = tuple(getattr(error, "__notes__", ()))
    text = "\n".join([
        str(error),
        repr(error),
        *notes,
        "".join(traceback.format_exception(error)),
    ])
    return text


def _stored(path):
    """Read stored bytes without following a symbolic link."""
    chunks = []
    for directory, dirnames, filenames in os.walk(path, followlinks=False):
        kept = []
        for name in dirnames:
            candidate = os.path.join(directory, name)
            if os.path.islink(candidate):
                chunks.append(os.readlink(candidate).encode())
            else:
                kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            candidate = os.path.join(directory, name)
            if os.path.islink(candidate):
                chunks.append(os.readlink(candidate).encode())
            else:
                chunks.append(Path(candidate).read_bytes())
    return b"\n".join(chunks)


def _docker_commands(recorded, action):
    return [args for args in recorded if args[:2] == ["docker", action]]


def _production(checkout, bare, files, monkeypatch, tmp_path, **kwargs):
    """Publish production with the explicit example configuration."""
    arguments = {
        "configuration": _example(),
        "credentials": _TOKENS,
        "identity": "run-1.1",
        "state_ref": REF,
        "state_path": DOCUMENT,
    }
    arguments.update(kwargs)
    return _publish(checkout, bare, "prod", files, monkeypatch, tmp_path, **arguments)


class TestPublishPinnedRelease:
    """One extraction feeds production intent and the builds archive."""

    def test_stage_publishes_without_purge_state(self, monkeypatch, tmp_path):
        """Stage replaces the master archive and does not touch purge inputs."""
        bare, checkout = _checkout(tmp_path, "master")

        def fail(*_args, **_kwargs):
            raise AssertionError("purge state was accessed")

        monkeypatch.setattr(deployment_purge, "read_purge_state", fail)
        monkeypatch.setattr(deployment_release, "prepare_deployment_intent", fail)
        result, _docker, recorded, created, _checked = _publish(
            checkout, bare, "stage", {"index.html": b"stage\n"}, monkeypatch, tmp_path,
        )

        assert result is None
        assert (checkout / "index.html").read_bytes() == b"stage\n"
        assert not (checkout / "old.txt").exists()
        assert (checkout / "README.md").read_text(encoding="utf-8") == "readme-sentinel\n"
        assert _git(bare, "rev-parse", "--verify", "-q", REF, check=False).returncode != 0
        assert len(_docker_commands(recorded, "create")) == 1
        assert not any(Path(path).exists() for path in created)

    def test_production_preflight_runs_before_docker_and_replacement(self, monkeypatch, tmp_path):
        """A missing zone token fails before extraction or archive deletion."""
        bare, checkout = _checkout(tmp_path, "prod")
        docker, recorded, _created, _checked = _install(monkeypatch, tmp_path, lambda _destination: None)
        docker.forbid = True
        _secrets(monkeypatch)
        credentials = {"example": _TOKENS["example"]}

        with pytest.raises(ValueError, match="^api_token is required$"):
            deployment_release.publish_pinned_release(
                IMAGE,
                "prod",
                checkout,
                str(bare),
                "manual deployment.",
                configuration=_example(),
                credentials=credentials,
                identity="run-1.1",
                state_ref=REF,
                state_path=DOCUMENT,
            )

        assert (checkout / "old.txt").read_text(encoding="utf-8") == "old\n"
        assert _docker_commands(recorded, "create") == []
        assert _TOKEN not in _visible(ValueError("api_token is required"))

    def test_unpinned_image_fails_before_docker(self, monkeypatch, tmp_path):
        """A mutable tag never starts extraction."""
        bare, checkout = _checkout(tmp_path, "prod")
        _docker, recorded, _created, _checked = _install(monkeypatch, tmp_path, lambda _destination: None)
        _secrets(monkeypatch)

        with pytest.raises(ValueError, match="^image must be pinned by digest$"):
            deployment_release.publish_pinned_release(
                IMAGE.replace("@sha256:" + "a" * 64, ":latest"),
                "prod",
                checkout,
                str(bare),
                "manual deployment.",
                configuration=_example(),
                credentials=_TOKENS,
                identity="run-1.1",
                state_ref=REF,
                state_path=DOCUMENT,
            )

        assert (checkout / "old.txt").exists()
        assert _docker_commands(recorded, "create") == []

    def test_one_extraction_persists_intent_before_replacing_the_archive(self, monkeypatch, tmp_path):
        """The fingerprinted bytes and the published bytes come from one copy."""
        bare, checkout = _checkout(tmp_path, "prod")
        observed = {"during_write": None}
        real_write = deployment_purge.write_purge_state

        def write(*args, **kwargs):
            observed["during_write"] = (checkout / "old.txt").exists()
            return real_write(*args, **kwargs)

        monkeypatch.setattr(deployment_purge, "write_purge_state", write)
        result, _docker, recorded, created, checked = _production(
            checkout, bare, _SITE, monkeypatch, tmp_path,
        )

        archived = {
            relative: (checkout / relative).read_bytes()
            for relative in _SITE
        }
        fingerprints = cache_purge.content_fingerprints(archived, _example().rules)
        pushes = [args for args in recorded if "HEAD:prod" in args]
        stored = _stored(checkout) + _stored(bare)
        visible = cache_purge.encode_purge_state(result.state)
        assert observed["during_write"] is True
        assert not (checkout / "old.txt").exists()
        assert archived == _SITE
        assert dict(result.state.intent.fingerprints) == fingerprints
        assert result.state.intent.image == IMAGE
        assert result.state.intent.identity == "run-1.1"
        assert set(result.state.pending) == {"www.example", "addons.example", "updates.example"}
        assert len(_docker_commands(recorded, "create")) == 1
        assert len(_docker_commands(recorded, "cp")) == 1
        assert pushes and pushes[0][-1] == "HEAD:prod"
        assert "--force" not in pushes[0]
        assert _git(checkout, "log", "-1", "--format=%an%n%ae%n%s").stdout.decode() == (
            f"Thundernest Bot\n{_EMAIL}\nWebsite rebuild triggered by manual deployment.\n"
        )
        assert checked["askpass"] is True
        assert _TOKEN.encode() not in stored
        assert b"example-zone-token" not in stored
        assert b"updates-zone-token" not in stored
        assert _TOKEN not in visible
        assert "example-zone-token" not in visible
        assert all(_TOKEN not in " ".join(args) for args in recorded)
        assert not any(Path(path).exists() for path in created)
        assert (checkout / ".git" / "marker").read_text(encoding="utf-8") == "git-marker\n"
        assert (checkout / "README.md").read_text(encoding="utf-8") == "readme-sentinel\n"
        assert os.environ.get("GIT_ASKPASS") is None
        scripts = [env["GIT_ASKPASS"] for env in checked["envs"] if env and env.get("GIT_ASKPASS")]
        assert scripts and all(not Path(script).exists() for script in scripts)
        archive = [args for args in recorded if args and args[0] == "git" and "credential.helper=" in args]
        assert any("HEAD:prod" in args for args in archive)

    def test_state_access_uses_a_shallow_archive_checkout(self, monkeypatch, tmp_path):
        """A depth-one builds clone can register and then update purge state."""
        bare, checkout = _checkout(tmp_path, "prod", shallow=True)
        assert _git(checkout, "rev-parse", "--is-shallow-repository").stdout.decode().strip() == "true"
        first, *_rest = _production(checkout, bare, _SITE, monkeypatch, tmp_path)
        updated = dict(_SITE)
        updated["wsgi.py"] = b"redirect-b"
        second, *_rest = _production(checkout, bare, updated, monkeypatch, tmp_path, identity="run-1.2")

        parent = _git(bare, "rev-parse", f"{second.revision}^").stdout.decode().strip()
        assert parent == first.revision
        assert (checkout / "wsgi.py").read_bytes() == b"redirect-b"
        assert second.state.intent.identity == "run-1.2"
        assert store.read_purge_state(str(checkout), str(bare), REF, DOCUMENT).state.intent.identity == "run-1.2"

    def test_unchanged_archive_does_not_create_a_commit(self, monkeypatch, tmp_path):
        """Identical site bytes are pushed without a new archive commit."""
        bare, checkout = _checkout(tmp_path, "master")
        head = _git(checkout, "rev-parse", "HEAD").stdout.decode().strip()
        result, *_rest = _publish(
            checkout, bare, "stage", {"old.txt": b"old\n"}, monkeypatch, tmp_path,
        )

        assert result is None
        assert _git(checkout, "rev-parse", "HEAD").stdout.decode().strip() == head
        assert _git(bare, "rev-parse", "master").stdout.decode().strip() == head
        assert _git(checkout, "log", "-1", "--format=%s").stdout.decode().strip() == "seed"

    def test_repository_metadata_and_links_stay_unfollowed(self, monkeypatch, tmp_path):
        """Cleanup keeps .git and README, and copies links as links."""
        bare, checkout = _checkout(tmp_path, "master")
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_bytes(b"do-not-copy")
        old_link = checkout / "old-link"
        old_link.symlink_to(secret)
        _git(checkout, "add", "old-link")
        _git(checkout, "commit", "-q", "-m", "link")

        def plant(destination):
            _plant_files(destination, {"index.html": b"stage\n"})
            os.symlink(str(outside), Path(destination) / "dirlink")

        _secrets(monkeypatch)
        _install(monkeypatch, tmp_path, plant)
        deployment_release.publish_pinned_release(
            IMAGE, "stage", checkout, str(bare), "manual deployment.",
        )

        published = checkout / "dirlink"
        assert published.is_symlink()
        assert os.readlink(published) == str(outside)
        assert secret.read_bytes() == b"do-not-copy"
        assert list(outside.iterdir()) == [secret]
        assert not old_link.exists()
        assert (checkout / "README.md").read_text(encoding="utf-8") == "readme-sentinel\n"
        assert (checkout / ".git" / "marker").read_text(encoding="utf-8") == "git-marker\n"
        assert not (checkout / ".git" / "marker").is_symlink()

    def test_artifact_git_content_is_rejected(self, monkeypatch, tmp_path):
        """An artifact .git entry neither replaces the checkout nor is persisted."""
        bare, checkout = _checkout(tmp_path, "prod")

        def fail(*_args, **_kwargs):
            raise AssertionError("purge state was accessed")

        monkeypatch.setattr(deployment_purge, "read_purge_state", fail)
        files = dict(_SITE)
        files[".git/config"] = _TOKEN.encode() + b"\n"
        with pytest.raises(deployment_release.ArchivePublicationError, match="^artifact must not contain .git$") as caught:
            _production(checkout, bare, files, monkeypatch, tmp_path)

        assert (checkout / "old.txt").read_text(encoding="utf-8") == "old\n"
        assert (checkout / ".git" / "marker").read_text(encoding="utf-8") == "git-marker\n"
        assert _TOKEN not in _visible(caught.value)
        assert _git(bare, "rev-parse", "--verify", "-q", REF, check=False).returncode != 0

    def test_state_conflict_keeps_the_winning_pending_work(self, monkeypatch, tmp_path):
        """A lost compare-and-swap is not replayed and does not replace the archive."""
        bare, checkout = _checkout(tmp_path, "prod")
        reads = []
        writes = []
        real_read = deployment_purge.read_purge_state
        real_write = deployment_purge.write_purge_state

        def read(*args, **kwargs):
            reads.append(args)
            snapshot = real_read(*args, **kwargs)
            if len(reads) == 1:
                current = cache_purge.PurgeState({}, frozenset({"kept.example"}), None)
                expected = None if isinstance(snapshot, store.PurgeStateAbsent) else snapshot.revision
                winner = cache_purge.begin_deployment_intent(
                    current, "other-run", OTHER_IMAGE, {"www.example": "f" * 64},
                )
                real_write(*args[:4], expected, winner)
            return snapshot

        def write(*args, **kwargs):
            writes.append(args)
            return real_write(*args, **kwargs)

        monkeypatch.setattr(deployment_purge, "read_purge_state", read)
        monkeypatch.setattr(deployment_purge, "write_purge_state", write)
        with pytest.raises(store.PurgeStateConflict):
            _production(checkout, bare, _SITE, monkeypatch, tmp_path)

        saved = store.read_purge_state(str(checkout), str(bare), REF, DOCUMENT)
        assert len(reads) == 1
        assert len(writes) == 1
        assert (checkout / "old.txt").read_text(encoding="utf-8") == "old\n"
        assert saved.state.intent.identity == "other-run"
        assert "kept.example" in saved.state.pending
        assert "run-1.1" not in cache_purge.encode_purge_state(saved.state)

    def test_archive_push_failure_leaves_the_intent_pending(self, monkeypatch, tmp_path):
        """A rejected archive push propagates and does not roll back purge state."""
        bare, checkout = _checkout(tmp_path, "prod")
        before = _git(bare, "rev-parse", "prod").stdout.decode().strip()
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Caller Name")
        hook = bare / "hooks" / "pre-receive"
        hook.write_text(
            "#!/bin/sh\n"
            "while read old new ref; do\n"
            "  case \"$ref\" in\n"
            "    refs/heads/purge-state) ;;\n"
            "    *) exit 1 ;;\n"
            "  esac\n"
            "done\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        _secrets(monkeypatch)
        _docker, _recorded, created, _checked = _install(
            monkeypatch, tmp_path, lambda destination: _plant_files(destination, _SITE),
        )
        with pytest.raises(deployment_release.ArchivePublicationError, match="^archive publication failed$") as caught:
            deployment_release.publish_pinned_release(
                IMAGE,
                "prod",
                checkout,
                str(bare),
                "manual deployment.",
                configuration=_example(),
                credentials=_TOKENS,
                identity="run-1.1",
                state_ref=REF,
                state_path=DOCUMENT,
            )

        saved = store.read_purge_state(str(checkout), str(bare), REF, DOCUMENT)
        assert _git(bare, "rev-parse", "prod").stdout.decode().strip() == before
        assert saved.state.intent.identity == "run-1.1"
        assert set(saved.state.pending) == {"www.example", "addons.example", "updates.example"}
        assert saved.state.purged == {}
        assert _TOKEN not in _visible(caught.value)
        assert "example-zone-token" not in _visible(caught.value)
        assert not any(Path(path).exists() for path in created)
        assert os.environ.get("GIT_AUTHOR_NAME") == "Caller Name"
        scripts = [env["GIT_ASKPASS"] for env in _checked["envs"] if env and env.get("GIT_ASKPASS")]
        assert scripts and all(not Path(script).exists() for script in scripts)

    def test_inherited_git_state_cannot_redirect_the_checkout(self, monkeypatch, tmp_path):
        """Branch checks and publication use the supplied checkout."""
        bare, checkout = _checkout(tmp_path, "master")
        other = tmp_path / "other"
        _init(other)
        _git(other, "config", "user.email", "other@example.com")
        _git(other, "config", "user.name", "Other")
        _git(other, "checkout", "-q", "-b", "other")
        (other / "only-other.txt").write_text("other\n")
        _git(other, "add", "only-other.txt")
        _git(other, "commit", "-q", "-m", "other")
        other_head = _git(other, "rev-parse", "HEAD").stdout
        helper = tmp_path / "helper.sh"
        helper.write_text(f"#!/bin/sh\ntouch {tmp_path / 'helper-ran'}\nexit 1\n", encoding="utf-8")
        helper.chmod(0o755)
        config = tmp_path / "caller.gitconfig"
        config.write_text(
            f"[user]\n\tname = Caller Name\n[credential]\n\thelper = {helper}\n",
            encoding="utf-8",
        )
        original = config.read_bytes()
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
        monkeypatch.setenv("GIT_DIR", str(other / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(other))
        monkeypatch.setenv("GIT_COMMON_DIR", str(other / ".git"))
        monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "poison.index"))
        monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(other / ".git" / "objects"))
        monkeypatch.setenv("GIT_ALTERNATE_OBJECT_DIRECTORIES", str(other / ".git" / "objects"))
        monkeypatch.setenv("GIT_NAMESPACE", "poison")
        monkeypatch.setenv("GIT_PREFIX", str(other))
        _result, _docker, recorded, _created, checked = _publish(
            checkout, bare, "stage", {"index.html": b"stage\n"}, monkeypatch, tmp_path,
        )

        git_envs = [env for env in checked["envs"] if env and env.get("LC_ALL") == "C"]
        archive = [args for args in recorded if args and args[0] == "git"]
        inspections = [args for args in archive if "rev-parse" in args]
        assert (checkout / "index.html").read_bytes() == b"stage\n"
        assert _clean(bare, "show", "master:index.html").stdout == b"stage\n"
        assert _clean(checkout, "rev-parse", "HEAD").stdout == _clean(bare, "rev-parse", "master").stdout
        assert _clean(other, "rev-parse", "HEAD").stdout == other_head
        assert inspections and os.fspath(checkout) in inspections[0]
        assert git_envs
        assert all(env.get("GIT_CONFIG_GLOBAL") == str(config) for env in git_envs)
        assert all(env.get("GIT_CONFIG_NOSYSTEM") == os.environ.get("GIT_CONFIG_NOSYSTEM") for env in git_envs)
        assert all("GIT_DIR" not in env and "GIT_INDEX_FILE" not in env for env in git_envs)
        assert archive and all("credential.helper=" in args for args in archive)
        assert config.read_bytes() == original
        assert not (tmp_path / "helper-ran").exists()
        assert _clean(checkout, "log", "-1", "--format=%an").stdout.decode().strip() == "Thundernest Bot"
        assert (other / "only-other.txt").read_text(encoding="utf-8") == "other\n"
        assert not (tmp_path / "poison.index").exists()

    def test_executable_bytes_are_preserved_without_an_extra_commit(self, monkeypatch, tmp_path):
        """Executable mode and complete contents survive publication."""
        bare, checkout = _checkout(tmp_path, "master")
        body = bytes(index % 256 for index in range(300000))
        tool = b"#!/bin/sh\ntrue\n"
        executable = checkout / "tool"
        executable.write_bytes(tool)
        executable.chmod(0o755)
        _git(checkout, "config", "core.filemode", "true")
        _git(checkout, "add", "tool")
        _git(checkout, "commit", "-q", "-m", "tool")
        unchanged = _git(checkout, "rev-parse", "HEAD").stdout.decode().strip()
        _publish(
            checkout, bare, "stage",
            {"old.txt": b"old\n", "tool": ("exe", tool)},
            monkeypatch, tmp_path,
        )
        assert _git(checkout, "rev-parse", "HEAD").stdout.decode().strip() == unchanged
        assert stat.S_IMODE(executable.stat().st_mode) == 0o755

        payload = {"old.txt": b"old\n", "tool": ("exe", tool), "wide.bin": body}
        _publish(checkout, bare, "stage", payload, monkeypatch, tmp_path)
        assert (checkout / "wide.bin").read_bytes() == body
        assert stat.S_IMODE((checkout / "tool").stat().st_mode) == 0o755
        recorded_mode = _git(checkout, "ls-files", "-s", "tool").stdout.decode()
        assert recorded_mode.startswith("100755 ")

    def test_commit_failure_leaves_the_intent_pending(self, monkeypatch, tmp_path):
        """A rejected archive commit does not roll back the persisted intent."""
        bare, checkout, before = _prod_hook(tmp_path, "#!/bin/sh\nexit 1\n")
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Caller Name")
        observed = []
        with pytest.raises(deployment_release.ArchivePublicationError, match="^archive publication failed$") as caught:
            _release_prod(checkout, bare, monkeypatch, tmp_path, observed=observed)

        _docker, _recorded, created, checked = observed[0]
        _assert_pending(checkout, bare, before, caught.value)
        assert os.environ.get("GIT_AUTHOR_NAME") == "Caller Name"
        assert created and all(not Path(path).exists() for path in created)
        assert checked["scripts"] and all(not Path(path).exists() for path in checked["scripts"])

    def test_commit_timeout_leaves_the_intent_pending(self, monkeypatch, tmp_path):
        """A commit that exceeds its wait leaves the intent pending."""
        bare, checkout, before = _prod_hook(tmp_path, "#!/bin/sh\nsleep 30\n")
        monkeypatch.setattr(deployment_release, "_ARCHIVE_TIMEOUT", 1)
        observed = []
        with pytest.raises(
            deployment_release.ArchivePublicationError,
            match="^archive publication timed out$",
        ) as caught:
            _release_prod(checkout, bare, monkeypatch, tmp_path, observed=observed)

        _docker, _recorded, created, checked = observed[0]
        _assert_pending(checkout, bare, before, caught.value)
        assert "sleep" not in _visible(caught.value)
        assert created and all(not Path(path).exists() for path in created)
        assert checked["scripts"] and all(not Path(path).exists() for path in checked["scripts"])

    def test_commit_launch_failure_hides_the_executor_error(self, monkeypatch, tmp_path):
        """A commit that cannot start does not expose the launch error."""
        bare, checkout = _checkout(tmp_path, "prod")
        before = _git(bare, "rev-parse", "prod").stdout.decode().strip()
        _secrets(monkeypatch)
        _docker, _recorded, created, checked = _install(
            monkeypatch, tmp_path, lambda destination: _plant_files(destination, _SITE),
        )
        installed = subprocess.Popen

        def popen(args, **kwargs):
            if "commit" in list(args):
                raise OSError("secret-launch")
            return installed(args, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", popen)
        with pytest.raises(deployment_release.ArchivePublicationError, match="^archive publication failed$") as caught:
            _release_prod(checkout, bare, monkeypatch, tmp_path, install=False)

        _assert_pending(checkout, bare, before, caught.value)
        assert "secret-launch" not in _visible(caught.value)
        assert created and all(not Path(path).exists() for path in created)
        assert checked["scripts"] and all(not Path(path).exists() for path in checked["scripts"])

    def test_authentication_setup_failure_restores_the_caller(self, monkeypatch, tmp_path):
        """A failed askpass setup removes its file and leaves the environment."""
        bare, checkout = _checkout(tmp_path, "master")
        config = tmp_path / "caller.gitconfig"
        config.write_bytes(b"[user]\n\tname = Caller Name\n")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Caller Name")
        _secrets(monkeypatch)
        real_chmod = os.chmod
        created = []

        def chmod(path, mode):
            if "tb-builds-askpass-" in str(path):
                created.append(path)
                raise OSError("setup failed")
            return real_chmod(path, mode)

        monkeypatch.setattr(deployment_release.os, "chmod", chmod)
        with pytest.raises(deployment_release.ArchivePublicationError, match="^archive publication failed$"):
            deployment_release.publish_pinned_release(
                IMAGE, "stage", checkout, str(bare), "manual deployment.",
            )

        assert created and all(not Path(path).exists() for path in created)
        assert os.environ["GIT_AUTHOR_NAME"] == "Caller Name"
        assert os.environ["GIT_CONFIG_GLOBAL"] == str(config)
        assert config.read_bytes() == b"[user]\n\tname = Caller Name\n"
        assert (checkout / "old.txt").read_text(encoding="utf-8") == "old\n"

    def test_interruption_restores_authentication(self, monkeypatch, tmp_path):
        """Cancellation restores caller settings and removes the askpass program."""
        bare, checkout = _checkout(tmp_path, "master")
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Caller Name")
        _secrets(monkeypatch)
        _docker, _recorded, created, checked = _install(monkeypatch, tmp_path, lambda destination: None)

        def interrupt(_image):
            raise KeyboardInterrupt()

        monkeypatch.setattr(deployment_release, "extract_pinned_content", interrupt)
        with pytest.raises(KeyboardInterrupt):
            deployment_release.publish_pinned_release(
                IMAGE, "stage", checkout, str(bare), "manual deployment.",
            )

        assert os.environ["GIT_AUTHOR_NAME"] == "Caller Name"
        assert checked["scripts"] and all(not Path(path).exists() for path in checked["scripts"])
        assert all(not Path(path).exists() for path in created)

    def test_askpass_write_interruption_removes_its_file(self, monkeypatch, tmp_path):
        """Interrupting askpass creation deletes that file and keeps the caller's error."""
        bare, checkout = _checkout(tmp_path, "master")
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Caller Name")
        _secrets(monkeypatch)
        created = []
        real_open = builtins.open

        def tracked_open(file, mode="r", *args, **kwargs):
            if "tb-builds-askpass-" in str(file) and "w" in str(mode):
                created.append(file)
                raise KeyboardInterrupt()
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", tracked_open)
        with pytest.raises(KeyboardInterrupt) as caught:
            deployment_release.publish_pinned_release(
                IMAGE, "stage", checkout, str(bare), "manual deployment.",
            )

        assert caught.type is KeyboardInterrupt
        assert created and all(not Path(path).exists() for path in created)
        assert os.environ["GIT_AUTHOR_NAME"] == "Caller Name"
        assert os.environ.get("GIT_ASKPASS") is None
        assert _TOKEN not in _visible(caught.value)
        assert (checkout / "old.txt").read_text(encoding="utf-8") == "old\n"

    def test_askpass_chmod_interruption_removes_its_file(self, monkeypatch, tmp_path):
        """An exit during askpass chmod deletes that file and preserves the exit."""
        bare, checkout = _checkout(tmp_path, "master")
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Caller Name")
        _secrets(monkeypatch)
        created = []
        real_chmod = os.chmod

        def chmod(path, mode):
            if "tb-builds-askpass-" in str(path):
                created.append(path)
                assert _TOKEN not in Path(path).read_text(encoding="utf-8")
                raise SystemExit(3)
            return real_chmod(path, mode)

        monkeypatch.setattr(deployment_release.os, "chmod", chmod)
        with pytest.raises(SystemExit) as caught:
            deployment_release.publish_pinned_release(
                IMAGE, "stage", checkout, str(bare), "manual deployment.",
            )

        assert caught.value.code == 3
        assert created and all(not Path(path).exists() for path in created)
        assert os.environ["GIT_AUTHOR_NAME"] == "Caller Name"
        assert os.environ.get("GIT_ASKPASS") is None
        assert (checkout / "old.txt").read_text(encoding="utf-8") == "old\n"

    def test_failed_entry_keeps_its_error_when_cleanup_is_interrupted(self, monkeypatch):
        """Entry failure survives a restoration failure and an interrupted removal.

        Publication and purge share this context manager. The test removes
        its own askpass file and restores the environment if an assertion fails.
        """
        created = []
        removed = []
        restored = []
        real_mkstemp = tempfile.mkstemp
        real_unlink = os.unlink
        saved_env = _git_identity()

        def mkstemp(*args, **kwargs):
            result = real_mkstemp(*args, **kwargs)
            if kwargs.get("prefix") == "tb-builds-askpass-":
                created.append(result[1])
            return result

        def explode(_script, _email):
            raise ValueError("entry failed")

        def restore(saved):
            restored.append(saved)
            raise RuntimeError("restore failed")

        def unlink(path):
            if "tb-builds-askpass-" in str(path):
                removed.append(path)
                raise KeyboardInterrupt()
            return real_unlink(path)

        monkeypatch.setattr(tempfile, "mkstemp", mkstemp)
        monkeypatch.setattr(deployment_release, "_export_auth", explode)
        monkeypatch.setattr(deployment_release, "_restore_auth", restore)
        monkeypatch.setattr(deployment_release.os, "unlink", unlink)
        _secrets(monkeypatch)
        try:
            with pytest.raises(ValueError) as caught:
                with deployment_release.BuildsGitAuth():
                    raise AssertionError("command started")
            assert str(caught.value) == "entry failed"
            assert caught.type is ValueError
            assert any(frame.name == "explode" for frame in traceback.extract_tb(caught.value.__traceback__))
            assert restored
            assert removed
        finally:
            _restore_identity(saved_env)
            for path in created:
                try:
                    real_unlink(path)
                except OSError:
                    pass

    def test_restore_failure_still_removes_askpass(self, monkeypatch):
        """A successful command still removes askpass when restoration fails."""
        created = []
        removed = []
        real_mkstemp = tempfile.mkstemp
        real_unlink = os.unlink
        saved_env = _git_identity()

        def mkstemp(*args, **kwargs):
            result = real_mkstemp(*args, **kwargs)
            if kwargs.get("prefix") == "tb-builds-askpass-":
                created.append(result[1])
            return result

        def restore(_saved):
            raise RuntimeError("restore failed")

        def unlink(path):
            if "tb-builds-askpass-" in str(path):
                removed.append(path)
            return real_unlink(path)

        monkeypatch.setattr(tempfile, "mkstemp", mkstemp)
        monkeypatch.setattr(deployment_release, "_restore_auth", restore)
        monkeypatch.setattr(deployment_release.os, "unlink", unlink)
        _secrets(monkeypatch)
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Caller Name")
        try:
            with pytest.raises(RuntimeError, match="^restore failed$"):
                with deployment_release.BuildsGitAuth():
                    assert os.environ["GIT_ASKPASS"]
                    assert _TOKEN not in Path(os.environ["GIT_ASKPASS"]).read_text(encoding="utf-8")
            assert removed
            assert all(not Path(path).exists() for path in removed)
        finally:
            _restore_identity(saved_env)
            for path in created:
                try:
                    real_unlink(path)
                except OSError:
                    pass

    def test_interruption_during_git_stops_its_process_group(self, monkeypatch, tmp_path):
        """Cancellation reaps a running archive Git command and its child."""
        bare, checkout = _checkout(tmp_path, "prod")
        before = _git(bare, "rev-parse", "prod").stdout.decode().strip()
        marker = tmp_path / "git-children"
        hook = checkout / ".git" / "hooks" / "pre-commit"
        hook.write_text(
            "#!/bin/sh\n"
            f"echo $$ > '{marker}'\n"
            "sleep 30 &\n"
            f"echo $! >> '{marker}'\n"
            "wait\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Caller Name")
        _secrets(monkeypatch)
        _docker, _recorded, created, checked = _install(
            monkeypatch, tmp_path, lambda destination: _plant_files(destination, _SITE),
        )
        installed = subprocess.Popen
        owned = {}

        def popen(args, **kwargs):
            process = installed(args, **kwargs)
            if "commit" in list(args):
                real_wait = process.wait
                owned["process"] = process
                owned["wait"] = real_wait

                def wait(timeout=None):
                    real_wait(timeout=timeout)
                    raise OSError("secret-wait")

                def communicate(input=None, timeout=None):
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        descendants = _marker_pids(marker)
                        if len(descendants) >= 2:
                            assert process.poll() is None
                            assert all(_pid_alive(pid) for pid in descendants)
                            raise KeyboardInterrupt()
                        time.sleep(0.02)
                    raise AssertionError("archive git child did not start")

                process.communicate = communicate
                process.wait = wait
            return process

        real_killpg = os.killpg

        def killpg(pid, sig):
            real_killpg(pid, sig)
            raise OSError("secret-kill")

        monkeypatch.setattr(subprocess, "Popen", popen)
        monkeypatch.setattr(deployment_release.os, "killpg", killpg)
        try:
            with pytest.raises(KeyboardInterrupt) as caught:
                _release_prod(checkout, bare, monkeypatch, tmp_path, install=False)

            visible = _visible(caught.value)
            process = owned["process"]
            descendants = _marker_pids(marker)
            assert caught.type is KeyboardInterrupt
            assert any(
                frame.filename.endswith("test_deployment_release.py")
                for frame in traceback.extract_tb(caught.tb)
            )
            assert "secret-kill" not in visible
            assert "secret-wait" not in visible
            assert _TOKEN not in visible
            assert process.poll() is not None
            assert len(descendants) >= 2
            assert all(_descendant_gone(pid) for pid in descendants)
            _assert_pending(checkout, bare, before, caught.value)
            assert os.environ["GIT_AUTHOR_NAME"] == "Caller Name"
            assert os.environ.get("GIT_ASKPASS") is None
            assert checked["scripts"] and all(not Path(path).exists() for path in checked["scripts"])
            assert created and all(not Path(path).exists() for path in created)
        finally:
            _reap_owned(
                owned.get("process"),
                owned.get("wait"),
                _marker_pids(marker),
                real_killpg,
                os.kill,
            )

    def test_failed_git_stop_stays_bounded_and_preserves_the_interruption(self, monkeypatch, tmp_path):
        """A kill that fails before signaling does not wait out the child."""
        bare, checkout = _checkout(tmp_path, "prod")
        before = _git(bare, "rev-parse", "prod").stdout.decode().strip()
        marker = tmp_path / "git-children"
        hook = checkout / ".git" / "hooks" / "pre-commit"
        hook.write_text(
            "#!/bin/sh\n"
            f"echo $$ > '{marker}'\n"
            "sleep 30 &\n"
            f"echo $! >> '{marker}'\n"
            "wait\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        _secrets(monkeypatch)
        _install(monkeypatch, tmp_path, lambda destination: _plant_files(destination, _SITE))
        installed = subprocess.Popen
        owned = {}

        def popen(args, **kwargs):
            process = installed(args, **kwargs)
            if "commit" in list(args):
                real_wait = process.wait
                owned["process"] = process
                owned["wait"] = real_wait

                def wait(timeout=None):
                    return real_wait(timeout=timeout)

                def communicate(input=None, timeout=None):
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        descendants = _marker_pids(marker)
                        if len(descendants) >= 2:
                            assert process.poll() is None
                            assert all(_pid_alive(pid, real_kill) for pid in descendants)
                            raise KeyboardInterrupt()
                        time.sleep(0.02)
                    raise AssertionError("archive git child did not start")

                process.communicate = communicate
                process.wait = wait
            return process

        real_killpg = os.killpg
        real_kill = os.kill

        def killpg(pid, sig):
            raise OSError("secret-kill")

        def kill(pid, sig):
            raise OSError("secret-direct")

        monkeypatch.setattr(subprocess, "Popen", popen)
        monkeypatch.setattr(deployment_release.os, "killpg", killpg)
        monkeypatch.setattr(deployment_release.os, "kill", kill)
        started = time.monotonic()
        try:
            with pytest.raises(KeyboardInterrupt) as caught:
                _release_prod(checkout, bare, monkeypatch, tmp_path, install=False)

            visible = _visible(caught.value)
            process = owned["process"]
            descendants = _marker_pids(marker)
            assert time.monotonic() - started < 10
            assert caught.type is KeyboardInterrupt
            assert "secret-kill" not in visible
            assert "secret-direct" not in visible
            assert _TOKEN not in visible
            assert str(checkout) not in visible
            assert process.poll() is None
            assert descendants and all(_pid_alive(pid, real_kill) for pid in descendants)
            _assert_pending(checkout, bare, before, caught.value)
        finally:
            _reap_owned(
                owned.get("process"),
                owned.get("wait"),
                _marker_pids(marker),
                real_killpg,
                real_kill,
            )

        assert owned["process"].poll() is not None
        assert all(_descendant_gone(pid, kill=real_kill) for pid in _marker_pids(marker))

    def test_production_publication_stays_on_the_supplied_checkout(self, monkeypatch, tmp_path):
        """Production intent and archive publication ignore an unrelated repository."""
        bare, checkout = _checkout(tmp_path, "prod")
        other = tmp_path / "other"
        _init(other)
        _git(other, "config", "user.email", "other@example.com")
        _git(other, "config", "user.name", "Other")
        _git(other, "config", "other.marker", "kept")
        _git(other, "checkout", "-q", "-b", "other")
        (other / "only-other.txt").write_text("other\n")
        _git(other, "add", "only-other.txt")
        _git(other, "commit", "-q", "-m", "other")
        _git(other, "update-ref", "refs/tags/kept", "HEAD")
        (other / "only-other.txt").write_text("edited\n")
        index_bytes = (other / ".git" / "index").read_bytes()
        config_bytes = (other / ".git" / "config").read_bytes()
        refs = _git(other, "for-each-ref", "--format=%(refname) %(objectname)").stdout
        poison = tmp_path / "poison.index"
        poison.write_bytes(b"not-an-index")
        caller = tmp_path / "caller.gitconfig"
        caller.write_bytes(b"[user]\n\tname = Caller Name\n")
        caller_bytes = caller.read_bytes()
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(caller))
        monkeypatch.setenv("GIT_DIR", str(other / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(other))
        monkeypatch.setenv("GIT_COMMON_DIR", str(other / ".git"))
        monkeypatch.setenv("GIT_INDEX_FILE", str(poison))
        monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(other / ".git" / "objects"))
        monkeypatch.setenv("GIT_ALTERNATE_OBJECT_DIRECTORIES", str(other / ".git" / "objects"))
        monkeypatch.setenv("GIT_NAMESPACE", "poison")
        monkeypatch.setenv("GIT_PREFIX", str(other))
        result, _docker, recorded, _created, checked = _production(
            checkout, bare, _SITE, monkeypatch, tmp_path,
        )

        pairs = [
            (args, env)
            for args, env in zip(recorded, checked["envs"])
            if args and args[0] == "git" and env and env.get("LC_ALL") == "C"
        ]
        other_git = str(other / ".git")
        blocked = {str(poison), str(other / ".git" / "index"), str(other)}
        saved = store.read_purge_state(str(checkout), str(bare), REF, DOCUMENT)
        assert pairs
        assert all("GIT_DIR" not in env and "GIT_COMMON_DIR" not in env for _args, env in pairs)
        assert all(env.get("GIT_INDEX_FILE") not in blocked for _args, env in pairs)
        assert all(env.get("GIT_WORK_TREE") != str(other) for _args, env in pairs)
        assert all(env.get("GIT_CONFIG_GLOBAL") == str(caller) for _args, env in pairs)
        assert all(other_git not in args for args, _env in pairs)
        store_commands = [env for args, env in pairs if "credential.helper=" not in args]
        archive = [args for args, _env in pairs if "credential.helper=" in args]
        assert store_commands and all(env.get("GIT_ASKPASS") for env in store_commands)
        assert any(os.fspath(checkout) in args and "HEAD:prod" in args for args in archive)
        assert result.state.intent.identity == "run-1.1"
        assert saved.state.intent.identity == "run-1.1"
        assert set(saved.state.pending) == {"www.example", "addons.example", "updates.example"}
        assert (checkout / "wsgi.py").read_bytes() == b"redirect-a"
        assert _clean(bare, "rev-parse", "prod").stdout == _clean(checkout, "rev-parse", "HEAD").stdout
        assert _clean(checkout, "log", "-1", "--format=%an").stdout.decode().strip() == "Thundernest Bot"
        assert (other / ".git" / "index").read_bytes() == index_bytes
        assert (other / ".git" / "config").read_bytes() == config_bytes
        assert (other / "only-other.txt").read_text(encoding="utf-8") == "edited\n"
        assert _clean(other, "for-each-ref", "--format=%(refname) %(objectname)").stdout == refs
        assert poison.read_bytes() == b"not-an-index"
        assert caller.read_bytes() == caller_bytes
