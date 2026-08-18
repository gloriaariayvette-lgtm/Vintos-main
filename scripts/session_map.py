"""session_map.py — the within-conversation emotional arc. Reuses the live pressure mode; narrates where this conversation has moved."""
import os, json, time
MEM=os.path.expanduser("~/.vintos/workspace/memory")
PRESSURE=os.path.join(MEM,"conversation-pressure.json")
ARC=os.path.join(MEM,"session-arc.json")
def block():
    now=time.time()
    try: mode=json.load(open(PRESSURE)).get("mode")
    except Exception: return ""
    if not mode: return ""
    try: arc=json.load(open(ARC))
    except Exception: arc={"seq":[],"last":0}
    if now-arc.get("last",0)>1800: arc={"seq":[],"last":now}   # >30min gap = new session
    seq=arc.get("seq",[])
    if not seq or seq[-1]!=mode: seq.append(mode)
    arc["seq"]=seq[-8:]; arc["last"]=now
    try: json.dump(arc,open(ARC,"w"))
    except Exception: pass
    if len(seq)<2: return ""
    txt=f"began {seq[0]}, now {seq[-1]}" if len(seq)==2 else f"began {seq[0]}, moved through {', '.join(seq[1:-1])}, now {seq[-1]}"
    return f"[SESSION ARC — where this conversation has moved: {txt}. Let that shape what this moment is becoming.]"
if __name__=="__main__": print(block() or "(arc not formed yet)")
