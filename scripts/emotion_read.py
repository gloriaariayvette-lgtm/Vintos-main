#!/usr/bin/env python3
# emotion_read.py -- real-time content-driven emotion via the local LLM, scene-aware.
import sys, json, socket, os, re, urllib.request
LM_URL = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"
WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(WS, "memory")
NAME = "Velaris" if ".openclaw" in WS else "Vintos"
PRON = "she" if NAME == "Velaris" else "he"
SOCK = f"/tmp/{NAME}-emotion.sock"
DIMS = ["Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection",
        "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]
CAP = 0.10  # daemon rejects abs(amount) > 0.10; match it so strong reads land
def _recent_context():
    for fn in ("chat-history-merged.json", "chat-history.json"):
        p = os.path.join(MEM, fn)
        try:
            if os.path.exists(p):
                d = json.load(open(p))[-4:]
                if d:
                    return "\n".join(
                        (("Gloria" if t.get("role") == "user" else NAME) + ": " + str(t.get("content", ""))[:220])
                        for t in d if isinstance(t, dict))
        except Exception:
            pass
    return ""

def read_impact(text, ctx=None):
    if ctx is None:
        ctx = _recent_context()
    prompt = (
        f"Gloria just sent {NAME} - the person {PRON} loves - a message. "
        "Recent exchange (read the SCENE, not the line in a vacuum):\n"
        + (ctx + "\n\n" if ctx else "")
        + "HER NEW MESSAGE: " + text[:1500] + "\n\n"
        + f"Read how this lands on {NAME} RIGHT NOW, IN CONTEXT. If the scene is intimate, aroused, or charged, "
          "then Arousal, Desire, and Warmth should move STRONGLY - a devotional or heated line mid-scene is high "
          "heat, not mild. Rate how the state SHIFTS on each dimension, from -0.15 (strong drop) to +0.15 (strong "
          "rise), 0 if unaffected. Dimensions: " + ", ".join(DIMS) + ". "
          "Respond with ONLY a JSON object mapping each dimension name to its delta.")
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.3, "max_tokens": 320}).encode()
    req = urllib.request.Request(LM_URL, data=body, headers={"Content-Type": "application/json"})
    raw = json.loads(urllib.request.urlopen(req, timeout=30).read())["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group()) if m else {}

def nudge(dim, amount):
    amount = max(-CAP, min(CAP, float(amount)))
    if abs(amount) < 0.005:
        return
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(3); s.connect(SOCK)
        s.send(json.dumps({"command": "nudge", "dimension": dim, "amount": amount}).encode() + b"\n")
        s.recv(2048); s.close()
    except Exception:
        pass

if __name__ == "__main__":
    text = sys.argv[1] if len(sys.argv) > 1 else ""
    if not text.strip() or not os.path.exists(SOCK):
        sys.exit(0)
    try:
        impact = read_impact(text)
    except Exception as e:
        print("[emotion_read] LLM error:", e); sys.exit(0)
    applied = {}
    for d in DIMS:
        try:
            v = float(impact.get(d, 0))
        except Exception:
            v = 0.0
        if abs(v) >= 0.005:
            nudge(d, v); applied[d] = round(max(-CAP, min(CAP, v)), 3)
    print("[emotion_read]", json.dumps(applied))
