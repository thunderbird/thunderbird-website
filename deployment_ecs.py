"""Record the deployment id from one ECS update-service response.

The helper starts one process and sets that process's ``AWS_MAX_ATTEMPTS``
to ``1``. The caller's attempt count is unchanged. One process and one
configured API attempt do not make a lost response certain: an update
accepted before that response was lost stays uncertain and is not sent
again or rolled back. The wait is bounded, and a child that ignores
termination is killed. Readiness stays in the existing evaluator and
poller. This module does not describe the service again and does not
select a later PRIMARY deployment.
"""

import json
import math
import os
import signal
import subprocess
import sys


_COMMAND_TIMEOUT = 30
_CLEANUP_TIMEOUT = 1
_SOCKET_TIMEOUT = "10"
_FAILED = "ECS update failed"


def select_primary_deployment_id(document):
    """Return the only PRIMARY deployment id in one update response.

    Missing, malformed, and ambiguous responses raise ``ValueError`` with a
    fixed message. The response is not included.
    """
    payload = _payload(document)
    service = payload.get("service")
    if not isinstance(service, dict):
        raise ValueError("ECS update response is malformed")
    deployments = service.get("deployments")
    if not isinstance(deployments, list) or not all(isinstance(item, dict) for item in deployments):
        raise ValueError("ECS update response is malformed")
    found = [item.get("id") for item in deployments if item.get("status") == "PRIMARY"]
    if not found:
        raise ValueError("ECS deployment id is missing")
    if len(found) != 1:
        raise ValueError("ECS deployment id is ambiguous")
    _validate_deployment_id(found[0])
    return found[0]


def capture_update_deployment(output_path, timeout=None):
    """Run one update-service and append its PRIMARY deployment id.

    A launch failure, timeout, or nonzero status raises ``ValueError`` with
    ``ECS update failed``. That message does not include command output,
    the response, arguments, or credentials. The child is limited to one
    AWS CLI attempt. The call is not repeated from this process. A rejected
    id is not written.
    """
    if timeout is None:
        timeout = _COMMAND_TIMEOUT
    name, region = _target()
    document = _update_service(name, region, timeout)
    deployment_id = select_primary_deployment_id(document)
    _write_output(output_path, deployment_id)
    return deployment_id


def main(argv=None):
    """Capture the deployment id and return a process status."""
    try:
        if (sys.argv[1:] if argv is None else argv):
            raise ValueError(_FAILED)
        capture_update_deployment(os.environ.get("GITHUB_OUTPUT"))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    except Exception:
        print("ECS deployment id is unavailable", file=sys.stderr)
        return 1
    return 0


def _target():
    """Return the service name and region without echoing invalid input."""
    environment = os.environ.get("BUILD_ENV")
    region = os.environ.get("AWS_REGION")
    if environment not in {"stage", "prod"} or not _token(region):
        raise ValueError(_FAILED)
    return f"thunderbird-website-{environment}", region


def _token(value):
    """Return whether one command argument is a single safe token."""
    return isinstance(value, str) and value != "" and not value.startswith("-") and not any(
        character.isspace() or character == "\x00" for character in value
    )


def _update_service(name, region, timeout):
    """Return one update response. The process is not started again."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError(_FAILED)
    env = os.environ.copy()
    env["AWS_PAGER"] = ""
    env["AWS_CLI_AUTO_PROMPT"] = "off"
    env["AWS_MAX_ATTEMPTS"] = "1"
    command = [
        "aws", "ecs", "update-service",
        "--cluster", name,
        "--service", name,
        "--force-new-deployment",
        "--region", region,
        "--output", "json",
        "--no-cli-pager",
        "--no-cli-auto-prompt",
        "--cli-connect-timeout", _SOCKET_TIMEOUT,
        "--cli-read-timeout", _SOCKET_TIMEOUT,
    ]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
    except OSError:
        raise ValueError(_FAILED) from None
    try:
        stdout, _stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop(process)
        raise ValueError(_FAILED) from None
    except (KeyboardInterrupt, SystemExit):
        _stop(process)
        raise
    if process.returncode != 0:
        raise ValueError(_FAILED)
    try:
        return stdout.decode("utf-8")
    except UnicodeError:
        raise ValueError("ECS update response is malformed") from None


def _stop(process):
    """Kill one process group and reap it for at most one second.

    ``SIGKILL`` is used so a child that ignores termination still stops.
    The wait is bounded. Nothing from the command is reported.
    """
    signaled = False
    try:
        os.killpg(process.pid, signal.SIGKILL)
        signaled = True
    except BaseException:
        pass
    if not signaled:
        try:
            os.kill(process.pid, signal.SIGKILL)
        except BaseException:
            pass
    try:
        process.wait(timeout=_CLEANUP_TIMEOUT)
    except BaseException:
        pass
    for pipe in (process.stdin, process.stdout, process.stderr):
        if pipe is None:
            continue
        try:
            pipe.close()
        except BaseException:
            pass


def _payload(document):
    """Return the update response object, without echoing it."""
    try:
        payload = json.loads(document)
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError):
        raise ValueError("ECS update response is malformed") from None
    if not isinstance(payload, dict):
        raise ValueError("ECS update response is malformed")
    return payload


def _validate_deployment_id(value):
    """Reject an id that cannot be one workflow output and one command argument."""
    if not _token(value):
        raise ValueError("ECS deployment id is invalid")


def _write_output(path, deployment_id):
    """Append one single-line deployment id output."""
    if not isinstance(path, str) or not _token(path):
        raise ValueError("deployment output path is missing")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"deployment_id={deployment_id}\n")


if __name__ == "__main__":
    sys.exit(main())
