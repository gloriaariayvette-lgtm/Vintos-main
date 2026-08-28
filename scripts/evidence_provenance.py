#!/usr/bin/env python3
"""Shared provenance contract for post-response evidence writers.

The counterpart's verbatim input remains eligible.  A generated reply may be
stored as an act, but a stratagem-influenced (or malformed/unknown) reply may
not witness predictions, causality, repair, identity, or want learning.

Missing is intentionally distinct from malformed: old cron and non-coordinated
surfaces keep their pre-envelope behaviour, while a coordinator that attempted
to send corrupt provenance fails closed for witnessing and records the fault.
"""
import json
import os
from datetime import datetime

ENV_KEY = "VINTOS_EVIDENCE_ENVELOPE"
MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
EVENTS = os.path.join(MEMORY, "evidence-writer-events.jsonl")
BROKER = "http://127.0.0.1:8611"

_OUTPUTS = {"ordinary_generation", "stratagem_influenced", "unknown"}
_STATUSES = {"started", "completed", "failed", "HELD", "unknown"}


def _legacy():
    return {"schema": 1, "turn_id": "", "surface": "legacy",
            "input_provenance": "counterpart_verbatim",
            "output_provenance": "ordinary_generation", "may_witness": True,
            "capsule_commitment": {}, "envelope_state": "absent_legacy"}


def _unknown(reason):
    return {"schema": 1, "turn_id": "", "surface": "unknown",
            "input_provenance": "counterpart_verbatim",
            "output_provenance": "unknown", "may_witness": False,
            "capsule_commitment": {}, "envelope_state": "malformed",
            "reason": str(reason)[:160]}


def normalize(envelope=None):
    """Return a conservative, JSON-safe envelope.

    ``None`` reads ENV_KEY.  No variable means a genuine legacy caller;
    present-but-invalid data is unknown and cannot witness.
    """
    if envelope is None:
        raw = os.environ.get(ENV_KEY)
        if raw is None:
            return _legacy()
        try:
            envelope = json.loads(raw)
        except Exception as exc:
            return _unknown("invalid JSON: %s" % exc)
    if not isinstance(envelope, dict):
        return _unknown("envelope is not an object")
    output = envelope.get("output_provenance")
    if output not in _OUTPUTS:
        return _unknown("unknown output provenance")
    turn_id = str(envelope.get("turn_id", ""))[:80]
    surface = str(envelope.get("surface", "unknown"))[:40]
    commitment = envelope.get("capsule_commitment") or {}
    if not isinstance(commitment, dict):
        return _unknown("capsule commitment is not an object")
    may = bool(envelope.get("may_witness")) and output == "ordinary_generation"
    return {"schema": 1, "turn_id": turn_id, "surface": surface,
            "input_provenance": "counterpart_verbatim",
            "output_provenance": output, "may_witness": may,
            "capsule_commitment": {
                "stratagem_project": str(commitment.get("stratagem_project", ""))[:80],
                "capsule_sha256": str(commitment.get("capsule_sha256", ""))[:64],
            } if commitment else {},
            "envelope_state": str(envelope.get("envelope_state", "present"))[:40]}


def output_can_witness(envelope=None, claim_kind=None):
    """Whether generated output can update a claimed model of the world/self."""
    return bool(normalize(envelope).get("may_witness"))


def subprocess_env(envelope):
    env = os.environ.copy()
    env[ENV_KEY] = json.dumps(normalize(envelope), sort_keys=True)
    return env


def writer_event(writer, status, envelope=None, detail=None):
    """Append a local event and, for a capsule turn, notify the broker.

    Broker notification is best-effort, but the local append happens first so
    broker unavailability cannot become a silent success.
    """
    env = normalize(envelope)
    status = status if status in _STATUSES else "unknown"
    event = {"at": datetime.now().isoformat(), "writer": str(writer)[:80],
             "status": status, "turn_id": env.get("turn_id", ""),
             "surface": env.get("surface", ""),
             "output_provenance": env.get("output_provenance"),
             "may_witness": env.get("may_witness", False),
             "detail": str(detail or "")[:300]}
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(EVENTS, "a") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")
    except Exception as exc:
        import sys
        print("[evidence-provenance] local writer event failed: %s" % str(exc)[:160],
              file=sys.stderr)
    c = env.get("capsule_commitment") or {}
    if not (c.get("stratagem_project") and c.get("capsule_sha256") and env.get("turn_id")):
        return event
    try:
        import urllib.request
        body = {"id": c["stratagem_project"], "turn_id": env["turn_id"],
                "capsule_sha256": c["capsule_sha256"], "writer": event["writer"],
                "status": status, "detail": event["detail"]}
        req = urllib.request.Request(BROKER + "/stratagem/writer-event",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2.0):
            pass
    except Exception as exc:
        try:
            with open(EVENTS, "a") as f:
                f.write(json.dumps({**event, "status": "unknown",
                                    "detail": "broker notification failed: %s" % str(exc)[:160]},
                                   sort_keys=True) + "\n")
        except Exception:
            pass
    return event
