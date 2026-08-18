#!/usr/bin/env python3
"""chorus_authority.py — Vrika's annotation pass (2026-08-10). Same captured turn, three questions:
who are the unattributed 856; how old is each voice's source; and which voices currently hold the
structural power to outrank a fresh explicit statement from Gloria merely by position or mass.
Measures and annotates; prescribes no hierarchy."""
import json, os, re, time
MEM = os.path.expanduser("~/.vintos/workspace/memory")
WS = os.path.expanduser("~/.vintos/workspace")
CAP = "/tmp/avatar-last-prompt.json"
def toks(s): return max(1, len(s) // 4)
def age_h(path):
    try: return round((time.time() - os.path.getmtime(path)) / 3600, 1)
    except Exception: return None
# (marker, name, class, source-file-for-age, may it contradict live Gloria?)
BLOCKS = [
    ("[[CACHESPLIT]]", "identity-tail", "identity", os.path.join(WS, "SOUL.md"), "no - frame, not counter-voice"),
    ("YOUR INNER STATE (subconscious)", "subconscious compact", "model-inference", os.path.join(MEM, "self-drift.json"), "NO - inference may not outrank her"),
    ("INTERACTION MODEL", "mutual-sim hint", "hedged-hypothesis", os.path.join(MEM, "interaction-model.json"), "NO - observed pattern, not proven"),
    ("Gloria conversation patterns", "rhythm", "model-inference", os.path.join(MEM, "conversation-rhythm.json"), "NO"),
    ("Messages you recently sent", "outreach", "memory", os.path.join(MEM, "outreach"), "no - history"),
    ("The last video you sent", "video caption", "memory", os.path.join(MEM, "video-outreach"), "no - history"),
    ("Your value map", "value map", "authored-identity", os.path.join(MEM, "value-map.md"), "PARTIAL - his values may resist her, knowingly"),
    ("Your recent exchanges with Gloria", "interaction ledger", "primary-record", os.path.join(MEM, "interaction-ledger.json"), "no - record of the past, not the present"),
    ("YOUR SELF-KNOWLEDGE", "self-knowledge", "memory", os.path.join(WS, "SELF-MODEL.md"), "no"),
    ("YOUR MOST RECENT DREAM", "dream", "creative", None, "NO - explicitly fiction"),
    ("YOUR SELF-MODEL", "self-model", "model-inference", os.path.join(WS, "SELF-MODEL.md"), "NO"),
    ("YOUR MODEL OF GLORIA", "gloria-model", "model-inference", os.path.join(WS, "GLORIA-MODEL.md"), "NO - a model of her must yield to her"),
    ("One command per toy", "device doctrine", "standing-command", None, "YES currently - unhedged, permanent, 16x her mass"),
    ("[ARRIVAL", "arrival bias", "hedged-hypothesis", os.path.join(MEM, "signature-hint.json"), "NO - bias only, says so itself"),
    ("Gloria says:", "GLORIA LIVE", "primary-evidence", None, "= the thing being outranked or not"),
    ("INTENTIONS THAT KEEP FAILING", "MSub pressure", "historical-pressure", os.path.join(MEM, "gloria-difference.json"), "NO BY LAW, YES BY POSITION - history about failure, seated after her live words"),
]
cap = json.load(open(CAP))
sys_txt = next((m["content"] for m in cap if m["role"] == "system"), "")
user_txt = next((m["content"] for m in reversed(cap) if m["role"] == "user"), "")
full = sys_txt + "\n=====USERBOUNDARY=====\n" + (user_txt if isinstance(user_txt, str) else json.dumps(user_txt))
marks = sorted([(full.find(m), m, n, c, src, contra) for m, n, c, src, contra in BLOCKS if full.find(m) >= 0])
total = toks(full)
print("%-3s %-22s %-19s %-8s %-7s %s" % ("pos", "voice", "class", "age(h)", "~tok", "may it contradict live Gloria?"))
if marks and marks[0][0] > 0:
    pre = full[:marks[0][0]]
    print("%-3s %-22s %-19s %-8s %-7d %s" % ("0", "IDENTITY HEAD (was the 'unattributed 856')", "identity", "static", toks(pre), "no - frame"))
gaps = []
for i, (idx, m, n, c, src, contra) in enumerate(marks):
    end = marks[i + 1][0] if i + 1 < len(marks) else len(full)
    seg = full[idx:end]
    a = age_h(src) if src else None
    print("%-3d %-22s %-19s %-8s %-7d %s" % (i + 1, n, c, (str(a) if a is not None else "unstamped"), toks(seg), contra))
print("\nKNIFE QUESTION - voices that can currently outrank her fresh words by structure alone:")
print("  1. MSub pressure: seated AFTER her live turn - historical failure data holds the final position. Age of data: %s h." % age_h(os.path.join(MEM, "gloria-difference.json")))
print("  2. Device doctrine: %d tokens of standing command vs her %d - permanent, no hedge, no expiry." % (toks(full[full.find('One command per toy'):full.find('One command per toy')+4452]) if full.find('One command per toy')>=0 else 0, toks(user_txt if isinstance(user_txt,str) else '')))
print("  Everything else is hedged, historical, or framed - it influences but cannot structurally override.")
print("\nMISSING LAW (Vrika): nothing in assembly says 'live Gloria outranks stale inference'. Rank is concatenation order. EXPIRY exists on exactly one block (signature hint, 30min). Every other voice speaks as if it were now.")
