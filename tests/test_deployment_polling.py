"""Bounded ECS readiness polling with scripted AWS responses and a fake clock."""

import json
import subprocess

import pytest

import deployment_polling as polling
import deployment_readiness as readiness


DIGEST = "a" * 64
OTHER_DIGEST = "b" * 64
IMAGE = f"123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod@sha256:{DIGEST}"
OTHER_IMAGE = f"123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod@sha256:{OTHER_DIGEST}"
TASK = "arn:aws:ecs:us-west-2:123456789012:task-definition/thunderbird-website-prod:42"
OTHER_TASK = "arn:aws:ecs:us-west-2:123456789012:task-definition/thunderbird-website-prod:41"
INTENDED = "ecs-svc/1111111111111111111"
CURRENT = "ecs-svc/2222222222222222222"
CLUSTER = "cluster-prod"
SERVICE = "thunderbird-website-prod"
REGION = "us-west-2"


def _deployment(**overrides):
    """Return one deployment object the readiness evaluator can judge."""
    deployment = {
        "id": INTENDED,
        "status": "PRIMARY",
        "taskDefinition": TASK,
        "desiredCount": 8,
        "pendingCount": 0,
        "runningCount": 8,
        "rolloutState": "COMPLETED",
    }
    deployment.update(overrides)
    return deployment


def _service(*deployments, **overrides):
    """Return one service object wrapped by a describe-services envelope."""
    service = {
        "deployments": list(deployments) or [_deployment()],
        "desiredCount": 8,
        "runningCount": 8,
        "pendingCount": 0,
        "taskDefinition": TASK,
    }
    service.update(overrides)
    return {"services": [service], "failures": []}


def _definition(image=IMAGE, arn=TASK):
    """Return a describe-task-definition envelope for the web container."""
    return {
        "taskDefinition": {
            "taskDefinitionArn": arn,
            "containerDefinitions": [{"name": "web", "image": image}],
        },
    }


class Clock:
    """A monotonic clock that advances only when a test says it should."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Script:
    """Serve canned process results and record every AWS invocation."""

    def __init__(self, clock, actions):
        self.clock = clock
        self.actions = list(actions)
        self.calls = []
        self.timeouts = []
        self.killed = []
        self.waited = 0

    def popen(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        script = self

        class Process:
            pid = 2**22
            returncode = None

            def communicate(self, timeout=None):
                script.timeouts.append(timeout)
                action = script.actions.pop(0)
                return action(self, script.clock, timeout)

            def wait(self):
                script.waited += 1
                self.returncode = 1
                return self.returncode

        return Process()


def _ok(payload, advance=0):
    """Return a successful JSON response, optionally moving the clock."""
    def action(process, clock, _budget):
        clock.now += advance
        process.returncode = 0
        return json.dumps(payload).encode(), b""
    return action


def _fail(stderr=b"secret-aws-token"):
    """Return a nonzero AWS command without exposing its output to the caller."""
    def action(process, _clock, _budget):
        process.returncode = 2
        return b"", stderr
    return action


def _spend(payload=None):
    """Use the command's real execution budget, then succeed or time out."""
    def action(process, clock, budget):
        clock.now += budget
        if payload is None:
            raise subprocess.TimeoutExpired("aws", budget)
        process.returncode = 0
        return json.dumps(payload).encode(), b""
    return action


def _install(monkeypatch, actions):
    """Replace the clock, sleep, and AWS process with the supplied script."""
    clock = Clock()
    script = Script(clock, actions)
    monkeypatch.setattr(polling.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(polling.time, "sleep", clock.sleep)
    monkeypatch.setattr(polling.subprocess, "Popen", script.popen)
    monkeypatch.setattr(polling.os, "killpg", lambda pid, sig: script.killed.append((pid, sig)))
    return clock, script


def _poll(**overrides):
    """Poll with the fixture identity unless a test overrides it."""
    arguments = {
        "cluster": CLUSTER,
        "service": SERVICE,
        "region": REGION,
        "deployment_id": INTENDED,
        "image": IMAGE,
    }
    arguments.update(overrides)
    return polling.poll_deployment_readiness(**arguments)


def _ready_pair():
    """Two fresh observations of the same ready deployment."""
    return [
        _ok(_service()),
        _ok(_definition()),
        _ok(_service()),
        _ok(_definition()),
    ]


def _targets(script, option):
    """Return the values passed for one AWS option."""
    values = []
    for args, _kwargs in script.calls:
        if option in args:
            values.append(args[args.index(option) + 1])
    return values


class TestDeploymentPolling:
    """Polling spends one deadline on the caller-selected deployment."""

    def test_ready_is_returned_only_after_an_immediate_recheck(self, monkeypatch):
        """The second ready observation has to agree before readiness is returned."""
        clock, script = _install(monkeypatch, _ready_pair())

        result = _poll(timeout=600, interval=15)

        assert result == readiness.DeploymentEvaluation(readiness.READY)
        assert clock.sleeps == []
        assert _targets(script, "--cluster") == [CLUSTER, CLUSTER]
        assert _targets(script, "--services") == [SERVICE, SERVICE]
        assert _targets(script, "--region") == [REGION, REGION, REGION, REGION]
        assert _targets(script, "--task-definition") == [TASK, TASK]
        assert script.timeouts == [30, 30, 30, 30]
        assert _targets(script, "--cli-read-timeout") == ["10", "10", "10", "10"]
        assert _targets(script, "--cli-connect-timeout") == ["10", "10", "10", "10"]

    def test_waiting_and_invalid_observations_resume_until_ready(self, monkeypatch):
        """Waiting and invalid results stay inside the original deadline."""
        actions = [
            _ok(_service(_deployment(rolloutState="IN_PROGRESS"))),
            _ok(_definition()),
            _ok(_service()),
            _ok(_definition(image=OTHER_IMAGE)),
            *_ready_pair(),
        ]
        clock, _script = _install(monkeypatch, actions)

        result = _poll(timeout=100, interval=15)

        assert result.outcome == readiness.READY
        assert clock.sleeps == [15, 15]

    def test_terminal_service_outcomes_skip_the_task_definition(self, monkeypatch):
        """Failed and superseded are returned from the service response alone."""
        cases = (
            (_service(_deployment(rolloutState="FAILED")), readiness.FAILED),
            (
                _service(
                    _deployment(status="INACTIVE", runningCount=0, pendingCount=0),
                    _deployment(id=CURRENT, taskDefinition=OTHER_TASK),
                ),
                readiness.SUPERSEDED,
            ),
        )
        for service, outcome in cases:
            _clock, script = _install(monkeypatch, [_ok(service)])
            assert _poll(timeout=30).outcome == outcome
            assert script.calls
            assert _targets(script, "--task-definition") == []

    def test_confirmation_resets_after_a_waiting_recheck(self, monkeypatch):
        """A waiting recheck discards the first ready result and waits for a new pair."""
        actions = [
            _ok(_service()),
            _ok(_definition()),
            _ok(_service(_deployment(rolloutState="IN_PROGRESS"))),
            _ok(_definition()),
            *_ready_pair(),
        ]
        clock, script = _install(monkeypatch, actions)

        result = _poll(timeout=100, interval=15)

        assert result.outcome == readiness.READY
        assert clock.sleeps == [15]
        assert _targets(script, "--task-definition") == [TASK, TASK, TASK, TASK]

    def test_confirming_observation_can_be_terminal(self, monkeypatch):
        """The immediate recheck returns failed or superseded without another command."""
        failed = _service(_deployment(rolloutState="FAILED"))
        superseded = _service(
            _deployment(status="INACTIVE", runningCount=0, pendingCount=0),
            _deployment(id=CURRENT, taskDefinition=OTHER_TASK),
        )
        for service, outcome in ((failed, readiness.FAILED), (superseded, readiness.SUPERSEDED)):
            _clock, script = _install(monkeypatch, [_ok(_service()), _ok(_definition()), _ok(service)])
            assert _poll(timeout=30).outcome == outcome
            assert len(script.calls) == 3
            assert _targets(script, "--task-definition") == [TASK]

    def test_expected_deployment_is_not_replaced_by_the_primary(self, monkeypatch):
        """A ready primary with a different id does not satisfy the requested id."""
        foreign = _service(_deployment(id=CURRENT, taskDefinition=OTHER_TASK))
        clock, script = _install(monkeypatch, [_ok(foreign), *_ready_pair()])

        result = _poll(timeout=50, interval=10)

        assert result.outcome == readiness.READY
        assert clock.sleeps == [10]
        assert _targets(script, "--task-definition") == [TASK, TASK]

    def test_invalid_arguments_do_not_call_aws(self, monkeypatch):
        """Images, identities, and timing are rejected before a process starts."""
        def refuse(*_args, **_kwargs):
            raise AssertionError("AWS started")

        monkeypatch.setattr(polling.subprocess, "Popen", refuse)
        rejected = [
            ({"deployment_id": ""}, "deployment id"),
            ({"deployment_id": None}, "deployment id"),
            ({"image": "nginx:latest"}, "image"),
            ({"timeout": 0}, "timeout"),
            ({"timeout": -5}, "timeout"),
            ({"timeout": float("nan")}, "timeout"),
            ({"timeout": float("inf")}, "timeout"),
            ({"timeout": True}, "timeout"),
            ({"interval": 0}, "interval"),
            ({"interval": float("nan")}, "interval"),
            ({"cluster": ""}, "cluster"),
            ({"cluster": "-prod"}, "cluster"),
            ({"service": None}, "service"),
            ({"region": "us-west-2\n"}, "region"),
        ]
        for overrides, message in rejected:
            with pytest.raises(ValueError, match=message):
                _poll(**overrides)

    def test_malformed_and_failed_envelopes_are_retried(self, monkeypatch):
        """Bad JSON, the wrong shape, and service failures do not end polling."""
        actions = [
            _ok_bytes(b"{"),
            _ok_bytes(b"[]"),
            _ok({"services": [], "failures": [{"reason": "MISSING", "detail": "secret-aws-token"}]}),
            *_ready_pair(),
        ]
        _clock, script = _install(monkeypatch, actions)

        result = _poll(timeout=80, interval=5)

        assert result.outcome == readiness.READY
        assert len(script.calls) == 7
        assert "secret-aws-token" not in "".join(str(item) for item in result)

    def test_command_failure_and_timeout_are_retried(self, monkeypatch):
        """A nonzero exit or a 30-second timeout is retried while the deadline remains."""
        actions = [_fail(), _spend(), *_ready_pair()]
        clock, script = _install(monkeypatch, actions)

        result = _poll(timeout=100, interval=4)

        assert result.outcome == readiness.READY
        assert script.timeouts[1] == 30
        assert clock.now == 4 + 30 + 4
        assert clock.sleeps == [4, 4]
        assert script.killed
        assert script.waited == 1
        assert len(script.calls) == 6

    def test_launch_failure_is_sanitized(self, monkeypatch):
        """A process that cannot start raises a polling error without its reason."""
        def explode(*_args, **_kwargs):
            raise OSError("secret-launch-token")

        monkeypatch.setattr(polling.subprocess, "Popen", explode)
        with pytest.raises(polling.DeploymentPollingError, match="command failed") as caught:
            _poll()
        assert "secret-launch-token" not in str(caught.value)

    def test_deadline_during_a_command_is_terminal(self, monkeypatch):
        """Using the whole remaining budget on one command ends polling."""
        clock, script = _install(monkeypatch, [_spend(_service()), _ok(_definition())])

        with pytest.raises(polling.DeploymentPollingError, match="deadline expired"):
            _poll(timeout=30)
        assert script.timeouts == [30]
        assert len(script.calls) == 1
        assert clock.sleeps == []

    def test_deadline_during_task_definition_lookup_is_terminal(self, monkeypatch):
        """A task-definition command that reaches the deadline starts nothing further."""
        actions = [_ok(_service()), _spend(_definition()), _ok(_service())]
        _clock, script = _install(monkeypatch, actions)

        with pytest.raises(polling.DeploymentPollingError, match="deadline expired"):
            _poll(timeout=30)
        assert len(script.calls) == 2
        assert script.timeouts == [30, 30]

    def test_deadline_during_the_recheck_rejects_ready(self, monkeypatch):
        """The confirming observation is held to the same original deadline."""
        actions = [*_ready_pair()[:2], _spend(_service()), _ok(_definition())]
        _clock, script = _install(monkeypatch, actions)

        with pytest.raises(polling.DeploymentPollingError, match="deadline expired"):
            _poll(timeout=30)
        assert len(script.calls) == 3

    def test_decoding_after_the_deadline_rejects_ready(self, monkeypatch):
        """The confirming document is not accepted when decoding reaches the deadline."""
        clock, script = _install(monkeypatch, _ready_pair())
        real_loads = polling.json.loads

        def loads(payload, *args, **kwargs):
            data = real_loads(payload, *args, **kwargs)
            if isinstance(data, dict) and "taskDefinition" in data and len(script.calls) >= 4:
                clock.now = 30
            return data

        monkeypatch.setattr(polling.json, "loads", loads)
        with pytest.raises(polling.DeploymentPollingError, match="deadline expired"):
            _poll(timeout=30)
        assert len(script.calls) == 4
        assert clock.sleeps == []

    def test_evaluation_after_the_deadline_rejects_ready(self, monkeypatch):
        """The confirming decision is not accepted when evaluation reaches the deadline."""
        clock, script = _install(monkeypatch, _ready_pair())
        real_evaluate = polling.evaluate_deployment
        seen = {"ready": 0}

        def evaluate(*args, **kwargs):
            result = real_evaluate(*args, **kwargs)
            if result.outcome == readiness.READY:
                seen["ready"] += 1
                if seen["ready"] == 2:
                    clock.now = 30
            return result

        monkeypatch.setattr(polling, "evaluate_deployment", evaluate)
        with pytest.raises(polling.DeploymentPollingError, match="deadline expired"):
            _poll(timeout=30)
        assert len(script.calls) == 4
        assert seen["ready"] == 2
        assert clock.sleeps == []

    def test_budgets_shrink_and_sleeps_stop_at_the_deadline(self, monkeypatch):
        """Later commands and sleeps receive only the time that is still left."""
        actions = [_ok_bytes(b"{"), _ok_bytes(b"{"), _ok_bytes(b"not-json")]
        clock, script = _install(monkeypatch, actions)

        with pytest.raises(polling.DeploymentPollingError, match="deadline expired") as caught:
            _poll(timeout=25, interval=15)

        assert "secret-aws-token" not in str(caught.value)
        assert script.timeouts == [25, 10]
        assert _targets(script, "--cli-read-timeout") == ["10", "10"]
        assert clock.sleeps == [15, 10]
        assert len(script.calls) == 2

    def test_fractional_budget_keeps_a_positive_socket_timeout(self, monkeypatch):
        """A fraction of a second must not disable the AWS socket timeout."""
        _clock, script = _install(monkeypatch, [_ok_bytes(b"{")])

        with pytest.raises(polling.DeploymentPollingError, match="deadline expired"):
            _poll(timeout=0.4, interval=15)

        args = script.calls[0][0]
        assert args[args.index("--cli-connect-timeout") + 1] == "1"
        assert args[args.index("--cli-read-timeout") + 1] == "1"
        assert script.timeouts == [pytest.approx(0.4)]

    def test_commands_use_json_and_preserve_credentials(self, monkeypatch):
        """The AWS CLI is selected explicitly and inherits the caller credentials."""
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "secret-access-token")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-key-token")
        monkeypatch.setenv("AWS_SESSION_TOKEN", "secret-session-token")
        _clock, script = _install(monkeypatch, _ready_pair())

        _poll(timeout=600)

        args, kwargs = script.calls[0]
        assert args[:3] == ["aws", "ecs", "describe-services"]
        assert "--output" in args and args[args.index("--output") + 1] == "json"
        assert "--no-cli-pager" in args
        assert "--no-cli-auto-prompt" in args
        assert kwargs["env"]["AWS_ACCESS_KEY_ID"] == "secret-access-token"
        assert kwargs["env"]["AWS_SECRET_ACCESS_KEY"] == "secret-key-token"
        assert kwargs["env"]["AWS_SESSION_TOKEN"] == "secret-session-token"
        task_args = script.calls[1][0]
        assert task_args[:3] == ["aws", "ecs", "describe-task-definition"]
        assert "thunderbird-website-prod" not in task_args

    def test_decoder_limits_are_unsuccessful_and_then_recover(self, monkeypatch):
        """An oversized integer or a recursive document is retried, not raised."""
        huge = b'{"value":' + b"1" * 4301 + b"}"
        nested = b"[" * 1000 + b"]" * 1000
        clock, script = _install(monkeypatch, [_ok_bytes(huge), _ok_bytes(nested), *_ready_pair()])

        result = _poll(timeout=80, interval=5)

        assert result.outcome == readiness.READY
        assert clock.sleeps == [5, 5]
        assert len(script.calls) == 6


def _ok_bytes(payload):
    """Return raw stdout that is not rewritten by the JSON helper."""
    def action(process, _clock, _budget):
        process.returncode = 0
        return payload, b"secret-aws-token"
    return action
