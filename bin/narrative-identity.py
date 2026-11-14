#!/usr/bin/env python3
"""
narrative-identity.py — Continuity of self-shape, not story spam.

Stores thin narrative fragments: "I tend to...", "I often...", "I avoid..."
Updates only when repeated pattern observed across days.
Overwrites slowly — does not append endlessly.
Used for: slight tone bias, mirror context, nothing heavy.

Evidence (2026-11-14). A fragment rests only on evidence that is there to point to: each proposal carries a
reference (a causal self-model entry and the evidence mark it had, a pearl candidate id), and the candidate or
fragment keeps those references. The causal feed proposes an entry once per new piece of evidence on it, never
again for the same state, so an unchanged entry re-read every drift cycle cannot count as repetition. A candidate
whose last sighting is older than FRAGMENT_STALE_DAYS starts over: evidence from months ago does not combine with
one fresh sighting to form a fragment, and a stale fragment is reinforced only by a fresh proposal.
"""

import os, json, hashlib
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
NARRATIVE_FILE = os.path.join(MEMORY, "narrative-identity.json")
MAX_FRAGMENTS = 12
MIN_DAYS_TO_OVERWRITE = 3
FRAGMENT_HALF_LIFE_DAYS = 30.0   # a fragment's weight halves each month it is not reinforced
FRAGMENT_STALE_DAYS = 30         # not reinforced for this long: no longer offered as who he is now
# The causal feed's gate. 0.5 is a level the producers reach on evidence, not an untouched default: the behavioural
# intercept writes 0.3 + 0.1 per attempt and promotes at two attempts, the trial extractor 0.3 + 0.1 per dated
# observation and promotes at two dates. The gate was "> 0.5", which shut out exactly that plateau - every promoted
# entry sat at 0.50 and none was ever eligible (2026-11-14).
FEED_MIN_CONFIDENCE = 0.5
FEED_TOP_N = 8
MAX_EVIDENCE_REFS = 10
MAX_FED_RECEIPTS = 400
# The template words the feed wraps every entry in. Matching on them made unrelated short entries look alike.
_TEMPLATE_WORDS = frozenset(("i", "tend", "to", "avoid", "when", "no", "longer", "struggle", "enact:"))

def load_narrative():
    try:
        return json.load(open(NARRATIVE_FILE))
    except:
        return {"fragments": [], "candidate_pool": []}

def save_narrative(data):
    json.dump(data, open(NARRATIVE_FILE, "w"), indent=2)

def _text_overlap(a, b):
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb: return 0.0
    return len(wa & wb) / max(len(wa), len(wb))

def _polarity(text):
    """Which way a fragment points. The template words dropped below include "avoid" and "no longer struggle", so
    without this "I tend to avoid X", "I tend to X" and a pearl's "I no longer struggle to enact: X" all had the
    same content and reinforced one another (review 2026-11-14)."""
    t = " " + " ".join(text.lower().split()) + " "
    if " no longer " in t:
        return "no-longer"
    if " avoid " in t:
        return "avoid"
    return "plain"

def _content_overlap(a, b):
    """_text_overlap on the words that carry content: the shared frame ("I tend to ... when") is left out.
    Fragments that point opposite ways never match."""
    if _polarity(a) != _polarity(b):
        return 0.0
    wa = set(a.lower().split()) - _TEMPLATE_WORDS
    wb = set(b.lower().split()) - _TEMPLATE_WORDS
    if not wa or not wb: return 0.0
    return len(wa & wb) / max(len(wa), len(wb))

def _get_frame_conditions():
    """Read frame-state for pattern bias and stability."""
    try:
        import json as _fj, os as _fos
        _mem = _fos.path.expanduser("~/.vintos/workspace/memory")
        fs = _fj.load(open(_fos.path.join(_mem, "frame-state.json")))
        pattern = fs.get("second_order", {}).get("pattern", "")
        strength = fs.get("third_order", {}).get("strength", 0.5)
        stability = round(1.0 - strength, 3)
        return pattern, stability
    except:
        return "", 0.5

def _add_evidence(rec, evidence, now):
    if not evidence:
        return
    ref = dict(evidence); ref.setdefault("at", now.isoformat())
    refs = rec.setdefault("evidence", [])
    if not any(r.get("ref") == ref.get("ref") for r in refs if ref.get("ref")):
        refs.append(ref)
        del refs[:-MAX_EVIDENCE_REFS]

def propose_fragment(fragment_text, source="pattern", evidence=None, now=None):
    """Propose a narrative fragment. Only promotes if seen repeatedly.
    Frame engine conditions bias promotion threshold and fragment confidence.
    evidence: a reference to what this proposal rests on ({"ref": ..., ...}); it is kept on the candidate and
    travels to the fragment."""
    now = now or datetime.now()
    data = load_narrative()
    pool = data.get("candidate_pool", [])
    fragments = data.get("fragments", [])
    _pattern_bias, _stability = _get_frame_conditions()
    # Self-drift bias — stable direction increases candidate weight
    _drift_dir, _drift_strength = None, 0.0
    try:
        import sys as _sd_sys, os as _sd_os
        _sd_sys.path.insert(0, _sd_os.path.expanduser("~/.vintos/workspace/scripts"))
        from self_drift import get_direction_bias as _sd_bias
        _drift_dir, _drift_strength = _sd_bias()
    except: pass

    # Check if similar fragment already confirmed
    for f in fragments:
        if _content_overlap(f["text"], fragment_text) > 0.55:
            # Reinforce confirmed fragment (a fresh proposal is fresh evidence, so a stale fragment may return here)
            f["reinforced"] = now.isoformat()
            f["count"] = f.get("count", 1) + 1
            _add_evidence(f, evidence, now)
            save_narrative(data)
            return "reinforced"

    # Check candidate pool
    for c in pool:
        if _content_overlap(c["text"], fragment_text) > 0.55:
            if _days_since(c.get("last_seen") or c.get("formed"), now) > FRAGMENT_STALE_DAYS:
                # Old sightings do not count toward a fragment formed now: the candidate starts over.
                c["count"] = 0
                c["formed"] = now.isoformat()
                c["evidence"] = []
            c["count"] = c.get("count", 0) + 1
            c["last_seen"] = now.isoformat()
            _add_evidence(c, evidence, now)
            # Promote if seen enough times across enough days
            days_span = int(_days_since(c["formed"], now))
            # Pattern bias lowers threshold — if current frame pattern matches fragment
            _threshold = 3
            _days_req = 2
            if _pattern_bias and any(w in fragment_text.lower() for w in _pattern_bias.lower().split()[:4]):
                _threshold = 2  # one fewer reinforcement needed
            # Low stability — identity not landing cleanly, require more evidence
            if _stability < 0.35:
                _threshold += 1
            # Drift bias — if fragment aligns with dominant direction, lower threshold
            if _drift_dir and _drift_strength > 0.3 and _drift_dir.lower() in fragment_text.lower():
                _threshold = max(2, _threshold - 1)
            if c["count"] >= _threshold and days_span >= _days_req:
                # Tag with stability so _promote knows how confident to sound
                c["stability"] = _stability
                _promote_to_fragment(c, data, now=now)
                save_narrative(data)
                # Update absence map — if fragment rhymes with an absence, reduce its intensity
                try:
                    import sys as _na_sys, os as _na_os
                    _na_sys.path.insert(0, _na_os.path.expanduser("~/.vintos/workspace/scripts"))
                    from absence_map_cold import get_absence_gravity as _na_gravity, load_cold as _na_load, save_cold as _na_save
                    _na_result = _na_gravity(fragment_text)
                    # "dominant" is the absence's description (a string); "dominant_id" is its id. Until
                    # 2026-10-16 this called .get on the string, the AttributeError was swallowed, and a
                    # promoted fragment never relieved an absence.
                    _na_dom = _na_result.get("dominant")
                    _na_id = _na_result.get("dominant_id") or (_na_dom.get("id") if isinstance(_na_dom, dict) else None)
                    if _na_result.get("pull", 0) > 0.4 and (_na_id or _na_dom):
                        _na_data = _na_load()
                        for _na_abs in _na_data.get("absences", []):
                            if _na_abs.get("reached"):
                                continue
                            if (_na_id and _na_abs.get("id") == _na_id) or \
                               (not _na_id and isinstance(_na_dom, str) and _na_abs.get("description", "")[:80] == _na_dom):
                                _na_abs["intensity"] = max(0.1, _na_abs["intensity"] - 0.05)
                                _na_abs["last_touched"] = now.isoformat()
                                break
                        _na_save(_na_data)
                except: pass
                return "promoted"
            save_narrative(data)
            return "candidate_reinforced"

    # New candidate
    cand = {
        "text": fragment_text[:200],
        "source": source,
        "count": 1,
        "formed": now.isoformat(),
        "last_seen": now.isoformat(),
    }
    _add_evidence(cand, evidence, now)
    pool.append(cand)
    # Trim pool
    pool = pool[-20:]
    data["candidate_pool"] = pool
    save_narrative(data)
    return "candidate_added"

def _promote_to_fragment(candidate, data, now=None):
    """Promote candidate to confirmed narrative fragment."""
    now = now or datetime.now()
    fragments = data.get("fragments", [])

    # Find similar existing fragment to overwrite (slow overwrite)
    for f in fragments:
        if _content_overlap(f["text"], candidate["text"]) > 0.4:
            days_old = int(_days_since(f.get("formed", now.isoformat()), now))
            if days_old >= MIN_DAYS_TO_OVERWRITE:
                f["text"] = candidate["text"]
                f["formed"] = now.isoformat()
                f["reinforced"] = now.isoformat()
                f["count"] = candidate["count"]
                f["source"] = candidate["source"]
                f["evidence"] = list(candidate.get("evidence", []))
                data["candidate_pool"] = [c for c in data.get("candidate_pool", []) if c["text"] != candidate["text"]]
                return

    # New fragment
    fragments.append({
        "text": candidate["text"][:200],
        "source": candidate["source"],
        "count": candidate["count"],
        "formed": now.isoformat(),
        "reinforced": now.isoformat(),
        "evidence": list(candidate.get("evidence", [])),
    })
    # Trim to max
    if len(fragments) > MAX_FRAGMENTS:
        fragments.sort(key=lambda f: fragment_weight(f, now))
        fragments = fragments[-MAX_FRAGMENTS:]
    data["fragments"] = fragments
    data["candidate_pool"] = [c for c in data.get("candidate_pool", []) if c["text"] != candidate["text"]]

def _days_since(iso, now):
    """Days since an ISO time. Stored times are naive local or UTC with a Z; mixing them raised, and the except
    turned every fragment into 365 days old (audit, 18 October). Both are compared in one frame now."""
    try:
        then = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if (then.tzinfo is None) != (now.tzinfo is None):
            then, now = then.astimezone(), now.astimezone()   # a naive time is local
        return max(0.0, (now - then).total_seconds() / 86400.0)
    except Exception:
        return 365.0


def fragment_weight(f, now=None):
    """count, aged by time since last reinforced (2026-10-16). Ranked by raw count, which only grows,
    the oldest most re-fed fragments always won."""
    now = now or datetime.now()
    return f.get("count", 1) * 0.5 ** (_days_since(f.get("reinforced") or f.get("formed"), now) / FRAGMENT_HALF_LIFE_DAYS)


def _current_fragments(data, now=None):
    now = now or datetime.now()
    live = [f for f in data.get("fragments", [])
            if _days_since(f.get("reinforced") or f.get("formed"), now) <= FRAGMENT_STALE_DAYS]
    return sorted(live, key=lambda f: -fragment_weight(f, now))


def get_narrative_context():
    """Return narrative identity for context injection. Thin. Only fragments reinforced within
    FRAGMENT_STALE_DAYS, ranked by aged weight."""
    data = load_narrative()
    fragments = _current_fragments(data)[:4]
    if not fragments:
        return ""
    lines = [f["text"] for f in fragments]
    return "NARRATIVE IDENTITY:\n" + "\n".join(f"- {l}" for l in lines)

def get_tone_bias():
    """Return subtle tone bias from narrative identity."""
    data = load_narrative()
    fragments = _current_fragments(data)
    if not fragments:
        return ""
    # Return the most reinforced current fragment as tone anchor
    top = fragments[0]
    return top["text"][:100]

def _entry_ref(e):
    """A stable name for a causal self-model entry (its type and text), and the mark of the evidence it holds now."""
    key = "%s|%s|%s" % (e.get("type", "positive"), e.get("trigger", ""), e.get("tendency", ""))
    ref = "csm:" + hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:12]
    mark = "%s|%s" % (e.get("evidence_count", 1), e.get("last_seen") or e.get("formed") or "")
    return ref, mark

def feed_from_causal_model(now=None):
    """Pull top causal self-model entries and propose as narrative fragments. Returns what happened, so the caller's
    log says it (it logged "updated" whether or not anything was proposed: audit, 18 October).
    An entry is proposed only when it holds evidence the feed has not proposed before (its evidence count or last
    sighting changed), and only when that evidence is from the last FRAGMENT_STALE_DAYS (2026-11-14)."""
    now = now or datetime.now()
    tally = {"entries": 0, "eligible": 0}
    try:
        import sys as _nm_sys; _nm_sys.path.insert(0, SCRIPTS)
        from causal_self_model import load_model
        data = load_model()
        tally["entries"] = len(data["entries"])
        _metric_terms = ["Valence", "Playfulness", "Groundedness", "Arousal", "Tension",
                         "shifted simultaneously", "spike", "carryover", "image generation",
                         "recurring pattern", "this cluster", "this spike", "this follows"]
        eligible = []
        for e in data["entries"]:
            if float(e.get("confidence", 0) or 0) < FEED_MIN_CONFIDENCE:
                continue
            tendency = e.get("tendency", "")
            trigger = e.get("trigger", "")
            # Skip raw metric/spike descriptions — not identity material
            if any(t in tendency or t in trigger for t in _metric_terms):
                continue
            eligible.append(e)
        tally["eligible"] = len(eligible)
        # Among equals the most recently evidenced first (a stable sort on confidence alone kept the oldest).
        eligible.sort(key=lambda e: (float(e.get("confidence", 0) or 0), str(e.get("last_seen") or e.get("formed") or "")),
                      reverse=True)
        fed = load_narrative().get("fed_evidence", {})
        proposals = []
        for e in eligible:
            ref, mark = _entry_ref(e)
            if fed.get(ref) == mark:
                tally["already_fed"] = tally.get("already_fed", 0) + 1
                continue
            seen = e.get("last_seen") or e.get("formed")
            if not seen or _days_since(seen, now) > FRAGMENT_STALE_DAYS:
                tally["stale"] = tally.get("stale", 0) + 1
                continue
            proposals.append((e, ref, mark))
        for e, ref, mark in proposals[:FEED_TOP_N]:
            tendency = e.get("tendency", "")
            trigger = e.get("trigger", "")
            if e.get("type") == "negative":
                fragment = f"I tend to avoid {tendency[:100]} when {trigger[:80]}"
            elif trigger.strip():
                fragment = f"I tend to {tendency[:100]} when {trigger[:80]}"
            else:
                fragment = f"I tend to {tendency[:100]}"
            result = propose_fragment(fragment, source="causal-self-model", now=now,
                                      evidence={"ref": ref + "@" + mark.split("|")[0], "entry": ref,
                                                "evidence_count": e.get("evidence_count", 1),
                                                "seen": str(e.get("last_seen") or e.get("formed") or "")[:19]})
            tally[result] = tally.get(result, 0) + 1
            nd = load_narrative()
            receipts = nd.setdefault("fed_evidence", {})
            receipts.pop(ref, None); receipts[ref] = mark
            while len(receipts) > MAX_FED_RECEIPTS:
                receipts.pop(next(iter(receipts)))
            save_narrative(nd)
    except Exception as e:
        tally["error"] = "%s: %s" % (type(e).__name__, str(e)[:120])
    return tally

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        data = load_narrative()
        frags = data.get("fragments", [])
        pool = data.get("candidate_pool", [])
        print(f"{len(frags)} confirmed fragments, {len(pool)} candidates:")
        for f in frags:
            print(f"  [{f.get('count',1)}x] {f['text'][:80]}")
        print("Candidates:")
        for c in pool:
            print(f"  [{c.get('count',1)}x] {c['text'][:80]}")
    elif cmd == "feed":
        print("Fed from causal model: %s" % feed_from_causal_model())
