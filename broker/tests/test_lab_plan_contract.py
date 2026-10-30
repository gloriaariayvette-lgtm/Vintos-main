#!/usr/bin/env python3
"""The planner's output contract (16 October, after the 10:12 CDT deploy): a replan ended on the refusal ("REFUSED, IT
IS A REPEAT: ... 5nh1 ..."), and the local model answered it as a person asking for help, in prose. Every pass failed
"no JSON object" and the notebook gained nothing. Now every planner request ends on the contract, a prose reply is
asked for once more as JSON, and an over-long prompt loses its oldest context instead of its instructions.
The planner is a stub; scratch HOME; no socket."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-plan-contract-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("the Lab's stores are scratch and sockets are refused", C.ROOT.startswith(HOME) and C.FAULTS.startswith(HOME))

PROSE = ("It appears you are receiving a system error or a \"refusal\" message because the underlying tool has "
         "flagged your request as a duplicate. Here is how to proceed: ### 1. Choose a Different Question")
GOOD = json.dumps({"browse_lane": "protein", "question": "What is the fold of human ISCU?"})
asks = []
def stub(replies):
    def ask(system, prompt, **k):
        asks.append((prompt, k)); return replies.pop(0)
    return ask

C._ask = stub([GOOD])
v = C._plan("Return JSON only.", "TASK\n\nREFUSED, IT IS A REPEAT: structure_evidence for 5nh1. Choose a different question.")
check("a refusal is never the last thing the planner reads: the contract follows it",
      asks[-1][0].endswith(C.PLAN_TAIL) and asks[-1][0].index("REFUSED") < asks[-1][0].index("ONLY the JSON object"), asks[-1][0][-300:])
check("a JSON reply is used as it is", v.get("question") == "What is the fold of human ISCU?", v)

asks.clear(); C._ask = stub([PROSE, GOOD])
v = C._plan("Return JSON only.", "TASK\n\nREFUSED, IT IS A REPEAT: x.")
check("a prose reply is asked for once more, as JSON", len(asks) == 2 and "was prose" in asks[1][0] and v.get("browse_lane") == "protein", asks)
check("the second ask is cooler", asks[1][1].get("temperature") == 0.3, asks[1][1])
faults = [json.loads(l) for l in open(C.FAULTS)] if os.path.exists(C.FAULTS) else []
check("a prose reply the re-ask repaired is not a fault (29 October: ten such faults, all repaired)",
      not any(f["stage"] == "plan_not_json" for f in faults), faults)

asks.clear(); C._ask = stub([PROSE, PROSE])
try:
    C._plan("Return JSON only.", "TASK"); raised = False
except C.ModelJSONError:
    raised = True
check("two prose replies fail the pass, as before (no third model call)", raised and len(asks) == 2)
faults = [json.loads(l) for l in open(C.FAULTS)]
check("and that is written down once, with the prompt's size",
      [f["stage"] for f in faults].count("plan_not_json") == 1
      and any(f["stage"] == "plan_not_json" and f.get("prompt_chars") for f in faults), faults)

asks.clear(); C._ask = stub([GOOD])
long = "OLD CONTEXT " * 10000 + "\n\nChoose ONE protein question. Return its fields."
C._plan("Return JSON only.", long)
sent = asks[-1][0]
check("an over-long prompt keeps its instructions and loses its oldest context",
      len(sent) <= C.PLAN_MAX_CHARS + len(C.PLAN_TAIL) + 64 and "Choose ONE protein question" in sent
      and sent.startswith("[older Lab context cut to fit]"), len(sent))
faults = [json.loads(l) for l in open(C.FAULTS)]
check("and the cut is written down with its sizes",
      any(f["stage"] == "plan_prompt_trimmed" and f.get("prompt_chars") == len(long) for f in faults))

src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
_outside = src.replace(src[src.index("def _plan("):src.index("def _compact_names(")], "")
check("no planner call bypasses the contract", "_json_object(_ask(system," not in _outside)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
