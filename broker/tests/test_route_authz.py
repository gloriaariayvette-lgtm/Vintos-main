#!/usr/bin/env python3
"""The Atelier seal, at the door rather than inside each room.

Sol's P0: /artifact returned sealed content to anyone, /visit/open handed
sealed material to any caller who wrote as="gloria", and /reveal/confirm
consumed nothing, so an unveiling could be declared without ever happening.
These assert the matrix, not the individual routes.
"""
import os, sys, json, tempfile, shutil, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import broker as BK

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:70]) if d else ""))

TMP = tempfile.mkdtemp(prefix="authz-")
BK.ROOT = TMP
BK.HEALTH = os.path.join(TMP, "health.jsonl")
BK._KEYPATH = os.path.join(TMP, ".visit-key")
os.makedirs(os.path.join(TMP, "projects"))

pid = BK.create_project({"intent": "mine", "sealed": True})["id"]
BK.to_table({"id": pid})

print("--- every route is a decision ---")
check("no route is unlisted", set(BK.ROUTES) - set(BK.POLICY) == set(),
      sorted(set(BK.ROUTES) - set(BK.POLICY)))
check("an invented door is refused", authz := (BK.authorize_route("/backdoor", {"id": pid})[0] is False))
check("a policy entry with no handler is refused",
      BK.authorize_route("/nope", {}) == (False, "unknown door"))

print("\n--- sealed content needs the ceremony ---")
ok, why = BK.authorize_route("/artifact", {"id": pid, "file": "x.md"})
check("/artifact with no capability is refused", not ok, why)
ok, why = BK.authorize_route("/make", {"id": pid, "kind": "write", "content": "c"})
check("/make with no capability is refused", not ok, why)
ok, why = BK.authorize_route("/handoff", {"id": pid, "text": "t"})
check("/handoff with no capability is refused", not ok, why)
check("a stop is never gated", BK.authorize_route("/stratagem/strategy-stop", {})[0])
check("the content-free door stays open", BK.authorize_route("/door", {})[0])

print("\n--- a real capability opens exactly its own project ---")
other = BK.create_project({"intent": "another", "sealed": True})["id"]
op = BK.open_visit({"id": pid})
cap = op["visit_capability"]
check("/visit/open mints one", bool(cap))
check("capability opens its own project", BK.authorize_route("/make", {"id": pid, "visit_capability": cap})[0])
ok, why = BK.authorize_route("/make", {"id": other, "visit_capability": cap})
check("capability does not cross to another project", not ok, why)
forged = json.loads(json.dumps(cap)); forged["sig"] = "0" * 64
ok, why = BK.authorize_route("/make", {"id": pid, "visit_capability": forged})
check("a forged signature is refused", not ok, why)

print("\n--- Gloria sees that he works, not what he made ---")
g = BK.open_visit({"id": pid, "as": "gloria"})
check("no intent leaks pre-reveal", "intent" not in g, g)
check("no artifact list leaks pre-reveal", "artifacts" not in g)
check("no handoff leaks pre-reveal", "handoff" not in g)
check("she is told it is sealed", g.get("sealed") is True)
check("his footprint is still recorded", g.get("footprint_recorded") is True)
check("the footprint really was written",
      len(json.load(open(os.path.join(BK._p(pid), "project.json")))["footprints"]) == 1)

print("\n--- unveiling is a transaction, not an announcement ---")
BK.open_visit({"id": pid})
BK.make({"id": pid, "kind": "write", "content": "the thing itself"})
art = sorted(os.listdir(os.path.join(BK._p(pid), "artifacts")))[0]
check("confirm before prepare is refused",
      "error" in BK.reveal_confirm({"id": pid, "receipt": {"nonce": "x"}}))
prep = BK.reveal_prepare({"id": pid, "artifact": art})
check("prepare mints a receipt", bool(prep["receipt"]["nonce"]))
check("a wrong receipt is refused",
      "error" in BK.reveal_confirm({"id": pid, "receipt": {"nonce": "deadbeef"}}))
check("still not revealed after a refused confirm",
      json.load(open(os.path.join(BK._p(pid), "project.json")))["visibility"] != "revealed")
done = BK.reveal_confirm({"id": pid, "receipt": prep["receipt"]})
check("the right receipt confirms", done.get("ok"), done)
check("confirm hands back an export capability", bool(done.get("export_capability")))
check("the receipt is one-use",
      "error" in BK.reveal_confirm({"id": pid, "receipt": prep["receipt"]}))

print("\n--- export is bound to what was actually revealed ---")
ec = done["export_capability"]
check("revealed artifact travels on the export capability",
      BK.authorize_route("/artifact", {"id": pid, "file": art, "export_capability": ec})[0])
ok, why = BK.authorize_route("/artifact", {"id": pid, "file": "other.md", "export_capability": ec})
check("a different file does not", not ok, why)
ok, why = BK.authorize_route("/artifact", {"id": other, "file": art, "export_capability": ec})
check("another project does not", not ok, why)

print("\n--- a swapped artifact fails the manifest ---")
p2 = BK.create_project({"intent": "swap", "sealed": True})["id"]
BK.to_table({"id": p2}) if False else None
a2 = BK._j(os.path.join(BK.ROOT, "active.json"), {})
BK._w(os.path.join(BK.ROOT, "active.json"), {"id": p2})
BK.set_state({"id": p2, "state": "ACTIVE"})
BK.open_visit({"id": p2})
BK.make({"id": p2, "kind": "write", "content": "original"})
f2 = sorted(os.listdir(os.path.join(BK._p(p2), "artifacts")))[0]
pr2 = BK.reveal_prepare({"id": p2, "artifact": f2})
open(os.path.join(BK._p(p2), "reveal", f2), "w").write("substituted after preparation")
out = BK.reveal_confirm({"id": p2, "receipt": pr2["receipt"]})
check("a substituted artifact cannot be confirmed", "error" in out, out)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
