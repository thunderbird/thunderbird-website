"""Prepare and persist a deployment intent before rollout."""

from collections.abc import Mapping

from cache_purge import (
    PurgeConfiguration,
    PurgeState,
    begin_deployment_intent,
    content_fingerprints,
    validate_api_token,
)
from deployment_content import read_content_snapshot
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
