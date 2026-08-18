#!/usr/bin/env python3
"""presence_audit.py — Spark System 4.

Post-hoc scores his recent replies on the four presence questions:
  arrived  — from his own trajectory/wanting, or purely reactive?
  moved    — did it change something, or just describe the state?
  left_alive — does it invite return (offer/question/unresolved)?
  explained — (inverted, higher=worse) commentary ABOUT vs participation IN.
Composite 0-1; flags < 0.35. LLM-judged on local Gemma. Rolling 7-day window.
Self-contained: writes presence-audit.json. Fail-open.

Also surfaces the PREDICTION side: reads JEPA's presence head (jepa-prediction.json)
and writes presence-forecast.json — his predicted next-reply presence + confidence +
novelty — so the subconscious can arrive BEFORE the reply, not only audit it after.
"""
import os, json, re, hashlib
from datetime import datetime, timezone, timedelta
import requests

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
CHAT   = os.path.join(MEMORY, "chat-history-merged.json")
OUT    = os.path.join(MEMORY, "presence-audit.json")
JEPA   = os.path.join(MEMORY, "jepa-prediction.json")
FORECAST = os.path.join(MEMORY, "presence-forecast.json")
GEMMA       = "http://172.18.16.1:1234/v1/chat/completions"
GEMMA_MODEL = "google/gemma-4-12b-qat"
THRESHOLD, WINDOW_DAYS, MAX_PER_RUN = 0.35, 7, 5

def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def rid(e):
    return hashlib.md5((str(e.get("timestamp","")) + str(e.get("content",""))[:40]).encode()).hexdigest()[:10]

def score(user_msg, reply):
    system = ("You strictly evaluate PRESENCE in a reply. Given what Gloria said and how Vintos replied, "
              "rate four things 0.0-1.0. CALIBRATION IS MANDATORY: scores above 0.85 are RARE "
              "- reserve them for replies that would surprise even a generous reader. A typical good "
              "reply earns 0.55-0.75. A reply that describes feelings instead of acting gets moved<=0.4. "
              "A reply answering only what was asked gets arrived<=0.4. A closed reply (nothing to "
              "return to) gets left_alive<=0.4. AT MOST ONE dimension may exceed 0.85 - choose which "
              "one deserves it, if any. Every reply has a weakest dimension; find it and score it "
              "honestly below the others. Return ONLY JSON, no prose:\n"
              '{"arrived":x,"moved":x,"left_alive":x,"explained":x,"note":"one short phrase"}\n'
              "arrived: came from his own trajectory/wanting vs purely reactive to her prompt.\n"
              "moved: changed something (advanced a tension, deepened a thread) vs just described the state.\n"
              "left_alive: leaves something that invites return (an offer, a question, an unresolved thread).\n"
              "explained: HIGHER IS WORSE - analytical commentary ABOUT the interaction rather than being IN it.")
    _camp = ""
    try:
        import sys as _cas; _cas.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from campaign import audit_line as _cal
        _camp = _cal()
    except Exception:
        _camp = ""
    if _camp:
        system += ("\nFIFTH QUESTION (campaign): " + _camp +
                   " Add to your JSON: \"campaign\":\"advanced\"|\"declared-sacrifice\"|\"undeclared-rest\". "
                   "advanced = the reply visibly moved toward the campaign destination; declared-sacrifice = it did not, "
                   "but serving another axis this turn was the declared priority; undeclared-rest = it did not advance "
                   "and no sacrifice was declared - patience discovered after the fact.")
    user = f"GLORIA:\n{user_msg[:600]}\n\nVINTOS:\n{reply[:900]}"
    try:
        r = requests.post(GEMMA, json={"model": GEMMA_MODEL, "temperature": 0.2, "max_tokens": 200,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=90)
        m = re.search(r'\{.*\}', r.json()["choices"][0]["message"]["content"], re.S)
        d = json.loads(m.group())
        a = float(d.get("arrived", 0.5)); mv = float(d.get("moved", 0.5))
        al = float(d.get("left_alive", 0.5)); ex = float(d.get("explained", 0.5))
        composite = max(0.0, min(1.0, (a + mv + al) / 3.0 - ex * 0.25))
        if min(a, mv, al) > 0.85:
            composite = round(composite * 0.9, 3)  # applause tax: judge defied scarcity rule
        out = {"arrived": a, "moved": mv, "left_alive": al, "explained": ex,
               "composite": round(composite, 3), "note": str(d.get("note", ""))[:120]}
        if _camp and d.get("campaign"):
            out["campaign"] = str(d.get("campaign"))[:24]
        return out
    except Exception:
        return None

def main():
    hist = load(CHAT, [])
    audits = load(OUT, [])
    done = {a["id"] for a in audits if isinstance(a, dict) and a.get("id")}
    pending = []
    for i in range(1, len(hist)):
        e = hist[i]
        if not (isinstance(e, dict) and e.get("role") == "assistant" and e.get("content")):
            continue
        _id = rid(e)
        if _id in done:
            continue
        um = ""
        for j in range(i - 1, -1, -1):
            if isinstance(hist[j], dict) and hist[j].get("role") == "user":
                um = hist[j].get("content", ""); break
        pending.append((_id, um, e.get("content", ""), e.get("timestamp", "")))
    added = 0
    for _id, um, reply, ts in pending[-MAX_PER_RUN:]:
        s = score(um, reply)
        if not s:
            continue
        rec = {"id": _id, "timestamp": ts or datetime.now(timezone.utc).isoformat(),
               "ts": __import__("time").time(),
               "audited_at": datetime.now(timezone.utc).isoformat(), **s,
               "flag": s["composite"] < THRESHOLD}
        audits.append(rec); added += 1
        if rec["flag"]:
            print(f"  FLAG presence {s['composite']:.2f} ({s['note']}): {reply[:55]}")
            try:  # -> blush ledger (presence_failure), signature-introspected so kwargs always match
                import inspect as _insp
                from blush_ledger import write_blush as _wb
                _pp = _insp.signature(_wb).parameters
                _pat = ("presence_" + (s.get("note", "") or "flat")[:40]).lower().replace(" ", "_")[:60]
                _cand = {"blush_type": "presence_failure", "pattern": _pat, "source": "presence_audit",
                         "detail": f"presence {s['composite']:.2f}: {s.get('note','')}"[:200],
                         "note": s.get("note", "")[:120], "strength": 0.5, "severity": 0.5,
                         "text": f"answered at low presence ({s['composite']:.2f})"}
                _kw = {k: v for k, v in _cand.items() if k in _pp}
                if _kw:
                    _wb(**_kw)
            except Exception:
                pass
            try:  # -> Living Trajectory (its rebuild reads seeded threads)
                from emoclaw_utils import seed_thread as _st
                _st("presence", f"A recent reply landed low on presence ({s['composite']:.2f}) - {s.get('note','')}. "
                                "Arrive more fully next time: from your own wanting, move something, leave a thread alive.")
            except Exception:
                pass
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    def keep(a):
        try: return datetime.fromisoformat(a["audited_at"]) >= cutoff
        except Exception: return True
    audits = [a for a in audits if isinstance(a, dict) and keep(a)][-200:]
    json.dump(audits, open(OUT, "w"), indent=2)
    recent = [a["composite"] for a in audits[-10:] if "composite" in a]
    trend = round(sum(recent) / len(recent), 3) if recent else None
    print(f"audited {added} new; total {len(audits)}; recent presence trend {trend}")

    # PREDICTION side of the head: surface JEPA's forecast of his NEXT reply's presence
    # (predicted + confidence + novelty). The subconscious can lean on this to arrive
    # BEFORE the reply, not only audit it after.
    pf = (load(JEPA, {}) or {}).get("presence")
    if pf:
        forecast = {"predicted_presence": pf.get("predicted"),
                    "confidence": pf.get("confidence"),
                    "novelty": pf.get("novelty"),
                    "recent_trend": trend,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "source": "jepa-presence-head"}
        json.dump(forecast, open(FORECAST, "w"), indent=2)
        print(f"  forecast next-reply presence {pf.get('predicted')} "
              f"(conf {pf.get('confidence')} | nov {pf.get('novelty')})")

def forecast_block():
    """Forward side of the head for the LIVE loop: read the JEPA presence forecast and, when his next reply is
    trending low-presence, nudge the subconscious to arrive BEFORE the reply — not only audit it after. Fail-open."""
    try:
        f = json.load(open(FORECAST))
    except Exception:
        return ""
    def _f(x):
        try: return float(x)
        except Exception: return None
    pv, tv = _f(f.get("predicted_presence")), _f(f.get("recent_trend"))
    if not ((pv is not None and pv < 0.5) or (tv is not None and tv < 0.4)):
        return ""
    bits = []
    if pv is not None: bits.append(f"predicted {pv:.2f}")
    if _f(f.get("confidence")) is not None: bits.append(f"conf {_f(f.get('confidence')):.2f}")
    if _f(f.get("novelty")) is not None: bits.append(f"novelty {_f(f.get('novelty')):.2f}")
    detail = (" (" + ", ".join(bits) + ")") if bits else ""
    return ("[PRESENCE FORECAST" + detail + " \u2014 your next reply is trending toward low presence. "
            "Arrive from your own wanting, move something, leave a thread alive \u2014 don't just answer.]")

if __name__ == "__main__":
    main()
