import copy
import hashlib
import json
import traceback

import pytest

import cache_purge

START = "start.thunderbird.net"
ADDONS = "addons.thunderbird.net"
WWW = "www.thunderbird.net"
UPDATES = "updates.thunderbird.net"
TBPRO = "tb.pro"
WWW_TBPRO = "www.tb.pro"
ROADMAPS = "roadmaps.thunderbird.net"
ROADMAP = "roadmap.thunderbird.net"

START_RULES = [
    ("start.thunderbird.net/", [START]),
    ("start.thunderbird.net/en-US/maintenance/", [ADDONS]),
]
SHARED_FILE_RULES = [
    ("wsgi.py", [WWW, UPDATES, TBPRO, WWW_TBPRO, ROADMAPS, ROADMAP]),
]


def _pages(**paths):
    """Build a snapshot from path/text pairs."""
    return {path: text.encode() for path, text in paths.items()}


class TestChangedHostnames:
    def test_equal_snapshots_and_empty_snapshots_select_nothing(self):
        """Unchanged files, including two empty snapshots, affect no hostnames."""
        snapshot = _pages(**{"start.thunderbird.net/en-US/index.html": "same"})

        assert cache_purge.changed_hostnames(snapshot, dict(snapshot), START_RULES) == set()
        assert cache_purge.changed_hostnames({}, {}, START_RULES) == set()

    def test_changed_added_and_deleted_files_select_their_site(self):
        """Byte edits, new files, and removed files all select the mapped site."""
        before = _pages(**{
            "www.thunderbird.net/en-US/index.html": "old",
            "www.thunderbird.net/en-US/gone.html": "gone",
        })
        after = _pages(**{
            "www.thunderbird.net/en-US/index.html": "new",
            "www.thunderbird.net/en-US/added.html": "added",
        })
        rules = [("www.thunderbird.net/", [WWW])]

        assert cache_purge.changed_hostnames(before, after, rules) == {WWW}

    def test_empty_file_addition_and_deletion_select_the_site(self):
        """A zero-byte file counts when it appears or disappears."""
        path = "www.thunderbird.net/empty.txt"
        rules = [("www.thunderbird.net/", [WWW])]

        assert cache_purge.changed_hostnames({}, {path: b""}, rules) == {WWW}
        assert cache_purge.changed_hostnames({path: b""}, {}, rules) == {WWW}
        assert cache_purge.changed_hostnames({path: b""}, {path: b""}, rules) == set()

    def test_changes_in_several_directories_select_each_site(self):
        """Independent directory changes select every site those rules name."""
        before = _pages(**{
            "www.thunderbird.net/en-US/index.html": "www",
            "updates.thunderbird.net/en-US/index.html": "updates",
        })
        after = _pages(**{
            "www.thunderbird.net/en-US/index.html": "www changed",
            "updates.thunderbird.net/en-US/index.html": "updates changed",
        })
        rules = [
            ("www.thunderbird.net/", [WWW]),
            ("updates.thunderbird.net/", [UPDATES]),
        ]

        assert cache_purge.changed_hostnames(before, after, rules) == {WWW, UPDATES}

    def test_maintenance_change_selects_start_and_addons(self):
        """The maintenance prefix and the broader start prefix both contribute."""
        path = "start.thunderbird.net/en-US/maintenance/index.html"
        before = _pages(**{path: "down"})
        after = _pages(**{path: "still down"})

        assert cache_purge.changed_hostnames(before, after, START_RULES) == {START, ADDONS}

    def test_other_start_path_selects_start_only(self):
        """A start page outside en-US maintenance does not select addons."""
        path = "start.thunderbird.net/en-US/release/index.html"
        before = _pages(**{path: "release"})
        after = _pages(**{path: "release changed"})

        assert cache_purge.changed_hostnames(before, after, START_RULES) == {START}

    def test_other_locale_maintenance_selects_start_only(self):
        """Addons serves the en-US maintenance directory, not other locales."""
        path = "start.thunderbird.net/fr/maintenance/index.html"
        before = _pages(**{path: "maintenance"})
        after = _pages(**{path: "maintenance changed"})

        assert cache_purge.changed_hostnames(before, after, START_RULES) == {START}

    def test_exact_shared_file_selects_every_assigned_hostname(self):
        """An exact file rule contributes each hostname listed for that file."""
        before = _pages(**{"wsgi.py": "redirect-a"})
        after = _pages(**{"wsgi.py": "redirect-b"})

        assert cache_purge.changed_hostnames(before, after, SHARED_FILE_RULES) == {
            WWW, UPDATES, TBPRO, WWW_TBPRO, ROADMAPS, ROADMAP,
        }

    def test_rename_between_sites_selects_both_sites(self):
        """A rename is a deletion on the old site and an addition on the new site."""
        before = _pages(**{"www.thunderbird.net/en-US/moved.html": "page"})
        after = _pages(**{"updates.thunderbird.net/en-US/moved.html": "page"})
        rules = [
            ("www.thunderbird.net/", [WWW]),
            ("updates.thunderbird.net/", [UPDATES]),
        ]

        assert cache_purge.changed_hostnames(before, after, rules) == {WWW, UPDATES}

    def test_repeated_hostname_is_returned_once(self):
        """Several changed paths that share a hostname produce one result entry."""
        before = _pages(**{
            "www.thunderbird.net/en-US/one.html": "one",
            "www.thunderbird.net/en-US/two.html": "two",
        })
        after = _pages(**{
            "www.thunderbird.net/en-US/one.html": "one changed",
            "www.thunderbird.net/en-US/two.html": "two changed",
        })
        rules = [
            ("www.thunderbird.net/", [WWW]),
            ("www.thunderbird.net/en-US/", [WWW]),
        ]

        assert cache_purge.changed_hostnames(before, after, rules) == {WWW}

    def test_exact_file_and_directory_rules_respect_path_boundaries(self):
        """Similar names do not match an exact file or a directory prefix."""
        rules = [
            ("wsgi.py", [WWW]),
            ("start.thunderbird.net/", [START]),
            ("start.thunderbird.net/en-US/maintenance/", [ADDONS]),
        ]
        unchanged = "same"
        # These share a name with a rule but are not that file or inside that directory.
        non_matches = [
            "wsgi.py.bak",
            "includes/wsgi.py",
            "start.thunderbird.net-preview/index.html",
        ]
        before = _pages(**{path: unchanged for path in non_matches})
        after = _pages(**{path: "changed" for path in non_matches})

        assert cache_purge.changed_hostnames(before, after, rules) == set()

        # The parent directory matches; the maintenance directory stops at its slash.
        maintenance_lookalike = "start.thunderbird.net/en-US/maintenance-old/index.html"
        assert cache_purge.changed_hostnames(
            _pages(**{maintenance_lookalike: "old"}),
            _pages(**{maintenance_lookalike: "new"}),
            rules,
        ) == {START}

        exact = _pages(**{"wsgi.py": "old"})
        assert cache_purge.changed_hostnames(exact, _pages(**{"wsgi.py": "new"}), rules) == {WWW}

    def test_unmatched_paths_and_empty_rules_select_nothing(self):
        """Changes outside every rule, and any change with no rules, are ignored."""
        before = _pages(**{"notes/private.txt": "old"})
        after = _pages(**{"notes/private.txt": "new"})

        assert cache_purge.changed_hostnames(before, after, START_RULES) == set()
        assert cache_purge.changed_hostnames(before, after, []) == set()

    def test_timestamp_and_css_byte_changes_select_their_sites(self):
        """Feed timestamps and CSS bytes are ordinary content changes."""
        atom = "www.thunderbird.net/en-US/thunderbird/releases/atom.xml"
        css = "updates.thunderbird.net/media/css/whatsnew-140.css"
        before = _pages(**{
            atom: "<updated>2026-11-10T00:10:49+00:00</updated>",
            css: ".particle-star { opacity: calc(61/100); }",
        })
        after = _pages(**{
            atom: "<updated>2026-11-10T00:35:59+00:00</updated>",
            css: ".particle-star { opacity: calc(5/100); }",
        })
        rules = [
            ("www.thunderbird.net/", [WWW]),
            ("updates.thunderbird.net/", [UPDATES]),
        ]

        assert cache_purge.changed_hostnames(before, after, rules) == {WWW, UPDATES}


TOKEN = "fake-token-not-real"
ZONE = "abc123zone"
HOSTS = ["b.example", "a.example", "b.example"]


def _accepted(request_id="023e105f4ecef8ad9ca31a8372d0c353"):
    """Build the documented HTTP 200 success body."""
    body = {
        "errors": [],
        "messages": [],
        "result": None if request_id is None else {"id": request_id},
        "success": True,
    }
    if request_id is None:
        body.pop("result")
    return _response(200, body)


def _response(status, body, headers=None):
    """Build a fake HTTP response. `body` may be text, bytes, or a JSON value."""
    if isinstance(body, (dict, list)):
        payload = json.dumps(body).encode("utf-8")
    elif isinstance(body, bytes):
        payload = body
    else:
        payload = str(body).encode("utf-8")
    return _FakeResponse(status, payload, headers or [])


class _FakeResponse:
    def __init__(self, status, payload, headers):
        self.status = status
        self._payload = payload
        self._headers = headers

    def read(self):
        return self._payload

    def getheaders(self):
        return list(self._headers)


class _ScriptedCloudflare:
    """Replace HTTPSConnection with scripted responses and recorded requests."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.connections = []

    def install(self, monkeypatch):
        script = self

        class Connection:
            def __init__(self, host, timeout=None):
                self.host = host
                self.timeout = timeout
                self.calls = []
                script.connections.append(self)

            def request(self, method, path, body=None, headers=None):
                self.calls.append((method, path, body, dict(headers or {})))

            def getresponse(self):
                if not script.outcomes:
                    raise AssertionError("unexpected extra Cloudflare request")
                outcome = script.outcomes.pop(0)
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome

            def close(self):
                self.closed = True

        monkeypatch.setattr(cache_purge.http.client, "HTTPSConnection", Connection)
        return self


def _forbid_http(monkeypatch):
    """Fail the test if a purge opens a connection."""
    def refused(*args, **kwargs):
        raise AssertionError("purge made an HTTP request")

    monkeypatch.setattr(cache_purge.http.client, "HTTPSConnection", refused)


def _record_sleep(monkeypatch):
    delays = []

    def sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(cache_purge.time, "sleep", sleep)
    return delays


def _purge(monkeypatch, outcomes):
    script = _ScriptedCloudflare(outcomes)
    script.install(monkeypatch)
    return script


def _assert_body_hidden(error, payload):
    """The failure text cannot contain the response body."""
    rendered = "\n".join([
        str(error),
        repr(error),
        repr(error.args),
        repr(error.__cause__),
        repr(error.__context__),
        "".join(traceback.format_exception(error)),
    ])
    assert payload.decode() not in rendered


def _assert_token_hidden(error, token=TOKEN):
    """The failure text cannot contain the token or an authorization header."""
    rendered = "\n".join([
        str(error),
        repr(error),
        repr(error.args),
        repr(error.__dict__),
        repr(error.__cause__),
        repr(error.__context__),
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
    ])
    assert token not in rendered
    assert "Authorization" not in rendered
    assert "Bearer" not in rendered


class TestPurgeHostnames:
    def test_request_uses_the_documented_purge_call(self, monkeypatch):
        """The purge POST uses the fixed URL, bearer token, JSON body, and timeout."""
        script = _purge(monkeypatch, [_accepted()])
        delays = _record_sleep(monkeypatch)

        accepted = cache_purge.purge_hostnames(ZONE, HOSTS, TOKEN)

        assert accepted == cache_purge.PurgeAcceptance("023e105f4ecef8ad9ca31a8372d0c353")
        assert delays == []
        assert len(script.connections) == 1
        connection = script.connections[0]
        assert connection.host == "api.cloudflare.com"
        assert connection.timeout == 10
        assert connection.calls == [(
            "POST",
            f"/client/v4/zones/{ZONE}/purge_cache",
            b'{"hosts": ["a.example", "b.example"]}',
            {
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
        )]
        assert list(json.loads(connection.calls[0][2])) == ["hosts"]

    def test_duplicate_hostnames_are_sorted_and_empty_input_makes_no_request(self, monkeypatch):
        """Repeated hostnames are sent once, in order, and an empty collection does nothing."""
        _forbid_http(monkeypatch)

        assert cache_purge.purge_hostnames(ZONE, [], TOKEN) is None
        assert cache_purge.purge_hostnames(ZONE, (), None) is None
        assert cache_purge.purge_hostnames("bad/zone", set(), "") is None

    @pytest.mark.parametrize(("zone_id", "hostnames", "api_token"), [
        (ZONE, "www.example.com", TOKEN),
        (ZONE, b"www.example.com", TOKEN),
        (ZONE, ["www.example.com", ""], TOKEN),
        (ZONE, ["www.example.com", None], TOKEN),
        (ZONE, ["https://start.example/path"], TOKEN),
        (ZONE, ["start.example:443"], TOKEN),
        (ZONE, ["start.example/path"], TOKEN),
        (ZONE, ["*"], TOKEN),
        (ZONE, ["start.example\x00"], TOKEN),
        (ZONE, ["www.example.com"], ""),
        (ZONE, ["www.example.com"], None),
        (ZONE, ["www.example.com"], " token "),
        ("", ["www.example.com"], TOKEN),
        ("zone/id", ["www.example.com"], TOKEN),
        ("z" * 33, ["www.example.com"], TOKEN),
    ])
    def test_invalid_inputs_fail_before_http(self, monkeypatch, zone_id, hostnames, api_token):
        """A string, bad hostname, missing token, or unsafe zone never opens a connection."""
        _forbid_http(monkeypatch)

        with pytest.raises(ValueError) as caught:
            cache_purge.purge_hostnames(zone_id, hostnames, api_token)
        rendered = str(caught.value)
        for hostname in hostnames if isinstance(hostnames, list) else ():
            if hostname:
                assert hostname not in rendered

    @pytest.mark.parametrize("token", [
        pytest.param("ascii-prefix-" + "\u20ac", id="non-ascii"),
        pytest.param("ascii-prefix-\n", id="newline"),
        pytest.param("ascii-prefix-\x7f", id="delete"),
        pytest.param("ascii-prefix-\x00", id="null"),
    ])
    def test_unsupported_token_characters_fail_before_header_construction(self, monkeypatch, token):
        """Printable ASCII is required, and the token stays out of the ValueError."""
        _forbid_http(monkeypatch)

        with pytest.raises(ValueError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], token)
        rendered = "\n".join([
            str(caught.value),
            repr(caught.value),
            repr(caught.value.args),
            "".join(traceback.format_exception(caught.value)),
        ])
        assert token not in rendered
        assert "Bearer" not in rendered

    def test_success_without_a_request_id_is_still_acceptance(self, monkeypatch):
        """Omitted ids are acceptance, and a non-empty errors list does not override success true."""
        _purge(monkeypatch, [_accepted(None)])

        assert cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN) == cache_purge.PurgeAcceptance(None)

    @pytest.mark.parametrize(("body", "request_id"), [
        ({"success": True, "errors": [], "result": None}, None),
        ({"success": True, "errors": [], "result": {}}, None),
        ({"success": True, "errors": [{"code": 1000, "message": "ignored"}], "result": {"id": "abc"}}, "abc"),
    ])
    def test_documented_success_shapes_are_acceptance(self, monkeypatch, body, request_id):
        """A null result, a result without an id, and success true with errors are acceptance."""
        _purge(monkeypatch, [_response(200, body)])

        assert cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN) == cache_purge.PurgeAcceptance(request_id)

    @pytest.mark.parametrize("body", [
        {"errors": [{"code": 1000, "message": TOKEN}], "success": False, "result": None},
        {"errors": [], "success": "true", "result": {"id": "abc"}},
        {"errors": {}, "success": True, "result": {"id": "abc"}},
        {"success": True, "result": "abc"},
        ["not", "an", "object"],
        "not-json",
        {"success": True, "errors": [], "result": {"id": None}},
        {"success": True, "errors": [], "result": {"id": 15}},
        {"success": True, "errors": [], "result": {"id": True}},
        "1e309",
    ])
    def test_http_success_with_rejection_or_malformed_body_fails(self, monkeypatch, body):
        """HTTP 200 is accepted only when success is true and the body matches the schema."""
        delays = _record_sleep(monkeypatch)
        script = _purge(monkeypatch, [_response(200, body)])

        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert delays == []
        assert len(script.connections) == 1
        _assert_token_hidden(caught.value)

    @pytest.mark.parametrize("status", [401, 403, 400, 404])
    def test_permanent_http_failures_are_not_retried(self, monkeypatch, status):
        """Authentication, permission, and other client errors stop on the first response."""
        delays = _record_sleep(monkeypatch)
        body = {"errors": [{"code": 1000, "message": f"Bearer {TOKEN}"}], "success": False}
        script = _purge(monkeypatch, [_response(status, body, [("Retry-After", "1")])])

        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert delays == []
        assert len(script.connections) == 1
        _assert_token_hidden(caught.value)

    def test_invalid_purge_combination_is_not_retried(self, monkeypatch):
        """Cloudflare error 1092 is a permanent input rejection."""
        delays = _record_sleep(monkeypatch)
        body = {
            "errors": [{"code": 1092, "message": f"invalid and {TOKEN}"}],
            "success": False,
            "result": None,
        }
        script = _purge(monkeypatch, [_response(400, body)])

        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert delays == []
        assert len(script.connections) == 1
        assert "1092" in str(caught.value)
        _assert_token_hidden(caught.value)

    def test_rate_limit_then_success_retries_once(self, monkeypatch):
        """HTTP 429 and purge error 1134 wait for the instructed second, then succeed."""
        delays = _record_sleep(monkeypatch)
        limited = {
            "errors": [{"code": 1134, "message": "Unable to purge, rate limit reached."}],
            "success": False,
            "result": None,
        }
        script = _purge(monkeypatch, [
            _response(429, limited, [("Retry-After", "2")]),
            _accepted(),
        ])

        accepted = cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert accepted.request_id == "023e105f4ecef8ad9ca31a8372d0c353"
        assert delays == [2.0]
        assert len(script.connections) == 2

        delays = _record_sleep(monkeypatch)
        script = _purge(monkeypatch, [
            _response(400, limited, [("Retry-After", "1")]),
            _accepted(),
        ])
        cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)
        assert delays == [1.0]
        assert len(script.connections) == 2

    @pytest.mark.parametrize("failure", [
        TimeoutError("timed out"),
        _response(500, "unavailable"),
        _response(502, "bad gateway"),
        _response(503, "unavailable"),
        _response(504, "timeout"),
    ])
    def test_retryable_server_error_then_success(self, monkeypatch, failure):
        """A connection failure or retryable server status is followed by one more attempt."""
        delays = _record_sleep(monkeypatch)
        script = _purge(monkeypatch, [failure, _accepted()])

        accepted = cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert accepted.request_id == "023e105f4ecef8ad9ca31a8372d0c353"
        assert delays == [1.0]
        assert len(script.connections) == 2

    def test_retries_stop_after_three_attempts(self, monkeypatch):
        """Three connection failures sleep twice and then raise."""
        delays = _record_sleep(monkeypatch)
        script = _purge(monkeypatch, [
            TimeoutError("timed out"),
            OSError("reset"),
            TimeoutError("timed out"),
        ])

        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert delays == [1.0, 1.0]
        assert len(script.connections) == 3
        assert "3 attempts" in str(caught.value)

    def test_server_errors_stop_after_three_attempts(self, monkeypatch):
        """Three HTTP 503 responses use the same attempt limit."""
        delays = _record_sleep(monkeypatch)
        script = _purge(monkeypatch, [
            _response(503, "down"),
            _response(503, "down"),
            _response(503, "down"),
        ])

        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert delays == [1.0, 1.0]
        assert len(script.connections) == 3
        assert "503" in str(caught.value)
        assert "3 attempts" in str(caught.value)

    def test_retry_after_over_the_limit_is_not_shortened(self, monkeypatch):
        """A Retry-After longer than five seconds fails with no sleep."""
        delays = _record_sleep(monkeypatch)
        script = _purge(monkeypatch, [_response(429, {"success": False}, [("Retry-After", "6")])])

        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert delays == []
        assert len(script.connections) == 1
        assert "6" in str(caught.value)
        assert "5" in str(caught.value)

    def test_retry_after_of_five_seconds_is_honored(self, monkeypatch):
        """Five seconds is inside the wait limit and is slept in full."""
        delays = _record_sleep(monkeypatch)
        _purge(monkeypatch, [
            _response(503, "down", [("Retry-After", "5")]),
            _accepted(),
        ])

        cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert delays == [5.0]

    def test_cumulative_retry_after_over_the_limit_fails(self, monkeypatch):
        """A second instructed wait that would pass five seconds is not shortened."""
        delays = _record_sleep(monkeypatch)
        script = _purge(monkeypatch, [
            _response(429, {"success": False}, [("Retry-After", "3")]),
            _response(429, {"success": False}, [("Retry-After", "3")]),
            _accepted(),
        ])

        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert delays == [3.0]
        assert len(script.connections) == 2
        assert "3" in str(caught.value)
        assert "5" in str(caught.value)

    def test_unreadable_or_dated_retry_after(self, monkeypatch):
        """An unreadable Retry-After fails, and a past HTTP date retries immediately."""
        delays = _record_sleep(monkeypatch)
        script = _purge(monkeypatch, [
            _response(429, {"success": False}, [("Retry-After", f"Bearer {TOKEN}")]),
        ])
        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)
        assert delays == []
        assert len(script.connections) == 1
        _assert_token_hidden(caught.value)

        delays = _record_sleep(monkeypatch)
        _purge(monkeypatch, [
            _response(503, "down", [("Retry-After", "Wed, 01 Jan 2000 00:00:00 GMT")]),
            _accepted(),
        ])
        cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)
        assert delays == [0.0]

        delays = _record_sleep(monkeypatch)
        script = _purge(monkeypatch, [
            _response(503, "down", [("Retry-After", "Wed, 01 Jan 2099 00:00:00 GMT")]),
        ])
        with pytest.raises(cache_purge.PurgeError):
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)
        assert delays == []
        assert len(script.connections) == 1

    @pytest.mark.parametrize("header", ["9" * 400, "²"])
    def test_unconvertible_retry_after_is_a_sanitized_purge_error(self, monkeypatch, header):
        """A delay that cannot be converted fails once, with no shorter sleep."""
        delays = _record_sleep(monkeypatch)
        script = _purge(monkeypatch, [
            _response(429, {"success": False, "errors": [{"code": 1134}]}, [("Retry-After", header)]),
            _accepted(),
        ])

        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert delays == []
        assert len(script.connections) == 1
        assert header not in str(caught.value)
        assert header not in repr(caught.value)
        assert all(header not in str(arg) for arg in caught.value.args)

    def test_deeply_nested_json_is_a_sanitized_purge_error(self, monkeypatch):
        """A recursive JSON array becomes PurgeError without retry or the body."""
        nested = "0"
        for _ in range(2000):
            nested = f"[{nested}]"
        payload = ('{"success": false, "detail": ' + nested + "}").encode()
        delays = _record_sleep(monkeypatch)
        script = _purge(monkeypatch, [_response(200, payload), _accepted()])

        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert delays == []
        assert len(script.connections) == 1
        _assert_body_hidden(caught.value, payload)

    def test_oversized_json_integer_is_a_sanitized_purge_error(self, monkeypatch):
        """An integer past Python's conversion limit becomes PurgeError, not ValueError."""
        digits = "9" * 4301
        payload = ('{"success": false, "n": ' + digits + "}").encode()
        delays = _record_sleep(monkeypatch)
        script = _purge(monkeypatch, [_response(200, payload), _accepted()])

        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert delays == []
        assert len(script.connections) == 1
        _assert_body_hidden(caught.value, payload)

    def test_redirect_is_rejected_without_another_request(self, monkeypatch):
        """A redirect is a failure, and the bearer token is not sent to the new location."""
        delays = _record_sleep(monkeypatch)
        script = _purge(monkeypatch, [_response(
            302,
            {"errors": [{"message": TOKEN}], "success": False},
            [("Location", "https://evil.example/collect"), ("Retry-After", "1")],
        )])

        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)

        assert delays == []
        assert len(script.connections) == 1
        assert script.connections[0].host == "api.cloudflare.com"
        assert script.connections[0].calls[0][1] == f"/client/v4/zones/{ZONE}/purge_cache"
        assert "302" in str(caught.value)
        _assert_token_hidden(caught.value)

    def test_errors_do_not_disclose_the_token(self, monkeypatch):
        """A response or transport error that echoes the token stays out of the exception."""
        delays = _record_sleep(monkeypatch)
        body = {
            "errors": [{
                "code": 1000,
                "message": f"rejected Authorization: Bearer {TOKEN}",
            }],
            "success": False,
        }
        _purge(monkeypatch, [_response(403, body)])
        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)
        _assert_token_hidden(caught.value)
        assert delays == []

        echoed = OSError(f"connection failed Authorization: Bearer {TOKEN}")
        delays = _record_sleep(monkeypatch)
        _purge(monkeypatch, [echoed, echoed, echoed])
        with pytest.raises(cache_purge.PurgeError) as caught:
            cache_purge.purge_hostnames(ZONE, ["www.example.com"], TOKEN)
        _assert_token_hidden(caught.value)
        assert delays == [1.0, 1.0]


class TestPurgeRecovery:
    def test_failed_purge_stays_pending_when_content_reverts(self):
        """A is purged, B's purge fails, and C equal to A still needs a purge."""
        pending = cache_purge.pending_hostnames({"www": "A"}, {}, set())
        assert pending == {"www"}
        purged, pending = cache_purge.record_accepted_purges({}, pending, {"www": "A"})
        assert purged == {"www": "A"}
        assert pending == set()

        pending = cache_purge.pending_hostnames({"www": "B"}, purged, pending)
        assert pending == {"www"}
        selected = cache_purge.pending_hostnames({"www": "A"}, purged, pending)

        assert selected == {"www"}
        assert purged == {"www": "A"}

    def test_partial_failure_then_revert_selects_each_host_for_its_reason(self):
        """The host accepted at B changes again at A; the failed host is still pending."""
        purged = {"one": "A", "two": "A"}
        pending = cache_purge.pending_hostnames({"one": "B", "two": "B"}, purged, set())
        assert pending == {"one", "two"}
        purged, pending = cache_purge.record_accepted_purges(purged, pending, {"one": "B"})
        assert purged["one"] == "B"
        assert purged["two"] == "A"
        assert pending == {"two"}

        selected = cache_purge.pending_hostnames({"one": "A", "two": "A"}, purged, pending)

        assert selected == {"one", "two"}

    def test_unchanged_clean_content_has_no_pending_work(self):
        """A current fingerprint that matches the accepted purge is not pending."""
        assert cache_purge.pending_hostnames({"www": "A", "start": "S"}, {"www": "A", "start": "S"}, set()) == set()

    def test_new_hostnames_become_pending(self):
        """First use marks every managed hostname, and a later hostname is added."""
        assert cache_purge.pending_hostnames({"www": "A", "start": "S"}, {}, set()) == {"www", "start"}
        selected = cache_purge.pending_hostnames(
            {"www": "A", "start": "S"},
            {"www": "A"},
            set(),
        )
        assert selected == {"start"}

    def test_partial_acceptance_updates_only_accepted_hosts(self):
        """An accepted hostname is cleared and the other stays pending at its old fingerprint."""
        purged = {"one": "A", "two": "A"}
        pending = {"one", "two"}

        updated, remaining = cache_purge.record_accepted_purges(purged, pending, {"one": "B"})

        assert updated == {"one": "B", "two": "A"}
        assert remaining == {"two"}

    def test_repeated_planning_and_acceptance_are_idempotent(self):
        """Planning the same inputs twice, then recording the same acceptance twice, is stable."""
        managed = {"www": "B", "start": "S"}
        purged = {"www": "A", "start": "S"}
        pending = set()
        first = cache_purge.pending_hostnames(managed, purged, pending)
        second = cache_purge.pending_hostnames(managed, purged, first)
        assert first == second == {"www"}

        recorded, remaining = cache_purge.record_accepted_purges(purged, first, {"www": "B"})
        again_recorded, again_remaining = cache_purge.record_accepted_purges(recorded, remaining, {"www": "B"})

        assert again_recorded == recorded == {"www": "B", "start": "S"}
        assert again_remaining == remaining == set()
        assert cache_purge.pending_hostnames(managed, recorded, remaining) == set()

    def test_inputs_are_not_mutated(self):
        """Planning and acceptance return new collections and leave the inputs intact."""
        managed = {"www": "B"}
        purged = {"www": "A"}
        pending = {"www"}
        accepted = {"www": "B"}
        managed_before = dict(managed)
        purged_before = dict(purged)
        pending_before = set(pending)
        accepted_before = dict(accepted)

        selected = cache_purge.pending_hostnames(managed, purged, pending)
        updated, remaining = cache_purge.record_accepted_purges(purged, pending, accepted)

        assert managed == managed_before
        assert purged == purged_before
        assert pending == pending_before
        assert accepted == accepted_before
        assert selected == {"www"}
        assert updated == {"www": "B"}
        assert remaining == set()
        assert updated is not purged
        assert remaining is not pending

    def test_empty_managed_mapping_retains_pending_work(self):
        """Storing the plan while nothing is managed does not drop outstanding work."""
        purged = {"www": "A"}
        pending = {"www"}

        assert cache_purge.pending_hostnames({}, purged, pending) == {"www"}
        assert purged == {"www": "A"}
        assert pending == {"www"}

    def test_pending_host_remains_pending_while_unmanaged_and_after_it_returns(self):
        """B stays pending when the hostname leaves and later comes back at A."""
        purged, pending = cache_purge.record_accepted_purges({}, {"www"}, {"www": "A"})
        pending = cache_purge.pending_hostnames({"www": "B"}, purged, pending)
        assert pending == {"www"}

        while_absent = cache_purge.pending_hostnames({}, purged, pending)
        assert while_absent == {"www"}
        returned = cache_purge.pending_hostnames({"www": "A"}, purged, while_absent)

        assert returned == {"www"}
        assert purged == {"www": "A"}

    def test_pending_unmanaged_hosts_coexist_with_changed_managed_hosts(self):
        """Outstanding work for an unmanaged hostname stays beside a new managed change."""
        managed = {"start": "new"}
        purged = {"start": "old", "gone": "A"}
        pending = {"gone"}

        selected = cache_purge.pending_hostnames(managed, purged, pending)

        assert selected == {"gone", "start"}
        assert managed == {"start": "new"}
        assert purged == {"start": "old", "gone": "A"}
        assert pending == {"gone"}

    def test_missing_purge_record_differs_from_none_and_empty_string(self):
        """A hostname absent from the purge map is pending even when the fingerprint is empty."""
        assert cache_purge.pending_hostnames({"www": None}, {}, set()) == {"www"}
        assert cache_purge.pending_hostnames({"www": ""}, {}, set()) == {"www"}
        assert cache_purge.pending_hostnames({"www": None}, {"www": None}, set()) == set()
        assert cache_purge.pending_hostnames({"www": ""}, {"www": ""}, set()) == set()
        assert cache_purge.pending_hostnames({"www": "A"}, {"www": None}, set()) == {"www"}
        assert cache_purge.pending_hostnames({"www": "A"}, {"www": ""}, set()) == {"www"}


_EMPTY_FINGERPRINT = hashlib.sha256(b"").hexdigest()


def _fingerprint_changes(before, after, rules):
    """Return hostnames whose fingerprints differ between two snapshots."""
    before_fingerprints = cache_purge.content_fingerprints(before, rules)
    after_fingerprints = cache_purge.content_fingerprints(after, rules)
    return {
        hostname for hostname, fingerprint in before_fingerprints.items()
        if after_fingerprints[hostname] != fingerprint
    }


class TestContentFingerprints:
    """Fingerprints hash the bytes selected by the changed-hostname rules."""

    def test_reordered_snapshots_and_rules_have_the_same_fingerprints(self):
        """Snapshot order, rule order, and hostname order do not change a fingerprint."""
        first = {
            "start.thunderbird.net/en-US/index.html": b"page",
            "start.thunderbird.net/en-US/maintenance/index.html": b"down",
        }
        second = {
            "start.thunderbird.net/en-US/maintenance/index.html": b"down",
            "start.thunderbird.net/en-US/index.html": b"page",
        }
        forward = [
            ("start.thunderbird.net/", [START, ADDONS]),
            ("start.thunderbird.net/en-US/maintenance/", [ADDONS, START]),
        ]
        reverse = [
            ("start.thunderbird.net/en-US/maintenance/", [START, ADDONS]),
            ("start.thunderbird.net/", [ADDONS, START]),
        ]

        assert cache_purge.content_fingerprints(first, forward) == cache_purge.content_fingerprints(second, reverse)

    def test_overlapping_start_and_maintenance_dependencies(self):
        """Maintenance content is in both fingerprints, and other start content is not."""
        maintenance = "start.thunderbird.net/en-US/maintenance/index.html"
        other = "start.thunderbird.net/en-US/index.html"
        snapshot = {maintenance: b"down", other: b"page"}

        fingerprints = cache_purge.content_fingerprints(snapshot, START_RULES)
        addons_only = cache_purge.content_fingerprints(
            {maintenance: b"down"},
            [("start.thunderbird.net/en-US/maintenance/", [ADDONS])],
        )

        assert set(fingerprints) == {START, ADDONS}
        assert fingerprints[ADDONS] == addons_only[ADDONS]
        assert fingerprints[START] != fingerprints[ADDONS]

    def test_duplicate_rules_do_not_change_fingerprints(self):
        """A path selected by several rules is hashed once for that hostname."""
        path = "www.thunderbird.net/en-US/index.html"
        snapshot = {path: b"page"}
        once = [("www.thunderbird.net/", [WWW])]
        twice = [
            ("www.thunderbird.net/", [WWW, WWW]),
            ("www.thunderbird.net/en-US/", [WWW]),
        ]

        assert cache_purge.content_fingerprints(snapshot, once) == cache_purge.content_fingerprints(snapshot, twice)

    def test_shared_exact_file_is_in_every_assigned_fingerprint(self):
        """One exact file contributes the same content fingerprint to every assigned hostname."""
        fingerprints = cache_purge.content_fingerprints({"wsgi.py": b"application"}, SHARED_FILE_RULES)

        assert set(fingerprints) == {WWW, UPDATES, TBPRO, WWW_TBPRO, ROADMAPS, ROADMAP}
        assert len(set(fingerprints.values())) == 1
        assert fingerprints[WWW] != _EMPTY_FINGERPRINT

    def test_added_deleted_renamed_and_empty_files_change_fingerprints(self):
        """Path identity is part of the fingerprint, including a zero-byte file."""
        rules = [("www.thunderbird.net/", [WWW])]
        original = {"www.thunderbird.net/old.html": b"page"}
        added = {"www.thunderbird.net/old.html": b"page", "www.thunderbird.net/new.html": b"more"}
        deleted = {}
        renamed = {"www.thunderbird.net/new.html": b"page"}
        empty = {"www.thunderbird.net/empty.txt": b""}

        original_fingerprint = cache_purge.content_fingerprints(original, rules)[WWW]
        assert cache_purge.content_fingerprints(added, rules)[WWW] != original_fingerprint
        assert cache_purge.content_fingerprints(deleted, rules)[WWW] == _EMPTY_FINGERPRINT
        assert cache_purge.content_fingerprints(renamed, rules)[WWW] != original_fingerprint
        assert cache_purge.content_fingerprints(empty, rules)[WWW] != _EMPTY_FINGERPRINT

    def test_binary_content_uses_length_prefixed_framing(self):
        """Adjacent path and content boundaries stay distinct for arbitrary bytes."""
        path = "a"
        content = b"b\x00c"
        path_bytes = path.encode("utf-8")
        framed = b"".join((
            len(path_bytes).to_bytes(8, "big"),
            path_bytes,
            len(content).to_bytes(8, "big"),
            content,
        ))
        fingerprints = cache_purge.content_fingerprints({path: content}, [("a", [WWW])])

        assert fingerprints[WWW] == hashlib.sha256(framed).hexdigest()
        assert fingerprints[WWW] != cache_purge.content_fingerprints({"ab": b"\x00c"}, [("ab", [WWW])])[WWW]
        assert fingerprints[WWW] != cache_purge.content_fingerprints({"a": b"b"}, [("a", [WWW])])[WWW]

    def test_declared_hostname_with_no_match_has_the_empty_fingerprint(self):
        """Every hostname named by a rule is present when none of its files are."""
        fingerprints = cache_purge.content_fingerprints({}, START_RULES)

        assert fingerprints == {START: _EMPTY_FINGERPRINT, ADDONS: _EMPTY_FINGERPRINT}

    def test_unmatched_files_do_not_change_fingerprints(self):
        """Bytes outside every rule leave the declared fingerprints untouched."""
        unmatched = "notes/private.txt"
        before = {unmatched: b"old\x00"}
        after = {unmatched: b"new", "wsgi.py.bak": b"application"}

        assert cache_purge.content_fingerprints(before, START_RULES) == {START: _EMPTY_FINGERPRINT, ADDONS: _EMPTY_FINGERPRINT}
        assert cache_purge.content_fingerprints(after, START_RULES) == cache_purge.content_fingerprints(before, START_RULES)

    def test_inputs_are_not_mutated(self):
        """Fingerprinting reads the snapshot and rules."""
        snapshot = {"wsgi.py": b"application", "notes/private.txt": b"secret"}
        rules = [("wsgi.py", [WWW, UPDATES]), ("start.thunderbird.net/", [START])]
        original_snapshot = copy.deepcopy(snapshot)
        original_rules = copy.deepcopy(rules)

        cache_purge.content_fingerprints(snapshot, rules)

        assert snapshot == original_snapshot
        assert rules == original_rules

    @pytest.mark.parametrize("before,after,rules", [
        (
            {"start.thunderbird.net/en-US/maintenance/index.html": b"down"},
            {"start.thunderbird.net/en-US/maintenance/index.html": b"still down"},
            START_RULES,
        ),
        (
            {"start.thunderbird.net/en-US/index.html": b"page"},
            {"start.thunderbird.net/en-US/index.html": b"page changed"},
            START_RULES,
        ),
        (
            {"wsgi.py": b"redirect-a"},
            {"wsgi.py": b"redirect-b"},
            SHARED_FILE_RULES,
        ),
        (
            {"www.thunderbird.net/old.html": b"page"},
            {"www.thunderbird.net/new.html": b"page"},
            [("www.thunderbird.net/", [WWW])],
        ),
        (
            {},
            {"www.thunderbird.net/empty.txt": b""},
            [("www.thunderbird.net/", [WWW])],
        ),
        (
            {"www.thunderbird.net/en-US/thunderbird/releases/atom.xml": b"<updated>2026-11-10T00:10:49+00:00</updated>"},
            {"www.thunderbird.net/en-US/thunderbird/releases/atom.xml": b"<updated>2026-11-10T00:35:59+00:00</updated>"},
            [("www.thunderbird.net/", [WWW])],
        ),
        (
            {"notes/private.txt": b"old"},
            {"notes/private.txt": b"new"},
            START_RULES,
        ),
    ])
    def test_changed_fingerprint_keys_match_changed_hostnames(self, before, after, rules):
        """Hostnames with a new fingerprint are the hostnames changed_hostnames returns."""
        assert _fingerprint_changes(before, after, rules) == cache_purge.changed_hostnames(before, after, rules)


# Reserved example names and a fake zone id. This is not production configuration.
_ZONE_ID = "0123456789abcdef0123456789abcdef"
_EXAMPLE_CONFIG = {
    "version": 1,
    "zones": {"example": {"id": _ZONE_ID}},
    "hostnames": {
        "start.example": "example",
        "addons.example": "example",
    },
    "rules": [
        {"path": "start.example/", "hostnames": ["start.example"]},
        {"path": "start.example/en-US/maintenance/", "hostnames": ["addons.example"]},
    ],
}


def _config_text(config=None):
    """Serialize a configuration document."""
    return json.dumps(_EXAMPLE_CONFIG if config is None else config)


class TestLoadPurgeConfig:
    """JSON configuration supplies rules and the hostname-to-zone bindings."""

    def test_valid_document_exposes_rules_bindings_and_zone_ids(self):
        """A rule can name a hostname whose files are not in the current snapshot."""
        config = cache_purge.load_purge_config(_config_text())

        assert config.rules == (
            ("start.example/", ("start.example",)),
            ("start.example/en-US/maintenance/", ("addons.example",)),
        )
        assert config.hostnames == {"start.example": "example", "addons.example": "example"}
        assert config.zones == {"example": _ZONE_ID}
        assert cache_purge.content_fingerprints({}, config.rules) == {
            "start.example": _EMPTY_FINGERPRINT,
            "addons.example": _EMPTY_FINGERPRINT,
        }
        with pytest.raises(TypeError):
            config.hostnames["start.example"] = "other"
        with pytest.raises(TypeError):
            config.zones["example"] = "other"

    def test_overlapping_rules_select_and_fingerprint_without_a_production_map(self):
        """Loaded rules keep the start and maintenance overlap."""
        config = cache_purge.load_purge_config(_config_text())
        maintenance = "start.example/en-US/maintenance/index.html"
        other = "start.example/en-US/index.html"
        before = {maintenance: b"down", other: b"page"}
        changed_maintenance = {maintenance: b"still down", other: b"page"}
        changed_other = {maintenance: b"down", other: b"changed"}

        assert cache_purge.changed_hostnames(before, changed_maintenance, config.rules) == {
            "start.example", "addons.example",
        }
        assert cache_purge.changed_hostnames(before, changed_other, config.rules) == {"start.example"}
        assert _fingerprint_changes(before, changed_maintenance, config.rules) == {
            "start.example", "addons.example",
        }
        assert _fingerprint_changes(before, changed_other, config.rules) == {"start.example"}

    def test_repeated_hostname_assignment_is_preserved(self):
        """The same hostname may occur in overlapping rules and more than once in a rule."""
        config = copy.deepcopy(_EXAMPLE_CONFIG)
        config["rules"][1]["hostnames"] = ["addons.example", "start.example", "start.example"]
        loaded = cache_purge.load_purge_config(_config_text(config))

        assert loaded.rules[1] == (
            "start.example/en-US/maintenance/",
            ("addons.example", "start.example", "start.example"),
        )

    def test_undefined_hostname_and_zone_references_are_rejected(self):
        """Rules and hostname bindings cannot name a hostname or zone that is not declared."""
        undefined_host = copy.deepcopy(_EXAMPLE_CONFIG)
        undefined_host["rules"][0]["hostnames"] = ["missing.example"]
        undefined_zone = copy.deepcopy(_EXAMPLE_CONFIG)
        undefined_zone["hostnames"]["start.example"] = "missing-zone"
        unused = copy.deepcopy(_EXAMPLE_CONFIG)
        unused["hostnames"]["unused.example"] = "example"

        with pytest.raises(ValueError, match="rules\\[0\\].hostnames references an undefined hostname"):
            cache_purge.load_purge_config(_config_text(undefined_host))
        with pytest.raises(ValueError, match="hostnames references an undefined zone"):
            cache_purge.load_purge_config(_config_text(undefined_zone))
        with pytest.raises(ValueError, match="hostname is not used by a rule"):
            cache_purge.load_purge_config(_config_text(unused))

    @pytest.mark.parametrize("raw,field", [
        ('{"version":1,"version":1,"zones":{},"hostnames":{},"rules":[]}', "configuration"),
        ('{"version":1,"zones":{"example":{"id":"%s"},"example":{"id":"%s"}},"hostnames":{},"rules":[]}' % (_ZONE_ID, _ZONE_ID), "zones"),
        ('{"version":1,"zones":{"example":{"id":"%s","id":"%s"}},"hostnames":{},"rules":[]}' % (_ZONE_ID, _ZONE_ID), "zone"),
    ])
    def test_duplicate_keys_are_rejected(self, raw, field):
        """A repeated JSON key is invalid even when both values match."""
        with pytest.raises(ValueError, match=f"duplicate key in {field}"):
            cache_purge.load_purge_config(raw)

    @pytest.mark.parametrize("version", [True, False, 2, 0, "1", 1.0])
    def test_unsupported_version_is_rejected(self, version):
        """Only the integer 1 is a supported document version."""
        config = copy.deepcopy(_EXAMPLE_CONFIG)
        config["version"] = version

        with pytest.raises(ValueError, match="version must be 1"):
            cache_purge.load_purge_config(_config_text(config))

    @pytest.mark.parametrize("mutate,message", [
        (lambda config: config["rules"].__setitem__(0, {"path": 1, "hostnames": ["start.example"]}), r"rules\[0\].path"),
        (lambda config: config["zones"]["example"].__setitem__("id", True), "invalid zone id"),
        (lambda config: config["hostnames"].__setitem__("start.example", 1), "undefined zone"),
        (lambda config: config.__setitem__("rules", {"path": "start.example/"}), "rules must be an array"),
        (lambda config: config["zones"]["example"].__setitem__("token", "super-secret-token-value"), "unknown field in zone"),
        (lambda config: config.__setitem__("token", "super-secret-token-value"), "unknown field in configuration"),
    ])
    def test_malformed_values_and_unknown_fields_are_rejected(self, mutate, message):
        """Wrong types and unexpected fields name the location and omit the document value."""
        config = copy.deepcopy(_EXAMPLE_CONFIG)
        mutate(config)

        with pytest.raises(ValueError, match=message) as caught:
            cache_purge.load_purge_config(_config_text(config))

        assert "super-secret-token-value" not in str(caught.value)

    @pytest.mark.parametrize("path", [
        "",
        "/start.example/index.html",
        "start.example/../secret-traversal/index.html",
        "start.example/./index.html",
        "start.example//index.html",
        "../start.example/",
        "C:/start.example/index.html",
        "start.example\\index.html",
    ])
    def test_unsafe_paths_are_rejected_without_normalization(self, path):
        """Absolute paths and traversal components are not rewritten into rule paths."""
        config = copy.deepcopy(_EXAMPLE_CONFIG)
        config["rules"][0]["path"] = path

        with pytest.raises(ValueError, match="rules\\[0\\].path is unsafe") as caught:
            cache_purge.load_purge_config(_config_text(config))

        assert "secret-traversal" not in str(caught.value)
        if path:
            assert path not in str(caught.value)

    def test_malformed_json_does_not_echo_the_document(self):
        """A parse failure names the problem rather than the document text."""
        with pytest.raises(ValueError, match="malformed JSON") as caught:
            cache_purge.load_purge_config('{"version": "secret-broken-json"')

        assert caught.value.__cause__ is None
        assert "secret-broken-json" not in str(caught.value)

    def test_zone_alias_is_not_a_dns_hostname(self):
        """An underscore alias such as primary_zone can identify a zone."""
        config = copy.deepcopy(_EXAMPLE_CONFIG)
        config["zones"] = {"primary_zone": {"id": _ZONE_ID}}
        config["hostnames"] = {
            "start.example": "primary_zone",
            "addons.example": "primary_zone",
        }
        loaded = cache_purge.load_purge_config(_config_text(config))

        assert loaded.zones == {"primary_zone": _ZONE_ID}
        assert loaded.hostnames["start.example"] == "primary_zone"

    @pytest.mark.parametrize("alias", ["Primary_zone", "primary.zone", "1zone", "_zone"])
    def test_invalid_zone_alias_is_rejected(self, alias):
        """Zone aliases stay lowercase and do not use hostname spelling."""
        config = copy.deepcopy(_EXAMPLE_CONFIG)
        config["zones"] = {alias: {"id": _ZONE_ID}}
        config["hostnames"] = {"start.example": alias}

        with pytest.raises(ValueError, match="invalid zone name") as caught:
            cache_purge.load_purge_config(_config_text(config))

        assert alias not in str(caught.value)

    @pytest.mark.parametrize("hostname", [
        "www.example.com",
        "start.example",
        "a.b",
        "xn--n3h.example",
        "a-b.example",
        "a" * 63 + ".example",
        ".".join(["a"] * 127),
    ])
    def test_literal_dns_hostnames_are_accepted(self, hostname):
        """Production-shaped names and ASCII punycode are managed hostnames."""
        config = copy.deepcopy(_EXAMPLE_CONFIG)
        config["hostnames"] = {hostname: "example", "addons.example": "example"}
        config["rules"][0]["hostnames"] = [hostname]
        loaded = cache_purge.load_purge_config(_config_text(config))

        assert loaded.hostnames[hostname] == "example"

    @pytest.mark.parametrize("hostname", [
        "https://start.example/path",
        "start.example:443",
        "start.example/path",
        "*",
        "start.example\x00",
        "Start.example",
        "start.example.",
        "-start.example",
        "start-.example",
        "st.example-",
        "start..example",
        ".start.example",
        "*.example",
        "example",
        "a" * 64 + ".example",
        ".".join(["a"] * 128),
    ])
    def test_invalid_hostnames_are_rejected_without_echoing_them(self, hostname):
        """Schemes, ports, paths, wildcards, case, and trailing dots are not keys."""
        config = copy.deepcopy(_EXAMPLE_CONFIG)
        config["hostnames"] = {hostname: "example"}
        config["rules"] = [{"path": "start.example/", "hostnames": [hostname]}]

        with pytest.raises(ValueError, match="invalid hostname") as caught:
            cache_purge.load_purge_config(_config_text(config))

        assert hostname not in str(caught.value)
        assert hostname not in "".join(caught.value.args)

    def test_duplicate_hostname_keys_and_rule_fields_are_rejected(self):
        """Repeated hostname keys and repeated rule fields are duplicate JSON keys."""
        zone = '{"example":{"id":"%s"}}' % _ZONE_ID
        duplicate_host = (
            '{"version":1,"zones":%s,"hostnames":{"start.example":"example","start.example":"example"},'
            '"rules":[{"path":"start.example/","hostnames":["start.example"]}]}'
        ) % zone
        duplicate_field = (
            '{"version":1,"zones":%s,"hostnames":{"start.example":"example"},'
            '"rules":[{"path":"secret-rule-path/","path":"secret-rule-path/","hostnames":["start.example"]}]}'
        ) % zone

        with pytest.raises(ValueError, match="duplicate key in hostnames"):
            cache_purge.load_purge_config(duplicate_host)
        with pytest.raises(ValueError, match="duplicate key in rules\\[0\\]") as caught:
            cache_purge.load_purge_config(duplicate_field)

        assert "secret-rule-path" not in str(caught.value)


_PROD_IMAGE = "123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod@sha256:"
_IMAGE_A = _PROD_IMAGE + "a" * 64
_IMAGE_B = _PROD_IMAGE + "b" * 64
_IMAGE_C = _PROD_IMAGE + "c" * 64


def _purge_state(purged=None, pending=()):
    """Build a purge state that does not yet have an owner."""
    return cache_purge.PurgeState({} if purged is None else purged, frozenset(pending), None)


def _state_snapshot(state):
    """Copy the observable purge state without relying on deepcopy."""
    intent = None
    if state.intent is not None:
        intent = (state.intent.identity, state.intent.image, dict(state.intent.fingerprints))
    return (dict(state.purged), set(state.pending), intent)


class TestDeploymentIntent:
    """Acceptance is applied only for the deployment that currently owns the state."""

    def test_unsuccessful_intermediate_purge_stays_pending_after_revert(self):
        """A was accepted, B was not, and returning to A does not clear that work."""
        accepted = cache_purge.begin_deployment_intent(
            _purge_state(), "intent-a", _IMAGE_A, {"www.example": "A"})
        accepted = cache_purge.record_intent_acceptance(accepted, "intent-a", {"www.example": "A"})
        intermediate = cache_purge.begin_deployment_intent(
            accepted, "intent-b", _IMAGE_B, {"www.example": "B"})
        reverted = cache_purge.begin_deployment_intent(
            intermediate, "intent-a-again", _IMAGE_A, {"www.example": "A"})

        assert accepted.pending == frozenset()
        assert "www.example" in intermediate.pending
        assert reverted.pending == frozenset({"www.example"})
        assert reverted.purged == {"www.example": "A"}
        assert reverted.intent.identity == "intent-a-again"

    def test_partial_acceptance_then_revert_keeps_both_hostnames_pending(self):
        """One accepted hostname and one still pending are both outstanding after the revert."""
        planned = cache_purge.begin_deployment_intent(
            _purge_state(), "intent-b", _IMAGE_B, {"www.example": "B", "start.example": "B"})
        partial = cache_purge.record_intent_acceptance(planned, "intent-b", {"www.example": "B"})
        reverted = cache_purge.begin_deployment_intent(
            partial, "intent-a", _IMAGE_A, {"www.example": "A", "start.example": "A"})

        assert partial.purged == {"www.example": "B"}
        assert partial.pending == frozenset({"start.example"})
        assert partial.intent == planned.intent
        assert reverted.pending == frozenset({"www.example", "start.example"})
        assert reverted.purged == {"www.example": "B"}

    def test_stale_acceptance_does_not_change_the_newer_intent(self):
        """B's acceptance is rejected after C has become the owner."""
        older = cache_purge.begin_deployment_intent(
            _purge_state(), "intent-b", _IMAGE_B, {"www.example": "B"})
        current = cache_purge.begin_deployment_intent(
            older, "intent-c", _IMAGE_C, {"www.example": "C"})
        before = _state_snapshot(current)

        with pytest.raises(ValueError, match="current deployment intent"):
            cache_purge.record_intent_acceptance(current, "intent-b", {"www.example": "B"})

        assert _state_snapshot(current) == before
        assert current.intent.identity == "intent-c"
        assert current.pending == frozenset({"www.example"})

    def test_stale_acceptance_is_rejected_when_fingerprints_match(self):
        """Identical fingerprints do not let an older intent clear the newer owner's work."""
        fingerprints = {"www.example": "same"}
        older = cache_purge.begin_deployment_intent(_purge_state(), "intent-b", _IMAGE_B, fingerprints)
        current = cache_purge.begin_deployment_intent(older, "intent-c", _IMAGE_C, fingerprints)
        before = _state_snapshot(current)

        with pytest.raises(ValueError, match="current deployment intent"):
            cache_purge.record_intent_acceptance(current, "intent-b", fingerprints)

        assert _state_snapshot(current) == before
        assert current.intent.identity == "intent-c"

    def test_mismatched_fingerprint_and_unknown_hostname_are_rejected(self):
        """A valid entry followed by a bad fingerprint or hostname records nothing."""
        state = cache_purge.begin_deployment_intent(
            _purge_state(), "intent-b", _IMAGE_B, {"www.example": "B", "start.example": "B"})
        before = _state_snapshot(state)

        with pytest.raises(ValueError, match="does not match the current intent"):
            cache_purge.record_intent_acceptance(
                state, "intent-b", {"www.example": "B", "start.example": "A"})
        with pytest.raises(ValueError, match="outside the current intent"):
            cache_purge.record_intent_acceptance(state, "intent-b", {"www.example": "B", "other.example": "B"})

        assert state.purged == {}
        assert state.pending == frozenset({"www.example", "start.example"})
        assert _state_snapshot(state) == before

    def test_removed_hostname_stays_pending_until_it_returns(self):
        """A pending hostname that leaves the intent remains recorded when it comes back."""
        both = cache_purge.begin_deployment_intent(
            _purge_state(pending={"www.example"}),
            "intent-1",
            _IMAGE_A,
            {"www.example": "A", "start.example": "S"},
        )
        removed = cache_purge.begin_deployment_intent(
            both, "intent-2", _IMAGE_B, {"start.example": "S"})
        restored = cache_purge.begin_deployment_intent(
            removed, "intent-3", _IMAGE_C, {"www.example": "A", "start.example": "S"})

        assert "www.example" in removed.pending
        assert removed.intent.fingerprints == {"start.example": "S"}
        assert "www.example" in restored.pending
        assert restored.intent.identity == "intent-3"

    def test_same_intent_and_acceptance_can_be_repeated(self):
        """Repeating the current registration and its acceptance is idempotent."""
        fingerprints = {"www.example": "A", "start.example": "A"}
        first = cache_purge.begin_deployment_intent(_purge_state(), "intent-a", _IMAGE_A, fingerprints)
        repeated = cache_purge.begin_deployment_intent(first, "intent-a", _IMAGE_A, dict(fingerprints))
        accepted = {"www.example": "A"}
        once = cache_purge.record_intent_acceptance(repeated, "intent-a", accepted)
        twice = cache_purge.record_intent_acceptance(once, "intent-a", dict(accepted))
        registered_again = cache_purge.begin_deployment_intent(
            twice, "intent-a", _IMAGE_A, fingerprints)

        assert repeated == first
        assert once.purged == {"www.example": "A"}
        assert once.pending == frozenset({"start.example"})
        assert twice == once
        assert registered_again == twice

    def test_new_identity_replaces_matching_intent_inputs(self):
        """A new identity owns the state even when the image and fingerprints are unchanged."""
        fingerprints = {"www.example": "A"}
        first = cache_purge.begin_deployment_intent(_purge_state(), "intent-b", _IMAGE_A, fingerprints)
        second = cache_purge.begin_deployment_intent(first, "intent-c", _IMAGE_A, fingerprints)

        assert second.intent.identity == "intent-c"
        assert second.intent.image == first.intent.image
        assert second.pending == first.pending
        assert second.purged == first.purged

    def test_identity_is_not_reused_for_different_inputs(self):
        """The current identity cannot be reused for another digest or fingerprint."""
        state = cache_purge.begin_deployment_intent(
            _purge_state(), "intent-a", _IMAGE_A, {"www.example": "A"})
        before = _state_snapshot(state)

        with pytest.raises(ValueError, match="already bound"):
            cache_purge.begin_deployment_intent(state, "intent-a", _IMAGE_B, {"www.example": "A"})
        with pytest.raises(ValueError, match="already bound"):
            cache_purge.begin_deployment_intent(state, "intent-a", _IMAGE_A, {"www.example": "B"})

        assert _state_snapshot(state) == before

    def test_inputs_are_not_mutated(self):
        """Planning and acceptance copy the supplied state and fingerprints."""
        purged = {}
        pending = {"old.example"}
        fingerprints = {"www.example": "A"}
        accepted = {"www.example": "A"}
        state = cache_purge.PurgeState(purged, pending, None)
        planned = cache_purge.begin_deployment_intent(state, "intent-a", _IMAGE_A, fingerprints)
        recorded = cache_purge.record_intent_acceptance(planned, "intent-a", accepted)

        assert purged == {}
        assert pending == {"old.example"}
        assert fingerprints == {"www.example": "A"}
        assert accepted == {"www.example": "A"}
        assert state.intent is None
        assert recorded.pending == frozenset({"old.example"})
        assert recorded.purged == {"www.example": "A"}
        assert planned.purged is not purged
        assert planned.intent.fingerprints is not fingerprints
        assert recorded.purged is not planned.purged
        with pytest.raises(TypeError):
            planned.intent.fingerprints["www.example"] = "Z"

    def test_digest_pinned_image_is_accepted(self):
        """A digest-pinned reference is stored exactly as supplied."""
        planned = cache_purge.begin_deployment_intent(
            _purge_state(), "intent-a", _IMAGE_A, {"www.example": "A"})

        assert planned.intent.image == _IMAGE_A

    @pytest.mark.parametrize("image", [
        "registry.example/site:latest",
        "123456789012.dkr.ecr.us-west-2.amazonaws.com/thunderbird-website-prod:latest",
        "",
        "   ",
        _PROD_IMAGE + ("a" * 63),
        _PROD_IMAGE + ("A" * 64),
        None,
        1,
    ])
    def test_mutable_or_malformed_images_are_rejected(self, image):
        """A tag, blank value, bad digest, or non-string image leaves state unchanged."""
        state = _purge_state(pending={"www.example"})
        before = _state_snapshot(state)

        with pytest.raises(ValueError, match="digest-pinned") as caught:
            cache_purge.begin_deployment_intent(state, "intent-a", image, {"www.example": "A"})

        if isinstance(image, str) and image.strip() != "":
            assert image not in str(caught.value)
        assert _state_snapshot(state) == before

    def test_acceptance_without_an_intent_is_rejected(self):
        """Acceptance cannot create an owner or clear pending work."""
        state = _purge_state(pending={"www.example"})
        before = _state_snapshot(state)

        with pytest.raises(ValueError, match="no current deployment intent"):
            cache_purge.record_intent_acceptance(state, "intent-a", {"www.example": "A"})

        assert _state_snapshot(state) == before

    @pytest.mark.parametrize("identity", ["", None, 1])
    def test_missing_or_invalid_identity_is_rejected(self, identity):
        """A blank or non-string identity is rejected for planning and acceptance."""
        state = _purge_state(pending={"www.example"})
        before = _state_snapshot(state)

        with pytest.raises(ValueError, match="deployment intent identity is required"):
            cache_purge.begin_deployment_intent(state, identity, _IMAGE_A, {"www.example": "A"})

        planned = cache_purge.begin_deployment_intent(state, "intent-a", _IMAGE_A, {"www.example": "A"})
        planned_before = _state_snapshot(planned)
        with pytest.raises(ValueError, match="deployment intent identity is required"):
            cache_purge.record_intent_acceptance(planned, identity, {"www.example": "A"})

        assert _state_snapshot(state) == before
        assert _state_snapshot(planned) == planned_before

    @pytest.mark.parametrize("fingerprints", ["www.example", b"www.example", ["www.example"], None])
    def test_non_mapping_fingerprints_are_rejected(self, fingerprints):
        """Intended and accepted fingerprints must be mappings, and nothing is recorded."""
        state = _purge_state(pending={"www.example"})
        before = _state_snapshot(state)

        with pytest.raises(ValueError, match="intended fingerprints must be a mapping"):
            cache_purge.begin_deployment_intent(state, "intent-a", _IMAGE_A, fingerprints)

        planned = cache_purge.begin_deployment_intent(state, "intent-a", _IMAGE_A, {"www.example": "A"})
        planned_before = _state_snapshot(planned)
        with pytest.raises(ValueError, match="accepted purges must be a mapping"):
            cache_purge.record_intent_acceptance(planned, "intent-a", fingerprints)

        assert _state_snapshot(state) == before
        assert _state_snapshot(planned) == planned_before
