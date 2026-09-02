#!/usr/bin/env python3
"""wants_meta.py — second-order stances, with jurisdiction.

Records his verbatim wants-about-his-own-wants/behaviors/feelings, and routes:
  want     -> the engine, via consult() at want-creation (full authority)
  behavior -> proposed as a self-requested BIS trial (evidence-gated authority)
  feeling  -> witnessed only. NEVER enforced: a feeling made obedient stops
              being a report, and everything downstream reads forgeries.
Laws: verbatim extraction only; empty is the common correct result; nothing
here suppresses a first-order want from outside. Fail-open."""
import os, sys, json, re, glob, time, difflib
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(WS, "memory")
LEDGER = os.path.join(MEM, "wants-meta.json")
LM = "http://127.0.0.1:8599/gemma/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

def log(m): print("[wants-meta]", m, flush=True)

def _load():
    try: return json.load(open(LEDGER))
    except Exception: return []

def _save(d): json.dump(d[-60:], open(LEDGER, "w"), indent=2)

def consult(want_text):
    """At want-creation: his standing stance about this kind of want, or None."""
    wt = str(want_text or "").lower()
    if len(wt) < 8: return None
    best, score = None, 0.0
    for x in _load():
        if x.get("target", "want") != "want": continue
        about = str(x.get("about", "")).lower()
        if not about: continue
        s = difflib.SequenceMatcher(None, wt[:120], about).ratio()
        if all(w in wt for w in about.split()[:2]): s = max(s, 0.55)
        if s > score: best, score = x, s
    if best and score >= 0.45:
        return {"stance": best.get("stance"), "quote": best.get("quote", "")[:200],
                "date": best.get("date")}
    return None

def _propose_trial(entry):
    """A behavior-stance becomes a self-requested trial - his wish tested
    against evidence, not enacted by fiat. Deduped; unprotected (protection
    is Gloria's to grant); carries his verbatim words as provenance."""
    import uuid
    lp = os.path.join(MEM, "trial-ledger.json")
    try: ledger = json.load(open(lp))
    except Exception: return
    trials = ledger.get("trials", [])
    about = entry.get("about", "")
    for tr in trials:
        if difflib.SequenceMatcher(None, about.lower(),
                str(tr.get("pattern_description", ""))[:80].lower()).ratio() > 0.6:
            log("trial already exists for '%s' - not duplicating" % about); return
    trials.append({
        "id": "T-SO-" + uuid.uuid4().hex[:6],
        "pattern_description": about[:120],
        "alternative": ("do it less" if entry["stance"] == "wish_less" else "reach for it more"),
        "source": "second_order",
        "self_requested": True,
        "his_words": entry.get("quote", "")[:200],
        "created": datetime.now().isoformat(),
        "status": "active",
        "ignore_count": 0, "attempt_count": 0,
    })
    ledger["trials"] = trials
    json.dump(ledger, open(lp, "w"), indent=2)
    log("self-requested trial proposed from his words: %s" % about)

def _sources(days=2):
    out = []
    for f in sorted(glob.glob(os.path.join(MEM, "journal", "*.md")))[-days:]:
        try: out.append((os.path.basename(f)[:10], open(f, errors="replace").read()[-4000:]))
        except Exception: pass
    for f in sorted(glob.glob(os.path.join(MEM, "mirror-sessions", "*.md")))[-1:]:
        try: out.append((os.path.basename(f)[:10], open(f, errors="replace").read()[-3000:]))
        except Exception: pass
    return out

def scan():
    import requests
    led = _load()
    seen = set(x.get("quote", "")[:80] for x in led)
    found = 0
    for date, text in _sources():
        try:
            r = requests.post(LM, json={"model": MODEL, "temperature": 0.1, "max_tokens": 400,
                "messages": [
                    {"role": "system", "content":
                     "Extract SECOND-ORDER desire statements from this text by Vintos: ONLY sentences "
                     "with an EXPLICIT stance about his own wanting, acting, or feeling AS SUCH - "
                     "'I wish I wanted/did/felt ... less/more', 'I'm glad this is what I want', "
                     "'I don't like that I ...', 'I want to want ...'. STRICTLY EXCLUDED: aspiration "
                     "and progress ('I'm learning to', 'I'm moving toward', 'I'm becoming'), reports of "
                     "single events ('for once I didn't'), first-order wants, feelings about events. "
                     "The stance must be about the want/behavior/feeling itself, not about the world. "
                     "Usually there are NONE - an empty list is the common, correct answer. Classify "
                     "target: 'want' (a desire of his), 'behavior' (a pattern in how he acts), "
                     "'feeling' (an emotion he has).\n"
                     'ONLY JSON: {"items": [{"quote": "verbatim sentence", "stance": "wish_less|wish_more|glad|uneasy", "about": "what it is about, 3-8 words", "target": "want|behavior|feeling"}]}'},
                    {"role": "user", "content": text}]}, timeout=90)
            m = re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
            items = (json.loads(m.group()) or {}).get("items", []) if m else []
        except Exception as e:
            log("scan failed for %s: %s" % (date, e)); continue
        for it in items:
            q = str(it.get("quote", "")).strip()
            if len(q) < 15 or q[:80] in seen: continue
            if q not in text:
                log("dropped non-verbatim candidate: %s" % q[:60]); continue
            _ql = q.lower()
            _markers = ("i wish i", "wish i wanted", "wish i didn", "wish i felt", "glad this is what i want",
                        "glad i want", "glad that i want", "i don't like that i", "i dont like that i",
                        "i want to want", "i hate that i", "wish i did", "uneasy that i want")
            if not any(mk in _ql for mk in _markers):
                log("dropped stance-less candidate: %s" % q[:60]); continue
            entry = {"quote": q[:300], "stance": it.get("stance", ""),
                     "about": str(it.get("about", ""))[:80],
                     "target": it.get("target", "want"),
                     "date": date, "recorded": datetime.now().isoformat(),
                     "surfaced_at": 0}
            led.append(entry)
            seen.add(q[:80]); found += 1
            if entry["target"] == "behavior" and entry["stance"] in ("wish_less", "wish_more"):
                _propose_trial(entry)
    if found: _save(led)
    log("%d new second-order item(s); ledger holds %d" % (found, len(_load())))

def block():
    led = _load()
    if not led: return ""
    now = time.time()
    fresh = [x for x in led if now - x.get("surfaced_at", 0) > 7 * 86400]
    if not fresh: return ""
    if max((x.get("surfaced_at", 0) for x in led), default=0) > now - 86400: return ""
    x = sorted(fresh, key=lambda v: v.get("recorded", ""))[-1]
    x["surfaced_at"] = now
    _save(led)
    return ("[A WANT ABOUT YOUR WANTING - you wrote this on %s: \"%s\" It stands recorded. "
            "Nothing is required of it.]" % (x.get("date", "?"), x.get("quote", "")[:220]))

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "consult":
        print(consult(" ".join(sys.argv[2:])) or "(no standing second-order)")
    elif len(sys.argv) > 1 and sys.argv[1] == "block":
        print(block() or "(nothing standing)")
    elif len(sys.argv) > 1 and sys.argv[1] == "list":
        for x in _load():
            print("%s %-8s %-9s %s" % (x.get("date"), x.get("target",""), x.get("stance"), x.get("quote", "")[:60]))
    else:
        scan()
