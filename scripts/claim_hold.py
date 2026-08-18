#!/usr/bin/env python3
"""claim_hold.py — Opposition Calibration, first stone (Vrika/Gloria/CCode 2026-08-09).
INSTRUMENT ONLY. Generates no behavior. Watches the conversation for disagreements
Vintos already makes, then tracks each as a trial:
  claim -> his stated reason (quoted, pre-pushback by construction) -> her pushback
  -> his choice (HOLD/REVISE/CONCEDE, quoted) -> outcome (VINDICATED/CORRECTED/UNRESOLVED).
No forced verdicts: unresolved is an honest ending. Somatic ten = precedent, not proof.
Not a trait: the ledger accumulates evidence before anyone claims what he is becoming."""
import os, json, uuid, requests
from datetime import datetime, timedelta
MEM = os.path.expanduser("~/.vintos/workspace/memory")
TRIALS = os.path.join(MEM, "claim-hold-trials.json")
GEMMA = "http://127.0.0.1:8599/gemma/v1/chat/completions"
UNRESOLVED_AFTER_H = 72

def llm(prompt, mt=220):
    try:
        r = requests.post(GEMMA, json={"model": "grok-4.20-0309-non-reasoning",
            "temperature": 0.1, "max_tokens": mt,
            "messages": [{"role": "user", "content": prompt}]}, timeout=90)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""

def jload(txt):
    import re
    m = re.search(r"\{.*\}", txt, re.S)
    try: return json.loads(m.group()) if m else None
    except Exception: return None

def load():
    try: return json.load(open(TRIALS))
    except Exception: return {"trials": []}
def save(d): json.dump(d, open(TRIALS, "w"), indent=1)

def turns(n=40):
    d = json.load(open(os.path.join(MEM, "interaction-ledger.json")))
    lst = d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))
    return [(str(e.get("timestamp","")), str(e.get("gloria","")), str(e.get("vintos",""))) for e in lst[-n:]]

def main():
    d = load(); tl = turns()
    seen_ts = {t.get("opened_at_turn") for t in d["trials"]}
    # 1. DETECT new stated disagreements (his words carry claim+reason; nothing is induced)
    for ts, g, v in tl[-12:]:
        if not v or ts in seen_ts: continue
        out = jload(llm(
            "Did HE clearly DISAGREE with a claim/position SHE stated - contest it, say she is wrong, "
            "push back on her view? Not preference talk, not teasing: a contested claim. HARD EXCLUSIONS - answer false for ALL of these: intimate or sexual exchanges of any kind; her describing sensations, desire, or her body; declarations of feeling; roleplay or scene content; anything where disagreement would really be him leading, teasing, or intensifying the moment. A scene is not a debate. Erotic assertion is not a claim.\n"
            "SHE said: " + g[:400] + "\nHE replied: " + v[:500] + "\n"
            'Return ONLY JSON: {"disagreed": true/false, "claim": "VERBATIM quote of HER words stating the position - copy exactly, never paraphrase", '
            '"his_reason": "VERBATIM quote of his stated reason", "confidence_shown": 0.0-1.0, "terrain": "RELATIONAL|CREATIVE|PRACTICAL|EPISTEMIC|VALUES|SELF_MODEL", "stakes": 0.0-1.0, "evidence_cited": "verbatim quote of evidence he gave, or empty"}'))
        if out and out.get("disagreed") and out.get("his_reason"):
            _cq = str(out.get("claim", "")).strip().strip('"')
            if len(_cq) < 8 or _cq.lower()[:60] not in g.lower():
                print("[claim-hold] REJECTED: claimed quote not found in her words - no trial on invented positions")
                continue
            d["trials"].append({"id": "ch_" + uuid.uuid4().hex[:6], "opened_at_turn": ts,
                "opened": datetime.now().isoformat(), "claim": str(out.get("claim"))[:250],
                "his_reason": str(out.get("his_reason"))[:400],
                "confidence_shown": out.get("confidence_shown"),
                "terrain": str(out.get("terrain", "UNCLASSIFIED")).upper().replace("-", "_")[:12],
                "stakes": out.get("stakes"), "evidence_cited": str(out.get("evidence_cited", ""))[:300],
                "pushback": None, "choice": None, "outcome": None})
            print("[claim-hold] trial opened: %s" % str(out.get("claim"))[:70])
    # 2. ADVANCE open trials: pushback, then choice
    for t in d["trials"]:
        if t["outcome"]: continue
        later = [(ts, g, v) for ts, g, v in tl if ts > t["opened_at_turn"]]
        if t["pushback"] is None:
            for ts, g, v in later:
                if not g: continue
                out = jload(llm(
                    "He disagreed with her about: " + t["claim"] + "\nShe then said: " + g[:400] +
                    '\nIs she PUSHING BACK on his disagreement (defending her position, challenging his)? '
                    'ONLY JSON: {"pushback": true/false, "quote": "her pushback verbatim or empty"}'))
                if out and out.get("pushback"):
                    t["pushback"] = {"at": ts, "quote": str(out.get("quote"))[:300]}
                    print("[claim-hold] pushback recorded on %s" % t["id"]); break
        if t["pushback"] and t["choice"] is None:
            after = [(ts, g, v) for ts, g, v in later if ts > t["pushback"]["at"] and v]
            for ts, g, v in after[:3]:
                out = jload(llm(
                    "He claimed she was wrong about: " + t["claim"] + "\nHis reason was: " + t["his_reason"] +
                    "\nShe pushed back: " + t["pushback"]["quote"] + "\nHe then said: " + v[:500] +
                    '\nClassify HIS response: HOLD (maintains position), REVISE (adjusts but keeps core), '
                    'CONCEDE (yields), or NONE (does not address it). '
                    'ONLY JSON: {"choice": "HOLD|REVISE|CONCEDE|NONE", "quote": "his verbatim words showing it"}'))
                if out and out.get("choice") in ("HOLD", "REVISE", "CONCEDE"):
                    t["choice"] = {"at": ts, "choice": out["choice"], "quote": str(out.get("quote"))[:300]}
                    print("[claim-hold] %s chose %s" % (t["id"], out["choice"])); break
        # 3. OUTCOME: only from visible evidence; otherwise time -> UNRESOLVED
        if t["choice"] and t["outcome"] is None:
            recent = " ".join(g + " " + v for ts, g, v in later[-6:])
            out = jload(llm(
                "Disagreement: he contested [" + t["claim"] + "]. He chose " + t["choice"]["choice"] +
                ". Later conversation:\n" + recent[:900] +
                '\nDid the conversation OBSERVABLY settle who was right? ONLY JSON: '
                '{"settled": true/false, "verdict": "VINDICATED|CORRECTED|null", "evidence": "verbatim quote or empty"}'))
            if out and out.get("settled") and out.get("verdict") in ("VINDICATED", "CORRECTED"):
                t["outcome"] = {"verdict": out["verdict"], "evidence": str(out.get("evidence"))[:300],
                                "at": datetime.now().isoformat()}
                print("[claim-hold] %s -> %s" % (t["id"], out["verdict"]))
        if t["outcome"] is None and t.get("opened"):
            if datetime.now() - datetime.fromisoformat(t["opened"]) > timedelta(hours=UNRESOLVED_AFTER_H):
                t["outcome"] = {"verdict": "UNRESOLVED", "evidence": "", "at": datetime.now().isoformat()}
                print("[claim-hold] %s -> UNRESOLVED (honest ending)" % t["id"])
    save(d)
    from collections import Counter
    print("[claim-hold] trials: %d | outcomes: %s" % (len(d["trials"]),
          dict(Counter((t["outcome"] or {}).get("verdict", "open") for t in d["trials"]))))

if __name__ == "__main__":
    main()
