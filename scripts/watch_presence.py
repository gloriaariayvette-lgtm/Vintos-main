#!/usr/bin/env python3
"""Private Apple Watch presence, replies and APNs delivery state.

This is deliberately separate from heart_rate.py: the R21M ring remains its own
source and no downstream reader can accidentally blend the two devices.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import time
from datetime import datetime, timezone

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
SECRETS = os.path.expanduser("~/.vintos/secrets")
LATEST = os.path.join(MEMORY, "watch-presence.json")
HISTORY = os.path.join(MEMORY, "watch-presence-history.jsonl")
REPLIES = os.path.join(MEMORY, "watch-replies.jsonl")
DEVICES = os.path.join(MEMORY, "watch-apns-devices.json")
HELD = os.path.join(MEMORY, "watch-held-notifications.jsonl")
TOKEN_FILE = os.path.join(SECRETS, "watch-bearer")

ALLOWED_KINDS = {
    "heart_rate", "resting_heart_rate", "hrv_sdnn", "sleep", "respiratory_rate",
    "wrist_temperature", "oxygen_saturation", "time_in_daylight", "activity",
    "workout", "noise_exposure", "state_of_mind", "motion", "battery", "wearing",
}
NUMERIC_BOUNDS = {
    "heart_rate": (30.0, 220.0), "resting_heart_rate": (30.0, 220.0),
    "hrv_sdnn": (0.0, 1000.0), "respiratory_rate": (2.0, 80.0),
    "wrist_temperature": (20.0, 45.0), "oxygen_saturation": (0.0, 1.0),
    "noise_exposure": (0.0, 160.0), "time_in_daylight": (0.0, 86400.0),
}


def _parse_ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _atomic(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(value, out, ensure_ascii=False, indent=2)
            out.flush(); os.fsync(out.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def _append(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as out:
        out.write(json.dumps(value, ensure_ascii=False) + "\n")
        out.flush(); os.fsync(out.fileno())
    os.chmod(path, 0o600)


def authorized(header, token_file=None):
    path = token_file or TOKEN_FILE
    try: expected = open(path).read().strip()
    except Exception: return False
    supplied = str(header or "").removeprefix("Bearer ").strip()
    return bool(expected) and hmac.compare_digest(supplied, expected)


def _clean_sample(sample, now):
    if not isinstance(sample, dict): raise ValueError("sample is not an object")
    kind = str(sample.get("kind") or "").strip()
    if kind not in ALLOWED_KINDS: raise ValueError("unsupported watch sample kind")
    observed = str(sample.get("observed_at") or "")[:48]
    observed_ts = _parse_ts(observed)
    if observed_ts is None: raise ValueError("observed_at missing or unreadable")
    if observed_ts > now + 300 or observed_ts < now - 172800:
        raise ValueError("observed_at outside accepted freshness window")
    value = sample.get("value")
    if kind in NUMERIC_BOUNDS:
        try: value = float(value)
        except (TypeError, ValueError): raise ValueError("numeric value required")
        low, high = NUMERIC_BOUNDS[kind]
        if not low <= value <= high: raise ValueError("value outside plausible range")
    elif kind == "motion":
        value = str(value or "")
        if value not in ("stationary", "walking", "running", "automotive", "cycling", "unknown"):
            raise ValueError("unsupported motion state")
    elif kind == "battery":
        if not isinstance(value, dict): raise ValueError("battery value is not an object")
        try: level = float(value.get("level"))
        except (TypeError, ValueError): raise ValueError("battery level required")
        if not 0 <= level <= 1: raise ValueError("battery level outside range")
        value = {"level": level, "state": str(value.get("state") or "unknown")[:24]}
    else:
        if isinstance(value, (dict, list)): value = value
        else: value = str(value or "")[:500]
    return {"kind": kind, "value": value, "unit": str(sample.get("unit") or "")[:24],
            "device": "AppleWatch", "observed_at": observed, "observed_ts": observed_ts,
            "age_seconds": round(max(0.0, now - observed_ts), 1),
            "estimate": "device estimate, not a medical fact"}


def record(payload, now=None):
    if not isinstance(payload, dict): return False, "body is not an object"
    now = float(time.time() if now is None else now)
    raw = payload.get("samples")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 64:
        return False, "samples must contain 1 to 64 rows"
    try: samples = [_clean_sample(row, now) for row in raw]
    except ValueError as exc: return False, str(exc)
    latest = {}
    try:
        old = json.load(open(LATEST)); latest = old.get("latest", {}) if isinstance(old, dict) else {}
    except Exception: pass
    for row in samples:
        previous = latest.get(row["kind"])
        if not previous or row["observed_ts"] >= float(previous.get("observed_ts") or 0):
            latest[row["kind"]] = row
        _append(HISTORY, row)
    battery = latest.get("battery") or {}
    motion = latest.get("motion") or {}
    charging = isinstance(battery.get("value"), dict) and battery["value"].get("state") == "charging"
    recent_signal = max((float(x.get("observed_ts") or 0) for k, x in latest.items()
                         if k not in ("battery", "wearing")), default=0)
    wearing = "no" if charging else ("probably" if now - recent_signal <= 900 else "unknown")
    asleep = bool(payload.get("asleep"))
    snapshot = {"device": "AppleWatch", "received_at": datetime.now(timezone.utc).isoformat(),
                "received_ts": now, "latest": latest, "wearing": wearing, "asleep": asleep,
                "motion": (motion.get("value") or "unknown"),
                "estimate": "Watch readings and wearing state are device estimates, not medical facts"}
    try: _atomic(LATEST, snapshot)
    except OSError as exc: return False, "could not store: %s" % exc
    return True, {"stored": len(samples), "device": "AppleWatch", "wearing": wearing, "asleep": asleep}


def register_apns(payload):
    if not isinstance(payload, dict): return False, "body is not an object"
    token = str(payload.get("device_token") or "").lower().strip()
    environment = str(payload.get("environment") or "development")
    if len(token) < 32 or len(token) > 256 or any(c not in "0123456789abcdef" for c in token):
        return False, "invalid APNs device token"
    if environment not in ("development", "production"): return False, "invalid APNs environment"
    try: rows = json.load(open(DEVICES))
    except Exception: rows = []
    rows = [r for r in rows if r.get("device_token") != token]
    rows.append({"device_token": token, "environment": environment, "device": "AppleWatch",
                 "registered_at": datetime.now(timezone.utc).isoformat()})
    _atomic(DEVICES, rows[-8:])
    return True, {"registered": True, "device": "AppleWatch"}


def record_reply(payload):
    if not isinstance(payload, dict): return False, "body is not an object"
    kind = str(payload.get("kind") or "").strip()
    if kind not in ("dictation", "scribble", "heart", "heartbeat", "action"):
        return False, "unsupported reply kind"
    text = str(payload.get("text") or "").strip()[:1000]
    if kind in ("dictation", "scribble") and not text: return False, "reply text required"
    row = {"id": hashlib.sha256(os.urandom(24)).hexdigest()[:16], "device": "AppleWatch",
           "kind": kind, "text": text, "message_id": str(payload.get("message_id") or "")[:80],
           "observed_at": str(payload.get("observed_at") or datetime.now(timezone.utc).isoformat())[:48],
           "received_at": datetime.now(timezone.utc).isoformat(), "consumed": False}
    _append(REPLIES, row)
    return True, {"stored": True, "id": row["id"]}


def latest():
    try:
        value = json.load(open(LATEST)); return value if isinstance(value, dict) else {}
    except Exception: return {}


def should_hold():
    state = latest()
    # A lost Watch must not leave her messages held indefinitely. Sleep is usable only
    # while the Watch has refreshed the snapshot within the last two hours.
    fresh = time.time() - float(state.get("received_ts") or 0) <= 7200
    asleep = bool(state.get("asleep")) and fresh
    return asleep, ("Gloria is asleep" if asleep else "")
