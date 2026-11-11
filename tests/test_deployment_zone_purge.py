"""Post-deployment zone purges through the real Git adapter."""

from pathlib import Path

import pytest

import cache_purge
import deployment_purge
import purge_state_store as store
from deployment_readiness import FAILED, SUPERSEDED, DeploymentEvaluation
from test_purge_state_store import (
    DOCUMENT,
    REF,
    _IMAGE_B,
    _IMAGE_C,
    _layout,
    _publish,
    _remote_revision,
)


_EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "examples" / "cache-purge.example.json"
_TOKEN = "secret-zone-token"
_TOKENS = {
    "example": "example-zone-token",
    "example_updates": "updates-zone-token",
}
_CLUSTER = "thunderbird-website-prod"
_SERVICE = "thunderbird-website-prod"
_REGION = "us-west-2"
_DEPLOYMENT = "ecs-deploy-1"
_RETIRED = "retired.example"


def _configuration():
    """Load the checked-in example explicitly. Production code has no default."""
    return cache_purge.load_purge_config(_EXAMPLE.read_text(encoding="utf-8"))


def _fingerprints(configuration):
    """Fingerprint one artifact with the example rules."""
    return cache_purge.content_fingerprints(
        {
            "www.example/index.html": b"home\r\n",
            "www.example/en-US/maintenance/index.html": b"down",
            "wsgi.py": b"redirect-a",
        },
        configuration.rules,
    )


def _seed(writer, remote, fingerprints, pending, purged=None, identity="run-1.1", image=_IMAGE_B):
    """Publish one intent directly and return that intent and the stored snapshot."""
    intent = cache_purge.DeploymentIntent(identity, image, dict(fingerprints))
    state = cache_purge.PurgeState(dict(purged or {}), frozenset(pending), intent)
    store.write_purge_state(str(writer), str(remote), REF, DOCUMENT, None, state)
    saved = store.read_purge_state(str(writer), str(remote), REF, DOCUMENT)
    return intent, saved


def _install(monkeypatch, poll=None, purge=None):
    """Stub AWS polling and Cloudflare, recording every attempt."""
    polls = []
    purges = []

    def wrapped_poll(*args, **kwargs):
        polls.append((args, kwargs))
        if poll is not None:
            return poll(*args, **kwargs)
        return DeploymentEvaluation("ready")

    def wrapped_purge(zone_id, hostnames, api_token):
        purges.append((zone_id, tuple(hostnames), api_token))
        if purge is not None:
            return purge(zone_id, hostnames, api_token)
        return cache_purge.PurgeAcceptance("req-1")

    monkeypatch.setattr(deployment_purge, "poll_deployment_readiness", wrapped_poll)
    monkeypatch.setattr(deployment_purge, "purge_hostnames", wrapped_purge)
    return polls, purges


def _run(writer, remote, configuration, intent, credentials=None):
    """Purge one seeded deployment through the coordinator."""
    return deployment_purge.purge_ready_deployment(
        configuration,
        _TOKENS if credentials is None else credentials,
        str(writer),
        str(remote),
        REF,
        DOCUMENT,
        intent,
        _CLUSTER,
        _SERVICE,
        _REGION,
        _DEPLOYMENT,
    )


def _visible(error):
    """Return the text a caller sees for one exception."""
    return "\n".join([str(error), repr(error)])


class TestPurgeReadyDeployment:
    """One expected intent is purged by zone after a ready observation."""

    def test_no_eligible_work_keeps_retired_hostnames(self, monkeypatch, tmp_path):
        """Accepted intent work returns without AWS or Cloudflare, and retired names stay."""
        _reader, writer, remote = _layout(tmp_path)
        configuration = _configuration()
        fingerprints = _fingerprints(configuration)
        intent, seeded = _seed(
            writer,
            remote,
            fingerprints,
            {_RETIRED},
            purged=fingerprints,
        )
        polls, purges = _install(monkeypatch)

        result = _run(writer, remote, configuration, intent)

        assert result == seeded
        assert result.state.pending == frozenset({_RETIRED})
        assert polls == []
        assert purges == []

    def test_ready_deployment_purges_each_zone_in_order(self, monkeypatch, tmp_path):
        """Eligible hosts are sent once, grouped by zone, and retired work stays pending."""
        _reader, writer, remote = _layout(tmp_path)
        configuration = _configuration()
        fingerprints = _fingerprints(configuration)
        intent, seeded = _seed(
            writer, remote, fingerprints, set(fingerprints) | {_RETIRED},
        )
        revisions = []

        def poll(*args, **kwargs):
            revisions.append(store.read_purge_state(str(writer), str(remote), REF, DOCUMENT).revision)
            return DeploymentEvaluation("ready")

        polls, purges = _install(monkeypatch, poll=poll)
        result = _run(writer, remote, configuration, intent)
        saved = store.read_purge_state(str(writer), str(remote), REF, DOCUMENT)
        sent = [hostname for _zone, hosts, _token in purges for hostname in hosts]

        assert [item[:2] for item in purges] == [
            (configuration.zones["example"], ("addons.example", "www.example")),
            (configuration.zones["example_updates"], ("updates.example",)),
        ]
        assert [item[2] for item in purges] == ["example-zone-token", "updates-zone-token"]
        assert sent == ["addons.example", "www.example", "updates.example"]
        assert len(sent) == len(set(sent))
        assert _RETIRED not in sent
        assert len(polls) == 2
        assert all(
            call[0] == (_CLUSTER, _SERVICE, _REGION, _DEPLOYMENT, _IMAGE_B) and call[1] == {}
            for call in polls
        )
        assert revisions[1] != revisions[0]
        assert revisions[1] != seeded.revision
        assert result == saved
        assert result.state.pending == frozenset({_RETIRED})
        assert dict(result.state.purged) == fingerprints
        assert result.state.intent == saved.state.intent

    @pytest.mark.parametrize("outcome", [FAILED, SUPERSEDED])
    def test_unready_deployment_sends_no_request(self, monkeypatch, tmp_path, outcome):
        """A failed or superseded deployment stops before Cloudflare."""
        _reader, writer, remote = _layout(tmp_path)
        configuration = _configuration()
        fingerprints = _fingerprints(configuration)
        intent, seeded = _seed(writer, remote, fingerprints, set(fingerprints))
        polls, purges = _install(
            monkeypatch,
            poll=lambda *_args, **_kwargs: DeploymentEvaluation(outcome),
        )

        with pytest.raises(ValueError, match="^deployment is not ready$"):
            _run(writer, remote, configuration, intent)

        assert len(polls) == 1
        assert purges == []
        assert store.read_purge_state(str(writer), str(remote), REF, DOCUMENT) == seeded

    def test_intent_mismatch_sends_no_request(self, monkeypatch, tmp_path):
        """Identity, image, and fingerprint mismatches are rejected before any request."""
        configuration = _configuration()
        fingerprints = _fingerprints(configuration)
        altered = dict(fingerprints)
        altered["www.example"] = "a" * 64
        cases = (
            ("run-9", _IMAGE_B, fingerprints),
            ("run-1.1", _IMAGE_C, fingerprints),
            ("run-1.1", _IMAGE_B, altered),
        )
        for identity, image, stored in cases:
            _reader, writer, remote = _layout(tmp_path / identity / image[-4:])
            intent, seeded = _seed(writer, remote, stored, set(stored), identity=identity, image=image)
            expected = cache_purge.DeploymentIntent("run-1.1", _IMAGE_B, dict(fingerprints))
            polls, purges = _install(monkeypatch)
            with pytest.raises(ValueError, match="^purge state intent does not match the expected deployment$"):
                _run(writer, remote, configuration, expected)
            assert polls == []
            assert purges == []
            assert store.read_purge_state(str(writer), str(remote), REF, DOCUMENT) == seeded

    def test_incompatible_configuration_is_rejected(self, monkeypatch, tmp_path):
        """A configuration that drops an intended hostname does not purge the others."""
        _reader, writer, remote = _layout(tmp_path)
        configuration = _configuration()
        fingerprints = _fingerprints(configuration)
        intent, seeded = _seed(writer, remote, fingerprints, set(fingerprints))
        narrower = cache_purge.load_purge_config(
            """
            {
              "version": 1,
              "zones": {"example": {"id": "0123456789abcdef0123456789abcdef"}},
              "hostnames": {"www.example": "example", "addons.example": "example"},
              "rules": [
                {"path": "www.example/", "hostnames": ["www.example"]},
                {"path": "www.example/en-US/maintenance/", "hostnames": ["addons.example"]}
              ]
            }
            """
        )
        polls, purges = _install(monkeypatch)

        with pytest.raises(ValueError, match="^purge configuration does not cover the expected intent$"):
            _run(writer, remote, narrower, intent, credentials={"example": "example-zone-token"})

        assert polls == []
        assert purges == []
        assert store.read_purge_state(str(writer), str(remote), REF, DOCUMENT) == seeded

    def test_revision_before_the_first_zone_is_not_purged(self, monkeypatch, tmp_path):
        """A newer revision after planning is left intact, including its acceptance."""
        _reader, writer, remote = _layout(tmp_path)
        configuration = _configuration()
        fingerprints = _fingerprints(configuration)
        intent, seeded = _seed(
            writer, remote, fingerprints, set(fingerprints) | {_RETIRED},
        )
        polls, purges = _install(monkeypatch)
        real_read = deployment_purge.read_purge_state
        winner = []
        calls = {"count": 0}

        def read_after_planning(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                current = store.read_purge_state(str(writer), str(remote), REF, DOCUMENT)
                accepted = {
                    hostname: intent.fingerprints[hostname] for hostname in intent.fingerprints
                }
                updated = cache_purge.record_intent_acceptance(current.state, intent.identity, accepted)
                winner.append(store.write_purge_state(
                    str(writer), str(remote), REF, DOCUMENT, current.revision, updated,
                ))
            return real_read(*args, **kwargs)

        monkeypatch.setattr(deployment_purge, "read_purge_state", read_after_planning)
        with pytest.raises(ValueError, match="^purge state changed$"):
            _run(writer, remote, configuration, intent)

        saved = store.read_purge_state(str(writer), str(remote), REF, DOCUMENT)
        assert polls == []
        assert purges == []
        assert winner == [saved.revision]
        assert saved.revision != seeded.revision
        assert saved.state.pending == frozenset({_RETIRED})
        assert dict(saved.state.purged) == fingerprints
        assert saved.state.intent == intent

    def test_revision_between_zones_stops_the_next_zone(self, monkeypatch, tmp_path):
        """A newer revision after the first acceptance is not polled, purged, or overwritten."""
        _reader, writer, remote = _layout(tmp_path)
        configuration = _configuration()
        fingerprints = _fingerprints(configuration)
        intent, _seeded = _seed(
            writer, remote, fingerprints, set(fingerprints) | {_RETIRED},
        )
        polls, purges = _install(monkeypatch)
        real_write = deployment_purge.write_purge_state
        winner = []

        def persist_then_yield(*args, **kwargs):
            revision = real_write(*args, **kwargs)
            if not winner:
                current = store.read_purge_state(str(writer), str(remote), REF, DOCUMENT)
                updated = cache_purge.PurgeState(
                    dict(current.state.purged),
                    current.state.pending | frozenset({"winner.example"}),
                    current.state.intent,
                )
                winner.append(store.write_purge_state(
                    str(writer), str(remote), REF, DOCUMENT, current.revision, updated,
                ))
            return revision

        monkeypatch.setattr(deployment_purge, "write_purge_state", persist_then_yield)
        with pytest.raises(ValueError, match="^purge state changed$"):
            _run(writer, remote, configuration, intent)

        saved = store.read_purge_state(str(writer), str(remote), REF, DOCUMENT)
        assert len(polls) == 1
        assert [hosts for _zone, hosts, _token in purges] == [("addons.example", "www.example")]
        assert winner == [saved.revision]
        assert saved.state.pending == frozenset({"updates.example", _RETIRED, "winner.example"})
        assert set(saved.state.purged) == {"addons.example", "www.example"}
        assert saved.state.intent == intent

    def test_state_change_during_polling_sends_no_request(self, monkeypatch, tmp_path):
        """A revision that moves while readiness is observed is not purged."""
        _reader, writer, remote = _layout(tmp_path)
        configuration = _configuration()
        fingerprints = _fingerprints(configuration)
        intent, seeded = _seed(writer, remote, fingerprints, set(fingerprints))

        def poll(*_args, **_kwargs):
            current = store.read_purge_state(str(writer), str(remote), REF, DOCUMENT)
            store.write_purge_state(
                str(writer), str(remote), REF, DOCUMENT, current.revision, current.state,
            )
            return DeploymentEvaluation("ready")

        _polls, purges = _install(monkeypatch, poll=poll)
        with pytest.raises(ValueError, match="^purge state changed$"):
            _run(writer, remote, configuration, intent)

        saved = store.read_purge_state(str(writer), str(remote), REF, DOCUMENT)
        assert purges == []
        assert saved.revision != seeded.revision
        assert saved.state == seeded.state

    def test_later_zone_failure_keeps_the_earlier_acceptance(self, monkeypatch, tmp_path):
        """The first zone stays recorded when the next request fails."""
        _reader, writer, remote = _layout(tmp_path)
        configuration = _configuration()
        fingerprints = _fingerprints(configuration)
        intent, _seeded = _seed(
            writer, remote, fingerprints, set(fingerprints) | {_RETIRED},
        )

        def purge(zone_id, hostnames, _api_token):
            purges.append((zone_id, tuple(hostnames)))
            if len(purges) == 2:
                raise cache_purge.PurgeError("Cloudflare purge failed because HTTP 403 was rejected")
            return cache_purge.PurgeAcceptance("req-1")

        purges = []
        _install(monkeypatch, purge=purge)
        with pytest.raises(cache_purge.PurgeError, match="^Cloudflare purge failed because HTTP 403 was rejected$") as caught:
            _run(writer, remote, configuration, intent)

        saved = store.read_purge_state(str(writer), str(remote), REF, DOCUMENT)
        assert [hosts for _zone, hosts in purges] == [
            ("addons.example", "www.example"),
            ("updates.example",),
        ]
        assert saved.state.pending == frozenset({"updates.example", _RETIRED})
        assert set(saved.state.purged) == {"addons.example", "www.example"}
        assert _TOKEN not in _visible(caught.value)
        assert "example-zone-token" not in _visible(caught.value)

    def test_acceptance_conflict_is_not_replayed(self, monkeypatch, tmp_path):
        """A request accepted remotely is not written again after the revision moves."""
        _reader, writer, remote = _layout(tmp_path)
        configuration = _configuration()
        fingerprints = _fingerprints(configuration)
        intent, seeded = _seed(writer, remote, fingerprints, set(fingerprints) | {_RETIRED})
        moved = []

        def purge(_zone_id, hostnames, _api_token):
            purges.append(tuple(hostnames))
            current = store.read_purge_state(str(writer), str(remote), REF, DOCUMENT)
            moved.append(store.write_purge_state(
                str(writer), str(remote), REF, DOCUMENT, current.revision, current.state,
            ))
            return cache_purge.PurgeAcceptance("req-1")

        purges = []
        _install(monkeypatch, purge=purge)
        with pytest.raises(store.PurgeStateConflict, match="^purge state ref is not the expected revision$") as caught:
            _run(writer, remote, configuration, intent)

        saved = store.read_purge_state(str(writer), str(remote), REF, DOCUMENT)
        assert purges == [("addons.example", "www.example")]
        assert moved == [saved.revision]
        assert saved.state == seeded.state
        assert _TOKEN not in _visible(caught.value)
        assert "secret-remote-token" not in _visible(caught.value)
        assert str(remote) not in _visible(caught.value)

    def test_missing_state_is_not_initialized(self, monkeypatch, tmp_path):
        """Confirmed absence is an error and does not create purge state."""
        _reader, writer, remote = _layout(tmp_path)
        configuration = _configuration()
        intent = cache_purge.DeploymentIntent("run-1.1", _IMAGE_B, _fingerprints(configuration))
        polls, purges = _install(monkeypatch)

        with pytest.raises(ValueError, match="^purge state is required$"):
            _run(writer, remote, configuration, intent)

        assert _remote_revision(remote) is None
        assert polls == []
        assert purges == []

    def test_corrupt_state_and_bad_credentials_are_not_purged(self, monkeypatch, tmp_path):
        """An unusable document or token fails before AWS and Cloudflare."""
        _reader, writer, remote = _layout(tmp_path)
        configuration = _configuration()
        fingerprints = _fingerprints(configuration)
        intent = cache_purge.DeploymentIntent("run-1.1", _IMAGE_B, fingerprints)
        polls, purges = _install(monkeypatch)
        _publish(writer, remote, {DOCUMENT: f'{{"token":"{_TOKEN}"}}'.encode()})

        with pytest.raises(store.PurgeStateStoreError, match="^purge state document is invalid$") as caught:
            _run(writer, remote, configuration, intent)

        assert _TOKEN not in _visible(caught.value)
        assert polls == []
        assert purges == []

        credentials = {"example": "example-zone-token", "example_updates": f"{_TOKEN} "}
        with pytest.raises(ValueError, match="^api_token is required$") as credential_error:
            _run(writer, remote, configuration, intent, credentials=credentials)

        assert _TOKEN not in _visible(credential_error.value)
        assert polls == []
        assert purges == []
