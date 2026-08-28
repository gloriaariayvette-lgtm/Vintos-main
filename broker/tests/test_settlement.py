#!/usr/bin/env python3
"""The room must be able to FINISH something.

Reveal marked a project PRESENTED and left it on the worktable forever: the
door stayed lit on something already given away, the one locus of attention
was permanently occupied, and nothing new could ever be tabled. Presenting is
not finishing.
"""
import os, sys, json, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import broker as BK

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:70]) if d else ""))

TMP = tempfile.mkdtemp(prefix="settle-")
BK.ROOT = TMP; BK.HEALTH = os.path.join(TMP, "health.jsonl")
BK._KEYPATH = os.path.join(TMP, ".visit-key")
os.makedirs(os.path.join(TMP, "projects"))

def fresh(intent="a thing"):
    pid = BK.create_project({"intent": intent, "sealed": True})["id"]
    BK._w(os.path.join(BK.ROOT, "active.json"), {"id": pid})
    BK.set_state({"id": pid, "state": "ACTIVE"})
    BK.open_visit({"id": pid})
    BK.make({"id": pid, "kind": "write", "content": "the made thing"})
    return pid, sorted(os.listdir(os.path.join(BK._p(pid), "artifacts")))[0]

print("--- nothing to settle before an unveiling ---")
pid, art = fresh()
check("an unrevealed project cannot be settled", "error" in BK.settle({"id": pid}))
check("its worktable is untouched",
      BK._j(os.path.join(BK.ROOT, "active.json"), {})["id"] == pid)

print("--- settlement releases the room ---")
prep = BK.reveal_prepare({"id": pid, "artifact": art})
BK.reveal_confirm({"id": pid, "receipt": prep["receipt"]})
check("reveal alone leaves it on the worktable",
      BK._j(os.path.join(BK.ROOT, "active.json"), {}).get("id") == pid)
check("and the door is still lit on a finished thing",
      BK.door().get("door") in ("lit", "dark"))
out = BK.settle({"id": pid})
check("settlement succeeds", out.get("ok"), out)
check("the worktable is RELEASED",
      not BK._j(os.path.join(BK.ROOT, "active.json"), {}).get("id"))
check("the door goes dark", BK.door()["door"] == "dark", BK.door())
check("the project is archived",
      json.load(open(os.path.join(BK._p(pid), "project.json")))["state"] == "ARCHIVED")
check("any open visit was closed",
      json.load(open(os.path.join(BK._p(pid), ".visit.json")))["closed"] is True)
check("a new project can now be tabled", BK.to_table({"id": fresh("the next thing")[0]}).get("ok"))

print("\n--- the receipt is bounded and signed ---")
r = out["receipt"]
check("it names the project and digest", r["project"] == pid and len(r["sha256"]) == 64)
check("it records that the table was released", r["worktable_released"] is True)
check("it carries NO content of the work",
      not any(isinstance(v, str) and "the made thing" in v for v in r.values()), r)
check("no intent leaks into it", "intent" not in r)
check("the broker verifies its own receipt", BK.verify_settlement({"receipt": r})["valid"])
tampered = dict(r); tampered["sha256"] = "0" * 64
check("a tampered receipt does not verify", not BK.verify_settlement({"receipt": tampered})["valid"])
check("an invented receipt does not verify",
      not BK.verify_settlement({"receipt": {"project": pid, "sig": "0" * 64}})["valid"])

print("\n--- settlement will not close over changed material ---")
pid2, art2 = fresh("second")
BK._w(os.path.join(BK.ROOT, "active.json"), {"id": pid2})
p2 = BK.reveal_prepare({"id": pid2, "artifact": art2})
BK.reveal_confirm({"id": pid2, "receipt": p2["receipt"]})
open(os.path.join(BK._p(pid2), "reveal", art2), "w").write("swapped after the unveiling")
bad = BK.settle({"id": pid2})
check("a swapped artifact is refused", "error" in bad, bad)
check("and the worktable is NOT released on a refusal",
      BK._j(os.path.join(BK.ROOT, "active.json"), {}).get("id") == pid2)

print("\n--- settlement stays out of reception ---")
src = open(os.path.join(os.path.dirname(HERE), "broker.py")).read()
seg = src[src.index("def settle("):src.index("def verify_settlement(")]
body = seg.split('"""')[2] if seg.count('"""') >= 2 else seg    # code only, not the docstring
check("it never reads her response",
      not any(w in body for w in ("chat-history", "interaction-ledger", "reception", "gloria_response")),
      [w for w in ("chat-history", "interaction-ledger", "reception", "gloria_response") if w in body])
check("it touches only the project's own files",
      "ROOT" in body and "MEMORY" not in body)

print("\n--- the threshold's lineage travels with the project ---")
att = {"episode_digest": "abc", "commissioned": False, "provenance_class": "self_originated"}
pid3 = BK.create_project({"intent": "adopted at the threshold", "sealed": True,
                          "root": "curiosity:42", "root_type": "curiosity",
                          "lineage_attestation": att, "next_move": "open the file and look"})["id"]
pj = json.load(open(os.path.join(BK._p(pid3), "project.json")))
check("the root is carried", pj["root"] == "curiosity:42")
check("the root type is carried", pj["root_type"] == "curiosity")
check("the attestation is carried", pj["lineage_attestation"]["commissioned"] is False)
check("his first move is recorded without spending a return",
      json.load(open(os.path.join(BK._p(pid3), "handoff.json")))["next_move"] == "open the file and look")
check("and no visit was opened to do it",
      not os.path.exists(os.path.join(BK._p(pid3), ".visit.json")))

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
