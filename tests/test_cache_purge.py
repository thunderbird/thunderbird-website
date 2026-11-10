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

        with pytest.raises(ValueError):
            cache_purge.purge_hostnames(zone_id, hostnames, api_token)

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
