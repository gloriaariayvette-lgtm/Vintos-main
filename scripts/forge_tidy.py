#!/usr/bin/env python3
"""forge_tidy.py — stop the old Lab write-ups in the Forge, and nothing else (Gloria, 2026-10-03: "Stop the old lab
write ups but don't prevent new ones").

The Lab stopped sending "Document this sourced Lab question" write-ups on 26 September; the dozens still open share
the Forge's three steps a day with everything that matters, and her page already calls each one "safe to stop".
This stops them through the Forge's own owner API (the same Stop her page uses). It does not touch the Lab's
intake, so a new write-up can still arrive; it never stops a project of any other kind.

    python3 forge_tidy.py          list what would be stopped
    python3 forge_tidy.py --stop   stop them
"""
import json, os, sys
from urllib.request import Request, urlopen

FORGE_BASE = os.environ.get("VINTOS_FORGE_BASE", "http://127.0.0.1:8612")
OWNER_TOKEN = os.path.expanduser("~/.config/vintos/forge-owner")
OLD_WRITE_UP = "Document this sourced Lab question"
DONE = ("complete", "cancelled", "abandoned")


def _token():
    from forge_loop_runtime import secret
    return secret(OWNER_TOKEN)


def _call(path, method="GET", token=None, opener=None):
    req = Request(FORGE_BASE + path, method=method, data=(b"{}" if method == "POST" else None),
                  headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with (opener or urlopen)(req, timeout=20) as r:
        return json.loads(r.read(4 * 1024 * 1024))


def old_write_ups(projects):
    """Open projects that are old Lab write-ups, by the words they begin with; never a private one."""
    return [p for p in projects if isinstance(p, dict) and p.get("state") not in DONE and not p.get("private")
            and str(p.get("intent") or "").strip().startswith(OLD_WRITE_UP)]


def tidy(stop=False, opener=None, token=None):
    token = token or _token()
    projects = _call("/api/projects", token=token, opener=opener)
    found = old_write_ups(projects if isinstance(projects, list) else [])
    stopped = []
    for p in found:
        if stop:
            _call("/api/projects/%s/cancel" % p["id"], "POST", token=token, opener=opener)
            stopped.append(p["id"])
    return found, stopped


if __name__ == "__main__":
    found, stopped = tidy(stop="--stop" in sys.argv)
    for p in found:
        first = str(p.get("intent") or "").split("\n")[0][len(OLD_WRITE_UP):].strip(" :")[:100]
        print(("stopped  " if p["id"] in stopped else "would stop  ") + first)
    print("%d old Lab write-up(s) %s; nothing else touched; new write-ups can still arrive"
          % (len(found), "stopped" if "--stop" in sys.argv else "found (run with --stop to stop them)"))
