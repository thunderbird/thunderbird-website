"""Poll ECS until one expected deployment is ready, or stop on a terminal result.

The caller supplies the cluster, service, region, deployment id, and
digest-pinned image. This module asks the AWS CLI for those exact objects and
delegates the readiness decision to ``evaluate_deployment``. It does not
select a primary deployment on its own, purge a cache, or record the result.

A ready return requires two fresh observations, one immediately after the
other, both ready for that same deployment and image. The service can still
change after the second observation. Callers must not treat readiness as a
lock.

Each command runs for at most 30 seconds, or for the time still left in the
original deadline when that is shorter. Connection and read timeouts are at
most 10 seconds and never zero. A command that uses up its own limit can be
retried while the deadline has time left. Once that deadline has passed, the
result is not accepted and no further command starts.
"""

import json
import math
import os
import signal
import subprocess
import time

from deployment_readiness import (
    FAILED,
    READY,
    SUPERSEDED,
    DeploymentEvaluation,
    digest_pinned,
    evaluate_deployment,
)


DEFAULT_TIMEOUT = 600
DEFAULT_INTERVAL = 15
_COMMAND_TIMEOUT = 30
_SOCKET_TIMEOUT = 10

_UNSUCCESSFUL = "unsuccessful"


class DeploymentPollingError(Exception):
    """Polling could not obtain a terminal readiness result."""


class _CommandFailed(Exception):
    """One AWS command failed before the deadline and can be retried."""


class _Late(Exception):
    """The original deadline passed before an observation could be accepted."""


def poll_deployment_readiness(
    cluster,
    service,
    region,
    deployment_id,
    image,
    timeout=DEFAULT_TIMEOUT,
    interval=DEFAULT_INTERVAL,
):
    """Return readiness for ``deployment_id``, or raise when the deadline passes.

    ``timeout`` is the overall budget in seconds and ``interval`` is the pause
    between unsuccessful, waiting, or invalid observations. Both must be
    positive finite numbers. The deployment id is required; a missing id is
    not replaced with whichever deployment is currently PRIMARY.

    Failed and superseded results return as soon as the service observation
    shows them, without a task-definition request. Waiting, invalid, and
    unsuccessful observations continue until the original deadline. After the
    first ready observation, the next observation runs immediately. Ready is
    returned only when that recheck is also ready. Any other recheck resumes
    polling without extending the deadline.

    Decoding and evaluation are part of the observation. A result that is
    ready only after the deadline has passed is rejected. Two agreeing
    observations still cannot prevent the deployment from changing afterward.
    """
    _validate(cluster, service, region, deployment_id, image, timeout, interval)
    deadline = time.monotonic() + timeout
    confirming = False
    while True:
        _ensure_time_remains(deadline)
        try:
            outcome = _observe(cluster, service, region, deployment_id, image, deadline)
        except _Late:
            raise DeploymentPollingError("deployment readiness deadline expired") from None
        if outcome in (FAILED, SUPERSEDED):
            return DeploymentEvaluation(outcome)
        if outcome == READY:
            if confirming:
                return DeploymentEvaluation(outcome)
            confirming = True
            continue
        confirming = False
        _pause(deadline, interval)


def _validate(cluster, service, region, deployment_id, image, timeout, interval):
    """Reject caller errors before any AWS process starts."""
    _identity("cluster", cluster)
    _identity("service", service)
    _identity("region", region)
    _identity("deployment id", deployment_id)
    if not digest_pinned(image):
        raise ValueError("image must be pinned by digest")
    _duration("timeout", timeout)
    _duration("interval", interval)


def _identity(name, value):
    """Reject a missing or unsafe command argument."""
    if not isinstance(value, str) or value == "" or value.startswith("-") or any(
        character in value for character in "\n\r\x00"
    ):
        raise ValueError(f"{name} must be a non-empty string")


def _duration(name, value):
    """Reject booleans, non-numbers, and non-positive or non-finite durations.

    Positive fractions of a second are valid.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number of seconds")


def _ensure_time_remains(deadline):
    """Stop before starting work that can no longer finish in time."""
    if time.monotonic() >= deadline:
        raise DeploymentPollingError("deployment readiness deadline expired")


def _pause(deadline, interval):
    """Sleep for the interval or the remaining budget, whichever is smaller."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DeploymentPollingError("deployment readiness deadline expired")
    time.sleep(min(interval, remaining))


def _observe(cluster, service, region, deployment_id, image, deadline):
    """Return one evaluator outcome, or ``unsuccessful`` when AWS was unusable.

    Failed and superseded are decided from the service alone. The deadline is
    checked after decoding and again after evaluation, before that outcome is
    returned.
    """
    try:
        described = _invoke(_service_command(cluster, service, region), deadline)
    except _CommandFailed:
        return _UNSUCCESSFUL
    observed = _service(described)
    if observed is None:
        return _UNSUCCESSFUL
    preliminary = evaluate_deployment(observed, {}, image, deployment_id).outcome
    _accept(deadline)
    if preliminary in (FAILED, SUPERSEDED):
        return preliminary
    arn = _task_definition_arn(observed, deployment_id)
    if arn is None:
        return preliminary
    try:
        described = _invoke(_task_command(arn, region), deadline)
    except _CommandFailed:
        return _UNSUCCESSFUL
    task_definition = described.get("taskDefinition")
    if not isinstance(task_definition, dict):
        return _UNSUCCESSFUL
    outcome = evaluate_deployment(observed, task_definition, image, deployment_id).outcome
    _accept(deadline)
    return outcome


def _accept(deadline):
    """Reject an observation whose decode or evaluation crossed the deadline."""
    if time.monotonic() >= deadline:
        raise _Late()


def _service(payload):
    """Return the only reported service when the envelope has no failures."""
    if not isinstance(payload, dict):
        return None
    failures = payload.get("failures", [])
    services = payload.get("services")
    if not isinstance(failures, list) or failures:
        return None
    if not isinstance(services, list) or len(services) != 1 or not isinstance(services[0], dict):
        return None
    return services[0]


def _task_definition_arn(service, deployment_id):
    """Return the expected deployment's exact revision ARN, when it has one."""
    deployments = service.get("deployments")
    if not isinstance(deployments, list):
        return None
    found = None
    for deployment in deployments:
        if not isinstance(deployment, dict) or deployment.get("id") != deployment_id:
            continue
        if found is not None:
            return None
        found = deployment.get("taskDefinition")
    if not isinstance(found, str) or ":task-definition/" not in found:
        return None
    family, separator, revision = found.rsplit(":task-definition/", 1)[-1].partition(":")
    if separator != ":" or family == "" or not revision.isdigit():
        return None
    if found.startswith("-") or any(character in found for character in "\n\r\x00"):
        return None
    return found


def _service_command(cluster, service, region):
    """Build a describe-services command for the supplied service."""
    return [
        "aws", "ecs", "describe-services",
        "--cluster", cluster,
        "--services", service,
        "--region", region,
    ]


def _task_command(arn, region):
    """Build a describe-task-definition command for one revision ARN."""
    return [
        "aws", "ecs", "describe-task-definition",
        "--task-definition", arn,
        "--region", region,
    ]


def _common_options(budget):
    """Return JSON, noninteractive, and finite socket-timeout options."""
    seconds = str(_socket_timeout(budget))
    return [
        "--output", "json",
        "--no-cli-pager",
        "--no-cli-auto-prompt",
        "--cli-connect-timeout", seconds,
        "--cli-read-timeout", seconds,
    ]


def _command_budget(deadline):
    """Return the time this command may run, or raise when none remains."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _Late()
    return min(_COMMAND_TIMEOUT, remaining)


def _socket_timeout(budget):
    """Return a positive whole-second timeout of at most ten seconds.

    A fractional budget is raised to one second. Zero would disable the AWS
    CLI socket timeout instead of bounding it.
    """
    if budget <= 0:
        return 1
    return min(_SOCKET_TIMEOUT, max(1, math.ceil(budget)))


def _invoke(args, deadline):
    """Run one AWS command inside its budget and return its JSON object."""
    budget = _command_budget(deadline)
    try:
        process = subprocess.Popen(
            [*args, *_common_options(budget)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy(),
            start_new_session=True,
        )
    except OSError:
        raise DeploymentPollingError("deployment readiness command failed") from None
    try:
        stdout, _stderr = process.communicate(timeout=budget)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        if time.monotonic() >= deadline:
            raise _Late()
        raise _CommandFailed()
    if time.monotonic() >= deadline:
        raise _Late()
    if process.returncode != 0:
        raise _CommandFailed()
    return _decode(stdout, deadline)


def _decode(stdout, deadline):
    """Return one JSON object.

    Unsupported decoder input is an unsuccessful command. A deadline that
    passes during decoding is terminal, including when decoding also fails.
    """
    try:
        payload = json.loads(stdout.decode("utf-8"))
    except (AttributeError, ValueError, OverflowError, RecursionError):
        payload = None
    if time.monotonic() >= deadline:
        raise _Late()
    if not isinstance(payload, dict):
        raise _CommandFailed()
    return payload
