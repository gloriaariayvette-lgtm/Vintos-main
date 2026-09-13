#!/usr/bin/env python3
"""The Lab's visible body: read endpoints and the LAB pane. Scratch HOME; no server, no network."""
import ast
import asyncio
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-gallery-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS

sys.path.insert(0, os.path.join(REPO, "scripts"))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module
lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:200]) if detail and not ok else ""))

check("test is in a scratch workspace",
      lab.WS == WS and HOME in lab.ROOT and not lab.ROOT.startswith("/home/gloria"), lab.ROOT)

# --- run the endpoint code itself, against the scratch Lab -------------------------------------
SERVER = open(os.path.join(REPO, "bin", "server.py")).read()
block = SERVER[SERVER.index("def _chemistry_tail("):SERVER.index('@app.get("/api/briefing/latest")')]
block = "\n".join(l for l in block.splitlines() if not l.startswith("@app."))
secrets = []
scope = {"os": os, "math": __import__("math"), "Request": object,
         "_chemistry_lab_module": lambda: lab,
         "_require_secret": lambda request: secrets.append(request)}
exec(compile(ast.parse(block), "server-chemistry-block", "exec"), scope)
check("the Lab endpoints are ordinary code that can be exercised",
      all(k in scope for k in ("chemistry_lab_notebook", "chemistry_lab_sessions",
                               "chemistry_lab_grades", "chemistry_lab_taste", "chemistry_lab_curve")))

GRADE = {"run_id": "RUN-A", "at": "2026-09-13T03:20:00+00:00", "experiment": "molecule",
         "execution_state": "completed", "aggregate_accuracy": "ALL_WORSE_THAN_HARTREE_FOCK",
         "graded_points": 3, "total_points": 3, "grader_version": "chemistry_grade/1",
         "isolation_attestation": "host_attested",
         "points": [{"bond_length": 0.5, "vqe_energy": -0.9, "hartree_fock_energy": -1.0,
                     "exact_energy": -1.05, "energy_above_hartree_fock": 0.1,
                     "correlation_recovered": -2.0, "accuracy_outcome": "WORSE_THAN_HARTREE_FOCK",
                     "counts_as": "accuracy"},
                    {"bond_length": 0.735, "vqe_energy": float("nan"), "hartree_fock_energy": None,
                     "accuracy_outcome": "UNGRADED_UNREADABLE", "counts_as": "nothing"},
                    {"bond_length": 1.0, "vqe_energy": -0.8, "hartree_fock_energy": -0.85,
                     "energy_above_hartree_fock": 0.05, "correlation_recovered": float("inf"),
                     "accuracy_outcome": "WORSE_THAN_HARTREE_FOCK", "counts_as": "accuracy"}]}
lab._append(os.path.join(lab.ROOT, "experiment-grades.jsonl"), json.loads(json.dumps(GRADE, default=str)))
lab._append(os.path.join(lab.ROOT, "sessions.jsonl"), {
    "session_id": "CHEM-1", "at": "2026-09-13T03:20:00+00:00", "lens": "claude", "state": "completed",
    "plan": {"experiment": "molecule", "question": "how flat is it?", "parameters": {"bond_length": 0.735}},
    "mac_run_id": "RUN-A", "owed_reading": "NOTHING_OWED",
    "mac_result": {"enormous": "x" * 5000},
    "grade": GRADE, "reading": {"reading": "a shallow basin", "next_question": "deeper?"}})
lab._append(lab.NOTEBOOK, {"at": "2026-09-13T03:21:00+00:00", "kind": "frontier_session", "session_id": "CHEM-1"})
lab._atomic(os.path.join(lab.ROOT, "taste.json"),
            {"entries": {"experiment||molecule": {"kind": "experiment", "key": "molecule", "score": 0.7,
                                                  "signals": {"chosen": 2}, "last_seen": "x"},
                         "broken||nan": {"kind": "broken", "key": "nan", "score": float("nan"), "signals": {}}},
             "candidates": {"accession||P00001": {"kind": "accession", "key": "P00001", "mentions": 2}}})

req = object()
sessions = asyncio.run(scope["chemistry_lab_sessions"](req, limit=5))
row = sessions["sessions"][0]
check("a session card carries instrument state and answer state as two fields",
      row["execution_state"] == "completed" and row["aggregate_accuracy"] == "ALL_WORSE_THAN_HARTREE_FOCK", row)
check("the huge Mac payload is not shipped to the page", "mac_result" not in row and len(json.dumps(row)) < 900, len(json.dumps(row)))
check("the reading and the next question come through", row["reading"] == "a shallow basin" and row["next_question"] == "deeper?")

curve = asyncio.run(scope["chemistry_lab_curve"](req, "RUN-A"))
check("the curve is read from the preserved grade, not recomputed",
      curve["ok"] and curve["aggregate_accuracy"] == "ALL_WORSE_THAN_HARTREE_FOCK" and len(curve["points"]) == 2, curve)
check("non-finite values never reach the page",
      all(p["correlation_recovered"] is None or abs(p["correlation_recovered"]) < 1e9 for p in curve["points"])
      and "NaN" not in json.dumps(curve) and "Infinity" not in json.dumps(curve), curve["points"])
check("an unreadable point is dropped rather than drawn",
      all(p["vqe_energy"] is not None for p in curve["points"]))
missing = asyncio.run(scope["chemistry_lab_curve"](req, "RUN-NOPE"))
check("a run with no grade says so instead of inventing points", missing["ok"] is False and missing["points"] == [])

grades = asyncio.run(scope["chemistry_lab_grades"](req, limit=5))
check("the grade list keeps execution and accuracy apart",
      grades["grades"][0]["execution_state"] == "completed"
      and grades["grades"][0]["aggregate_accuracy"] == "ALL_WORSE_THAN_HARTREE_FOCK"
      and "points" not in grades["grades"][0], grades["grades"][0])

taste = asyncio.run(scope["chemistry_lab_taste"](req))
check("taste comes through with its candidates named separately",
      taste["taste"][0]["key"] == "molecule" and taste["candidates"][0]["key"] == "P00001", taste)
check("an unreadable score sinks rather than leading the list",
      taste["taste"][-1]["score"] is None, [t["key"] for t in taste["taste"]])
check("a non-finite score is nulled, not drawn",
      any(t["score"] is None for t in taste["taste"]) and "NaN" not in json.dumps(taste), taste["taste"])

notebook = asyncio.run(scope["chemistry_lab_notebook"](req, limit=3))
check("the notebook tail is bounded", notebook["ok"] and len(notebook["entries"]) <= 3)
check("a limit cannot be widened past the cap", len(asyncio.run(scope["chemistry_lab_notebook"](req, limit=10000))["entries"]) <= 60)
check("every Lab read required the secret", len(secrets) == 7, len(secrets))

# --- the page ------------------------------------------------------------------------------------
PAGE = open(os.path.join(REPO, "clients", "mobile", "index.html")).read()
check("there is a LAB tab and pane", 'data-tab="lab"' in PAGE and 'id="pane-lab"' in PAGE and "loadLab()" in PAGE)
check("the pane shows instrument state and answer state as separate marks",
      "'instrument: '" in PAGE and "'answer: '" in PAGE and "_labVerdict" in PAGE)
check("a worse-than-Hartree-Fock answer is not dressed as a success",
      "ALL_WORSE_THAN_HARTREE_FOCK: ['worse than Hartree-Fock'" in PAGE)
check("every drawn value goes through a finite check", "_labNum" in PAGE and "Number.isFinite" in PAGE)
check("the curve is capped", "LAB_CURVE_CAP = 48" in PAGE and "slice(0, LAB_CURVE_CAP)" in PAGE)
check("the page escapes through the shared escaper", "_labChip" in PAGE and PAGE.count("_esc(") > 40 and "innerHTML = cards.join" not in PAGE.replace("cards.length ? cards.join('')", ""))
check("no charting library was added",
      not any(lib in PAGE.lower() for lib in ("chart.js", "d3.min.js", "plotly", "recharts", "3dmol", "cdn.jsdelivr")))
check("the curve is hand-rolled svg", "<svg viewBox=" in PAGE and "stroke-dasharray" in PAGE)
check("taste is labelled as taste, not as score", "grades are a separate ledger" in PAGE)
check("what he wants to try next is shown", "what I want to try next" in PAGE)

check("the routes are all behind the secret",
      SERVER.count("_require_secret(request)") >= 7 and
      all(('@app.get("/api/lab/chemistry/%s' % name) in SERVER
          for name in ("notebook", "sessions", "grades", "taste", "curve/{run_id}")))
check("no Lab endpoint writes anything",
      not any(w in block for w in ("_append(", "_atomic(", "set_enabled(", "open(")), 
      [w for w in ("_append(", "_atomic(", "set_enabled(", "open(") if w in block])
check("the Lab pane never reaches the Atelier", "atelier" not in block.lower())

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
