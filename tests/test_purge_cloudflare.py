import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import http.client
import pytest

TOKEN = "dummy-token-slice2"
ZONE_NET = "0123456789abcdef0123456789abcdef"
ZONE_PRO = "fedcba9876543210fedcba9876543210"
ZONES = json.dumps({"thunderbird.net": ZONE_NET, "tb.pro": ZONE_PRO, "net": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"})

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "purge-cloudflare.py"
spec = importlib.util.spec_from_file_location("purge_cloudflare", SCRIPT)
purge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(purge)


def write_paths(tmp_path, paths):
    filename = tmp_path / "changed.z"
    filename.write_bytes(b"\0".join(path.encode() for path in paths) + (b"\0" if paths else b""))
    return str(filename)


def run(monkeypatch, filename, token=TOKEN, zones=ZONES):
    if token is None:
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", token)
    if zones is None:
        monkeypatch.delenv("CLOUDFLARE_ZONES", raising=False)
    else:
        monkeypatch.setenv("CLOUDFLARE_ZONES", zones)
    return purge.main([filename])


class Recorder(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.requests.append({
            "path": self.path,
            "body": body.decode(),
            "authorization": self.headers.get("Authorization"),
            "content_type": self.headers.get("Content-Type"),
        })
        mode = self.server.mode
        if mode == "delay":
            time.sleep(30)
            mode = "ok"
        if mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "/stolen")
            self.end_headers()
            return
        if mode == "second-fails":
            status = 200 if len(self.server.requests) == 1 else 500
        else:
            status = 200 if mode == "ok" else int(mode)
        payload = b'{"success":true}' if status == 200 else b'{"success":false}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


def serve(mode):
    server = HTTPServer(("127.0.0.1", 0), Recorder)
    server.mode = mode
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def use_server(monkeypatch, server):
    port = server.server_address[1]

    def connect(host, timeout=None, context=None):
        assert host == purge.API
        return http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)

    monkeypatch.setattr(purge.http.client, "HTTPSConnection", connect)


def bodies(server):
    return [json.loads(item["body"]) for item in server.requests]


class TestPurgeCloudflare:
    def test_site_paths_select_their_hosts(self, tmp_path, monkeypatch):
        server = serve("ok")
        use_server(monkeypatch, server)
        filename = write_paths(tmp_path, [
            "updates.thunderbird.net/en-US/index.html",
            "tb.pro/en-US/index.html",
            "roadmaps.thunderbird.net/index.html",
        ])
        assert run(monkeypatch, filename) == 0
        assert bodies(server) == [
            {"hosts": ["updates.thunderbird.net", "roadmaps.thunderbird.net", "roadmap.thunderbird.net"]},
            {"hosts": ["tb.pro", "www.tb.pro"]},
        ]

    def test_assets_and_shared_files_select_the_sites_that_serve_them(self, tmp_path, monkeypatch):
        server = serve("ok")
        use_server(monkeypatch, server)
        filename = write_paths(tmp_path, [
            "www.thunderbird.net/media/css/site.css",
            "start.thunderbird.net/media/js/app.js",
            "wsgi.py",
            "settings.py",
        ])
        assert run(monkeypatch, filename) == 0
        assert bodies(server) == [
            {"hosts": [
                "www.thunderbird.net",
                "start.thunderbird.net",
                "updates.thunderbird.net",
                "roadmaps.thunderbird.net",
                "roadmap.thunderbird.net",
            ]},
            {"hosts": ["tb.pro", "www.tb.pro"]},
        ]
        server.requests.clear()
        wsgi_only = write_paths(tmp_path, ["wsgi.py", "settings.py"])
        assert run(monkeypatch, wsgi_only) == 0
        sent = [host for payload in bodies(server) for host in payload["hosts"]]
        assert "start.thunderbird.net" not in sent
        assert "www.thunderbird.net" in sent and "updates.thunderbird.net" in sent
        assert all(item["authorization"] == f"Bearer {TOKEN}" for item in server.requests)
        assert all(item["content_type"] == "application/json" for item in server.requests)
        assert all("/purge_cache" in item["path"] and "purge_everything" not in item["body"] for item in server.requests)

    def test_deleted_path_is_classified_without_the_file(self, tmp_path, monkeypatch):
        server = serve("ok")
        use_server(monkeypatch, server)
        deleted = "start.thunderbird.net/en-US/removed/index.html"
        assert not os.path.exists(deleted)
        assert run(monkeypatch, write_paths(tmp_path, [deleted])) == 0
        assert bodies(server) == [{"hosts": ["start.thunderbird.net"]}]

    def test_unchanged_diff_makes_no_request(self, tmp_path, monkeypatch):
        called = []
        monkeypatch.setattr(purge.http.client, "HTTPSConnection", lambda *args, **kwargs: called.append(args))
        assert run(monkeypatch, write_paths(tmp_path, []), token=None, zones=None) == 0
        assert run(monkeypatch, write_paths(tmp_path, ["README.md"]), token=None, zones=None) == 0
        assert called == []

    def test_hosts_group_by_longest_zone_domain(self, tmp_path, monkeypatch):
        server = serve("ok")
        use_server(monkeypatch, server)
        filename = write_paths(tmp_path, [
            "www.thunderbird.net/index.html",
            "tb.pro/index.html",
        ])
        assert run(monkeypatch, filename) == 0
        assert [item["path"] for item in server.requests] == [
            f"/client/v4/zones/{ZONE_NET}/purge_cache",
            f"/client/v4/zones/{ZONE_PRO}/purge_cache",
        ]
        assert bodies(server) == [
            {"hosts": ["www.thunderbird.net"]},
            {"hosts": ["tb.pro", "www.tb.pro"]},
        ]

    def test_missing_configuration_sends_nothing(self, tmp_path, monkeypatch, capsys):
        called = []
        monkeypatch.setattr(purge.http.client, "HTTPSConnection", lambda *args, **kwargs: called.append(1))
        filename = write_paths(tmp_path, ["www.thunderbird.net/index.html"])
        secret = "dummy-token-slice2"
        cases = [
            (None, ZONES),
            ("", ZONES),
            (f"{secret} x", ZONES),
            (secret, None),
            (secret, ""),
            (secret, "{"),
            (secret, json.dumps({"example.com": ZONE_NET})),
            (secret, json.dumps({"thunderbird.net": "not-a-zone"})),
        ]
        for token, zones in cases:
            with pytest.raises(SystemExit) as caught:
                run(monkeypatch, filename, token=token, zones=zones)
            assert caught.value.code == 1
        assert called == []
        captured = capsys.readouterr()
        assert secret not in captured.out
        assert secret not in captured.err
        assert "No Cloudflare zone configured for www.thunderbird.net" in captured.err
        assert "CLOUDFLARE_API_TOKEN is missing" in captured.err

    def test_rejected_response_names_the_zone_not_the_token(self, tmp_path, monkeypatch, capsys):
        server = serve("401")
        use_server(monkeypatch, server)
        with pytest.raises(SystemExit) as caught:
            run(monkeypatch, write_paths(tmp_path, ["www.thunderbird.net/index.html"]))
        assert caught.value.code == 1
        error = capsys.readouterr().err
        assert f"HTTP 401" in error
        assert ZONE_NET in error
        assert TOKEN not in error
        assert len(server.requests) == 1

    def test_redirect_is_not_followed(self, tmp_path, monkeypatch, capsys):
        server = serve("redirect")
        use_server(monkeypatch, server)
        with pytest.raises(SystemExit):
            run(monkeypatch, write_paths(tmp_path, ["start.thunderbird.net/index.html"]))
        assert [item["path"] for item in server.requests] == [f"/client/v4/zones/{ZONE_NET}/purge_cache"]
        assert TOKEN not in capsys.readouterr().err

    def test_later_zone_failure_keeps_the_first_request(self, tmp_path, monkeypatch, capsys):
        server = serve("second-fails")
        use_server(monkeypatch, server)
        filename = write_paths(tmp_path, ["www.thunderbird.net/index.html", "tb.pro/index.html"])
        with pytest.raises(SystemExit) as caught:
            run(monkeypatch, filename)
        assert caught.value.code == 1
        assert bodies(server) == [
            {"hosts": ["www.thunderbird.net"]},
            {"hosts": ["tb.pro", "www.tb.pro"]},
        ]
        assert TOKEN not in capsys.readouterr().err

    def test_connection_failure_is_fast(self, tmp_path, monkeypatch, capsys):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        closed = probe.getsockname()[1]
        probe.close()

        def refuse(host, timeout=None, context=None):
            return http.client.HTTPConnection("127.0.0.1", closed, timeout=timeout)

        monkeypatch.setattr(purge.http.client, "HTTPSConnection", refuse)
        started = time.monotonic()
        with pytest.raises(SystemExit):
            run(monkeypatch, write_paths(tmp_path, ["www.thunderbird.net/index.html"]))
        assert time.monotonic() - started < 5
        error = capsys.readouterr().err
        assert "request failed" in error
        assert TOKEN not in error

    def test_slow_response_fails_within_the_timeout(self, tmp_path, monkeypatch, capsys):
        server = serve("delay")
        use_server(monkeypatch, server)
        started = time.monotonic()
        with pytest.raises(SystemExit):
            run(monkeypatch, write_paths(tmp_path, ["www.thunderbird.net/index.html"]))
        elapsed = time.monotonic() - started
        assert purge.TIMEOUT - 1 <= elapsed <= purge.TIMEOUT + 5
        assert TOKEN not in capsys.readouterr().err
        server.server_close()


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/deploy.yml"


def workflow_text():
    return WORKFLOW.read_text()


def publication_capture_script():
    """Return the publish commands from git add through the commit, excluding push."""
    lines = workflow_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "git add -A")
    end = next(i for i, line in enumerate(lines) if line.strip() == "git push")
    assert start < end
    body = "\n".join(lines[start:end])
    assert "git diff --cached --name-only --no-renames -z" in body
    assert "${{ secrets.TB_BUILDS_GIT_EMAIL }}" in body
    assert "BUILD_MESSAGE" in body
    assert "git push" not in body
    # Actions expands the expression before bash starts. The shell that
    # actually runs cannot contain the raw ${{ }} form.
    return body.replace("${{ secrets.TB_BUILDS_GIT_EMAIL }}", "bot@example.com") + "\n"


def git_env(runner, home):
    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "RUNNER_TEMP": str(runner),
        "BUILD_MESSAGE": "slice3 publication",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    })
    return env


def git(repo, env, *args):
    subprocess.run(["git", *args], cwd=repo, env=env, check=True)


def init_publication(repo, env):
    repo.mkdir()
    git(repo, env, "init", "-b", "main")
    for directory in ("www.thunderbird.net", "start.thunderbird.net"):
        (repo / directory).mkdir()
    (repo / "www.thunderbird.net" / "keep.html").write_text("keep\n")
    (repo / "www.thunderbird.net" / "old.html").write_text("old\n")
    (repo / "start.thunderbird.net" / "gone.html").write_text("gone\n")
    git(repo, env, "add", "-A")
    git(repo, env, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base")


def run_capture(repo, env):
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", publication_capture_script()],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def nul_paths(filename):
    data = Path(filename).read_bytes()
    return [item.decode() for item in data.split(b"\0") if item]


class TestPublicationWiring:
    def test_staged_changes_remain_after_commit(self, tmp_path, monkeypatch):
        repo = tmp_path / "publication"
        runner = tmp_path / "runner"
        runner.mkdir()
        env = git_env(runner, tmp_path / "home")
        init_publication(repo, env)
        (repo / "www.thunderbird.net" / "keep.html").write_text("changed\n")
        (repo / "updates.thunderbird.net").mkdir()
        (repo / "updates.thunderbird.net" / "new.html").write_text("new\n")
        (repo / "start.thunderbird.net" / "gone.html").unlink()
        git(repo, env, "mv", "www.thunderbird.net/old.html", "www.thunderbird.net/renamed.html")

        result = run_capture(repo, env)
        assert result.returncode == 0, result.stderr
        captured = runner / "publication-changes"
        assert set(nul_paths(captured)) == {
            "www.thunderbird.net/keep.html",
            "www.thunderbird.net/old.html",
            "www.thunderbird.net/renamed.html",
            "start.thunderbird.net/gone.html",
            "updates.thunderbird.net/new.html",
        }
        message = subprocess.check_output(
            ["git", "log", "-1", "--format=%s"], cwd=repo, env=env, text=True,
        )
        assert message.strip() == "Website rebuild triggered by slice3 publication"
        assert set(nul_paths(captured)) == {
            "www.thunderbird.net/keep.html",
            "www.thunderbird.net/old.html",
            "www.thunderbird.net/renamed.html",
            "start.thunderbird.net/gone.html",
            "updates.thunderbird.net/new.html",
        }

        server = serve("ok")
        use_server(monkeypatch, server)
        assert run(monkeypatch, str(captured)) == 0
        assert len(bodies(server)) == 1
        assert set(bodies(server)[0]["hosts"]) == {
            "www.thunderbird.net",
            "start.thunderbird.net",
            "updates.thunderbird.net",
        }

        again = run_capture(repo, env)
        assert again.returncode == 0, again.stderr
        assert nul_paths(captured) == []
        called = []
        monkeypatch.setattr(purge.http.client, "HTTPSConnection", lambda *args, **kwargs: called.append(args))
        assert run(monkeypatch, str(captured)) == 0
        assert called == []

    def test_failed_capture_does_not_fail_publication_or_leave_a_diff(self, tmp_path):
        repo = tmp_path / "publication"
        runner = tmp_path / "runner"
        runner.mkdir()
        env = git_env(runner, tmp_path / "home")
        init_publication(repo, env)
        (repo / "www.thunderbird.net" / "keep.html").write_text("changed\n")
        stale = runner / "publication-changes"
        stale.write_bytes(b"www.thunderbird.net/stale\0")
        (runner / "publication-changes.partial").mkdir()

        result = run_capture(repo, env)
        assert result.returncode == 0, result.stderr
        assert "production cache purge will be skipped" in result.stdout + result.stderr
        assert not stale.exists()
        assert b"stale" not in result.stdout.encode()
        message = subprocess.check_output(
            ["git", "log", "-1", "--format=%s"], cwd=repo, env=env, text=True,
        )
        assert "slice3 publication" in message

        missing = runner / "publication-changes"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(missing)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.returncode != 0
        assert "Could not read changed paths" in proc.stderr
        assert TOKEN not in proc.stderr

    def test_publication_outside_a_repository_fails_before_purge(self, tmp_path):
        repo = tmp_path / "not-a-repo"
        repo.mkdir()
        runner = tmp_path / "runner"
        runner.mkdir()
        result = run_capture(repo, git_env(runner, tmp_path / "home"))
        assert result.returncode != 0
        assert not (runner / "publication-changes").exists()

    def test_yaml_runs_purge_only_after_successful_production_readiness(self):
        text = workflow_text()
        names = []
        current = None
        steps = []
        for line in text.splitlines():
            if line.startswith("      - name: "):
                current = {
                    "name": line.split("name: ", 1)[1],
                    "if": None,
                    "continue_on_error": False,
                }
                steps.append(current)
                names.append(current["name"])
            elif current is not None and line.startswith("        if: "):
                current["if"] = line.split("if: ", 1)[1]
            elif current is not None and line.strip() == "continue-on-error: true":
                current["continue_on_error"] = True

        order = [
            "Publish to tb-website-builds",
            "Update ECS service",
            "Wait for production ECS service stability",
            "Purge changed production hosts",
        ]
        positions = [names.index(name) for name in order]
        assert positions == sorted(positions)
        purge_step = next(step for step in steps if step["name"] == order[-1])
        wait_step = next(step for step in steps if step["name"] == order[-2])
        assert purge_step["if"] == "env.DEPLOY_ENV == 'prod'"
        assert wait_step["if"] == "env.DEPLOY_ENV == 'prod'"
        assert purge_step["continue_on_error"] is True
        assert sum(step["continue_on_error"] for step in steps) == 1
        for step in (purge_step, wait_step):
            assert not any(token in (step["if"] or "") for token in ("success(", "failure(", "always(", "cancelled("))
        assert "CACHE_PURGE_CONFIG" not in text
        assert "vars.CLOUDFLARE_ZONES" in text
        assert "secrets.CLOUDFLARE_API_TOKEN" in text
        assert 'python3 tools/purge-cloudflare.py "$RUNNER_TEMP/publication-changes"' in text
        assert "AWS_MAX_ATTEMPTS" not in text
        assert "cancel-in-progress:" in text

        # GitHub supplies success() when an if has no status function. This is
        # that documented rule, not a live workflow run.
        def purge_runs(deploy_env, prior_steps_succeeded):
            return prior_steps_succeeded and deploy_env == "prod"

        assert purge_runs("prod", True) is True
        assert purge_runs("prod", False) is False
        assert purge_runs("stage", True) is False
