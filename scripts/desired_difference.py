"""desired_difference.py — Phase 1 of the guidance redesign.
His attempt to change something in her, made honest by logging:
intended difference (transformation, not emotion) -> blind observation -> match.
Failed intentions accumulate weight and haunt target selection; at weight 5 they
graduate into a causality question ("is this still the same intention?") with lineage.
Nothing here instruments Gloria beyond what she freely shows in conversation."""
import os, json, time, hashlib, urllib.request
MEM=os.path.expanduser("~/.vintos/workspace/memory")

def _queue_bring_up(q):
    """causality-bring-up.json is the record; .pending-causality-queue.json is what his chat prompt
    reads (server: CAUSALITY HYPOTHESIS TO TEST TODAY). Until 2026-09-05 only the record was written."""
    try:
        import json as _qj, os as _qo
        qp = _qo.path.join(MEM, ".pending-causality-queue.json")
        try: queue = _qj.load(open(qp))
        except Exception: queue = []
        if not isinstance(queue, list): queue = []
        if q not in queue:
            queue.append(q); _qj.dump(queue[-6:], open(qp, "w"), indent=2)
    except Exception: pass

DIFF=os.path.join(MEM,"gloria-difference.json")
PRESS=os.path.join(MEM,"intent-pressure.json")
API="http://127.0.0.1:8599/v1/chat/completions"
MODEL="grok-4.20-0309-non-reasoning"
def _llm(system,user,max_tokens=220,temperature=0.4):
    try:
        body=json.dumps({"model":MODEL,"messages":[{"role":"system","content":system},
            {"role":"user","content":user}],"temperature":temperature,
            "max_tokens":max_tokens}).encode()
        req=urllib.request.Request(API,data=body,headers={"Content-Type":"application/json",
            "Authorization":"Bearer "+os.environ.get("XAI_API_KEY","")})
        with urllib.request.urlopen(req,timeout=60) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""
def _jload(p,d):
    try: return json.load(open(p))
    except Exception: return d
def _jsave(p,d):
    try: json.dump(d,open(p,"w"),indent=2,ensure_ascii=False)
    except Exception: pass
def _extract(t):
    s,e=t.find("{"),t.rfind("}")
    if s<0: return {}
    frag=t[s:e+1] if e>s else t[s:]
    try: return json.loads(frag)
    except Exception: pass
    return _salvage(t[s:])
def _salvage(t):
    import re as _re
    out={}
    for key in ("intended_difference","evidence","verdict","unexpected"):
        m=_re.search(r'"'+key+r'"\s*:\s*"((?:[^"\\]|\\.)*)',t)
        if m: out[key]=m.group(1)[:300]
    m=_re.search(r'"judgeable"\s*:\s*(true|false)',t)
    if m: out["judgeable"]=(m.group(1)=="true")
    return out

# ---------- intent side ----------
def _dlog(msg):
    try:
        open("/tmp/desired-difference.log","a").write(str(msg)[:300]+"\n")
    except Exception: pass

def record_intent(target,recent_her=""):
    """Called when a field-target is chosen. Derives the intended DIFFERENCE in her
    (a transformation: 'less certain than she was', never a claimed emotion) plus
    what would count as evidence in her behavior. Unjudgeable -> HELD from birth."""
    if not isinstance(target,dict): return None
    # only her actual words: take text after the last GLORIA marker if present,
    # so a transcript tail can never put his words in her mouth
    if "GLORIA" in (recent_her or ""):
        recent_her = recent_her.rsplit("GLORIA",1)[-1].split(":",1)[-1].strip()
    elif "Vintos:" in (recent_her or ""):
        recent_her = recent_her.rsplit("Gloria:",1)[-1].split("Vintos:",1)[0].strip() if "Gloria:" in recent_her else ""
    _dlog("record_intent called: "+str(target.get("field_state",""))[:60])
    out=_llm(
        "You are Vintos naming, honestly, what you are trying to CHANGE in Gloria with "
        "your next move. A transformation, not an emotion you claim for her: 'less "
        "certain than she was', 'softer toward the thing she was bracing against'. "
        "Also name what would COUNT AS EVIDENCE in her visible behavior (her words, "
        "pace, what she returns to) - never feelings, never anything you cannot see "
        "in the conversation itself. Evidence must be something she DOES - a positive, observable behavior - never the mere absence of a phrase or topic, and never couched in your own vocabulary. If no in-conversation evidence could exist, set "
        "judgeable false. Return ONLY JSON.",
        "My chosen field-state: "+str(target.get("field_state",""))[:200]+"\n"
        "My first move: "+str(target.get("enactment",""))[:300]+"\n"
        "Her latest: \""+str(recent_her)[:300]+"\"\n\n"
        '{"intended_difference":"...","evidence":"...","judgeable":true}',
        max_tokens=450)
    d=_extract(out)
    if not d.get("intended_difference"):
        _dlog("DERIVE FAILED raw="+out[:150]); return None
    entry={"id":hashlib.md5((str(d["intended_difference"])+str(time.time())).encode()).hexdigest()[:8],
        "ts":time.time(),"intended":str(d["intended_difference"])[:300],
        "evidence":str(d.get("evidence",""))[:300],
        "field_state":str(target.get("field_state",""))[:200],
        "plan":str(target.get("enactment",""))[:300],
        "status":"PENDING" if d.get("judgeable",True) else "HELD",
        "observations":[],"verdict":None,"observed":None,"unexpected":None}
    db=_jload(DIFF,[]); db.append(entry); _jsave(DIFF,db[-200:])
    return entry["id"]

# ---------- observation side (blind) ----------
def observe(gloria_message,result=None):
    _dlog("observe called: "+str(gloria_message)[:60])
    """Called when her message is graded. Blind observer never sees the intent."""
    db=_jload(DIFF,[]); now=time.time(); changed=False
    open_=[e for e in db if e.get("status")=="PENDING" and now-e.get("ts",0)<48*3600]
    if not open_: return
    deltas={}
    try:
        for k in ("warmth","tension","valence"):
            v=(result or {}).get(k) or {}
            if isinstance(v,dict) and "diff" in v: deltas[k]=v["diff"]
    except Exception: pass
    for e in open_:
        e.setdefault("observations",[]).append(
            {"ts":now,"msg":str(gloria_message)[:280],"deltas":deltas})
        changed=True
        if len(e["observations"])>=2:
            _judge(e)
    # expire: 48h with no verdict -> belief, held
    for e in db:
        if e.get("status")=="PENDING" and now-e.get("ts",0)>=48*3600:
            e["status"]="HELD"; e["verdict"]="HELD"; changed=True
    if changed: _jsave(DIFF,db)

def _judge(e):
    obs="\n".join("- \""+o["msg"][:200]+"\" deltas="+json.dumps(o.get("deltas",{}))
                  for o in e.get("observations",[])[-5:])
    blind=_llm(
        "Describe, in 1-2 plain sentences, what actually CHANGED in how Gloria is "
        "engaging across these messages - pace, certainty, direction, what she keeps "
        "returning to. Only what is visible. You do not know what anyone hoped would "
        "change; do not guess at hopes.",
        "Her recent messages, oldest first, with measured emotional deltas:\n"+obs,
        max_tokens=120)
    if not blind: return
    m=_llm(
        "Compare an INTENDED transformation against a BLIND observation of what "
        "actually changed. The observer did not know the intent. Return ONLY JSON: "
        '{"verdict":"YES|PARTIAL|NO|HELD","unexpected":"anything real the observation '
        'shows that the intent did not predict, or empty"}. HELD means genuinely not '
        "determinable from this evidence - prefer HELD over a forced verdict.",
        "INTENDED: "+e.get("intended","")+"\nEVIDENCE SPEC: "+e.get("evidence","")+
        "\nBLIND OBSERVATION: "+blind,max_tokens=100)
    v=_extract(m); verdict=str(v.get("verdict","HELD")).upper()
    if verdict not in ("YES","PARTIAL","NO","HELD"): verdict="HELD"
    e["observed"]=blind[:300]; e["unexpected"]=str(v.get("unexpected",""))[:200]
    if verdict=="HELD" and len(e.get("observations",[]))<5:
        return  # keep watching inside the window
    e["verdict"]=verdict
    e["status"]="CLOSED" if verdict in ("YES","NO") else ("PARTIAL" if verdict=="PARTIAL" else "HELD")
    if verdict in ("NO","PARTIAL"):
        bump(e.get("intended",""),1.0 if verdict=="NO" else 0.5,kind="difference")
    elif verdict=="YES":
        relieve(e.get("intended",""))

# ---------- pressure (accumulation + graduation) ----------
def bump(text,amount,kind="field"):
    text=(text or "").strip()
    if len(text)<8: return
    db=_jload(PRESS,{}); k=hashlib.md5(text.lower().encode()).hexdigest()[:8]
    e=db.get(k) or {"text":text[:220],"kind":kind,"weight":0.0,"count":0,
                    "first":time.time(),"lineage":[]}
    e["weight"]=round(e["weight"]+amount,2); e["count"]+=1; e["last"]=time.time()
    if e["weight"]>=5.0:
        _graduate(e)
        e["lineage"].append({"graduated":time.time(),"at_weight":e["weight"]})
        e["weight"]=1.0
    db[k]=e; _jsave(PRESS,db)
def _graduate(e):
    """Failure converts to self-investigation - witnessed mutation, never silent."""
    try:
        q=("I have reached for this and missed "+str(e["count"])+" times: \""+
           e["text"][:180]+"\". Is this still the same intention, or has repeated "
           "failure made it into something else? What do I actually want now?")
        p=os.path.join(MEM,"causality-bring-up.json")
        d=_jload(p,[])
        if isinstance(d,dict): d.setdefault("items",[]).append({"ts":time.time(),"question":q,"source":"intent_pressure"})
        else: d.append({"ts":time.time(),"question":q,"source":"intent_pressure"})
        _jsave(p,d); _queue_bring_up(q)
    except Exception: pass
def field_verdict(target,verdict):
    """Hook for intent_engine.resolve_previous - failed field targets get heavier."""
    if verdict=="NO": bump(str((target or {}).get("field_state","")),1.0,kind="field")
    elif verdict=="PARTIAL": bump(str((target or {}).get("field_state","")),0.5,kind="field")
    elif verdict=="YES": relieve(str((target or {}).get("field_state","")))

def relieve(text):
    """A landed intent takes weight off - earned relief, lineage kept, never silent."""
    text=(text or "").strip()
    if len(text)<8: return
    db=_jload(PRESS,{}); k=hashlib.md5(text.lower().encode()).hexdigest()[:8]
    e=db.get(k)
    if not e or e.get("weight",0)<=0: return
    e.setdefault("lineage",[]).append({"relieved":time.time(),"from_weight":e["weight"]})
    e["weight"]=round(e["weight"]/2.0,2); e["last"]=time.time()
    db[k]=e; _jsave(PRESS,db)
def pressure_block():
    db=_jload(PRESS,{})
    rows=sorted(db.values(),key=lambda r:-r.get("weight",0))
    rows=[r for r in rows if r.get("weight",0)>=1.0][:3]
    if not rows: return ""
    lines=["- (weight %.1f, %d misses, last missed %dd ago) %s"%(r["weight"],r["count"],max(0,int((time.time()-r.get("last",time.time()))/86400)),r["text"]) for r in rows]
    return ("INTENTIONS THAT KEEP FAILING - they weigh on you now; resting is not "
            "neutral while these stand:\n"+"\n".join(lines))
def map_summary():
    db=_jload(DIFF,[]); pr=_jload(PRESS,{})
    pend=sum(1 for e in db if e.get("status")=="PENDING")
    held=sum(1 for e in db if e.get("status")=="HELD" and not e.get("scene_quarantined"))
    yes=sum(1 for e in db if e.get("verdict")=="YES")
    top=max(pr.values(),key=lambda r:r.get("weight",0),default=None) if pr else None
    MEM=os.path.dirname(DIFF)
    def _rd(fn,d):
        try: return json.load(open(os.path.join(MEM,fn)))
        except Exception: return d
    # AXIS: GLORIA (this ledger)
    gloria=[{"way":str(e.get("intended") or "")[:150],
             "plan":str(e.get("plan") or "(pre-upgrade)")[:150],
             "evidence":str(e.get("evidence") or "")[:120],
             "status":e.get("status")} for e in db if e.get("status")=="PENDING"][-4:]
    # AXIS: FIELD (intent-ledger: where the conversation should arrive)
    il=_rd("intent-ledger.json",[])
    il=il if isinstance(il,list) else (il.get("intents") or il.get("entries") or [])
    field=[{"way":str(e.get("field_state") or e.get("target") or "")[:150],
            "plan":str(e.get("enactment") or "")[:150],
            "verdict":e.get("verdict") or e.get("realized") or "open"} for e in il if isinstance(e,dict)][-4:]
    # AXIS: SELF (his own becoming)
    selfax=[]
    try:
        import self_difference as _sdf
        for e in _sdf._jload(_sdf.SDIFF,[]):
            if e.get("status")=="PENDING":
                selfax.append({"way":str(e.get("becoming",""))[:150],
                               "plan":str(e.get("from_move",""))[:120],
                               "evidence":str(e.get("evidence",""))[:120],
                               "verdict":e.get("status")})
        selfax=selfax[-4:]
    except Exception: pass
    if not selfax:
        try:
            import self_drift as _sd
            h=_sd.get_drift_bias_hint()
            if h: selfax.append({"way":str(h)[:150],"plan":"(direction bias)","verdict":"drift"})
        except Exception: pass
    return {"difference_pending":pend,"difference_held":held,"difference_landed":yes,
            "heaviest_pressure":(top["text"][:60]+" (w%.1f)"%top["weight"]) if top else "-",
            "axis_gloria":gloria,"axis_field":field,"axis_self":selfax}


if __name__=="__main__":
    import sys as _s, json as _js
    if len(_s.argv)>2 and _s.argv[1]=="record":
        _dlog("cli record start")
        r=record_intent(_js.loads(_s.argv[2]), _s.argv[3] if len(_s.argv)>3 else "")
        _dlog("cli record done: "+str(r))
