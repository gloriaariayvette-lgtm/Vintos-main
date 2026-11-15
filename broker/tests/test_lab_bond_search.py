#!/usr/bin/env python3
"""The Lab's bond-length search (lab_bond_search, 14 November 2026).

Every molecule step on record sent the menu's example grid 0.6/0.735/0.9/1.2 A, the textbook minima of H2 and HeH+, so
the Lab found a molecule's minimum only where the textbook had put a point. A planner now writes
"bond_lengths": "search"; the search brackets, refines where the minimum can still be, stops when 95% sure, and says
"not sure" when its budget is spent. Exact mode reads the exact column; measured mode weighs the bench's noise,
including stalled searches past about 1.6 A.

Synthetic curves only (Morse shapes with made-up parameters); scratch HOME and Lab stores; the Mac door is a stub; every
socket is refused. Nothing reaches the Mac."""
import json, math, os, socket, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-lab-bond-search-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
os.environ["VINTOS_CHEMISTRY_MAC_CONFIG"] = os.path.join(HOME, "chemistry-mac.json")
os.environ.pop("LAB_PLANNER_TRIAL", None)
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos.")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no(sock, *a, **k):
    if sock.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))

import numpy as np
import lab_bond_search as S
import lab_experiments as E
import chemistry_lab as lab
import chemistry_mac as mac
import lab_investigations as LI
import lab_planner_trial as T

check("every store is scratch", lab.ROOT.startswith(HOME) and mac.CONFIG.startswith(HOME), (lab.ROOT, mac.CONFIG))


class Curve:
    """A made-up Morse curve: depth D (Ha), stiffness a (1/A), minimum r_e (A), and Hartree-Fock above it by a
    correlation that grows with r."""
    def __init__(self, r_e, D=0.17, a=1.9, e0=-1.5):
        self.r_e, self.D, self.a, self.e0 = r_e, D, a, e0
    def exact(self, r):
        return self.e0 + self.D * (1 - math.exp(-self.a * (r - self.r_e))) ** 2
    def hf(self, r):
        return self.exact(r) + 0.02 + 0.06 * max(0.0, r - self.r_e)
    def e_min(self):
        return self.e0


def drive(curve, exact, seed=0, budget=S.BUDGET, stall_from=None):
    """The search on a synthetic curve, with readings as the bench would give them (measured: the calibrated bias and
    spread, a shared offset; a stalled search reads Hartree-Fock past stall_from). Returns (verdict, estimate, plans)."""
    rng = np.random.default_rng(seed)
    offset = rng.normal(0, 0.001)
    readings, spent, plans = [], 0.0, []
    for step in range(14):
        plan, verdict, est = S.propose(readings, exact, spent, 14 - step, budget=budget)
        if plan is None:
            return verdict, est, plans
        plans.append(plan)
        for b in plan["bond_lengths"]:
            if exact:
                readings.append(S.Reading(b, round(curve.exact(b), 6), True, hf=curve.hf(b)))
                continue
            s, k = plan["vqe_shots"], plan["restarts"]
            bias, sd = S._bias_sd(b, s, k)
            value = curve.exact(b) + bias + offset + rng.normal(0, sd)
            if stall_from is not None and b >= stall_from:
                value = curve.hf(b) + rng.normal(0, 0.001)
            readings.append(S.Reading(b, round(value, 6), False, s, k, hf=curve.hf(b)))
        spent += S.cost(len(plan["bond_lengths"]), exact, plan.get("vqe_shots") or 4096, plan.get("restarts") or 4)
    plan, verdict, est = S.propose(readings, exact, spent, 0, budget=budget)
    return verdict, est, plans


# ---- 1. the menu no longer hands the planner the textbook answer
req = E.EXPERIMENTS["molecule"]["request"]
check("the menu's molecule example asks the search, not the textbook grid",
      req["parameters"]["bond_lengths"] == "search" and "0.735" not in json.dumps(req), req)
check("its limits say what search does and that a list still runs as written",
      all(w in E.EXPERIMENTS["molecule"]["limits"] for w in ('"search"', "95%", "not sure", "1.6 A", "as written")))
check("the first request is a wide bracket centred on no textbook minimum",
      S.BRACKET[0] <= 0.45 and S.BRACKET[-1] >= 2.2 and len(S.BRACKET) == 9 and 0.735 not in S.BRACKET
      and all(b2 / b1 < 1.25 for b1, b2 in zip(S.BRACKET, S.BRACKET[1:])), S.BRACKET)

# ---- 2. exact mode: the exact column, read to the minimum, wherever it is
for r_e in (0.52, 0.74, 0.93, 1.31, 1.62, 1.95):
    c = Curve(r_e)
    verdict, est, plans = drive(c, True)
    check("exact mode finds a minimum at %.2f A and says it is sure" % r_e,
          verdict == "sure" and abs(est["bond_length"] - r_e) <= S.TOL_BOND
          and abs(est["energy"] - c.e_min()) <= S.TOL_ENERGY and len(plans) <= 4, (verdict, est, plans))
    check("every request it makes is the bench's shape (at most 9 lengths, 0.40-2.50 A, no word)",
          all(isinstance(p["bond_lengths"], list) and 1 <= len(p["bond_lengths"]) <= 9
              and all(S.LO <= b <= S.HI for b in p["bond_lengths"]) for p in plans), plans)
c = Curve(0.93)
v1, e1, p1 = drive(c, True)
check("the second request refines where the minimum can still be, not the bracket again",
      len(p1) >= 2 and p1[1]["bond_lengths"] != p1[0]["bond_lengths"]
      and max(p1[1]["bond_lengths"]) - min(p1[1]["bond_lengths"]) < 0.5
      and min(p1[1]["bond_lengths"]) <= 0.93 <= max(p1[1]["bond_lengths"]), p1)

# ---- 3. measured mode: noisy readings, an honest confidence, and stalled searches past 1.6 A
right_when_sure, sure_n, cases = 0, 0, 0
for r_e in (0.62, 0.81, 1.05, 1.3):
    for seed in (1, 2, 3):
        c = Curve(r_e)
        verdict, est, plans = drive(c, False, seed=seed)
        cases += 1
        if verdict == "sure":
            sure_n += 1
            right_when_sure += abs(est["bond_length"] - r_e) <= S.TOL_BOND
check("measured mode is sure in most cases and right whenever it is sure",
      sure_n >= 9 and right_when_sure == sure_n, (sure_n, right_when_sure, cases))
c = Curve(1.62, D=0.08, a=1.4)
bracket = [S.Reading(b, round(c.exact(b) + S._bias_sd(b, 4096, 1)[0], 6), False, 4096, 1, hf=c.hf(b))
           for b in S.BRACKET]
plan, verdict, est = S.propose(bracket, False, S.cost(9, False, 4096, 1))
check("a refinement reaching past 1.55 A asks for 2 restarts (stretched bonds stall less with them)",
      plan and max(plan["bond_lengths"]) > S.NOISY_FROM and plan["restarts"] == 2, (plan, est))
c = Curve(0.8)
bracket = [S.Reading(b, round(c.exact(b) + S._bias_sd(b, 4096, 1)[0], 6), False, 4096, 1, hf=c.hf(b))
           for b in S.BRACKET]
plan, verdict, est = S.propose(bracket, False, S.cost(9, False, 4096, 1))
check("and one near 0.8 A asks for 1, at the most shots the budget allows",
      plan and max(plan["bond_lengths"]) < S.NOISY_FROM and plan["restarts"] == 1 and plan["vqe_shots"] == 16384,
      (plan, est))
c = Curve(1.32, D=0.06, a=1.3)
stalled = [S.Reading(b, round(c.hf(b), 6), False, 4096, 1, hf=c.hf(b)) for b in (1.47, 1.8, 2.2)]
good = [S.Reading(b, round(c.exact(b), 6), False, 4096, 1, hf=c.hf(b)) for b in (0.45, 0.55, 0.67, 0.81, 0.99, 1.21)]
est = S.estimate(good + stalled)
check("searches stalled at Hartree-Fock past 1.2 A do not push the minimum out of where it can be",
      est["interval"][0] <= 1.32 <= est["interval"][1] and est["bond_confidence"] < S.SURE, est)
c = Curve(0.74)
est = S.estimate([S.Reading(b, round(c.exact(b), 6), True) for b in (0.6, 0.7, 0.735, 0.74, 0.78, 0.9, 1.2)])
check("readings between grid points (0.735 beside 0.74) are placed where they were taken, not snapped",
      not est["at_edge"] and abs(est["bond_length"] - 0.74) <= S.TOL_BOND, est)
mac.request = lambda body, timeout=600: SENT_EARLY.append(body) or {"ok": True, "run": {}}
SENT_EARLY = []
mac.run("Molecule", {"molecule": "H2", "bond_lengths": "search"}, 4096)
check("an experiment written \"Molecule\" is still never sent the word",
      SENT_EARLY and SENT_EARLY[-1]["parameters"]["bond_lengths"] == list(S.BRACKET), SENT_EARLY)
sd_far = S._bias_sd(2.2, 4096, 1)[1]
sd_near = S._bias_sd(0.9, 4096, 1)[1]
check("past 1.6 A a measured reading carries the bench's larger spread", sd_far > 3 * sd_near, (sd_far, sd_near))

# ---- 4. the budget: "not sure" when it runs out, with the best answer and how sure
c = Curve(1.05)
verdict, est, plans = drive(c, False, seed=5, budget=3.5)
check("a spent budget says not sure, with its best answer and confidence",
      verdict == "budget" and est["bond_length"] is not None and est["bond_confidence"] < S.SURE, (verdict, est))
words = S._words("H2", est, verdict, 3.5)
check("in words", words.startswith("not sure (search budget spent") and "% sure" in words, words)
plan, verdict, est = S.propose([S.Reading(0.9, -1.1, True)], False, 0.0, steps_left=0)
check("no step left is the end of the budget too, whatever cost units remain", plan is None and verdict == "budget",
      (plan, verdict))
c = Curve(0.93)
est = S.estimate([S.Reading(b, round(c.exact(b), 6), True) for b in S.BRACKET])
check("the bracket alone is never sure, however smooth the belief: no reading stands near the answer on both sides",
      est["bond_confidence"] <= S.UNSUPPORTED < S.SURE and abs(est["bond_length"] - 0.93) <= 0.05, est)
sure_bond = dict(est, bond_confidence=0.99, energy_confidence=0.6)
words = S._words("X", sure_bond, "budget", 20.0)
check("a spent budget with the bond length sure says which part it is sure of",
      words.startswith("bond length sure, energy not sure") and "60% sure" in words, words)
c = Curve(0.3)
verdict, est, plans = drive(c, True)
check("a minimum below 0.40 A is never claimed: not sure, it may lie outside the range",
      verdict != "sure" and est["at_edge"] and "outside" in S._words("X", est, verdict, 0), (verdict, est))

# ---- 5. fill: only "search" is touched, deterministically
listed = {"experiment": "molecule", "parameters": {"molecule": "HeH+", "bond_lengths": [0.6, 0.9]}, "shots": 2048}
check("a written list runs exactly as written", S.fill("experiment", listed, []) == (listed, "", None))
other = {"experiment": "fold", "parameters": {"sequence": "HPHP"}}
check("another experiment or route is untouched", S.fill("experiment", other, [])[0] is other
      and S.fill("source", {"source": "pubmed"}, [])[1] == "")
ask = {"experiment": "molecule", "parameters": {"molecule": "HeH+", "bond_lengths": "search", "exact": False},
       "shots": 4096}
a1, a2 = S.fill("experiment", ask, []), S.fill("experiment", ask, [])
check("search with nothing measured yet is the bracket, with shots and restarts for measured mode",
      a1[0]["parameters"]["bond_lengths"] == list(S.BRACKET) and a1[0]["parameters"]["vqe_shots"] == 4096
      and a1[0]["parameters"]["restarts"] == 1 and a1[1] == "" and a1[2]["verdict"] == "searching", a1)
check("filled the same way twice (the trial's check and the step agree)", a1 == a2)
fixed = dict(ask, parameters=dict(ask["parameters"], vqe_shots=16384, restarts=4))
f = S.fill("experiment", fixed, [])[0]["parameters"]
check("shots and restarts the planner set are kept", f["vqe_shots"] == 16384 and f["restarts"] == 4, f)
lih = S.fill("experiment", {"experiment": "molecule", "parameters": {"molecule": "LiH", "bond_lengths": "search"}}, [])
check("LiH asks at most 5 lengths (its runs are slow against the bench's 180 s)",
      len(lih[0]["parameters"]["bond_lengths"]) == 5, lih)
check("the original request is not changed in place", ask["parameters"]["bond_lengths"] == "search")

# ---- 6. the Mac door never sends the word
SENT = []
def bench(body, timeout=600):
    SENT.append(body)
    return {"ok": True, "configured": True, "run_id": "R-door", "pyqpanda3": "0.4.1", "run": {"result": {}}}
mac.request = bench
mac.run("molecule", {"molecule": "H2", "bond_lengths": "search"}, 4096)
check("search with no investigation behind it (the daily session) is sent as the bracket",
      SENT and SENT[-1]["parameters"]["bond_lengths"] == list(S.BRACKET), SENT[-1:])
mac.run("molecule", {"molecule": "H2", "bond_lengths": [0.7, 0.8]}, 4096)
check("a list is sent unchanged", SENT[-1]["parameters"]["bond_lengths"] == [0.7, 0.8], SENT[-1:])

# ---- 7. inside an investigation: each step builds on the last, and the search stops itself
CURVE = Curve(1.12, D=0.12, a=1.6, e0=-2.1)
RUNS = []
def execute(route, request, question, steps):
    RUNS.append(request)
    params = request["parameters"]
    rows = [{"bond_length": b, "exact": round(CURVE.exact(b), 6), "vqe": round(CURVE.exact(b) + 0.0004, 6),
             "hartree_fock": round(CURVE.hf(b), 6)} for b in params["bond_lengths"]]
    return {"ok": True, "configured": True, "run_id": "R-%d" % len(RUNS), "pyqpanda3": "0.4.1",
            "run": {"experiment": "molecule", "parameters": params, "result": {"molecule": params["molecule"],
                                                                               "results": rows}}}
LI._gate = lambda inquiry: {}
data = {"investigations": [{"id": "I-test", "question": "where is the minimum of this molecule's curve?",
                            "state": "open", "steps": [], "at": lab.now_iso()}]}
inv = data["investigations"][0]
proposal = {"route": "experiment", "request": {"experiment": "molecule", "parameters": {"molecule": "HeH+",
            "bond_lengths": "search", "layers": 2}, "shots": 4096}, "step_question": "the curve near its minimum"}
outcomes, verdicts = [], []
for turn in range(6):
    before = len(inv["steps"])
    if turn == 1:
        check("the planner's trial check fills the request as the step will",
              T.explain(proposal, inv) == ("", ""), T.explain(proposal, inv))
    try:
        row = LI._carry_out(data, inv, json.loads(json.dumps(proposal)), None, "", None, execute, True)
        outcomes.append(row.get("state"))
    except LI._Replan as exc:
        outcomes.append("replan:" + exc.kind)
        verdicts.append(exc.note.get("why_not_run"))
        break
done = [s for s in inv["steps"] if s.get("state") == "completed"]
check("each search step ran a list the search chose, and the bench never got the word",
      done and all(isinstance(r["parameters"]["bond_lengths"], list) for r in RUNS)
      and all(isinstance(s["executed_request"]["parameters"]["bond_lengths"], list) for s in done), RUNS)
check("the second step refined, not repeated", len(RUNS) >= 2 and RUNS[1]["parameters"]["bond_lengths"]
      != RUNS[0]["parameters"]["bond_lengths"], RUNS[:2])
check("once sure, nothing more is sent: the planner is told the answer and to finish",
      outcomes[-1] == "replan:bond_search_done" and verdicts and "already sure" in verdicts[-1]
      and "1.12" in verdicts[-1] and len(RUNS) <= 4, (outcomes, verdicts))
check("the step records what the search knew, and what it knows with its readings in",
      all(isinstance(s.get("bond_length_search"), dict) and s["bond_length_search"].get("now") for s in done)
      and done[-1]["bond_length_search"]["now"].startswith("sure: minimum at 1.12"), [s.get("bond_length_search") for s in done])
check("the trial's check says the same as the step", T.explain(proposal, inv)[0] == "bond_search_done",
      T.explain(proposal, inv))
view = S.planner_view(inv["steps"])
check("the planner's task shows the answer and that the search is done",
      view and view[0]["molecule"] == "HEH+" and view[0]["said"].startswith("sure") and view[0]["next"].startswith("finish"),
      view)
obs = LI._observations(inv["steps"])["additional_source"]["receipt"]["records"]
check("the finish review reads the search's own verdict beside each output",
      obs and all(o.get("bond_length_search") for o in obs), obs[:1])
readings, spent = S.history(inv["steps"], ("HEH+", ""))
check("history reads the stored outputs (exact column) and counts what was spent",
      readings and all(r.exact for r in readings) and spent > 0, (readings[:3], spent))
copy = dict(done[-1], id="S-copy", reused_from=done[-1]["id"])
again, spent2 = S.history(inv["steps"] + [copy], ("HEH+", ""))
check("a step handed an earlier output adds no readings and no cost", len(again) == len(readings) and spent2 == spent)
elsewhere = dict(done[0], id="S-elsewhere", reused_from="S-in-another-investigation", output_sha256="e" * 64)
alone, spent3 = S.history([elsewhere], ("HEH+", ""), load=lambda step, steps: LI.resolve(
    {"step": done[0]["id"], "path": []}, inv["steps"]))
check("a step handed another investigation's run (the bracket is the same everywhere) reads it, at no cost",
      len(alone) == len(done[0]["executed_request"]["parameters"]["bond_lengths"]) and spent3 == 0,
      (len(alone), spent3))
twin = dict(done[-1], id="S-twin", same_receipt_as=done[-1]["id"], output_sha256="0" * 64)
again, _ = S.history(inv["steps"] + [twin], ("HEH+", ""), load=lambda step, steps: LI.resolve(
    {"step": done[-1]["id"], "path": []}, steps))
check("a step that came back with an earlier step's receipt adds no readings", len(again) == len(readings),
      (len(again), len(readings)))

# ---- 8. a measured search inside an investigation reads the VQE column
data2 = {"investigations": [{"id": "I-m", "question": "q", "state": "open", "steps": [], "at": lab.now_iso()}]}
inv2 = data2["investigations"][0]
RUNS.clear()
def execute_measured(route, request, question, steps):
    RUNS.append(request)
    params = request["parameters"]
    rows = [{"bond_length": b, "vqe": round(CURVE.exact(b) - 0.002, 6), "hartree_fock": round(CURVE.hf(b), 6)}
            for b in params["bond_lengths"]]
    return {"ok": True, "configured": True, "run_id": "M-%d" % len(RUNS), "pyqpanda3": "0.4.1",
            "run": {"experiment": "molecule", "parameters": params, "result": {"results": rows}}}
m = json.loads(json.dumps(proposal)); m["request"]["parameters"]["exact"] = False
LI._carry_out(data2, inv2, m, None, "", None, execute_measured, True)
r2, _ = S.history(inv2["steps"], ("HEH+", ""))
check("measured mode: the VQE values with the request's shots and restarts",
      r2 and not any(r.exact for r in r2) and r2[0].shots == 4096 and r2[0].restarts == 1
      and RUNS[0]["parameters"]["vqe_shots"] == 4096, (r2[:2], RUNS[:1]))

check("nothing left this host", NET == [], NET)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
