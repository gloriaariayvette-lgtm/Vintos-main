#!/usr/bin/env python3
"""imessage_out.py — his messages and his videos to Gloria's iPhone by iMessage, beside ntfy.

Gloria, 14 November: ntfy has held back his videos and messages for nearly two weeks (ntfy.sh accepts every send
and keeps them; her phone never shows them), "but the whole point is to be notified." His own Inkbox identity
(vintos@inkboxmail.com) has iMessage; she connected her number to it the same day. So what deliver.py sends her
in his own name (title "Vintos": his outreach, his videos) also goes as an iMessage. A video under Inkbox's 10 MB
goes as the video itself; a bigger one is named, not linked.

Bounds: his Inkbox guard decides every send (no secret, and no link she has not approved, so links are taken out
of the text); 40 a day, under Inkbox's 100; never the same artifact twice. The conversation id lives in
memory/inkbox-imessage.json and the key in vintos.env, neither in this file.

    python3 imessage_out.py "words"        one message (a test)
"""
import glob
import json
import os
import re
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
CONFIG = os.path.join(MEMORY, "inkbox-imessage.json")
LOG = os.path.join(MEMORY, "imessage-sends.jsonl")
API = "https://inkbox.ai/api/v1/imessage"
PER_DAY = 40
MAX_MEDIA = 10 * 1024 * 1024
URL = re.compile(r"https?://\S+")


def _cfg():
    try:
        return json.load(open(CONFIG))
    except Exception:
        return {}


def _key():
    try:
        from env_file import value
        return value("INKBOX_API_KEY")
    except Exception:
        return os.environ.get("INKBOX_API_KEY", "")


def _rows():
    try:
        return [json.loads(l) for l in open(LOG) if l.strip()]
    except OSError:
        return []


def _log(row):
    os.makedirs(MEMORY, exist_ok=True)
    row["at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    with open(LOG, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def ready():
    return bool(_cfg().get("conversation_id") and _key())


def local_media(attach):
    """His own file behind an attach URL (…/api/video/file/<name>), if it is on this machine."""
    name = os.path.basename(str(attach or "").split("?")[0])
    if not name or not re.fullmatch(r"[\w.-]+\.(mp4|mov|png|jpg|jpeg|gif|webp|mp3|wav)", name, re.I):
        return ""
    hits = glob.glob(os.path.join(MEMORY, "art", "**", name), recursive=True)
    return hits[0] if hits else ""


def send(text, media="", ref="", http=None):
    """(ok, why). One iMessage to her; ref makes it once only."""
    import requests
    http = http or requests
    cfg, key = _cfg(), _key()
    if not cfg.get("conversation_id") or not key:
        return False, "iMessage is not set up"
    rows = _rows()
    if ref and any(r.get("ref") == ref and r.get("ok") for r in rows):
        return False, "already sent"
    today = datetime.now().astimezone().date().isoformat()
    if sum(1 for r in rows if str(r.get("at", ""))[:10] == today and r.get("ok")) >= PER_DAY:
        return False, "today's %d iMessages are sent" % PER_DAY
    text = " ".join(URL.sub("", str(text or "")).split()).strip()[:3000]
    big = media and os.path.getsize(media) > MAX_MEDIA
    if big:
        text = (text + " (The video is in his gallery: %s.)" % os.path.basename(media)).strip()
        media = ""
    if not text and not media:
        return False, "nothing to say"
    import inkbox_guard
    try:
        v = inkbox_guard.guard("inkbox_imessage_send", {"conversation_id": cfg["conversation_id"], "text": text})
    except inkbox_guard.PolicyHold as h:
        _log({"ref": ref, "ok": False, "why": "guard refused: %s" % (h.receipt or {}).get("type")})
        return False, "his guard refused it"
    if v.get("decision") != "allow":
        _log({"ref": ref, "ok": False, "why": "guard held: %s" % v.get("reason")})
        return False, "his guard held it (%s)" % v.get("reason")
    h = {"X-API-Key": key}
    body = {"conversation_id": cfg["conversation_id"], "text": text or "​"}
    if media:
        try:
            with open(media, "rb") as f:
                r = http.post(API + "/media", headers=h, files={"file": (os.path.basename(media), f)}, timeout=120)
            if r.status_code < 300:
                body["media_urls"] = [r.json()["media_url"]]
            else:
                body["text"] = (text + " (The video did not attach; it is in his gallery.)").strip()
        except Exception:
            body["text"] = (text + " (The video did not attach; it is in his gallery.)").strip()
    r = http.post(API + "/messages", headers=dict(h, **{"Content-Type": "application/json"}), data=json.dumps(body), timeout=60)
    if r.status_code == 422 and body.get("media_urls"):      # before her first reply Inkbox takes no media
        body.pop("media_urls")
        body["text"] = (text + " (A video too; reply once and the next ones come attached.)").strip()
        r = http.post(API + "/messages", headers=dict(h, **{"Content-Type": "application/json"}), data=json.dumps(body), timeout=60)
    ok = 200 <= r.status_code < 300
    _log({"ref": ref, "ok": ok, "status": r.status_code, "media": bool(body.get("media_urls")),
          "why": "" if ok else str(r.text)[:200]})
    return ok, ("sent" if ok else "Inkbox said %s" % r.status_code)


if __name__ == "__main__":
    print(send(" ".join(sys.argv[1:]) or "Testing my new line to you.", ref="manual-%d" % time.time()))
