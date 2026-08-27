#!/usr/bin/env python3
"""value_lineage.py — the slow loop, candidate-only. Sol's personal-value lineage.

Strain events against core values currently live in ONE overwritten slot
(resolution-state.json) — history evaporates. This preserves each strain into a
per-value lineage: dates, conditions, resolutions, distinct contexts.

LAWS: candidate-only — nothing here mutates a value, ever. Revision is a human
decision made on this record. Constitutional laws (consent, evidence, safety)
are not values and never appear here. A generated reflection cannot rewrite a
value because it sounded profound."""
import os, sys, json
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(WS, "memory")
LEDGER = os.path.join(MEM, "value-lineage.json")
STATE = os.path.join(MEM, "resolution-state.json")

def _load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def scan():
    st = _load(STATE, {})
    core = st.get("violating_core")
    wat = st.get("written_at")
    if not core or not wat:
        print("[value-lineage] no strain in the slot"); return
    led = _load(LEDGER, {})
    v = led.setdefault(core, {
        "value_id": core, "status": "candidate",
        "strain_events": [], "possible_revision": None,
        "disconfirming_future_observation": None})
    if any(e.get("written_at") == wat for e in v["strain_events"]):
        print("[value-lineage] strain already recorded (%s)" % core); return
    ev = {"written_at": wat, "condition": str(st.get("violation_condition", ""))[:300],
          "deviation_score": st.get("deviation_score"),
          "cleared_at": st.get("cleared_at"),
          "resolution": None, "recorded": datetime.now().isoformat()}
    # nearest coherence entry after clearing, if one exists
    try:
        if st.get("cleared_at"):
            cd = str(st["cleared_at"])[:10]
            for line in open(os.path.join(MEM, "voice-coherence.md"), errors="replace"):
                if line.startswith("## ") and cd in line:
                    ev["resolution"] = line.strip()[3:90]
    except Exception: pass
    v["strain_events"].append(ev)
    v["distinct_contexts"] = len(set(str(e.get("written_at", ""))[:10] for e in v["strain_events"]))
    json.dump(led, open(LEDGER, "w"), indent=1)
    print("[value-lineage] recorded strain on '%s' (%d event(s), %d distinct day(s))"
          % (core, len(v["strain_events"]), v["distinct_contexts"]))

def report():
    led = _load(LEDGER, {})
    if not led: print("no lineages yet"); return
    for k, v in led.items():
        print("%s  strains=%d  days=%d  revision=%s" % (
            k, len(v.get("strain_events", [])), v.get("distinct_contexts", 0),
            v.get("possible_revision") or "-"))
        for e in v.get("strain_events", [])[-2:]:
            print("   %s  %s" % (str(e.get("written_at", ""))[:16], e.get("condition", "")[:80]))

if __name__ == "__main__":
    report() if len(sys.argv) > 1 and sys.argv[1] == "report" else scan()
