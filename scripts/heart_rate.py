#!/usr/bin/env python3
"""heart_rate.py — Gloria's live pulse, from her R21M ring into his body.

The R21M Bridge app (Sol's) POSTs valid readings to Aegis with this shape:

    {"device":"R21M","heart_rate_bpm":86,"observed_at":"2026-08-29T12:34:56Z",
     "source":"0x060A","peripheral_id":"<CoreBluetooth UUID>"}

This is the Aegis half the README left deliberately uninvented: it receives one
reading, validates it, and atomically replaces a single latest-reading record.
A short freshness window decides whether his context calls it LIVE or omits it —
an old reading must never be presented as her heartbeat right now.
"""
import os, json, time, tempfile
from datetime import datetime, timezone

MEM = os.path.expanduser("~/.vintos/workspace/memory")
LATEST = os.path.join(MEM, "heart-rate.json")
HIST = os.path.join(MEM, "heart-rate-history.jsonl")
SNAPSHOT = os.path.join(MEM, "ring-temporal-snapshot.json")
SNAPSHOT_HIST = os.path.join(MEM, "ring-temporal-snapshots.jsonl")
SLEEP = os.path.join(MEM, "ring-sleep-latest.json")
SLEEP_HIST = os.path.join(MEM, "ring-sleep-history.jsonl")
SNAPSHOT_SECONDS = 1800

# A reading older than this is not "now". The ring streams ~1/1-2s, so 90s is
# generous headroom that still refuses a genuinely stale value.
FRESH_SECONDS = 90
# Between fresh and this, mention it but flag it as possibly stale.
MENTION_SECONDS = 600
# Plausible human range. The app already drops zero/implausible, but the store
# refuses again — nothing downstream should ever have to trust the network.
BPM_MIN, BPM_MAX = 30, 220


def _parse_ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _atomic(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(value, f); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp): os.unlink(tmp)
        except OSError: pass


def _append(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(value) + "\n"); f.flush(); os.fsync(f.fileno())


def _maybe_snapshot(rec, force=False):
    """Keep a temporal receipt roughly every half hour of delivered data.

    This never claims iOS woke on schedule while suspended or disconnected.
    """
    try: old = json.load(open(SNAPSHOT))
    except Exception: old = {}
    if not force and time.time() - float(old.get("received_ts") or 0) < SNAPSHOT_SECONDS:
        return False
    snap = {k: rec.get(k) for k in ("bpm", "observed_at", "observed_ts", "received_at", "received_ts", "source", "device")}
    snap.update({"kind":"ring_periodic_snapshot", "truth_status":"delivered_ring_reading_not_continuous_monitoring"})
    _atomic(SNAPSHOT, snap); _append(SNAPSHOT_HIST, snap)
    return True


def record(payload):
    """Validate one reading and atomically replace the latest record.

    Returns (ok, result_or_reason). Never raises into the request path.
    """
    if not isinstance(payload, dict):
        return False, "body is not an object"
    try:
        bpm = int(round(float(payload.get("heart_rate_bpm"))))
    except (TypeError, ValueError):
        return False, "heart_rate_bpm missing or non-numeric"
    if not (BPM_MIN <= bpm <= BPM_MAX):
        return False, "bpm %s outside plausible range" % bpm

    observed = str(payload.get("observed_at", "")).strip()
    rec = {
        "bpm": bpm,
        "observed_at": observed,
        "observed_ts": _parse_ts(observed) or time.time(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "received_ts": time.time(),
        "source": str(payload.get("source", ""))[:16],
        "device": str(payload.get("device", ""))[:32],
        "peripheral_id": str(payload.get("peripheral_id", ""))[:64],
        "provenance": "r21m_ring",
    }
    try:
        _atomic(LATEST, rec)
    except OSError as e:
        return False, "could not store: %s" % e
    try:                                             # a bounded trail, best-effort
        with open(HIST, "a") as f:
            f.write(json.dumps({"bpm": bpm, "at": rec["received_at"],
                                "source": rec["source"]}) + "\n")
    except OSError:
        pass
    try: _maybe_snapshot(rec)
    except OSError: pass
    try:                                             # review 94: a fresh change may move him, within limits
        import sensor_reactions as _sr
        _sr.observe("heart_rate", bpm, at=rec["observed_ts"])
    except Exception:
        pass
    return True, {"stored": True, "bpm": bpm}


def record_sleep(payload):
    """Store a completed ring sleep estimate; never reinterpret it medically."""
    if not isinstance(payload, dict): return False, "body is not an object"
    stages = payload.get("stages_minutes") or {}
    if not isinstance(stages, dict): return False, "stages_minutes is not an object"
    clean = {}
    try:
        for name in ("awake", "light", "deep", "rem", "nap"):
            value = int(stages.get(name, 0) or 0)
            if value < 0 or value > 1440: return False, "%s minutes outside range" % name
            clean[name] = value
    except (TypeError, ValueError): return False, "sleep minutes are not integers"
    total = int(payload.get("total_sleep_minutes") or (clean["light"] + clean["deep"] + clean["rem"] + clean["nap"]))
    if total < 0 or total > 1440: return False, "total_sleep_minutes outside range"
    ended = str(payload.get("ended_at") or payload.get("observed_at") or "")[:40]
    if not _parse_ts(ended): return False, "ended_at missing or unreadable"
    score = payload.get("score")
    if score is not None:
        try: score = max(0, min(100, int(score)))
        except (TypeError, ValueError): return False, "score is not numeric"
    try: wake_count = max(0, min(200, int(payload.get("wake_count") or 0)))
    except (TypeError, ValueError): return False, "wake_count is not numeric"
    rec = {"kind":"ring_sleep_estimate", "started_at":str(payload.get("started_at") or "")[:40],
           "ended_at":ended, "ended_ts":_parse_ts(ended), "received_at":datetime.now(timezone.utc).isoformat(),
           "received_ts":time.time(), "total_sleep_minutes":total, "stages_minutes":clean,
           "score":score, "wake_count":wake_count,
           "source":str(payload.get("source") or "r21m_sleep_file")[:40], "provenance":"r21m_ring",
           "truth_status":"device_estimate_not_medical_measurement"}
    try:
        previous = json.load(open(SLEEP))
        same = all(previous.get(k) == rec.get(k) for k in
                   ("started_at", "ended_at", "total_sleep_minutes", "stages_minutes", "source"))
        if same:
            return True, {"stored":False, "duplicate":True, "total_sleep_minutes":total, "ended_at":ended}
    except Exception: pass
    try: _atomic(SLEEP, rec); _append(SLEEP_HIST, rec)
    except OSError as e: return False, "could not store: %s" % e
    return True, {"stored":True, "total_sleep_minutes":total, "ended_at":ended}


def latest():
    try:
        with open(LATEST) as f:
            r = json.load(f)
        return r if isinstance(r, dict) else None
    except Exception:
        return None


def status(now=None):
    """(state, bpm, age_seconds). state is 'live' | 'stale' | 'none'."""
    r = latest()
    if not r:
        return "none", None, None
    now = now if now is not None else time.time()
    age = now - float(r.get("received_ts") or 0)
    bpm = r.get("bpm")
    if age <= FRESH_SECONDS:
        return "live", bpm, age
    if age <= MENTION_SECONDS:
        return "stale", bpm, age
    return "none", bpm, age


def context_line(now=None):
    """One line for his prompt, or '' when there is nothing honest to say.

    LIVE inside the freshness window; flagged as possibly-stale a little longer;
    silent beyond that. It is a reading of HER body — stated, never something he
    should reach for or narrate back to her.
    """
    state, bpm, age = status(now)
    if state == "live":
        return ("GLORIA'S HEART RATE right now, live from the ring on her hand: %d bpm. "
                "This is her actual pulse as you speak — real, hers, happening. "
                "Let it inform how you meet her; do not recite it back to her." % bpm)
    if state == "stale":
        mins = int((age or 0) / 60)
        return ("GLORIA'S HEART RATE was %d bpm about %d minute%s ago (the ring has gone "
                "quiet since — treat it as a last glimpse, not her pulse right now)."
                % (bpm, mins, "" if mins == 1 else "s"))
    return ""


def temporal_block(now=None):
    """Bounded ring facts for temporal-context.txt, with explicit staleness."""
    now = time.time() if now is None else now; lines = []
    try:
        snap = json.load(open(SNAPSHOT)); age = max(0, now - float(snap.get("received_ts") or 0))
        if age <= 7200:
            lines.append("Ring periodic update: %s bpm observed %d minutes ago (delivered snapshot, not continuous monitoring)." %
                         (snap.get("bpm"), int(age / 60)))
    except Exception: pass
    try:
        sl = json.load(open(SLEEP)); age = max(0, now - float(sl.get("ended_ts") or 0))
        if age <= 172800:
            st = sl.get("stages_minutes") or {}; detail = ", ".join("%s %dm" % (k, st.get(k, 0)) for k in ("deep","rem","light","awake"))
            score = " score %s," % sl["score"] if sl.get("score") is not None else ""
            mins = int(sl.get("total_sleep_minutes", 0))
            lines.append("Ring sleep estimate:%s total %dh %02dm (%s), ended %d hours ago. Device estimate, not a medical measurement." %
                         (score, mins // 60, mins % 60, detail, int(age / 3600)))
    except Exception: pass
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "line":
        print(context_line() or "(no fresh reading)")
    elif len(sys.argv) > 1 and sys.argv[1] == "temporal":
        print(temporal_block())
    else:
        print(json.dumps(latest() or {}, indent=2))
