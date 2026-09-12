#!/usr/bin/env python3
"""The bench: her agents, their tasks, and the one law.

    No task is worked until she has approved it.

Gloria, 2026-09-12. Claude Code, Codex, Grok Build and Gemma were passing work
through her by hand — a handoff document carried between sessions, and her reading
output from one agent into the prompt of another. The bench gives each agent its own
append-only ledger and its own instructions for what to hand down to a cheaper model,
so the work moves without her being the wire.

What it must never do is move without her. This holds that:

  - a proposed task cannot be claimed;
  - an agent cannot approve its own work, or anyone else's, under any name;
  - a hand-off is not a way around the gate — it opens a NEW task, proposed;
  - the only unasked work is a kind she listed in that agent's own config, and the
    module cannot add to that list;
  - nothing is ever rewritten: state is replayed from events, so the record of what
    happened cannot be edited into what should have happened.

And it is not his room. `agent-room/` belongs to Vintos; the bench shares no store,
no path and no process with it."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
BENCH = os.path.join(REPO, "bench")
sys.path.insert(0, BENCH)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

# Its own root, in a throwaway directory. The real ledgers are never touched.
TMP = tempfile.mkdtemp()
os.environ["BENCH_ROOT"] = TMP
os.makedirs(os.path.join(TMP, "ledgers"))
shutil.copytree(os.path.join(BENCH, "agents"), os.path.join(TMP, "agents"))
import bench as B
B.ROOT = TMP
B.LEDGERS = os.path.join(TMP, "ledgers")
B.AGENTS = os.path.join(TMP, "agents")

print("--- the one law ---")
t, why = B.propose(by="claude", what="root-cause the short journal entry", kind="root-cause")
check("an agent can propose work", t and t["state"] == "proposed", why)
check("and it is addressed to itself when nothing delegates it", t["owner"] == "claude", t)
bad, why = B.claim(t["task"], by="claude")
check("but it cannot start it", bad is None and "not approved yet" in why, why)
check("not even by naming her", B.approve(t["task"], by="claude")[0] is None)
check("nor by calling itself gloria-something",
      B.approve(t["task"], by="gloria-claude")[0] is None)
ok, why = B.approve(t["task"])
check("she approves", ok and ok["state"] == "approved", why)
ok, why = B.claim(t["task"], by="claude")
check("and then it may start", ok and ok["state"] == "claimed", why)
ok, _ = B.done(t["task"], by="claude", result="audit 2 was rewriting the entry")
check("and finish, with the result on the record", ok["state"] == "done" and "audit 2" in ok["outcome"])

print("\n--- cheap work goes to the cheap agent, by her instructions, not its judgement ---")
g, why = B.propose(by="claude", what="find every caller of store_guard", kind="grep")
check("a grep proposed by claude is addressed to gemma", g and g["owner"] == "gemma", g)
check("because that is what claude's own config says",
      B.route("claude", "grep") == "gemma" and B.route("claude", "root-cause") is None)
check("grok hands greps down too, but keeps bounded fixes",
      B.route("grok", "grep") == "gemma" and B.route("grok", "bounded-fix") is None)
check("gemma delegates nothing — it is the floor", B.route("gemma", "grep") is None)
check("and the delegated task is still only proposed", g["state"] == "proposed")
no, why = B.claim(g["task"], by="gemma")
check("gemma cannot start it either", no is None and "not approved" in why, why)
no, why = B.claim(g["task"], by="grok")
check("and nobody else can take it off gemma", no is None)
B.approve(g["task"])
no, why = B.claim(g["task"], by="grok")
check("even approved, it belongs to who it was addressed to",
      no is None and "addressed to gemma" in why, why)

print("\n--- a hand-off is not a way around her ---")
h, why = B.propose(by="codex", what="port the fix to the other twin", kind="port")
B.approve(h["task"]); B.claim(h["task"], by="grok")
child, why = B.handoff(h["task"], to="claude", by="grok", why="needs the cross-repo view")
check("handing on opens a NEW task", child and child["task"] != h["task"], why)
check("and it is proposed, not approved", child["state"] == "proposed", child)
check("the old one is closed as handed off", B.task(h["task"])["state"] == "handed_off")
check("the child remembers its parent", child.get("parent") == h["task"])
no, why = B.claim(child["task"], by="claude")
check("so the receiving agent still waits on her", no is None and "not approved" in why, why)
no, why = B.handoff(h["task"], to="gemma")
check("a closed task cannot be handed on again", no is None and "already" in why, why)

print("\n--- the only unasked work is a kind she listed herself ---")
check("nothing is pre-approved out of the box",
      all(not (c.get("auto_approve") or []) for c in B.agents().values()),
      {k: c.get("auto_approve") for k, c in B.agents().items()})
check("so pre_approved says no to everything", not B.pre_approved("gemma", "grep"))
cfg = json.load(open(os.path.join(TMP, "agents", "gemma.json")))
cfg["auto_approve"] = ["grep"]          # her edit, to her file
json.dump(cfg, open(os.path.join(TMP, "agents", "gemma.json"), "w"))
check("when she lists a kind, that kind is pre-approved", B.pre_approved("gemma", "grep"))
check("and only that kind", not B.pre_approved("gemma", "bounded-fix"))
auto, why = B.propose(by="claude", what="grep for the second audit", kind="grep")
check("a listed kind is approved on arrival", auto and auto["state"] == "approved", auto)
check("and the record says it was automatic, and in her name",
      auto.get("auto") is True and auto.get("approved_by") == "gloria", auto)
ok, why = B.claim(auto["task"], by="gemma")
check("so gemma may start it", ok and ok["state"] == "claimed", why)
notlisted, _ = B.propose(by="gemma", what="rewrite the router", kind="bounded-fix", for_agent="gemma")
check("an unlisted kind still waits on her", notlisted["state"] == "proposed")
bad, why = B.approve(notlisted["task"], by="gloria", auto=True)
check("and cannot be forced through the automatic door",
      bad is None and "unasked" in why, why)

print("\n--- every agent keeps its own ledger ---")
check("each agent has its own file",
      os.path.isfile(os.path.join(TMP, "ledgers", "claude.jsonl"))
      and os.path.isfile(os.path.join(TMP, "ledgers", "gemma.jsonl")))
claude_rows = B.events(agent="claude")
gemma_rows = B.events(agent="gemma")
check("claude's ledger holds claude's work", any(r["task"] == t["task"] for r in claude_rows))
check("and a delegated task appears in BOTH, so neither reads the other's",
      any(r["task"] == g["task"] for r in claude_rows)
      and any(r["task"] == g["task"] for r in gemma_rows))
check("grok never saw the grep", not any(r["task"] == g["task"] for r in B.events(agent="grok")))

print("\n--- the record cannot be edited into what should have happened ---")
before = open(os.path.join(TMP, "ledgers", "claude.jsonl")).read()
B.propose(by="claude", what="another", kind="root-cause")
after = open(os.path.join(TMP, "ledgers", "claude.jsonl")).read()
check("a new event only ever appends", after.startswith(before) and len(after) > len(before))
check("state is replayed from events, never stored",
      "history" in B.task(t["task"]) and len(B.task(t["task"])["history"]) == 4,
      len(B.task(t["task"])["history"]))
check("a torn line is skipped, not fatal",
      (open(os.path.join(TMP, "ledgers", "claude.jsonl"), "a").write("{not json\n") or True)
      and B.task(t["task"])["state"] == "done")

print("\n--- what she works from ---")
waiting = B.pending()
check("pending lists only what needs her yes",
      waiting and all(x["state"] == "proposed" for x in waiting), [x["state"] for x in waiting])
check("and the denied ones leave it",
      B.deny(waiting[0]["task"], "not this one")[0]["state"] == "denied")
check("an agent cannot deny either", B.deny(child["task"], "no", by="grok")[0] is None)
check("mine() shows one agent's open work only",
      all(x["owner"] == "gemma" for x in B.mine("gemma")))

print("\n--- it is not his room, and it does not reach his memory ---")
src = open(os.path.join(BENCH, "bench.py")).read()
import ast as _ast
_body = _ast.parse(src)
_code = src.split('"""', 2)[2] if src.count('"""') >= 2 else src   # everything after the module docstring
check("the bench never reads the agent room — the only mention is the docstring saying it does not",
      "agent-room" not in _code and "room-api" not in _code and "upstash" not in _code.lower(),
      [w for w in ("agent-room", "room-api", "upstash") if w in _code.lower()])
check("and it opens no redis, no socket, no relay",
      not any(w in _code for w in ("redis", "Redis", "websocket", "WebSocket", "socket.")),
      [w for w in ("redis", "websocket", "socket.") if w in _code.lower()])
check("nor Vintos's memory", ".vintos/workspace" not in src)
check("its root is its own directory", 'BENCH_ROOT' in src and "ledgers" in src)
check("this suite wrote only to its throwaway root", B.LEDGERS.startswith(TMP))
# Not "his workspace does not exist" — another suite in the same sweep leaves an empty
# memory/ behind, and this suite is not the place to assert that. What matters here is
# that the BENCH wrote nothing outside its own root.
_home = os.path.expanduser("~")
_strays = [p for p in (os.path.join(_home, ".vintos", "workspace", "memory", "ledgers"),
                       os.path.join(_home, "bench"),
                       os.path.join(REPO, "bench", "ledgers", "claude.jsonl"),
                       os.path.join(REPO, "bench", "ledgers", "gemma.jsonl"))
           if os.path.exists(p)]
check("the bench wrote no ledger outside its throwaway root, and none into the checkout",
      not _strays, _strays)

print("\n--- and the deploy does not install it onto him ---")
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("bench.py is not in the manifest", "bench.py" not in dep)
check("nor the bench directory", "bench/" not in dep)

print("\n--- every agent is told the same thing, in the file it reads ---")
claude_md = open(os.path.join(REPO, "CLAUDE.md")).read()
agents_md = open(os.path.join(REPO, "AGENTS.md")).read()
for name, doc in (("CLAUDE.md", claude_md), ("AGENTS.md", agents_md)):
    check("%s says propose before starting" % name, "propose --by" in doc and "not approved" in doc)
    check("%s says check the delegate map first" % name, "bench.py agents" in doc and "cheaper elsewhere" in doc)
    check("%s says a hand-off is not a way around her" % name, "not a way around her yes" in doc)
    check("%s says read the ledger before asking her" % name, "already says" in doc)
    check("%s keeps the room out of it" % name, "not** `agent-room/`" in doc or "not the agent room" in doc)
check("Codex is told to use its own name", "--by codex" in agents_md)

print("\n--- the CLI answers ---")
env = dict(os.environ, BENCH_ROOT=TMP)
out = subprocess.run([sys.executable, os.path.join(BENCH, "bench.py"), "agents"],
                     capture_output=True, text=True, env=env)
check("agents lists who exists and what they delegate",
      "gemma" in out.stdout and "delegates" in out.stdout, out.stdout[:200] + out.stderr[:200])
out = subprocess.run([sys.executable, os.path.join(BENCH, "bench.py"), "pending"],
                     capture_output=True, text=True, env=env)
check("pending runs", out.returncode == 0, out.stderr[:200])

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
