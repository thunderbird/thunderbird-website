"""Prepare a deployment intent, and purge its pending hostnames after rollout."""

from collections.abc import Mapping

from cache_purge import (
    DeploymentIntent,
    PurgeConfiguration,
    PurgeState,
    begin_deployment_intent,
    content_fingerprints,
    purge_hostnames,
    record_intent_acceptance,
    validate_api_token,
)
from deployment_content import read_content_snapshot
from deployment_polling import poll_deployment_readiness
from deployment_readiness import READY
from purge_state_store import (
    PurgeStateAbsent,
    PurgeStateSnapshot,
    read_purge_state,
    write_purge_state,
)


def persist_deployment_intent(workspace, remote, ref, path, identity, image, fingerprints):
    """Persist one deployment intent and return its ``PurgeStateSnapshot``.

    Before Pulumi can expose content, the caller must validate configuration
    and credentials and successfully persist this intent. Persistence does
    not establish deployment readiness or authorize a purge.

    Only a confirmed missing state ref initializes empty state. The intent
    is prepared with ``begin_deployment_intent`` and published against the
    exact revision read, or expected absence for initialization. Pending
    work is retained and no purge acceptance is recorded.

    Input and storage errors propagate, including revision conflicts.
    Conflicts are not reread, merged, or replayed.
    """
    snapshot = read_purge_state(workspace, remote, ref, path)
    if isinstance(snapshot, PurgeStateAbsent):
        current = PurgeState({}, frozenset(), None)
        expected = None
    else:
        current = snapshot.state
        expected = snapshot.revision
    planned = begin_deployment_intent(current, identity, image, fingerprints)
    revision = write_purge_state(workspace, remote, ref, path, expected, planned)
    return PurgeStateSnapshot(revision, planned)


def prepare_deployment_intent(
    configuration,
    artifact_root,
    credentials,
    workspace,
    remote,
    ref,
    path,
    identity,
    image,
):
    """Fingerprint one configured artifact and persist that deployment intent.

    ``configuration`` is the ``PurgeConfiguration`` returned by
    ``load_purge_config``. ``artifact_root`` is a completed, stable artifact
    directory. ``credentials`` maps each zone alias used by a managed
    hostname to an API token. The remaining arguments are the Git location,
    deployment identity, and digest-pinned image accepted by
    ``persist_deployment_intent``. The supplied configuration is the only
    hostname map. No example or production file is read as a fallback.

    Every zone used by a managed hostname must have a credential, including
    when the artifact matches accepted content. ``require_zone_credentials``
    applies ``validate_api_token`` to each one. That check is local syntax
    only. It does not prove Cloudflare authorization or zone access, and this
    function does not send a purge request. A missing or malformed token
    raises ``ValueError`` before publication and does not drop the hostname.
    The token is not included in the error or the returned
    ``PurgeStateSnapshot``.

    The snapshot is read with ``read_content_snapshot`` and fingerprinted
    with ``content_fingerprints``. A snapshot failure or a revision conflict
    propagates and is not replayed.
    """
    require_zone_credentials(configuration, credentials)
    snapshot = read_content_snapshot(artifact_root)
    fingerprints = content_fingerprints(snapshot, configuration.rules)
    return persist_deployment_intent(
        workspace, remote, ref, path, identity, image, fingerprints)


def require_zone_credentials(configuration, credentials):
    """Reject a run that lacks a locally well-formed token for a used zone.

    ``configuration`` is a ``PurgeConfiguration``. ``credentials`` maps each
    zone alias used by a managed hostname to an API token. The token check is
    ``validate_api_token``: presence and local syntax only. It does not prove
    Cloudflare authorization or zone access. A missing or malformed token
    raises ``ValueError`` and is not included in that error.
    """
    if not isinstance(configuration, PurgeConfiguration):
        raise ValueError("purge configuration is required")
    if not isinstance(credentials, Mapping):
        raise ValueError("zone credentials must be a mapping")
    for zone_name in set(configuration.hostnames.values()):
        if zone_name not in credentials:
            raise ValueError("api_token is required")
        validate_api_token(credentials[zone_name])


def purge_ready_deployment(
    configuration,
    credentials,
    workspace,
    remote,
    ref,
    path,
    intent,
    cluster,
    service,
    region,
    deployment_id,
):
    """Purge one ready deployment's pending hostnames, one zone at a time.

    ``configuration`` and ``credentials`` are the loaded purge configuration
    and zone tokens. ``workspace``, ``remote``, ``ref``, and ``path`` locate
    the purge state. ``intent`` is the ``DeploymentIntent`` the release
    persisted. ``cluster``, ``service``, ``region``, and ``deployment_id``
    select this run's ECS deployment. The hostname map in ``configuration``
    is the only zone assignment. No example file is opened.

    Credentials are checked before any purge. Missing state is an error and
    is not initialized. The stored intent must match ``intent``'s identity,
    image, and fingerprints. A configuration that omits an intended hostname
    is rejected instead of dropping that hostname.

    Eligible work is pending hostnames that belong to both ``intent`` and
    the configuration. Other pending names stay recorded and are not sent.
    No eligible work returns the current snapshot without AWS or Cloudflare
    calls.

    Hostnames are grouped by zone name, in lexicographic order, from the
    snapshot that selected them. Each zone starts only when the stored
    revision equals that planning revision, or the revision returned by this
    coordinator's latest acceptance write. An unexpected revision stops the
    run before that zone is polled or sent. The newer state is not adopted,
    the planned groups are not replayed, and the winning writer is not
    overwritten. A matching revision must still name this intent.
    ``poll_deployment_readiness`` must then be ready for this deployment and
    image, and a re-read must show the same revision and intent. Those
    observations are not locks. The caller must serialize production
    deployments.

    ``purge_hostnames`` sends that zone's hosts. After acceptance,
    ``record_intent_acceptance`` is persisted against the revision checked
    before the request. That write finishes before the next zone. A failed
    request or a failed write stops the run. Earlier recorded acceptances
    remain. A purge accepted remotely but not persisted stays pending and
    may be repeated. The two services are not one atomic update.

    Returns the latest persisted ``PurgeStateSnapshot``.
    """
    require_zone_credentials(configuration, credentials)
    _require_intent_coverage(configuration, intent)
    snapshot = _owned_snapshot(workspace, remote, ref, path, intent)
    groups = _zone_groups(configuration, _eligible(snapshot.state, configuration, intent))
    if not groups:
        return snapshot
    for zone_name, hostnames in groups:
        before = _owned_snapshot(workspace, remote, ref, path, intent)
        if before.revision != snapshot.revision:
            raise ValueError("purge state changed")
        outcome = poll_deployment_readiness(cluster, service, region, deployment_id, intent.image)
        if outcome.outcome != READY:
            raise ValueError("deployment is not ready")
        after = _owned_snapshot(workspace, remote, ref, path, intent, allow_mismatch=True)
        if after.revision != before.revision or not _same_intent(after.state.intent, intent):
            raise ValueError("purge state changed")
        purge_hostnames(configuration.zones[zone_name], hostnames, credentials[zone_name])
        accepted = {hostname: intent.fingerprints[hostname] for hostname in hostnames}
        updated = record_intent_acceptance(after.state, intent.identity, accepted)
        revision = write_purge_state(workspace, remote, ref, path, after.revision, updated)
        snapshot = PurgeStateSnapshot(revision, updated)
    return snapshot


def _require_intent_coverage(configuration, intent):
    """Reject an intent the supplied configuration cannot address."""
    if not isinstance(intent, DeploymentIntent):
        raise ValueError("deployment intent is required")
    for hostname in intent.fingerprints:
        zone_name = configuration.hostnames.get(hostname)
        if not isinstance(zone_name, str) or zone_name not in configuration.zones:
            raise ValueError("purge configuration does not cover the expected intent")


def _owned_snapshot(workspace, remote, ref, path, intent, allow_mismatch=False):
    """Read purge state and require the expected intent unless a re-read may differ."""
    snapshot = read_purge_state(workspace, remote, ref, path)
    if isinstance(snapshot, PurgeStateAbsent):
        raise ValueError("purge state is required")
    if not allow_mismatch and not _same_intent(snapshot.state.intent, intent):
        raise ValueError("purge state intent does not match the expected deployment")
    return snapshot


def _same_intent(current, expected):
    """Return whether two intents name the same deployment inputs."""
    if not isinstance(current, DeploymentIntent):
        return False
    return (
        current.identity == expected.identity
        and current.image == expected.image
        and dict(current.fingerprints) == dict(expected.fingerprints)
    )


def _eligible(state, configuration, intent):
    """Return pending hostnames owned by this intent and configuration."""
    return {
        hostname
        for hostname in state.pending
        if hostname in intent.fingerprints and hostname in configuration.hostnames
    }


def _zone_groups(configuration, hostnames):
    """Group hostnames by configured zone name, in stable order."""
    grouped = {}
    for hostname in sorted(hostnames):
        grouped.setdefault(configuration.hostnames[hostname], []).append(hostname)
    return [(zone_name, tuple(grouped[zone_name])) for zone_name in sorted(grouped)]
