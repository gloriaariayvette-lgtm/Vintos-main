#!/usr/bin/env python3
"""Read-only projection of work Vintos explicitly revealed from the Atelier.

This module never calls the broker and never opens its sealed store.  Reveal
transport writes a separate house-side export ledger; the app receives only a
small allowlist from that ledger.  Missing means honestly empty.  Malformed is
an error, never silently empty.
"""
import json
import os


class RevealStoreError(RuntimeError):
    pass


FIELDS = ("artifact", "revealed_at", "disclosure", "disclosure_sentence", "content")


def read_reveals(memory, limit=20):
    path = os.path.join(memory, "atelier-reveals.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
    except Exception as e:
        raise RevealStoreError("reveal export ledger is unreadable: %s" % e)
    if not isinstance(rows, list):
        raise RevealStoreError("reveal export ledger is not a list")
    out = []
    for row in rows:
        if not isinstance(row, dict) or row.get("revealed", True) is not True:
            continue
        projected = {key: row.get(key) for key in FIELDS if row.get(key) is not None}
        # The first version of the reveal transport called this field ``at``.
        # Preserve those already-revealed works without exposing any extra data.
        if not projected.get("revealed_at") and row.get("at") is not None:
            projected["revealed_at"] = row.get("at")
        # A transport record without an artifact or content is not a reveal
        # card. Preserve it in the ledger; refuse to manufacture UI content.
        if not projected.get("artifact") and not projected.get("content"):
            continue
        out.append(projected)
    out.sort(key=lambda x: str(x.get("revealed_at", "")), reverse=True)
    return out[:max(1, min(int(limit), 100))]
