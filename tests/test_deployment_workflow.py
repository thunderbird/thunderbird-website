"""Pre-rollout publication wiring in the deploy workflow.

Static checks compare workflow fields. They do not execute GitHub's
expression engine. Script checks are either argument handoffs through
local stubs, or validation by the real deployment CLI.
"""

import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import yaml


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


class TestDeployWorkflow:
    """Publication is wired before Pulumi. Purge remains unwired."""

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
        assert steps.index(publish) < steps.index(pulumi)
        assert "continue-on-error" not in publish
        assert "continue-on-error" not in job
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
        assert "deployment_cli.py purge" not in ecs["run"]
        assert ecs["run"].strip().startswith("aws ecs update-service")
        checked = subprocess.run(
            [_bash(), "-n", "--", "/dev/stdin"],
            input=publish["run"],
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
