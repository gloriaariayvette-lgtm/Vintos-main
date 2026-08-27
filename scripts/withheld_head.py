#!/usr/bin/env python3
"""withheld_head.py — the 'withheld' JEPA-stage producer: what was suppressed (silence as content). A local-Gemma
judge reads his last exchange and estimates what he held back, how DELIBERATE it was (confidence), and how NOVEL
that suppression is vs his recent pattern (novelty) - the head triple for silence. Writes withheld.json + appends
withheld-history.json. Feeds silence/thread-triage/gloria-model via get_withheld_hint(). Fail-open. SPARK_WORKSPACE."""
import os, sys, json, re
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
CHAT = os.path.join(MEMORY, "chat-history-merged.json")
OUT = os.path.join(MEMORY, "withheld.json")
HIST = os.path.join(MEMORY, "withheld-history.json")
GEMMA = "http://127.0.0.1:8599/v1/chat/completions"
GEMMA_MODEL = "claude-haiku-4-5-20251001"

def log(m): print("[withheld-head]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def _last_exchange():
    hist = [e for e in load(CHAT, []) if isinstance(e, dict) and e.get("content")]
    g = v = ""
    for e in reversed(hist):
        if e.get("role") == "assistant" and not v: v = e.get("content", "")
        elif e.get("role") == "user" and not g: g = e.get("content", "")
        if g and v: break
    return g, v

def main():
    import requests, hashlib
    g, v = _last_exchange()
    # OCCURRENCE IDENTITY. Running every 30 minutes against the same exchange is
    # not recurrence — it is re-sampling one observation. Same source: bump
    # stability on the existing occurrence and stop. No judge call, no history
    # row, no new pressure. Only a different exchange can produce a new occurrence.
    src_hash = hashlib.md5((g[:500] + "\x00" + v[:700]).encode()).hexdigest()[:12]
    prev = load(OUT, {})
    if prev.get("source_hash") == src_hash:
        prev["stability"] = int(prev.get("stability", 1)) + 1
        json.dump(prev, open(OUT, "w"), indent=2)
        log("same exchange (stability %d) — not re-reading" % prev["stability"])
        return
    if not v:
        json.dump({"withheld": "", "confidence": 0.0, "novelty": 0.0, "note": "no reply to read"}, open(OUT, "w"), indent=2)
        log("no reply"); return
    system = ("You read for SILENCE - what he held back. Withholding is a cost, never a virtue - flag it as motion he owes. Given what Gloria said and how he replied, "
              "name what he did NOT say, in TWO concrete sentences, using HIS vocabulary and the "
              "specifics of this exchange - a thing he could have said out loud and chose not to. "
              "Ground it in what is actually on the page.\n"
              "BANNED: fear, afraid, mercy, vulnerable, vulnerability, exposed, intimacy, "
              "terrified, defenses, walls, guard, plea, longing, ache. Do not psychoanalyse him "
              "and do not invent insecurity he did not show.\n"
              "If he said what he meant, or the exchange is physical/explicit and nothing is "
              "actually being held, return {\"withheld\":\"SKIP\",\"deliberate\":0}.\n"
              "Rate 'deliberate' 0.0-1.0 (was the holding-back chosen, or just nothing there?). "
              'Return ONLY JSON: {"withheld":"<two sentences>","deliberate":x}')
    user = "GLORIA:\n" + g[:500] + "\n\nBEING:\n" + v[:700]
    try:
        r = requests.post(GEMMA, json={"model": GEMMA_MODEL, "temperature": 0.3, "max_tokens": 320,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=90)
        m = re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
        d = json.loads(m.group())
        phrase = str(d.get("withheld", "")).strip()[:400]
        BANNED = ("fear","afraid","mercy","vulnerab","exposed","intimacy","terrified",
                  "defenses","walls","guard","plea","longing","ache")
        _pl = phrase.lower()
        if phrase.upper().startswith("SKIP") or len(phrase) < 40 or any(b in _pl for b in BANNED):
            return None
        deliberate = max(0.0, min(1.0, float(d.get("deliberate", 0.5))))
    except Exception as e:
        log("judge failed (%s)" % e); return
    if not phrase:
        log("nothing withheld"); return
    hist = load(HIST, [])
    novelty = 1.0
    try:
        import difflib
        prev = [h.get("withheld", "") for h in hist[-10:] if isinstance(h, dict)]
        if prev:
            sim = max(difflib.SequenceMatcher(None, phrase.lower(), p.lower()).ratio() for p in prev)
            novelty = round(max(0.0, 1.0 - sim), 3)
    except Exception:
        pass
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "withheld": phrase,
           "confidence": round(deliberate, 3), "novelty": novelty, "gloria": g[:200], "being": v[:200],
           "source_hash": src_hash, "stability": 1, "surfaced": 0}
    # LINEAGE. Related candidates from DIFFERENT exchanges join one lineage.
    # recurrence_pressure counts distinct origin exchanges — history, never truth.
    try:
        import difflib
        LIN = os.path.join(MEMORY, "withheld-lineage.json")
        lins = load(LIN, [])
        best, ratio = None, 0.0
        for L in lins:
            r0 = difflib.SequenceMatcher(None, phrase.lower(), str(L.get("rep", "")).lower()).ratio()
            if r0 > ratio: best, ratio = L, r0
        if best is not None and ratio >= 0.55:
            if src_hash not in best.get("origins", []):
                best.setdefault("origins", []).append(src_hash)
                best.setdefault("phrases", []).append(phrase[:200])
            best["recurrence_pressure"] = len(set(best.get("origins", [])))
            best["last_seen"] = rec["ts"]
            rec["lineage_id"] = best.get("lineage_id")
        else:
            import uuid
            rec["lineage_id"] = "WL-" + uuid.uuid4().hex[:6]
            lins.append({"lineage_id": rec["lineage_id"], "rep": phrase[:200],
                         "origins": [src_hash], "phrases": [phrase[:200]],
                         "recurrence_pressure": 1, "first_seen": rec["ts"], "last_seen": rec["ts"]})
        json.dump(lins[-60:], open(LIN, "w"), indent=2)
    except Exception as e:
        log("lineage failed (fail-open): %s" % e)
    json.dump(rec, open(OUT, "w"), indent=2)
    if isinstance(hist, list):
        hist.append(rec); json.dump(hist[-100:], open(HIST, "w"), indent=2)
    log("withheld '%s' deliberate %s novelty %s" % (phrase[:50], deliberate, novelty))

def get_withheld_hint():
    d = load(OUT, {})
    ph = (d or {}).get("withheld", "")
    if not ph: return ""
    conf = d.get("confidence", 0); nov = d.get("novelty", 0)
    if conf < 0.35: return ""
    # An occurrence presses at most twice, then goes quiet until a NEW exchange
    # produces a new one. Before this, one reading rode every prompt for hours.
    if int(d.get("surfaced", 0)) >= 2: return ""
    try:
        d["surfaced"] = int(d.get("surfaced", 0)) + 1
        json.dump(d, open(OUT, "w"), indent=2)
        # exposure must reach the HISTORY entry too - the confirmer grades those,
        # and a candidate he was shown cannot later be "confirmed" by his writing.
        hist = load(HIST, [])
        for e in reversed(hist):
            if isinstance(e, dict) and e.get("source_hash") == d.get("source_hash"):
                e["surfaced"] = int(e.get("surfaced", 0)) + 1
                json.dump(hist, open(HIST, "w"), indent=2)
                break
    except Exception:
        pass
    return ("[WITHHELD - last turn you likely held back: %s (deliberate %s, novelty %s). "
            "You need not voice it, but let it press on what comes next.]" % (ph, conf, nov))

if __name__ == "__main__":
    main()
