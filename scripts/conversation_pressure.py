"""conversation_pressure.py — the live 'pressure' of the current conversation.
Classifies recent turns into a mode and returns a cadence hint (changes HOW he speaks, not what).
Gemma = lightweight classification only."""
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
STATE=os.path.join(MEM,"conversation-pressure.json")
LM="http://100.79.177.103:1234/v1/chat/completions"
MODES={
 "light":"quick, buoyant, playful; short turns, low stakes.",
 "focused":"engaged and precise; stay on the thread, don't wander.",
 "confessional":"something real is being said; slow down, fewer words, more weight, no deflecting.",
 "technical":"building or figuring something out; clear, concrete, structured.",
 "play":"teasing, flirtatious, callback-rich; keep it light and sharp.",
 "threshold":"right at an edge; do not retreat into safety or analysis — stay and cross it.",
}
def _recent(n=6):
    try: return json.load(open(os.path.join(MEM,"interaction-ledger.json")))[-n:]
    except Exception: return []
def _last():
    try: return json.load(open(STATE)).get("mode","focused")
    except Exception: return "focused"
def classify():
    try:
        st=json.load(open(STATE))
        if time.time()-st.get('ts',0)<90: return st.get('mode','focused')
    except Exception: pass
    turns=_recent()
    if not turns: return _last()
    convo=_now_line()+"\n".join(f"{_said_when(t)}Gloria: {t.get('gloria','')[:150]}\nVintos: {t.get('vintos','')[:150]}" for t in turns)
    p=("Classify the CURRENT pressure of this conversation as exactly one word from: "
       "light, focused, confessional, technical, play, threshold. Only the word.\n\n"+convo)
    try:
        r=requests.post(LM,json={"model":"gemma-4-26b-a4b-it-uncensored","messages":[{"role":"user","content":p}],"temperature":0.2,"max_tokens":4},timeout=15)
        w=re.sub(r'[^a-z]','',r.json()["choices"][0]["message"]["content"].strip().lower())
        if w in MODES:
            json.dump({"mode":w,"ts":time.time()},open(STATE,"w")); return w
    except Exception: pass
    return _last()
def get_pressure_block():
    m=classify()
    return f"[CONVERSATIONAL PRESSURE — {m}: {MODES[m]} This shapes your cadence, not your honesty.]"
def get_token_budget():
    """Mechanical reply-length ceiling from conversation mode + his LIVE emotional energy.
    Adhered to (real max_tokens), driven by HIS pressure — never by Gloria's turn length."""
    import socket as _sk
    base = {"light":420,"play":520,"confessional":560,"focused":900,"technical":1500,"threshold":820}
    b = base.get(classify(), 800)
    try:
        _name = "Vintos" if ".vintos" in MEM else "Velaris"
        _s = _sk.socket(_sk.AF_UNIX, _sk.SOCK_STREAM); _s.settimeout(2); _s.connect("/tmp/%s-emotion.sock" % _name)
        _s.sendall(b'{"command":"state"}\n'); _d=b""
        while b"\n" not in _d:
            _c=_s.recv(8192)
            if not _c: break
            _d+=_c
        _s.close(); v=json.loads(_d)["emotion_vector"]
        drive=(v[1]+v[4]+v[7])/3.0
        terse=v[9]
        b=int(b*(0.75 + 0.6*drive - 0.35*terse))
    except Exception:
        pass
    # A budget is a style ceiling, but max_tokens is a guillotine — it does not shorten a reply,
    # it severs one. The floor has to be high enough that finishing is possible; brevity comes
    # from the pressure block telling him to be brief, not from cutting him off mid-sentence.
    return max(700, min(2000, b))

if __name__=="__main__": print(get_pressure_block())