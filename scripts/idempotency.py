#!/usr/bin/env python3
"""idempotency.py - the same request, acknowledged twice, executes once.

Review item 80 (2026-09-10). The organs that already had this (GCS presses by event id, pulses by id,
wants API events by step id, deliver by receipt) each keep it. This is the one door for the rest:
once(key, ttl_s) is True the first time a key is seen inside its window and False after, recorded in
memory/idempotency.jsonl so a refusal is visible.

    once("encounter:" + text_digest, ttl_s=3600) -> True (proceed) | False (already done in window)
"""
import os, json, time, hashlib, fcntl

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
STORE = os.path.join(MEMORY, "idempotency.json")
LOG = os.path.join(MEMORY, "idempotency.jsonl")


def key_of(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8", "replace")).hexdigest()[:16]


def once(key, ttl_s=3600, now=None):
    now = now if now is not None else time.time()
    os.makedirs(MEMORY, exist_ok=True)
    with open(STORE + ".lock", "a+") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            d = json.load(open(STORE))
        except Exception:
            d = {}
        d = {k: v for k, v in d.items() if now - float(v.get("at", 0)) < float(v.get("ttl", ttl_s))}
        seen = d.get(key)
        if seen:
            try:
                with open(LOG, "a") as f:
                    f.write(json.dumps({"at": now, "key": key, "refused": True, "first_at": seen.get("at")}) + "\n")
            except OSError:
                pass
            tmp = STORE + ".tmp"; json.dump(d, open(tmp, "w")); os.replace(tmp, STORE)
            return False
        d[key] = {"at": now, "ttl": ttl_s}
        tmp = STORE + ".tmp"; json.dump(d, open(tmp, "w")); os.replace(tmp, STORE)
    return True
