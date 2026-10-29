#!/usr/bin/env python3
"""phone_voip.py - his call rings her iPhone as a real incoming call (CallKit), 27 October.

Gloria chose this over a phone number: when the attention ladder reaches its call step, her iPhone shows "Vintos" on
the system's incoming-call screen, locked or not, app open or closed. Answering drops her into his ordinary in-app
call; declining is "Not now".

The phone app (Capacitor shell dev.vintos.app, its VintosCall plugin) registers a PushKit VoIP token with the house
(POST /api/attention/voip-register, authenticated like every app route). The token is kept privately beside the
Watch's (memory/phone-voip-devices.json, 0600). A ring is one APNs push of type "voip" to topic <bundle>.voip, signed
with the same .p8 key, team and key id as the Watch's pushes (secrets/apns-watch.json, read through watch_apns).

The environment (sandbox or production APNs) is the one the app reports at registration: the app reads it from its
own signed provisioning profile (an Xcode-installed build is "development", so sandbox), as the Watch app reports its
own. A token pushed to the wrong environment is refused by Apple (400 BadDeviceToken); that is recorded, never retried
elsewhere.

iOS ends an app that receives a VoIP push and does not report a call, so the payload is only ever a call: the call's
id, its lane, and how long the phone may ring before it lets the ring go (the ladder rings again on its own cadence).
The other pushes of a ring (Watch, ntfy) are unchanged and remain the backup.

Tests replace TRANSPORT; no suite reaches Apple.

    python3 phone_voip.py                 the registered phone(s), tokens shortened
"""
from __future__ import annotations
import json, os, time
from datetime import datetime, timezone

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
DEVICES = os.path.join(MEMORY, "phone-voip-devices.json")
RECEIPTS = os.path.join(MEMORY, "phone-voip-receipts.jsonl")
BUNDLE = "dev.vintos.app"
RING_SECONDS = 60          # one CallKit ring; the ladder rings again every ring_every_minutes
ENVIRONMENTS = ("development", "production")
TRANSPORT = None           # None: watch_apns's HTTP/2 POST (curl). Tests set their own.


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _atomic(path, value):
    import tempfile
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


def _receipt(row):
    os.makedirs(os.path.dirname(RECEIPTS), exist_ok=True)
    fd = os.open(RECEIPTS, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as out: out.write(json.dumps(row) + "\n")
    os.chmod(RECEIPTS, 0o600)
    return row


def devices():
    try:
        rows = json.load(open(DEVICES))
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def register(payload):
    """{voip_token, environment, bundle?}: (ok, result). The newest registration of a token replaces its older row;
    at most four phones are kept."""
    if not isinstance(payload, dict): return False, "body is not an object"
    token = str(payload.get("voip_token") or "").lower().strip()
    environment = str(payload.get("environment") or "development")
    bundle = str(payload.get("bundle") or BUNDLE).strip()
    if len(token) < 32 or len(token) > 256 or any(c not in "0123456789abcdef" for c in token):
        return False, "invalid VoIP token"
    if environment not in ENVIRONMENTS: return False, "invalid APNs environment"
    if not bundle or len(bundle) > 120 or any(not (c.isalnum() or c in ".-") for c in bundle):
        return False, "invalid bundle id"
    rows = [r for r in devices() if r.get("voip_token") != token]
    rows.append({"voip_token": token, "environment": environment, "bundle": bundle, "device": "iPhone",
                 "registered_at": _now_iso()})
    _atomic(DEVICES, rows[-4:])
    return True, {"registered": True, "device": "iPhone", "environment": environment}


def _forget(tokens):
    keep = [r for r in devices() if r.get("voip_token") not in set(tokens)]
    try: _atomic(DEVICES, keep)
    except OSError: pass


def payload_for(call_id, lane, ring_seconds=RING_SECONDS):
    return {"ladder_call": str(call_id), "lane": str(lane or ""), "caller": "Vintos",
            "ring_seconds": int(ring_seconds)}


def ring(call_id, lane, ring_seconds=RING_SECONDS, config_path=None, transport=None, now=None):
    """One VoIP push per registered phone: her iPhone rings as a call from "Vintos". A receipt is always written."""
    import watch_apns
    at = _now_iso()
    rows = devices()
    if not rows:
        return _receipt({"state": "failed", "why": "no registered phone (the app has not sent its VoIP token)",
                         "call": call_id, "at": at})
    try:
        config = watch_apns._config(config_path)
    except Exception as e:
        return _receipt({"state": "failed", "why": "APNs configuration: %s" % str(e)[:120], "call": call_id, "at": at})
    body = json.dumps(payload_for(call_id, lane, ring_seconds), separators=(",", ":")).encode()
    jwt = watch_apns._jwt(config, now=now)
    t = int(time.time() if now is None else now)
    results, gone = [], []
    for device in rows[-4:]:
        host = "api.push.apple.com" if device.get("environment") == "production" else "api.sandbox.push.apple.com"
        url = "https://%s/3/device/%s" % (host, device["voip_token"])
        headers = {"authorization": "bearer " + jwt, "apns-topic": (device.get("bundle") or BUNDLE) + ".voip",
                   "apns-push-type": "voip", "apns-priority": "10",
                   # a ring that arrives after its own ring is over would be a ghost call
                   "apns-expiration": str(t + int(ring_seconds)), "apns-collapse-id": str(call_id)[:64],
                   "content-type": "application/json"}
        try:
            status, response = (transport or TRANSPORT or watch_apns.TRANSPORT)(url, body, headers, 20)
            text = response.decode(errors="replace")[:200] if isinstance(response, bytes) else str(response)[:200]
            results.append({"status": int(status), "ok": 200 <= int(status) < 300, "response": text,
                            "environment": device.get("environment"), "token": device["voip_token"][-8:]})
            if int(status) == 410: gone.append(device["voip_token"])
        except Exception as exc:
            results.append({"status": 0, "ok": False, "response": "%s: %s" % (type(exc).__name__, str(exc)[:160]),
                            "token": device["voip_token"][-8:]})
    if gone: _forget(gone)
    delivered = [r for r in results if r["ok"]]
    row = {"state": "sent" if delivered else "failed", "call": call_id, "lane": lane, "results": results,
           "delivered_to": len(delivered), "devices": len(results), "at": at}
    if gone: row["forgot_unregistered"] = len(gone)
    if not delivered: row["why"] = "; ".join(r["response"] for r in results)[:200] or "no answer from APNs"
    return _receipt(row)


if __name__ == "__main__":
    print(json.dumps([{"environment": r.get("environment"), "bundle": r.get("bundle"),
                       "token": "…" + str(r.get("voip_token", ""))[-8:], "registered_at": r.get("registered_at")}
                      for r in devices()], indent=2))
