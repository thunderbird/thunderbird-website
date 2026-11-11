"""Connect publication, deployment-id capture, and purge through the commands.

Git repositories, the ECS entry point, the readiness poller and evaluator, and
the Cloudflare client are real. Docker, AWS command responses, and the
Cloudflare HTTP transport are local stubs. This is not a live registry,
production ECS call, or Cloudflare cache removal.
"""

import json
import os
import sys

import cache_purge
import deployment_ecs
import deployment_polling
import deployment_purge
import purge_state_store as store
from test_cache_purge import _ScriptedCloudflare, _accepted, _forbid_http, _response
from test_deployment_cli import (
    IMAGE,
    _IDENTITY,
    _SITE,
    _TOKENS,
    _config,
    _credentials,
    _invoke,
    _publish_args,
)
from test_deployment_polling import INTENDED, OTHER_IMAGE, TASK, _definition, _deployment, _service
from test_deployment_release import _TOKEN, _checkout, _install, _plant_files, _secrets
from test_deployment_zone_purge import _RETIRED
from test_purge_state_store import DOCUMENT, REF


_CLUSTER = "thunderbird-website-prod"
_SERVICE = "thunderbird-website-prod"
_REGION = "us-west-2"
_SECRETS = (_TOKEN, *_TOKENS.values())
_REJECTED = _response(403, {"success": False, "errors": [], "messages": [], "result": None})


def _aws_program():
    """Return an AWS CLI stub that serves the JSON files named by the test."""
    return "#!" + sys.executable + """
import json
import os
import sys
from pathlib import Path

argv = sys.argv
if "update-service" in argv:
    kind = "update-service"
    source = "AWS_UPDATE"
elif "describe-services" in argv:
    kind = "describe-services"
    source = "AWS_SERVICE"
elif "describe-task-definition" in argv:
    kind = "describe-task-definition"
    source = "AWS_TASK"
else:
    kind = ""
    source = ""
record = {"command": kind, "argv": argv, "attempts": os.environ.get("AWS_MAX_ATTEMPTS", "missing")}
with Path(os.environ["AWS_LOG"]).open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record) + "\\n")
if not source:
    raise SystemExit(2)
sys.stdout.write(Path(os.environ[source]).read_text(encoding="utf-8"))
"""


def _prepare(monkeypatch, tmp_path, capsys):
    """Publish one production receipt, then capture this update's deployment id."""
    bare, checkout = _checkout(tmp_path, "prod")
    _secrets(monkeypatch)
    _credentials(monkeypatch, json.dumps(_TOKENS))
    config, configuration = _config(tmp_path)
    _install(monkeypatch, tmp_path, lambda destination: _plant_files(destination, _SITE))
    store.write_purge_state(
        str(checkout),
        str(bare),
        REF,
        DOCUMENT,
        None,
        cache_purge.PurgeState({}, frozenset({_RETIRED}), None),
    )
    receipt = tmp_path / "purge-receipt.json"
    status, out, err = _invoke(capsys, _publish_args(checkout, bare, config, receipt, "prod"))
    assert status == 0
    assert out == ""
    assert err == ""
    original = receipt.read_bytes()
    saved = store.read_purge_state(str(checkout), str(bare), REF, DOCUMENT)
    decoded = cache_purge.decode_purge_state(original.decode("utf-8"))
    assert decoded == saved.state
    assert decoded.intent.identity == _IDENTITY
    assert decoded.intent.image == IMAGE
    assert set(decoded.intent.fingerprints) == set(configuration.hostnames)
    assert saved.state.pending == set(configuration.hostnames) | {_RETIRED}
    deployment_id, log, task = _capture(monkeypatch, tmp_path, capsys)
    return checkout, bare, config, configuration, receipt, original, deployment_id, log, task


def _capture(monkeypatch, tmp_path, capsys):
    """Run the ECS entry point and return the deployment id written for the workflow."""
    stubs = tmp_path / "aws-stubs"
    stubs.mkdir()
    log = tmp_path / "aws.jsonl"
    service = tmp_path / "service.json"
    task = tmp_path / "task.json"
    update = tmp_path / "update.json"
    service.write_text(json.dumps(_service(_deployment())), encoding="utf-8")
    task.write_text(json.dumps(_definition(image=IMAGE)), encoding="utf-8")
    update.write_text(json.dumps({"service": {"deployments": [
        {"id": "ecs-svc/100", "status": "ACTIVE"},
        {"id": INTENDED, "status": "PRIMARY"},
    ]}}), encoding="utf-8")
    program = stubs / "aws"
    program.write_text(_aws_program(), encoding="utf-8")
    program.chmod(0o755)
    output = tmp_path / "github_output"
    output.write_text("image_uri=kept\n", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{stubs}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("BUILD_ENV", "prod")
    monkeypatch.setenv("AWS_REGION", _REGION)
    monkeypatch.setenv("AWS_LOG", str(log))
    monkeypatch.setenv("AWS_SERVICE", str(service))
    monkeypatch.setenv("AWS_TASK", str(task))
    monkeypatch.setenv("AWS_UPDATE", str(update))
    monkeypatch.setenv("AWS_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert deployment_ecs.main([]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    recorded = _records(log)
    assert recorded == [{
        "command": "update-service",
        "argv": recorded[0]["argv"],
        "attempts": "1",
    }]
    assert "describe-services" not in recorded[0]["argv"]
    assert os.environ["AWS_MAX_ATTEMPTS"] == "4"
    assert output.read_text(encoding="utf-8") == f"image_uri=kept\ndeployment_id={INTENDED}\n"
    return _output_value(output, "deployment_id"), log, task


def _output_value(path, name):
    """Return one key written to GITHUB_OUTPUT."""
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values[name]


def _records(log):
    """Return every AWS command the stub has served."""
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def _command(checkout, bare, config, receipt, deployment_id):
    """Return the purge command using the published receipt and captured id."""
    return [
        "purge",
        "--configuration", str(config),
        "--receipt", str(receipt),
        "--identity", _IDENTITY,
        "--image", IMAGE,
        "--workspace", str(checkout),
        "--remote", str(bare),
        "--state-ref", REF,
        "--state-path", DOCUMENT,
        "--cluster", _CLUSTER,
        "--service", _SERVICE,
        "--region", _REGION,
        "--deployment-id", deployment_id,
    ]


def _deadlines(monkeypatch, timeout=5, interval=0.05):
    """Give the real poller a short budget without replacing its decision."""
    real = deployment_polling.poll_deployment_readiness

    def poll(*args, **kwargs):
        kwargs.setdefault("timeout", timeout)
        kwargs.setdefault("interval", interval)
        return real(*args, **kwargs)

    monkeypatch.setattr(deployment_purge, "poll_deployment_readiness", poll)


def _zone_path(configuration, zone):
    """Return the purge path for one zone in the loaded configuration."""
    return f"/client/v4/zones/{configuration.zones[zone]}/purge_cache"


def _zone_hosts(configuration, zone):
    """Return the configured hostnames for one zone, in the order the client sends."""
    return tuple(sorted(host for host, name in configuration.hostnames.items() if name == zone))


def _calls(script):
    """Return the HTTP requests recorded by one Cloudflare transport stub."""
    calls = []
    for connection in script.connections:
        for method, path, body, headers in connection.calls:
            calls.append((connection.host, method, path, json.loads(body), headers))
    return calls


def _hidden(text):
    """Return whether a diagnostic contains a fixture credential."""
    return any(secret in text for secret in _SECRETS)


class TestConnectedDeployment:
    """The command entry points share one receipt, image, and deployment id."""

    def test_publication_capture_and_purge_accept_managed_hostnames(self, monkeypatch, tmp_path, capsys):
        """A ready deployment records acceptance and keeps the retired hostname."""
        prepared = _prepare(monkeypatch, tmp_path, capsys)
        checkout, bare, config, configuration, receipt, original, deployment_id, log, _task = prepared
        _deadlines(monkeypatch)
        script = _ScriptedCloudflare([_accepted("req-1"), _accepted("req-2")]).install(monkeypatch)
        status, out, err = _invoke(capsys, _command(checkout, bare, config, receipt, deployment_id))
        saved = store.read_purge_state(str(checkout), str(bare), REF, DOCUMENT)
        calls = _calls(script)
        describes = [record for record in _records(log) if record["command"] == "describe-services"]
        definitions = [record for record in _records(log) if record["command"] == "describe-task-definition"]

        assert status == 0
        assert out == ""
        assert err == ""
        assert deployment_id == INTENDED
        assert [call[:3] for call in calls] == [
            ("api.cloudflare.com", "POST", _zone_path(configuration, "example")),
            ("api.cloudflare.com", "POST", _zone_path(configuration, "example_updates")),
        ]
        assert [tuple(call[3]["hosts"]) for call in calls] == [
            _zone_hosts(configuration, "example"),
            _zone_hosts(configuration, "example_updates"),
        ]
        assert [call[4]["Authorization"] for call in calls] == [
            f"Bearer {_TOKENS['example']}",
            f"Bearer {_TOKENS['example_updates']}",
        ]
        assert _RETIRED not in {host for _host, _method, _path, body, _headers in calls for host in body["hosts"]}
        assert len(describes) == 4
        assert len(definitions) == 4
        assert all(_CLUSTER in record["argv"] and _SERVICE in record["argv"] for record in describes)
        assert all(_REGION in record["argv"] and TASK in record["argv"] for record in definitions)
        assert all(record["attempts"] == "4" for record in describes + definitions)
        assert saved.state.pending == frozenset({_RETIRED})
        assert set(saved.state.purged) == set(configuration.hostnames)
        assert receipt.read_bytes() == original
        assert not _hidden(out + err + original.decode("utf-8"))

    def test_partial_failure_recovers_without_resending_or_dropping_retired_work(
        self, monkeypatch, tmp_path, capsys,
    ):
        """A failed later zone is retried alone. A superseded intent is not purged."""
        prepared = _prepare(monkeypatch, tmp_path, capsys)
        checkout, bare, config, configuration, receipt, original, deployment_id, log, _task = prepared
        _deadlines(monkeypatch)
        failed = _ScriptedCloudflare([_accepted("req-1"), _REJECTED]).install(monkeypatch)
        status, out, err = _invoke(capsys, _command(checkout, bare, config, receipt, deployment_id))
        saved = store.read_purge_state(str(checkout), str(bare), REF, DOCUMENT)
        calls = _calls(failed)

        assert status == 1
        assert err.strip() == "Cloudflare did not accept the purge (HTTP 403)"
        assert out == ""
        assert [tuple(call[3]["hosts"]) for call in calls] == [
            _zone_hosts(configuration, "example"),
            _zone_hosts(configuration, "example_updates"),
        ]
        assert saved.state.pending == frozenset({*_zone_hosts(configuration, "example_updates"), _RETIRED})
        assert set(saved.state.purged) == set(_zone_hosts(configuration, "example"))
        assert not _hidden(out + err)
        assert receipt.read_bytes() == original

        after_failure = len(_records(log))
        resumed = _ScriptedCloudflare([_accepted("req-2")]).install(monkeypatch)
        status, out, err = _invoke(capsys, _command(checkout, bare, config, receipt, deployment_id))
        saved = store.read_purge_state(str(checkout), str(bare), REF, DOCUMENT)
        resumed_calls = _calls(resumed)
        resumed_commands = _records(log)[after_failure:]

        assert status == 0
        assert [tuple(call[3]["hosts"]) for call in resumed_calls] == [_zone_hosts(configuration, "example_updates")]
        assert [record["command"] for record in resumed_commands] == [
            "describe-services", "describe-task-definition",
            "describe-services", "describe-task-definition",
        ]
        assert saved.state.pending == frozenset({_RETIRED})
        assert set(saved.state.purged) == set(configuration.hostnames)
        assert receipt.read_bytes() == original

        superseded = cache_purge.DeploymentIntent("run-9", IMAGE, dict(saved.state.intent.fingerprints))
        store.write_purge_state(
            str(checkout),
            str(bare),
            REF,
            DOCUMENT,
            saved.revision,
            cache_purge.PurgeState(dict(saved.state.purged), saved.state.pending, superseded),
        )
        before_commands = len(_records(log))
        before_requests = len(resumed.connections)
        status, out, err = _invoke(capsys, _command(checkout, bare, config, receipt, deployment_id))
        current = store.read_purge_state(str(checkout), str(bare), REF, DOCUMENT)

        assert status == 1
        assert err.strip() == "purge state intent does not match the expected deployment"
        assert len(_records(log)) == before_commands
        assert len(resumed.connections) == before_requests
        assert current.state.intent.identity == "run-9"
        assert current.state.pending == frozenset({_RETIRED})
        assert receipt.read_bytes() == original
        assert not _hidden(out + err)

    def test_wrong_observed_image_prevents_purge(self, monkeypatch, tmp_path, capsys):
        """An image that does not match the task definition is not sent to Cloudflare."""
        prepared = _prepare(monkeypatch, tmp_path, capsys)
        checkout, bare, config, configuration, receipt, original, deployment_id, log, task = prepared
        task.write_text(json.dumps(_definition(image=OTHER_IMAGE)), encoding="utf-8")
        _deadlines(monkeypatch)
        _forbid_http(monkeypatch)
        before = len(_records(log))
        status, out, err = _invoke(capsys, _command(checkout, bare, config, receipt, deployment_id))
        saved = store.read_purge_state(str(checkout), str(bare), REF, DOCUMENT)
        observed = [record["command"] for record in _records(log)[before:]]

        assert status == 1
        assert err.strip() == "deployment readiness deadline expired"
        assert out == ""
        assert "describe-services" in observed
        assert "describe-task-definition" in observed
        assert saved.state.pending == set(configuration.hostnames) | {_RETIRED}
        assert saved.state.purged == {}
        assert receipt.read_bytes() == original
        assert not _hidden(out + err)
