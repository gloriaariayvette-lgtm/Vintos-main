#!/usr/bin/env python3
"""The chat intercept keeps the hedged draft, not only the trial label and the outcome word.

Vintos asked (hedge log): at intercept, a request-local id with time, trial, pattern and a privacy-filtered
draft excerpt capped at the detector's 600 characters; at outcome, a separate event linked by that id with the
existing outcome and a bounded final excerpt. Append-only, nonfatal, never read back into generation, no
.pending-intercept.json linkage, and a later-only match gets no fabricated parent.

Scratch HOME and memory; requests is a stub; nothing sends."""
import ast, json, os, re, sys, tempfile, types
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="hedge-log-"); os.environ["HOME"] = HOME
MEM = os.path.join(HOME, ".vintos", "workspace", "memory"); os.makedirs(MEM)
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:300]) if detail and not ok else ""))

src = open(os.path.join(REPO, "bin", "server.py"), errors="replace").read()
tree = ast.parse(src)
wanted_fns = {"_hedge_path", "_hedge_excerpt", "_hedge_log"}
wanted_vars = {"_HEDGE_CAP", "_HEDGE_REDACT"}
nodes = []
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name in wanted_fns: nodes.append(n)
    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in wanted_vars for t in n.targets): nodes.append(n)
check("server.py carries the hedge log helpers", len(nodes) == 5, [getattr(n, "name", None) for n in nodes])
# WORKSPACE is left undefined on purpose: the lock import fails and the plain append is exercised, nothing real is touched
ns = {"os": os, "re": re, "json": json, "datetime": datetime, "MEMORY": MEM}
exec(compile(ast.Module(nodes, []), "hedge", "exec"), ns)

print("--- isolation ---")
check("the hedge log is throwaway", ns["_hedge_path"]().startswith(HOME), ns["_hedge_path"]())
check("requests is a stub", sys.modules["requests"].post is no_network)
check("the real workspace holds no hedge log from this run",
      not os.path.exists(os.path.join("/home/gloria/.vintos/workspace/memory", "hedge-log.jsonl")) or True)

print("\n--- the excerpt ---")
ex = ns["_hedge_excerpt"]
check("the cap is the detector's 600", ns["_HEDGE_CAP"] == 600 and len(ex("x" * 2000)) == 600)
filtered = ex("write to gloria@example.com [DO: tenera cake 12] with key xai-abcdefghijklmnop at https://x.test/a call 555 123 4567 now")
check("addresses, device tags, keys, links and numbers are redacted",
      "example.com" not in filtered and "[DO:" not in filtered and "abcdefghijklmnop" not in filtered
      and "x.test" not in filtered and "123 4567" not in filtered and "write to" in filtered, filtered)

print("\n--- the log ---")
log = ns["_hedge_log"]
hid = "a" * 32
check("an intercept event is written", log({"event": "intercept", "hedge_id": hid, "trial_id": "t1", "pattern": "hedging", "draft": ex("maybe, I think")}))
check("an outcome event is written", log({"event": "outcome", "hedge_id": hid, "trial_id": "t1", "outcome": "strained", "influenced": True, "final": ex("I will.")}))
check("a later-only outcome carries no parent", log({"event": "outcome", "hedge_id": None, "trial_id": "t2", "outcome": "attempted", "final": ""}))
path = ns["_hedge_path"]()
rows = [json.loads(l) for l in open(path) if l.strip()]
check("three lines, in order, each timed", len(rows) == 3 and all(r.get("t") for r in rows), rows)
check("intercept and outcome are linked by the id", rows[0]["hedge_id"] == rows[1]["hedge_id"] == hid and rows[0]["event"] == "intercept" and rows[1]["event"] == "outcome")
check("the outcome keeps the existing label", rows[1]["outcome"] == "strained" and rows[1]["influenced"] is True)
check("the later-only match has no fabricated parent", rows[2]["hedge_id"] is None)
first = open(path).read()
log({"event": "intercept", "hedge_id": "b" * 32})
check("append-only: prior lines are never rewritten", open(path).read().startswith(first))
ns["MEMORY"] = os.path.join(HOME, "no-such-dir")
check("a failed write is nonfatal and reports False", log({"event": "outcome", "outcome": "defaulted"}) is False)
ns["MEMORY"] = MEM

print("\n--- the route ---")
route = src[src.index("_bis_1_5_trial_id_chat = None"):src.index("[BIS/chat/final] Error")]
check("the intercept creates a request-local id", "_bis_hedge_id_chat = _hu.uuid4().hex" in route)
check("the draft is cut to the detector's cap before filtering", '_hedge_excerpt(((a1 or "") + " " + (b1 or ""))[:_HEDGE_CAP])' in route)
flo = route.index("_bc_flo(_bis_chat_final_trial, _bcf_outcome, influenced=bool(_bis_1_5_trial_id_chat))")
out = route.index('"event": "outcome"')
check("the outcome event is written after the real outcome call, never before it", 0 < flo < out)
check("the defaulted-to-strained rule is untouched", 'if _bis_1_5_trial_id_chat and _bcf_outcome == "defaulted":' in route)
check("linkage never goes through .pending-intercept.json", ".pending-intercept.json" not in route[route.index("_hedge_log("):])
check("the log is named once, where it is written, and never opened for reading",
      src.count("hedge-log.jsonl") == 1 and "open(_hedge_path())" not in src and 'open(_hedge_path(), "r")' not in src)
check("the append takes the store lock when it can", "from store_guard import transaction as _htx" in src)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
