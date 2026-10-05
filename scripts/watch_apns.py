#!/usr/bin/env python3
"""Bounded APNs sender for Vintos's own watchOS app.

The .p8 key and identifiers live only in ~/.vintos/secrets/apns-watch.json.
Tests replace TRANSPORT; no suite can reach Apple.
"""
from __future__ import annotations
import base64, json, os, time, urllib.request, uuid
from datetime import datetime, timezone

import watch_presence

SECRETS = os.path.expanduser("~/.vintos/secrets")
CONFIG = os.path.join(SECRETS, "apns-watch.json")
RECEIPTS = os.path.expanduser("~/.vintos/workspace/memory/watch-delivery-receipts.jsonl")


def _b64(value): return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _jwt(config, now=None):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    now = int(time.time() if now is None else now)
    header = _b64(json.dumps({"alg":"ES256", "kid":config["key_id"]}, separators=(",", ":")).encode())
    claims = _b64(json.dumps({"iss":config["team_id"], "iat":now}, separators=(",", ":")).encode())
    key = serialization.load_pem_private_key(open(config["key_file"], "rb").read(), password=None)
    der = key.sign((header + "." + claims).encode(), ec.ECDSA(hashes.SHA256()))
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    r, s = decode_dss_signature(der)
    return header + "." + claims + "." + _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def _http(url, body, headers, timeout=20):
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read(4096)


TRANSPORT = _http


def _config(path=None):
    value = json.load(open(path or CONFIG))
    required = ("team_id", "key_id", "key_file", "topic")
    if any(not value.get(k) for k in required): raise ValueError("APNs configuration incomplete")
    if not os.path.isfile(value["key_file"]): raise ValueError("APNs .p8 key missing")
    return value


def _receipt(row):
    os.makedirs(os.path.dirname(RECEIPTS), exist_ok=True)
    fd = os.open(RECEIPTS, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as out: out.write(json.dumps(row) + "\n")
    os.chmod(RECEIPTS, 0o600)
    return row


def send(title, body, kind="message", media_url="", image_url="", message_id="", config_path=None,
         transport=None, now=None, force=False):
    title, body = str(title)[:120], str(body)[:600]
    if not title or not body: return {"state":"failed", "why":"title and body required"}
    if not force:
        held, why = watch_presence.should_hold()
        if held:
            watch_presence._append(watch_presence.HELD, {"title":title, "body":body, "kind":kind,
                "media_url":media_url, "image_url":image_url, "message_id":message_id,
                "held_at":datetime.now(timezone.utc).isoformat(), "why":why})
            return _receipt({"state":"held", "why":why, "kind":kind, "at":datetime.now(timezone.utc).isoformat()})
    config = _config(config_path)
    try: devices = json.load(open(watch_presence.DEVICES))
    except Exception: devices = []
    if not devices: return _receipt({"state":"failed", "why":"no registered Watch", "kind":kind,
                                     "at":datetime.now(timezone.utc).isoformat()})
    category = {"song":"VINTOS_SONG", "painting":"VINTOS_PAINTING"}.get(kind, "VINTOS_MESSAGE")
    payload = {"aps":{"alert":{"title":title, "body":body}, "sound":"vintos.caf",
                      "category":category, "thread-id":"vintos", "interruption-level":"active"},
               "vintos":{"kind":kind, "message_id":message_id or uuid.uuid4().hex,
                          "media_url":str(media_url)[:1000], "image_url":str(image_url)[:1000]}}
    encoded = json.dumps(payload, separators=(",", ":")).encode()
    if len(encoded) > 4096: return _receipt({"state":"failed", "why":"payload exceeds APNs limit", "kind":kind})
    jwt = _jwt(config, now=now); results = []
    for device in devices[-4:]:
        host = "api.push.apple.com" if device.get("environment") == "production" else "api.sandbox.push.apple.com"
        url = "https://%s/3/device/%s" % (host, device["device_token"])
        headers = {"authorization":"bearer " + jwt, "apns-topic":config["topic"],
                   "apns-push-type":"alert", "apns-priority":"10", "content-type":"application/json"}
        try:
            status, response = (transport or TRANSPORT)(url, encoded, headers, 20)
            results.append({"status":int(status), "ok":200 <= int(status) < 300,
                            "response":response.decode(errors="replace")[:200] if isinstance(response, bytes) else str(response)[:200]})
        except Exception as exc:
            results.append({"status":0, "ok":False, "response":"%s: %s" % (type(exc).__name__, str(exc)[:160])})
    state = "sent" if results and all(r["ok"] for r in results) else "failed"
    return _receipt({"state":state, "kind":kind, "results":results,
                     "at":datetime.now(timezone.utc).isoformat(), "message_id":payload["vintos"]["message_id"]})


def flush_held(transport=None, limit=8):
    """Deliver a bounded set held during sleep; failed rows remain durable for the next wake."""
    try:
        with open(watch_presence.HELD) as source:
            rows = [json.loads(line) for line in source if line.strip()]
    except (OSError, ValueError):
        return {"state":"empty", "sent":0, "remaining":0}
    sent_count, remaining = 0, []
    for index, row in enumerate(rows):
        if index >= max(1, min(int(limit), 8)):
            remaining.append(row); continue
        result = send(row.get("title"), row.get("body"), row.get("kind", "message"),
                      row.get("media_url", ""), row.get("image_url", ""), row.get("message_id", ""),
                      transport=transport, force=True)
        if result.get("state") == "sent": sent_count += 1
        else: remaining.append(row)
    os.makedirs(os.path.dirname(watch_presence.HELD), exist_ok=True)
    fd, tmp = __import__("tempfile").mkstemp(prefix="watch-held.", dir=os.path.dirname(watch_presence.HELD))
    try:
        with os.fdopen(fd, "w") as out:
            for row in remaining: out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush(); os.fsync(out.fileno())
        os.chmod(tmp, 0o600); os.replace(tmp, watch_presence.HELD)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return {"state":"flushed", "sent":sent_count, "remaining":len(remaining)}


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument("kind"); parser.add_argument("title"); parser.add_argument("body")
    parser.add_argument("--media-url", default=""); parser.add_argument("--image-url", default="")
    args=parser.parse_args(); print(json.dumps(send(args.title,args.body,args.kind,args.media_url,args.image_url), indent=2))
