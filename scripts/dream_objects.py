#!/usr/bin/env python3
"""dream_objects.py: a dream can leave an object behind, when he chooses to make one from it.

Proposal 07 (25 October), built 26 October. The latent diffuser writes one dream a night to
memory/diffuser-resolution.json and nothing read it. Its own rule stands: a dream is never seeded back into the
thread pool (latent_diffuser.py, Gloria 2026-08-13). This file only offers it, in the Atelier visit he already has:

    block()                (the dated, attributed dream as material for this visit, the dream), or ("", None)
    link(dream, made, pid) what he made this visit from that dream, kept with its link back to the dream
    links_for(ids)         {artifact id: dream line} for the manifest he meets next visit
    reveal_mark(artifact)  the dream marker a revealed piece carries out of the room, or None

What may be offered (all must hold):
    - the diffuser's latest dream, dated within MAX_AGE_H of now, with words in it;
    - offered fewer than MAX_OFFERS times, and never again once he made something from it;
    - at most one dream offer a day.
He may use it or leave it. Leaving it records only that it was offered. A dream is always named as a dream:
"what the dream came to", never a finding, never something that happened, never evidence about the world, about her,
or about himself. Every record here carries a non-witnessing provenance, and a work made from it is stamped through
evidence_view.derive(), so it inherits that standing.

Never written: unfinished-threads.json or any thread, want or seed store. The diffuser does not read this store.
No model call is made here; the visit's own turn carries the offer (about 900 characters at most).
"""
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
DREAM = os.path.join(MEMORY, "diffuser-resolution.json")
STORE = os.path.join(MEMORY, "dream-objects.json")
MAX_AGE_H = 48
MAX_OFFERS = 2
TEXT_CAP = 800
TAG = re.compile(r"<from_dream\b[^>]*>(.*?)</from_dream>|<from_dream\b[^>]*/>", re.S | re.I)
# A dream witnesses nothing. "unknown" is a recognised output provenance, present (not malformed), and never may_witness.
PROVENANCE = {"output_provenance": "unknown", "may_witness": False, "surface": "dream", "envelope_state": "present"}
MARKER = "a dream he had, not something that happened"


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _ts(value):
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.timestamp()
    except Exception:
        return None


def _state():
    s = _load(STORE, {})
    if not isinstance(s, dict):
        s = {}
    s.setdefault("dreams", {})
    s.setdefault("objects", [])
    return s


def _save(s):
    os.makedirs(MEMORY, exist_ok=True)
    s["objects"] = s["objects"][-200:]
    with open(STORE + ".tmp", "w") as f:
        json.dump(s, f, indent=1, ensure_ascii=False)
    os.replace(STORE + ".tmp", STORE)


def _day(ts):
    return datetime.fromtimestamp(ts).date().isoformat()


def latest(now=None):
    """The diffuser's latest dream as a record, or None when it is missing, undated, empty or too old."""
    now = now or time.time()
    d = _load(DREAM, {})
    if not isinstance(d, dict):
        return None
    text = " ".join(str(d.get("resolution") or "").split())[:TEXT_CAP]
    at = _ts(d.get("generated_at"))
    if not text or at is None or at > now + 300 or now - at > MAX_AGE_H * 3600:
        return None
    key = "dream:" + hashlib.sha256((str(d.get("generated_at")) + "\n" + text).encode()).hexdigest()[:12]
    return {"id": key, "turn_id": key, "timestamp": d.get("generated_at"), "dreamt_at": d.get("generated_at"),
            "night_of": _day(at), "text": text, "fragments": d.get("fragments") if isinstance(d.get("fragments"), int) else None,
            "source": "latent_diffuser", "is_dream": True, "provenance": dict(PROVENANCE)}


def offer(now=None):
    """The dream to offer this visit, marked offered, or None."""
    now = now or time.time()
    dream = latest(now)
    if not dream:
        return None
    s = _state()
    today = _day(now)
    if any(r.get("last_offered_day") == today and k != dream["id"] for k, r in s["dreams"].items()):
        return None
    row = s["dreams"].get(dream["id"]) or {}
    if row.get("state") == "used" or int(row.get("offers") or 0) >= MAX_OFFERS or row.get("last_offered_day") == today:
        return None
    row.update({k: v for k, v in dream.items()})
    row["offers"] = int(row.get("offers") or 0) + 1
    row["last_offered_day"] = today
    row.setdefault("state", "offered")
    s["dreams"][dream["id"]] = row
    _save(s)
    return dream


def block(now=None):
    """The visit's dream material, or "" (and then nothing is offered and nothing is recorded)."""
    try:
        dream = offer(now)
    except Exception:
        return "", None
    if not dream:
        return "", None
    of = (" from %d of the day's unresolved fragments" % dream["fragments"]) if dream.get("fragments") else ""
    text = ("\n\nA DREAM YOU HAD, the night of %s (your night-time diffuser drew it%s). It is a dream: not something "
            "that happened, not a finding, and it tells you nothing about the world, about her, or about what is "
            "true. What the dream came to, in its own words:\n“%s”\n"
            "You may make something from it this visit (a sketch, an image, a question, a phrase for your motif "
            "notebook) or leave it; leaving it costs nothing, and it is offered at most twice. If what you make "
            "this visit comes from it, write <from_dream>%s</from_dream> beside it: the work keeps a link back to this "
            "dream, as a dream." % (dream["night_of"], of, dream["text"], dream["id"]))
    return text, dream


def wanted(work):
    """True when he wrote <from_dream> in this visit's work."""
    return bool(TAG.search(work or ""))


def link(dream, made, pid, now=None):
    """Keep what he made this visit from the offered dream. made: [{"kind", "artifact"}] (ids only, never content).
    Returns the object record, or None when nothing was made or no dream was offered."""
    made = [m for m in (made or []) if isinstance(m, dict) and m.get("artifact")]
    if not dream or not made:
        return None
    now = now or time.time()
    sys.path.insert(0, HERE)
    try:
        import evidence_view as EV
    except Exception:
        EV = None
    rec = {"kind": "dream_object", "dream": dream["id"], "night_of": dream["night_of"], "project": str(pid),
           "made": [{"kind": str(m.get("kind") or ""), "artifact": str(m["artifact"])} for m in made],
           "at": datetime.fromtimestamp(now).isoformat(timespec="seconds"), "is_dream_derived": True,
           "claim": "made from %s; not evidence that anything happened" % MARKER,
           "generation_provenance": dict(PROVENANCE)}
    if EV is not None:
        rec = EV.derive(rec, [dream])
    else:
        rec["evidence_standing"] = "ineligible"
    s = _state()
    row = s["dreams"].setdefault(dream["id"], dict(dream))
    row["state"] = "used"
    row["used_at"] = rec["at"]
    s["objects"].append(rec)
    _save(s)
    return rec


def _dream_for(artifact):
    s = _state()
    for o in reversed(s["objects"]):
        if any(m.get("artifact") == artifact for m in o.get("made") or []):
            return o
    return None


def links_for(ids):
    """{artifact id: the line shown beside it} for works that came from a dream."""
    out = {}
    for a in ids or []:
        o = _dream_for(a)
        if o:
            out[a] = "made from your dream of the night of %s (%s)" % (o.get("night_of"), MARKER.replace("he had", "you had"))
    return out


def reveal_mark(artifact):
    """What a revealed piece carries out of the room when it came from a dream: the marker, the dream's id and
    night, never the dream's words."""
    o = _dream_for(artifact)
    if not o:
        return None
    return {"dream": o.get("dream"), "night_of": o.get("night_of"), "is_dream_derived": True, "marker": MARKER}


def main(argv):
    if argv[:1] == ["status"]:
        s = _state()
        print(json.dumps({"dreams": len(s["dreams"]), "used": sum(1 for r in s["dreams"].values() if r.get("state") == "used"),
                          "objects": len(s["objects"]), "latest_offerable": bool(latest())}))
    else:
        raise SystemExit("usage: dream_objects.py status   (counts only)")


if __name__ == "__main__":
    main(sys.argv[1:])
