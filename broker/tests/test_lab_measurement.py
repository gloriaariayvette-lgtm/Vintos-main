#!/usr/bin/env python3
"""A scientific claim with a way to fail (Codex's design 04): a frozen measurement contract judges an output by its
own fields, and execution, measurement and novelty stay separate facts.

Scratch HOME and workspace; every output is an invented fixture; sockets are refused; no model is asked."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-measurement-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import lab_measurement as M
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:500],)))

check("its stores are scratch", all(p.startswith(HOME) for p in (M.contracts_path(), M.results_path())),
      (M.contracts_path(), M.results_path()))
NOW = "2026-10-26T12:00:00+00:00"


def output(sid, payload, route="instrument", tool="instrument:rt_locus_screen", state="completed", **extra):
    """An investigation step with a retained output, hashed the way lab_investigations hashes it."""
    step = {"id": sid, "route": route, "tool": tool, "state": state, **extra}
    if state == "completed":
        rel = "investigation-outputs/%s.json" % sid
        path = os.path.join(M._root(), rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(payload, open(path, "w"))
        step.update(output_file=rel, output_sha256=M._sha(payload))
    return step


def counts(hits, total, **more):
    return {"result": {"hits": hits, "total": total, **more}}


def role(nth, **kw):
    base = {"select": {"tool": "rt_locus_screen", "nth": nth}, "hits": ["result", "hits"],
            "total": ["result", "total"], "meaning": "loci with an array beside the RT"}
    base.update(kw)
    return base


def proportion(**over):
    c = {"mode": "confirmatory", "hypothesis": "array-adjacent RTs are commoner in phage loci", "unit": "locus",
         "variable": "share of loci with an array", "units": "proportion", "evaluator": "proportion_vs_control",
         "predicts": "case_higher", "min_effect": 0.2, "supports": "case share exceeds control by 0.2",
         "opposes": "the interval rules out a 0.2 excess", "case": role(1), "control": role(2, meaning="matched background")}
    c.update(over)
    return c


def run(inv_id, contract, steps, final=False, existing=()):
    row = M.freeze(contract, by="test", investigation_id=inv_id, existing_steps=existing, now=NOW)
    return row, M.evaluate(row, steps, final=final, now=NOW)


# --- a fixed result with known counts ---------------------------------------------------------------------------------
steps = [output("S-a1", counts(18, 20)), output("S-a2", counts(4, 20))]
row, res = run("I-known", proportion(), steps)
check("a valid contract is frozen with its revision, time and digest",
      row["status"] == "frozen" and row["revision"] == 1 and row["frozen_at"] == NOW and len(row["contract_sha256"]) == 64,
      row)
check("18/20 against 4/20 supports a predicted excess of 0.2",
      res["measurement_state"] == "supported" and res["estimate"]["difference"] == 0.7 and res["estimate"]["ci95"][0] > 0.2,
      res)
check("execution, measurement, novelty and truth are separate facts",
      res["execution_state"] == "completed" and res["novelty_state"] == "candidate_computational_finding"
      and "not experimental biological validation" in res["truth_status"] and "not a" in res["novelty_note"], res)
check("bound to the output digests, the contract revision and its digest",
      [b["output_sha256"] for b in res["bound"]] == [s["output_sha256"] for s in steps]
      and res["contract_sha256"] == row["contract_sha256"] and res["revision"] == 1, res["bound"])
check("measured on outputs produced after the freeze, it is confirmatory", res["confirmatory"] is True, res)
check("and the Fisher p is computed, not guessed", 0 < res["estimate"]["fisher_p"] < 0.001, res["estimate"])
check("the Newcombe interval matches a hand value", abs(M.newcombe(18, 20, 4, 20)[1] - 0.4049) < 0.001,
      M.newcombe(18, 20, 4, 20))

# --- a null case ------------------------------------------------------------------------------------------------------
steps = [output("S-n1", counts(10, 40)), output("S-n2", counts(10, 40))]
_, res = run("I-null", proportion(), steps)
check("a clean null against a predicted 0.2 excess refutes it, execution still completed",
      res["measurement_state"] == "refuted" and res["execution_state"] == "completed" and res["negative"] is True, res)
_, res0 = run("I-null0", proportion(min_effect=0), steps)
check("with no minimum effect the same null is only inconclusive", res0["measurement_state"] == "inconclusive", res0)

# --- a known positive: reproducing a cited value -----------------------------------------------------------------------
known = {"mode": "confirmatory", "hypothesis": "the fold reproduces the published Cas1 dimer RMSD", "unit": "structure",
         "variable": "C-alpha RMSD to the reference", "units": "angstrom", "evaluator": "reproducibility",
         "predicts": "reproduces", "tolerance": 0.5, "supports": "within 0.5 A", "opposes": "further than 0.5 A",
         "measure": {"select": {"tool": "structure.compare"}, "value": ["result", "rmsd"],
                     "unit_field": ["result", "units"], "meaning": "RMSD after superposition"},
         "reference": {"value": 1.8, "citation": "a published Cas1 structure comparison"}}
steps = [output("S-k1", {"result": {"rmsd": 2.1, "units": "Angstrom"}}, tool="instrument:structure.compare")]
_, res = run("I-known-pos", known, steps)
check("a replicated published value is a reproduced known result, not a discovery",
      res["measurement_state"] == "supported" and res["novelty_state"] == "reproduced_known_result", res)

# --- a missing comparator -----------------------------------------------------------------------------------------------
no_control = proportion(); no_control.pop("control")
row, res = run("I-nocontrol", no_control, [output("S-m1", counts(9, 10))])
check("a proportion with no control is refused at the freeze, with the reason",
      row["status"] == "refused" and any("comparator" in e for e in row["errors"]) and res is None, row)
steps = [output("S-m2", counts(9, 10)), output("S-m3", {"result": {"total": 10}})]
_, res = run("I-nocontrol-out", proportion(), steps)
check("a control output that lacks the named field is not evaluated, never refuted",
      res["measurement_state"] == "not_evaluated" and "not in the output" in res["why"], res)

# --- a changed output hash ----------------------------------------------------------------------------------------------
steps = [output("S-h1", counts(18, 20)), output("S-h2", counts(4, 20))]
row, res = run("I-hash", proportion(), steps)
json.dump(counts(1, 20), open(os.path.join(M._root(), steps[0]["output_file"]), "w"))
check("a result no longer stands once an output it measured changes", M.verify(res, steps) is False)
row2 = M.freeze(proportion(), by="test", investigation_id="I-hash2", now=NOW)
res2 = M.evaluate(row2, steps, now=NOW)
check("and a changed output is never measured", res2["measurement_state"] == "not_evaluated" and "changed" in res2["why"],
      res2)

# --- a unit mismatch ------------------------------------------------------------------------------------------------------
steps = [output("S-u1", {"result": {"rmsd": 0.21, "units": "nm"}}, tool="instrument:structure.compare")]
_, res = run("I-units", known, steps)
check("an output in other units is not compared", res["measurement_state"] == "not_evaluated" and "nm" in res["why"], res)

# --- a wrong cohort -------------------------------------------------------------------------------------------------------
cohort = proportion(cohort_digest="c0ffee" * 4, case=role(1, cohort_field=["cohort"]),
                    control=role(2, cohort_field=["cohort"], meaning="background"))
steps = [output("S-c1", dict(counts(18, 20), cohort="c0ffee" * 4)), output("S-c2", dict(counts(4, 20), cohort="beef" * 6))]
_, res = run("I-cohort", cohort, steps)
check("a control drawn from another cohort is not evaluated",
      res["measurement_state"] == "not_evaluated" and "different cohort" in res["why"], res)

# --- invalid numeric values -----------------------------------------------------------------------------------------------
for name, bad in (("more hits than total", counts(21, 20)), ("a fractional count", counts(2.5, 20)),
                  ("a string", counts("18", 20)), ("NaN", counts(float("nan"), 20)), ("zero total", counts(0, 0))):
    steps = [output("S-v1-" + name[:3], bad), output("S-v2-" + name[:3], counts(4, 20))]
    _, res = run("I-bad-" + name, proportion(), steps)
    check("an invalid value (%s) is not evaluated" % name, res["measurement_state"] == "not_evaluated", res)
for name, bad in (("a string threshold", dict(known, evaluator="structural_measure", predicts="below", threshold="2")),
                  ("code as a field", proportion(case=role(1, hits="result['hits'] * 2"))),
                  ("a criterion with no meaning", proportion(case=role(1, meaning=""))),
                  ("an unknown evaluator", proportion(evaluator="eval"))):
    row = M.freeze(bad, by="test", investigation_id="I-refuse-" + name, now=NOW)
    check("a contract with %s is refused, not run" % name, row["status"] == "refused" and row["errors"], row)

# --- duplicated relatives -------------------------------------------------------------------------------------------------
def loci(spec):
    return {"result": {"loci": [{"votu": v, "array": a} for v, a in spec]}}
rec = lambda nth, meaning: {"select": {"tool": "rt_locus_screen", "nth": nth}, "records": ["result", "loci"],
                            "positive": {"field": ["array"], "is_true": True}, "meaning": meaning}
case = [("v1", True)] * 8 + [("v2", False), ("v3", False)]           # eight copies of one relative
ctrl = [("w%d" % i, i < 2) for i in range(10)]
steps = [output("S-d1", loci(case)), output("S-d2", loci(ctrl))]
_, naive = run("I-dup-naive", proportion(case=rec(1, "phage loci"), control=rec(2, "background")), steps)
_, indep = run("I-dup-indep", proportion(case=rec(1, "phage loci"), control=rec(2, "background"),
                                         independence="one_per_unit", unit_key=["votu"]), steps)
check("counted as records, eight relatives look like a strong excess",
      naive["estimate"]["case"]["hits"] == 8 and naive["measurement_state"] == "supported", naive)
check("one per vOTU, they count once and the excess is not supported",
      indep["estimate"]["case"] == {"hits": 1, "total": 3, "records": 10, "excluded": 0, "units_counted": 3}
      and indep["measurement_state"] != "supported", indep)
_, bare = run("I-dup-bare", proportion(independence="one_per_unit", unit_key=["votu"]),
              [output("S-d3", counts(9, 10)), output("S-d4", counts(1, 10))])
check("bare counts cannot satisfy a one-per-unit contract",
      bare["measurement_state"] == "not_evaluated" and "related" in bare["why"], bare)
missing = loci(case); missing["result"]["loci"].append({"votu": "v9"})
steps = [output("S-d5", missing), output("S-d6", loci(ctrl))]
_, res = run("I-missing", proportion(case=rec(1, "phage loci"), control=rec(2, "background")), steps)
_, res_x = run("I-missing-x", proportion(case=rec(1, "phage loci"), control=rec(2, "background"), missing="exclude"), steps)
check("a record missing its field stops the measurement unless the contract excludes it",
      res["measurement_state"] == "not_evaluated" and res_x["estimate"]["case"]["excluded"] == 1, (res, res_x))

# --- a result that strongly refutes him -----------------------------------------------------------------------------------
steps = [output("S-r1", counts(1, 30)), output("S-r2", counts(25, 30))]
inv_r = {"id": "I-refuted", "state": "open", "steps": steps}
M.freeze(proportion(), by="gemma", investigation_id="I-refuted", now=NOW)
settled = M.settle(inv_r, now=NOW)
check("a strong contradiction is a successful measurement that refutes the prediction",
      len(settled) == 1 and settled[0]["measurement_state"] == "refuted" and settled[0]["execution_state"] == "completed"
      and settled[0]["confirmatory"] is True, settled)
check("it is kept, retrievable as a negative finding", any(r["investigation"] == "I-refuted" for r in M.negatives(10)))
check("and settled once", M.settle(inv_r, now=NOW) == [])
view = M.planner_view({"id": "I-next", "state": "open", "steps": []}, now=NOW)
check("the next investigation's planner is shown it, and how to state a contract",
      any(n["hypothesis"].startswith("array-adjacent") and n["measurement_state"] == "refuted"
          for n in view["your_negative_results"]) and view["how"] == M.SPEC, view)

# --- a failed tool ---------------------------------------------------------------------------------------------------------
failed = [output("S-f1", None, state="failed", error="HTTP 503 from the screen service"),
          output("S-f2", None, state="failed", error="HTTP 503 from the screen service")]
row = M.freeze(proportion(), by="gemma", investigation_id="I-failed", now=NOW)
check("while the investigation is open, a failed tool leaves the contract waiting", M.evaluate(row, failed) is None)
res = M.evaluate(row, failed, final=True, now=NOW)
check("closed on a failed tool: not evaluated, execution failed, never evidence against him",
      res["measurement_state"] == "not_evaluated" and res["execution_state"] == "failed"
      and "says nothing about the hypothesis" in res["why"] and not res.get("negative"), res)
M.settle({"id": "I-failed", "state": "stalled", "steps": failed}, now=NOW)
check("and it is not among his negative results", all(r["investigation"] != "I-failed" for r in M.negatives(20)))

# --- a contract changed after seeing results -------------------------------------------------------------------------------
steps = [output("S-p1", counts(12, 20)), output("S-p2", counts(8, 20))]
inv_p = {"id": "I-posthoc", "state": "open", "steps": steps}
M.freeze(proportion(), by="gemma", investigation_id="I-posthoc", now=NOW)
first = M.settle(inv_p, now=NOW)
check("the first contract is measured on its own terms", first and first[0]["revision"] == 1, first)
loose = proportion(min_effect=0.0, predicts="case_higher", hypothesis="array-adjacent RTs are at least as common")
rev2 = M.freeze(loose, by="gemma", investigation_id="I-posthoc", existing_steps=["S-p1", "S-p2"], now=NOW)
second = M.settle(inv_p, now=NOW)
check("a revision after the result is a new revision marked post hoc",
      rev2["revision"] == 2 and rev2["supersedes"] == 1 and "post_hoc" in rev2, rev2)
check("the outputs it was revised after are not its evidence: it waits for a new holdout", second == [], second)
inv_p["steps"] += [output("S-p3", counts(19, 20)), output("S-p4", counts(3, 20))]
third = M.settle(inv_p, now=NOW)
check("measured on that fresh holdout, the revision is judged and says it was revised after a result",
      third and third[0]["revision"] == 2 and [b["step"] for b in third[0]["bound"]] == ["S-p3", "S-p4"]
      and third[0]["confirmatory"] is True and "post_hoc" in third[0], third)
check("the old prediction's result is not edited", [r for r in M.results() if r["contract_id"] == rev2["contract_id"]
                                                    and r["revision"] == 1] == first)
tampered = dict(rev2, contract=dict(rev2["contract"], min_effect=0.9))
res = M.evaluate(tampered, steps, now=NOW)
check("a contract edited in place after its freeze judges nothing",
      res["measurement_state"] == "not_evaluated" and "changed after it was frozen" in res["why"], res)
row = M.freeze(proportion(), by="test", investigation_id="I-pre", existing_steps=["S-a1", "S-a2"], now=NOW)
res = M.evaluate(row, [output("S-a1", counts(18, 20)), output("S-a2", counts(4, 20))], now=NOW)
check("a contract frozen after its outputs existed does not select them", res is None, res)
row = M.freeze(proportion(case=dict(role(1), select={"step": "S-a1"}), control=dict(role(2), select={"step": "S-a2"})),
               by="test", investigation_id="I-pre2", existing_steps=["S-a1", "S-a2"], now=NOW)
res = M.evaluate(row, [output("S-a1", counts(18, 20)), output("S-a2", counts(4, 20))], now=NOW)
check("named explicitly, they are measured but cannot confirm it",
      res["measurement_state"] == "supported" and res["confirmatory"] is False, res)

# --- the planner door ------------------------------------------------------------------------------------------------------
inv = {"id": "I-door", "line_id": "L-1", "state": "open", "steps": []}
got = M.from_planner(inv, {"route": "instrument", "measurement": proportion()}, now=NOW)
again = M.from_planner(inv, {"route": "instrument", "measurement": proportion()}, now=NOW)
check("the planner's contract is frozen once; restating it adds no revision",
      got["status"] == "frozen" and again["revision"] == 1, (got, again))
bad = M.from_planner(inv, {"measurement": {"hypothesis": "something vague"}}, now=NOW)
check("a vague restatement never displaces the frozen contract",
      bad["revision"] == 1 and bad["status"] == "frozen" and "refused_revision" in bad, bad)
check("no measurement returned: nothing is frozen", M.from_planner(inv, {"route": "source"}) is None)
view = M.planner_view(inv, now=NOW)
check("the planner is shown its frozen contract and the rule against revising it after the fact",
      view["contract"]["status"] == "frozen" and "cannot confirm" in view["rule"], view)
explore = M.freeze({"mode": "exploratory", "hypothesis": "what sits beside these RTs"}, by="gemma",
                   investigation_id="I-explore", now=NOW)
check("exploratory is an honest mode, not a refusal", explore["status"] == "exploratory" and not explore["errors"], explore)
check("and it is never evaluated", M.evaluate(explore, []) is None)
check("a planner view never raises", M.planner_view({"id": None, "steps": None}) is None
      or isinstance(M.planner_view({"id": None, "steps": None}), dict))
check("the evaluators run no code: there is no eval or exec in the module",
      not any(w in open(M.__file__).read() for w in ("eval(", "exec(", "compile(")))

# --- a frontier plan step carries a contract -------------------------------------------------------------------------------
import lab_lines
line = lab_lines.opened_by("RT neighbourhoods", "Do phage RTs sit beside arrays more than background?", "test",
                           origin="test")
plan = [{"objective": "screen phage loci", "route": "instrument", "tool": "rt_locus_screen",
         "success_criteria": "a count", "measurement": dict(known, measure=dict(known["measure"], select={}))}]
n = lab_lines.set_plan(line["id"], plan, "frontier-test")
live = lab_lines.get(line["id"])
fr = [r for r in M.contracts() if r.get("plan_id") == live["plan_id"]]
check("a frontier plan step's contract is frozen with the plan, bound to its id and step",
      n == 1 and live["plan"][0].get("measurement") and fr and fr[0]["step_index"] == 0 and fr[0]["status"] == "frozen", fr)
ps = output("S-fr1", {"result": {"rmsd": 1.7, "units": "angstrom"}}, tool="instrument:structure.compare",
            plan_ref={"line_id": line["id"], "plan_id": live["plan_id"], "step_index": 0})
done = M.settle({"id": "I-frontier", "state": "open", "steps": [ps]}, now=NOW)
check("and the step carried out under that plan is measured by it",
      done and done[0]["measurement_state"] == "supported" and done[0]["investigation"] == "I-frontier", done)
check("the plan's own credit is untouched: done still means the operation completed",
      "measurement" not in str(lab_lines.advance_plan.__doc__) and live["plan"][0]["state"] == "pending")

# --- finding appraisal keeps provenance apart --------------------------------------------------------------------------------
import lab_findings as F
gemma = lambda s, p: ('{"terms": ["x"]}' if '"terms"' in p else
                      '{"novelty": "unclear", "value": 2, "why": "thin", "keep": false, "tell_gloria": false}')
lookup = {"id": "I-lookup", "question": "q", "state": "answered",
          "steps": [{"id": "S-l1", "state": "completed", "route": "source", "tool": "source:pubmed"}]}
row = F.record(lookup, {"factual_observation": "a documented fact"}, gemma, sources=None, now=NOW)
check("a lookup alone is not a new result; it is counted as source retrieval",
      row["new_result"] is False and row["provenance"]["counts"] == {"source_retrieval": 1}, row)
check("the novelty record lists what was searched and is no certificate",
      row["novelty_record"]["certificate"] is False and row["novelty_record"]["searched"][0]["where"] == "Europe PMC titles",
      row["novelty_record"])
computed = {"id": "I-refuted", "question": "q", "state": "answered", "steps": inv_r["steps"]}
asked = []
row = F.record(computed, {"factual_observation": "1 of 30 against 25 of 30"},
               lambda s, p: asked.append(p) or gemma(s, p), sources=None, now=NOW)
check("a computed one is, and it carries its measured contract",
      row["new_result"] is True and row["measurements"] and row["measurements"][0]["measurement_state"] == "refuted", row)
check("the appraisal is told the prediction was refuted, and that this is a result",
      any("refuted" in p and "not a failure" in p for p in asked), asked[-1:])

src = open(os.path.join(REPO, "scripts", "lab_investigations.py")).read()
check("the investigation planner shows the contract only where it fits, and freezes what it returns",
      "planner_view(investigation)" in src and "<= limit" in src and "from_planner(investigation, value)" in src)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
