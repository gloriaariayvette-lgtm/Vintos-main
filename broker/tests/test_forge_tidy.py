#!/usr/bin/env python3
"""Stopping the old Lab write-ups touches nothing else and does not close the Lab's intake (2026-10-03). The Forge
is a stub that records each call; no token file is read; no socket opens."""
import io, json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
os.environ["HOME"] = tempfile.mkdtemp(prefix="forge-tidy-")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import forge_tidy as T
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
P = [{"id": "a", "state": "ready", "intent": "Document this sourced Lab question: pendrin H723R\nSource packet ..."},
     {"id": "b", "state": "ready", "intent": "The Lab needs an instrument it does not have: an MD simulator"},
     {"id": "c", "state": "complete", "intent": "Document this sourced Lab question: done already"},
     {"id": "d", "state": "ready", "intent": "Document this sourced Lab question: sealed", "private": True},
     {"id": "e", "state": "needs_authorization", "intent": "Document this sourced Lab question: AQP1"}]
CALLS = []
class _R(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False
def opener(req, timeout=0):
    CALLS.append((req.get_method(), req.full_url))
    return _R(json.dumps(P if req.full_url.endswith("/api/projects") else {"cancelled": True}).encode())
found, stopped = T.tidy(stop=False, opener=opener, token="t" * 40)
check("only open, non-private old Lab write-ups are found", [p["id"] for p in found] == ["a", "e"], found)
check("listing stops nothing", stopped == [] and all(m == "GET" for m, _ in CALLS), CALLS)
CALLS.clear()
found, stopped = T.tidy(stop=True, opener=opener, token="t" * 40)
check("--stop stops exactly those, through the Forge's own Stop",
      stopped == ["a", "e"] and [u for m, u in CALLS if m == "POST"] ==
      [T.FORGE_BASE + "/api/projects/a/cancel", T.FORGE_BASE + "/api/projects/e/cancel"], CALLS)
src = open(os.path.join(REPO, "scripts", "forge_tidy.py")).read()
check("the Lab's intake is never touched, so new write-ups can still arrive", "intake" not in src.split('"""', 2)[2])
check("nothing reached the network", NET == [], NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
