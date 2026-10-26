#!/usr/bin/env python3
"""Two retained readings that disagree, their incompatible predictions frozen, and one local measurement that says
which - if either - it supports (Codex's proposal 11).

Scratch HOME, scratch workspace, scratch Lab: every store this suite touches is under a temporary directory and is
asserted to be. The divergence row is written here by hand; no reader is called, the paid ledger refuses to be
touched, sockets are closed off and `requests` and the plugin gateway raise.
"""
import json, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="vintos-disagreement-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")


def _no_network(*a, **k):
    raise AssertionError("a test must never reach the network")


def _no_paid(*a, **k):
    raise AssertionError("a disagreement never reserves or spends a paid reading")


def _no_socket(self, *a, **k):
    raise AssertionError("a test must never open a socket")


socket.socket.connect = _no_socket
sys.modules["requests"] = types.SimpleNamespace(get=_no_network, post=_no_network)
sys.modules["plugin_gateway"] = types.SimpleNamespace(run_skill=_no_network, call=_no_network)
sys.modules["compute_admission"] = types.SimpleNamespace(reserve_paid=_no_paid, release_paid=_no_paid,
                                                          admit=_no_paid)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import lab_measurement as M
import lab_disagreement as D

R = []


def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:500]) if detail and not ok else ""))


def refuses(name, call, kinds=(ValueError,)):
    try:
        call()
        check("refused: " + name, False, "it was allowed")
    except kinds as exc:
        check("refused: " + name, True, exc)
    except Exception as exc:                     # noqa: BLE001 - a wrong error type is a failure, not a pass
        check("refused: " + name, False, "%s: %s" % (type(exc).__name__, exc))


# ---------------------------------------------------------------- isolation
LAB = str(D.lab_root())
check("the divergence, disagreement, verdict and measurement stores are all in the scratch workspace",
      all(str(p).startswith(HOME) for p in (D.divergence_path(), D.disagreements_path(), D.verdicts_path(),
                                            M.contracts_path(), M.results_path())),
      (D.divergence_path(), D.disagreements_path()))
check("the disagreement and the measurement read and write the same Lab directory", LAB == M._root(), (LAB, M._root()))
check("nothing in this suite can send, fetch or spend",
      sys.modules["requests"].get is _no_network and sys.modules["compute_admission"].reserve_paid is _no_paid)

# ---------------------------------------------------------------- a retained divergence row, written by hand
ASTRA = ("Most of the chain sits in confident helix; I expect the model to be well determined across the core, "
         "with mean confidence comfortably high.")
GROK = ("The loop between the two helices looks unresolved to me; I would bet the whole model is weakly "
        "determined, a low-confidence prediction overall.")
ROW = {"session_id": "CHEM-000000000001-D", "at": "2026-09-27T08:21:03+00:00", "mode": "divergence",
       "state": "completed_with_held_lenses", "read_of": "20260927-031945-aaaa", "experiment": "protein",
       "identical_prompt_sha256": "f" * 64,
       "readings": [{"lens": "astra", "state": "read", "question": "Is the core well determined?",
                     "why_this": "the helices", "what_you_notice": ASTRA},
                    {"lens": "grok", "state": "read", "question": "Is the loop resolved?",
                     "why_this": "the loop", "what_you_notice": GROK},
                    {"lens": "opus", "state": "held", "error": "TimeoutError"},
                    {"lens": "fable", "state": "read", "question": "", "why_this": "", "what_you_notice": ""}],
       "agreement": "not_computed", "truth_status": "independent_readings_no_consensus_claim"}
os.makedirs(LAB, exist_ok=True)
with open(D.divergence_path(), "w") as f:
    f.write(json.dumps(ROW) + "\n")
    f.write(json.dumps(dict(ROW, session_id="CHEM-000000000002-D",
                            readings=[ROW["readings"][0], ROW["readings"][2]])) + "\n")

found = D.pairs()
check("a retained pair is a divergence row where two lenses actually read; a held or empty lens is not one",
      [p["divergence"] for p in found] == ["CHEM-000000000001-D"] and found[0]["lenses"] == ["astra", "grok"], found)

GOOD = {"divergence": "CHEM-000000000001-D", "variable": "mean per-residue confidence of the retained model",
        "units": "pLDDT",
        "predictions": {"astra": {"predicts": {"above": 80}, "basis": "with mean confidence comfortably high"},
                        "grok": {"predicts": {"below": 65}, "basis": "a low-confidence prediction overall"}}}


def variant(**over):
    raw = json.loads(json.dumps(GOOD))
    for key, value in over.items():
        if key in ("astra", "grok"):
            raw["predictions"][key].update(value)
        else:
            raw[key] = value
    return raw


T0, T1, T2 = "2026-10-26T10:00:00+00:00", "2026-10-26T12:00:00+00:00", "2026-10-26T09:00:00+00:00"

# ---------------------------------------------------------------- what may be declared
refuses("a lens that was held, not read", lambda: D.declare(variant(predictions={
    "astra": GOOD["predictions"]["astra"], "opus": {"predicts": {"below": 65}, "basis": "anything at all here ok"}}),
    now=T0))
refuses("a lens whose reading is empty", lambda: D.declare(variant(predictions={
    "astra": GOOD["predictions"]["astra"], "fable": {"predicts": {"below": 65}, "basis": "anything at all here ok"}}),
    now=T0))
refuses("a basis the lens never wrote (a prediction is grounded in its own words)",
        lambda: D.declare(variant(grok={"basis": "the model is plainly unreliable everywhere"}), now=T0))
refuses("a basis too short to be a reason", lambda: D.declare(variant(grok={"basis": "low"}), now=T0))
refuses("two predictions that overlap: a value satisfying both is no disagreement",
        lambda: D.declare(variant(grok={"predicts": {"below": 85}}), now=T0))
refuses("between ranges that overlap", lambda: D.declare(variant(astra={"predicts": {"between": [60, 90]}},
                                                                 grok={"predicts": {"between": [50, 70]}}), now=T0))
refuses("both predictions quoting the same words",
        lambda: D.declare(variant(grok={"basis": "with mean confidence comfortably high"}), now=T0))
refuses("predictions without units", lambda: D.declare(variant(units=""), now=T0))
refuses("one lens is not a disagreement", lambda: D.declare(variant(predictions={
    "astra": GOOD["predictions"]["astra"]}), now=T0))
refuses("a prediction in words rather than numbers", lambda: D.declare(variant(grok={"predicts": {"below": "low"}}),
                                                                       now=T0))
refuses("a divergence the Lab does not have", lambda: D.declare(variant(divergence="CHEM-nope"), now=T0))
check("nothing refused was written", D.disagreements() == [], D.disagreements())

dis = D.declare(GOOD, now=T0, today="2026-10-26")
DIS = dis["disagreement_id"]
check("a declared disagreement is frozen with its predictions, each lens's reading digested",
      DIS.startswith("DIS-") and dis["predictions"]["grok"]["predicts"] == {"below": 65.0}
      and len(dis["predictions"]["astra"]["reading_sha256"]) == 64
      and dis["identical_prompt_sha256"] == "f" * 64 and dis["read_of"] == ROW["read_of"], dis)
check("the threshold that separates them is recorded", dis["threshold_between"] == 72.5, dis["threshold_between"])
check("the same declaration twice is the same disagreement, written once",
      D.declare(GOOD, now=T1, today="2026-10-26")["disagreement_id"] == DIS and len(D.disagreements()) == 1)
check("touching boundaries are not an overlap (below 70 and above 70 can be separated)",
      not D.overlap((float("-inf"), 70.0), (70.0, float("inf"))))

# ---------------------------------------------------------------- the deterministic judgement
P = dis["predictions"]
v, who, states, why = D.judge(60.0, 2.0, P)
check("a value inside one prediction and outside the other supports that one",
      v == "supports_one" and who == "grok" and states == {"astra": "contradicted", "grok": "consistent"}, (v, states))
v, who, states, why = D.judge(72.0, 1.0, P)
check("a value outside both supports neither", v == "supports_neither" and who is None, (v, states))
v, who, states, why = D.judge(72.0, 10.0, P)
check("an interval reaching into both ranges is inconclusive, and says the measurement accommodates both",
      v == "inconclusive" and "accommodates both" in why, (v, why))
v, who, states, why = D.judge(82.0, 3.0, P)
check("an interval straddling one boundary is inconclusive", v == "inconclusive" and states["astra"] == "undecided",
      (v, states))
v, _, states, _ = D.judge(65.0, 0.0, P)
check("a value exactly at an open boundary is not below it", states["grok"] == "contradicted", states)

# ---------------------------------------------------------------- the measurement contract carries the id
check("the measurement contract keeps a well-formed disagreement id",
      M.normalize({"mode": "exploratory", "hypothesis": "h", "disagreement": DIS})[0].get("disagreement") == DIS)
c, errs = M.normalize({"mode": "exploratory", "hypothesis": "h", "disagreement": "DIS-; rm -rf"})
check("a malformed id is refused, not kept", "disagreement" not in c and errs, (c, errs))
check("a contract without one is exactly what it was before",
      "disagreement" not in M.normalize({"mode": "exploratory", "hypothesis": "h"})[0])


def output(sid, payload, tool="instrument:fold_read", route="instrument", state="completed"):
    step = {"id": sid, "route": route, "tool": tool, "state": state}
    if state == "completed":
        rel = "investigation-outputs/%s.json" % sid
        path = os.path.join(M._root(), rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(payload, open(path, "w"))
        step.update(output_file=rel, output_sha256=M._sha(payload))
    else:
        step["error"] = "the instrument timed out"
    return step


def contract(dis_id, units="pLDDT", evaluator="structural_measure", **over):
    c = {"mode": "confirmatory", "hypothesis": "the retained model is well determined overall", "unit": "model",
         "variable": "mean pLDDT", "units": units, "evaluator": evaluator, "predicts": "above", "threshold": 72.5,
         "uncertainty": 0, "supports": "mean above 72.5", "opposes": "mean at or below 72.5",
         "measure": {"select": {"tool": "fold_read", "nth": 1}, "value": ["result", "mean_plddt"],
                     "uncertainty_field": ["result", "sd_of_mean"], "meaning": "mean confidence of the model"},
         "disagreement": dis_id}
    c.update(over)
    return c


def measure(inv_id, dis_id, steps, now=T1, existing=(), **kw):
    row = M.freeze(contract(dis_id, **kw), by="gemma", investigation_id=inv_id, existing_steps=existing, now=now)
    M.settle({"id": inv_id, "state": "open", "steps": steps}, now=now)
    return row


# a measurement frozen after the disagreement, of an output produced after it: grok's prediction is supported
measure("INV-1", DIS, [output("s1", {"result": {"mean_plddt": 58.4, "sd_of_mean": 1.2}})])
got = D.verdicts(DIS)
check("the ordinary measurement result is judged against the frozen predictions as soon as it settles",
      len(got) == 1 and got[0]["verdict"] == "supports_one" and got[0]["supports"] == "grok"
      and got[0]["measured"] == {"value": 58.4, "uncertainty": 1.2, "units": "pLDDT"}, got)
check("the verdict is bound to the contract revision and the output it measured",
      got[0]["contract_id"] and got[0]["revision"] == 1 and got[0]["bound"][0]["step"] == "s1"
      and got[0]["bound"][0]["output_sha256"], got[0])
check("the measurement result itself names the disagreement it was chosen for",
      [r.get("disagreement") for r in M.results()] == [DIS])
check("a decisive verdict settles the disagreement", D.state(DIS) == "settled")
check("settling again adds nothing", D.settle() == [] and len(D.verdicts(DIS)) == 1)
check("the verdict says what it is: a computed fit to frozen predictions, not which reader is right in general",
      "not which reader is right in general" in got[0]["truth_status"])

# ---------------------------------------------------------------- what cannot adjudicate
dis2 = D.declare(variant(astra={"predicts": {"above": 75}}), now=T0, today="2026-10-26")
DIS2 = dis2["disagreement_id"]
refuses("a third disagreement on one day", lambda: D.declare(variant(astra={"predicts": {"above": 90}}), now=T0,
                                                             today="2026-10-26"), kinds=(PermissionError,))

# a post-hoc measurement: the output existed before the contract was frozen
pre = output("p1", {"result": {"mean_plddt": 50.0, "sd_of_mean": 0.5}})
row = M.freeze(dict(contract(DIS2), measure=dict(contract(DIS2)["measure"], select={"step": "p1"})), by="gemma",
               investigation_id="INV-2", existing_steps=["p1"], now=T1)
M.settle({"id": "INV-2", "state": "open", "steps": [pre]}, now=T1)
last = D.verdicts(DIS2)[-1]
check("a measurement of an output that existed before it was frozen cannot adjudicate",
      last["verdict"] == "not_evaluated" and "existed before" in last["why"], last)

# a failed tool says nothing about either reader
M.freeze(contract(DIS2), by="gemma", investigation_id="INV-3", now=T1)
M.settle({"id": "INV-3", "state": "closed", "steps": [output("f1", None, state="failed")]}, now=T1)
last = D.verdicts(DIS2)[-1]
check("a tool that produced nothing is not evidence against either reader",
      last["verdict"] == "not_evaluated" and "says nothing about" in last["why"], last)

measure("INV-4", DIS2, [output("u1", {"result": {"mean_plddt": 58.0, "sd_of_mean": 1.0}})], units="percent")
last = D.verdicts(DIS2)[-1]
check("a measurement in other units than the predictions cannot judge them",
      last["verdict"] == "not_evaluated" and "percent" in last["why"], last)

measure("INV-5", DIS2, [output("e1", {"result": {"mean_plddt": 58.0, "sd_of_mean": 1.0}})], now=T2)
last = D.verdicts(DIS2)[-1]
check("a measurement frozen before the disagreement was declared was not chosen to separate it",
      last["verdict"] == "not_evaluated" and "before the disagreement" in last["why"], last)
check("none of these used up a measurement or settled anything", D.state(DIS2) == "open")

# three inconclusive measurements exhaust it: measuring until one side wins is not discrimination
for i in range(3):
    measure("INV-W%d" % i, DIS2, [output("w%d" % i, {"result": {"mean_plddt": 70.0, "sd_of_mean": 8.0}})])
check("an interval reaching into both predictions is inconclusive",
      [r["verdict"] for r in D.verdicts(DIS2)][-3:] == ["inconclusive"] * 3)
check("after %d inconclusive measurements the disagreement is exhausted, not measured again" % D.MAX_MEASUREMENTS,
      D.state(DIS2) == "exhausted")
measure("INV-W9", DIS2, [output("w9", {"result": {"mean_plddt": 40.0, "sd_of_mean": 1.0}})])
check("a fourth measurement after exhaustion is not judged", D.state(DIS2) == "exhausted"
      and all(r.get("supports") is None for r in D.verdicts(DIS2)))

# a retained reading that changes underneath the record
dis3 = D.declare(variant(astra={"predicts": {"above": 77}}), now=T0, today="2026-10-27")
DIS3 = dis3["disagreement_id"]
rows = [json.loads(l) for l in open(D.divergence_path())]
rows[0]["readings"][1]["what_you_notice"] = GROK + " (edited later)"
with open(D.divergence_path(), "w") as f:
    f.write("".join(json.dumps(r) + "\n" for r in rows))
measure("INV-6", DIS3, [output("c1", {"result": {"mean_plddt": 50.0, "sd_of_mean": 1.0}})])
last = D.verdicts(DIS3)[-1]
check("a reading changed since the disagreement was frozen judges nothing",
      last["verdict"] == "not_evaluated" and "changed" in last["why"], last)

fake = D.adjudicate(dis3, {"contract_id": "MC-x", "revision": 1, "frozen_at": T1,
                           "contract": {"evaluator": "proportion_vs_control", "units": "pLDDT"}},
                    {"execution_state": "completed", "measurement_state": "supported", "confirmatory": True,
                     "estimate": {"difference": 0.4}})
check("a proportion against a control is not one measured value and cannot judge two predicted values",
      fake["verdict"] == "not_evaluated" and "one measured value" in fake["why"], fake)

# ---------------------------------------------------------------- what the investigation planner is shown
view = M.planner_view({"id": "INV-NEW", "state": "open", "steps": []})
shown = (view or {}).get("disagreements") or {}
check("the planner is shown the open disagreements, with the separating threshold and how to bind a measurement",
      [d["id"] for d in shown.get("open", [])] == [DIS3] and shown["open"][0]["separating_threshold"] == 71.0
      and "disagreement" in shown.get("how", "") and "no fold" in shown.get("how", ""), shown)
check("a settled or exhausted disagreement is not offered again",
      DIS not in json.dumps(shown.get("open")) and DIS2 not in json.dumps(shown.get("open")))
check("and the latest verdict is in front of it", (shown.get("last_verdict") or {}).get("verdict") in
      ("supports_one", "supports_neither", "inconclusive"), shown.get("last_verdict"))
check("how to write a contract is shown beside it", "measurement (optional" in (view or {}).get("how", ""))
check("the planner view fits in a small prompt", len(json.dumps(shown)) < 1500, len(json.dumps(shown)))

# ---------------------------------------------------------------- what it never touches
check("no reader was called and the multi-reader session was never loaded",
      "chemistry_session" not in sys.modules and "lab_investigations" not in sys.modules)
check("the divergence store was only read: still the two rows written here",
      len(open(D.divergence_path()).read().splitlines()) == 2)
check("display names each prediction with its own words and every measurement",
      any("from its own words" in line for line in D.display(D.disagreement(DIS)))
      and any("supports_one (grok)" in line for line in D.display(D.disagreement(DIS))))

print("%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
