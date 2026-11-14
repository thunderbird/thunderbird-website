#!/usr/bin/env python3
"""Purge Cloudflare hostnames affected by one publication diff."""

import http.client
import json
import os
import ssl
import sys

API = "api.cloudflare.com"
TIMEOUT = 10

# Published directory -> production hostnames. Directories are the render paths
# copied from dist/ (settings.py, docker/Dockerfile). Extra names are production
# ServerAlias values in docker/conf/ssl.conf, not stage or test names.
SITES = {
    "www.thunderbird.net": ["www.thunderbird.net"],
    "start.thunderbird.net": ["start.thunderbird.net"],
    "updates.thunderbird.net": ["updates.thunderbird.net"],
    "tb.pro": ["tb.pro", "www.tb.pro"],
    "roadmaps.thunderbird.net": ["roadmaps.thunderbird.net", "roadmap.thunderbird.net"],
}
# Copied beside the sites and imported by the WSGI vhosts. start is static.
SHARED = {
    "wsgi.py": ["www.thunderbird.net", "updates.thunderbird.net", "tb.pro", "roadmaps.thunderbird.net"],
    "settings.py": ["www.thunderbird.net", "updates.thunderbird.net", "tb.pro", "roadmaps.thunderbird.net"],
}


def die(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def changed_paths(filename):
    try:
        data = open(filename, "rb").read()
    except OSError:
        die(f"Could not read changed paths from {filename}")
    return [item.decode() for item in data.split(b"\0") if item]


def affected(paths):
    hosts = []
    for path in paths:
        sites = SHARED.get(path)
        if sites is None:
            directory = path.split("/", 1)[0]
            sites = [directory] if directory in SITES else []
        for site in sites:
            for host in SITES[site]:
                if host not in hosts:
                    hosts.append(host)
    return hosts


def zones_for(hosts):
    raw = os.environ.get("CLOUDFLARE_ZONES", "")
    if not raw.strip():
        die("CLOUDFLARE_ZONES is missing")
    try:
        configured = json.loads(raw)
    except json.JSONDecodeError:
        die("CLOUDFLARE_ZONES is invalid")
    if not isinstance(configured, dict) or not configured:
        die("CLOUDFLARE_ZONES is invalid")
    grouped = {}
    for host in hosts:
        domains = [domain for domain in configured if host == domain or host.endswith("." + domain)]
        if not domains:
            die(f"No Cloudflare zone configured for {host}")
        domain = max(domains, key=len)
        zone_id = configured[domain]
        if not isinstance(zone_id, str) or len(zone_id) != 32 or not set(zone_id) <= set("0123456789abcdefABCDEF"):
            die(f"Cloudflare zone id for {domain} is invalid")
        grouped.setdefault(zone_id, []).append(host)
    return grouped


def api_token():
    value = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not value or any(char.isspace() for char in value):
        die("CLOUDFLARE_API_TOKEN is missing")
    return value


def purge(zone_id, hosts, token):
    connection = http.client.HTTPSConnection(API, timeout=TIMEOUT, context=ssl.create_default_context())
    try:
        connection.request(
            "POST",
            f"/client/v4/zones/{zone_id}/purge_cache",
            body=json.dumps({"hosts": hosts}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        status, raw = response.status, response.read()
    except (OSError, http.client.HTTPException):
        die(f"Cloudflare purge request failed for zone {zone_id}")
    finally:
        connection.close()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    if status != 200 or not isinstance(parsed, dict) or parsed.get("success") is not True:
        die(f"Cloudflare purge for zone {zone_id} was not accepted (HTTP {status})")


def main(argv):
    if len(argv) != 1:
        die("Usage: purge-cloudflare.py CHANGED_PATHS")
    hosts = affected(changed_paths(argv[0]))
    if not hosts:
        return 0
    token = api_token()
    for zone_id, names in zones_for(hosts).items():
        purge(zone_id, names, token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
