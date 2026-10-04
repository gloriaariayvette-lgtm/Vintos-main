#!/usr/bin/env python3
"""Find the MCP url of a connector Gloria has connected to her Claude account, so she never has to (2026-10-04).

Her connectors are attached to the account, not to a url she was ever shown. The headless relay
(claude_connector_relay.py) does need a url, so until now a new connector sat unreachable with a note asking her
for something she does not have.

This asks the network instead. For each connector with no url, it tries the candidate endpoints for its name and
keeps the first that answers as an MCP server. An endpoint "answers" when it replies at all in a way only a real
MCP endpoint does: 200 with a JSON-RPC body, or 401/403 (there, and asking for the account's credentials). A 404,
a redirect to a sign-in page, or nothing at all is not a connector.

What it finds goes in ~/.vintos/connector-urls.json, which claude_connector_catalog reads on every pass; nothing
else changes, and a connector whose url is not found is simply still not offered.

    python3 connector_discover.py [--write] [name ...]
"""
from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import claude_connector_catalog as catalog

TIMEOUT = 20
# Anthropic hosts a connector at https://<slug>.mcp.claude.com/mcp (pubmed, already wired, is one). A connector's
# slug is not always its name here, so each gets a few spellings of its own name, and nothing else is tried.
HOSTED = "https://%s.mcp.claude.com/mcp"


def candidates(name, entry):
    slugs, server = [], str(entry.get("server") or name)
    for raw in (name, server, server.replace("_API", ""), server.replace("_by_", "-").replace("_", "-")):
        slug = raw.lower().replace("_", "-").strip("-")
        if slug and slug not in slugs:
            slugs.append(slug)
    # the last word of a multi-part server name ("EDEN_by_Basecamp_Research" -> "basecamp-research")
    tail = "-".join(server.lower().split("_by_")[-1].split("_"))
    if tail and tail not in slugs:
        slugs.append(tail)
    return [HOSTED % s for s in slugs] + list(entry.get("url_candidates") or [])


def answers(url, opener=None):
    """(True, why) when a real MCP endpoint is there. An initialize with no credentials: 401/403 proves it as
    well as 200 does, and neither sends anything of hers."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "vintos-connector-discover", "version": "1"}}}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=TIMEOUT) as r:
            text = r.read(4096).decode("utf-8", "replace")
            if r.status == 200 and ("jsonrpc" in text or "protocolVersion" in text or "result" in text):
                return True, "answered an MCP initialize"
            return False, "replied %s but not as an MCP server" % r.status
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return True, "there, and asking for the account's credentials (%d)" % exc.code
        return False, "HTTP %d" % exc.code
    except Exception as exc:
        return False, type(exc).__name__


def account_probe(name):
    """Through her Claude login: the connector's one free read-only call (claude_connector_gateway.probe)."""
    import claude_connector_gateway
    return claude_connector_gateway.probe(name)


def find(names=(), opener=None):
    """[{name, url, why}] for each connector whose url was found, and the misses. A connector with no address
    that answers its free probe through her Claude login is found as catalog.ACCOUNT."""
    found, missed = [], []
    for name, entry in sorted(catalog.PLUGINS.items()):
        if names and name not in names:
            continue
        if catalog.url_for(name):
            continue                     # already reachable: nothing to look for
        if entry.get("enabled") is False:
            continue                     # blocked for another reason; a url would not help
        why_not = []
        for url in candidates(name, entry):
            ok, why = answers(url, opener)
            if ok:
                found.append({"name": name, "url": url, "why": why})
                break
            why_not.append("%s: %s" % (url, why))
        else:
            if entry.get("probe"):
                ok, why = account_probe(name)
                if ok:
                    found.append({"name": name, "url": catalog.ACCOUNT, "why": why})
                    continue
                why_not.append("her Claude login: %s" % why)
            missed.append({"name": name, "tried": why_not})
    return found, missed


def write(found):
    """Add what was found to her file, keeping anything already in it."""
    try:
        with open(catalog.URLS_FILE) as f:
            rows = json.load(f)
        rows = rows if isinstance(rows, dict) else {}
    except Exception:
        rows = {}
    rows.update({r["name"]: r["url"] for r in found})
    os.makedirs(os.path.dirname(catalog.URLS_FILE), exist_ok=True)
    tmp = catalog.URLS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rows, f, indent=1, sort_keys=True)
    os.replace(tmp, catalog.URLS_FILE)
    return rows


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    found, missed = find(tuple(args))
    for row in found:
        print("found   %-14s %s  (%s)" % (row["name"], row["url"], row["why"]))
    for row in missed:
        print("not found %-12s tried: %s" % (row["name"], "; ".join(row["tried"])[:400]))
    if found and "--write" in sys.argv[1:]:
        write(found)
        print("\nwritten to %s — offered on his next pass" % catalog.URLS_FILE)
    elif found:
        print("\n(nothing written; run again with --write)")
