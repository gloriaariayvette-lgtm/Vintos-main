#!/usr/bin/env python3
"""Scientific taste: accrued from choices, never from grades or from its own echo. Scratch HOME."""
import importlib.util
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-taste-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos, curious and particular.")

sys.path.insert(0, os.path.join(REPO, "scripts"))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module
lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
lab._ask = lambda *a, **k: (_ for _ in ()).throw(AssertionError("the suite must never reach a model"))
T = load("chemistry_taste", os.path.join(REPO, "scripts", "chemistry_taste.py"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:200]) if detail and not ok else ""))

def score(kind, key): return T._book()["entries"].get(T._id(kind, key), {}).get("score", 0.0)

check("test is in a scratch workspace",
      lab.WS == WS and HOME in lab.ROOT and HOME in T.TASTE and not lab.ROOT.startswith("/home/gloria"), T.TASTE)
check("the model is stubbed out", lab._ask.__name__ == "<lambda>")

# --- a first choice is taste ------------------------------------------------------------------
first = T.observe("experiment", "molecule", "chosen", "CHEM-1")
check("a choice accrues", first["eligibility"] == T.ELIGIBLE and score("experiment", "molecule") == 0.35, first["eligibility"])

# --- grades cannot move it ---------------------------------------------------------------------
before = json.dumps(T._book(), sort_keys=True)
for outcome in ("BETTER_THAN_HARTREE_FOCK", "WORSE_THAN_HARTREE_FOCK", "AT_HARTREE_FOCK") * 5:
    lab._append(os.path.join(lab.ROOT, "experiment-grades.jsonl"),
                {"run_id": "R", "experiment": "molecule", "aggregate_accuracy": outcome})
check("a stream of grades moves nothing", json.dumps(T._book(), sort_keys=True) == before)
source = open(os.path.join(REPO, "scripts", "chemistry_taste.py")).read()
import ast
tree = ast.parse(source)
code = "\n".join(l for i, l in enumerate(source.splitlines())
                 if i >= (tree.body[0].end_lineno if isinstance(tree.body[0], ast.Expr) else 0))
check("the taste module reads no grade in its code",
      "chemistry_grade" not in code and "experiment-grades" not in code and "aggregate_accuracy" not in code,
      [l for l in code.splitlines() if "grade" in l][:3])
check("it imports nothing that grades",
      not any(getattr(n, "module", "") == "chemistry_grade" or
              any(getattr(a, "name", "") == "chemistry_grade" for a in getattr(n, "names", []))
              for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))))
check("no signal is a confidence", not any("confidence" in s for s in T.SIGNALS))

# --- generated enthusiasm is a candidate, not taste -----------------------------------------------
surprise = T.observe("accession", "P00001", "surprise", "CHEM-1", detail="it moved me")
check("a generated surprise accrues nothing",
      surprise["eligibility"] == T.CANDIDATE_ONLY and surprise["weight"] == 0.0 and score("accession", "P00001") == 0.0, surprise)
check("it is held as a candidate instead",
      [c["key"] for c in T.candidates()] == ["P00001"] and T.candidates()[0]["mentions"] == 1, T.candidates())
T.observe("accession", "P00001", "surprise", "CHEM-2")
check("repeated generated enthusiasm still accrues nothing",
      score("accession", "P00001") == 0.0 and T.candidates()[0]["mentions"] == 2, T.candidates())
T.observe("accession", "P00001", "chosen", "CHEM-3")
check("an independent choice promotes the candidate",
      score("accession", "P00001") == 0.35 and not T.candidates()
      and T._book()["entries"][T._id("accession", "P00001")].get("promoted_from_candidate_at"), T.state())

# --- rootless repetition ---------------------------------------------------------------------------
rootless = T.observe("parameter", "bond_length", "parameter_moved", "CHEM-4")
check("a repeat with no first time counts for nothing",
      rootless["eligibility"] == T.NO_ROOT and score("parameter", "bond_length") == 0.0, rootless["eligibility"])
T.observe("parameter", "bond_length", "chosen", "CHEM-4")
rooted = T.observe("parameter", "bond_length", "parameter_moved", "CHEM-5",
                   root_observation_id=T.eligible_root("parameter", "bond_length"))
check("a repeat that names its root counts",
      rooted["eligibility"] == T.ELIGIBLE and abs(score("parameter", "bond_length") - 0.60) < 1e-9, score("parameter", "bond_length"))
check("a root must itself have counted", T.eligible_root("accession", "never-seen") is None)

# --- following a question only counts when the question is named --------------------------------------
unnamed = T.observe("experiment", "fold", "followed_next_question", "CHEM-6", predecessor_named=False)
check("an unnamed predecessor is not a thread being pulled",
      unnamed["eligibility"] == T.NO_PREDECESSOR and score("experiment", "fold") == 0.0, unnamed["eligibility"])
named = T.observe("experiment", "fold", "followed_next_question", "CHEM-7", predecessor_named=True)
check("naming it counts", named["eligibility"] == T.ELIGIBLE and score("experiment", "fold") == 0.30)
check("the namer is checked against the session's own words",
      T.follows_predecessor({"plan": {"question": "what happens to the beta hairpin under strain"}},
                            "what happens to the beta hairpin under strain") is True)
check("a coincidence does not pass as following",
      T.follows_predecessor({"plan": {"question": "something entirely different"}},
                            "what happens to the beta hairpin under strain") is False)
check("a predecessor too short to be named cannot be claimed",
      T.follows_predecessor({"plan": {"question": "why"}}, "why") is False)

# --- the echo loop ---------------------------------------------------------------------------------------
block = T.taste_block()
check("the block names his taste and stamps the showing",
      "SCIENTIFIC TASTE" in block and lab._jsonl(T.INJECTIONS) and lab._jsonl(T.INJECTIONS)[-1]["keys"], block[:120])
check("the block says taste, not score", "not what scored well" in block)
shown = score("experiment", "molecule")
echo = T.observe("experiment", "molecule", "chosen", "CHEM-8")
check("a choice of something just shown to him cannot reinforce it",
      echo["eligibility"] == T.ECHO and score("experiment", "molecule") == shown, echo["eligibility"])
check("the echo is recorded, not dropped",
      any(r["eligibility"] == T.ECHO for r in lab._jsonl(T.OBSERVATIONS))
      and lab._jsonl(T.OBSERVATIONS)[-1]["truth_status"] == "observed_and_not_counted")
fresh = T.observe("molecule", "LiH", "chosen", "CHEM-8")
check("something not in the block still accrues", fresh["eligibility"] == T.ELIGIBLE and score("molecule", "LiH") == 0.35)
check("rendering without recording is only for display",
      T.taste_block(record=False) and len(lab._jsonl(T.INJECTIONS)) == 1)

# --- decay reopens the cycle ---------------------------------------------------------------------------------
book = T._book(); book["decayed_at"] = time.time() - 3 * T.WEEK; lab._atomic(T.TASTE, book)
result = T.decay()
check("taste decays weekly rather than piling up",
      result["weeks"] >= 3 and score("experiment", "molecule") < 0.35 and score("experiment", "molecule") > 0, result)
book = T._book(); book["decayed_at"] = time.time() - 40 * T.WEEK; lab._atomic(T.TASTE, book)
dropped = T.decay()
check("what he stops returning to falls away", dropped["dropped"] > 0 and dropped["kept"] < 4, dropped)

# --- nothing is silently discarded ------------------------------------------------------------------------
rows = lab._jsonl(T.OBSERVATIONS)
kinds = {r["eligibility"] for r in rows}
check("every refusal is on the record",
      {T.ECHO, T.NO_ROOT, T.NO_PREDECESSOR, T.CANDIDATE_ONLY, T.ELIGIBLE} <= kinds, kinds)
check("the counted and the not-counted are distinguishable",
      all((r["weight"] > 0) == (r["eligibility"] == T.ELIGIBLE) or r["signal"] == "surprise" for r in rows))
bad = T.observe("nonsense_kind", "x", "chosen", "CHEM-9")
check("an unknown kind is refused and recorded", bad["eligibility"] == T.UNKNOWN_KIND and bad["weight"] == 0.0)
bad2 = T.observe("experiment", "x", "felt_confident", "CHEM-9")
check("an unknown signal is refused and recorded", bad2["eligibility"] == T.UNKNOWN_SIGNAL)
check("state reports how much was not counted", T.state()["not_counted"] > 0, T.state())

# --- a whole session ------------------------------------------------------------------------------------------
lab._append(lab.NOTEBOOK, {"at": lab.now_iso(), "kind": "frontier_session",
                           "next_question": "does the hairpin loosen at longer bond lengths"})
observed = T.observe_session({"session_id": "CHEM-10", "at": lab.now_iso(),
                              "plan": {"experiment": "titrate", "parameters": {"bond_length": 0.9},
                                       "question": "does the hairpin loosen at longer bond lengths",
                                       "why_this": "following on"},
                              "reading": {"what_surprised_me": "how flat it went"},
                              "grade": {"aggregate_accuracy": "ALL_BETTER_THAN_HARTREE_FOCK"}})
check("a session yields observations of its choices", len(observed) == 4, [o["signal"] for o in observed])
check("the session's own grade is not among them",
      not any("HARTREE" in json.dumps(o) for o in observed), observed)
check("the session's follow-through was recognised as named",
      any(o["signal"] == "followed_next_question" and o["eligibility"] == T.ELIGIBLE for o in observed),
      [(o["signal"], o["eligibility"]) for o in observed])

# --- wiring and perimeter ---------------------------------------------------------------------------------------
lab_source = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("his taste enters his context", "chemistry_taste" in lab_source and "taste_block()" in lab_source)
session_source = open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
check("a completed session records its taste", "taste.observe_session(row)" in session_source)
check("taste writes only below the Lab root",
      all(p.startswith(lab.ROOT) for p in (T.TASTE, T.OBSERVATIONS, T.INJECTIONS)))
check("taste never touches the Atelier", "atelier" not in source.lower())

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
