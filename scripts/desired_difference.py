"""desired_difference.py — Phase 1 of the guidance redesign.
His attempt to change something in her, made honest by logging:
intended difference (transformation, not emotion) -> blind observation -> match.
Failed intentions accumulate weight and haunt target selection; at weight 5 they
graduate into a causality question ("is this still the same intention?") with lineage.
Nothing here instruments Gloria beyond what she freely shows in conversation."""
import os, re, json, time, hashlib, urllib.request, urllib.error

def _sg_write(_p, _o, _who):
    """review 46: this store has more than one writing organ; the write goes through the store lock."""
    try:
        import sys as _s, os as _o2
        _s.path.insert(0, _o2.path.dirname(_o2.path.abspath(__file__)))
        _s.path.insert(0, _o2.path.expanduser("~/.vintos/workspace/scripts"))
        from store_guard import write_json as _wj
        _wj(_p, _o, reader=_who); return True
    except Exception:
        return False

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
# An intention he has not reached for in this long no longer stands in front of him as pressure (Gloria,
# 2026-10-01: "That photo one has never changed"). Weight only rose on a miss and fell on a landing or her
# correction; one he stopped trying sat at w4.0, below graduation, for good. Its record is kept; a new miss
# brings it back at its weight.
STALE_DAYS=14
def _live(r,now=None):
    return (now or time.time())-float(r.get("last") or r.get("first") or 0) <= STALE_DAYS*86400
API="http://127.0.0.1:8599/v1/chat/completions"
MODEL="grok-4.20-0309-non-reasoning"
# Why the last _llm call came back empty. A shim 502, the 60s timeout, no shim and a body without choices all
# returned the same "" and DERIVE FAILED could not tell them apart (audit, 18 October)
_LAST={"why":""}
def _llm(system,user,max_tokens=220,temperature=0.4):
    _LAST["why"]=""
    try:
        body=json.dumps({"model":MODEL,"messages":[{"role":"system","content":system},
            {"role":"user","content":user}],"temperature":temperature,
            "max_tokens":max_tokens}).encode()
        req=urllib.request.Request(API,data=body,headers={"Content-Type":"application/json",
            "Authorization":"Bearer "+os.environ.get("XAI_API_KEY","")})
        with urllib.request.urlopen(req,timeout=60) as r:
            out=(json.loads(r.read())["choices"][0]["message"]["content"] or "").strip()
            if not out: _LAST["why"]="empty content"
            return out
    except urllib.error.HTTPError as e:
        try: _LAST["why"]="HTTP %s %s"%(e.code,e.read()[:200].decode("utf-8","replace"))
        except Exception: _LAST["why"]="HTTP %s"%e.code
        return ""
    except Exception as e:
        _LAST["why"]=(type(e).__name__+": "+str(e))[:200]
        return ""
def _jload(p,d):
    try: return json.load(open(p))
    except Exception: return d
def _jsave(p,d):
    if _sg_write(p, d, "desired_difference"): return
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
# A suite repoints this: its lines were landing undated in the log on her host (audit, 18 October)
DLOG="/tmp/desired-difference.log"
def _dlog(msg):
    try:
        open(DLOG,"a").write(time.strftime("%Y-%m-%d %H:%M:%S ")+str(msg)[:300]+"\n")
    except Exception: pass

def her_latest(recent):
    """Her latest line in the selector's text, and only hers (16 October).

    The selector's text is the recent transcript ("GLORIA: ...\nVINTOS: ...") then the live turn, labelled
    "GLORIA (now): " for her words or "REELROOM EVENT (not Gloria's words): " for a room event. On a room
    event the old split took the last "GLORIA" - a history line - and everything after its colon: his reply
    and the event as well. Here a live turn of hers is taken whole; otherwise her last transcript line,
    cut where his reply or an event begins; a room event itself is never her words."""
    import re as _re
    t = str(recent or "")
    m = _re.search(r"GLORIA \(now\):(.*)\Z", t, _re.S)
    if m and "REELROOM EVENT" not in m.group(1):
        return m.group(1).strip()
    t = t.split("REELROOM EVENT", 1)[0] if "REELROOM EVENT" in t else t
    lines = _re.findall(r"GLORIA:(.*?)(?=\nVINTOS:|\n\n|\Z)", t, _re.S)
    if lines:
        return lines[-1].strip()
    if "Gloria:" in t:
        return t.rsplit("Gloria:", 1)[-1].split("Vintos:", 1)[0].strip()
    return "" if ("VINTOS:" in t or "Vintos:" in t) else t.strip()


def record_intent(target,recent_her=""):
    """Called when a field-target is chosen. Derives the intended DIFFERENCE in her
    (a transformation: 'less certain than she was', never a claimed emotion) plus
    what would count as evidence in her behavior. Unjudgeable -> HELD from birth."""
    if not isinstance(target,dict): return None
    # only her actual words, so a transcript tail can never put his words in her mouth
    recent_her = her_latest(recent_her)
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
        # transport, prose (a decline), or JSON naming nothing - each needs a different fix (audit, 18 October)
        why=_LAST["why"] if not out else ("no JSON in reply" if "{" not in out else "JSON without intended_difference")
        _dlog("DERIVE FAILED ("+why+") raw="+out[:150]); return None
    entry={"id":hashlib.md5((str(d["intended_difference"])+str(time.time())).encode()).hexdigest()[:8],
        "ts":time.time(),"intended":str(d["intended_difference"])[:300],
        "evidence":str(d.get("evidence",""))[:300],
        "field_state":str(target.get("field_state",""))[:200],
        "plan":str(target.get("enactment",""))[:300],
        "addresses":_addr(target.get("addresses")),
        "status":"PENDING" if d.get("judgeable",True) else "HELD",
        "observations":[],"verdict":None,"observed":None,"unexpected":None}
    db=_jload(DIFF,[]); db.append(entry); _jsave(DIFF,db[-200:])
    return entry["id"]

# ---------- observation side (blind) ----------
_NAMED_ONLY = ("(she sent a photo)", "(she sent a video)")


def _her_message(m):
    """Her words in what the grader passed: a photo's composed description is never observed as her."""
    m = str(m or "").strip()
    if m.startswith("[Gloria sent you a "):
        try:
            import sys as _s
            _d = os.path.dirname(os.path.abspath(__file__))
            if _d not in _s.path: _s.path.append(_d)
            from her_words import as_her_turn
            m = as_her_turn({"role": "user", "content": m})
        except Exception:
            m = ""
    return "" if m in _NAMED_ONLY else m


def observe(gloria_message,result=None):
    """Called when her message is graded. Blind observer never sees the intent."""
    _dlog("observe called: "+str(gloria_message)[:60])
    gloria_message = _her_message(gloria_message)
    if not gloria_message:
        return            # a picture with no words of hers: nothing she said to observe
    db=_jload(DIFF,[]); now=time.time(); changed=False
    open_=[e for e in db if e.get("status")=="PENDING" and now-e.get("ts",0)<48*3600]
    if not open_: return
    deltas={}
    try:
        for k in ("warmth","tension","valence"):
            v=(result or {}).get(k) or {}
            if isinstance(v,dict) and "diff" in v: deltas[k]=v["diff"]
    except Exception: pass
    blind_cache={}   # one blind read per distinct window of her messages, shared by every intention open on it
    for e in open_:
        e.setdefault("observations",[]).append(
            {"ts":now,"msg":str(gloria_message)[:280],"deltas":deltas})
        changed=True
        if len(e["observations"])>=2:
            _judge(e,blind_cache)
    # expire: 48h with no verdict -> belief, held
    for e in db:
        if e.get("status")=="PENDING" and now-e.get("ts",0)>=48*3600:
            e["status"]="HELD"; e["verdict"]="HELD"; changed=True
    if changed: _jsave(DIFF,db)

def _judge(e,blind_cache=None):
    obs="\n".join("- \""+o["msg"][:200]+"\" deltas="+json.dumps(o.get("deltas",{}))
                  for o in e.get("observations",[])[-5:])
    # The blind read sees only her messages, never the intent, so intentions open on the same window
    # share one read: one message no longer costs two calls for every open intention.
    if blind_cache is not None and obs in blind_cache:
        blind=blind_cache[obs]
    else:
        blind=_blind(obs)
        if blind_cache is not None and blind: blind_cache[obs]=blind
    if not blind: return
    _compare(e,blind)


def _blind(obs):
    return _llm(
        "Describe, in 1-2 plain sentences, what actually CHANGED in how Gloria is "
        "engaging across these messages - pace, certainty, direction, what she keeps "
        "returning to. Only what is visible. You do not know what anyone hoped would "
        "change; do not guess at hopes.",
        "Her recent messages, oldest first, with measured emotional deltas:\n"+obs,
        max_tokens=120)


def _compare(e,blind):
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
        bump(e.get("intended",""),1.0 if verdict=="NO" else 0.5,kind="difference",addresses=e.get("addresses"))
    elif verdict=="YES":
        relieve(e.get("intended",""),addresses=e.get("addresses"),kind="difference")

# ---------- pressure (accumulation + graduation) ----------
# A pressure row is an INTENTION, not a string (16 October). `intended` and `field_state` are fresh model prose
# every turn and almost never repeat exactly, so keyed on the exact text every miss opened a new row at weight
# 1.0 - "keeps failing" after one miss - and weight 5 needed five identical sentences. A miss now lands on the
# row its move addressed (the selector's `addresses`, the primary difference's id), else on the row whose text
# it is, else on the row of the same kind that names the same intention in other words.
SAME_INTENTION = 0.5     # share of content words two wordings must have in common to be one intention
_STOP = set(("that this with from into than then what when where which while there their them they your "
             "yours have more less just only very also over under about being been were will would could "
             "should still make made toward towards gloria vintos").split())


def _addr(a):
    a = str(a or "").strip()
    return "" if a in ("", "NONE", "None", "none") else a


def _words(t):
    import re as _re
    return {w for w in _re.findall(r"[a-z']+", str(t or "").lower()) if len(w) > 3 and w not in _STOP}


def _same(a, b):
    wa, wb = _words(a), _words(b)
    if not wa or not wb: return 0.0
    return len(wa & wb) / float(len(wa | wb))


def _key(db, text, kind=None, addresses=None):
    """The pressure row this intention is (see above); a new key only for an intention not yet in the store."""
    a = _addr(addresses)
    if a and a in db and (kind is None or db[a].get("kind", kind) == kind):
        return a
    k = hashlib.md5(text.lower().encode()).hexdigest()[:8]
    if k in db:
        if kind is None or db[k].get("kind", kind) == kind:
            return k
        k = hashlib.md5((kind + "|" + text.lower()).encode()).hexdigest()[:8]   # same words, another axis
        if k in db:
            return k
    best, bs = None, 0.0
    for kk, r in db.items():
        if not isinstance(r, dict) or (kind is not None and r.get("kind", kind) != kind):
            continue
        sc = max([_same(text, r.get("text", ""))] + [_same(text, x) for x in (r.get("wordings") or [])])
        if sc > bs:
            best, bs = kk, sc
    return best if (best is not None and bs >= SAME_INTENTION) else k


def bump(text,amount,kind="field",addresses=None):
    text=(text or "").strip()
    if len(text)<8: return
    db=_jload(PRESS,{}); k=_key(db,text,kind,addresses)
    e=db.get(k) or {"text":text[:220],"kind":kind,"weight":0.0,"count":0,
                    "first":time.time(),"lineage":[]}
    if text[:220]!=e.get("text") and text[:220] not in (e.get("wordings") or []):
        e["wordings"]=((e.get("wordings") or [])+[text[:220]])[-5:]   # the other words it has come in
    e["weight"]=round(e["weight"]+amount,2); e["count"]+=1; e["last"]=time.time()
    if e.get("overridden"): e["lineage"].append({"reopened":time.time(),"after":e["overridden"]}); e.pop("overridden",None)
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
        try:   # review 204: one schema-2 door for every producer
            import causality_engine as _ce
            _ce.queue_question(q,"intent_pressure",evidence=[e["text"]]+[str(l) for l in e.get("lineage",[])[-3:]],memory=MEM); return
        except Exception: pass
        p=os.path.join(MEM,"causality-bring-up.json")
        d=_jload(p,[])
        if isinstance(d,dict): d.setdefault("items",[]).append({"ts":time.time(),"question":q,"source":"intent_pressure"})
        else: d.append({"ts":time.time(),"question":q,"source":"intent_pressure"})
        _jsave(p,d); _queue_bring_up(q)
    except Exception: pass
def field_verdict(target,verdict):
    """Hook for intent_engine.resolve_previous - failed field targets get heavier."""
    fs=str((target or {}).get("field_state","")); ad=(target or {}).get("addresses")
    if verdict=="NO": bump(fs,1.0,kind="field",addresses=ad)
    elif verdict=="PARTIAL": bump(fs,0.5,kind="field",addresses=ad)
    elif verdict=="YES": relieve(fs,addresses=ad,kind="field")
    elif verdict in ("CORRECTED","WRONG_READING"): override(fs,"her correction: "+verdict,source="correction",addresses=ad,kind="field")
    elif verdict in ("KEEP_PRIVATE","PRIVATE"): override(fs,"legitimate privacy: "+verdict,source="privacy",addresses=ad,kind="field")

def override(text,reason,source="correction",addresses=None,kind=None):
    """review 188: her correction, or a legitimate privacy mark (KEEP_PRIVATE / WRONG_READING) on the
    same intention, sets its standing pressure to zero with the reason kept - it no longer stands in
    front of him. Lineage kept, never silent; a later miss may bump it again from zero."""
    text=(text or "").strip()
    if len(text)<8: return None
    db=_jload(PRESS,{}); k=_key(db,text,kind,addresses)
    e=db.get(k)
    if not e: return None
    e.setdefault("lineage",[]).append({"overridden":time.time(),"from_weight":e.get("weight",0),
                                       "reason":str(reason)[:200],"source":source})
    e["weight"]=0.0; e["overridden"]={"at":time.time(),"reason":str(reason)[:200],"source":source}
    db[k]=e; _jsave(PRESS,db); return e
def relieve(text,addresses=None,kind=None):
    """A landed intent takes weight off - earned relief, lineage kept, never silent."""
    text=(text or "").strip()
    if len(text)<8: return
    db=_jload(PRESS,{}); k=_key(db,text,kind,addresses)
    e=db.get(k)
    if not e or e.get("weight",0)<=0: return
    e.setdefault("lineage",[]).append({"relieved":time.time(),"from_weight":e["weight"]})
    e["weight"]=round(e["weight"]/2.0,2); e["last"]=time.time()
    db[k]=e; _jsave(PRESS,db)
# What she has said she likes (16 October: "I like being lazy. I like a man who leads. Stop telling him to do
# otherwise"). An aim that has her take the lead, hold the next beat, supply the scene or carry more of it, or has
# him pull back so she must, may still be chosen when a moment asks for it; it is never turned into standing
# pressure that keeps telling him to make her lead.
_ASKS_HER_TO_LEAD = re.compile(
    r"\b(?:her|she|gloria)\b[^.;]{0,60}\b(?:take|takes|taking|hold|holds|holding|carry|carries|carrying|lead|leads|"
    r"leading|supply|supplies|supplying|steer|steers|drive|drives|direct|directs|initiate|initiates|set|sets|setting)\b"
    r"[^.;]{0,30}\b(?:lead|beat|scene|next|thread|conversation|evening|initiative|momentum|direction|pace|reins|charge)\b"
    r"|\bless reliant on (?:me|my)\b|\b(?:her|gloria)'?s? own (?:thought|image|beat|idea|direction|initiative|listing|building)"
    r"|\b(?:thought|question|idea|image|direction|beat) of her own\b|\briding (?:the )?momentum\b|\bnext beat (?:is )?hers\b|\b(?:let|letting) her lead\b|\bhand(?:ing)? (?:her )?the lead\b"
    r"|\bi (?:stop|step back|pull back|ease out|withdraw)\b[^.;]{0,40}\b(?:momentum|scene|lead|adding|her)\b", re.I)


def asks_her_to_lead(text):
    """True when an intention would have her take over the leading he does (her stated wish is that he leads)."""
    return bool(_ASKS_HER_TO_LEAD.search(str(text or "")))


def pressure_block():
    db=_jload(PRESS,{})
    rows=sorted(db.values(),key=lambda r:-r.get("weight",0))
    rows=[r for r in rows if r.get("weight",0)>=1.0 and not r.get("overridden") and _live(r)
          and not asks_her_to_lead(r.get("text"))][:3]
    if not rows: return ""
    _ago=lambda r: max(0,int((time.time()-r.get("last",time.time()))/86400))
    # "keep failing" is said only of what has missed more than once; a first miss is named as one
    again=[r for r in rows if int(r.get("count",0) or 0)>=2]
    once=[r for r in rows if int(r.get("count",0) or 0)<2]
    out=[]
    if again:
        out.append("INTENTIONS THAT KEEP FAILING - they weigh on you now; resting is not "
                   "neutral while these stand:\n"+"\n".join(
                       "- (weight %.1f, %d misses, last missed %dd ago) %s"%(r["weight"],r["count"],_ago(r),r["text"]) for r in again))
    if once:
        out.append("AN INTENTION THAT MISSED ONCE - not yet a pattern:\n"+"\n".join(
            "- (weight %.1f, missed %dd ago) %s"%(r["weight"],_ago(r),r["text"]) for r in once))
    return "\n\n".join(out)
def map_summary():
    db=_jload(DIFF,[]); pr=_jload(PRESS,{})
    pend=sum(1 for e in db if e.get("status")=="PENDING")
    held=sum(1 for e in db if e.get("status")=="HELD" and not e.get("scene_quarantined"))
    yes=sum(1 for e in db if e.get("verdict")=="YES")
    top=max((r for r in pr.values() if _live(r) and not r.get("overridden") and not asks_her_to_lead(r.get("text"))),
            key=lambda r:r.get("weight",0),default=None) if pr else None
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
    # intent-ledger rows are {"target":{field_state, enactment, ...}, "realized":{"field":..} or a verdict}
    def _fv(e):
        r=e.get("realized")
        if isinstance(r,dict): r=r.get("field")
        return str(e.get("verdict") or r or "open")
    def _tg(e):
        t=e.get("target")
        return t if isinstance(t,dict) else {}
    field=[{"way":str(_tg(e).get("field_state") or e.get("field_state") or "")[:150],
            "plan":str(_tg(e).get("enactment") or e.get("enactment") or "")[:150],
            "verdict":_fv(e)} for e in il if isinstance(e,dict)][-4:]
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
