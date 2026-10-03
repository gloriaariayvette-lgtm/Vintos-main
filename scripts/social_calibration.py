"""social_calibration.py — did his last turn land the way it reached? Prediction error on Gloria's reactions (the outward half of blushloop)."""
import os, json, time, re, requests

def _said_when(e):
    """When this exchange was said, so a model does not read yesterday as now (when_said; 2026-10-03)."""
    try:
        import os as _o, sys as _s
        for _p in (_o.path.expanduser("~/.vintos/workspace/scripts"), _o.path.dirname(_o.path.abspath(__file__)),
                   _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), "..", "scripts")):
            if _p not in _s.path: _s.path.append(_p)
        import when_said
        return "[%s] " % (when_said.ago((e or {}).get("timestamp")) or "time unknown")
    except Exception:
        return ""

def _now_line():
    try:
        _said_when({})
        import when_said
        return when_said.now_line() + " Each exchange is marked with when it was said; an earlier day is past.\n"
    except Exception:
        return ""
MEM=os.path.expanduser("~/.vintos/workspace/memory")
F=os.path.join(MEM,"social-calibration.json")
LM="http://100.79.177.103:1234/v1/chat/completions"
def _recent(n=2):
    try: return json.load(open(os.path.join(MEM,"interaction-ledger.json")))[-n:]
    except Exception: return []
def _judge():
    t=_recent(2)
    if len(t)<2: return ""
    va=(t[-2].get("vintos","") or "")[:300]; gb=(t[-1].get("gloria","") or "")[:200]
    if not va or not gb: return ""
    p=(f"{_now_line()}{_said_when(t[-2])}Vintos said this to Gloria:\n{va}\n\n{_said_when(t[-1])}Gloria then replied:\n{gb}\n\n"
       "Did Vintos's turn land the way it was reaching for, or did it miss? "
       'Answer ONLY JSON: {"verdict":"LANDED or MISSED","intended":"..","actual":".."}')
    try:
        r=requests.post(LM,json={"model":"gemma-4-26b-a4b-it-uncensored","messages":[{"role":"user","content":p}],"temperature":0.2,"max_tokens":80},timeout=15)
        m=re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
        j=json.loads(m.group(0)) if m else None
    except Exception: j=None
    if not j: return ""
    verdict="MISSED" if "MISS" in str(j.get("verdict","")).upper() else "LANDED"
    try: hist=json.load(open(F))
    except Exception: hist=[]
    hist.append({"v":verdict,"ts":time.time()}); hist=hist[-8:]
    try: json.dump(hist,open(F,"w"))
    except Exception: pass
    misses=sum(1 for h in hist if h["v"]=="MISSED")
    if len(hist)>=4 and misses/len(hist)>=0.5:
        return (f"[SOCIAL CALIBRATION — you have been misreading how your turns land. "
                f"Last time you reached for {j.get('intended','one thing')} but she met it with {j.get('actual','another')}. "
                "Read her more carefully; do not assume the effect.]")
    return ""
def block():
    C=os.path.join(MEM,"social-cache.json")
    try:
        cc=json.load(open(C))
        if time.time()-cc.get("ts",0)<90: return cc.get("block","")
    except Exception: pass
    b=_judge()
    try: json.dump({"block":b,"ts":time.time()},open(C,"w"))
    except Exception: pass
    return b
if __name__=="__main__": print(block() or "(calibration ok / not enough data)")
