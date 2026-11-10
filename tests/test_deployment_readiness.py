"""ECS deployment readiness from caller-supplied service data."""

import copy

import pytest

import deployment_readiness as readiness


DIGEST = "a" * 64
OTHER_DIGEST = "b" * 64
IMAGE = f"123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod@sha256:{DIGEST}"
OTHER_IMAGE = f"123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod@sha256:{OTHER_DIGEST}"
TASK = "arn:aws:ecs:us-west-2:123456789012:task-definition/thunderbird-website-prod:42"
OTHER_TASK = "arn:aws:ecs:us-west-2:123456789012:task-definition/thunderbird-website-prod:41"
INTENDED = "ecs-svc/1111111111111111111"
CURRENT = "ecs-svc/2222222222222222222"


def _deployment(**overrides):
    deployment = {
        "id": INTENDED,
        "status": "PRIMARY",
        "taskDefinition": TASK,
        "desiredCount": 8,
        "pendingCount": 0,
        "runningCount": 8,
        "failedTasks": 0,
        "rolloutState": "COMPLETED",
    }
    deployment.update(overrides)
    return deployment


def _service(*deployments, **overrides):
    service = {
        "deployments": list(deployments),
        "taskDefinition": TASK,
        "desiredCount": 8,
        "runningCount": 8,
        "pendingCount": 0,
    }
    service.update(overrides)
    return service


def _task(image=IMAGE, arn=TASK):
    return {
        "taskDefinitionArn": arn,
        "containerDefinitions": [{"name": "web", "image": image, "essential": True}],
    }


class TestDeploymentReadiness:
    """Readiness uses the current primary deployment and a digest-pinned image."""

    def test_completed_primary_with_expected_image_is_ready(self):
        """A steady primary is ready when the replaced deployment has no remaining tasks."""
        older = _deployment(
            id=CURRENT,
            status="INACTIVE",
            rolloutState="COMPLETED",
            taskDefinition=OTHER_TASK,
            runningCount=0,
            pendingCount=0,
        )
        evaluation = readiness.evaluate_deployment(_service(_deployment(), older), _task(), IMAGE, INTENDED)

        assert evaluation == readiness.DeploymentEvaluation(readiness.READY)

    def test_in_progress_primary_is_waiting(self):
        """A started rollout waits even when its task counts already match."""
        deployment = _deployment(rolloutState="IN_PROGRESS")
        evaluation = readiness.evaluate_deployment(_service(deployment), _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.WAITING

    def test_another_completed_deployment_does_not_make_the_intended_one_ready(self):
        """An older deployment that still has tasks does not finish the current rollout."""
        intended = _deployment(rolloutState="IN_PROGRESS", runningCount=4, pendingCount=4)
        previous = _deployment(
            id=CURRENT, status="ACTIVE", rolloutState="COMPLETED", taskDefinition=OTHER_TASK, runningCount=8, pendingCount=0)
        service = _service(intended, previous, runningCount=12, pendingCount=4)
        evaluation = readiness.evaluate_deployment(service, _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.WAITING

    @pytest.mark.parametrize("status,running,pending,service_running", [
        ("ACTIVE", 8, 0, 16),
        ("INACTIVE", 0, 0, 8),
    ])
    def test_replaced_intended_deployment_is_superseded(self, status, running, pending, service_running):
        """An intended deployment that is no longer primary has been replaced."""
        intended = _deployment(status=status, rolloutState="COMPLETED", runningCount=running, pendingCount=pending)
        current = _deployment(id=CURRENT, rolloutState="COMPLETED", taskDefinition=OTHER_TASK)
        service = _service(intended, current, runningCount=service_running)
        evaluation = readiness.evaluate_deployment(service, _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.SUPERSEDED

    def test_missing_expected_deployment_is_invalid(self):
        """Absence of the expected id is not evidence that it was superseded."""
        evaluation = readiness.evaluate_deployment(_service(_deployment(id=CURRENT)), _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.INVALID

    def test_failed_rollout_is_not_ready(self):
        """A failed primary rollout does not allow a purge."""
        evaluation = readiness.evaluate_deployment(
            _service(_deployment(rolloutState="FAILED")), _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.FAILED

    @pytest.mark.parametrize("image", [
        "123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod:latest",
        "123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod:" + "a" * 40,
    ])
    def test_mutable_tag_expectation_is_not_ready(self, image):
        """A tag that equals the container image is not an immutable reference."""
        evaluation = readiness.evaluate_deployment(_service(_deployment()), _task(image=image), image, INTENDED)

        assert evaluation.outcome == readiness.INVALID

    @pytest.mark.parametrize("observed", [
        OTHER_IMAGE,
        "123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod:latest",
    ])
    def test_container_image_must_equal_the_pinned_expectation(self, observed):
        """The web container must contain the expected digest, not another reference."""
        evaluation = readiness.evaluate_deployment(_service(_deployment()), _task(image=observed), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.INVALID

    def test_contradictory_service_task_definition_is_invalid(self):
        """A service task definition that disagrees with the deployment is unusable."""
        evaluation = readiness.evaluate_deployment(
            _service(_deployment(), taskDefinition=OTHER_TASK), _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.INVALID

    def test_task_definition_identity_mismatch_is_invalid(self):
        """The deployment's task-definition ARN must be the supplied definition."""
        evaluation = readiness.evaluate_deployment(
            _service(_deployment()), _task(arn=OTHER_TASK), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.INVALID

    def test_missing_application_container_is_invalid(self):
        """Readiness needs the web container named by the Pulumi service."""
        task = _task()
        task["containerDefinitions"] = [{"name": "sidecar", "image": IMAGE}]
        evaluation = readiness.evaluate_deployment(_service(_deployment()), task, IMAGE, INTENDED)

        assert evaluation.outcome == readiness.INVALID

    @pytest.mark.parametrize("deployment_counts,service_counts", [
        ({"runningCount": 7}, {}),
        ({"pendingCount": 1}, {}),
        ({"desiredCount": 0}, {}),
        ({"desiredCount": True, "runningCount": True}, {}),
        ({"runningCount": "8"}, {}),
        ({"runningCount": 8.0}, {}),
        ({"runningCount": []}, {}),
        ({"pendingCount": -1}, {}),
        ({"rolloutState": None}, {}),
        ({}, {"desiredCount": 16, "runningCount": 8, "pendingCount": 8}),
        ({}, {"runningCount": "8"}),
        ({}, {"pendingCount": []}),
        ({}, {"desiredCount": True}),
        ({}, {"runningCount": -1}),
    ])
    def test_inconsistent_or_malformed_counts_are_invalid(self, deployment_counts, service_counts):
        """Required service and deployment counts must be usable non-negative integers."""
        evaluation = readiness.evaluate_deployment(
            _service(_deployment(**deployment_counts), **service_counts), _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.INVALID

    @pytest.mark.parametrize("rollout_state", ["COMPLETED", "IN_PROGRESS"])
    def test_conflicting_service_and_deployment_counts_are_invalid(self, rollout_state):
        """A service total that disagrees with its deployments is not an incomplete rollout."""
        deployment = _deployment(rolloutState=rollout_state)
        service = _service(deployment, desiredCount=16, runningCount=8, pendingCount=8)
        evaluation = readiness.evaluate_deployment(service, _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.INVALID

    @pytest.mark.parametrize("status,running,pending,service_running,service_pending", [
        ("ACTIVE", 2, 0, 10, 0),
        ("ACTIVE", 1, 1, 9, 1),
        ("INACTIVE", 8, 0, 16, 0),
        ("INACTIVE", 0, 2, 8, 2),
    ])
    def test_older_deployment_with_remaining_tasks_is_not_ready(self, status, running, pending, service_running, service_pending):
        """A completed primary is not steady while another deployment still has tasks."""
        older = _deployment(
            id=CURRENT,
            status=status,
            rolloutState="COMPLETED",
            taskDefinition=OTHER_TASK,
            runningCount=running,
            pendingCount=pending,
        )
        service = _service(_deployment(), older, runningCount=service_running, pendingCount=service_pending)
        evaluation = readiness.evaluate_deployment(service, _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.INVALID

    def test_incomplete_capacity_waits(self):
        """A consistent rollout that has not reached the desired count is waiting."""
        deployment = _deployment(rolloutState="IN_PROGRESS", runningCount=4, pendingCount=4)
        service = _service(deployment, runningCount=4, pendingCount=4)
        evaluation = readiness.evaluate_deployment(service, _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.WAITING

    def test_scaling_observation_waits(self):
        """Raising the shared desired count waits until the new tasks are running."""
        deployment = _deployment(rolloutState="IN_PROGRESS", desiredCount=10, runningCount=8, pendingCount=2)
        service = _service(deployment, desiredCount=10, runningCount=8, pendingCount=2)
        evaluation = readiness.evaluate_deployment(service, _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.WAITING

    def test_active_deployment_without_running_tasks_is_invalid(self):
        """ACTIVE means tasks are still running, so a zero count contradicts that status."""
        older = _deployment(id=CURRENT, status="ACTIVE", taskDefinition=OTHER_TASK, runningCount=0, pendingCount=0)
        evaluation = readiness.evaluate_deployment(_service(_deployment(), older), _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.INVALID

    def test_missing_required_count_is_invalid(self):
        """Absent service or deployment counts are not treated as zero."""
        service = _service(_deployment())
        del service["runningCount"]
        deployment = _deployment()
        del deployment["pendingCount"]

        assert readiness.evaluate_deployment(service, _task(), IMAGE, INTENDED).outcome == readiness.INVALID
        assert readiness.evaluate_deployment(_service(deployment), _task(), IMAGE, INTENDED).outcome == readiness.INVALID

    @pytest.mark.parametrize("deployments", [
        (_deployment(), _deployment(id=CURRENT)),
        (_deployment(status="ACTIVE"),),
        (),
    ])
    def test_multiple_or_missing_primary_deployments_are_invalid(self, deployments):
        """Exactly one PRIMARY deployment is the current deployment."""
        service = _service(*deployments) if deployments else {"deployments": [], "taskDefinition": TASK}
        evaluation = readiness.evaluate_deployment(service, _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.INVALID

    def test_optional_deployment_id_evaluates_only_the_primary_image(self):
        """Omitting the id does not establish which workflow owns the primary."""
        older = _deployment(id=CURRENT, status="INACTIVE", taskDefinition=OTHER_TASK, runningCount=0, pendingCount=0)
        evaluation = readiness.evaluate_deployment(_service(_deployment(), older), _task(), IMAGE)

        assert evaluation.outcome == readiness.READY
        waiting = readiness.evaluate_deployment(_service(_deployment(rolloutState="IN_PROGRESS")), _task(), IMAGE)
        assert waiting.outcome == readiness.WAITING

    @pytest.mark.parametrize("status", [[], {}, "DRAINING"])
    def test_intended_deployment_status_is_validated(self, status):
        """A non-string or unknown status on the expected deployment is invalid."""
        evaluation = readiness.evaluate_deployment(_service(_deployment(status=status)), _task(), IMAGE, INTENDED)

        assert evaluation.outcome == readiness.INVALID

    @pytest.mark.parametrize("deployment_id", [INTENDED, None])
    @pytest.mark.parametrize("status", [[], {}, "DRAINING"])
    def test_malformed_status_is_invalid(self, deployment_id, status):
        """Required deployment statuses are strings with the documented values."""
        sibling = _deployment(id=CURRENT, status=status, runningCount=0, pendingCount=0)
        evaluation = readiness.evaluate_deployment(_service(_deployment(), sibling), _task(), IMAGE, deployment_id)

        assert evaluation.outcome == readiness.INVALID

    @pytest.mark.parametrize("deployment_id", [INTENDED, None])
    def test_duplicate_deployment_identity_is_invalid(self, deployment_id):
        """Two deployments with one id do not identify a current deployment."""
        duplicate = _deployment(id=INTENDED, status="ACTIVE", runningCount=8, pendingCount=0)
        evaluation = readiness.evaluate_deployment(_service(_deployment(), duplicate), _task(), IMAGE, deployment_id)

        assert evaluation.outcome == readiness.INVALID

    def test_inputs_are_not_mutated(self):
        """Evaluation only reads the supplied service and task definition."""
        service = _service(_deployment())
        task = _task()
        original_service = copy.deepcopy(service)
        original_task = copy.deepcopy(task)

        readiness.evaluate_deployment(service, task, IMAGE, INTENDED)

        assert service == original_service
        assert task == original_task
