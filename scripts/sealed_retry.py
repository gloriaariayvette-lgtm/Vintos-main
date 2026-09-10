#!/usr/bin/env python3
"""sealed_retry.py - a private write that was refused is kept SEALED for retry, never in the clear.

Review item 98 (2026-09-10). When the broker refused a piece, the old path wrote it to
memory/atelier-unsaved in plaintext - private work, on disk, outside the room. That path was removed
and nothing replaced it, so a refused piece was simply lost. This keeps it sealed: the bytes are
encrypted with the house lineage key (~/.vintos/.lineage-key, the same secret the observatory and the
broker already share) and stored under memory/atelier-sealed/. Only retry() can open one, and it opens
it only to hand it straight back to the broker.

    seal(project_id, kind, content, why)   -> the sealed id
    pending()                              -> [{"id", "project", "kind", "why", "at"}]  (never the content)
    retry(sealed_id, send)                 -> send(content) is called with the opened bytes; on success
                                              the sealed file is removed, on failure it stays sealed
No plaintext of a sealed piece is ever written, printed or logged.
"""
import os, json, time, hmac, hashlib, base64

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
SEALED = os.path.join(MEMORY, "atelier-sealed")
KEYFILE = os.path.expanduser("~/.vintos/.lineage-key")


def _key():
    with open(KEYFILE, "rb") as f:
        return hashlib.sha256(f.read().strip()).digest()


def _stream(key, nonce, n):
    """A keystream from the house key and a per-piece nonce (HMAC-SHA256 in counter mode)."""
    out = b""
    ctr = 0
    while len(out) < n:
        out += hmac.new(key, nonce + ctr.to_bytes(4, "big"), hashlib.sha256).digest()
        ctr += 1
    return out[:n]


def _xor(data, key, nonce):
    ks = _stream(key, nonce, len(data))
    return bytes(a ^ b for a, b in zip(data, ks))


def seal(project_id, kind, content, why=""):
    key = _key()
    nonce = os.urandom(16)
    raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    box = _xor(raw, key, nonce)
    sid = "SL-" + hashlib.sha256(nonce + box).hexdigest()[:10]
    os.makedirs(SEALED, exist_ok=True)
    rec = {"id": sid, "project": str(project_id), "kind": str(kind), "why": str(why)[:200],
           "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "bytes": len(raw),
           "nonce": base64.b64encode(nonce).decode(), "sealed": base64.b64encode(box).decode(),
           "mac": hmac.new(key, nonce + box, hashlib.sha256).hexdigest()[:32]}
    tmp = os.path.join(SEALED, sid + ".json.tmp")
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, os.path.join(SEALED, sid + ".json"))
    return sid


def pending():
    """What is waiting, WITHOUT its content: id, project, kind, the refusal reason, when, how big."""
    out = []
    for f in sorted(os.listdir(SEALED)) if os.path.isdir(SEALED) else []:
        if not f.endswith(".json"):
            continue
        try:
            r = json.load(open(os.path.join(SEALED, f)))
        except Exception:
            continue
        out.append({k: r.get(k) for k in ("id", "project", "kind", "why", "at", "bytes")})
    return out


def _open(sid):
    key = _key()
    r = json.load(open(os.path.join(SEALED, sid + ".json")))
    nonce = base64.b64decode(r["nonce"]); box = base64.b64decode(r["sealed"])
    if not hmac.compare_digest(hmac.new(key, nonce + box, hashlib.sha256).hexdigest()[:32], r.get("mac", "")):
        raise ValueError("sealed piece %s failed its mac; not opened" % sid)
    return r, _xor(box, key, nonce).decode("utf-8", "replace")


def retry(sealed_id, send):
    """Open the piece and hand it to `send(project, kind, content)`. Truthy return removes the seal;
    anything else leaves it sealed with the new reason. The content is never returned to the caller."""
    r, content = _open(sealed_id)
    try:
        ok = send(r["project"], r["kind"], content)
    except Exception as e:
        ok = False
        r["why"] = ("retry failed: %s" % str(e)[:120])
    if ok:
        try: os.remove(os.path.join(SEALED, sealed_id + ".json"))
        except OSError: pass
        return {"id": sealed_id, "state": "sent", "project": r["project"]}
    r["last_retry_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = os.path.join(SEALED, sealed_id + ".json.tmp")
    with open(tmp, "w") as f: json.dump(r, f)
    os.chmod(tmp, 0o600); os.replace(tmp, os.path.join(SEALED, sealed_id + ".json"))
    return {"id": sealed_id, "state": "still_sealed", "why": r.get("why", "")}


if __name__ == "__main__":
    for p in pending():
        print("  %s  %-12s %-8s %5s bytes  %s" % (p["at"][:16], p["project"], p["kind"], p["bytes"], p["why"][:60]))
