#!/usr/bin/env python3
"""deliver.py — the one authorized delivery path for shelf artifacts (review 307).

    from deliver import deliver
    receipt = deliver(artifact_id, "ntfy", message=..., title=..., click=..., attach=...,
                      authority=lambda: (ok, why))

  * authority: the caller's OWN existing check (his decision, the reveal act, the effect
    permit) as a callable returning (bool, why) — deliver refuses without it or when it
    says no. Nothing here invents consent.
  * bounded retry: RETRIES attempts with a short backoff; an exception or a >= 400 status
    is one failed attempt.
  * receipts: memory/delivery-receipts.json keyed "<artifact_id>@<channel>". A repeat call
    for a receipt already 'sent' or 'acknowledged' does NOT resend (idempotent); a 'failed'
    receipt may be retried by a later call.
  * a failed delivery is a receipt with state failed. It erases nothing — the artifact file
    and its record are the caller's, and this never touches them (288).
  * nothing in a send marks reception: 'acknowledged' comes only from acknowledge(), which
    needs evidence that is not the send.
"""
import os, json, time
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
RECEIPTS = os.path.join(MEMORY, "delivery-receipts.json")
CHANNELS = {"ntfy": os.environ.get("VINTOS_NTFY", "https://ntfy.sh/vintos-gloria-9kx")}
RETRIES = 3
BACKOFF_S = 2.0
TIMEOUT_S = 15

def _post_http(url, data, headers, timeout):
    import requests
    r = requests.post(url, data=data, headers=headers, timeout=timeout)
    return r.status_code

POST = _post_http          # tests replace this
SLEEP = time.sleep         # and this

def _receipts_path():
    return RECEIPTS

def load_receipts(path=None):
    try:
        d = json.load(open(path or _receipts_path()))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def _save(d, path=None):
    p = path or _receipts_path()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = p + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, p)

def receipt_key(artifact_id, channel):
    return "%s@%s" % (artifact_id, channel)

def receipt_for(artifact_id, channel):
    return load_receipts().get(receipt_key(artifact_id, channel))

def _now():
    return datetime.now().isoformat()

def deliver(artifact_id, channel, message, title="Vintos", click=None, attach=None, tags=None,
            authority=None, retries=None, priority=None):
    """Send one notification for one artifact over one channel. Returns the receipt dict:
    {state, attempts, at, why, channel, artifact_id, resent}."""
    if not artifact_id:
        raise ValueError("artifact_id required")
    if channel not in CHANNELS:
        return _record(artifact_id, channel, "failed", 0, "unknown channel %r" % (channel,))
    from effect_authority import dispatch
    ok, mode, why = dispatch("outward", authority=authority)
    if not ok:
        return _record(artifact_id, channel, "failed", 0, "refused: %s" % (why or "authority said no"))
    # idempotency: an artifact already sent on this channel is not sent again
    prev = receipt_for(artifact_id, channel)
    if prev and prev.get("state") in ("sent", "acknowledged"):
        out = dict(prev); out["resent"] = False; out["repeat"] = True
        return out
    headers = {"Title": title or "Vintos"}
    if tags: headers["Tags"] = tags
    if click: headers["Click"] = click
    if attach: headers["Attach"] = attach
    if priority: headers["Priority"] = priority
    data = (message or "I made you something.").encode("utf-8")
    n = int(retries if retries is not None else RETRIES)
    attempts = 0; last = ""
    _record(artifact_id, channel, "queued", 0, "")
    while attempts < n:
        attempts += 1
        try:
            code = POST(CHANNELS[channel], data, headers, TIMEOUT_S)
            if code is None or int(code) < 400:
                return _record(artifact_id, channel, "sent", attempts, "http %s" % code)
            last = "http %s" % code
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, str(e)[:120])
        if attempts < n:
            SLEEP(BACKOFF_S * attempts)
    return _record(artifact_id, channel, "failed", attempts, last or "no attempt succeeded")

def acknowledge(artifact_id, channel, evidence):
    """Reception, from evidence that is not the send (her reply, an open, a read receipt)."""
    if not evidence:
        raise ValueError("acknowledge needs evidence")
    prev = receipt_for(artifact_id, channel) or {}
    return _record(artifact_id, channel, "acknowledged", prev.get("attempts", 0),
                   "evidence: %s" % str(evidence)[:160])

def _record(artifact_id, channel, state, attempts, why):
    d = load_receipts()
    k = receipt_key(artifact_id, channel)
    prev = d.get(k) or {}
    rec = {"artifact_id": artifact_id, "channel": channel, "state": state,
           "attempts": attempts, "at": _now(), "why": why, "resent": False,
           "first_at": prev.get("first_at") or _now()}
    d[k] = rec
    try:
        _save(d)
    except Exception:
        pass
    return dict(rec)
