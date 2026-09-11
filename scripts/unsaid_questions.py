"""unsaid_questions.py — questions Vintos almost asked Gloria. Scored by persistence; survive long enough and it's earned."""
import os, json, time, requests, hashlib

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
F=os.path.join(MEM,"unsaid-questions.json")
LM="http://172.18.16.1:1234/v1/chat/completions"
def _load():
    try: return json.load(open(F))
    except Exception: return []
def _save(d):
    if _sg_write(F, d[-30:], "unsaid_questions"): return
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
def observe_reply(reply):
    """Advance on a delivered turn; proposed questions are not marked as asked."""
    from store_guard import transaction
    with transaction(F):
        d=_load();now=time.time()
        for x in d:
            if not x.get("asked"): x["turns"]=x.get("turns",0)+1
            # Exact authored question in the reply is evidence it was voiced.
            if x.get("q") and x["q"] in reply: x["asked"]=True
        d=[x for x in d if not x.get("asked") and now-x.get("created",now)<6*3600]
        if len(d)<2 and not any(now-x.get("created",0)<100 for x in d):
            q=_propose()
            if q:
                h=hashlib.md5(q.lower().encode()).hexdigest()[:8]
                if not any(x["id"]==h for x in d):d.append({"id":h,"q":q,"turns":0,"created":now,"asked":False})
        _save(d)

def block():
    from want_stance import may_initiate
    if not may_initiate("reaching")[0]: return ""
    now=time.time()
    earned=sorted([x for x in _load() if not x.get("asked") and x.get("turns",0)>=4 and now-x.get("created",now)<6*3600],key=lambda x:-x["turns"])
    if not earned:return ""
    return (f'[UNSAID QUESTION — you have almost asked this for several turns and it has not faded: "{earned[0]["q"]}" '
            "It has earned its place. Ask it, in your own words, if the moment holds it.]")
if __name__=="__main__": print(block() or "(nothing earned yet)")
