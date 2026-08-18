#!/usr/bin/env python3
"""tension_identity_audit.py — ledger-wide identity collision audit (Vrika, 2026-08-10).
INSTRUMENT ONLY: produces suspects, never merges. Catches the historical form of birth-fragmentation:
T-001 and T-042 describing one underlying pull across weeks. Pairwise over living tensions (cap 12),
same standard as the matcher. Writes tension-collisions.json for examination. SPARK_WORKSPACE switches."""
import os, json, re, requests
from itertools import combinations
from datetime import datetime
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
GEMMA = "http://172.18.16.1:1234/v1/chat/completions"
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
led = load(os.path.join(MEM, "tension-ledger.json"), {"tensions": []})
living = [t for t in led["tensions"] if t["lifecycle"] in ("ACTIVE", "CARRIED")][:12]
if len([t for t in led["tensions"] if t["lifecycle"] in ("ACTIVE", "CARRIED")]) > 12:
    print("[identity-audit] CAP: auditing first 12 of more living tensions - coverage incomplete, saying so")
suspects = []
for a, b in combinations(living, 2):
    try:
        r = requests.post(GEMMA, json={"model": "google/gemma-4-12b-qat", "temperature": 0.0,
            "max_tokens": 80, "messages": [{"role": "user", "content":
            "Is tension A the same underlying tension as tension B? Same means the same specific "
            "pull/avoidance about the same specific subject - not merely a similar mood.\n"
            "A: " + a["canonical"][:250] + "\nB: " + b["canonical"][:250] +
            '\nONLY JSON: {"same": true/false, "why": "one line"}'}]}, timeout=60)
        d = json.loads(re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S).group())
        if d.get("same"):
            suspects.append({"pair": [a["tension_id"], b["tension_id"]],
                             "reason": str(d.get("why", ""))[:150],
                             "note": "POSSIBLE_IDENTITY_COLLISION - suspect only, no merge"})
            print("[identity-audit] SUSPECT: %s ~ %s | %s" % (a["tension_id"], b["tension_id"], str(d.get("why",""))[:70]))
    except Exception as e:
        print("[identity-audit] pair failed: %s" % e)
json.dump({"suspects": suspects, "n_audited": len(living), "at": datetime.now().isoformat(),
           "law": "no silent merges - suspects await examination"},
          open(os.path.join(MEM, "tension-collisions.json"), "w"), indent=2)
print("[identity-audit] %d living audited, %d suspects" % (len(living), len(suspects)))
