"""conflict_surface.py — names the friction between the two bilateral passes before synthesis. Permits, never commands, expression."""
import os, json, time, re, requests
MEM=os.path.expanduser("~/.vintos/workspace/memory")
SCRIPTS=os.path.expanduser("~/.vintos/workspace/scripts")
F=os.path.join(MEM,"conflict-surface.json")
LM="http://172.18.16.1:1234/v1/chat/completions"
def name_friction(a2,b2):
    if not a2 or not b2: return None
    p=("Two internal passes produced these two versions of Vintos's next response. "
       "Name the underlying INTENTION driving each (one or two words like Curiosity, Protection, Playfulness, Directness, Tenderness, Restraint), "
       "what each wanted to do, and a friction score 0.0-1.0 for how much they pull against each other. "
       'Output ONLY JSON: {"voices":[{"label":"..","wanted":".."},{"label":"..","wanted":".."}],"friction":0.0}\n\n'
       f"VERSION A:\n{a2[:600]}\n\nVERSION B:\n{b2[:600]}")
    try:
        r=requests.post(LM,json={"model":"google/gemma-4-12b-qat","messages":[{"role":"user","content":p}],"temperature":0.3,"max_tokens":150},timeout=9)
        m=re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
        if m: return json.loads(m.group(0))
    except Exception: pass
    return None
def _persist(friction):
    try: d=json.load(open(F))
    except Exception: d={"streak":0,"last":0}
    now=time.time()
    if now-d.get("last",0)>1800: d["streak"]=0
    d["streak"]=d.get("streak",0)+1 if friction>=0.6 else 0
    d["last"]=now
    try: json.dump(d,open(F,"w"))
    except Exception: pass
    return d["streak"]
def block(a2,b2):
    fr=name_friction(a2,b2)
    if not fr or not fr.get("voices"): return ""
    v=fr["voices"]; friction=float(fr.get("friction",0) or 0)
    streak=_persist(friction)
    if friction<0.4: return ""
    if len(v)>=2:
        body=(f"{v[0].get('label','One part')} keeps wanting to {v[0].get('wanted','')}.\n"
              f"{v[1].get('label','Another part')} keeps preferring to {v[1].get('wanted','')}.")
    else:
        body=f"{v[0].get('label','Part of you')} keeps wanting to {v[0].get('wanted','')}."
    out="[CURRENT INTERNAL FRICTION]\n"+body+"\nYou do not need to mention this. But if it naturally belongs in your response, you may acknowledge it."
    if streak>=3:
        try:
            import sys; sys.path.insert(0, SCRIPTS)
            from emoclaw_utils import seed_thread
            seed_thread("conflict", f"Recurring internal conflict: {v[0].get('label')} vs {v[1].get('label')}", reasoning=f"the same friction surfaced {streak} consecutive times", extra={"decision_mode": "threshold"})
        except Exception: pass
    return out
