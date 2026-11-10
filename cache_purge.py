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
hostname. ``pending_hostnames`` and ``record_accepted_purges`` track
outstanding purge work from caller-supplied fingerprints. They do not read
Git, Cloudflare, or deployment state.
"""

import hashlib
import json
import math
import time
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import NamedTuple, TypeVar

import http.client


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
    ``{"hosts": [...]}`` only. ``zone_id`` must be 1 to 32 ASCII letters or
    digits. ``api_token`` must be non-empty printable ASCII without spaces.
    Invalid input raises ValueError before a header is built, and that error
    does not include the token.

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
        if not isinstance(hostname, str) or hostname == "" or hostname.strip() != hostname:
            raise ValueError("hostnames must be a collection of hostname strings")
        if any(character.isspace() for character in hostname):
            raise ValueError("hostnames must be a collection of hostname strings")
        cleaned.append(hostname)
    return sorted(set(cleaned))


def _validate_request(zone_id, api_token):
    """Reject a zone id or token that must not be sent."""
    if (
        not isinstance(zone_id, str)
        or not zone_id.isascii()
        or not zone_id.isalnum()
        or len(zone_id) > 32
    ):
        raise ValueError("zone_id must be 1 to 32 ASCII letters or digits")
    if not isinstance(api_token, str) or not _header_safe_token(api_token):
        raise ValueError("api_token is required")


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
