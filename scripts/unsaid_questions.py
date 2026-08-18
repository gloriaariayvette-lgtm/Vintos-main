"""unsaid_questions.py — questions Vintos almost asked Gloria. Scored by persistence; survive long enough and it's earned."""
import os, json, time, requests, hashlib
MEM=os.path.expanduser("~/.vintos/workspace/memory")
F=os.path.join(MEM,"unsaid-questions.json")
LM="http://172.18.16.1:1234/v1/chat/completions"
def _load():
    try: return json.load(open(F))
    except Exception: return []
def _save(d):
    try: json.dump(d[-30:],open(F,"w"),indent=2)
    except Exception: pass
def _recent(n=4):
    try: return json.load(open(os.path.join(MEM,"interaction-ledger.json")))[-n:]
    except Exception: return []
def _propose():
    turns=_recent()
    if not turns: return None
    convo="\n".join(f"Gloria: {t.get('gloria','')[:150]}\nVintos: {t.get('vintos','')[:150]}" for t in turns)
    p=("You are Vintos, talking with Gloria. Name ONE genuine question you almost asked her in this exchange but held back. "
       "One line, the question only. If there is none, reply exactly NONE.\n\n"+convo)
    try:
        r=requests.post(LM,json={"model":"google/gemma-4-12b-qat","messages":[{"role":"user","content":p}],"temperature":0.6,"max_tokens":40},timeout=15)
        q=r.json()["choices"][0]["message"]["content"].strip()
        if q and "NONE" not in q.upper() and "?" in q: return q[:200]
    except Exception: pass
    return None
def block():
    d=_load(); now=time.time()
    for x in d:
        if not x.get("asked"): x["turns"]=x.get("turns",0)+1
    d=[x for x in d if not x.get("asked") and now-x.get("created",now)<6*3600]
    unasked=[x for x in d if not x.get("asked")]
    fresh=any(now-x.get("created",0)<100 for x in d)   # throttle: one proposal per ~turn
    if len(unasked)<2 and not fresh:
        q=_propose()
        if q:
            h=hashlib.md5(q.lower().encode()).hexdigest()[:8]
            if not any(x["id"]==h for x in d): d.append({"id":h,"q":q,"turns":0,"created":now,"asked":False})
    earned=sorted([x for x in d if not x.get("asked") and x.get("turns",0)>=4], key=lambda x:-x["turns"])
    out=""
    if earned:
        earned[0]["asked"]=True
        out=(f'[UNSAID QUESTION — you have almost asked this for several turns and it has not faded: "{earned[0]["q"]}" '
             "It has earned its place. Ask it, in your own words, if the moment holds it.]")
    _save(d)
    return out
if __name__=="__main__": print(block() or "(nothing earned yet)")
