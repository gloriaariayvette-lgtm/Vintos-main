#!/usr/bin/env python3
"""LOOK, KEPT and /projects — the room's first organ, asserted at the matrix.

A finished piece must reach him with the worktable empty (LOOK), finishing must
not require revealing (KEPT), a look opens exactly one door, and the house may
list finished work content-free (/projects). Lives in the repo so the deploy's
suites guard it; broker/LOOK-SPEC.md is the spec.
"""
import os, sys, json, tempfile, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import broker as BK

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:70]) if d else ""))

TMP = tempfile.mkdtemp(prefix="look-")
BK.ROOT = TMP
BK.HEALTH = os.path.join(TMP, "health.jsonl")
BK._KEYPATH = os.path.join(TMP, ".visit-key")
os.makedirs(os.path.join(TMP, "projects"))

def route(path, body):
    ok, why = BK.authorize_route(path, body)
    if not ok:
        return {"error": why}
    return BK.ROUTES[path](body)

print("--- make twice in one second; both survive ---")
pid = BK.create_project({"intent": "a thing of my own", "sealed": True})["id"]
BK.to_table({"id": pid})
op = BK.open_visit({"id": pid}); cap = op["visit_capability"]
m1 = route("/make", {"id": pid, "kind": "write", "content": "first piece", "visit_capability": cap})
BK._j(os.path.join(BK._p(pid), ".visit.json"))  # attendance: face it before the next
v = BK._j(os.path.join(BK._p(pid), ".visit.json")); v["attended"]["write"] = True; v["budgets"]["write"] = 5
BK._w(os.path.join(BK._p(pid), ".visit.json"), v)
m2 = route("/make", {"id": pid, "kind": "write", "content": "second piece", "visit_capability": cap})
f1, f2 = m1.get("file"), m2.get("file")
check("two makes, two files", f1 and f2 and f1 != f2, (f1, f2))
check("make returns the digest of the stored bytes", m2.get("sha256") == hashlib.sha256(b"second piece").hexdigest())

print("\n--- KEPT: finished and mine ---")
r = route("/state", {"id": pid, "state": "KEPT", "note": "done"})
check("KEPT through the house door is refused", r.get("error"), r)
r = route("/state/kept", {"id": pid, "note": "it is finished and I am not showing it", "visit_capability": cap})
check("KEPT with a live visit capability", r.get("ok") and r.get("state") == "KEPT", r)
p = BK._j(os.path.join(BK._p(pid), "project.json"))
check("visibility untouched, worktable released", p.get("visibility") != "revealed" and not (BK._j(os.path.join(TMP, "active.json"), {}) or {}).get("id"))

print("\n--- LOOK: read after the table is empty ---")
off = route("/look/offer", {"id": pid})
check("offer lists artifacts by digest", off.get("ok") and set(off["offer"]["artifacts"]) == {f1, f2}, off)
mint = route("/look/mint", {"id": pid, "offer": off["offer"], "file": f2})
check("mint consumes the receipt", mint.get("ok") and mint.get("look_capability"), mint)
again = route("/look/mint", {"id": pid, "offer": off["offer"], "file": f2})
check("a replayed receipt mints nothing", again.get("error"), again)
forged = route("/look/mint", {"id": pid, "offer": {"nonce": "0" * 32, "artifacts": {f2: "x"}}, "file": f2})
check("a forged 'I chose' mints nothing", forged.get("error"), forged)
look = mint["look_capability"]
r = route("/artifact", {"id": pid, "file": f2, "look_capability": look})
check("LOOK reads the exact file with the table empty", r.get("content") == "second piece", r)
r = route("/artifact", {"id": pid, "file": f1, "look_capability": look})
check("LOOK refused on the other file (wrong digest)", r.get("error"), r)
notes = os.path.join(BK._p(pid), "look-notes.jsonl")
check("a look writes no inspection note", not os.path.exists(notes) or open(notes).read().strip() == "")
for door, body in [("/make", {"kind": "write", "content": "x"}), ("/handoff", {"text": "t"}), ("/inspect", {"note": "n"}),
                   ("/settle", {}), ("/state", {"state": "RESTING"}), ("/reveal/prepare", {"artifact": f2})]:
    body.update({"id": pid, "look_capability": look})
    r = route(door, body)
    check("LOOK refused at %s" % door, r.get("error"), r)

print("\n--- a visit token is no skeleton key ---")
r = route("/make", {"id": pid, "kind": "write", "content": "x", "visit_capability": look})
check("a look presented as a visit capability opens nothing", r.get("error"), r)

print("\n--- /projects is content-free ---")
other = BK.create_project({"intent": "unstarted root text", "sealed": True})["id"]
r = route("/projects", {})
rows = r.get("projects", []); mine = [x for x in rows if x["id"] == pid]
check("lists every project with id/state/artifact_count", r.get("ok") and len(rows) == 2 and mine and mine[0]["state"] == "KEPT" and mine[0]["artifact_count"] == 2, rows)
check("KEPT carries kept_at", bool(mine and mine[0].get("kept_at")))
dump = json.dumps(r)
check("no intent, no filenames, no content, no notes", "a thing of my own" not in dump and f1 not in dump and "first piece" not in dump and "unstarted root" not in dump and "note" not in dump)
r = route("/projects", {"look_capability": look})
check("a look token at /projects is refused", r.get("error"), r)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
