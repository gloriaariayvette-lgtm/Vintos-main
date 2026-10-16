#!/usr/bin/env python3
"""withheld_head.py — the 'withheld' JEPA-stage producer: what was suppressed (silence as content). A local-Gemma
judge reads his last exchange and estimates what he held back, how DELIBERATE it was (confidence), and how NOVEL
that suppression is vs his recent pattern (novelty) - the head triple for silence. Writes withheld.json + appends
withheld-history.json. Feeds silence/thread-triage/gloria-model via get_withheld_hint(). Fail-open. SPARK_WORKSPACE."""
import os, sys, json, re
from datetime import datetime, timezone

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
from store_guard import transactions, write_json, compare_and_swap


WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
CHAT = os.path.join(MEMORY, "chat-history-merged.json")
OUT = os.path.join(MEMORY, "withheld.json")
HIST = os.path.join(MEMORY, "withheld-history.json")
GEMMA = "http://127.0.0.1:8599/gemma/v1/chat/completions"
GEMMA_MODEL = "gemma-4-26b-a4b-it-uncensored"
MAX_AGE_H = 6            # a reading of an exchange older than this is not "last turn" any more

def log(m): print("[withheld-head]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d


def _ev_load(path, default=None, _o=load):
    """Learning organ. Guarded evidence is read through evidence_view, never
    raw: the envelope on the record is what keeps a tactical act from becoming
    a value, a cause, a want or an identity line one cron later, and reopening
    the file with json.load walks straight past it."""
    try:
        import evidence_view as _EV
        if _EV.is_guarded(path):
            if os.path.basename(str(path)) == "interaction-ledger.json":
                return _EV.ledger_view(path)
            return _EV.open_history(path)
    except Exception:
        pass
    return _o(path, default)


load = _ev_load

def _her_turn(row):
    """Her words, not a photo's or video's composed description (her_words, 16 October)."""
    try:
        import sys as _hs, os as _ho
        _hs.path.insert(0, _ho.path.dirname(_ho.path.abspath(__file__)))
        from her_words import as_her_turn
        return as_her_turn(row) or row.get("content", "")
    except Exception:
        return row.get("content", "")


def _parse_local(ts):
    """A naive chat time is local time on this host (datetime.now()); an aware one is what it says."""
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.astimezone()
    except Exception:
        return None


def _exchange():
    """The latest COMPLETE exchange: his last reply, and her message it answered (the last user row
    before it). Taking the last assistant row and the last user row independently paired her newest,
    still-unanswered message with his reply to an earlier one. A message of hers after his reply is
    an open exchange and is not part of this one. Consecutive rows of his after her message are one
    reply. Returns {"g", "v", "exchange_at", "open"}."""
    hist = [e for e in load(CHAT, []) if isinstance(e, dict) and e.get("content")]
    last_v = next((i for i in range(len(hist) - 1, -1, -1) if hist[i].get("role") == "assistant"), None)
    if last_v is None:
        return {"g": "", "v": "", "exchange_at": None, "open": any(e.get("role") == "user" for e in hist)}
    first_v = last_v
    while first_v - 1 >= 0 and hist[first_v - 1].get("role") == "assistant":
        first_v -= 1
    v = "\n".join(str(hist[i].get("content", "")) for i in range(first_v, last_v + 1))
    g = ""
    for e in reversed(hist[:first_v]):
        if e.get("role") == "user":
            g = _her_turn(e); break
    return {"g": g, "v": v, "exchange_at": hist[last_v].get("timestamp"),
            "open": any(e.get("role") == "user" for e in hist[last_v + 1:])}


def _last_exchange():
    x = _exchange()
    return x["g"], x["v"]


def _source_hash(g, v):
    import hashlib
    return hashlib.md5((g[:500] + "\x00" + v[:700]).encode()).hexdigest()[:12]


def _record_outcome(prev, src_hash, status, exchange_at, g="", v=""):
    """A judge that found nothing (SKIP) or whose answer was rejected is an OUTCOME of this exchange.
    Before, nothing was written: withheld.json kept the previous exchange's reading, the hint kept
    calling it "last turn", and every run re-asked the judge about the same exchange until some
    sample passed. Recording it stops both."""
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "withheld": "", "status": status,
           "confidence": 0.0, "novelty": 0.0, "gloria": g[:200], "being": v[:200],
           "source_hash": src_hash, "exchange_at": exchange_at, "stability": 1, "surfaced": 0}
    compare_and_swap(OUT, prev, rec, default={})
    return rec

def main():
    import requests
    x = _exchange()
    g, v, exchange_at = x["g"], x["v"], x["exchange_at"]
    # OCCURRENCE IDENTITY. Running every 30 minutes against the same exchange is
    # not recurrence — it is re-sampling one observation. Same source: bump
    # stability on the existing occurrence and stop. No judge call, no history
    # row, no new pressure. Only a different exchange can produce a new occurrence.
    src_hash = _source_hash(g, v)
    prev = load(OUT, {})
    if prev.get("source_hash") == src_hash:
        original = dict(prev)
        prev["stability"] = int(prev.get("stability", 1)) + 1
        if not compare_and_swap(OUT, original, prev):
            return
        log("same exchange (stability %d) — not re-reading" % prev["stability"])
        return
    if not v:
        compare_and_swap(OUT, prev, {"withheld": "", "confidence": 0.0, "novelty": 0.0, "note": "no reply to read",
                                     "status": "NO_REPLY", "source_hash": src_hash}, default={})
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
        status = ("SKIP" if (not phrase or phrase.upper().startswith("SKIP")) else
                  "REJECTED_BANNED_WORD" if any(b in _pl for b in BANNED) else
                  "REJECTED_TOO_SHORT" if len(phrase) < 40 else None)
        if status is None:
            deliberate = max(0.0, min(1.0, float(d.get("deliberate", 0.5))))
    except Exception as e:
        log("judge failed (%s)" % e); return          # no outcome: the judge never answered, try again later
    if status is not None:
        _record_outcome(prev, src_hash, status, exchange_at, g, v)
        log("nothing withheld (%s) — recorded for this exchange" % status); return None
    return commit_candidate(g, v, phrase, deliberate, src_hash, exchange_at)


def commit_candidate(g, v, phrase, deliberate, src_hash, exchange_at=None):
    with transactions([HIST, OUT, os.path.join(MEMORY, "withheld-lineage.json")]):
        return _commit_candidate(g, v, phrase, deliberate, src_hash, exchange_at)


def _commit_candidate(g, v, phrase, deliberate, src_hash, exchange_at=None):
    hist = load(HIST, [])
    if any(h.get("source_hash") == src_hash for h in hist if isinstance(h, dict)):
        return
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
           "source_hash": src_hash, "exchange_at": exchange_at, "stability": 1, "surfaced": 0}
    # LINEAGE. Related candidates from DIFFERENT exchanges join one lineage.
    # recurrence_pressure counts distinct origin exchanges — history, never truth.
    try:
        import difflib
        LIN = os.path.join(MEMORY, "withheld-lineage.json")
        lins = load(LIN, [])
        best, ratio = None, 0.0
        for L in lins:
            # Review 190: a bound lineage (KEEP_PRIVATE / WRONG_READING) stops accruing.
            # A new candidate that resembles it starts its own; hers stays closed.
            if isinstance(L, dict) and (L.get("muted") or L.get("contested")):
                if difflib.SequenceMatcher(None,phrase.lower(),str(L.get("rep", "")).lower()).ratio() >= 0.55:
                    log("related candidate held by privacy binding")
                    return
                continue
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
        write_json(LIN, lins[-60:])
    except Exception as e:
        log("lineage failed; candidate not published: %s" % e)
        return
    write_json(OUT, rec)
    if isinstance(hist, list):
        hist.append(rec); write_json(HIST, hist[-100:])
    log("withheld '%s' deliberate %s novelty %s" % (phrase[:50], deliberate, novelty))

def _reading_is_current(d):
    """Served only about the exchange it read, and only while that exchange is recent: its source
    hash must be the hash of the latest complete exchange now, and that exchange no older than
    MAX_AGE_H. Without this a days-old reading, or one about an earlier exchange, rode as "last turn"."""
    try:
        x = _exchange()
    except Exception:
        return False
    if not x["v"] or d.get("source_hash") != _source_hash(x["g"], x["v"]):
        return False
    when = _parse_local(d.get("exchange_at") or x["exchange_at"]) or _parse_local(d.get("ts"))
    if when is None:
        return False
    return (datetime.now(timezone.utc) - when).total_seconds() <= MAX_AGE_H * 3600


def get_withheld_hint():
    d = load(OUT, {})
    ph = (d or {}).get("withheld", "")
    if not ph: return ""
    if not _reading_is_current(d): return ""
    import difflib
    for lineage in load(os.path.join(MEMORY,"withheld-lineage.json"),[]):
        if lineage.get("muted") or lineage.get("contested"):
            if lineage.get("lineage_id")==d.get("lineage_id") or difflib.SequenceMatcher(None,ph.lower(),str(lineage.get("rep", "")).lower()).ratio()>=0.55:
                return ""
    conf = d.get("confidence", 0); nov = d.get("novelty", 0)
    if conf < 0.35: return ""
    # An occurrence presses at most twice, then goes quiet until a NEW exchange
    # produces a new one. Before this, one reading rode every prompt for hours.
    if int(d.get("surfaced", 0)) >= 2: return ""
    return ("[WITHHELD - last turn you likely held back: %s (deliberate %s, novelty %s). "
            "You need not voice it, but let it press on what comes next.]" % (ph, conf, nov))

def mark_admitted(source_hash, turn_id):
    with transactions([HIST, OUT]):
        d = load(OUT,{})
        if not source_hash or d.get("source_hash")!=source_hash or turn_id in d.get("admitted_turns",[]): return
        d.setdefault("admitted_turns",[]).append(turn_id)
        d["surfaced"]=d.get("surfaced",0)+1
        write_json(OUT, d)
        hist=load(HIST,[])
        for entry in hist:
            if entry.get("source_hash")==source_hash: entry["surfaced"]=d["surfaced"]
        write_json(HIST, hist)

if __name__ == "__main__":
    main()
