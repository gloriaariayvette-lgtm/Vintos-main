#!/usr/bin/env python3
"""The frontier's log builds on itself; Gemma's journal stays Gemma's (Gloria, 2026-09-28).

Scratch HOME and workspace; no model, Mac or network is called — only the context builders run.
"""
import contextlib, importlib.util, json, os, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-frontier-log-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos.")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod


lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
sys.modules["chemistry_mac"] = types.SimpleNamespace()
@contextlib.contextmanager
def admitted(*a, **k): yield object()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
session = load("chemistry_session_log_test", os.path.join(REPO, "scripts", "chemistry_session.py"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:300]) if detail and not ok else ""))

check("the suite writes only to a scratch workspace",
      lab.ROOT.startswith(HOME) and session.SESSIONS.startswith(HOME) and session.DIVERGENCE.startswith(HOME), lab.ROOT)

lab._ensure()
# Gemma's own work, in her notebook.
lab._append(lab.NOTEBOOK, {"at": "2026-09-27T10:00:00+00:00", "kind": "reflection", "entry_id": "G1",
                           "inquiry": {"question": "GEMMA-QUESTION about the S-layer"},
                           "factual_observation": "GEMMA-FINDING", "next_question": "GEMMA-NEXT",
                           "source_accessions": ["Q1"]})
# Two frontier sessions, their blind readers, and the rows the session also leaves in the notebook.
for n, (lens, pred) in enumerate((("claude", "PRED-ONE"), ("grok", "PRED-TWO")), 1):
    sid = "CHEM-%d" % n
    lab._append(session.SESSIONS, {"session_id": sid, "at": "2026-09-2%dT03:17:00+00:00" % (5 + n), "lens": lens,
        "state": "completed", "plan": {"experiment": "h2_vqe", "question": "FRONTIER-Q%d" % n, "prediction": pred},
        "grade": {"execution_state": "completed", "aggregate_accuracy": "ALL_BETTER_THAN_HARTREE_FOCK"},
        "reading": {"reading": "READ-%d" % n, "prediction_vs_result": "MISS-%d" % n, "next_question": "NEXT-%d" % n}})
    lab._append(session.DIVERGENCE, {"session_id": sid + "-D", "source_session_id": sid, "mode": "divergence",
        "readings": [{"lens": "fable", "state": "read", "question": "FABLE-ASKS-%d" % n},
                     {"lens": "opus", "state": "held"}]})
    lab._append(lab.NOTEBOOK, {"at": "2026-09-2%dT03:20:00+00:00" % (5 + n), "kind": "frontier_session",
                               "session_id": sid, "question": "FRONTIER-Q%d" % n, "next_question": "NEXT-%d" % n})
lab._append(session.SESSIONS, {"session_id": "CHEM-X", "state": "held_mac_unavailable", "lens": "sol"})

log = session.frontier_log()
check("the frontier log holds its own completed sessions, oldest first",
      [e["session_id"] for e in log] == ["CHEM-1", "CHEM-2"] and log[1]["prediction"] == "PRED-TWO"
      and log[0]["prediction_vs_result"] == "MISS-1" and log[1]["next_question"] == "NEXT-2", log)
check("each session carries what the blind readers asked of it",
      log[0]["blind_readers_asked"] == [{"lens": "fable", "question": "FABLE-ASKS-1"}], log[0])

fctx, freceipt = session.frontier_context()
check("the frontier's context builds on its own log",
      "YOUR FRONTIER LOG" in fctx and "NEXT-2" in fctx and "PRED-ONE" in fctx
      and any(s["name"] == "frontier_log" for s in freceipt["sources"]), fctx[-600:])
check("and carries nothing of Gemma's journal",
      "GEMMA-FINDING" not in fctx and "GEMMA-QUESTION" not in fctx and "GEMMA-NEXT" not in fctx
      and not any(s["name"] in ("lab_journal_threads", "search_misses", "recent_lab_source", "lab_notebook")
                  for s in freceipt["sources"]), freceipt["sources"])

gctx, _ = lab.lab_context()
check("Gemma's context still has her own journal",
      "GEMMA-FINDING" in gctx or "GEMMA-NEXT" in gctx, gctx[-600:])
check("and none of the frontier's sessions",
      "FRONTIER-Q" not in gctx and "NEXT-1" not in gctx and "NEXT-2" not in gctx, gctx[-600:])
check("the app's thread view still shows both",
      any("FRONTIER-Q" in t["question"] for t in lab.journal_threads())
      and not any("FRONTIER-Q" in t["question"] for t in lab.journal_threads(include_frontier=False)))
check("the scheduled session plans from the frontier context",
      "context, receipt = frontier_context()" in open(os.path.join(REPO, "scripts", "chemistry_session.py")).read())

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
