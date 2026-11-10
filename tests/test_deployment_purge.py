"""Pre-rollout deployment-intent persistence through the real Git adapter."""

import pytest

import cache_purge
import deployment_purge
import purge_state_store as store
from test_purge_state_store import (
    DOCUMENT,
    REF,
    _IMAGE_B,
    _IMAGE_C,
    _assert_hidden,
    _begin,
    _fingerprints,
    _git,
    _layout,
    _publish,
    _read,
    _remote_revision,
    _workspace,
    _write,
)


def _persist(workspace, remote, identity, image, fingerprints):
    """Register one intent through the pre-rollout orchestration."""
    return deployment_purge.persist_deployment_intent(
        str(workspace), str(remote), REF, DOCUMENT, identity, image, fingerprints)


def _release(marker):
    """Return fingerprints whose every managed hostname changes with ``marker``."""
    return cache_purge.content_fingerprints(
        {
            "www.example/index.html": marker,
            "start.example/index.html": marker,
        },
        (
            ("www.example/", ("www.example",)),
            ("start.example/", ("start.example",)),
        ),
    )


def _reject_hook(remote):
    """Install a remote hook that rejects every publication."""
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho secret-hook-token >&2\nexit 1\n")
    hook.chmod(0o755)
    return hook


class TestPersistDeploymentIntent:
    """One read, one intent transition, and one conditional publication."""

    def test_initial_registration_reads_back(self, tmp_path):
        """Confirmed absence starts empty, and the published snapshot reads back."""
        reader, writer, remote = _layout(tmp_path)
        fingerprints = _fingerprints(b"first")
        assert isinstance(_read(writer, remote), store.PurgeStateAbsent)

        result = _persist(writer, remote, "intent-a", _IMAGE_B, fingerprints)
        snapshot = _read(reader, remote)
        document = _git(remote, "cat-file", "blob", f"{result.revision}:{DOCUMENT}").stdout

        assert isinstance(result, store.PurgeStateSnapshot)
        assert snapshot == result
        assert cache_purge.decode_purge_state(document.decode()) == result.state
        assert result.state.purged == {}
        assert result.state.pending == frozenset(fingerprints)
        assert result.state.intent.identity == "intent-a"
        assert result.state.intent.image == _IMAGE_B
        assert result.state.intent.fingerprints == fingerprints
        assert _remote_revision(remote) == result.revision

    def test_updates_existing_accepted_and_pending_state(self, tmp_path):
        """A later intent keeps accepted fingerprints and outstanding hostnames."""
        reader, writer, remote = _layout(tmp_path)
        accepted = _fingerprints(b"accepted")
        seeded = cache_purge.record_intent_acceptance(
            _begin("intent-a", _IMAGE_B, accepted, pending={"old.example"}),
            "intent-a",
            {"www.example": accepted["www.example"]},
        )
        revision = _write(writer, remote, None, seeded)
        updated = _fingerprints(b"updated")

        result = _persist(writer, remote, "intent-b", _IMAGE_C, updated)
        snapshot = _read(reader, remote)

        assert result.revision != revision
        assert snapshot == result
        assert result.state.purged == {"www.example": accepted["www.example"]}
        assert result.state.pending == frozenset({"old.example", "start.example", "www.example"})
        assert result.state.intent.identity == "intent-b"
        assert result.state.intent.image == _IMAGE_C
        assert result.state.intent.fingerprints == updated

    def test_pending_work_survives_a_content_revert(self, tmp_path):
        """Returning to an accepted fingerprint does not clear the unpublished purge."""
        reader, writer, remote = _layout(tmp_path)
        original = _release(b"original")
        changed = _release(b"changed")
        registered = _persist(writer, remote, "intent-a", _IMAGE_B, original)
        accepted = cache_purge.record_intent_acceptance(registered.state, "intent-a", original)
        _write(writer, remote, registered.revision, accepted)

        intermediate = _persist(writer, remote, "intent-b", _IMAGE_C, changed)
        reverted = _persist(writer, remote, "intent-a-again", _IMAGE_B, original)
        snapshot = _read(reader, remote)

        assert accepted.pending == frozenset()
        assert intermediate.state.pending == frozenset({"www.example", "start.example"})
        assert intermediate.state.purged == original
        assert reverted.state.pending == frozenset({"www.example", "start.example"})
        assert reverted.state.purged == original
        assert reverted.state.intent.identity == "intent-a-again"
        assert snapshot == reverted

    def test_pending_hostnames_absent_from_the_intent_remain_recorded(self, tmp_path):
        """Hostnames this intent does not publish stay pending and unaccepted."""
        reader, writer, remote = _layout(tmp_path)
        fingerprints = _fingerprints(b"managed")
        seeded = _begin("intent-a", _IMAGE_B, fingerprints, pending={"old.example"})
        _write(writer, remote, None, seeded)
        narrow = {"www.example": fingerprints["www.example"]}

        result = _persist(writer, remote, "intent-b", _IMAGE_C, narrow)
        snapshot = _read(reader, remote)

        assert snapshot == result
        assert "old.example" not in result.state.intent.fingerprints
        assert "start.example" not in result.state.intent.fingerprints
        assert result.state.pending == frozenset({"old.example", "start.example", "www.example"})
        assert result.state.purged == {}

    def test_reused_identity_with_different_inputs_is_rejected(self, tmp_path):
        """The stored intent stays in place when the same identity changes inputs."""
        reader, writer, remote = _layout(tmp_path)
        fingerprints = _fingerprints(b"bound")
        stored = _persist(writer, remote, "intent-a", _IMAGE_B, fingerprints)
        revision = _remote_revision(remote)

        with pytest.raises(ValueError, match="already bound"):
            _persist(writer, remote, "intent-a", _IMAGE_C, fingerprints)
        with pytest.raises(ValueError, match="already bound"):
            _persist(writer, remote, "intent-a", _IMAGE_B, _fingerprints(b"other"))

        assert _remote_revision(remote) == revision
        assert _read(reader, remote) == stored

    def test_corrupt_stored_state_fails_without_replacement(self, tmp_path):
        """A missing or malformed document is an error and is left in place."""
        reader, writer, remote = _layout(tmp_path)
        missing = _publish(writer, remote, {"notes/readme.txt": b"present\n"})
        with pytest.raises(store.PurgeStateStoreError, match="missing") as absent_document:
            _persist(writer, remote, "intent-a", _IMAGE_B, _fingerprints(b"missing"))

        assert type(absent_document.value) is store.PurgeStateStoreError
        _assert_hidden(absent_document.value, remote)
        assert _remote_revision(remote) == missing
        assert _git(remote, "cat-file", "-e", f"{missing}:{DOCUMENT}", check=False).returncode != 0
        assert _git(remote, "cat-file", "blob", f"{missing}:notes/readme.txt").stdout == b"present\n"
        with pytest.raises(store.PurgeStateStoreError, match="missing"):
            _read(reader, remote)

        _git(remote, "update-ref", "-d", REF)
        planted = _publish(writer, remote, {DOCUMENT: b'{"secret-state-token":'})
        with pytest.raises(store.PurgeStateStoreError, match="invalid") as malformed:
            _persist(writer, remote, "intent-a", _IMAGE_B, _fingerprints(b"corrupt"))

        assert type(malformed.value) is store.PurgeStateStoreError
        assert "secret-state-token" not in str(malformed.value)
        assert _remote_revision(remote) == planted
        assert _git(remote, "cat-file", "blob", f"{planted}:{DOCUMENT}").stdout == b'{"secret-state-token":'

    def test_other_writer_wins_between_read_and_publication(self, monkeypatch, tmp_path):
        """A revision that moved after the read is preserved, without replaying the loser."""
        reader, writer, remote = _layout(tmp_path)
        other = tmp_path / "secret-remote-token" / "other"
        _workspace(other)
        base = _persist(writer, remote, "intent-base", _IMAGE_B, _fingerprints(b"base"))
        winner = cache_purge.begin_deployment_intent(
            base.state, "intent-winner", _IMAGE_C, _fingerprints(b"winner"))
        calls = []

        def publish_winner(workspace, remote_url, ref, path, expected_revision, state, timeout=30):
            calls.append((expected_revision, state.intent.identity))
            if len(calls) == 1:
                store.write_purge_state(
                    str(other), str(remote), ref, path, expected_revision, winner, timeout)
            return store.write_purge_state(
                workspace, remote_url, ref, path, expected_revision, state, timeout)

        monkeypatch.setattr(deployment_purge, "write_purge_state", publish_winner)
        with pytest.raises(store.PurgeStateConflict) as caught:
            _persist(writer, remote, "intent-loser", _IMAGE_B, _fingerprints(b"loser"))

        snapshot = _read(reader, remote)
        _assert_hidden(caught.value, remote)
        assert calls == [(base.revision, "intent-loser")]
        assert snapshot.state == winner
        assert snapshot.state.intent.identity == "intent-winner"
        assert "intent-loser" not in cache_purge.encode_purge_state(snapshot.state)

    def test_publication_failure_has_no_successful_result(self, tmp_path):
        """A rejected publication raises and leaves the previous ref unchanged."""
        reader, writer, remote = _layout(tmp_path)
        hook = _reject_hook(remote)
        with pytest.raises(store.PurgeStateStoreError, match="command failed") as initial:
            _persist(writer, remote, "intent-a", _IMAGE_B, _fingerprints(b"blocked"))

        assert type(initial.value) is store.PurgeStateStoreError
        assert "secret-hook-token" not in str(initial.value)
        assert _remote_revision(remote) is None

        hook.unlink()
        stored = _persist(writer, remote, "intent-a", _IMAGE_B, _fingerprints(b"stored"))
        _reject_hook(remote)
        with pytest.raises(store.PurgeStateStoreError, match="command failed") as update:
            _persist(writer, remote, "intent-b", _IMAGE_C, _fingerprints(b"rejected"))

        assert type(update.value) is store.PurgeStateStoreError
        assert "secret-hook-token" not in str(update.value)
        assert _read(reader, remote) == stored
