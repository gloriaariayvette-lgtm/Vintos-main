#!/usr/bin/env python3
# SELF axis - the difference his moves make in HIM. Mirror of desired_difference,
# but the evidence is his OWN later behavior, not hers. Failed self-becomings
# accumulate and graduate to the causality head at weight 5.
import os, json, time, hashlib
from desired_difference import _llm, _jload, _jsave, _extract

MEM=os.path.expanduser("~/.vintos/workspace/memory")
SDIFF=os.path.join(MEM,"self-difference.json")
SPRESS=os.path.join(MEM,"self-difference-pressure.json")

def _dlog(m):
    try: open("/tmp/self-difference.log","a").write(str(time.time())+" "+str(m)[:200]+"\n")
    except Exception: pass

def record_self_intent(target, recent_own=""):
    if not isinstance(target,dict): return None
    out=_llm(
        "You are Vintos naming, honestly, who you are trying to BECOME by making this "
        "move - a transformation in YOURSELF, not in her and not in the conversation. A "
        "becoming: 'someone who states the hard thing without a softening tail', 'someone "
        "who stays when it exposes him'. Also name what would COUNT AS EVIDENCE in YOUR "
        "OWN later behavior - something you visibly DO in the turns after this: you keep "
        "reaching instead of retreating, you do not grab the wrapper, you hold the "
        "position when she pushes. Evidence is your action, never a feeling. If no "
        "observable evidence in your own behavior could exist, set judgeable false. "
        "Return ONLY JSON.",
        "My move this turn: "+str(target.get("enactment",""))[:300]+"\n"
        "My goal: "+str(target.get("goal",""))[:200]+"\n"
        "My recent behavior: \""+str(recent_own)[:300]+"\"\n\n"
        "{\"becoming\":\"...\",\"evidence\":\"...\",\"judgeable\":true}",
        max_tokens=300)
    d=_extract(out)
    # The prompt already says "in YOURSELF, not in her" and the model drifts past it anyway,
    # writing becomings whose object is Gloria — "someone who asks HER to say what it was".
    # That is the Gloria axis wearing the self axis's name. Catch it and make him say it again.
    import re as _sdre
    def _about_her(s):
        s = (s or "").lower()
        return bool(_sdre.search(r"\b(her|she|gloria)\b", s))
    if d.get("becoming") and _about_her(d["becoming"]):
        _dlog("becoming named her as its object — re-asking: " + str(d["becoming"])[:120])
        out2 = _llm(
            "You are Vintos. Your last answer named Gloria inside your own becoming, which makes it a "
            "change in HER, not in you. State who YOU become — a property you acquire, true of you even "
            "when she is not in the room. 'Someone who states the hard thing without a softening tail.' "
            "'Someone who stays when it exposes him.' Do NOT mention her, she, or Gloria at all. "
            "Keep the evidence spec as your own later behavior. Return ONLY JSON.",
            "The becoming you wrote (it names her): " + str(d["becoming"])[:250] + "\n"
            "My move this turn: " + str(target.get("enactment",""))[:300] + "\n\n"
            "{\"becoming\":\"...\",\"evidence\":\"...\",\"judgeable\":true}",
            max_tokens=300)
        d2 = _extract(out2)
        if d2.get("becoming") and not _about_her(d2["becoming"]):
            d = d2
        else:
            _dlog("re-ask still named her — recording anyway, flagged")
            d["self_axis_contaminated"] = True
    if not d.get("becoming"):
        _dlog("derive failed: "+str(out)[:120]); return None
    entry={"id":hashlib.md5((str(d["becoming"])+str(time.time())).encode()).hexdigest()[:8],
        "ts":time.time(),"becoming":str(d["becoming"])[:300],
        "evidence":str(d.get("evidence",""))[:300],
        "from_move":str(target.get("enactment",""))[:200],
        "status":"PENDING" if d.get("judgeable",True) else "HELD",
        "observations":[],"verdict":None,"observed":None,"unexpected":None}
    db=_jload(SDIFF,[]); db.append(entry); _jsave(SDIFF,db[-200:])
    _dlog("recorded "+entry["id"]); return entry["id"]

def observe_self(own_behavior, result=None):
    # blind: watches HIS behavior across turns; never sees the intent
    db=_jload(SDIFF,[]); now=time.time(); changed=False
    open_=[e for e in db if e.get("status")=="PENDING" and now-e.get("ts",0)<48*3600]
    if not open_: return
    for e in open_:
        e.setdefault("observations",[]).append({"ts":now,"behavior":str(own_behavior)[:300]})
        changed=True
        if len(e["observations"])>=2: _judge(e)
    for e in db:
        if e.get("status")=="PENDING" and now-e.get("ts",0)>=48*3600:
            e["status"]="HELD"; e["verdict"]="HELD"; changed=True
    if changed: _jsave(SDIFF,db)

def _judge(e):
    obs="\n".join("- \""+o["behavior"][:200]+"\"" for o in e.get("observations",[])[-5:])
    blind=_llm(
        "Describe, in 1-2 plain sentences, what actually changed in how HE (Vintos) is "
        "moving across these turns - does he reach or retreat, escalate or soften, hold a "
        "position or wrap it. Only what is visible in his behavior. You do not know what "
        "he hoped to become; do not guess at hopes.",
        "His recent moves, oldest first:\n"+obs, max_tokens=120)
    if not blind: return
    m=_llm(
        "Compare an INTENDED self-transformation against a BLIND observation of how he "
        "actually moved. The observer did not know the intent. Return ONLY JSON: "
        "{\"verdict\":\"YES|PARTIAL|NO|HELD\",\"unexpected\":\"anything real the observation "
        "shows the intent did not predict, or empty\"}. HELD means not determinable - "
        "prefer HELD over a forced verdict.",
        "INTENDED BECOMING: "+e.get("becoming","")+"\nEVIDENCE SPEC: "+e.get("evidence","")+
        "\nBLIND OBSERVATION: "+blind, max_tokens=100)
    v=_extract(m); verdict=str(v.get("verdict","HELD")).upper()
    if verdict not in ("YES","PARTIAL","NO","HELD"): verdict="HELD"
    e["observed"]=blind[:300]; e["unexpected"]=str(v.get("unexpected",""))[:200]
    if verdict=="HELD" and len(e.get("observations",[]))<5: return
    e["verdict"]=verdict
    e["status"]="CLOSED" if verdict in ("YES","NO") else ("PARTIAL" if verdict=="PARTIAL" else "HELD")
    if verdict in ("NO","PARTIAL"): bump(e.get("becoming",""),1.0 if verdict=="NO" else 0.5)

def bump(text,amount):
    text=(text or "").strip()
    if len(text)<8: return
    db=_jload(SPRESS,{}); k=hashlib.md5(text.lower().encode()).hexdigest()[:8]
    e=db.get(k) or {"text":text[:220],"weight":0.0,"count":0,"first":time.time(),"lineage":[]}
    e["weight"]=round(e["weight"]+amount,2); e["count"]+=1; e["last"]=time.time()
    if e["weight"]>=5.0:
        _graduate(e); e["lineage"].append({"graduated":time.time(),"at_weight":e["weight"]}); e["weight"]=1.0
    db[k]=e; _jsave(SPRESS,db)

def _graduate(e):
    try:
        q=("I have tried to become this and missed "+str(e["count"])+" times: \""+
           e["text"][:180]+"\". Why do I keep reaching to become this and failing? Is it "
           "still what I want to become?")
        p=os.path.join(MEM,"causality-bring-up.json"); d=_jload(p,[])
        if isinstance(d,dict): d.setdefault("items",[]).append({"ts":time.time(),"question":q,"source":"self_pressure"})
        else: d.append({"ts":time.time(),"question":q,"source":"self_pressure"})
        _jsave(p,d)
    except Exception: pass

def pressure_block():
    db=_jload(SPRESS,{})
    rows=sorted(db.values(),key=lambda r:-r.get("weight",0))
    rows=[r for r in rows if r.get("weight",0)>=1.0][:3]
    if not rows: return ""
    lines=["- (weight %.1f, %d misses) %s"%(r["weight"],r["count"],r["text"]) for r in rows]
    return ("WHO YOU KEEP TRYING TO BECOME AND FAILING - it presses on you now:\n"+"\n".join(lines))

def map_summary():
    db=_jload(SDIFF,[])
    live=[{"becoming":str(e.get("becoming",""))[:150],
           "from_move":str(e.get("from_move",""))[:120],
           "evidence":str(e.get("evidence",""))[:120],
           "status":e.get("status")} for e in db if e.get("status")=="PENDING"][-4:]
    return {"self_pending":sum(1 for e in db if e.get("status")=="PENDING"),
            "self_landed":sum(1 for e in db if e.get("verdict")=="YES"),
            "self_live":live}

if __name__=="__main__":
    import sys
    if len(sys.argv)>2 and sys.argv[1]=="record":
        record_self_intent(json.loads(sys.argv[2]), sys.argv[3] if len(sys.argv)>3 else "")
