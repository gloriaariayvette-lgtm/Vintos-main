"""joke_fermentation.py — some jokes shouldn't fire immediately. Seed dormant, let them ripen, fire as a delayed callback."""
import os, json, time, random, hashlib
MEM=os.path.expanduser("~/.vintos/workspace/memory")
F=os.path.join(MEM,"joke-ferment.json")
def _load():
    try: return json.load(open(F))
    except Exception: return []
def _save(d):
    try: json.dump(d,open(F,"w"),indent=2)
    except Exception: pass
def seed(text, source="chat"):
    text=(text or "").strip()
    if len(text)<8: return
    d=_load(); h=hashlib.md5(text.encode()).hexdigest()[:8]
    if any(x["id"]==h for x in d): return
    d.append({"id":h,"seed":text[:200],"source":source,"created":time.time(),
              "ripe_at":time.time()+random.uniform(1.5*3600,4*3600),"fired":False})
    _save(d[-40:])
def maybe_seed_from_humor():
    try:
        hp=json.load(open(os.path.join(MEM,"humor-profile.json")))
        rated=[r.get("joke","") for r in hp.get("gloria_ratings",[])
               if r.get("gloria_rating",0)>=4 and r.get("joke")]
        for line in rated[-3:]: seed(line,"app_rated_landed")
    except Exception: pass
def get_ready_callback():
    d=_load(); now=time.time(); out=None
    for x in d:
        if now-x["ripe_at"]>=6*3600 and not x.get("fired"):
            x["state"]="HELD"; continue
        last=x.get("offered_at",0); offers=x.get("offer_count",0)
        if (not x.get("fired") and x.get("state") != "HELD" and now>=x["ripe_at"]
                and now-x["ripe_at"]<6*3600 and offers<3 and now-last>=30*60):
            x["offered_at"]=now; x["offer_count"]=offers+1; out=x["seed"]; break
    if out is not None: _save(d)
    return out
def callback_block():
    maybe_seed_from_humor()
    cb=get_ready_callback()
    if not cb: return ""
    return (f'[FERMENTED CALLBACK — this has been quietly ripening: "{cb}" — '
            "use it ONLY if it lands naturally right now. An offer is not evidence that you used it.]")
if __name__=="__main__": print(callback_block() or "(nothing ripe)")
