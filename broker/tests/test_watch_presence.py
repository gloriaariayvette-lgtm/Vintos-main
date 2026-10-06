#!/usr/bin/env python3
"""The Watch has a private store and APNs is always stubbed in the suite."""
import json, os, shutil, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import watch_presence as W
import watch_apns as A

R=[]
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:160]) if detail else ""))

tmp=tempfile.mkdtemp(prefix="watch-")
mem=os.path.join(tmp,"memory"); secrets=os.path.join(tmp,"secrets")
os.makedirs(mem); os.makedirs(secrets)
W.MEMORY=mem; W.SECRETS=secrets
W.LATEST=os.path.join(mem,"watch-presence.json")
W.HISTORY=os.path.join(mem,"watch-presence-history.jsonl")
W.REPLIES=os.path.join(mem,"watch-replies.jsonl")
W.MOMENTS=os.path.join(mem,"watch-shared-moments.jsonl")
W.DEVICES=os.path.join(mem,"watch-apns-devices.json")
W.HELD=os.path.join(mem,"watch-held-notifications.jsonl")
W.TOKEN_FILE=os.path.join(secrets,"watch-bearer")
open(W.TOKEN_FILE,"w").write("throwaway-token")
A.RECEIPTS=os.path.join(mem,"watch-delivery-receipts.jsonl")

check("every Watch store is inside the scratch directory",
      all(os.path.commonpath([tmp,p]) == tmp for p in (W.LATEST,W.HISTORY,W.REPLIES,W.MOMENTS,W.DEVICES,W.HELD,W.TOKEN_FILE,A.RECEIPTS)))
check("the suite uses a throwaway bearer", W.authorized("Bearer throwaway-token"))
check("a missing or wrong bearer is refused", not W.authorized("") and not W.authorized("Bearer wrong"))

now=time.time(); iso=W.datetime.fromtimestamp(now,W.timezone.utc).isoformat()
ok,res=W.record({"samples":[
    {"kind":"heart_rate","value":91,"unit":"count/min","observed_at":iso},
    {"kind":"motion","value":"walking","observed_at":iso},
    {"kind":"battery","value":{"level":.72,"state":"unplugged"},"observed_at":iso}], "asleep":False}, now=now)
check("bounded Watch samples are stored separately", ok and res["device"] == "AppleWatch", res)
state=json.load(open(W.LATEST))
check("snapshot carries source, age and estimate wording",
      state["latest"]["heart_rate"]["device"] == "AppleWatch" and
      state["latest"]["heart_rate"]["age_seconds"] == 0 and "estimate" in state["latest"]["heart_rate"])
check("fresh non-charging signals imply probably worn", state["wearing"] == "probably")
check("implausible pulse is refused", not W.record({"samples":[{"kind":"heart_rate","value":500,"observed_at":iso}]},now=now)[0])
check("stale/future observations are refused", not W.record({"samples":[{"kind":"motion","value":"walking","observed_at":"2020-01-01T00:00:00Z"}]},now=now)[0])

charging={"samples":[{"kind":"battery","value":{"level":.8,"state":"charging"},"observed_at":iso}],"asleep":True}
W.record(charging,now=now)
check("charging means not worn and sleep holds a send", W.latest()["wearing"] == "no" and W.should_hold()[0])

ok,rec=W.register_apns({"device_token":"ab"*32,"environment":"development"})
check("APNs registration is bounded and stored 0600", ok and (os.stat(W.DEVICES).st_mode & 0o777) == 0o600,rec)
ok,reply=W.record_reply({"kind":"dictation","text":"I heard it.","message_id":"m1"})
check("a wrist reply lands in its private inbox",ok and json.loads(open(W.REPLIES).readline())["text"]=="I heard it.")
ok,moment=W.record_moment({"state":"started","observed_at":iso})
check("a shared moment has its own private store",ok and json.loads(open(W.MOMENTS).readline())["state"]=="started",moment)
block=W.temporal_block(now=now)
check("Watch facts and wrist words reach temporal memory with estimate wording",
      "Apple Watch update" in block and "Gloria wrote from her Watch: I heard it." in block and
      "not medical facts" in block and "Shared Watch moment: started" in block,block)
check("an old Watch snapshot yields no block so the ring can be fallback",W.temporal_block(now=now+7201)=="")

sends=[]
def fake_transport(url,body,headers,timeout):
    sends.append((url,json.loads(body),dict(headers))); return 200,b"{}"
A._config=lambda path=None:{"team_id":"T","key_id":"K","key_file":__file__,"topic":"dev.vintos.app.watchkitapp"}
A._jwt=lambda config,now=None:"stub-jwt"
held=A.send("Vintos","A line",transport=fake_transport)
check("sleep holds instead of sending",held["state"]=="held" and sends==[],held)
state=W.latest(); state["asleep"]=False; W._atomic(W.LATEST,state)
flushed=A.flush_held(transport=fake_transport)
check("a wake flushes held words through the stub and clears the private queue",
      flushed["sent"]==1 and flushed["remaining"]==0 and open(W.HELD).read()=="",flushed)
sends.clear()
sent=A.send("New song","Turn of the wrist",kind="song",media_url="https://example.test/song.mp3",transport=fake_transport)
check("APNs is stubbed and a song carries its primary-action category",
      sent["state"]=="sent" and len(sends)==1 and sends[0][1]["aps"]["category"]=="VINTOS_SONG",sent)
check("the stub proves no provider client escaped", sends[0][0].startswith("https://api.sandbox.push.apple.com/"))
check("no secret or bearer appears in the payload", "throwaway-token" not in json.dumps(sends[0][1]))
check("all files written by the suite stayed in scratch", not any(p.startswith(os.path.expanduser("~/.vintos")) for p in (W.LATEST,W.HISTORY,W.REPLIES,W.MOMENTS,W.DEVICES,W.HELD,A.RECEIPTS)))
temporal=open(os.path.join(ROOT,"scripts","temporal-context.sh")).read()
check("temporal context prefers Watch and uses ring only as fallback",
      'WATCH_TEMPORAL=' in temporal and 'if [ -n "$WATCH_TEMPORAL" ]' in temporal and
      temporal.index('WATCH_TEMPORAL=') < temporal.index('heart_rate.py'))
routes=open(os.path.join(ROOT,"scripts","watch_routes.py")).read()
check("the wrist feed is bounded to five newest Landings",'source.sent(days=max(1, min(int(days), 30)))[:5]' in routes)
check("Watch words never create Avatar-chat turns",'/api/avatar/chat' not in routes and 'record_reply(body)' in routes)
check("shared moments have a dedicated route",'@routes.post("/api/watch/moment")' in routes)

shutil.rmtree(tmp,ignore_errors=True)
print("\n%d/%d passed"%(sum(R),len(R))); raise SystemExit(0 if all(R) else 1)
