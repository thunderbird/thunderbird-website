"""Publication and production purge wiring in the deploy workflow.

Static checks compare workflow fields. They do not execute GitHub's
expression engine. Script checks are argument handoffs through local
stubs, or validation by the real deployment CLI. The deployment-id helper
is exercised directly so response checks do not depend on ``timeout`` or
``rm``.
"""

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import yaml

import deployment_ecs


_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = _ROOT / ".github" / "workflows" / "deploy.yml"
_EXAMPLE = _ROOT / "docs" / "examples" / "cache-purge.example.json"
_ENVIRONMENT = (
    "${{ github.event.inputs.environment || github.event.action || "
    "(github.ref_name == 'prod' && 'prod') || 'stage' }}"
)
_CANCEL = (
    "${{ (github.event.inputs.environment || github.event.action || "
    "(github.ref_name == 'prod' && 'prod') || 'stage') != 'prod' }}"
)
_MESSAGE = (
    "github.event.client_payload.message || (github.event_name == 'push' && "
    "format('thunderbird-website {0} push.', github.ref_name)) || 'manual deployment.'"
)
_BRANCH = "env.DEPLOY_ENV == 'prod' && 'prod' || 'master'"
_IMAGE = (
    "123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod@sha256:"
    + "ab" * 32
)
_KEY = "builds-key-secret"
_EMAIL = "bot@example.com"
_CREDENTIALS = '{"example":"secret-zone-token"}'
_CONFIG = '{"version":1,"marker":"secret-zone-token","unsafe":"$(id)"}'
_DEPLOYMENT = "ecs-svc/200"
_REGION = "us-west-2"
_MARKER = "secret-zone-token"
_TIMEOUT = 30
_CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
_ECR = "aws-actions/amazon-ecr-login@03f1aad4c6c7ffd436567f42f9384779290529bd"
_PULUMI = "pulumi/actions@96c7761824268174e0d2a4e8c7d75671eebd24a7"
_REMOVED = (
    "docker create",
    "docker cp",
    "x-access-token",
    "git remote set-url",
    "find . -maxdepth",
    "--name extract",
    "deployment_cli.py purge",
    "docs/examples/cache-purge.example.json",
)


def _workflow():
    """Return the parsed deploy workflow."""
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(parsed):
    """Return the workflow trigger mapping.

    PyYAML 1.1 loads the unquoted key ``on`` as boolean true.
    """
    if "on" in parsed:
        return parsed["on"]
    if True in parsed:
        return parsed[True]
    raise AssertionError("workflow triggers are missing")


def _step(steps, name):
    """Return one named step."""
    for step in steps:
        if step.get("name") == name:
            return step
    raise AssertionError(name)


def _inside(value):
    """Return the text inside one exact ``${{ }}`` binding."""
    prefix = "${{ "
    suffix = " }}"
    if not (isinstance(value, str) and value.startswith(prefix) and value.endswith(suffix)):
        raise AssertionError(value)
    return value[len(prefix):-len(suffix)]


def _commands(log):
    """Return recorded stub invocations as basename plus arguments."""
    if not log.exists():
        return []
    commands = []
    for line in log.read_text(encoding="utf-8").splitlines():
        argv = json.loads(line)
        commands.append([Path(argv[0]).name, *argv[1:]])
    return commands


def _install_stub(directory, name, log):
    """Install one recording executable that does not use a network."""
    body = f"""#!{sys.executable}
import json
import os
import sys
from pathlib import Path

log = Path(os.environ["STUB_LOG"])
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv) + "\\n")
name = Path(sys.argv[0]).name
if name == "git" and len(sys.argv) > 1 and sys.argv[1] == "clone":
    Path(sys.argv[-1]).mkdir(parents=True)
status = os.environ.get("STUB_GIT_STATUS" if name == "git" else "STUB_DOCKER_STATUS", "0")
if name == "python3":
    status = os.environ.get("STUB_PYTHON_STATUS", "0")
raise SystemExit(int(status))
"""
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _bash():
    """Return bash, which the publication script requires."""
    bash = shutil.which("bash")
    if bash is None:
        raise AssertionError("bash is required to run the publication script")
    return bash


def _run(script, env, cwd):
    """Run one publication script and bound the wait."""
    completed = subprocess.run(
        [_bash(), str(script)],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=_TIMEOUT,
        check=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


def _publication_script(tmp_path):
    """Write the workflow's publication script to a temporary file."""
    parsed = _workflow()
    step = _step(parsed["jobs"]["deploy"]["steps"], "Publish to tb-website-builds")
    script = tmp_path / "publish.sh"
    script.write_text(step["run"], encoding="utf-8")
    return script


def _run_stubbed(tmp_path, deploy_env, branch, extra=None, python_status="0"):
    """Run publication with git, docker, and python3 stubs.

    This checks argument handoff and shell behavior. It does not run the CLI.
    """
    runner = tmp_path / "runner"
    stubs = tmp_path / "stubs"
    runner.mkdir()
    stubs.mkdir()
    log = tmp_path / "commands.jsonl"
    for name in ("git", "docker", "python3"):
        _install_stub(stubs, name, log)
    env = {
        "PATH": str(stubs),
        "RUNNER_TEMP": str(runner),
        "DEPLOY_ENV": deploy_env,
        "TB_BUILDS_BRANCH": branch,
        "IMAGE_URI": _IMAGE,
        "BUILD_MESSAGE": "manual deployment.",
        "STUB_LOG": str(log),
        "STUB_PYTHON_STATUS": python_status,
        "STUB_GIT_STATUS": "0",
        "STUB_DOCKER_STATUS": "0",
    }
    if extra:
        env.update(extra)
    status, visible = _run(_publication_script(tmp_path), env, tmp_path)
    return status, visible, _commands(log), runner


def _run_real_cli(tmp_path, config, credentials):
    """Run production publication with the real CLI and local command stubs.

    Git and Docker are stubs. ``python3`` is this interpreter, so CLI
    validation actually runs. GitHub's empty bindings are empty strings.
    """
    runner = tmp_path / "runner"
    stubs = tmp_path / "stubs"
    runner.mkdir()
    stubs.mkdir()
    log = tmp_path / "commands.jsonl"
    for name in ("git", "docker"):
        _install_stub(stubs, name, log)
    (stubs / "python3").symlink_to(sys.executable)
    env = {
        "PATH": str(stubs),
        "RUNNER_TEMP": str(runner),
        "DEPLOY_ENV": "prod",
        "TB_BUILDS_BRANCH": "prod",
        "IMAGE_URI": _IMAGE,
        "BUILD_MESSAGE": "manual deployment.",
        "GITHUB_RUN_ID": "1001",
        "GITHUB_RUN_ATTEMPT": "2",
        "TB_BUILDS_KEY": _KEY,
        "TB_BUILDS_GIT_EMAIL": _EMAIL,
        "CACHE_PURGE_CONFIG": config,
        "CACHE_PURGE_ZONE_CREDENTIALS": credentials,
        "STUB_LOG": str(log),
        "STUB_GIT_STATUS": "0",
        "STUB_DOCKER_STATUS": "0",
    }
    status, visible = _run(_publication_script(tmp_path), env, _ROOT)
    return status, visible, _commands(log), runner


def _install_aws(directory, log):
    """Install an AWS stub that writes a fixture response and records its arguments.

    This is a handoff stub. It exits immediately and does not exercise the
    command timeout.
    """
    body = f"""#!{sys.executable}
import json
import os
import sys
from pathlib import Path

log = Path(os.environ["STUB_LOG"])
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({{
        "argv": sys.argv,
        "pager": os.environ.get("AWS_PAGER", "missing"),
        "prompt": os.environ.get("AWS_CLI_AUTO_PROMPT", "missing"),
        "attempts": os.environ.get("AWS_MAX_ATTEMPTS", "missing"),
    }}) + "\\n")
sys.stdout.write(os.environ.get("STUB_AWS_BODY", ""))
sys.stderr.write(os.environ.get("STUB_AWS_STDERR", ""))
raise SystemExit(int(os.environ.get("STUB_AWS_STATUS", "0")))
"""
    path = directory / "aws"
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _aws_records(log):
    """Return the stub's recorded invocations."""
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _step_script(tmp_path, name):
    """Write one named workflow step to a temporary script."""
    parsed = _workflow()
    step = _step(parsed["jobs"]["deploy"]["steps"], name)
    script = tmp_path / "step.sh"
    script.write_text(step["run"], encoding="utf-8")
    return script


def _update_response(deployments):
    """Return one update-service body with a marker that must stay out of diagnostics."""
    return json.dumps({
        "service": {
            "serviceName": "thunderbird-website-prod",
            "secretMarker": _MARKER,
            "deployments": deployments,
        }
    })


def _run_ecs(monkeypatch, capsys, tmp_path, body, aws_status="0", stderr=""):
    """Run the real id helper with a stubbed AWS CLI.

    The stub records the command and returns immediately. This does not
    verify the timeout. ``PATH`` contains only the stub directory.
    """
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    log = tmp_path / "commands.jsonl"
    _install_aws(stubs, log)
    output = tmp_path / "github_output"
    output.write_text("image_uri=kept\n", encoding="utf-8")
    monkeypatch.setenv("PATH", str(stubs))
    monkeypatch.setenv("BUILD_ENV", "prod")
    monkeypatch.setenv("AWS_REGION", _REGION)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("STUB_LOG", str(log))
    monkeypatch.setenv("STUB_AWS_BODY", body)
    monkeypatch.setenv("STUB_AWS_STATUS", aws_status)
    monkeypatch.setenv("STUB_AWS_STDERR", stderr)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-access-key")
    status = deployment_ecs.main([])
    captured = capsys.readouterr()
    return status, captured.out + captured.err, _aws_records(log), output


def _alive(pid):
    """Return whether a process is still running."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _dead(pid):
    """Return whether a process has exited within a bounded wait."""
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return False


def _reap(pid):
    """Kill one leftover process. The test owns this cleanup."""
    if not _alive(pid):
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _run_purge(tmp_path, deploy_env, extra=None, files=None):
    """Run the purge step with a python stub. This checks handoff, not validation."""
    runner = tmp_path / "runner"
    stubs = tmp_path / "stubs"
    runner.mkdir()
    stubs.mkdir()
    for name, content in (files or {}).items():
        (runner / name).write_text(content, encoding="utf-8")
    log = tmp_path / "commands.jsonl"
    _install_stub(stubs, "python3", log)
    env = {
        "PATH": str(stubs),
        "RUNNER_TEMP": str(runner),
        "DEPLOY_ENV": deploy_env,
        "STUB_LOG": str(log),
        "STUB_PYTHON_STATUS": "0",
    }
    if extra:
        env.update(extra)
    status, visible = _run(_step_script(tmp_path, "Purge production caches"), env, tmp_path)
    return status, visible, _commands(log), runner


class TestDeployWorkflow:
    """Publication runs before Pulumi. Production purge follows the ECS update."""

    def test_triggers_and_environment_bindings(self):
        """The three triggers and the shared environment binding are explicit."""
        parsed = _workflow()
        job = parsed["jobs"]["deploy"]
        triggers = _triggers(parsed)
        assert triggers["push"]["branches"] == ["master", "prod"]
        environment = triggers["workflow_dispatch"]["inputs"]["environment"]
        assert environment["required"] is True
        assert environment["type"] == "choice"
        assert environment["options"] == ["stage", "prod"]
        assert triggers["repository_dispatch"]["types"] == ["stage", "prod"]
        assert job["environment"] == _ENVIRONMENT
        assert job["env"]["DEPLOY_ENV"] == _ENVIRONMENT
        assert parsed["concurrency"]["group"] == f"deploy-{_ENVIRONMENT}"
        assert parsed["concurrency"]["cancel-in-progress"] == _CANCEL
        assert set(parsed["concurrency"]) == {"group", "cancel-in-progress"}
        assert _ENVIRONMENT in parsed["run-name"]

    def test_publication_step_preserves_the_surrounding_workflow(self):
        """Pins, permissions, Pulumi, and the archive message stay in place."""
        parsed = _workflow()
        job = parsed["jobs"]["deploy"]
        steps = job["steps"]
        publish = _step(steps, "Publish to tb-website-builds")
        pulumi = _step(steps, "Deploy infrastructure")
        ecs = _step(steps, "Update ECS service")
        purge = _step(steps, "Purge production caches")
        assert steps.index(publish) < steps.index(pulumi) < steps.index(ecs) < steps.index(purge)
        assert "continue-on-error" not in publish
        assert "continue-on-error" not in ecs
        assert "continue-on-error" not in purge
        assert "continue-on-error" not in job
        assert "always()" not in str(purge.get("if", ""))
        assert purge["if"] == "${{ env.DEPLOY_ENV == 'prod' }}"
        assert parsed["permissions"] == {"id-token": "write", "contents": "read"}
        assert _step(steps, "Checkout")["uses"] == _CHECKOUT
        assert _step(steps, "Login to private ECR")["uses"] == _ECR
        assert _step(steps, "Login to public ECR")["uses"] == _ECR
        assert _step(steps, "Build and push Docker image")["run"] == "python3 deployment_image.py"
        assert pulumi["uses"] == _PULUMI
        assert pulumi["with"]["command"] == "up"
        assert pulumi["with"]["stack-name"] == "thunderbird/thunderbird-website/${{ env.DEPLOY_ENV }}"
        assert pulumi["with"]["work-dir"] == "./pulumi"
        assert pulumi["with"]["refresh"] is True
        assert pulumi["env"]["IMAGE_URI"] == "${{ steps.build-image.outputs.image_uri }}"
        assert _inside(publish["env"]["IMAGE_URI"]) == "steps.build-image.outputs.image_uri"
        assert _inside(publish["env"]["TB_BUILDS_BRANCH"]) == _BRANCH
        assert _inside(publish["env"]["BUILD_MESSAGE"]) == _MESSAGE
        assert publish["env"]["TB_BUILDS_KEY"] == "${{ secrets.TB_BUILDS_KEY }}"
        assert publish["env"]["TB_BUILDS_GIT_EMAIL"] == "${{ secrets.TB_BUILDS_GIT_EMAIL }}"
        assert publish["env"]["CACHE_PURGE_CONFIG"] == "${{ vars.CACHE_PURGE_CONFIG }}"
        assert publish["env"]["CACHE_PURGE_ZONE_CREDENTIALS"] == "${{ secrets.CACHE_PURGE_ZONE_CREDENTIALS }}"
        for binding in (
            "secrets.TB_BUILDS_KEY",
            "secrets.TB_BUILDS_GIT_EMAIL",
            "secrets.CACHE_PURGE_ZONE_CREDENTIALS",
            "vars.CACHE_PURGE_CONFIG",
        ):
            assert binding not in publish["run"]
        for removed in _REMOVED:
            assert removed not in publish["run"]
        assert ecs["id"] == "update-ecs"
        assert ecs["run"] == "python3 deployment_ecs.py"
        assert "timeout" not in ecs["run"]
        assert "describe-services" not in ecs["run"]
        assert "deployment_cli.py purge" not in ecs["run"]
        assert ecs["env"]["AWS_PAGER"] == ""
        assert ecs["env"]["AWS_CLI_AUTO_PROMPT"] == "off"
        assert purge["env"]["IMAGE_URI"] == "${{ steps.build-image.outputs.image_uri }}"
        assert purge["env"]["DEPLOYMENT_ID"] == "${{ steps.update-ecs.outputs.deployment_id }}"
        assert purge["env"]["TB_BUILDS_KEY"] == "${{ secrets.TB_BUILDS_KEY }}"
        assert purge["env"]["TB_BUILDS_GIT_EMAIL"] == "${{ secrets.TB_BUILDS_GIT_EMAIL }}"
        assert purge["env"]["CACHE_PURGE_ZONE_CREDENTIALS"] == "${{ secrets.CACHE_PURGE_ZONE_CREDENTIALS }}"
        assert "deployment_cli.py purge" in purge["run"]
        assert 'if [ "$DEPLOY_ENV" != "prod" ]' in purge["run"]
        for binding in (
            "secrets.TB_BUILDS_KEY",
            "secrets.TB_BUILDS_GIT_EMAIL",
            "secrets.CACHE_PURGE_ZONE_CREDENTIALS",
            "vars.CACHE_PURGE_CONFIG",
        ):
            assert binding not in purge["run"]
        for script in (publish["run"], ecs["run"], purge["run"]):
            checked = subprocess.run(
                [_bash(), "-n", "--", "/dev/stdin"],
                input=script,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=_TIMEOUT,
                check=False,
            )
            assert checked.returncode == 0, checked.stderr

    def test_stage_argument_handoff_has_no_production_inputs(self, tmp_path):
        """The stubbed stage script clones master and omits purge arguments."""
        status, visible, commands, runner = _run_stubbed(tmp_path, "stage", "master")
        checkout = str(runner / "tb-website-builds")
        assert status == 0
        assert commands == [
            [
                "git", "clone", "--depth", "1", "--branch", "master",
                "https://github.com/thunderbird/tb-website-builds.git", checkout,
            ],
            [
                "python3", "deployment_cli.py", "publish",
                "--image", _IMAGE,
                "--environment", "stage",
                "--checkout", checkout,
                "--remote", "https://github.com/thunderbird/tb-website-builds.git",
                "--message", "manual deployment.",
            ],
        ]
        assert not (runner / "cache-purge-config.json").exists()
        assert not (runner / "purge-receipt.json").exists()
        assert _KEY not in visible
        assert _CREDENTIALS not in visible

    def test_production_argument_handoff_keeps_credentials_out_of_shell(self, tmp_path):
        """The stubbed production script passes files and does not echo their contents."""
        status, visible, commands, runner = _run_stubbed(
            tmp_path,
            "prod",
            "prod",
            extra={
                "GITHUB_RUN_ID": "1001",
                "GITHUB_RUN_ATTEMPT": "2",
                "TB_BUILDS_KEY": _KEY,
                "TB_BUILDS_GIT_EMAIL": _EMAIL,
                "CACHE_PURGE_CONFIG": _CONFIG,
                "CACHE_PURGE_ZONE_CREDENTIALS": _CREDENTIALS,
            },
        )
        checkout = runner / "tb-website-builds"
        config = runner / "cache-purge-config.json"
        receipt = runner / "purge-receipt.json"
        assert status == 0
        assert commands[0] == [
            "git", "clone", "--depth", "1", "--branch", "prod",
            "https://github.com/thunderbird/tb-website-builds.git", str(checkout),
        ]
        assert commands[1] == [
            "python3", "deployment_cli.py", "publish",
            "--image", _IMAGE,
            "--environment", "prod",
            "--checkout", str(checkout),
            "--remote", "https://github.com/thunderbird/tb-website-builds.git",
            "--message", "manual deployment.",
            "--configuration", str(config),
            "--identity", "1001.2",
            "--state-ref", "refs/heads/purge-state",
            "--state-path", "prod.json",
            "--receipt", str(receipt),
        ]
        assert [command[0] for command in commands] == ["git", "python3"]
        assert config.read_text(encoding="utf-8") == _CONFIG
        assert checkout not in receipt.parents
        assert receipt.parent == runner
        assert _CONFIG not in visible
        assert "$(id)" not in visible
        assert _CREDENTIALS not in visible
        assert _KEY not in visible
        assert _KEY not in json.dumps(commands)
        assert "@" not in commands[0][6]

    def test_stubbed_publication_failure_remains_nonzero(self, tmp_path):
        """A failing publish command fails the shell step."""
        status, visible, commands, _runner = _run_stubbed(
            tmp_path,
            "prod",
            "prod",
            extra={
                "GITHUB_RUN_ID": "1001",
                "GITHUB_RUN_ATTEMPT": "2",
                "TB_BUILDS_KEY": _KEY,
                "CACHE_PURGE_CONFIG": _CONFIG,
                "CACHE_PURGE_ZONE_CREDENTIALS": _CREDENTIALS,
            },
            python_status="1",
        )
        assert status != 0
        assert [command[0] for command in commands] == ["git", "python3"]
        assert _KEY not in visible
        assert _CONFIG not in visible

    def test_empty_configuration_fails_cli_validation(self, tmp_path):
        """An empty configuration binding is rejected by the CLI."""
        status, visible, commands, runner = _run_real_cli(tmp_path, "", _CREDENTIALS)
        assert status != 0
        assert visible.strip() == "malformed JSON"
        assert [command[0] for command in commands] == ["git"]
        assert (runner / "cache-purge-config.json").read_text(encoding="utf-8") == ""
        assert not (runner / "purge-receipt.json").exists()
        assert _CREDENTIALS not in visible
        assert _KEY not in visible

    def test_empty_credentials_fail_cli_validation(self, tmp_path):
        """An empty credential binding is rejected after the explicit configuration loads."""
        configuration = _EXAMPLE.read_text(encoding="utf-8")
        status, visible, commands, runner = _run_real_cli(tmp_path, configuration, "")
        assert status != 0
        assert visible.strip() == "zone credentials are required"
        assert [command[0] for command in commands] == ["git"]
        assert (runner / "cache-purge-config.json").read_text(encoding="utf-8") == configuration
        assert not (runner / "purge-receipt.json").exists()
        assert _KEY not in visible
        assert "secret-zone-token" not in visible

    def test_update_response_records_its_primary_deployment_id(self, monkeypatch, capsys, tmp_path):
        """The stubbed update command's PRIMARY id is the value written to the step output.

        This checks argument handoff and response parsing. It does not verify
        the command timeout.
        """
        body = _update_response([
            {"id": "ecs-svc/100", "status": "ACTIVE", "taskDefinition": "arn:aws:ecs:task"},
            {"id": _DEPLOYMENT, "status": "PRIMARY"},
        ])
        monkeypatch.setenv("AWS_MAX_ATTEMPTS", "4")
        status, visible, records, output = _run_ecs(monkeypatch, capsys, tmp_path, body)
        argv = [Path(records[0]["argv"][0]).name, *records[0]["argv"][1:]]
        assert status == 0
        assert len(records) == 1
        assert output.read_text(encoding="utf-8") == f"image_uri=kept\ndeployment_id={_DEPLOYMENT}\n"
        assert argv[:4] == ["aws", "ecs", "update-service", "--cluster"]
        assert "thunderbird-website-prod" in argv
        assert "--force-new-deployment" in argv
        assert "--region" in argv and _REGION in argv
        assert "--output" in argv and "json" in argv
        assert "--no-cli-pager" in argv
        assert "--no-cli-auto-prompt" in argv
        assert "--cli-connect-timeout" in argv and "10" in argv
        assert "describe-services" not in argv
        assert records[0]["pager"] == ""
        assert records[0]["prompt"] == "off"
        assert records[0]["attempts"] == "1"
        assert os.environ["AWS_MAX_ATTEMPTS"] == "4"
        assert _MARKER not in visible
        assert "arn:aws:ecs:task" not in visible
        assert "secret-access-key" not in visible
        assert _MARKER not in output.read_text(encoding="utf-8")

    def test_unusable_update_does_not_publish_a_deployment_id(self, monkeypatch, capsys, tmp_path):
        """A failed or unusable update exits nonzero and leaves the step output unchanged."""
        cases = (
            ("{", "0", "", "ECS update response is malformed"),
            ("", "0", "", "ECS update response is malformed"),
            (_update_response([{"id": "ecs-svc/100", "status": "ACTIVE"}]), "0", "", "ECS deployment id is missing"),
            (_update_response([]), "0", "", "ECS deployment id is missing"),
            (
                _update_response([
                    {"id": "ecs-svc/1", "status": "PRIMARY"},
                    {"id": "ecs-svc/2", "status": "PRIMARY"},
                ]),
                "0",
                "",
                "ECS deployment id is ambiguous",
            ),
            (
                _update_response([{"id": "ecs-svc/1\ninjected=true", "status": "PRIMARY"}]),
                "0",
                "",
                "ECS deployment id is invalid",
            ),
            (_update_response([{"id": "-ecs-svc/1", "status": "PRIMARY"}]), "0", "", "ECS deployment id is invalid"),
            (_update_response([{"id": "", "status": "PRIMARY"}]), "0", "", "ECS deployment id is invalid"),
            (
                _update_response([{"id": _DEPLOYMENT, "status": "PRIMARY"}]),
                "1",
                f"{_MARKER}\nsecret-access-key\n",
                "ECS update failed",
            ),
        )
        for index, (body, aws_status, stderr, diagnostic) in enumerate(cases):
            case = tmp_path / f"case-{index}"
            case.mkdir()
            status, visible, records, output = _run_ecs(
                monkeypatch, capsys, case, body, aws_status, stderr,
            )
            assert status != 0
            assert len(records) == 1
            assert visible.strip() == diagnostic
            assert _MARKER not in visible
            assert "secret-access-key" not in visible
            assert "injected=true" not in visible
            assert "injected=true" not in output.read_text(encoding="utf-8")
            assert output.read_text(encoding="utf-8") == "image_uri=kept\n"
            assert "thunderbird-website-prod" not in visible

    def test_invalid_timeout_does_not_start_aws(self, monkeypatch):
        """NaN, infinities, and non-positive durations fail before AWS starts."""
        def forbid(*_args, **_kwargs):
            raise AssertionError("aws started")

        monkeypatch.setattr(deployment_ecs.subprocess, "Popen", forbid)
        monkeypatch.setenv("BUILD_ENV", "prod")
        monkeypatch.setenv("AWS_REGION", _REGION)
        for timeout in (float("nan"), float("inf"), float("-inf"), 0, -1, True):
            try:
                deployment_ecs.capture_update_deployment("unused", timeout=timeout)
            except ValueError as error:
                assert str(error) == "ECS update failed"
            else:
                raise AssertionError(timeout)

    def test_fractional_timeout_runs_one_update(self, monkeypatch, tmp_path):
        """A positive finite fraction of a second still allows one update."""
        stubs = tmp_path / "stubs"
        stubs.mkdir()
        log = tmp_path / "commands.jsonl"
        _install_aws(stubs, log)
        output = tmp_path / "github_output"
        output.write_text("image_uri=kept\n", encoding="utf-8")
        monkeypatch.setenv("PATH", str(stubs))
        monkeypatch.setenv("BUILD_ENV", "prod")
        monkeypatch.setenv("AWS_REGION", _REGION)
        monkeypatch.setenv("STUB_LOG", str(log))
        monkeypatch.setenv("STUB_AWS_BODY", _update_response([{"id": _DEPLOYMENT, "status": "PRIMARY"}]))
        monkeypatch.setenv("STUB_AWS_STATUS", "0")
        monkeypatch.setenv("AWS_MAX_ATTEMPTS", "4")
        deployment_ecs.capture_update_deployment(str(output), timeout=0.25)
        records = _aws_records(log)
        assert len(records) == 1
        assert records[0]["attempts"] == "1"
        assert os.environ["AWS_MAX_ATTEMPTS"] == "4"
        assert output.read_text(encoding="utf-8") == f"image_uri=kept\ndeployment_id={_DEPLOYMENT}\n"

    def test_term_resistant_update_is_killed_once(self, monkeypatch, capsys, tmp_path):
        """A child that ignores TERM is killed, and the update is not retried.

        This runs the real termination path with a one-second budget. It does
        not use the response stub.
        """
        stubs = tmp_path / "stubs"
        stubs.mkdir()
        log = tmp_path / "starts.txt"
        parent_pid = tmp_path / "parent.pid"
        child_pid = tmp_path / "child.pid"
        output = tmp_path / "github_output"
        output.write_text("image_uri=kept\n", encoding="utf-8")
        aws = stubs / "aws"
        aws.write_text(
            f"""#!{sys.executable}
import os
import signal
import sys
import time

signal.signal(signal.SIGTERM, signal.SIG_IGN)
open(os.environ["PARENT_PID"], "w", encoding="utf-8").write(str(os.getpid()))
open(os.environ["STUB_LOG"], "a", encoding="utf-8").write("start\\n")
sys.stderr.write("secret-aws-error\\n")
sys.stdout.write("secret-response\\n")
child = os.fork()
if child == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    open(os.environ["CHILD_PID"], "w", encoding="utf-8").write(str(os.getpid()))
    time.sleep(60)
    os._exit(0)
time.sleep(60)
""",
            encoding="utf-8",
        )
        aws.chmod(0o755)
        monkeypatch.setenv("PATH", str(stubs))
        monkeypatch.setenv("BUILD_ENV", "prod")
        monkeypatch.setenv("AWS_REGION", _REGION)
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("STUB_LOG", str(log))
        monkeypatch.setenv("PARENT_PID", str(parent_pid))
        monkeypatch.setenv("CHILD_PID", str(child_pid))
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-access-key")
        monkeypatch.setattr(deployment_ecs, "_COMMAND_TIMEOUT", 1)
        pids = []
        started = time.monotonic()
        try:
            status = deployment_ecs.main([])
            elapsed = time.monotonic() - started
            captured = capsys.readouterr()
            visible = captured.out + captured.err
            for path in (parent_pid, child_pid):
                if path.exists():
                    pids.append(int(path.read_text(encoding="utf-8")))
            assert status == 1
            assert visible.strip() == "ECS update failed"
            assert elapsed < 10
            assert log.read_text(encoding="utf-8") == "start\n"
            assert "secret-aws-error" not in visible
            assert "secret-response" not in visible
            assert "secret-access-key" not in visible
            assert _REGION not in visible
            assert output.read_text(encoding="utf-8") == "image_uri=kept\n"
            assert child_pid.exists()
            assert pids
            assert all(_dead(pid) for pid in pids)
        finally:
            for path in (parent_pid, child_pid):
                if not path.exists():
                    continue
                _reap(int(path.read_text(encoding="utf-8")))

    def test_stage_purge_script_does_not_call_purge(self, tmp_path):
        """Stage leaves the purge command uninvoked and does not need production inputs."""
        status, visible, commands, runner = _run_purge(tmp_path, "stage")
        assert status == 0
        assert commands == []
        assert not (runner / "cache-purge-config.json").exists()
        assert not (runner / "purge-receipt.json").exists()
        assert _KEY not in visible
        assert _CREDENTIALS not in visible

    def test_production_purge_handoff_uses_the_captured_deployment(self, tmp_path):
        """The stubbed purge command receives this run's files, image, identity, and deployment id."""
        status, visible, commands, runner = _run_purge(
            tmp_path,
            "prod",
            extra={
                "IMAGE_URI": _IMAGE,
                "DEPLOYMENT_ID": _DEPLOYMENT,
                "AWS_REGION": _REGION,
                "GITHUB_RUN_ID": "1001",
                "GITHUB_RUN_ATTEMPT": "2",
                "TB_BUILDS_KEY": _KEY,
                "TB_BUILDS_GIT_EMAIL": _EMAIL,
                "CACHE_PURGE_ZONE_CREDENTIALS": _CREDENTIALS,
            },
            files={
                "cache-purge-config.json": _CONFIG,
                "purge-receipt.json": "receipt-sentinel\n",
            },
        )
        config = runner / "cache-purge-config.json"
        receipt = runner / "purge-receipt.json"
        assert status == 0
        assert commands == [[
            "python3", "deployment_cli.py", "purge",
            "--configuration", str(config),
            "--receipt", str(receipt),
            "--identity", "1001.2",
            "--image", _IMAGE,
            "--workspace", str(runner / "tb-website-builds"),
            "--remote", "https://github.com/thunderbird/tb-website-builds.git",
            "--state-ref", "refs/heads/purge-state",
            "--state-path", "prod.json",
            "--cluster", "thunderbird-website-prod",
            "--service", "thunderbird-website-prod",
            "--region", _REGION,
            "--deployment-id", _DEPLOYMENT,
        ]]
        assert _CONFIG not in visible
        assert _CREDENTIALS not in visible
        assert _KEY not in visible
        assert _KEY not in json.dumps(commands)
        assert "@" not in commands[0][commands[0].index("--remote") + 1]
        assert config.read_text(encoding="utf-8") == _CONFIG
        assert receipt.read_text(encoding="utf-8") == "receipt-sentinel\n"
