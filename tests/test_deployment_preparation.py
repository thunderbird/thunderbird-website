"""Configured pre-deployment purge preparation through real files and Git."""

import traceback
from pathlib import Path

import pytest

import cache_purge
import deployment_content
import deployment_purge
import purge_state_store as store
from test_deployment_content import _write
from test_purge_state_store import (
    DOCUMENT,
    REF,
    _IMAGE_B,
    _IMAGE_C,
    _git,
    _layout,
    _read,
    _remote_revision,
    _workspace,
    _write as _write_state,
)


_EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "examples" / "cache-purge.example.json"
_FILES = {
    "www.example/index.html": b"home\r\n",
    "www.example/en-US/maintenance/index.html": b"down",
    "wsgi.py": b"redirect-a",
    "notes/private.txt": b"secret",
}
_TOKENS = {
    "example": "example-zone-token",
    "example_updates": "updates-zone-token",
}


def _example():
    """Load the checked-in non-production example."""
    return cache_purge.load_purge_config(_EXAMPLE.read_text(encoding="utf-8"))


def _artifact(root):
    """Write the example sites into one completed directory."""
    return _write(root, _FILES)


def _prepare(workspace, remote, root, config, identity, credentials=None, image=_IMAGE_B):
    """Prepare one intent against the fixture ref."""
    return deployment_purge.prepare_deployment_intent(
        config,
        root,
        _TOKENS if credentials is None else credentials,
        str(workspace),
        str(remote),
        REF,
        DOCUMENT,
        identity,
        image,
    )


def _rendered(error):
    """Return the diagnostics a caller can see for one exception."""
    return "\n".join([
        str(error),
        repr(error),
        repr(error.args),
        "".join(traceback.format_exception(error)),
    ])


def _forbid_publication(monkeypatch):
    """Fail the test if preparation reaches a state write."""
    def fail_publish(*_args, **_kwargs):
        raise AssertionError("state was published")

    monkeypatch.setattr(deployment_purge, "write_purge_state", fail_publish)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Preparation must not validate credentials by contacting Cloudflare."""
    def explode(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr(cache_purge.http.client, "HTTPSConnection", explode)


class TestPrepareDeploymentIntent:
    """Credentials, the artifact snapshot, and configured fingerprints become one intent."""

    def test_example_configuration_loads(self):
        """The example file is valid, has no tokens, and is not production configuration."""
        document = _EXAMPLE.read_text(encoding="utf-8")
        config = cache_purge.load_purge_config(document)
        paths = {path: names for path, names in config.rules}

        assert "token" not in document
        assert paths["www.example/"] == ("www.example",)
        assert paths["www.example/en-US/maintenance/"] == ("addons.example",)
        assert paths["wsgi.py"] == ("www.example", "updates.example")
        assert set(config.hostnames) == {"www.example", "addons.example", "updates.example"}
        assert set(config.zones) == {"example", "example_updates"}

    def test_preparation_persists_configured_fingerprints(self, tmp_path):
        """The artifact snapshot is fingerprinted for every configured hostname and read back."""
        reader, writer, remote = _layout(tmp_path)
        root = _artifact(tmp_path / "artifact")
        config = _example()
        expected = cache_purge.content_fingerprints(
            deployment_content.read_content_snapshot(root), config.rules)

        result = _prepare(writer, remote, root, config, "intent-prepare")
        stored = _read(reader, remote)
        persisted = _git(remote, "cat-file", "blob", f"{result.revision}:{DOCUMENT}").stdout.decode()
        message = _git(remote, "log", "-1", "--format=%B", result.revision).stdout.decode()
        visible = "\n".join([
            persisted,
            message,
            cache_purge.encode_purge_state(result.state),
            str(result),
            repr(result),
        ])

        assert isinstance(result, store.PurgeStateSnapshot)
        assert stored == result
        assert result.state.intent.identity == "intent-prepare"
        assert result.state.intent.image == _IMAGE_B
        assert result.state.intent.fingerprints == expected
        assert set(result.state.intent.fingerprints) == set(config.hostnames)
        assert result.state.pending == frozenset(config.hostnames)
        for token in _TOKENS.values():
            assert token not in visible

    def test_missing_credentials_fail_before_publication_when_content_matches(self, tmp_path, monkeypatch):
        """A zone with no token is rejected even when accepted fingerprints already match."""
        _reader, writer, remote = _layout(tmp_path)
        root = _artifact(tmp_path / "artifact")
        config = _example()
        original = deployment_purge.write_purge_state
        _forbid_publication(monkeypatch)
        with pytest.raises(ValueError, match="api_token is required") as missing:
            _prepare(writer, remote, root, config, "intent-missing", credentials={"example": _TOKENS["example"]})
        assert "example-zone-token" not in _rendered(missing.value)
        assert _remote_revision(remote) is None
        monkeypatch.setattr(deployment_purge, "write_purge_state", original)

        published = _prepare(writer, remote, root, config, "intent-a")
        accepted = cache_purge.record_intent_acceptance(
            published.state, "intent-a", dict(published.state.intent.fingerprints))
        revision = _write_state(writer, remote, published.revision, accepted)
        _forbid_publication(monkeypatch)
        with pytest.raises(ValueError, match="api_token is required") as matched:
            _prepare(writer, remote, root, config, "intent-b", credentials={"example": _TOKENS["example"]})

        assert _remote_revision(remote) == revision
        assert _read(writer, remote).state == accepted
        assert "updates-zone-token" not in _rendered(matched.value)

    @pytest.mark.parametrize("token", ["secret token", "secret-token-\u20ac"])
    def test_malformed_tokens_fail_before_publication(self, tmp_path, monkeypatch, token):
        """A token purge_hostnames would refuse does not publish or appear in the error."""
        _reader, writer, remote = _layout(tmp_path)
        root = _artifact(tmp_path / "artifact")
        _forbid_publication(monkeypatch)

        with pytest.raises(ValueError, match="api_token is required") as caught:
            _prepare(writer, remote, root, _example(), "intent-bad", credentials={
                "example": _TOKENS["example"],
                "example_updates": token,
            })

        assert token not in _rendered(caught.value)
        assert _remote_revision(remote) is None

    def test_snapshot_failure_prevents_publication(self, tmp_path, monkeypatch):
        """An unreadable artifact fails before the intent is written."""
        _reader, writer, remote = _layout(tmp_path)
        _forbid_publication(monkeypatch)

        with pytest.raises(deployment_content.ContentSnapshotError):
            _prepare(writer, remote, tmp_path / "missing", _example(), "intent-snapshot")

        assert _remote_revision(remote) is None

    def test_revision_conflict_propagates_without_replay(self, monkeypatch, tmp_path):
        """Another writer who wins after the read is preserved, without registering again."""
        reader, writer, remote = _layout(tmp_path)
        other = tmp_path / "secret-remote-token" / "other"
        _workspace(other)
        root = _artifact(tmp_path / "artifact")
        config = _example()
        base = _prepare(writer, remote, root, config, "intent-base")
        winner = cache_purge.begin_deployment_intent(
            base.state, "intent-winner", _IMAGE_C, dict(base.state.intent.fingerprints))
        calls = []
        original = deployment_purge.write_purge_state

        def publish_winner(workspace, remote_url, ref, path, expected_revision, state, timeout=30):
            calls.append((expected_revision, state.intent.identity))
            if len(calls) == 1:
                original(str(other), str(remote), ref, path, expected_revision, winner, timeout)
            return original(workspace, remote_url, ref, path, expected_revision, state, timeout)

        monkeypatch.setattr(deployment_purge, "write_purge_state", publish_winner)
        with pytest.raises(store.PurgeStateConflict) as caught:
            _prepare(writer, remote, root, config, "intent-loser")

        snapshot = _read(reader, remote)
        assert calls == [(base.revision, "intent-loser")]
        assert snapshot.state == winner
        assert snapshot.state.intent.identity == "intent-winner"
        for token in _TOKENS.values():
            assert token not in _rendered(caught.value)
            assert token not in cache_purge.encode_purge_state(snapshot.state)
