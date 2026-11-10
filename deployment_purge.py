"""Persist deployment intents using revision-guarded Git state."""

from cache_purge import PurgeState, begin_deployment_intent
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
