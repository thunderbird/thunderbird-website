"""Persist one deployment intent before rollout can expose new content.

The caller supplies the Git workspace, remote, fully qualified state ref,
and document path, plus a unique deployment-intent identity, the
digest-pinned image reference, and the hostname fingerprints already
computed for that intent. This module does not choose hostname mappings,
read credentials, start a deployment, extract an image, or contact AWS or
Cloudflare.

The caller must complete configuration and credential checks and
successfully persist this intent before Pulumi can expose new content.
This function does not establish deployment readiness or authorize a purge.
"""

from cache_purge import PurgeState, begin_deployment_intent
from purge_state_store import (
    PurgeStateAbsent,
    PurgeStateSnapshot,
    read_purge_state,
    write_purge_state,
)


def persist_deployment_intent(workspace, remote, ref, path, identity, image, fingerprints):
    """Publish one deployment intent and return the persisted snapshot.

    One read, the ``begin_deployment_intent`` transition, and one
    conditional publication form a single attempt. ``begin_deployment_intent``
    keeps its identity binding, pending-work retention, and fingerprint
    rules. Pending hostnames are not cleared and no purge acceptance is
    recorded.

    The caller must complete configuration and credential checks and
    successfully persist this intent before Pulumi can expose new content.
    This function does not establish deployment readiness or authorize a
    purge.

    Only confirmed absence of the state ref starts from an empty
    ``PurgeState``. A missing document on an existing ref, malformed state,
    authentication failure, or transport failure propagates. Publication
    uses the revision from that read, or expected absence when the ref was
    absent. Success is a ``PurgeStateSnapshot`` of the revision publication
    returned and the state that was written. A revision conflict propagates
    and is not reread, registered again, merged, or replayed.
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
