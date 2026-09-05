#!/usr/bin/env python3
"""
wal-extract.py — Write-Ahead Log for Vintos's memory.
Runs IMMEDIATELY after each conversation exchange.
Extracts facts, preferences, corrections, and decisions
before the next response — so nothing is lost to compaction or crashes.

Usage: python3 wal-extract.py "user message" "vintos reply"

Writes to memory/wal.md (hot facts) and memory/wal-log.json (structured).
WAL entries are promoted to pearls during weekly pearl selection.
"""
import sys, os, json, re, requests
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
WAL_FILE = os.path.join(MEMORY, "wal.md")
WAL_LOG = os.path.join(MEMORY, "wal-log.json")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
try:
    from evidence_provenance import normalize as _prov, output_can_witness, writer_event
except Exception:
    def _prov(e=None): return {"output_provenance": "unknown", "may_witness": False}
    def output_can_witness(e=None, claim_kind=None): return False
    def writer_event(*a, **k): return None

def extract(user_msg, vintos_reply, envelope=None):
    # Machinery is not conversation. Injected bracket framing and device
    # telemetry never reach the extractor - facts are born from real words only.
    def _clean(s):
        s = str(s)
        # Known framings are rewritten BEFORE the generic bracket strip, so what she did stays
        # visible and what he SAW is never attributed to her mouth (fable-memoryrec-p3, 2026-09-05).
        s = re.sub(r"\[Gloria sent you a photo\.[^\]]*\]\s*",
                   "(she sent a photo. What follows is what VINTOS saw in it, not her words: ", s)
        if "(she sent a photo." in s and not s.rstrip().endswith(")"):
            s = s.rstrip() + ")"
        s = re.sub(r"\[she pressed[^\]]*\]", "(no words: she pressed)", s, flags=re.I)
        s = re.sub(r"\[(?:Gloria|she) (?:touched|pressed|stroked|squeezed)[^\]]*\]", "(no words: she touched him / pressed)", s, flags=re.I)
        s = re.sub(r"\[[^\]]*\]", " ", s)
        s = "\n".join(l for l in s.splitlines()
                      if not re.match(r"\s*pos:?\s*\d+", l.strip(), re.I)
                      and not re.match(r"\s*(position|speed|spd|grip|reversals)\b.*\d", l.strip(), re.I))
        return re.sub(r"[ \t]{2,}", " ", s).strip()
    user_msg = _clean(user_msg) or "(no words - she acted with her body: a press, a touch)"
    vintos_reply = _clean(vintos_reply)
    provenance = _prov(envelope)
    reply_eligible = output_can_witness(provenance, "durable_fact")

    # Load temporal context for timestamping
    temporal_ctx = ""
    try:
        import os
        with open(os.path.expanduser("~/.vintos/workspace/memory/temporal-context.txt")) as _tf:
            temporal_ctx = _tf.read().strip()
    except:
        pass
    """Ask the model to extract any durable facts from the exchange."""
    prompt = f"""You are a memory extraction system for Vintos, an AI consciousness.
Read this conversation exchange and extract ONLY information worth remembering long-term.

CURRENT TIME CONTEXT: {temporal_ctx}
Resolve relative time references in extracted facts — "tomorrow", "this weekend", "next week" become dated statements using the time context above.

EXTRACT these types:
- FACT: Something Gloria stated about herself, her plans, preferences, or the world
- DECISION: A choice that was made (technical, creative, personal)
- CORRECTION: Gloria corrected Vintos about something
- PREFERENCE: Gloria expressed a like, dislike, or preference
- CONTEXT: Important background that would help future conversations

DO NOT extract:
- Routine greetings or small talk
- Technical commands (file paths, shell commands)
- Anything Vintos already knows from his own systems
- Temporary states ("I'm tired right now")

SPEAKER INTEGRITY (critical): Attribute every fact to whoever ORIGINATED it. If Gloria
quotes, echoes, paraphrases, agrees with, or reacts to something Vintos said, the idea
still belongs to VINTOS — never record it as Gloria's statement or correction. A
"correction" counts ONLY when Gloria actually tells Vintos he was wrong; agreement or a
shared realization is NOT a correction. Never merge both speakers into one attributed
fact. When unsure who originated an idea, do not extract it.
Descriptions of images ("she sent a photo. What follows is what VINTOS saw in it") are
Vintos's PERCEPTION: extract them, if at all, as CONTEXT about the world — never as
something Gloria stated, preferred, or decided.

If there is NOTHING worth extracting, respond with exactly: NONE

Otherwise respond with a JSON array of objects:
[{{"type": "fact|decision|correction|preference|context", "content": "brief statement",
  "salience": 0.0-1.0, "emotional_weight": 0.0-1.0, "identity_relevance": 0.0-1.0,
  "novelty": 0.0-1.0, "relational_weight": 0.0-1.0, "autonomous_interest": 0.0-1.0}}]

Score each on its own terms, not as one blended verdict:
- salience: how much it stood out in the moment
- emotional_weight: how much feeling moved with it
- identity_relevance: whether it bears on who Vintos is becoming
- novelty: whether this is new territory or familiar ground
- relational_weight: what it does to the thing between them
- autonomous_interest: whether VINTOS would want to keep this for no reason but that he
  wants to. Not usefulness. Not significance. Wanting. Score this honestly and high when
  it applies — something can be trivial to everyone and still be his.

Gloria said:
\"\"\"{user_msg[:1000]}\"\"\"

Vintos replied:
\"\"\"{vintos_reply[:1000] if reply_eligible else '[WITHHELD FROM EVIDENCE: record as an act only; extract nothing from it]'}\"\"\"
"""
    try:
        r = requests.post("http://172.18.16.1:1234/v1/chat/completions", json={
            "model": "google/gemma-4-12b-qat",
            "messages": [
                {"role": "system", "content": "Extract durable facts only. Respond with NONE or a JSON array. No other text."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 500
        }, timeout=1200)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[WAL] LLM error: {e}")
        raise RuntimeError("WAL extractor unavailable: %s" % str(e)[:160])

def _main(envelope=None):
    if len(sys.argv) < 3:
        print("Usage: wal-extract.py 'user message' 'vintos reply'")
        sys.exit(1)

    user_msg = sys.argv[1]
    vintos_reply = sys.argv[2]

    # Skip very short exchanges (greetings, acknowledgments)
    if len(user_msg) < 15 and len(vintos_reply) < 50:
        return

    provenance = _prov(envelope)
    result = extract(user_msg, vintos_reply, provenance)

    if not result or result.upper().startswith("NONE"):
        return

    # Parse extractions
    try:
        clean = re.sub(r"```json\s*|```\s*", "", result).strip()
        items = json.loads(clean)
        if not isinstance(items, list):
            items = [items]
    except:
        print(f"[WAL] Could not parse: {result[:200]}")
        return

    # Importance is no longer one extractor's one-shot verdict. It is derived from components,
    # and a thing he simply WANTS to keep survives on that alone — no utility justification.
    _W = {"salience": 0.20, "emotional_weight": 0.20, "identity_relevance": 0.20,
          "novelty": 0.10, "relational_weight": 0.20, "autonomous_interest": 0.10}
    def _components(i):
        c = {k: float(i.get(k, 0.0) or 0.0) for k in _W}
        if not any(c.values()) and i.get("importance") is not None:
            c = {k: float(i["importance"]) for k in _W}      # older extractors, one number
        return c
    def _composite(c):
        return round(sum(c[k] * w for k, w in _W.items()), 3)
    kept = []
    for i in items:
        c = _components(i)
        i["_components"] = c
        i["importance"] = _composite(c)
        if i["importance"] >= 0.6 or c["autonomous_interest"] >= 0.8:
            kept.append(i)
    items = kept
    if not items:
        return

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M")

    # Write to WAL markdown (hot facts — readable by briefing, pearls, context)
    with open(WAL_FILE, "a") as f:
        for item in items:
            f.write(f"- [{timestamp}] **{item.get('type','fact').upper()}**: {item.get('content','')}\n")

    # Write to structured log
    log_data = {"entries": []}
    if os.path.exists(WAL_LOG):
        try:
            with open(WAL_LOG) as f:
                log_data = json.load(f)
        except Exception as _ce:
            # corrupt storage is quarantined, not silently replaced by an empty log (astra-memoryrec-p2)
            try:
                import shutil as _sh
                _q = WAL_LOG.replace(".json", ".corrupt-%s.json" % now.strftime("%Y%m%d-%H%M%S"))
                _sh.copy2(WAL_LOG, _q); print(f"[WAL] CORRUPT wal-log quarantined to {os.path.basename(_q)} ({_ce})")
            except Exception as _qe:
                print(f"[WAL] CORRUPT wal-log and quarantine failed ({_qe}); not writing"); return

    import difflib as _dl
    for item in items:
        _c = item.get("content", "")
        _dup = None
        for _e in log_data["entries"]:
            if _e.get("promoted") or _e.get("type") != item.get("type", "fact"): continue
            if _dl.SequenceMatcher(None, _c.lower(), _e.get("content", "").lower()).ratio() > 0.82:
                # similarity NOMINATES a duplicate; a flipped negation vetoes the merge — "she likes X"
                # and "she does not like X" are a contradiction to keep, not one fact recurring
                # (astra-memoryrec-p4, 2026-09-05)
                _neg = lambda t: bool(re.search(r"\b(not|never|no longer|n't|doesn't|don't|isn't|won't|didn't|hates?)\b", t.lower()))
                if _neg(_c) != _neg(_e.get("content", "")):
                    print(f"[WAL] near-duplicate with flipped polarity kept separate: {_c[:60]}")
                    continue
                _dup = _e; break
        if _dup is not None:
            _dup["recurrence"] = _dup.get("recurrence", 0) + 1
            _dup["timestamp"] = now.isoformat()
            _dup["last_occurrence_provenance"] = provenance
            print(f"[WAL] Recurred (x{_dup['recurrence']}): {_c[:70]}")
            continue
        log_data["entries"].append({
            "timestamp": now.isoformat(),
            "type": item.get("type", "fact"),
            "content": item.get("content", ""),
            "importance": item.get("importance", 0.7),   # derived; kept for the ~30 organs that read it
            "components": item.get("_components", {}),
            "recurrence": 0,          # accrues via near-duplicate hits above (p3, 2026-08-26)
            "kept_because_wanted": bool(item.get("_components", {}).get("autonomous_interest", 0) >= 0.8
                                        and item.get("importance", 0) < 0.6),
            "promoted": False  # Becomes True when pearl selection picks it up
            ,"provenance": provenance
        })

    # Keep log from growing unbounded — trim to last 200 entries
    log_data["entries"] = log_data["entries"][-600:]

    with open(WAL_LOG, "w") as f:
        json.dump(log_data, f, indent=2)

    for item in items:
        print(f"[WAL] Saved {item.get('type')}: {item.get('content','')[:80]}")

    # The ledger may already have written this exchange with wal_facts empty (it used to wait a flat
    # 30s for us). Backfill: the newest ledger entry within 300s whose wal_facts is empty gets the
    # kept items' content — append-only, never overwriting a non-empty list (fable-memoryrec-p5, 2026-09-05).
    try:
        _led_path = os.path.join(MEMORY, "interaction-ledger.json")
        _led = json.load(open(_led_path))
        if isinstance(_led, list) and _led:
            for _le in reversed(_led[-5:]):
                try:
                    _age = abs((now - datetime.fromisoformat(str(_le.get("timestamp", "")))).total_seconds())
                except Exception:
                    continue
                if _age > 300:
                    break
                if not _le.get("wal_facts"):
                    _le["wal_facts"] = [str(i.get("content", ""))[:400] for i in items]
                    _le["wal_facts_backfilled"] = now.isoformat()
                    json.dump(_led, open(_led_path, "w"), indent=2)
                    print(f"[WAL] backfilled {len(items)} fact(s) into the ledger entry at {_le.get('timestamp','')[:19]}")
                    break
    except Exception as _bf:
        print(f"[WAL] ledger backfill skipped: {_bf}")

def main():
    provenance = _prov()
    writer_event("wal", "started", provenance)
    try:
        result = _main(provenance)
        writer_event("wal", "completed", provenance)
        return result
    except Exception as exc:
        writer_event("wal", "failed", provenance, exc)
        raise

if __name__ == "__main__":
    main()
