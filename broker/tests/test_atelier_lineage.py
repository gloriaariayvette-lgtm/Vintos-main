#!/usr/bin/env python3
"""Lineage, budgets, settlement order, separate histories, and a chain that
binds every kind — the room asserted at the matrix.

  100  the hash chain covers every event kind (views/LOOKs and capsule issues
       included); verify recomputes; a mismatch is TAMPER_HELD; a kind missing
       from the chain is a FAIL here, not a shrug.
  268  a second /visit/open while one is open sees the RESERVED budget, never a reset.
  269  settlement writes and returns the receipt BEFORE the visit is revoked.
  270  settled / aborted / re_adopted are separate kinds and /projects reports the last of each.
  311  every artifact carries previous_artifact_id + revision; reveal and LOOK show it.
"""
import os, sys, json, tempfile, shutil, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import broker as BK
import stratagem_store as SS

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:90]) if d else ""))

TMP = tempfile.mkdtemp(prefix="lineage-")            # scratch only, never ~/.vintos
BK.ROOT = SS.ROOT = TMP
BK.HEALTH = os.path.join(TMP, "health.jsonl")
BK._KEYPATH = os.path.join(TMP, ".visit-key")
os.makedirs(os.path.join(TMP, "projects"))
import atexit as _ae
_ae.register(lambda: shutil.rmtree(TMP, ignore_errors=True))
# lineage/door gates have their own suites; stubbed open here so a capsule can issue
SS._verify_lineage = lambda att, ref, typ: (True, None)
SS._burn_nonce = lambda n: True
SS._on_worktable = lambda pid: (True, None)

def route(path, body):
    ok, why = BK.authorize_route(path, body)
    if not ok:
        return {"error": why}
    return BK.ROUTES[path](body)

def events(pid):
    return [json.loads(l) for l in open(os.path.join(BK._p(pid), "events.jsonl")) if l.strip()]

def face(pid, kind="write"):
    v = BK._j(os.path.join(BK._p(pid), ".visit.json")); v["attended"][kind] = True
    BK._w(os.path.join(BK._p(pid), ".visit.json"), v)

print("--- 311: revision lineage on every artifact ---")
pid = BK.create_project({"intent": "a scene that grows", "sealed": True, "next_return": "open"})["id"]
BK.to_table({"id": pid})
op = BK.open_visit({"id": pid}); cap = op["visit_capability"]
check("first visit: empty manifest", op.get("manifest") == [] and not op.get("resumed"), op.get("manifest"))
m1 = route("/make", {"id": pid, "kind": "write", "content": "draft one", "visit_capability": cap})
check("a fresh artifact is revision 1 with no previous", m1.get("revision") == 1 and m1.get("previous_artifact_id") is None, m1)
route("/inspect", {"id": pid, "kind": "write", "artifact": m1["file"], "note": "the opening line holds\nmore", "visit_capability": cap})
m2 = route("/make", {"id": pid, "kind": "write", "content": "draft two", "previous": m1["file"], "visit_capability": cap})
check("continuing it yields revision 2 pointing at revision 1",
      m2.get("revision") == 2 and m2.get("previous_artifact_id") == m1["file"], m2)
face(pid)
bad = route("/make", {"id": pid, "kind": "write", "content": "x", "previous": "not_here.md", "visit_capability": cap})
check("continuing an artifact that is not his is refused", bad.get("error"), bad)
v = BK._j(os.path.join(BK._p(pid), ".visit.json"))
check("the refused make gave its budget unit back", v["budgets"]["write"] == 4, v["budgets"])
made = [e for e in events(pid) if e["type"] == "made"]
check("the made events carry the lineage", made[-1]["data"].get("revision") == 2 and made[-1]["data"].get("previous_artifact_id") == m1["file"], made[-1]["data"])

print("\n--- 313 (broker half): the manifest the next visit puts before him ---")
route("/inspect", {"id": pid, "kind": "write", "artifact": m2["file"], "note": "closer", "visit_capability": cap})
route("/handoff", {"id": pid, "text": "closing", "next_move": "  tighten the second stanza  ", "next_return": "tomorrow", "visit_capability": cap})
op2 = BK.open_visit({"id": pid}); cap2 = op2["visit_capability"]
rows = {r["id"]: r for r in op2.get("manifest") or []}
check("manifest lists id, revision, kind, one-line note",
      rows.get(m1["file"], {}).get("note") == "the opening line holds" and rows.get(m2["file"], {}).get("revision") == 2
      and rows.get(m2["file"], {}).get("kind") == "write" and rows.get(m2["file"], {}).get("previous_artifact_id") == m1["file"], rows)
check("272: next_move comes back verbatim", op2.get("next_move") == "  tighten the second stanza  ", repr(op2.get("next_move")))

print("\n--- 268: a second open sees the reserved budget ---")
m3 = route("/make", {"id": pid, "kind": "write", "content": "draft three", "visit_capability": cap2})
check("made under the new visit", m3.get("ok") and m3.get("remaining") == 5, m3)
op3 = BK.open_visit({"id": pid})
check("second open while one is open RESUMES it: same visit, budget 5 not 6",
      op3.get("resumed") and op3.get("visit") == op2.get("visit") and op3["budgets"]["write"] == 5, op3.get("budgets"))
face(pid)
m4 = route("/make", {"id": pid, "kind": "write", "content": "draft four", "visit_capability": op3["visit_capability"]})
check("the capability from the resumed open works and spends the same budget", m4.get("remaining") == 4, m4)
r = route("/make", {"id": pid, "kind": "write", "content": "z", "visit_capability": cap2})
check("the first capability still spends THAT budget (no reset)", r.get("remaining") == 3 if r.get("ok") else "face" in r.get("error", ""), r)

print("\n--- 100: the chain covers every kind, including LOOK and capsule issue ---")
route("/handoff", {"id": pid, "text": "t", "next_return": "open", "visit_capability": cap2})
off = route("/look/offer", {"id": pid})
check("look offer shows lineage per artifact", off["offer"]["lineage"][m2["file"]]["revision"] == 2, off["offer"].get("lineage"))
mint = route("/look/mint", {"id": pid, "offer": off["offer"], "file": m2["file"]})
rd = route("/artifact", {"id": pid, "file": m2["file"], "look_capability": mint["look_capability"]})
check("LOOK shows the lineage", rd.get("lineage", {}).get("revision") == 2 and rd["lineage"]["previous_artifact_id"] == m1["file"], rd.get("lineage"))
vc = route("/chain/verify", {"id": pid})
check("clean project chain verifies", vc.get("ok") and vc.get("state") == "intact", vc)
for kind in ("born", "to_table", "return_opened", "made", "looked", "handoff_written", "return_resumed", "look_offered", "looked_quietly"):
    check("kind in chain: " + kind, kind in vc.get("kinds", []), vc.get("kinds"))
evs = events(pid)
check("every event is hashed and chained", all("hash" in e and "prev" in e for e in evs) and all(e["seq"] == i for i, e in enumerate(evs)))
check("hashes recompute", all(BK._ev_hash(e) == e["hash"] for e in evs))

# a stratagem, so a capsule issue sits on the same project
op4 = BK.open_visit({"id": pid}); cap4 = op4["visit_capability"]
ad = SS.adopt({"id": pid, "capability": cap4, "objective": "stay with it",
               "provenance": {"root_type": "want", "root_ref": "w@1", "commissioned": False,
                              "attestation": {"body": {"nonce": "n1"}, "sig": "x"}},
               "sequencing_advantage": "later is mine",
               "tactics": [{"tactic": "DEFER", "turn_objective": "wait"}, {"tactic": "PROBE", "turn_objective": "test"}],
               "perimeter_scope": ["creative"]})
check("stratagem adopted", ad.get("stratagem_id"), ad)
c1 = SS.capsule({"id": pid, "turn_id": "t1", "surface": "chat"})
check("capsule issued", c1.get("capsule"), c1)
ok, n, why = SS.verify(pid)
check("stratagem ledger verifies with capsule bound", ok, why)
sevs = [json.loads(l) for l in open(os.path.join(SS._sd(pid), "events.jsonl")) if l.strip()]
check("kind in stratagem chain: capsule_issued", any(e["type"] == "capsule_issued" for e in sevs))

cpath = os.path.join(SS._sd(pid), "capsules.jsonl")
saved = open(cpath).read()
open(cpath, "w").write("")                                   # drop the capsule record; the event remains
ok, n, why = SS.verify(pid)
check("a capsule record missing for its issue event is a mismatch", not ok and "no capsule record" in str(why), why)
r = SS.capsule({"id": pid, "turn_id": "t2", "surface": "chat"})
check("... and holds: TAMPER_HELD", "TAMPER_HELD" in str(r.get("error", "")), r)
open(cpath, "w").write(saved)
rec = json.loads(saved.strip().splitlines()[0])
rec2 = dict(rec); rec2["seq"] = rec["seq"] + 50
open(cpath, "a").write(json.dumps(rec2) + "\n")             # a capsule slipped in with no issue event
ok, n, why = SS.verify(pid)
check("a capsule with no capsule_issued event is a mismatch", not ok and "no matching capsule_issued" in str(why), why)
open(cpath, "w").write(saved)
check("restored ledger verifies", SS.verify(pid)[0])

evpath = os.path.join(BK._p(pid), "events.jsonl")
rows = events(pid)
i = next(k for k, e in enumerate(rows) if e["type"] == "looked_quietly")
rows[i]["type"] = "made"                                      # rewrite the LOOK, keep its hash
with open(evpath, "w") as f:
    for e in rows: f.write(json.dumps(e) + "\n")
vc = route("/chain/verify", {"id": pid})
check("an altered LOOK event is TAMPER_HELD", vc.get("state") == "TAMPER_HELD" and "hash mismatch" in str(vc.get("failure")), vc)
r = SS.capsule({"id": pid, "turn_id": "t3", "surface": "chat"})
check("the stratagem holds on the project chain too", "TAMPER_HELD" in str(r.get("error", "")), r)
del rows[i]                                                   # drop it instead
with open(evpath, "w") as f:
    for e in rows: f.write(json.dumps(e) + "\n")
vc = route("/chain/verify", {"id": pid})
check("a dropped LOOK event is TAMPER_HELD", vc.get("state") == "TAMPER_HELD", vc)
rows.insert(i, {"ts": "x", "type": "looked_quietly", "data": {}})   # an unchained line after the chain began
with open(evpath, "w") as f:
    for e in rows: f.write(json.dumps(e) + "\n")
vc = route("/chain/verify", {"id": pid})
check("an unchained line inside the chain is TAMPER_HELD", vc.get("state") == "TAMPER_HELD" and "unchained" in str(vc.get("failure")), vc)

print("\n--- 269: the receipt comes before the revocation ---")
pid2 = BK.create_project({"intent": "to be shown", "sealed": True, "next_return": "open"})["id"]
BK.to_table({"id": pid2})
op = BK.open_visit({"id": pid2}); capb = op["visit_capability"]
mk = route("/make", {"id": pid2, "kind": "write", "content": "the gift", "visit_capability": capb})
prep = route("/reveal/prepare", {"id": pid2, "artifact": mk["file"], "visit_capability": capb})
check("reveal manifest carries lineage", prep["manifest"].get("lineage", {}).get("revision") == 1, prep["manifest"].get("lineage"))
conf = route("/reveal/confirm", {"id": pid2, "receipt": prep["receipt"]})
check("confirmed", conf.get("ok"), conf)
writes = []
_orig_w = BK._w
def _spy(path, data):
    writes.append(os.path.basename(path)); _orig_w(path, data)
BK._w = _spy
st = route("/settle", {"id": pid2})
BK._w = _orig_w
check("settlement returns the receipt", st.get("ok") and st["receipt"].get("visit_closed") == op["visit"], st)
check("receipt is written BEFORE the visit is revoked",
      "settlement.json" in writes and ".visit.json" in writes and writes.index("settlement.json") < writes.index(".visit.json"), writes)
check("... and before the worktable is released (when it was still held)", "active.json" not in writes or writes.index("settlement.json") < writes.index("active.json"), writes)
check("the visit IS revoked at the end", BK.verify_capability(capb, pid2)[0] is False)
check("receipt verifies", BK.verify_settlement({"receipt": st["receipt"]}).get("valid"))

print("\n--- 270: terminal / aborted / re-adopted kept apart ---")
kinds2 = [e["type"] for e in events(pid2)]
check("settled is its own kind", "settled" in kinds2 and "aborted" not in kinds2, kinds2)
BK.clear_table()   # whatever the earlier scenarios left on the table
pid3 = BK.create_project({"intent": "to be left", "sealed": True})["id"]
check("pid3 tabled", BK.to_table({"id": pid3}).get("ok"))
BK.set_state({"id": pid3, "state": "RESTING"})
BK.clear_table()
check("pid3 re-tabled", BK.to_table({"id": pid3}).get("ok"))
BK.set_state({"id": pid3, "state": "ABANDONED_BY_CHOICE", "note": "I no longer want to continue, and I do not know why"})
kinds3 = [e["type"] for e in events(pid3)]
check("re_adopted recorded on the second tabling, not the first", kinds3.count("re_adopted") == 1 and kinds3.index("re_adopted") > kinds3.index("to_table"), kinds3)
check("aborted is its own kind, and not settled", "aborted" in kinds3 and "settled" not in kinds3, kinds3)
lst = {r["id"]: r for r in route("/projects", {})["projects"]}
e3 = {e["type"]: e["ts"] for e in events(pid3)}
check("/projects reports the last of each, separately",
      lst[pid3]["last_aborted"] == e3["aborted"] and lst[pid3]["last_re_adopted"] == e3["re_adopted"] and lst[pid3]["last_settled"] == "", lst[pid3])
e2 = {e["type"]: e["ts"] for e in events(pid2)}
check("... settled project reports last_settled only", lst[pid2]["last_settled"] == e2["settled"] and lst[pid2]["last_aborted"] == "" and lst[pid2]["last_re_adopted"] == "", lst[pid2])
check("/projects stays content-free", not any(k in ("intent", "note", "manifest") for k in lst[pid3]), list(lst[pid3]))

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
