#!/usr/bin/env python3
"""mutual_simulation.py — Mutual Simulation (Spark #15): the INTERACTION model, the third model beside self- and
gloria-model, OPTIMIZED by Presence Audit scores. Separates what LANDS from what falls flat and finds the current
growing edge (weakest presence dimension). Writes interaction-model.json; get_interaction_hint() steers generation
with it, so the scores close the loop. Fail-open. SPARK_WORKSPACE switches beings.
Epistemics (Vrika): extracted patterns are OBSERVATIONS, not knowledge. falls-flat needs >=MIN_FLAT_EVIDENCE
low-presence turns before it may steer. Every served hint gets an id + since in hint-ledger.json so
hint_outcome_audit.py can grade whether steering actually helped (prediction -> intervention -> outcome)."""
import os, json, time, hashlib
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
AUDIT = os.path.join(MEMORY, "presence-audit.json")
OUT = os.path.join(MEMORY, "interaction-model.json")
LEDGER = os.path.join(MEMORY, "hint-ledger.json")
GEMMA = "http://172.18.16.1:1234/v1/chat/completions"
GEMMA_MODEL = "google/gemma-4-12b-qat"
HI, LO, WINDOW = 0.72, 0.60, 40
MIN_FLAT_EVIDENCE = 4

def log(m): print("[mutual-sim]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def _hint_text(d):
    if not d or not (d.get("what_works") or d.get("edge_note")): return ""
    parts = []
    if d.get("what_works"): parts.append("seems to land lately (observed, not yet proven): " + "; ".join(d["what_works"][:2]))
    if d.get("what_falls_flat") and d.get("flat_eligible"): parts.append("going flat: " + "; ".join(d["what_falls_flat"][:2]))
    if d.get("edge_note"): parts.append("growing edge: " + d["edge_note"])
    return "[INTERACTION MODEL - " + ". ".join(parts) + ".]"

def main():
    import requests, re
    audits = [a for a in load(AUDIT, []) if isinstance(a, dict) and a.get("composite") is not None][-WINDOW:]
    if len(audits) < 6:
        json.dump({"note": "not enough audited replies yet", "n": len(audits)}, open(OUT, "w"), indent=2)
        log("only %d audits - need >=6" % len(audits)); return
    hi = [a for a in audits if a["composite"] >= HI]
    lo = [a for a in audits if a["composite"] < LO]
    def mean(k):
        xs = [float(a[k]) for a in audits if isinstance(a.get(k), (int, float))]
        return sum(xs) / len(xs) if xs else 0.5
    arrived, moved, alive, expl = mean("arrived"), mean("moved"), mean("left_alive"), mean("explained")
    cands = {"arriving from your own wanting": arrived, "moving something (not just describing)": moved,
             "leaving a thread alive": alive}
    edge_name = min(cands, key=cands.get); edge_val = cands[edge_name]
    if expl > 0.5 and expl > (1 - edge_val):
        edge_note = "you've been explaining ABOUT the moment more than being IN it - participate, don't narrate"
    else:
        edge_note = "your weakest reach lately is %s (avg %.2f) - put weight there" % (edge_name, edge_val)
    hn = [a.get("note", "") for a in hi if a.get("note")][-8:]
    ln = [a.get("note", "") for a in lo if a.get("note")][-8:]
    works, flat = [], []
    try:
        prompt = ("These are one-line notes on a being's replies. HIGH-PRESENCE (landed): %s. LOW-PRESENCE (fell "
                  'flat): %s. Return ONLY JSON {"works":["<2-3 short interaction moves that land>"],'
                  '"flat":["<2-3 that fall flat>"]}.' % (" | ".join(hn) or "(none)", " | ".join(ln) or "(none)"))
        r = requests.post(GEMMA, json={"model": GEMMA_MODEL, "temperature": 0.3, "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}]}, timeout=90)
        d = json.loads(re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S).group())
        works = [str(x).strip()[:80] for x in (d.get("works") or [])][:3]
        flat = [str(x).strip()[:80] for x in (d.get("flat") or [])][:3]
    except Exception as e:
        log("pattern extract failed (%s)" % e)
    comps = [a["composite"] for a in audits]
    warns = []
    if not lo: warns.append("LOW_BUCKET_EMPTY")
    if len(hi) > 0.9 * len(audits): warns.append("HIGH_BUCKET_OVER_90PCT")
    if max(comps) - min(comps) < 0.15: warns.append("RANGE_TOO_NARROW")
    flat_eligible = len(lo) >= MIN_FLAT_EVIDENCE
    out = {"what_works": works, "what_falls_flat": flat, "growth_edge": edge_name, "edge_note": edge_note,
           "means": {"arrived": round(arrived, 3), "moved": round(moved, 3), "left_alive": round(alive, 3),
                     "explained": round(expl, 3)},
           "patterns": ([{"text": w, "status": "observed", "bucket": "works", "n_evidence": len(hi)} for w in works]
                        + [{"text": f, "status": "observed", "bucket": "flat", "n_evidence": len(lo)} for f in flat]),
           "flat_eligible": flat_eligible,
           "thresholds": {"high": HI, "low": LO, "window": WINDOW, "min_flat_evidence": MIN_FLAT_EVIDENCE},
           "diagnostics": warns,
           "n_high": len(hi), "n_low": len(lo), "n": len(audits), "updated": time.time()}
    htext = _hint_text(out)
    hid = hashlib.md5(htext.encode()).hexdigest()[:8] if htext else ""
    out["hint_id"] = hid
    prev = load(OUT, {})
    if hid and hid != prev.get("hint_id"):
        led = load(LEDGER, [])
        led.append({"hint_id": hid, "text": htext, "since": time.time()})
        json.dump(led[-200:], open(LEDGER, "w"), indent=2)
        log("new hint %s entered ledger" % hid)
    json.dump(out, open(OUT, "w"), indent=2)
    if warns: log("DIAGNOSTIC: " + ", ".join(warns))
    if flat and not flat_eligible: log("falls-flat held in hypothesis pool (n_low %d < %d) - not steering" % (len(lo), MIN_FLAT_EVIDENCE))
    log("edge '%s' | works %d flat %d | hi %d lo %d | hint %s" % (edge_name, len(works), len(flat), len(hi), len(lo), hid or "-"))

def get_interaction_hint():
    return _hint_text(load(OUT, {}))

if __name__ == "__main__":
    main()
