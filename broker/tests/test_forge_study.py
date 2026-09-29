#!/usr/bin/env python3
"""The Forge asks the Study before it builds (Gloria, 2026-09-29).

A computer-use want reached the Forge as an ability he lacked, while his desktop-control code already
existed and failed. Every Forge request is now studied first: Fable orchestrates, Grok reads, through the
Study's own read/grep. Scratch workspace; the models, the Study room, ntfy and the Forge are stubs.
"""
import json, os, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-forge-study-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
sys.path.insert(0, os.path.join(REPO, "scripts"))

def _no_network(*a, **k): raise AssertionError("this suite must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(post=_no_network, get=_no_network)
import urllib.request as _ur
_ur.urlopen = _no_network

import forge_study as FS, skill_forge as SF, forge_house as FH

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:500]) if detail and not ok else ""))

check("every store is in the scratch workspace", FS.STUDIES.startswith(HOME) and SF.PROPOSALS.startswith(HOME))

class Room:
    """The Study's read/grep, stubbed with his desktop-control code."""
    calls = []
    def code_map(self): return "scripts/desktop_control.py\nscripts/desktop_winpy.py"
    def do_grep(self, pattern):
        self.calls.append(("grep", pattern)); return "scripts/desktop_control.py:12: backend = WinPyBackend()"
    def do_read(self, rel, start=1):
        self.calls.append(("read", rel)); return "   40  subprocess.run(['python.exe', ...])  # FileNotFoundError on this host"

turns = []
def orchestrate(system, user):
    turns.append(user)
    if len(turns) == 1:
        return json.dumps({"done": False, "tasks": [{"grep": "WinPyBackend", "why": "which backend runs"},
                                                     {"read": "scripts/desktop_winpy.py", "start": 1, "why": "how it starts python.exe"}]}), "fable"
    return json.dumps({"done": True, "already_have": True, "where": [{"file": "scripts/desktop_winpy.py", "line": 40, "what": "python.exe not found"}],
                       "fails_because": "python.exe is not on the service's PATH", "fix": "use the full path to python.exe",
                       "needs_from_gloria": "install pyautogui on the Windows side", "summary": "He already has desktop control; it cannot start Windows Python."}), "fable"
grok = []
def subagent(system, user):
    grok.append(user); return "desktop_winpy.py:40 runs python.exe; the report shows FileNotFoundError."

proposal = {"id": "SK-00000001", "state": "proposed", "capability": "computer_use", "why": "Blocked capability computer_use",
            "origin": {"want_id": "w1", "want": "I want to use the computer in front of me", "source": "skill_surfing"}}
f = FS.investigate(proposal, orchestrate=orchestrate, subagent=subagent, room=Room())
check("Fable plans, Grok reads what the Study pulls, Fable concludes",
      f["state"] == "done" and f["models"] == ["fable", "grok"] and len(grok) == 2
      and Room.calls == [("grep", "WinPyBackend"), ("read", "scripts/desktop_winpy.py")], f)
check("the subagent's reports reach the orchestrator", "FileNotFoundError" in turns[-1])
check("it finds that he already has it and where it fails",
      f["already_have"] is True and f["where"][0]["line"] == 40 and "PATH" in f["fails_because"], f)
row = FS.row_text(f)
check("the findings are written into the Forge request", "already has it: True" in row and "desktop_winpy.py:40" in row
      and "full path" in row, row)

def stubborn(system, user):
    turns.append(user)
    if "No more reading" in user:
        return json.dumps({"done": True, "already_have": False, "summary": "not found"}), "astra"
    return json.dumps({"done": False, "tasks": [{"grep": "x", "why": "y"}]}), "astra"
turns.clear()
f2 = FS.investigate(proposal, orchestrate=stubborn, subagent=subagent, room=Room())
check("reading is bounded: after %d rounds it must conclude" % FS.ROUNDS,
      f2["rounds"] == FS.ROUNDS and f2["state"] == "done" and "astra" in f2["models"], f2)

# tend: one study a pass, the request held back until studied, then sent with the findings; she is told.
json.dump([dict(proposal)], open(SF.PROPOSALS, "w"))
json.dump([{"id": "w1", "want": "I want to use the computer in front of me", "source": "skill_surfing"}],
          open(os.path.join(SF.MEMORY, "current-wants.json"), "w"))
told = []
FS.investigate = lambda p, **k: dict(f)
FS.notify = lambda findings, post=None: told.append(findings)
sent = []
FH.request = lambda path, body, transport=None: sent.append((path, body)) or []
FH.sync()
rows = [r for p, b in sent if p == "/api/gaps-sync" for r in b["rows"]]
check("the request reached the Forge with the Study's findings in it",
      len(rows) == 1 and "THE STUDY READ HIS CODE FIRST" in rows[0]["intent"] and "desktop_winpy.py:40" in rows[0]["intent"], rows)
check("Gloria was sent the Forge request with what was found", len(told) == 1 and told[0]["capability"] == "computer_use")
check("the proposal keeps the study", (SF._load()[0].get("study") or {}).get("already_have") is True)

json.dump([dict(proposal, id="SK-00000002", capability="read_logs")], open(SF.PROPOSALS, "w"))
FS.investigate = lambda p, **k: (_ for _ in ()).throw(RuntimeError("no orchestrator"))
sent.clear(); FH.sync()
check("a study that cannot run does not hold the request forever: it goes on, marked failed",
      (SF._load()[0].get("study") or {}).get("state") == "failed" and any(p == "/api/gaps-sync" and b["rows"] for p, b in sent))

json.dump([dict(proposal, id="SK-00000003", capability="x1")], open(SF.PROPOSALS, "w"))
FS._save(FS.LEDGER, {"date": __import__("datetime").date.today().isoformat(), "count": FS.STUDIES_PER_DAY})
sent.clear(); FH.sync()
check("past the day's studies, an unstudied request waits for tomorrow rather than going unread",
      not any(p == "/api/gaps-sync" and b["rows"] for p, b in sent) and not SF._load()[0].get("study"), sent)

check("nothing reached the world: models, the Study room, ntfy and the Forge were stubs",
      sys.modules["requests"].post is _no_network and FH.request.__name__ == "<lambda>")
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
