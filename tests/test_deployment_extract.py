"""Extract the archived site from a digest-pinned image."""

import subprocess
import traceback
from pathlib import Path

import pytest

import cache_purge
import deployment_content
import deployment_extract as extract


REGISTRY = "123456789012.dkr.ecr.us-west-2.amazonaws.com"
IMAGE = f"{REGISTRY}/thunderbird-website-prod@sha256:{'a' * 64}"
_FILES = {
    "www.example/index.html": b"home\r\n",
    "www.example/.hidden": b"\xff\x00",
    "www.example/empty.txt": b"",
    "nested/dir/file.txt": b"nested",
}
_RULES = (
    ("www.example/", ("www.example",)),
    ("nested/", ("nested.example",)),
)
_LABEL_PREFIX = "label=deployment-artifact="


class Docker:
    """Allocate containers separately from the response the CLI delivers."""

    def __init__(self):
        self.calls = []
        self.containers = {}
        self.modes = {}
        self.pending = None
        self._count = 0

    def add_unrelated(self):
        self._count += 1
        container_id = f"{self._count:064x}"
        self.containers[container_id] = {"token": "someone-else", "removed": False}
        return container_id

    def run(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        action = args[1]
        mode = self.modes.get(action, "ok")
        if mode == "launch":
            raise OSError("secret-launch")
        if action == "create":
            return self._create(args, kwargs, mode)
        if action == "ps":
            return self._ps(args, mode)
        if action == "cp":
            return self._cp(args, kwargs, mode)
        if action == "rm":
            return self._rm(args, kwargs, mode)
        return subprocess.CompletedProcess(args, 1)

    def _create(self, args, kwargs, mode):
        if mode == "timeout":
            self._allocate(args)
            raise subprocess.TimeoutExpired(args, kwargs.get("timeout", 0))
        if mode == "nonzero":
            self._allocate(args)
            return subprocess.CompletedProcess(args, 1, stdout=b"")
        if mode == "interrupt":
            self._allocate(args)
            raise self.pending
        container_id = self._allocate(args)
        if mode == "bad_stdout":
            return subprocess.CompletedProcess(args, 0, stdout=b"not-a-container-id\n")
        return subprocess.CompletedProcess(args, 0, stdout=f"{container_id}\n".encode())

    def _allocate(self, args):
        label = args[args.index("--label") + 1]
        token = label.split("=", 1)[1]
        self._count += 1
        container_id = f"{self._count:064x}"
        self.containers[container_id] = {"token": token, "removed": False}
        return container_id

    def _ps(self, args, mode):
        if mode == "timeout":
            raise subprocess.TimeoutExpired(args, 0)
        if mode == "nonzero":
            return subprocess.CompletedProcess(args, 1, stdout=b"")
        token = args[args.index("--filter") + 1][len(_LABEL_PREFIX):]
        owned = [
            container_id
            for container_id, info in self.containers.items()
            if info["token"] == token and not info["removed"]
        ]
        stdout = "".join(f"{container_id}\n" for container_id in owned).encode()
        return subprocess.CompletedProcess(args, 0, stdout=stdout)

    def _cp(self, args, kwargs, mode):
        if mode == "timeout":
            _plant(args[-1], complete=False)
            raise subprocess.TimeoutExpired(args, kwargs.get("timeout", 0))
        if mode == "nonzero":
            _plant(args[-1], complete=False)
            return subprocess.CompletedProcess(args, 1)
        _plant(args[-1], complete=True)
        return subprocess.CompletedProcess(args, 0)

    def _rm(self, args, kwargs, mode):
        if mode == "timeout":
            raise subprocess.TimeoutExpired(args, kwargs.get("timeout", 0))
        if mode == "nonzero":
            return subprocess.CompletedProcess(args, 1)
        target = args[-1]
        info = self.containers.get(target)
        if info is not None:
            info["removed"] = True
        return subprocess.CompletedProcess(args, 0)


def _plant(destination, complete):
    """Write the bytes docker cp would have placed in the artifact directory."""
    root = Path(destination)
    files = _FILES if complete else {"partial.txt": b"partial"}
    for relative, content in files.items():
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _install(monkeypatch, tmp_path, docker):
    """Point extraction at the stub and a directory this test can observe."""
    created = []

    def mkdtemp(prefix):
        path = tmp_path / f"{prefix}{len(created)}"
        path.mkdir()
        created.append(path)
        return str(path)

    monkeypatch.setattr(extract.subprocess, "run", docker.run)
    monkeypatch.setattr(extract.tempfile, "mkdtemp", mkdtemp)
    return created


def _commands(docker):
    return [args for args, _kwargs in docker.calls]


def _owner(args):
    name = args[args.index("--name") + 1]
    label = args[args.index("--label") + 1]
    token = label.split("=", 1)[1]
    return name, token


def _visible(error):
    notes = tuple(getattr(error, "__notes__", ()))
    text = "\n".join([
        str(error),
        repr(error),
        *notes,
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
    ])
    return text, notes


class TestExtractPinnedContent:
    """One stopped container supplies the archived tree, then its resources are removed."""

    def test_pinned_image_is_extracted_for_snapshot_and_fingerprints(self, monkeypatch, tmp_path):
        """The create command receives the digest reference, and the copy can be fingerprinted."""
        docker = Docker()
        created = _install(monkeypatch, tmp_path, docker)

        with extract.extract_pinned_content(IMAGE) as root:
            snapshot = deployment_content.read_content_snapshot(root)
            fingerprints = cache_purge.content_fingerprints(snapshot, _RULES)
            assert Path(root) == created[0]

        create, copy, remove = _commands(docker)
        name, token = _owner(create)
        container_id = f"{1:064x}"
        assert create == [
            "docker", "create", "--name", name, "--label", f"deployment-artifact={token}", IMAGE,
        ]
        assert name == f"deployment-artifact-{token}"
        assert name != "extract"
        assert copy == ["docker", "cp", f"{container_id}:/var/www/html/start/.", str(created[0])]
        assert remove == ["docker", "rm", "-f", container_id]
        assert [kwargs["timeout"] for _args, kwargs in docker.calls] == [
            extract.CREATE_TIMEOUT, extract.COPY_TIMEOUT, extract.CLEANUP_TIMEOUT,
        ]
        assert docker.calls[0][1]["stdout"] is subprocess.PIPE
        assert all(
            kwargs["stderr"] is None and kwargs["stdin"] is subprocess.DEVNULL
            for _args, kwargs in docker.calls
        )
        assert snapshot == _FILES
        assert set(fingerprints) == {"www.example", "nested.example"}
        assert docker.containers[container_id]["removed"] is True
        assert not created[0].exists()

    @pytest.mark.parametrize("image", [
        f"{REGISTRY}/thunderbird-website-prod:latest",
        f"{REGISTRY}/thunderbird-website-prod:{'a' * 64}",
        f"{REGISTRY}/thunderbird-website-prod@sha256:{'A' * 64}",
        f"{REGISTRY}/thunderbird-website-prod@sha256:{'a' * 63}",
        "",
        None,
    ])
    def test_mutable_images_are_rejected_before_docker_starts(self, monkeypatch, image):
        """A tag or malformed digest does not create a container."""
        def fail_if_called(*_args, **_kwargs):
            raise AssertionError("docker started")

        monkeypatch.setattr(extract.subprocess, "run", fail_if_called)
        with pytest.raises(ValueError, match="pinned by digest"):
            with extract.extract_pinned_content(image):
                raise AssertionError("artifact was yielded")

    @pytest.mark.parametrize("mode, message", [
        ("timeout", "container creation timed out"),
        ("bad_stdout", "container creation failed"),
        ("nonzero", "container creation failed"),
    ])
    def test_uncertain_create_removes_only_the_allocated_container(self, monkeypatch, tmp_path, mode, message):
        """A container allocated before a lost create response is removed by this call's label."""
        docker = Docker()
        unrelated = docker.add_unrelated()
        docker.modes["create"] = mode
        created = _install(monkeypatch, tmp_path, docker)

        with pytest.raises(extract.ArtifactExtractionError, match=f"^{message}$") as caught:
            with extract.extract_pinned_content(IMAGE):
                raise AssertionError("artifact was yielded")

        create, listed, remove = _commands(docker)
        _name, token = _owner(create)
        owned = f"{2:064x}"
        assert listed == [
            "docker", "ps", "-aq", "--no-trunc", "--filter", f"label=deployment-artifact={token}",
        ]
        assert remove == ["docker", "rm", "-f", owned]
        assert docker.containers[owned]["removed"] is True
        assert docker.containers[unrelated]["removed"] is False
        assert "not-a-container-id" not in " ".join(remove)
        assert not created[0].exists()
        visible, notes = _visible(caught.value)
        assert notes == ()
        assert IMAGE not in visible
        assert "secret" not in visible

    @pytest.mark.parametrize("action, message", [
        ("create", "container creation timed out"),
        ("cp", "artifact copy timed out"),
        ("rm", "container removal timed out"),
    ])
    def test_command_timeouts_use_the_docker_wait(self, monkeypatch, tmp_path, action, message):
        """Create, copy, and removal each stop when their own Docker wait expires."""
        docker = Docker()
        unrelated = docker.add_unrelated()
        docker.modes[action] = "timeout"
        created = _install(monkeypatch, tmp_path, docker)
        entered = False

        with pytest.raises(extract.ArtifactExtractionError) as caught:
            with extract.extract_pinned_content(IMAGE) as root:
                entered = True
                assert Path(root) == created[0]

        visible, notes = _visible(caught.value)
        assert IMAGE not in visible
        assert docker.containers[unrelated]["removed"] is False
        if action == "rm":
            assert entered is True
            assert str(caught.value) == "artifact cleanup failed"
            assert notes == (message,)
            assert not created[0].exists()
            assert docker.calls[-1][1]["timeout"] == extract.CLEANUP_TIMEOUT
        else:
            assert entered is False
            assert str(caught.value) == message
            assert notes == ()
            assert not created[0].exists()
            owned = next(container_id for container_id, info in docker.containers.items() if info["token"] != "someone-else")
            assert docker.containers[owned]["removed"] is True
            assert _commands(docker)[-1] == ["docker", "rm", "-f", owned]

    def test_launch_failure_does_not_invent_a_container(self, monkeypatch, tmp_path):
        """A command that never starts is looked up by label and removes nothing."""
        docker = Docker()
        unrelated = docker.add_unrelated()
        docker.modes["create"] = "launch"
        created = _install(monkeypatch, tmp_path, docker)

        with pytest.raises(extract.ArtifactExtractionError, match="^container creation failed$") as caught:
            with extract.extract_pinned_content(IMAGE):
                raise AssertionError("artifact was yielded")

        create, listed = _commands(docker)
        _name, token = _owner(create)
        assert listed == [
            "docker", "ps", "-aq", "--no-trunc", "--filter", f"label=deployment-artifact={token}",
        ]
        assert "rm" not in {args[1] for args in _commands(docker)}
        assert "secret-launch" not in _visible(caught.value)[0]
        assert docker.containers[unrelated]["removed"] is False
        assert not created[0].exists()

    def test_copy_failure_leaves_no_partial_artifact(self, monkeypatch, tmp_path):
        """Files written before a failed copy are removed with the directory."""
        docker = Docker()
        docker.modes["cp"] = "nonzero"
        created = _install(monkeypatch, tmp_path, docker)

        with pytest.raises(extract.ArtifactExtractionError, match="^artifact copy failed$"):
            with extract.extract_pinned_content(IMAGE):
                raise AssertionError("artifact was yielded")

        owned = next(iter(docker.containers))
        assert _commands(docker)[-1] == ["docker", "rm", "-f", owned]
        assert docker.containers[owned]["removed"] is True
        assert not created[0].exists()
        assert list(tmp_path.rglob("partial.txt")) == []

    def test_cleanup_failure_after_success_is_raised(self, monkeypatch, tmp_path):
        """A successful extraction still reports container removal failure."""
        docker = Docker()
        docker.modes["rm"] = "nonzero"
        created = _install(monkeypatch, tmp_path, docker)

        with pytest.raises(extract.ArtifactExtractionError) as caught:
            with extract.extract_pinned_content(IMAGE) as root:
                assert deployment_content.read_content_snapshot(root)["www.example/empty.txt"] == b""

        visible, notes = _visible(caught.value)
        assert str(caught.value) == "artifact cleanup failed"
        assert notes == ("container removal failed",)
        assert "secret" not in visible
        assert not created[0].exists()

    def test_cleanup_failure_is_raised_inside_an_unrelated_except(self, monkeypatch, tmp_path):
        """An exception the caller is already handling does not hide cleanup failure."""
        docker = Docker()
        docker.modes["rm"] = "nonzero"
        _install(monkeypatch, tmp_path, docker)

        try:
            raise RuntimeError("unrelated")
        except RuntimeError as unrelated:
            with pytest.raises(extract.ArtifactExtractionError) as caught:
                with extract.extract_pinned_content(IMAGE):
                    pass
            assert str(unrelated) == "unrelated"

        assert str(caught.value) == "artifact cleanup failed"
        assert _visible(caught.value)[1] == ("container removal failed",)

    def test_consumer_exception_is_preserved(self, monkeypatch, tmp_path):
        """A reader error keeps its type and traceback when cleanup succeeds."""
        docker = Docker()
        created = _install(monkeypatch, tmp_path, docker)

        with pytest.raises(RuntimeError, match="^consumer failed$") as caught:
            with extract.extract_pinned_content(IMAGE):
                raise RuntimeError("consumer failed")

        visible, notes = _visible(caught.value)
        assert notes == ()
        assert "raise RuntimeError(\"consumer failed\")" in visible
        assert docker.containers[f"{1:064x}"]["removed"] is True
        assert not created[0].exists()

    def test_primary_failure_keeps_secondary_cleanup_notes(self, monkeypatch, tmp_path):
        """Copy failure stays primary when container and directory cleanup also fail."""
        docker = Docker()
        unrelated = docker.add_unrelated()
        docker.modes["cp"] = "nonzero"
        docker.modes["rm"] = "nonzero"
        created = _install(monkeypatch, tmp_path, docker)

        def fail_rmtree(_path):
            raise OSError("secret-cleanup-disk")

        monkeypatch.setattr(extract.shutil, "rmtree", fail_rmtree)
        with pytest.raises(extract.ArtifactExtractionError) as caught:
            with extract.extract_pinned_content(IMAGE):
                raise AssertionError("artifact was yielded")

        visible, notes = _visible(caught.value)
        assert str(caught.value) == "artifact copy failed"
        assert notes == ("container removal failed", "artifact directory cleanup failed")
        assert "secret-cleanup-disk" not in visible
        assert IMAGE not in visible
        assert caught.value.__cause__ is None
        owned = next(container_id for container_id, info in docker.containers.items() if info["token"] != "someone-else")
        assert _commands(docker)[-1] == ["docker", "rm", "-f", owned]
        assert docker.containers[unrelated]["removed"] is False
        assert created[0].exists()

    @pytest.mark.parametrize("kind", [KeyboardInterrupt, SystemExit])
    @pytest.mark.parametrize("cleanup_fails", [False, True])
    def test_consumer_interruption_keeps_its_identity(self, monkeypatch, tmp_path, kind, cleanup_fails):
        """Cancellation or exit survives cleanup and is not replaced."""
        docker = Docker()
        unrelated = docker.add_unrelated()
        if cleanup_fails:
            docker.modes["rm"] = "nonzero"
        created = _install(monkeypatch, tmp_path, docker)
        interruption = kind("stop")

        with pytest.raises(kind) as caught:
            with extract.extract_pinned_content(IMAGE):
                raise interruption

        visible, notes = _visible(caught.value)
        owned = f"{2:064x}"
        assert caught.value is interruption
        assert "raise interruption" in visible
        assert IMAGE not in visible
        assert docker.containers[unrelated]["removed"] is False
        assert not created[0].exists()
        if cleanup_fails:
            assert notes == ("container removal failed",)
            assert docker.containers[owned]["removed"] is False
        else:
            assert notes == ()
            assert docker.containers[owned]["removed"] is True

    @pytest.mark.parametrize("kind", [KeyboardInterrupt, SystemExit])
    def test_interrupted_create_removes_only_the_allocated_container(self, monkeypatch, tmp_path, kind):
        """A labeled container allocated before create returns is still removed."""
        docker = Docker()
        unrelated = docker.add_unrelated()
        docker.modes["create"] = "interrupt"
        docker.pending = kind("stop")
        created = _install(monkeypatch, tmp_path, docker)

        with pytest.raises(kind) as caught:
            with extract.extract_pinned_content(IMAGE):
                raise AssertionError("artifact was yielded")

        create, listed, remove = _commands(docker)
        _name, token = _owner(create)
        owned = f"{2:064x}"
        visible, notes = _visible(caught.value)
        assert caught.value is docker.pending
        assert notes == ()
        assert "raise self.pending" in visible
        assert IMAGE not in visible
        assert listed == [
            "docker", "ps", "-aq", "--no-trunc", "--filter", f"label=deployment-artifact={token}",
        ]
        assert remove == ["docker", "rm", "-f", owned]
        assert docker.containers[owned]["removed"] is True
        assert docker.containers[unrelated]["removed"] is False
        assert not created[0].exists()
