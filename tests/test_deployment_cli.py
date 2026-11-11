"""Command entry points for publication and purge."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import cache_purge
import deployment_cli
import deployment_purge
import deployment_release
import purge_state_store as store
from deployment_readiness import DeploymentEvaluation
from test_deployment_release import (
    IMAGE,
    OTHER_IMAGE,
    _TOKEN,
    _TOKENS,
    _checkout,
    _docker_commands,
    _install,
    _plant_files,
    _secrets,
)
from test_purge_state_store import DOCUMENT, REF, _git, _layout


_EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "examples" / "cache-purge.example.json"
_SECRET = "secret-zone-token"
_IDENTITY = "1001.2"
_DEPLOYMENT = "explicit-deploy-42"
_RETIRED = "retired.example"
_SITE = {
    "www.example/index.html": b"home\r\n",
    "www.example/en-US/maintenance/index.html": b"down",
    "wsgi.py": b"redirect-a",
}


def _invoke(capsys, arguments):
    """Run one command and return its status and captured streams."""
    status = deployment_cli.main(arguments)
    captured = capsys.readouterr()
    return status, captured.out, captured.err


def _visible(out, err):
    """Return the diagnostics a command printed."""
    return f"{out}\n{err}"


def _config(directory):
    """Write the example at an explicit path and return the loaded configuration."""
    path = directory / "supplied-cache-purge.json"
    document = _EXAMPLE.read_text(encoding="utf-8")
    path.write_text(document, encoding="utf-8")
    return path, cache_purge.load_purge_config(document)


def _credentials(monkeypatch, document):
    """Install one credential document, or leave the variable unset."""
    if document is None:
        monkeypatch.delenv(deployment_cli.ZONE_CREDENTIALS, raising=False)
        return
    monkeypatch.setenv(deployment_cli.ZONE_CREDENTIALS, document)


def _publish_args(checkout, remote, config, receipt, environment):
    """Return the explicit inputs for one publication command."""
    return [
        "publish",
        "--image", IMAGE,
        "--environment", environment,
        "--checkout", str(checkout),
        "--remote", str(remote),
        "--message", _IDENTITY,
        "--configuration", str(config),
        "--identity", _IDENTITY,
        "--state-ref", REF,
        "--state-path", DOCUMENT,
        "--receipt", str(receipt),
    ]


def _purge_args(workspace, remote, config, receipt, identity=None, image=None):
    """Return the explicit inputs for one purge command."""
    return [
        "purge",
        "--configuration", str(config),
        "--receipt", str(receipt),
        "--identity", _IDENTITY if identity is None else identity,
        "--image", IMAGE if image is None else image,
        "--workspace", str(workspace),
        "--remote", str(remote),
        "--state-ref", REF,
        "--state-path", DOCUMENT,
        "--cluster", "example-cluster",
        "--service", "example-service",
        "--region", "example-region",
        "--deployment-id", _DEPLOYMENT,
    ]


class TestPublishCommand:
    """Stage publishes an archive. Production also leaves a completed receipt."""

    def test_stage_publishes_without_purge_inputs(self, monkeypatch, tmp_path, capsys):
        """Stage replaces the archive and does not read purge inputs or write a receipt."""
        bare, checkout = _checkout(tmp_path, "master")
        _secrets(monkeypatch)
        _credentials(monkeypatch, f'{{"example":"{_SECRET}"}}')
        _docker, recorded, _created, _checked = _install(
            monkeypatch,
            tmp_path,
            lambda destination: _plant_files(destination, {"index.html": b"stage\n"}),
        )
        receipt = tmp_path / "purge-receipt.json"

        def forbid_credentials():
            raise AssertionError("credentials were read")

        def forbid_configuration(_document):
            raise AssertionError("configuration was read")

        monkeypatch.setattr(deployment_cli, "_zone_credentials", forbid_credentials)
        monkeypatch.setattr(deployment_cli, "load_purge_config", forbid_configuration)
        status, out, err = _invoke(capsys, [
            "publish",
            "--image", IMAGE,
            "--environment", "stage",
            "--checkout", str(checkout),
            "--remote", str(bare),
            "--message", _IDENTITY,
        ])

        assert status == 0
        assert out == ""
        assert err == ""
        assert not receipt.exists()
        assert (checkout / "index.html").read_bytes() == b"stage\n"
        assert (checkout / "README.md").read_text(encoding="utf-8") == "readme-sentinel\n"
        assert not (checkout / "old.txt").exists()
        assert _git(bare, "rev-parse", "--verify", "-q", REF, check=False).returncode != 0
        assert len(_docker_commands(recorded, "create")) == 1
        assert _SECRET not in _visible(out, err)

        receipt.write_text("leave-me\n", encoding="utf-8")
        status, out, err = _invoke(capsys, [
            "publish",
            "--image", IMAGE,
            "--environment", "stage",
            "--checkout", str(checkout),
            "--remote", str(bare),
            "--message", _IDENTITY,
            "--receipt", str(receipt),
        ])
        assert status == 1
        assert err.strip() == "stage publication does not accept purge inputs"
        assert receipt.read_text(encoding="utf-8") == "leave-me\n"
        assert len(_docker_commands(recorded, "create")) == 1

    def test_production_receipt_round_trip(self, monkeypatch, tmp_path, capsys):
        """Production publication returns success only with a secret-free receipt."""
        bare, checkout = _checkout(tmp_path, "prod")
        _secrets(monkeypatch)
        _credentials(monkeypatch, json.dumps(_TOKENS))
        config, configuration = _config(tmp_path)
        _install(
            monkeypatch,
            tmp_path,
            lambda destination: _plant_files(destination, _SITE),
        )
        receipt = tmp_path / "purge-receipt.json"
        status, out, err = _invoke(
            capsys,
            _publish_args(checkout, bare, config, receipt, "prod"),
        )

        saved = store.read_purge_state(str(checkout), str(bare), REF, DOCUMENT)
        document = receipt.read_text(encoding="utf-8")
        assert status == 0
        assert out == ""
        assert err == ""
        assert document == cache_purge.encode_purge_state(saved.state)
        assert cache_purge.decode_purge_state(document) == saved.state
        assert saved.state.intent.identity == _IDENTITY
        assert saved.state.intent.image == IMAGE
        assert set(saved.state.pending) == set(configuration.hostnames)
        assert list(tmp_path.glob("tb-purge-receipt-*")) == []
        assert _SECRET not in document
        assert "example-zone-token" not in document
        assert "updates-zone-token" not in document
        assert _TOKEN not in document

    def test_missing_configuration_or_credentials_skip_extraction(self, monkeypatch, tmp_path, capsys):
        """Production rejects a missing configuration or credential before publication."""
        bare, checkout = _checkout(tmp_path, "prod")
        _secrets(monkeypatch)
        config, _configuration = _config(tmp_path)
        receipt = tmp_path / "purge-receipt.json"
        _credentials(monkeypatch, json.dumps(_TOKENS))

        def forbid_publish(*_args, **_kwargs):
            raise AssertionError("publication started")

        monkeypatch.setattr(deployment_cli, "publish_pinned_release", forbid_publish)
        missing_config = _publish_args(checkout, bare, config, receipt, "prod")
        missing_config[missing_config.index("--configuration") + 1] = str(tmp_path / "absent.json")
        status, out, err = _invoke(capsys, missing_config)

        assert status == 1
        assert err.strip() == "purge configuration is required"
        assert "publication started" not in err
        assert not receipt.exists()
        assert (checkout / "old.txt").read_text(encoding="utf-8") == "old\n"

        _credentials(monkeypatch, None)
        status, out, err = _invoke(capsys, _publish_args(checkout, bare, config, receipt, "prod"))
        assert status == 1
        assert err.strip() == "zone credentials are required"
        assert "publication started" not in err
        assert not receipt.exists()

    @pytest.mark.parametrize(("document", "message"), [
        ('{"example":"secret-zone-token"', "malformed JSON"),
        (
            '{"example":"secret-zone-token","example":"another-zone-token"}',
            "duplicate key in zone credentials",
        ),
        ('{"example":"secret-zone-token "}', "api_token is required"),
        ('["secret-zone-token"]', "zone credentials must be an object"),
    ])
    def test_bad_credentials_are_not_echoed(self, monkeypatch, tmp_path, capsys, document, message):
        """A bad credential document fails before extraction and is not printed."""
        bare, checkout = _checkout(tmp_path, "prod")
        _secrets(monkeypatch)
        config, _configuration = _config(tmp_path)
        receipt = tmp_path / "purge-receipt.json"
        _credentials(monkeypatch, document)

        def forbid_publish(*_args, **_kwargs):
            raise AssertionError("publication started")

        monkeypatch.setattr(deployment_cli, "publish_pinned_release", forbid_publish)
        status, out, err = _invoke(capsys, _publish_args(checkout, bare, config, receipt, "prod"))

        assert status == 1
        assert err.strip() == message
        assert "publication started" not in _visible(out, err)
        assert _SECRET not in _visible(out, err)
        assert not receipt.exists()

    def test_failed_publication_writes_no_receipt(self, monkeypatch, tmp_path, capsys):
        """A failed extraction is a nonzero command and leaves no receipt."""
        bare, checkout = _checkout(tmp_path, "prod")
        _secrets(monkeypatch)
        _credentials(monkeypatch, json.dumps({"example": _SECRET, "example_updates": "updates-zone-token"}))
        config, _configuration = _config(tmp_path)
        receipt = tmp_path / "purge-receipt.json"
        recorded = []
        real_run = subprocess.run

        def run(args, **kwargs):
            if args and args[0] == "docker":
                recorded.append(list(args))
                if len(args) > 1 and args[1] == "ps":
                    return subprocess.CompletedProcess(args, 0, stdout=b"")
                if len(args) > 1 and args[1] == "create":
                    return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"")
                return subprocess.CompletedProcess(args, 0, stdout=b"")
            return real_run(args, **kwargs)

        monkeypatch.setattr(subprocess, "run", run)
        status, out, err = _invoke(capsys, _publish_args(checkout, bare, config, receipt, "prod"))

        assert status == 1
        assert err.strip() == "container creation failed"
        assert not receipt.exists()
        assert list(tmp_path.glob("tb-purge-receipt-*")) == []
        assert (checkout / "old.txt").read_text(encoding="utf-8") == "old\n"
        assert _git(bare, "rev-parse", "--verify", "-q", REF, check=False).returncode != 0
        assert recorded[0][1] == "create"
        assert _SECRET not in _visible(out, err)
        assert str(bare) not in _visible(out, err)

    def test_failed_receipt_write_is_nonzero(self, monkeypatch, tmp_path, capsys):
        """Publication can finish while a failed receipt still fails the command."""
        bare, checkout = _checkout(tmp_path, "prod")
        _secrets(monkeypatch)
        _credentials(monkeypatch, json.dumps(_TOKENS))
        config, _configuration = _config(tmp_path)
        _install(monkeypatch, tmp_path, lambda destination: _plant_files(destination, _SITE))
        receipt = tmp_path / "purge-receipt.json"
        receipt.write_text("previous-receipt\n", encoding="utf-8")

        real_replace = os.replace
        real_mkstemp = tempfile.mkstemp
        created = []

        def fail_replace(source, destination):
            if os.path.abspath(destination) == os.path.abspath(receipt):
                raise OSError(f"replace failed for {_SECRET} response body")
            return real_replace(source, destination)

        def spy_mkstemp(*args, **kwargs):
            result = real_mkstemp(*args, **kwargs)
            if kwargs.get("prefix") == "tb-purge-receipt-":
                created.append(result[1])
            return result

        monkeypatch.setattr(os, "replace", fail_replace)
        monkeypatch.setattr(tempfile, "mkstemp", spy_mkstemp)
        status, out, err = _invoke(capsys, _publish_args(checkout, bare, config, receipt, "prod"))
        saved = store.read_purge_state(str(checkout), str(bare), REF, DOCUMENT)

        assert status == 1
        assert err.strip() == "receipt could not be written"
        assert _SECRET not in _visible(out, err)
        assert "response body" not in _visible(out, err)
        assert "Traceback" not in err
        assert receipt.read_text(encoding="utf-8") == "previous-receipt\n"
        assert created
        assert all(not os.path.exists(path) for path in created)
        assert saved.state.intent.identity == _IDENTITY
        assert not (checkout / "old.txt").exists()
        assert "example-zone-token" not in _visible(out, err)

    def test_unexpected_failure_hides_credentials(self, monkeypatch, capsys):
        """An unexpected exception is replaced by a fixed diagnostic."""
        monkeypatch.setenv(deployment_cli.ZONE_CREDENTIALS, f'{{"example":"{_SECRET}"}}')

        def explode(*_args, **_kwargs):
            observed = os.environ[deployment_cli.ZONE_CREDENTIALS]
            raise RuntimeError(f"Traceback response body {observed}")

        monkeypatch.setattr(deployment_cli, "publish_pinned_release", explode)
        status, out, err = _invoke(capsys, [
            "publish",
            "--image", IMAGE,
            "--environment", "stage",
            "--checkout", "/tmp/builds",
            "--remote", "https://example.invalid/builds.git",
            "--message", _IDENTITY,
        ])

        assert status == 1
        assert out == ""
        assert err.strip() == "deployment command failed"
        assert _SECRET not in _visible(out, err)
        assert "Traceback" not in err
        assert "response body" not in err

    def test_documented_errors_remain_useful(self, monkeypatch, capsys):
        """Validation and coordinator errors keep their sanitized messages."""
        arguments = [
            "publish",
            "--image", IMAGE,
            "--environment", "stage",
            "--checkout", "/tmp/builds",
            "--remote", "https://example.invalid/builds.git",
            "--message", _IDENTITY,
        ]

        def invalid(*_args, **_kwargs):
            try:
                raise RuntimeError(_SECRET)
            except RuntimeError as error:
                raise ValueError("api_token is required") from error

        monkeypatch.setattr(deployment_cli, "publish_pinned_release", invalid)
        status, out, err = _invoke(capsys, arguments)
        assert status == 1
        assert err.strip() == "api_token is required"
        assert _SECRET not in _visible(out, err)

        def archived(*_args, **_kwargs):
            raise deployment_release.ArchivePublicationError("archive publication failed")

        monkeypatch.setattr(deployment_cli, "publish_pinned_release", archived)
        status, out, err = _invoke(capsys, arguments)
        assert status == 1
        assert err.strip() == "archive publication failed"
        assert _SECRET not in _visible(out, err)

    def test_interrupt_and_usage_exit_propagate(self, monkeypatch, capsys):
        """Cancellation and argparse exits are not rewritten as command failures."""
        def interrupt(*_args, **_kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(deployment_cli, "publish_pinned_release", interrupt)
        with pytest.raises(KeyboardInterrupt):
            deployment_cli.main([
                "publish",
                "--image", IMAGE,
                "--environment", "stage",
                "--checkout", "/tmp/builds",
                "--remote", "https://example.invalid/builds.git",
                "--message", _IDENTITY,
            ])
        with pytest.raises(SystemExit) as caught:
            deployment_cli.main(["publish"])
        assert caught.value.code not in (0, None)
        capsys.readouterr()


class TestPurgeCommand:
    """The receipt selects the intent. Remote state selects the pending work."""

    def test_missing_malformed_or_intentless_receipt_is_not_purged(self, monkeypatch, tmp_path, capsys):
        """An unusable receipt fails before AWS, Cloudflare, or purge state."""
        config, _configuration = _config(tmp_path)
        receipt = tmp_path / "purge-receipt.json"
        _credentials(monkeypatch, json.dumps(_TOKENS))

        def forbid_purge(*_args, **_kwargs):
            raise AssertionError("purge started")

        monkeypatch.setattr(deployment_cli, "purge_ready_deployment", forbid_purge)
        status, out, err = _invoke(capsys, _purge_args(tmp_path, tmp_path / "remote.git", config, receipt))
        assert status == 1
        assert err.strip() == "receipt is required"
        assert "purge started" not in err

        receipt.write_text(f'{{"{_SECRET}":', encoding="utf-8")
        status, out, err = _invoke(capsys, _purge_args(tmp_path, tmp_path / "remote.git", config, receipt))
        assert status == 1
        assert err.strip() == "malformed JSON"
        assert _SECRET not in _visible(out, err)

        empty = cache_purge.PurgeState({}, frozenset(), None)
        receipt.write_text(cache_purge.encode_purge_state(empty), encoding="utf-8")
        status, out, err = _invoke(capsys, _purge_args(tmp_path, tmp_path / "remote.git", config, receipt))
        assert status == 1
        assert err.strip() == "receipt intent is required"
        assert "purge started" not in err

    @pytest.mark.parametrize(("identity", "image", "message"), [
        ("run-9", IMAGE, "receipt does not match this deployment"),
        (_IDENTITY, OTHER_IMAGE, "receipt does not match this deployment"),
        (_IDENTITY, "website:latest", "image must be pinned by digest"),
    ])
    def test_identity_or_image_mismatch_skips_services(
        self, monkeypatch, tmp_path, capsys, identity, image, message,
    ):
        """The caller's identity and pinned image are checked before any service call."""
        config, configuration = _config(tmp_path)
        fingerprints = cache_purge.content_fingerprints(_SITE, configuration.rules)
        intent = cache_purge.DeploymentIntent(_IDENTITY, IMAGE, fingerprints)
        state = cache_purge.PurgeState({}, frozenset(fingerprints), intent)
        receipt = tmp_path / "purge-receipt.json"
        receipt.write_text(cache_purge.encode_purge_state(state), encoding="utf-8")
        _credentials(monkeypatch, json.dumps({"example": _SECRET, "example_updates": _SECRET}))

        def forbid_purge(*_args, **_kwargs):
            raise AssertionError("purge started")

        monkeypatch.setattr(deployment_cli, "purge_ready_deployment", forbid_purge)
        status, out, err = _invoke(
            capsys,
            _purge_args(tmp_path, tmp_path / "remote.git", config, receipt, identity, image),
        )

        assert status == 1
        assert err.strip() == message
        assert "purge started" not in _visible(out, err)
        assert _SECRET not in _visible(out, err)
        assert receipt.read_text(encoding="utf-8") == cache_purge.encode_purge_state(state)

    def test_explicit_deployment_uses_remote_pending_work(self, monkeypatch, tmp_path, capsys):
        """The ECS deployment id is forwarded, and the receipt's maps are not replayed."""
        _reader, writer, remote = _layout(tmp_path)
        config, configuration = _config(tmp_path)
        fingerprints = cache_purge.content_fingerprints(_SITE, configuration.rules)
        intent = cache_purge.DeploymentIntent(_IDENTITY, IMAGE, fingerprints)
        remote_state = cache_purge.PurgeState({}, frozenset(set(fingerprints) | {_RETIRED}), intent)
        store.write_purge_state(str(writer), str(remote), REF, DOCUMENT, None, remote_state)
        claimed = cache_purge.PurgeState(dict(fingerprints), frozenset(), intent)
        receipt = tmp_path / "purge-receipt.json"
        receipt.write_text(cache_purge.encode_purge_state(claimed), encoding="utf-8")
        original = receipt.read_bytes()
        _credentials(monkeypatch, json.dumps({"example": _SECRET, "example_updates": "updates-zone-token"}))
        polls = []
        purges = []

        def poll(*args, **kwargs):
            polls.append((args, kwargs))
            return DeploymentEvaluation("ready")

        def purge(zone_id, hostnames, api_token):
            purges.append((zone_id, tuple(hostnames), api_token))
            return cache_purge.PurgeAcceptance("req-1")

        monkeypatch.setattr(deployment_purge, "poll_deployment_readiness", poll)
        monkeypatch.setattr(deployment_purge, "purge_hostnames", purge)
        status, out, err = _invoke(capsys, _purge_args(writer, remote, config, receipt))
        saved = store.read_purge_state(str(writer), str(remote), REF, DOCUMENT)
        sent = [hostname for _zone, hosts, _token in purges for hostname in hosts]

        assert status == 0
        assert out == ""
        assert err == ""
        assert receipt.read_bytes() == original
        assert polls == [
            (("example-cluster", "example-service", "example-region", _DEPLOYMENT, IMAGE), {}),
            (("example-cluster", "example-service", "example-region", _DEPLOYMENT, IMAGE), {}),
        ]
        assert sent == ["addons.example", "www.example", "updates.example"]
        assert _RETIRED not in sent
        assert "PRIMARY" not in _visible(out, err)
        assert saved.state.pending == frozenset({_RETIRED})
        assert set(saved.state.purged) == set(fingerprints)
        assert _SECRET not in _visible(out, err)
        assert "secret-remote-token" not in _visible(out, err)

    def test_missing_purge_credentials_skip_services(self, monkeypatch, tmp_path, capsys):
        """Purge credentials are required before the coordinator reads state or calls AWS."""
        config, _configuration = _config(tmp_path)
        receipt = tmp_path / "purge-receipt.json"
        receipt.write_text("{}", encoding="utf-8")
        _credentials(monkeypatch, None)

        def forbid_purge(*_args, **_kwargs):
            raise AssertionError("purge started")

        monkeypatch.setattr(deployment_cli, "purge_ready_deployment", forbid_purge)
        status, out, err = _invoke(capsys, _purge_args(tmp_path, tmp_path / "remote.git", config, receipt))

        assert status == 1
        assert err.strip() == "zone credentials are required"
        assert "purge started" not in err
        assert receipt.read_text(encoding="utf-8") == "{}"


def test_process_exits_nonzero(tmp_path):
    """A process invocation fails without accepting a token argument."""
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "deployment_cli.py"), "publish"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "--api-token" not in completed.stderr
    assert _SECRET not in completed.stdout + completed.stderr
