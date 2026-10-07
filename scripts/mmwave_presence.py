"""Software-only occupancy intake, prepared for a separately commissioned sensor.

This module has no device, network, identity, emotion or dispatch authority. It
returns bounded sensor events; no consumer is connected here. The caller supplies
an independent state file (never home-presence.json or sensor-reactions-state.json).
Timing defaults are proposed software settings, not measured device properties.
"""
import fcntl
import json
import math
import os
from pathlib import Path
import tempfile
import time

FRESH_S = 30
DEBOUNCE_S = 1
EXPIRES_S = 120
PER_HOUR = 2


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def update(previous, payload, now):
    """Pure state transition: exact bool or explicit unknown, no sensor dispatch."""
    state = dict(previous) if isinstance(previous, dict) else {}
    result = {"accepted": False, "reason": "invalid_payload", "event": None}
    if not _number(now) or not isinstance(payload, dict) or set(payload) != {"occupied", "observed_at"}:
        return state, result
    occupied, at = payload["occupied"], payload["observed_at"]
    if (occupied is not None and type(occupied) is not bool) or not _number(at):
        return state, result
    if at > now:
        return state, dict(result, reason="future")
    previous_at = state.get("observed_at")
    if _number(previous_at) and at <= previous_at:
        return state, dict(result, reason="out_of_order")
    expired = not _number(previous_at) or now - previous_at > FRESH_S
    if expired:
        state.update(occupied=None, candidate=None, candidate_since=None)
    state["observed_at"] = at
    if now - at > FRESH_S or occupied is None:
        state.update(occupied=None, candidate=None, candidate_since=None, status="unknown")
        return state, dict(result, accepted=occupied is None and now-at <= FRESH_S,
                           reason="unknown" if occupied is None else "stale")
    baseline = state.get("occupied")
    if type(baseline) is bool and baseline == occupied:
        state.update(status="fresh", candidate=None, candidate_since=None)
        return state, dict(result, accepted=True, reason="unchanged")
    if state.get("candidate") is not occupied or not _number(state.get("candidate_since")):
        state.update(candidate=occupied, candidate_since=at, status="debouncing")
        return state, dict(result, accepted=True, reason="debouncing")
    if at - state["candidate_since"] < DEBOUNCE_S:
        return state, dict(result, accepted=True, reason="debouncing")
    state.update(occupied=occupied, candidate=None, candidate_since=None, status="fresh")
    if type(baseline) is not bool:
        return state, dict(result, accepted=True, reason="baseline")
    recent = [t for t in state.get("reactions", []) if _number(t) and 0 <= now-t < 3600]
    state["reactions"] = recent
    if len(recent) >= PER_HOUR:
        return state, dict(result, accepted=True, reason="rate_limited")
    state["reactions"].append(now)
    event = {"sensor": "mmwave_presence", "occupied": occupied,
             "created": now, "expires_at": now + EXPIRES_S,
             "description": "room occupancy detected" if occupied else "room occupancy not detected"}
    return state, dict(result, accepted=True, reason="changed", event=event)


def intake(payload, *, state_path, now=None):
    """Serialize one independent store and atomically replace it. No live default."""
    path = Path(state_path)
    if path.name in {"home-presence.json", "sensor-reactions-state.json"}:
        raise ValueError("mmwave requires an independent state store")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock_fd, "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            with path.open() as stream:
                previous = json.load(stream)
        except (OSError, ValueError):
            previous = {}
        state, result = update(previous, payload, time.time() if now is None else now)
        if state == previous:
            return result
        fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(state, stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return result
