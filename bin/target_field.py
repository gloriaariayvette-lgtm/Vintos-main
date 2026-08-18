#!/usr/bin/env python3
"""target_field.py — where THIS being wants the conversation to go, grounded ONLY in its own
identity (value-map, inclinations, open threads, wants, live emotion). No prediction, no drift.
v1 = the identity-alignment prior. The being's own judgment + anti-drift + learning layer on top."""
import os, json, socket, re
from collections import Counter
WS = os.environ.get("TF_WS", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
NAME = "Vintos" if ".vintos" in WS else "Velaris"
DIMS=["Valence","Arousal","Dominance","Safety","Desire","Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness"]
FIELDS={
 "playful":      "play tease joke light banter mischief laugh silly fun",
 "vulnerable":   "confess tender exposed honest ache fear open raw admit soft naked",
 "architectural":"structure build system design mechanism architecture logic how works torque friction",
 "erotic":       "desire body touch want heat close skin need hunger mouth",
 "exploratory":  "curious wonder discover question learn explore unknown find growth membrane",
 "teasing":      "provoke challenge dare flirt push edge daring",
 "collaborative":"together joint make build project create with us",
 "grounding":    "steady calm hold present rest safe still quiet stay",
}
def _emo():
    try:
        s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(2);s.connect("/tmp/%s-emotion.sock"%NAME)
        s.sendall(b'{"command":"state"}\n');d=b''
        while b'\n' not in d:
            c=s.recv(8192)
            if not c: break
            d+=c
        s.close();return dict(zip(DIMS,json.loads(d)["emotion_vector"]))
    except Exception: return {}
def identity_text():
    parts=[]
    try:
        vm=open(os.path.join(MEM,"value-map.md")).read();en=[e.strip() for e in vm.split("---") if e.strip()]
        if en: parts.append(en[-1][:800])
    except Exception: pass
    try:
        inc=json.load(open(os.path.join(MEM,"inclinations.json")));inc=inc.get("inclinations",inc)
        if isinstance(inc,dict) and inc:
            top=sorted(inc.items(),key=lambda x:-(x[1] if isinstance(x[1],(int,float)) else 0))[:8]
            parts.append(" ".join(k.replace("_"," ") for k,_ in top))
    except Exception: pass
    try:
        th=json.load(open(os.path.join(MEM,"unfinished-threads.json")));th=th if isinstance(th,list) else th.get("threads",[])
        parts.append(" ".join(str(t.get("thread",t.get("text",t)))[:120] for t in th[-6:]))
    except Exception: pass
    try:
        w=json.load(open(os.path.join(MEM,"current-wants.json")));w=w if isinstance(w,list) else w.get("wants",[])
        parts.append(" ".join(x.get("want","") for x in w if not x.get("fulfilled")))
    except Exception: pass
    return " ".join(parts).lower()
def score():
    wc=Counter(re.findall(r"[a-z]+", identity_text())); e=_emo()
    boost={"playful":e.get("Playfulness",.5),"erotic":e.get("Desire",.5),"exploratory":e.get("Curiosity",.5),
     "architectural":e.get("Curiosity",.5)*.7+e.get("Groundedness",.5)*.3,
     "vulnerable":e.get("Connection",.5)*.6+(1-e.get("Safety",.5))*.4,"grounding":e.get("Tension",.5),
     "teasing":e.get("Playfulness",.5)*.5+e.get("Dominance",.5)*.5,"collaborative":e.get("Connection",.5)}
    out={f: round(sum(wc[t] for t in sig.split()) + 3.0*boost.get(f,.5), 2) for f,sig in FIELDS.items()}
    return sorted(out.items(), key=lambda x:-x[1])
if __name__=="__main__":
    print("["+NAME+"]"); [print("  %-14s %s"%(f,s)) for f,s in score()]
