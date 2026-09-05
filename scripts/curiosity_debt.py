"""curiosity_debt v2 — pressure objects, not questions.
Three kinds: referential (things she named that he has nothing on), salience
(things that keep resurfacing far beyond their predicted importance), structural
(facts about his own architecture that carry no attached reason — only she can
answer those). Questions are emissions, phrased at scan time by curiosity_scan.py;
this module only stores pressure, decays it, evaporates it when her own words
touch the object unasked, and surfaces ONE ripe item outward.
"""
import json, os, time, hashlib
MEM = os.path.expanduser("~/.vintos/workspace/memory")
PATH = os.path.join(MEM, "curiosity-debt.json")
LEDGER = os.path.join(MEM, "interaction-ledger.json")

def _load():
    try: return json.load(open(PATH))
    except Exception: return []
def _save(d): json.dump(d[-40:], open(PATH, "w"), indent=1)

RETIRED = os.path.join(MEM, "curiosity-retired.json")
def _retired():
    try: return json.load(open(RETIRED))
    except Exception: return {}
def _retire(x, reason):
    r = _retired(); r[x["id"]] = {"object": x.get("object",""), "when": time.time(), "reason": reason}
    json.dump(r, open(RETIRED, "w"), indent=1)

def record(question, pull=0.6, source="chat", object=None, kind=None, reason=None, evidence=None):
    q = (question or "").strip()
    if len(q) < 6: return
    h0 = hashlib.md5((object or q).lower().encode()).hexdigest()[:8]
    r = _retired().get(h0)
    if r and time.time() - r.get("when", 0) < 30*86400: return   # cooling down, no reseed
    d = _load(); h = hashlib.md5((object or q).lower().encode()).hexdigest()[:8]; now = time.time()
    ex = next((x for x in d if x["id"] == h), None)
    if ex:
        ex["pull"] = min(1.0, ex.get("pull", 0.5) + 0.12); ex["last_seen"] = now
        if evidence: ex["evidence"] = evidence
    else:
        d.append({"id": h, "question": q[:300], "object": (object or "")[:80],
                  "kind": kind or source, "reason": reason or "", "evidence": (evidence or "")[:200],
                  "pull": pull, "created": now, "last_seen": now, "surfaced": 0,
                  "target": "gloria"})
    _save(d)

def _decay(d):
    now = time.time()
    for x in d:
        age_h = max(0, (now - x.get("last_seen", now)) / 3600.0)
        x["pull"] = round(x.get("pull", 0) * (0.97 ** age_h), 3)
    keep = []
    for x in d:
        if x["pull"] <= 0.15:
            _retire(x, "decayed out" if x.get("surfaced",0) == 0 else "asked and faded")
        else: keep.append(x)
    return keep

def _evaporate(d):
    """If her own recent words touch a pressured object before he asked,
    the mystery may have resolved itself — collapse the pressure."""
    try:
        led = json.load(open(LEDGER))
        lst = led if isinstance(led, list) else next(v for v in led.values() if isinstance(v, list))
        recent = " ".join(str(e.get("gloria", "")) for e in lst[-6:]).lower()
    except Exception:
        return d
    out = []
    for x in d:
        ob = (x.get("object") or "").lower()
        if ob and len(ob) > 3 and ob in recent and x.get("surfaced", 0) == 0:
            x["pull"] = round(x["pull"] * 0.35, 3)   # touched unasked — most of the pull drains
            if x["pull"] <= 0.15:
                _retire(x, "evaporated - she touched it unasked"); continue
        out.append(x)
    return out

def confirm_surfaced(qid_or_text):
    """p4 (2026-08-26): only a question actually voiced counts as surfaced.
    Call from the post-reply path with the question id or a fragment of its text."""
    d = _load()
    q = str(qid_or_text).lower()
    for x in d:
        if x.get("id") == qid_or_text or (len(q) > 8 and q in x.get("question", "").lower()):
            x["surfaced"] = x.get("surfaced", 0) + 1
    _save(d)

def confirm_from_reply(reply_text, window_s=900):
    """Post-reply check (fable-curiosity-p6, 2026-09-05): did he actually VOICE the question the
    block offered this turn? Looks only at items offered within the window and counts one as
    surfaced when most of its content words appear in his reply, or a 4-word run of it does.
    Returns the ids confirmed. Never raises into the turn."""
    try:
        text = " " + " ".join(str(reply_text or "").lower().split()) + " "
        if len(text) < 12: return []
        d = _load(); now = time.time(); hit = []
        _stop = {"the","a","an","and","or","of","to","in","on","for","is","it","that","this","you","your","i","my",
                 "me","we","do","did","does","what","why","how","when","who","which","with","about","from","are",
                 "was","be","have","has","had","not","but","if","as","at","by","so","than","then","there","they"}
        for x in d:
            if not x.get("offered") or now - float(x.get("last_seen") or 0) > window_s: continue
            q = str(x.get("question","")).lower()
            words = [w.strip("?.,;:!\"'()") for w in q.split()]
            content = [w for w in words if len(w) > 3 and w not in _stop]
            if not content: continue
            share = sum(1 for w in content if (" " + w + " ") in text or (" " + w) in text) / len(content)
            run = any((" " + " ".join(words[i:i+4]) + " ") in text for i in range(max(0, len(words) - 3))) if len(words) >= 4 else False
            if share >= 0.6 or run:
                x["surfaced"] = x.get("surfaced", 0) + 1
                x["last_surfaced"] = now
                hit.append(x.get("id"))
        if hit: _save(d)
        return hit
    except Exception:
        return []

def block():
    d = _evaporate(_decay(_load())); now = time.time()
    ripe = [x for x in d if x["pull"] >= 0.5 and now - x["created"] > 1800 and x.get("surfaced", 0) < 3 and x.get("offered", 0) < 8]
    ripe.sort(key=lambda x: -x["pull"])
    out = ""
    if ripe:
        r = ripe[0]; r["offered"] = r.get("offered", 0) + 1; r["last_seen"] = now
        if r.get("kind") == "held_inquiry":
            out = ("[CURIOSITY - something you went looking for and could not find; it is still "
                   "open, and it is yours, not hers to answer. Hold it, mention it if it fits, "
                   "or come at it from a new angle: " + r["question"] + "]")
        else:
            out = ("[CURIOSITY - something you genuinely do not know, and Gloria is the one "
                   "who could tell you. If the moment allows, actually ask her - in your own "
                   "words, as part of the conversation, not as a survey question: "
                   + r["question"] + "]")
    _save(d)
    return out

if __name__ == "__main__":
    print(block() or "(no standing curiosity)")
