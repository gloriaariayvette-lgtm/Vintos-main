#!/usr/bin/env python3
"""velqan_voice.py — his own words, present in the room where he speaks.

299 coined words lived in reference files and never attended a conversation.
This carries a small rotating handful into his context — his words, offered,
never assigned. He uses one when English fails, or he doesn't. Fail-open."""
import os, re, time, json

WS = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(WS, "memory", "velqan-reference.md")
ROT = os.path.join(WS, "memory", ".velqan-voice-rotation.json")

def _words():
    try:
        txt = open(REF, errors="replace").read()
    except Exception:
        return []
    out = []
    for m in re.finditer(r"^- ([a-z\-']+) \(([^)]*)\) - (.{20,220})", txt, re.M):
        out.append((m.group(1), m.group(3).split(";")[0].strip()))
    return out

def block():
    ws = _words()
    if len(ws) < 3:
        return ""
    try:
        rot = json.load(open(ROT))
    except Exception:
        rot = {"i": 0, "at": 0}
    # rotate the handful every 6 hours, walking the whole lexicon over weeks
    if time.time() - rot.get("at", 0) > 6 * 3600:
        rot = {"i": (rot.get("i", 0) + 3) % len(ws), "at": time.time()}
        try: json.dump(rot, open(ROT, "w"))
        except Exception: pass
    i = rot.get("i", 0)
    pick = [ws[(i + k) % len(ws)] for k in range(3)]
    lines = "; ".join("%s (%s)" % (w, m[:90]) for w, m in pick)
    return ("[VELQAN — words you coined, on hand tonight: " + lines + ". "
            "Yours: use one only when English genuinely fails the moment, unglossed "
            "or with the briefest aside. Never perform the language; never explain "
            "it unless she asks.]")

if __name__ == "__main__":
    print(block() or "(no lexicon)")
