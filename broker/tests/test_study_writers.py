#!/usr/bin/env python3
"""When Fable cannot write a Study fix, Astra does, then Grok (Gloria, 2026-10-15: "The Study should have fallen to
Astra and/or Grok"). forge_study already fell from Fable to Astra; study_fix called Fable alone, and a refusal there
is not an error at all: the call returns empty and only the missing JSON shows it.

Isolation: scratch HOME and workbench; Fable, Astra and Grok are stubs that record what they were asked; no socket."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="study-writers-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_STUDY_WORKBENCH"] = os.path.join(HOME, "workbench")
os.environ["VINTOS_CHECKOUT"] = os.path.join(HOME, "Vintos-main")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import study_fix as S, claude_cache
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
ROOT = os.path.join(HOME, "workbench"); os.makedirs(os.path.join(ROOT, "scripts"))
open(os.path.join(ROOT, "CLAUDE.md"), "w").write("rules\n"); open(os.path.join(ROOT, "scripts", "a.py"), "w").write("X=1\n")
check("the workbench is scratch", S.WORKBENCH.startswith(HOME))
check("the order is Fable, then Astra, then Grok", [n for n, _ in S.WRITERS] == ["Fable", "Astra", "Grok"])

CALLS = []
FIX = json.dumps({"summary": "s", "edits": [], "new_files": []})
def refusing_fable(system, user):
    CALLS.append("Fable"); claude_cache.LAST.clear(); claude_cache.LAST.update(stop="refusal", out=0); return ""
def erroring(name):
    def call(system, user): CALLS.append(name); raise RuntimeError(name + " unavailable")
    return call
def answering(name):
    def call(system, user): CALLS.append(name); return FIX
    return call

row = {"id": "SF-00000001", "what": "a named retrieval route fallback for a held question", "events": []}
plan, _ = S.plan_fix(row, root=ROOT, writers=[("Fable", refusing_fable), ("Astra", answering("Astra")), ("Grok", answering("Grok"))])
check("Fable refusing, Astra writes the fix", plan.get("summary") == "s" and row.get("written_by") == "Astra"
      and CALLS == ["Fable", "Astra"], (CALLS, row.get("written_by")))
check("Fable's refusal is kept as what it was", (row.get("fable_failure") or {}).get("stop_reason") == "refusal", row.get("fable_failure"))
check("and the fix's record says who took it over", "Astra is writing it" in json.dumps(row), json.dumps(row)[:300])

CALLS.clear()
S.ask_json("sys", "repair", row, writers=[("Fable", refusing_fable), ("Astra", answering("Astra")), ("Grok", answering("Grok"))])
check("a repair goes to whoever wrote the fix, without asking Fable again", CALLS == ["Astra"], CALLS)

CALLS.clear(); row2 = {"id": "SF-00000002", "what": "x" * 20}
S.ask_json("sys", "u", row2, writers=[("Fable", erroring("Fable")), ("Astra", erroring("Astra")), ("Grok", answering("Grok"))])
check("Fable and Astra both down, Grok writes it", row2.get("written_by") == "Grok" and CALLS == ["Fable", "Astra", "Grok"], CALLS)

CALLS.clear(); row3 = {"id": "SF-00000003", "what": "x" * 20}
try:
    S.ask_json("sys", "u", row3, writers=[("Fable", refusing_fable), ("Astra", erroring("Astra")), ("Grok", erroring("Grok"))])
    raised = ""
except Exception as exc:
    raised = str(exc)
check("when none can, it says so and names each", "no writer answered" in raised and "Fable" in raised
      and "Astra unavailable" in raised and "Grok unavailable" in raised, raised)

CALLS.clear(); row4 = {"id": "SF-00000004", "what": "x" * 20}
def bad(system, user): CALLS.append("Fable"); return "I would rather explain in prose."
S.ask_json("sys", "u", row4, writers=[("Fable", bad), ("Astra", answering("Astra")), ("Grok", answering("Grok"))])
check("an answer with no JSON falls through too", row4.get("written_by") == "Astra", row4)

src = open(os.path.join(REPO, "scripts", "study_fix.py")).read()
check("the commit names who wrote the fix", 'row["what"][:400], row.get("written_by") or "Fable")' in src)
try:
    S.ask_json("sys", "u", {"id": "SF-5", "what": "x" * 20}, ask=lambda s, u: "")
    one = False
except ValueError as exc:
    one = "did not answer with JSON" in str(exc)
check("one writer given: its own error, unchanged", one)
check("nothing opened a socket", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
