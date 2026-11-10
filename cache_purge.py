"""Select hostnames affected by generated-file changes, and purge one zone.

Paths in snapshots and rules are canonical repository-relative strings that
already use "/" separators, such as ``start.thunderbird.net/en-US/index.html``
or ``wsgi.py``. Callers normalize paths before passing them in. This module
does not rewrite separators, resolve ``.`` or ``..``, or interpret a path as a
filesystem location.

A rule path ending in "/" is a directory prefix. Any other rule path is an
exact file. Directory rules match only at a path boundary, so
``start.thunderbird.net/`` matches ``start.thunderbird.net/index.html`` and
does not match ``start.thunderbird.net-preview/index.html``. Every matching
rule contributes its hostnames. The function does not contain a production
hostname map.

``purge_hostnames`` posts those hostnames to the fixed Cloudflare cache API.
``content_fingerprints`` hashes the files those rules select for each declared
hostname. ``load_purge_config`` validates JSON rules and hostname-to-zone
bindings. It does not read credentials or contain a production hostname map.
``validate_api_token`` checks local credential syntax and does not contact
Cloudflare or prove authorization.
``pending_hostnames`` and ``record_accepted_purges`` track outstanding purge
work from caller-supplied fingerprints. ``begin_deployment_intent`` and
``record_intent_acceptance`` attach that work to one deployment intent. The
intent image must be a digest-pinned reference. ``encode_purge_state`` and
``decode_purge_state`` convert that state to versioned JSON. They do not read
Git, Cloudflare, or deployment state.
"""

import hashlib
import json
import math
import time
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from types import MappingProxyType
from typing import NamedTuple, TypeVar

import http.client

from deployment_readiness import digest_pinned


# Documented Cloudflare API: POST https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache
_API_HOST = "api.cloudflare.com"
_REQUEST_TIMEOUT_SECONDS = 10
_MAX_ATTEMPTS = 3
# Total time this client will sleep while retrying. A longer Retry-After fails.
_MAX_RETRY_WAIT_SECONDS = 5
_DEFAULT_RETRY_DELAY_SECONDS = 1
# Purge error 1134 is the documented rate limit. HTTP 429 is the API rate limit.
_RATE_LIMIT_ERROR_CODE = 1134
# Purge error 1092 means the request mixed purge fields. It is not retryable.
_INVALID_PURGE_ERROR_CODE = 1092
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
_AUTH_STATUSES = frozenset({401, 403})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def changed_hostnames(
    before: Mapping[str, bytes],
    after: Mapping[str, bytes],
    rules: Sequence[tuple[str, Sequence[str]]],
) -> set[str]:
    """Return the hostnames affected by paths that differ between snapshots.

    `before` and `after` map repository-relative paths to file bytes. A path
    counts as changed when its bytes differ, when it is only in `before`
    (deletion), or when it is only in `after` (addition). A rename is a
    deletion at the old path plus an addition at the new path.

    `rules` is a sequence of ``(path, hostnames)`` pairs. Identical snapshots,
    an empty rule list, and changed paths that match no rule produce an empty
    set. Hostnames are unique, in no particular order.
    """
    changed = {
        path for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    }
    affected = set()
    for rule_path, hostnames in rules:
        if any(_rule_matches(rule_path, path) for path in changed):
            affected.update(hostnames)
    return affected


def _rule_matches(rule_path, changed_path):
    """Return whether one changed path falls under one supplied rule."""
    if rule_path.endswith("/"):
        return changed_path.startswith(rule_path)
    return changed_path == rule_path


def content_fingerprints(
    snapshot: Mapping[str, bytes],
    rules: Sequence[tuple[str, Sequence[str]]],
) -> dict[str, str]:
    """Return a SHA-256 fingerprint for every hostname declared by ``rules``.

    ``snapshot`` and ``rules`` use the same paths and matching rules as
    ``changed_hostnames``. Every matching rule contributes its hostnames. A
    path is included once for a hostname even when several rules select it.

    Each fingerprint is the lowercase hex SHA-256 of that hostname's matched
    files, ordered by path. A file is framed as an 8-byte big-endian length of
    the UTF-8 path, the path, an 8-byte big-endian length of the file bytes,
    and those bytes. Lengths keep paths and arbitrary contents unambiguous.
    A hostname with no matched file contributes no records. Its fingerprint is
    SHA-256 of empty input, ``e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855``.
    Identical matched bytes share a fingerprint. The bytes are hashed as
    given, including timestamps and randomized CSS.

    The values do not depend on snapshot order, rule order, hostname order, or
    repeated assignments. The inputs are not modified.
    """
    matched = {}
    for _rule_path, hostnames in rules:
        for hostname in hostnames:
            matched.setdefault(hostname, set())
    for path in snapshot:
        for rule_path, hostnames in rules:
            if _rule_matches(rule_path, path):
                for hostname in hostnames:
                    matched[hostname].add(path)
    return {hostname: _content_fingerprint(snapshot, paths) for hostname, paths in matched.items()}


def _content_fingerprint(snapshot, paths):
    """Hash one hostname's matched files in path order."""
    digest = hashlib.sha256()
    for path in sorted(paths):
        path_bytes = path.encode("utf-8")
        content = snapshot[path]
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


class _JSONObject(list):
    """JSON object pairs, retained so duplicate keys stay visible."""


class PurgeConfiguration(NamedTuple):
    """Rules and the hostname-to-zone bindings loaded from JSON.

    ``rules`` is the ``(path, hostnames)`` sequence accepted by
    ``changed_hostnames`` and ``content_fingerprints``. ``hostnames`` maps
    each managed hostname to its zone name. ``zones`` maps that name to the
    Cloudflare zone id. Neither mapping can be modified.
    """

    rules: tuple[tuple[str, tuple[str, ...]], ...]
    hostnames: Mapping[str, str]
    zones: Mapping[str, str]


def load_purge_config(document: str) -> PurgeConfiguration:
    """Validate purge configuration JSON and return its rules and zone bindings.

    The hostname map is the only assignment of hostnames to zones. Rules name
    hostnames and do not repeat zone ids. A hostname is a lowercase ASCII DNS
    name of two or more labels, with no trailing dot; uppercase and a trailing
    dot are different spellings of the same host and are rejected. Zone names
    are internal aliases, not DNS names: a lowercase letter followed by
    lowercase letters, digits, underscores, or hyphens, matched exactly.
    Paths keep the exact-file and trailing-slash directory distinction. They
    are not normalized.

    ``version`` must be the integer 1. Boolean ``true`` is rejected. Duplicate
    keys, unknown fields, unsafe paths, and references to an undefined
    hostname or zone are rejected. Every managed hostname needs a zone binding
    and must appear in at least one rule. A rule may match no current files.
    An unused hostname is invalid.

    Tokens are not part of this document. Before a deployment can expose
    content, the caller must supply a credential for every managed zone. A
    missing credential must fail that run and must not drop the hostname.
    """
    parsed = _parse_config_json(document)
    root = _config_object(parsed, "configuration", ("version", "zones", "hostnames", "rules"))
    if type(root["version"]) is not int or root["version"] != 1:
        raise ValueError("version must be 1")
    zones = _load_zones(root["zones"])
    hostnames = _load_hostnames(root["hostnames"], zones)
    rules = _load_rules(root["rules"], hostnames)
    used = {hostname for _path, names in rules for hostname in names}
    if set(hostnames) - used:
        raise ValueError("hostname is not used by a rule")
    return PurgeConfiguration(rules, MappingProxyType(hostnames), MappingProxyType(zones))


def _parse_config_json(document):
    """Return decoded configuration pairs, without a parse error's document excerpt."""
    return _parse_json_document(document, "purge configuration")


def _parse_json_document(document, label):
    """Return decoded JSON pairs, without retaining a parse error's document excerpt."""
    if not isinstance(document, str):
        raise ValueError(f"{label} must be JSON text")
    try:
        return json.loads(document, object_pairs_hook=_JSONObject)
    except (json.JSONDecodeError, RecursionError, ValueError):
        raise ValueError("malformed JSON") from None


def _object_pairs(value, field):
    """Return the pairs in one JSON object, rejecting a non-object or a repeated key."""
    if not isinstance(value, _JSONObject):
        raise ValueError(f"{field} must be an object")
    mapping = {}
    for key, item in value:
        if key in mapping:
            raise ValueError(f"duplicate key in {field}")
        mapping[key] = item
    return mapping


def _config_object(value, field, allowed):
    """Return one JSON object, rejecting unknown fields and omissions."""
    mapping = _object_pairs(value, field)
    for key in mapping:
        if key not in allowed:
            raise ValueError(f"unknown field in {field}")
    for key in allowed:
        if key not in mapping:
            raise ValueError(f"missing {key} in {field}")
    return mapping


def _load_zones(value):
    """Return zone aliases mapped to validated Cloudflare zone ids."""
    zones = {}
    for name, spec in _object_pairs(value, "zones").items():
        if not _valid_zone_alias(name):
            raise ValueError("invalid zone name")
        zone = _config_object(spec, "zone", ("id",))
        if not _valid_zone_id(zone["id"]):
            raise ValueError("invalid zone id")
        zones[name] = zone["id"]
    return zones


def _load_hostnames(value, zones):
    """Return managed hostnames mapped to known zone names."""
    bindings = {}
    for hostname, zone_name in _object_pairs(value, "hostnames").items():
        if not _valid_hostname(hostname):
            raise ValueError("invalid hostname")
        if not isinstance(zone_name, str) or zone_name not in zones:
            raise ValueError("hostnames references an undefined zone")
        bindings[hostname] = zone_name
    return bindings


def _load_rules(value, hostnames):
    """Return rule pairs, preserving overlap and repeated hostname assignments."""
    if isinstance(value, _JSONObject) or not isinstance(value, list):
        raise ValueError("rules must be an array")
    rules = []
    for index, rule in enumerate(value):
        field = f"rules[{index}]"
        mapping = _config_object(rule, field, ("path", "hostnames"))
        if not _canonical_rule_path(mapping["path"]):
            raise ValueError(f"{field}.path is unsafe")
        names = mapping["hostnames"]
        if isinstance(names, _JSONObject) or not isinstance(names, list):
            raise ValueError(f"{field}.hostnames must be an array")
        cleaned = []
        for name in names:
            if not _valid_hostname(name):
                raise ValueError(f"{field}.hostnames is invalid")
            if name not in hostnames:
                raise ValueError(f"{field}.hostnames references an undefined hostname")
            cleaned.append(name)
        rules.append((mapping["path"], tuple(cleaned)))
    return tuple(rules)


def _canonical_rule_path(path):
    """Return whether a rule path is a canonical relative file or directory."""
    if not isinstance(path, str) or path == "" or not path.isprintable():
        return False
    if any(character.isspace() for character in path) or "\\" in path or path.startswith("/"):
        return False
    if len(path) >= 2 and path[1] == ":":
        return False
    parts = path.split("/")
    if path.endswith("/"):
        parts = parts[:-1]
    return bool(parts) and all(part not in ("", ".", "..") for part in parts)


def _valid_hostname(hostname):
    """Return whether ``hostname`` is one exact lowercase DNS name.

    The name is two or more labels joined by dots, at most 253 characters,
    with no trailing dot. Each label is 1 to 63 ASCII letters, digits, or
    hyphens and does not start or end with a hyphen. Uppercase is rejected, so
    ``Start.example`` is not a second key for ``start.example``. A trailing
    dot is rejected for the same reason. Schemes, ports, paths, wildcards,
    whitespace, and controls are not labels. ASCII punycode is accepted.
    """
    if not isinstance(hostname, str) or len(hostname) > 253 or "." not in hostname:
        return False
    return all(_valid_dns_label(label) for label in hostname.split("."))


def _valid_dns_label(label):
    """Return whether one DNS label has a legal lowercase LDH boundary."""
    if not 1 <= len(label) <= 63:
        return False
    if label.startswith("-") or label.endswith("-"):
        return False
    return all(character in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in label)


def _valid_zone_alias(name):
    """Return whether ``name`` is an internal zone alias, not a DNS hostname.

    An alias is 1 to 63 characters: a lowercase letter, then lowercase letters,
    digits, underscores, or hyphens. ``primary_zone`` is valid. Matching is
    exact, so uppercase is a different spelling and is rejected. Dots are
    rejected so an alias cannot be mistaken for a hostname.
    """
    if not isinstance(name, str) or not 1 <= len(name) <= 63:
        return False
    if name[0] not in "abcdefghijklmnopqrstuvwxyz":
        return False
    return all(character in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in name)


def _valid_zone_id(zone_id):
    """Return whether a zone id meets the Cloudflare purge request policy."""
    return (
        isinstance(zone_id, str)
        and zone_id.isascii()
        and zone_id.isalnum()
        and len(zone_id) <= 32
    )


class PurgeAcceptance(NamedTuple):
    """Cloudflare accepted a hostname purge.

    ``request_id`` is the ``result.id`` string when the response includes one.
    Acceptance means HTTP 200 and JSON ``success`` true. It does not mean any
    cached response was observed to be removed.
    """

    request_id: str | None


class PurgeError(Exception):
    """The purge was not accepted, or it failed before Cloudflare answered.

    The message may include an HTTP status and Cloudflare error codes. It does
    not include the API token, the Authorization header, or the response body.
    """


def purge_hostnames(
    zone_id: str,
    hostnames: Collection[str],
    api_token: str,
) -> PurgeAcceptance | None:
    """Purge one Cloudflare zone for an explicit collection of hostnames.

    ``hostnames`` is a collection of strings, not one hostname string. An empty
    collection returns None and does not check credentials or connect. Any
    other collection is deduplicated by exact string, sorted, and sent as
    ``{"hosts": [...]}`` only. Each hostname is a lowercase DNS name, as
    required by configuration. ``zone_id`` must be 1 to 32 ASCII letters or
    digits. ``api_token`` must pass ``validate_api_token``: non-empty printable
    ASCII without spaces. Invalid input raises ValueError before a header is
    built, and that error does not include the token or the hostname.

    A nonempty call is HTTPS POST
    ``/client/v4/zones/{zone_id}/purge_cache`` on ``api.cloudflare.com``,
    with ``Content-Type: application/json``, a bearer token, a 10 second
    timeout, and no redirect.

    Returns PurgeAcceptance for HTTP 200 and JSON ``success`` exactly true.
    That is API acceptance, not observed cache removal. A non-empty ``errors``
    list does not override ``success`` true. When present, ``errors`` must be
    a list and ``result`` must be null or an object. An included ``result.id``
    must be a string. A missing result, a null result, or an object with no
    id is still acceptance, with ``request_id`` None.

    Every other outcome raises PurgeError. The message may include the HTTP
    status and Cloudflare error codes. It does not include the token or the
    response body.

    At most 3 attempts. Retry connection failures, HTTP 429, 500, 502, 503,
    and 504, and Cloudflare error 1134. Do not retry HTTP 401 or 403, error
    1092, other client errors, redirects, or a response that is not accepted.
    With no Retry-After, wait 1 second. Honor a decimal delay or an HTTP date.
    If the next wait would pass 5 seconds in total, or Retry-After cannot be
    read, raise PurgeError and do not sleep a shorter time.
    """
    hosts = _validated_hostnames(hostnames)
    if not hosts:
        return None
    _validate_request(zone_id, api_token)
    body = json.dumps({"hosts": hosts}).encode("utf-8")
    waited = 0.0
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        outcome = _post_purge(zone_id, body, api_token)
        if outcome is None:
            if attempt == _MAX_ATTEMPTS:
                raise PurgeError(
                    "Cloudflare purge failed after "
                    f"{_MAX_ATTEMPTS} attempts because the connection failed"
                )
            waited += _sleep_before_retry(None, waited)
            continue
        status, headers, payload = outcome
        if status in _REDIRECT_STATUSES:
            raise PurgeError(
                f"Cloudflare purge failed because HTTP {status} was a redirect"
            )
        data = _json_object(payload)
        accepted = _acceptance(status, data)
        if accepted is not None:
            return accepted
        if not _retryable(status, data):
            raise PurgeError(_failure_message(status, data))
        if attempt == _MAX_ATTEMPTS:
            raise PurgeError(
                f"{_failure_message(status, data)} after {_MAX_ATTEMPTS} attempts"
            )
        waited += _sleep_before_retry(headers, waited)


def _validated_hostnames(hostnames):
    """Return sorted unique hostnames, or reject a value that is not a collection."""
    if isinstance(hostnames, (str, bytes, bytearray)) or not isinstance(hostnames, Collection):
        raise ValueError("hostnames must be a collection of hostname strings")
    cleaned = []
    for hostname in hostnames:
        if not _valid_hostname(hostname):
            raise ValueError("hostnames must be a collection of hostname strings")
        cleaned.append(hostname)
    return sorted(set(cleaned))


def validate_api_token(api_token):
    """Reject a credential that ``purge_hostnames`` would refuse to send.

    The token must be non-empty printable ASCII without spaces. This checks
    local syntax only. It does not prove Cloudflare authorization or zone
    access, and the error does not include the token.
    """
    if not isinstance(api_token, str) or not _header_safe_token(api_token):
        raise ValueError("api_token is required")


def _validate_request(zone_id, api_token):
    """Reject a zone id or token that must not be sent."""
    if not _valid_zone_id(zone_id):
        raise ValueError("zone_id must be 1 to 32 ASCII letters or digits")
    validate_api_token(api_token)


def _header_safe_token(api_token):
    """Return whether the token is non-empty printable ASCII without spaces.

    Printable ASCII is the policy for header values. Latin-1 can encode many
    non-ASCII characters, so rejection is not limited to encoding failures.
    """
    return (
        bool(api_token)
        and api_token.isascii()
        and api_token.isprintable()
        and not any(character.isspace() for character in api_token)
    )


def _post_purge(zone_id, body, api_token):
    """POST one purge. Return None when the connection fails.

    The failure is returned instead of raised so the exception cannot carry
    the request, its headers, or a response body.
    """
    connection = http.client.HTTPSConnection(_API_HOST, timeout=_REQUEST_TIMEOUT_SECONDS)
    try:
        connection.request(
            "POST",
            f"/client/v4/zones/{zone_id}/purge_cache",
            body=body,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        return response.status, response.getheaders(), response.read()
    except (OSError, http.client.HTTPException):
        return None
    finally:
        connection.close()


def _acceptance(status, data):
    """Return PurgeAcceptance for the documented success response."""
    if status != 200 or not isinstance(data, dict) or data.get("success") is not True:
        return None
    if "errors" in data and not isinstance(data["errors"], list):
        return None
    if "result" not in data or data["result"] is None:
        return PurgeAcceptance(None)
    result = data["result"]
    if not isinstance(result, dict):
        return None
    if "id" not in result:
        return PurgeAcceptance(None)
    if not isinstance(result["id"], str):
        return None
    return PurgeAcceptance(result["id"])


def _retryable(status, data):
    """Return whether this response is a documented transient failure."""
    if status in _AUTH_STATUSES:
        return False
    codes = _error_codes(data)
    if _INVALID_PURGE_ERROR_CODE in codes:
        return False
    if _RATE_LIMIT_ERROR_CODE in codes:
        return True
    return status in _RETRYABLE_STATUSES


def _sleep_before_retry(headers, waited):
    """Sleep for the next attempt, or fail when the wait is over the limit."""
    delay = _retry_delay(headers)
    if waited + delay > _MAX_RETRY_WAIT_SECONDS:
        instructed = headers is not None and _header(headers, "retry-after") is not None
        raise PurgeError(_retry_limit_message(delay, waited, instructed))
    time.sleep(delay)
    return delay


def _retry_limit_message(delay, waited, instructed):
    """Describe a wait that is over the limit, without shortening it."""
    limit = f"{_MAX_RETRY_WAIT_SECONDS:g}"
    if instructed:
        return (
            f"Retry stopped: Retry-After {delay:g}s after {waited:g}s "
            f"exceeds the {limit}s limit"
        )
    return f"Retry stopped after {waited:g}s because it would exceed the {limit}s limit"


def _retry_delay(headers):
    """Return the seconds to wait, without shortening an instructed delay."""
    if headers is None:
        return _DEFAULT_RETRY_DELAY_SECONDS
    instructed = _header(headers, "retry-after")
    if instructed is None:
        return _DEFAULT_RETRY_DELAY_SECONDS
    parsed = _parse_retry_after(instructed)
    if parsed is None:
        raise PurgeError("Cloudflare sent a Retry-After value that could not be honored")
    return parsed


def _parse_retry_after(value):
    """Parse Retry-After seconds or an HTTP date. Return None if it is unusable.

    Unicode digits pass ``str.isdigit`` but are not ASCII delays. A long ASCII
    digit string can also fail when converted to a finite number of seconds.
    Both are unusable values, not waits this client shortens.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.isascii() and text.isdigit():
        try:
            delay = float(int(text))
        except (OverflowError, ValueError):
            return None
        if not math.isfinite(delay):
            return None
        return delay
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        delay = (parsed - datetime.now(timezone.utc)).total_seconds()
    except (OverflowError, OSError, ValueError):
        return None
    if not math.isfinite(delay):
        return None
    if delay < 0:
        return 0.0
    return delay


def _failure_message(status, data):
    """Describe a rejected purge without copying the response body."""
    codes = _error_codes(data)
    if codes:
        listed = ", ".join(str(code) for code in codes)
        return f"Cloudflare did not accept the purge (HTTP {status}, error {listed})"
    if status == 200:
        return "Cloudflare returned HTTP 200 but the purge response was not accepted"
    return f"Cloudflare did not accept the purge (HTTP {status})"


def _error_codes(data):
    """Return integer Cloudflare error codes, ignoring a body that is not that shape."""
    if not isinstance(data, dict) or not isinstance(data.get("errors"), list):
        return []
    codes = []
    for item in data["errors"]:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        if isinstance(code, int) and not isinstance(code, bool):
            codes.append(code)
    return codes


def _json_object(payload):
    """Return a decoded JSON object, or None when the body is not one.

    A decoder RecursionError or an integer past Python's digit limit is the
    same outcome as malformed JSON: no object, and the caller reports
    PurgeError without the body.
    """
    try:
        data = json.loads(payload.decode("utf-8"))
    except (AttributeError, ValueError, OverflowError, RecursionError):
        return None
    if isinstance(data, dict):
        return data
    return None


def _header(headers, name):
    """Return the first header value for `name`, ignoring case."""
    for header_name, value in headers:
        if header_name.lower() == name:
            return value
    return None


_Fingerprint = TypeVar("_Fingerprint")


def pending_hostnames(
    managed: Mapping[str, _Fingerprint],
    purged: Mapping[str, _Fingerprint],
    pending: Collection[str],
) -> set[str]:
    """Return outstanding purge work after planning the current fingerprints.

    The result contains every hostname already in ``pending``. It also
    contains each managed hostname that is absent from ``purged``, or whose
    current fingerprint differs from the stored one. Planning does not remove
    work. Only ``record_accepted_purges`` clears a hostname.

    A pending hostname absent from ``managed`` stays in the result. That
    records the work. It does not authorize a purge request for that hostname.
    Choosing which pending hostnames may be sent is later orchestration.

    Membership in ``purged`` distinguishes a missing accepted record from a
    stored fingerprint. ``None`` and ``""`` are ordinary fingerprints when
    the hostname is present. Fingerprints are otherwise opaque and compared
    with equality. An empty ``purged`` and empty ``pending`` marks every
    managed hostname pending.
    """
    outstanding = set(pending)
    for hostname, fingerprint in managed.items():
        if hostname not in purged or purged[hostname] != fingerprint:
            outstanding.add(hostname)
    return outstanding


def record_accepted_purges(
    purged: Mapping[str, _Fingerprint],
    pending: Collection[str],
    accepted: Mapping[str, _Fingerprint],
) -> tuple[dict[str, _Fingerprint], set[str]]:
    """Record accepted purges without changing the supplied inputs.

    ``accepted`` maps hostnames whose purge was accepted to the fingerprint
    that was accepted. Those hostnames are removed from the returned pending
    set, and only their entries in the returned fingerprint map are updated.
    Hostnames that were not accepted stay pending. Recording the same accepted
    fingerprints again yields the same result.

    These functions do not persist state, confirm deployment readiness, or
    make a remote write atomic. The caller must store pending work before a
    deployment can expose content, and must confirm readiness and ownership
    before treating an acceptance as success.
    """
    updated = dict(purged)
    updated.update(accepted)
    remaining = set(pending)
    remaining.difference_update(accepted)
    return updated, remaining


class DeploymentIntent(NamedTuple):
    """The deployment that currently owns changes to purge state.

    ``identity`` is a caller-supplied unique id. ``image`` is that deployment's
    digest-pinned reference, the same form required for deployment readiness.
    ``fingerprints`` are the hostname fingerprints it intends to publish. A
    later intent replaces this one even when those values match.
    """

    identity: str
    image: str
    fingerprints: Mapping[str, _Fingerprint]


class PurgeState(NamedTuple):
    """Accepted fingerprints, outstanding hostnames, and the owning intent.

    ``pending`` retains hostnames that are no longer managed. Replacing
    ``intent`` does not remove them.
    """

    purged: Mapping[str, _Fingerprint]
    pending: frozenset[str]
    intent: DeploymentIntent | None


def begin_deployment_intent(
    state: PurgeState,
    identity: str,
    image: str,
    fingerprints: Mapping[str, _Fingerprint],
) -> PurgeState:
    """Plan purge work for one deployment and make that deployment the owner.

    Outstanding hostnames stay pending. ``pending_hostnames`` also adds each
    intended hostname that has no accepted fingerprint or a different one.
    The returned intent replaces the previous owner even when the image,
    fingerprints, and pending set are unchanged.

    ``image`` must be a digest-pinned reference. A mutable tag, a blank value,
    a malformed digest, and a non-string are rejected before any state is
    built. Repeating the same identity with the same image and fingerprints
    is idempotent. The same identity with a different digest or different
    fingerprints is rejected and does not change ownership. These functions
    do not remember identities older than the current one.

    Nothing is persisted. A storage adapter must condition its write on the
    exact revision it read. After a conflict it must not register this intent
    again onto newer state.
    """
    _required_text(identity, "deployment intent identity is required")
    if not digest_pinned(image):
        raise ValueError("deployment intent image must be a digest-pinned reference")
    intended = _mapping(fingerprints, "intended fingerprints must be a mapping")
    current = state.intent
    if current is not None and current.identity == identity:
        if current.image != image or dict(current.fingerprints) != intended:
            raise ValueError("deployment intent identity is already bound to different inputs")
    pending = pending_hostnames(intended, state.purged, state.pending)
    intent = DeploymentIntent(identity, image, MappingProxyType(intended))
    return PurgeState(MappingProxyType(dict(state.purged)), frozenset(pending), intent)


def record_intent_acceptance(
    state: PurgeState,
    identity: str,
    accepted: Mapping[str, _Fingerprint],
) -> PurgeState:
    """Record purges accepted for the current intent.

    ``identity`` must be that intent. Every accepted hostname must be one of
    its intended hostnames, and the fingerprint must be the one that intent
    published. ``record_accepted_purges`` then updates only those hostnames.
    A missing, mismatched, or older acceptance raises ``ValueError`` before
    any hostname is cleared.

    Repeating an acceptance that was already recorded yields the same state.
    This does not make the write atomic. After a storage conflict the adapter
    must not apply this acceptance, or an acceptance computed for an older
    intent, to the newer revision.
    """
    _required_text(identity, "deployment intent identity is required")
    current = state.intent
    if current is None:
        raise ValueError("there is no current deployment intent")
    if current.identity != identity:
        raise ValueError("acceptance does not belong to the current deployment intent")
    recorded = _mapping(accepted, "accepted purges must be a mapping")
    for hostname, fingerprint in recorded.items():
        if hostname not in current.fingerprints:
            raise ValueError("accepted hostname is outside the current intent")
        if current.fingerprints[hostname] != fingerprint:
            raise ValueError("accepted fingerprint does not match the current intent")
    purged, pending = record_accepted_purges(state.purged, state.pending, recorded)
    return PurgeState(MappingProxyType(purged), frozenset(pending), current)


def _required_text(value, message):
    """Reject a missing or non-string intent field."""
    if not isinstance(value, str) or value == "":
        raise ValueError(message)


def _mapping(value, message):
    """Return a copy of a fingerprint mapping."""
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Mapping):
        raise ValueError(message)
    return dict(value)


def encode_purge_state(state: PurgeState) -> str:
    """Encode purge state as deterministic version-1 JSON.

    The document has ``version``, ``purged``, ``pending``, and ``intent``.
    ``purged`` maps a hostname to its accepted SHA-256 fingerprint. A hostname
    with no accepted record is omitted; it is not stored as null or an empty
    string. ``pending`` lists every outstanding hostname, including ones the
    current intent does not manage, in lexicographic order. ``intent`` is
    null, or the current identity, digest-pinned image, and intended
    fingerprints. Object keys are sorted. Hostnames use the same lowercase
    DNS spelling as purge configuration. Fingerprints are 64 lowercase hex
    characters, not arbitrary in-memory values. An intended hostname whose
    accepted fingerprint is missing or different must be pending. Extra
    pending hostnames are kept, including ones whose fingerprints already
    match. This document has no revision field: the storage adapter can use
    the Git commit that contains it.

    Encoding does not write that commit, and it does not make a later write
    atomic. After a conflict the adapter must not replay a stale intent
    registration or a stale acceptance onto a newer revision.
    """
    if not isinstance(state, PurgeState):
        raise ValueError("purge state is required")
    purged = _persistent_fingerprints(state.purged, "purged")
    pending = _persistent_pending(state.pending)
    intent = _persistent_intent(state.intent)
    fingerprints = None if intent is None else intent["fingerprints"]
    _require_outstanding_purges(purged, pending, fingerprints)
    document = {"version": 1, "purged": purged, "pending": pending, "intent": intent}
    return json.dumps(document, sort_keys=True, separators=(",", ":"))


def decode_purge_state(document: str) -> PurgeState:
    """Decode version-1 purge-state JSON into read-only purge state.

    Malformed JSON, an unsupported version, duplicate keys, unknown or missing
    fields, unsupported fingerprints, and an intent whose required purge is
    not pending raise ``ValueError``. They are not an empty initial state,
    and the missing hostname is not added. A missing remote state ref is the
    adapter's condition; this function does not invent state when the
    document is absent or unusable. The returned mappings cannot be modified.
    Decoding does not contact Git or make a conditional write.
    """
    parsed = _parse_json_document(document, "purge state")
    root = _config_object(parsed, "state", _STATE_FIELDS)
    if type(root["version"]) is not int or root["version"] != 1:
        raise ValueError("version must be 1")
    purged = _persistent_fingerprints(root["purged"], "purged")
    pending = _persistent_pending(root["pending"])
    intent = _load_persistent_intent(root["intent"])
    fingerprints = None if intent is None else intent.fingerprints
    _require_outstanding_purges(purged, pending, fingerprints)
    return PurgeState(MappingProxyType(purged), frozenset(pending), intent)


_STATE_FIELDS = ("version", "purged", "pending", "intent")
_INTENT_FIELDS = ("identity", "image", "fingerprints")


def _persistent_intent(intent):
    """Return the JSON intent object, or null when the state has no owner."""
    if intent is None:
        return None
    if not isinstance(intent, DeploymentIntent):
        raise ValueError("intent must be an object")
    _required_text(intent.identity, "deployment intent identity is required")
    if not digest_pinned(intent.image):
        raise ValueError("deployment intent image must be a digest-pinned reference")
    return {
        "identity": intent.identity,
        "image": intent.image,
        "fingerprints": _persistent_fingerprints(intent.fingerprints, "fingerprints"),
    }


def _load_persistent_intent(value):
    """Return the current intent, or None when the document stores null."""
    if value is None:
        return None
    mapping = _config_object(value, "intent", _INTENT_FIELDS)
    _required_text(mapping["identity"], "deployment intent identity is required")
    if not digest_pinned(mapping["image"]):
        raise ValueError("deployment intent image must be a digest-pinned reference")
    fingerprints = _persistent_fingerprints(mapping["fingerprints"], "fingerprints")
    return DeploymentIntent(mapping["identity"], mapping["image"], MappingProxyType(fingerprints))


def _require_outstanding_purges(purged, pending, fingerprints):
    """Reject an intent that omits a hostname whose purge is still required.

    Each intended hostname must be pending when its accepted fingerprint is
    absent or different. The check does not add that hostname, remove a
    pending hostname whose fingerprints match, or drop pending hostnames
    outside the intent. No intent means there are no intended fingerprints.
    """
    if fingerprints is None:
        return
    outstanding = set(pending)
    for hostname, intended in fingerprints.items():
        if (hostname not in purged or purged[hostname] != intended) and hostname not in outstanding:
            raise ValueError("intended purge is not pending")


def _persistent_fingerprints(mapping, field):
    """Return a hostname-to-SHA-256 mapping, preserving absent keys by omission."""
    if isinstance(mapping, _JSONObject):
        pairs = _object_pairs(mapping, field)
    elif isinstance(mapping, (str, bytes, bytearray)) or not isinstance(mapping, Mapping):
        raise ValueError(f"{field} must be an object")
    else:
        pairs = mapping
    loaded = {}
    for hostname, fingerprint in pairs.items():
        if not _valid_hostname(hostname):
            raise ValueError(f"invalid hostname in {field}")
        if not _sha256_fingerprint(fingerprint):
            raise ValueError(f"unsupported fingerprint in {field}")
        loaded[hostname] = fingerprint
    return loaded


def _sha256_fingerprint(value):
    """Return whether ``value`` is a lowercase SHA-256 hex digest."""
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value)


def _persistent_pending(pending):
    """Return outstanding hostnames in lexicographic order, without collapsing duplicates."""
    if isinstance(pending, _JSONObject) or not isinstance(pending, (list, tuple, frozenset, set)):
        raise ValueError("pending must be an array")
    names = []
    seen = set()
    for hostname in pending:
        if not _valid_hostname(hostname):
            raise ValueError("invalid hostname in pending")
        if hostname in seen:
            raise ValueError("duplicate hostname in pending")
        seen.add(hostname)
        names.append(hostname)
    names.sort()
    return names
