#!/usr/bin/env python3
"""A free pass measures what the Lab already holds before it looks anything up again (21 October).

Gloria asked for findings his own instruments make, not retrieval of what is written down. After a refused or
waiting pass the Lab took a record lookup; now, when it holds his ESMFold model of a protein and saved receipts for a
deposited structure of it, it compares the two (reference_compare: TM-score, RMSD) first. No search is made to find
the pair, the day's instrument limit holds, and an identical comparison is refused like any repeat.
No instrument runs here and no model is called; scratch HOME; no socket."""
import json, os, socket, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-held-measure-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C
import lab_instruments as I
def _never(*a, **k): raise AssertionError("nothing is called or sent in this suite")
C._ask = _never; C.urllib.request.urlopen = _never; I.run = _never
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the Lab's and the instruments' stores are scratch",
      C.ROOT.startswith(HOME) and str(I.LAB).startswith(HOME) and str(I.LEDGER).startswith(HOME))
check("no instrument can run and no model can be called", I.run is _never and C._ask is _never)

MODEL = "artifacts/esmfold/P69905-0123456789ab.pdb"
os.makedirs(os.path.join(C.ROOT, "artifacts", "esmfold"), exist_ok=True)
open(os.path.join(C.ROOT, MODEL), "w").write("ATOM\n")
def receipts(*rows):
    with open(C.SOURCE_RECEIPTS, "w") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
ARCHIVE = {"source": "pdb", "query": {"source": "pdb", "operation": "search_accession", "accession": "P69905"},
           "records": [{"entry_id": "1A3N", "mapped_accession": "P69905",
                        "modeled_residue_coverage": [{"chain": "A"}, {"chain": "C"}]}]}
GEOMETRY = {"source": "pdb", "query": {"source": "pdb", "entry_id": "1A3N", "operation": "structure_evidence"},
            "records": [{"entry_id": "1A3N", "geometry": {"chains": [
                {"chain": "A", "observed_residues": 141, "author_residue_min": 1, "author_residue_max": 141},
                {"chain": "C", "observed_residues": 12, "author_residue_min": 1, "author_residue_max": 12}]}}]}

admitted = []
def h2p(system, task, inq, value, lean, step, repeats, spent=None, replan=True):
    admitted.append((inq, replan)); return inq, value
C._held_to_plan = h2p
C._held_question = lambda inq: None
C._planning_evidence = lambda inq: {}
REP = types.SimpleNamespace(repeat=lambda inq: "")

print("--- a held model and a held structure are measured ---")
receipts(ARCHIVE, GEOMETRY)
got = C._next_held_measurement(REP, {"subjects": []})
iq = (got or {}).get("instrument_query") or {}
check("it chooses the comparison", iq.get("skill") == "reference_compare" and iq.get("operation") == "structure.compare", got)
check("of his model against the deposited entry and chain the receipts name", iq.get("files") == [MODEL]
      and iq.get("reference") == "1A3N" and iq.get("chain") == "A" and iq.get("ref_span") == [1, 141], iq)
check("a chain too short to measure is not chosen", iq.get("chain") != "C")
check("the question asks for the measurement, one thing", "TM-score" in got["question"] and C.second_ask(got["question"]) == "",
      got["question"])
check("it is not a lookup: no source query, the record fetched only by accession",
      not got.get("source_query") and got.get("uniprot_query") == "accession:P69905", got)
check("it passes the shared admission gate, without a re-plan", admitted and admitted[-1][1] is False)
check("the spent gate never stands between a subject and a new instrument",
      C.spent_retrieval(got, {"subjects": ["P69905", "hemoglobin"]}) is False)

print("--- nothing to measure, nothing invented ---")
receipts(ARCHIVE)
check("no structure receipt: no comparison", C._next_held_measurement(REP, {"subjects": []}) is None)
receipts(GEOMETRY)
check("no archive mapping to the model's protein: no comparison", C._next_held_measurement(REP, {"subjects": []}) is None)
receipts(ARCHIVE, GEOMETRY)
check("an identical comparison already made is refused, and nothing else is offered",
      C._next_held_measurement(types.SimpleNamespace(repeat=lambda inq: "repeat"), {"subjects": []}) is None)
json.dump({"day": I._runs_today().get("day"), "runs": [{"at": 0}] * I.DAILY_RUNS}, open(I.LEDGER, "w"))
saved_today = I._runs_today
I._runs_today = lambda: {"runs": [{}] * I.DAILY_RUNS}
check("the day's instrument runs used up: no comparison", C._next_held_measurement(REP, {"subjects": []}) is None)
I._runs_today = saved_today
os.remove(I.LEDGER)

print("--- in the pass after a refusal, it comes before a record lookup ---")
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
o = src[src.index("def _orient("):src.index("lean_text = ((")]
check("both free-pass recoveries try the measurement first",
      o.count("_held_measurement_or_none(lab_repeats, spent, lean)") == 2 and
      all(o.index("_held_measurement_or_none", i) < o.index("_next_sourced_record(lab_repeats", i)
          for i in (0, o.index("_next_sourced_record(lab_repeats") + 1)))
C._next_held_measurement = lambda *a: (_ for _ in ()).throw(OSError("a broken artifact"))
check("a broken artifact costs the option, not the pass", C._held_measurement_or_none(REP, {}) is None)
check("and is written down as a fault",
      any(json.loads(l).get("stage") == "held_measurement" for l in open(C.FAULTS)) if os.path.exists(C.FAULTS) else False)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
