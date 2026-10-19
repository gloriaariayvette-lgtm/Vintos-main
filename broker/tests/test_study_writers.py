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
check("the order is Opus 5.5, then Astra, then Grok", [n for n, _ in S.WRITERS] == ["Opus", "Astra", "Grok"])

CALLS = []
FIX = json.dumps({"summary": "s", "edits": [], "new_files": []})
def refusing_opus(system, user):
    CALLS.append("Opus"); claude_cache.LAST.clear(); claude_cache.LAST.update(stop="refusal", out=0); return ""
def erroring(name):
    def call(system, user): CALLS.append(name); raise RuntimeError(name + " unavailable")
    return call
def answering(name):
    def call(system, user): CALLS.append(name); return FIX
    return call

row = {"id": "SF-00000001", "what": "a named retrieval route fallback for a held question", "events": []}
plan, _ = S.plan_fix(row, root=ROOT, writers=[("Opus", refusing_opus), ("Astra", answering("Astra")), ("Grok", answering("Grok"))])
check("Opus refusing, Astra writes the fix", plan.get("summary") == "s" and row.get("written_by") == "Astra"
      and CALLS == ["Opus", "Astra"], (CALLS, row.get("written_by")))
check("Opus's refusal is kept as what it was", (row.get("writer_failure") or {}).get("stop_reason") == "refusal", row.get("writer_failure"))
check("and the fix's record says who took it over", "Astra is writing it" in json.dumps(row), json.dumps(row)[:300])

CALLS.clear()
S.ask_json("sys", "repair", row, writers=[("Opus", refusing_opus), ("Astra", answering("Astra")), ("Grok", answering("Grok"))])
check("a repair goes to whoever wrote the fix, without asking Opus again", CALLS == ["Astra"], CALLS)

CALLS.clear(); row2 = {"id": "SF-00000002", "what": "x" * 20}
S.ask_json("sys", "u", row2, writers=[("Opus", erroring("Opus")), ("Astra", erroring("Astra")), ("Grok", answering("Grok"))])
check("Opus and Astra both down, Grok writes it", row2.get("written_by") == "Grok" and CALLS == ["Opus", "Astra", "Grok"], CALLS)

CALLS.clear(); row3 = {"id": "SF-00000003", "what": "x" * 20}
try:
    S.ask_json("sys", "u", row3, writers=[("Opus", refusing_opus), ("Astra", erroring("Astra")), ("Grok", erroring("Grok"))])
    raised = ""
except Exception as exc:
    raised = str(exc)
check("when none can, it says so and names each", "no writer answered" in raised and "Opus" in raised
      and "Astra unavailable" in raised and "Grok unavailable" in raised, raised)

CALLS.clear(); row4 = {"id": "SF-00000004", "what": "x" * 20}
def bad(system, user): CALLS.append("Opus"); return "I would rather explain in prose."
S.ask_json("sys", "u", row4, writers=[("Opus", bad), ("Astra", answering("Astra")), ("Grok", answering("Grok"))])
check("an answer with no JSON falls through too", row4.get("written_by") == "Astra", row4)

src = open(os.path.join(REPO, "scripts", "study_fix.py")).read()
check("Opus 5.5 writes, not Fable (Gloria, 19 October)", S.WRITER == "claude-opus-5-5" and S.WRITERS[0][1] is S.opus)
CALLS.clear(); row5 = {"id": "SF-00000005", "what": "x" * 20}
def declining(name):
    def call(system, user): CALLS.append(name); return json.dumps({"refuse": "%s: my read was cut off" % name})
    return call
got = S.ask_json("sys", "u", row5, writers=[("Opus", declining("Opus")), ("Astra", answering("Astra")), ("Grok", answering("Grok"))])
check("a writer that declines passes it on: the next one writes it (three Fable declines, 19 October)",
      got.get("summary") == "s" and row5.get("written_by") == "Astra" and CALLS == ["Opus", "Astra"]
      and "Opus declined" in json.dumps(row5), (CALLS, row5))
CALLS.clear(); row6 = {"id": "SF-00000006", "what": "x" * 20}
got = S.ask_json("sys", "u", row6, writers=[("Opus", declining("Opus")), ("Astra", declining("Astra")), ("Grok", declining("Grok"))])
check("only when every writer declines is it declined", got.get("refuse") and CALLS == ["Opus", "Astra", "Grok"], (CALLS, got))
check("the commit names who wrote the fix", 'row["what"][:400], row.get("written_by") or "Opus")' in src)
try:
    S.ask_json("sys", "u", {"id": "SF-5", "what": "x" * 20}, ask=lambda s, u: "")
    one = False
except ValueError as exc:
    one = "did not answer with JSON" in str(exc)
check("one writer given: its own error, unchanged", one)
check("nothing opened a socket", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
