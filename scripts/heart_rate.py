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
        os.makedirs(MEM, exist_ok=True)
        tmp = LATEST + ".tmp"
        with open(tmp, "w") as f:
            json.dump(rec, f)
        os.replace(tmp, LATEST)                      # atomic single-record replace
    except OSError as e:
        return False, "could not store: %s" % e
    try:                                             # a bounded trail, best-effort
        with open(HIST, "a") as f:
            f.write(json.dumps({"bpm": bpm, "at": rec["received_at"],
                                "source": rec["source"]}) + "\n")
    except OSError:
        pass
    return True, {"stored": True, "bpm": bpm}


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


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "line":
        print(context_line() or "(no fresh reading)")
    else:
        print(json.dumps(latest() or {}, indent=2))
