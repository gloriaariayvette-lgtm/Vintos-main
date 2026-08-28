#!/usr/bin/env python3
"""The consumer door: a tactical act must not become a value one cron later.

evidence_provenance protects the write. These assert the read — including
transitively, which is the part that actually bites: a want derived from a
tactical turn is not less dangerous than the turn.
"""
import os, sys, json, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"))
import evidence_view as EV

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:70]) if d else ""))

ORD = {"generation_provenance": {"output_provenance": "ordinary_generation", "may_witness": True}}
TAC = {"generation_provenance": {"output_provenance": "stratagem_influenced", "may_witness": False}}
BAD = {"generation_provenance": "not an object"}

def rec(name, base=None, **kw):
    r = dict(base or {}); r.update(kw); r["turn_id"] = name; return r

ordinary = rec("ord", ORD, content="an ordinary turn")
tactical = rec("tac", TAC, content="a tactical act")
legacy   = rec("leg", content="a pre-envelope turn")
broken   = rec("bad", BAD, content="a malformed envelope")

print("--- standing of one record ---")
check("ordinary is eligible", EV.eligibility(ordinary) == EV.ELIGIBLE)
check("tactical is ineligible", EV.eligibility(tactical) == EV.INELIGIBLE)
check("pre-envelope stays ordinary", EV.eligibility(legacy) == EV.ELIGIBLE)
check("malformed is HELD, not ordinary", EV.eligibility(broken) == EV.HELD)
check("a non-record is HELD", EV.eligibility("nonsense") == EV.HELD)

print("\n--- the two views ---")
all4 = [ordinary, tactical, legacy, broken]
check("record_view keeps everything", len(EV.record_view(all4)) == 4)
check("record_view keeps his tactical act",
      any(r["turn_id"] == "tac" for r in EV.record_view(all4)))
w = EV.witness_view(all4)
check("witness_view drops the tactical act", not any(r["turn_id"] == "tac" for r in w))
check("witness_view drops the malformed one", not any(r["turn_id"] == "bad" for r in w))
check("witness_view keeps the ordinary ones", {r["turn_id"] for r in w} == {"ord", "leg"})
check("witness_view is a subset of record_view", len(w) < len(EV.record_view(all4)))
check("HELD is surfaced, not lost", [r["turn_id"] for r in EV.held(all4)] == ["bad"])

print("\n--- derived records inherit the least-eligible ancestor ---")
value = EV.derive({"kind": "value", "text": "I care about X"}, [ordinary, tactical])
check("a value built on a tactical turn is not eligible",
      value["evidence_standing"] == EV.INELIGIBLE, value["evidence_standing"])
check("and says so in its own provenance",
      value["generation_provenance"]["may_witness"] is False)
clean = EV.derive({"kind": "value", "text": "I care about Y"}, [ordinary, legacy])
check("a value built only on ordinary turns stays eligible",
      clean["evidence_standing"] == EV.ELIGIBLE)
check("a value with a HELD ancestor is HELD",
      EV.derive({"kind": "value"}, [ordinary, broken])["evidence_standing"] == EV.HELD)

print("\n--- transitively, which is the part that bites ---")
want = EV.derive({"kind": "want"}, [value])
check("a want derived from that value is still not eligible",
      want["evidence_standing"] == EV.INELIGIBLE, want["evidence_standing"])
ident = EV.derive({"kind": "self_model_line"}, [want])
check("an identity line three hops down is still not eligible",
      ident["evidence_standing"] == EV.INELIGIBLE)
check("none of them pass witness_view",
      EV.witness_view([value, want, ident]) == [])

print("\n--- lineage that cannot be resolved is HELD, not innocent ---")
orphan = rec("orphan", ORD, derived_from=[{"turn_id": "vanished"}])
check("an unresolvable ancestor is HELD", EV.standing(orphan) == EV.HELD)
check("resolving it restores its real standing",
      EV.standing(orphan, resolve=lambda r: tactical) == EV.INELIGIBLE)
check("malformed lineage is HELD",
      EV.standing(rec("m", ORD, derived_from="not a list")) == EV.HELD)
a = rec("a", ORD); b = rec("b", ORD, derived_from=[{"turn_id": "a"}])
a["derived_from"] = [{"turn_id": "b"}]
check("a lineage cycle is HELD",
      EV.standing(a, resolve=lambda r: b if r.get("turn_id") == "b" else a) == EV.HELD)

print("\n--- the door itself ---")
TMP = tempfile.mkdtemp(prefix="evview-")
p = os.path.join(TMP, "chat-history-merged.json")
json.dump(all4, open(p, "w"))
check("the guarded files are named", EV.is_guarded(p))
check("open_history defaults to the SAFE view",
      {r["turn_id"] for r in EV.open_history(p)} == {"ord", "leg"})
check("the exact history is still reachable on request",
      len(EV.open_history(p, view="record")) == 4)
try:
    EV.open_history(p, view="everything")
    check("a nonsense view is refused", False)
except ValueError:
    check("a nonsense view is refused", True)
try:
    EV.refuse_raw(p); check("raw access to a guarded file is refused", False)
except EV.NotADoor:
    check("raw access to a guarded file is refused", True)
check("an ordinary file is not obstructed", EV.refuse_raw(os.path.join(TMP, "notes.json")))
jl = os.path.join(TMP, "imprints.jsonl")
open(jl, "w").write("\n".join(json.dumps(r) for r in all4))
check("jsonl evidence reads through the same door",
      {r["turn_id"] for r in EV.open_history(jl)} == {"ord", "leg"})
check("a missing file is empty, not a crash",
      EV.open_history(os.path.join(TMP, "gone.json")) == [])
shutil.rmtree(TMP, ignore_errors=True)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
