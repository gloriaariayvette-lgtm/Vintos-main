#!/usr/bin/env python3
"""physical_contract.py - the one shape for a physical effect and a physical observation.

Review items 77 and 93 (2026-09-10). Device receipts said what the transport accepted; somatic records
said when a reading was sampled; neither shared a shape, so nothing could join "what he asked for" to
"what her body did" without knowing both dialects. This is the shape both use:

    effect(...)      requested -> accepted -> observed, each with its own time, and the permit that
                     authorized it. `observed` is only ever filled from an independent witness
                     (a sensor reading, her word), never from the fact that a send returned 200.
    observation(...) a reading with the time it was SAMPLED (not received), its window, the device
                     that produced it, its calibration state and its source.

Both are dicts; the writers keep their own stores. Nothing here sends or reads a device.
"""
import time

ACCEPT_STATES = ("accepted", "queued", "refused", "unavailable")
OBSERVE_STATES = ("observed", "not_observed", "unobservable", "pending")


def effect(effect_id, target, level, kind="", permit_digest=None, requested_at=None, turn_id=""):
    return {"contract": "physical-effect-1", "effect_id": effect_id, "target": str(target), "level": level,
            "kind": kind or "", "permit_digest": permit_digest, "turn_id": turn_id,
            "requested_at": requested_at or time.time(),
            "accepted": {"state": "queued", "at": None, "by": "", "why": ""},
            "observed": {"state": "pending", "at": None, "by": "", "evidence": ""}}


def accept(rec, state, by="", why=""):
    if state not in ACCEPT_STATES:
        raise ValueError("accept state %r not in %s" % (state, ACCEPT_STATES))
    rec["accepted"] = {"state": state, "at": time.time(), "by": by, "why": str(why)[:160]}
    return rec


def observe(rec, state, by="", evidence=""):
    """Only an independent witness fills this. A transport's own 200 is an acceptance, never an observation."""
    if state not in OBSERVE_STATES:
        raise ValueError("observe state %r not in %s" % (state, OBSERVE_STATES))
    if state == "observed" and not str(evidence).strip():
        raise ValueError("an observation needs its evidence: what witnessed it")
    rec["observed"] = {"state": state, "at": time.time(), "by": by, "evidence": str(evidence)[:240]}
    return rec


def observation(value, device, sampled_at, window_s=None, calibration="unknown", source="", stream=""):
    """A physical reading. sampled_at is when the WORLD produced it; received_at is now."""
    return {"contract": "physical-observation-1", "value": value, "device": str(device),
            "sampled_at": sampled_at, "received_at": time.time(),
            "freshness_s": (round(time.time() - float(sampled_at), 2) if sampled_at else None),
            "window_s": window_s, "calibration": calibration, "source": source or str(device), "stream": stream}


def joined(effects, observations, within_s=30):
    """Effects paired with any observation sampled within `within_s` after the request. A pairing is a
    candidate, never a cause: it says these two are close in time, nothing more."""
    out = []
    for e in effects:
        t = float(e.get("requested_at") or 0)
        near = [o for o in observations if o.get("sampled_at") and 0 <= float(o["sampled_at"]) - t <= within_s]
        out.append({"effect_id": e.get("effect_id"), "target": e.get("target"),
                    "accepted": (e.get("accepted") or {}).get("state"),
                    "observations_within_%ds" % within_s: len(near),
                    "note": "proximity in time only; not evidence of cause"})
    return out
