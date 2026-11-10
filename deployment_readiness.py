"""Decide whether a supplied ECS deployment is ready for a cache purge.

The service object is one element of a DescribeServices ``services`` list.
The task-definition object is the DescribeTaskDefinition ``taskDefinition``.
This module does not call AWS, poll, or record that the decision remains true.

Pulumi names the application container ``web``. Readiness uses that container's
image, the primary deployment, and the task-definition ARN on that deployment.
Service and deployment task counts are required for the decision. The ECS
schema marks those integers optional; a missing count is still unusable.
"""

import re
from collections.abc import Mapping
from typing import NamedTuple


# pulumi/__main__.py sets the service container and load-balancer name to "web".
APPLICATION_CONTAINER = "web"

READY = "ready"
WAITING = "waiting"
SUPERSEDED = "superseded"
FAILED = "failed"
INVALID = "invalid"

_DIGEST_IMAGE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
_DEPLOYMENT_STATUSES = frozenset({"PRIMARY", "ACTIVE", "INACTIVE"})
_SUPERSEDED_STATUSES = frozenset({"ACTIVE", "INACTIVE"})


class DeploymentEvaluation(NamedTuple):
    """The readiness decision for one supplied observation.

    ``outcome`` is ``ready``, ``waiting``, ``superseded``, ``failed``, or
    ``invalid``. A ready result does not mean the service stays in that state.
    """

    outcome: str


def evaluate_deployment(
    service: Mapping,
    task_definition: Mapping,
    image: str,
    deployment_id: str | None = None,
) -> DeploymentEvaluation:
    """Evaluate one ECS service observation against an immutable image.

    ``image`` must be the digest-pinned reference for this run. A tag without
    ``@sha256:<64 hex>`` is not sufficient, even when it equals the container
    image. ``deployment_id`` selects the deployment this workflow started.
    When it is omitted, only the current PRIMARY deployment is evaluated, and
    the result does not establish that this workflow owns that deployment.

    Every deployment needs a unique string id and a status of PRIMARY, ACTIVE,
    or INACTIVE. Exactly one deployment must be PRIMARY. List, mapping, and
    other status values are invalid. A missing expected id is invalid and is
    not treated as superseded. ACTIVE or INACTIVE, while another deployment is
    PRIMARY, is superseded.

    Ready requires that PRIMARY rollout to be COMPLETED, its task-definition
    ARN to be the supplied task definition, and the ``web`` image to match
    ``image`` exactly. The service ``desiredCount``, ``runningCount``, and
    ``pendingCount`` must be non-negative integers and must describe the same
    steady capacity as the deployments: the primary desired count equals the
    service desired count, that desired count is positive, service and primary
    running counts equal it, every pending count is 0, and every other
    deployment has no running or pending tasks. INACTIVE means the deployment
    was completely replaced, so its running and pending counts must be 0.
    ACTIVE means it still has running tasks.

    IN_PROGRESS is waiting when those count fields are present, well typed,
    and internally consistent, whether or not the counts are already steady.
    Consistency means the service desired count equals the primary desired
    count, and the service running and pending counts equal the sums of the
    deployment counts. Partial capacity, scaling, and an older deployment that
    still has tasks are waiting only while the rollout is IN_PROGRESS. Those
    shapes are invalid when the rollout says COMPLETED. A missing, negative,
    boolean, or non-integer count is invalid, as is a service total that does
    not match its deployments. That disagreement is contradictory evidence,
    not an incomplete rollout.

    A present service ``taskDefinition`` must match the primary deployment.
    The caller still has to read the intended cluster and service, pass the
    digest of the image built for this run, and treat a result without a
    deployment id as unowned. This function cannot guarantee that the
    deployment stays in the observed state.
    """
    if not digest_pinned(image):
        return DeploymentEvaluation(INVALID)
    deployments = _deployment_list(service)
    if deployments is None:
        return DeploymentEvaluation(INVALID)
    primary = _primary_deployment(deployments)
    if primary is None:
        return DeploymentEvaluation(INVALID)
    if deployment_id is not None:
        if not isinstance(deployment_id, str) or deployment_id == "":
            return DeploymentEvaluation(INVALID)
        intended = _deployment_with_id(deployments, deployment_id)
        if intended is None:
            return DeploymentEvaluation(INVALID)
        if intended.get("status") in _SUPERSEDED_STATUSES:
            return DeploymentEvaluation(SUPERSEDED)
    return _evaluate_primary(primary, deployments, service, task_definition, image)


def _evaluate_primary(primary, deployments, service, task_definition, image):
    """Evaluate the single current PRIMARY deployment."""
    state = primary.get("rolloutState")
    if state == "FAILED":
        return DeploymentEvaluation(FAILED)
    observed = _application_image(primary, service, task_definition)
    if observed is None or observed != image:
        return DeploymentEvaluation(INVALID)
    steady = _reconcile_counts(service, deployments, primary)
    if steady is None:
        return DeploymentEvaluation(INVALID)
    if state == "IN_PROGRESS":
        return DeploymentEvaluation(WAITING)
    if state == "COMPLETED" and steady:
        return DeploymentEvaluation(READY)
    return DeploymentEvaluation(INVALID)


def _deployment_list(service):
    """Return deployment mappings, or None when that list is not usable."""
    if not isinstance(service, Mapping):
        return None
    deployments = service.get("deployments")
    if not isinstance(deployments, list) or not deployments:
        return None
    if not all(isinstance(item, Mapping) for item in deployments):
        return None
    return deployments


def _primary_deployment(deployments):
    """Return the only PRIMARY deployment, or None when identities are ambiguous."""
    seen = set()
    primary = None
    for deployment in deployments:
        status = deployment.get("status")
        if not isinstance(status, str) or status not in _DEPLOYMENT_STATUSES:
            return None
        identity = deployment.get("id")
        if not isinstance(identity, str) or identity == "" or identity in seen:
            return None
        seen.add(identity)
        if status != "PRIMARY":
            continue
        if primary is not None:
            return None
        primary = deployment
    return primary


def _deployment_with_id(deployments, deployment_id):
    """Return the deployment with this id. Identities were already proven unique."""
    for deployment in deployments:
        if deployment.get("id") == deployment_id:
            return deployment
    return None


def _application_image(deployment, service, task_definition):
    """Return the web container image when the task definition is this deployment's."""
    if not isinstance(task_definition, Mapping):
        return None
    identity = deployment.get("taskDefinition")
    arn = task_definition.get("taskDefinitionArn")
    if not isinstance(identity, str) or identity == "" or identity != arn:
        return None
    if "taskDefinition" in service and service.get("taskDefinition") != identity:
        return None
    containers = task_definition.get("containerDefinitions")
    if not isinstance(containers, list):
        return None
    images = [
        container.get("image")
        for container in containers
        if isinstance(container, Mapping) and container.get("name") == APPLICATION_CONTAINER
    ]
    if len(images) != 1 or not isinstance(images[0], str):
        return None
    return images[0]


def _reconcile_counts(service, deployments, primary):
    """Return whether reconciled task counts describe a steady service.

    ``True`` means the service and its deployments agree on one positive
    steady capacity. ``False`` means those fields agree but work remains.
    ``None`` means a required count is missing, malformed, or contradictory.
    """
    service_desired = _count(service.get("desiredCount"))
    service_running = _count(service.get("runningCount"))
    service_pending = _count(service.get("pendingCount"))
    primary_desired = _count(primary.get("desiredCount"))
    primary_running = _count(primary.get("runningCount"))
    primary_pending = _count(primary.get("pendingCount"))
    if None in (service_desired, service_running, service_pending, primary_desired, primary_running, primary_pending):
        return None
    if primary_desired != service_desired:
        return None
    running_total = 0
    pending_total = 0
    others_idle = True
    for deployment in deployments:
        running = _count(deployment.get("runningCount"))
        pending = _count(deployment.get("pendingCount"))
        if running is None or pending is None:
            return None
        status = deployment.get("status")
        if status == "ACTIVE" and running < 1:
            return None
        if status == "INACTIVE" and (running != 0 or pending != 0):
            return None
        if deployment.get("id") != primary.get("id") and (running != 0 or pending != 0):
            others_idle = False
        running_total += running
        pending_total += pending
    if running_total != service_running or pending_total != service_pending:
        return None
    return (
        others_idle
        and service_desired >= 1
        and service_running == service_desired
        and service_pending == 0
        and primary_running == service_desired
        and primary_pending == 0
    )


def _count(value):
    """Return a non-negative integer count, rejecting booleans and other types."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def digest_pinned(image):
    """Return whether the reference names an image by its sha256 digest."""
    return isinstance(image, str) and _DIGEST_IMAGE.fullmatch(image) is not None
