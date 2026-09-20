#!/usr/bin/env python3
"""Desktop chat control: scratch stores, stubbed model/process/desktop, no sender or network."""
import importlib.util, json, os, sys, tempfile, types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
tmp = tempfile.TemporaryDirectory(); ws = Path(tmp.name) / "workspace"; (ws / "memory").mkdir(parents=True)
os.environ["SPARK_WORKSPACE"] = str(ws)
spec = importlib.util.spec_from_file_location("desktop_control", ROOT / "scripts" / "desktop_control.py")
dc = importlib.util.module_from_spec(spec); spec.loader.exec_module(dc); sys.modules["desktop_control"] = dc
checks=[]
def check(name, ok, detail=""):
    checks.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -- " + str(detail)) if detail and not ok else ""))

check("every store is scratch", all(str(Path(p)).startswith(tmp.name) for p in
      (dc.ROOT, dc.STORE, dc.EVENTS, dc.CHAT, dc.AVATAR_CHAT, dc.CANON, dc.CHAT_LOCK)))
check("start syntax is explicit", dc.parse_command("/desktop-control to choose two desserts on DoorDash")["commerce"])
check("ordinary talk cannot start it", dc.parse_command("could you use the desktop?") is None)
check("approval and stop are distinct", dc.parse_command("/desktop-control approve")["kind"] == "approve" and
      dc.parse_command("/desktop-control stop")["kind"] == "stop")
check("prompt promises work after the reply", "after this delivered reply" in dc.prompt_block(dc.parse_command("/desktop-control to open notes")))

calls=[]
class DA:
    @staticmethod
    def start_task(task, max_steps=60, extra_env=None):
        calls.append((task, extra_env)); return {"accepted":True,"job_id":"JOB1","state":{"status":"running"}}
    @staticmethod
    def request_stop(): return {"status":"stopping","job_id":"JOB1"}
    @staticmethod
    def read_state(): return {"status":"completed","job_id":"JOB1","reason":"visible result"}
sys.modules["desktop_agent"] = DA
class Proc:
    def __init__(self,*a,**k): self.pid=1
dc.RUNNER = Proc
dc._page_text = lambda: "Sweet Place\nChocolate cake\nLemon tart\nDelivery 35-45 min\nTotal $31.42"
dc._model = lambda prompt, max_tokens=300: json.dumps({"restaurant":"Sweet Place","items":["Chocolate cake","Lemon tart"],"eta":"35-45 min","total":"$31.42","note":"I chose the two that looked best."})

out=dc.start_from_chat("/desktop-control to order two desserts from a restaurant you choose on DoorDash", "I'll find us something.")
rid=out["request_id"]
check("the job starts after chat", out["accepted"] and "PREPARATION ONLY" in calls[0][0] and calls[0][1] is None)
rec=dc.settle(rid, {"status":"completed","job_id":"JOB1","reason":"cart visibly ready"})
check("completion becomes a quoted proposal", rec["state"] == "awaiting_approval" and rec["quote"]["total"] == "$31.42")
hist=json.load(open(dc.CHAT)); canon=[json.loads(x) for x in open(dc.CANON)]
check("one factual double text reaches both chat records", len(hist)==1 and hist[0]["source"]=="desktop-control" and
      "35-45 min" in hist[0]["content"] and "$31.42" in hist[0]["content"] and canon[0]["surface"]=="chat/full")
dc.settle(rid, {"status":"completed","job_id":"JOB1","reason":"cart visibly ready"})
check("settlement is idempotent", len(json.load(open(dc.CHAT))) == 1)

avatar=dc.start_from_chat("/desktop-control to open the dessert menu", "I'll take a look.", surface="avatar")
dc.settle(avatar["request_id"], {"status":"completed","job_id":"JOB1","reason":"menu opened"})
avhist=json.load(open(dc.AVATAR_CHAT)); canon=[json.loads(x) for x in open(dc.CANON)]
check("avatar work double-texts the avatar surface", len(avhist)==1 and
      avhist[0]["desktop_request_id"]==avatar["request_id"] and canon[-1]["surface"]=="avatar")
check("avatar settlement does not leak into main history", len(json.load(open(dc.CHAT))) == 1)

approved=dc.start_from_chat("/desktop-control approve " + rid, "Go on, then.")
check("chat approval starts the exact checkout job", approved["accepted"] and calls[-1][1] == {"VINTOS_DESKTOP_APPROVAL_ID":rid})
page="Sweet Place Chocolate cake Lemon tart Delivery 35-45 min Total $31.42"
ok,why=dc.authorize_purchase_click(rid,"Place order",page)
again,_=dc.authorize_purchase_click(rid,"Place order",page)
check("approval authorizes exactly one matching click", ok and not again, why)

# A fresh proposal must refuse when any quoted fact disappeared from the current page.
db=dc._load(); copy=dict(db[rid]); copy.update({"id":"desk-mismatch","state":"approval_granted","approval_consumed":False}); db[copy["id"]]=copy; dc._atomic(dc.STORE,db)
ok,why=dc.authorize_purchase_click("desk-mismatch","Place order","Sweet Place Chocolate cake Total $99.00")
check("a changed quote consumes nothing", not ok and "no longer shows" in why and not dc._load()["desk-mismatch"]["approval_consumed"])

server=(ROOT/"bin/server.py").read_text(); browser=(ROOT/"scripts/browser_agent.py").read_text()
check("the real chat route parses and starts the command", "_desktop_control.parse_command(message)" in server and
      "_desktop_control.start_from_chat(message, reply" in server)
check("avatar test mode is snapshotted onto the turn before any writer runs",
      "_test_turn = bool(_test_mode_active())" in server and
      "_tc.begin(_counterpart_text, _surface, test_mode=_test_turn)" in server)
check("avatar history and desktop execution obey the same immutable turn mode",
      'if _surface != "reelroom" and not _test_turn:' in server and
      "if _desktop_command and _desktop_control is not None and not _test_turn:" in server)
check("avatar route owns explicit desktop work and its same-surface receipt",
      '_surface == "avatar"' in server and 'surface="avatar"' in server and
      'avatar-overlay-chat.json' in dc.__loader__.get_source("desktop_control"))
check("the purchase guard calls the one-use authority", "authorize_purchase_click(approval, label, text)" in browser)
check("the public desktop route cannot inject authority", 'start_task(str(body.get("task", ""))' in (ROOT/"scripts/desktop_agent.py").read_text())
check("all process and model boundaries were stubbed", dc.RUNNER is Proc and dc._model.__module__ == "__main__")

print("\n%d/%d" % (sum(checks),len(checks)))
raise SystemExit(0 if all(checks) else 1)
