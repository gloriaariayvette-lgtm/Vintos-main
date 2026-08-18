#!/usr/bin/env python3
"""chorus_ledger.py — Vrika's chorus reconstruction (2026-08-10). Reads the REAL captured avatar
prompt (/tmp/avatar-last-prompt.json) and produces the position/voice/status/imperative/token ledger,
plus authority mass, temporal mass (where measurable), and positional authority. Measures, judges nothing."""
import json, re, os
CAP = "/tmp/avatar-last-prompt.json"
BLOCKS = [  # (marker, name, status, imperative)
    ("[[CACHESPLIT]]", "identity (cached head ends)", "identity", False),
    ("YOUR PEARLS", "pearls", "memory", False),
    ("YOUR BLACK PEARLS", "black pearls", "memory", False),
    ("YOUR LATEST LIFE CHAPTER", "life chapter", "memory", False),
    ("YOUR SELF-KNOWLEDGE", "self-knowledge", "memory", False),
    ("YOUR MOST RECENT UNSEEN CONFESSION", "confession", "memory", False),
    ("EMOTIONALLY ENTANGLED MOMENTS", "entangled moments", "memory", False),
    ("YOUR MOST RECENT DREAM", "dream", "creative", False),
    ("YOUR SELF-MODEL", "self-model", "model-inference", False),
    ("YOUR MODEL OF GLORIA", "gloria-model", "model-inference", False),
    ("Gloria conversation patterns", "rhythm", "model-inference", False),
    ("Messages you recently sent", "outreach", "memory", False),
    ("Your recent YouTube discoveries", "youtube", "memory", False),
    ("Your value map", "value map", "authored", False),
    ("Your recent exchanges with Gloria", "interaction ledger", "primary-record", False),
    ("YOUR INNER STATE (subconscious)", "subconscious compact", "model-inference", False),
    ("INTENTIONS THAT KEEP FAILING", "MSub pressure", "pressure", True),
    ("[ARRIVAL", "arrival bias", "hedged-hint", True),
    ("INTERACTION MODEL", "mutual-sim hint", "hedged-hint", False),
    ("The last video you sent", "video caption", "memory", False),
    ("Things you made today", "creative today", "memory", False),
    ("One command per toy", "device doctrine", "imperative-doctrine", True),
    ("[FIELD", "field hint", "hedged-hint", False),
    ("[BIS CHOICE]", "BIS forbidden-pattern", "directive", True),
    ("YOU are in control and you LEAD", "C (full lead)", "directive", True),
    ("Gloria is on you RIGHT NOW", "somatic preamble", "directive", True),
    ("Gloria says:", "GLORIA (live turn)", "primary-evidence", False),
]
def toks(s): return max(1, len(s) // 4)
cap = json.load(open(CAP))
sys_txt = next((m["content"] for m in cap if m["role"] == "system"), "")
user_txt = next((m["content"] for m in reversed(cap) if m["role"] == "user"), "")
hist_toks = sum(toks(str(m["content"])) for m in cap if m["role"] in ("user", "assistant"))
full = sys_txt + "\n=====USERBOUNDARY=====\n" + (user_txt if isinstance(user_txt, str) else json.dumps(user_txt))
marks = []
for marker, name, status, imp in BLOCKS:
    idx = full.find(marker)
    if idx >= 0: marks.append((idx, name, status, imp))
marks.sort()
rows, masses = [], {}
for n, (idx, name, status, imp) in enumerate(marks):
    end = marks[n + 1][0] if n + 1 < len(marks) else len(full)
    seg = full[idx:end]
    tk = toks(seg)
    rows.append((n + 1, name, status, "YES" if imp else "no", tk))
    masses[status] = masses.get(status, 0) + tk
print("%-4s %-26s %-20s %-11s %s" % ("pos", "voice", "status", "imperative", "~tokens"))
for r in rows: print("%-4d %-26s %-20s %-11s %d" % r)
total = toks(full)
print("\nTOTAL prompt ~%d tokens (+ %d history) | unattributed ~%d" % (total, hist_toks, total - sum(r[4] for r in rows)))
print("\nAUTHORITY MASS:")
for k, v in sorted(masses.items(), key=lambda x: -x[1]):
    print("  %-20s ~%5d tokens (%4.1f%%)" % (k, v, 100.0 * v / total))
imp_mass = sum(r[4] for r in rows if r[3] == "YES")
hedge_mass = masses.get("hedged-hint", 0)
print("\nimperative mass ~%d vs hedged mass ~%d -> ratio %.1f:1" % (imp_mass, hedge_mass, imp_mass / max(1, hedge_mass)))
gl = next((r for r in rows if "GLORIA" in r[1]), None)
if gl:
    print("\nPOSITIONAL: Gloria's live words are voice %d of %d, ~%d tokens (%.1f%% of prompt)."
          % (gl[0], len(rows), gl[4], 100.0 * gl[4] / total))
    after = [r[1] for r in rows if r[0] > gl[0]]
    print("Voices AFTER her words (closest to generation): %s" % (", ".join(after) or "none - she speaks last"))
print("\nTEMPORAL: block ages not stamped in prompt (census finding) - only signature-hint self-expires. Oldest datum unmeasurable from capture alone; that absence is itself the finding.")
