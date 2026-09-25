#!/usr/bin/env python3
"""grok_subscription.py — his Grok images and video on Gloria's SuperGrok subscription.

She already pays for SuperGrok; per-use Atlas and API-key renders were paying twice (Gloria,
2026-09-25). `grok login` (Grok Build, xAI's own CLI, already on Aegis for the bench) signs in
with her account and stores a session token in ~/.grok/auth.json. That token is accepted by
api.x.ai for image generation (verified on Aegis 2026-09-25: one grok-imagine-image render).

  token()   the stored token, refreshed through its own OIDC issuer when near expiry and
            written back so grok and this module keep one login
  image()   text -> image                       POST /v1/images/generations
  edit()    image(s) + text -> image (<=5 refs) POST /v1/images/edits
  video()   image + text -> mp4                 POST /v1/videos/generations, poll /v1/videos/{id}

Subscription only: when the login is missing or expired, or a weekly cap is reached, this raises
Unavailable and the caller makes nothing. It never falls back to the paid API key or Atlas.

The subscription's weekly pool is shared with her own Grok use, so his use is capped per week
(~/.vintos/grok-subscription.json: {"images_per_week": N, "videos_per_week": M}).

    grok_subscription.py status            login, expiry, and this week's use
    grok_subscription.py probe image|edit|video   one real render, to check a surface
"""
import base64, fcntl, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

AUTH = os.environ.get("VINTOS_GROK_AUTH") or os.path.expanduser("~/.grok/auth.json")
CONFIG = os.environ.get("VINTOS_GROK_SUB_CONFIG") or os.path.expanduser("~/.vintos/grok-subscription.json")
USAGE = os.environ.get("VINTOS_GROK_SUB_USAGE") or os.path.expanduser("~/.vintos/grok-subscription-usage.jsonl")
API = "https://api.x.ai/v1"
DEFAULTS = {"images_per_week": 40, "videos_per_week": 7,
            "image_model": "grok-imagine-image", "video_model": "grok-imagine-video-1.5"}
REFRESH_WITHIN_S = 3600
WEEK_S = 7 * 86400


class Unavailable(RuntimeError):
    """The subscription cannot make this right now; nothing was made and nothing was billed."""


def _open(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout)


def config():
    c = dict(DEFAULTS)
    try:
        c.update({k: v for k, v in json.load(open(CONFIG)).items() if k in DEFAULTS})
    except Exception:
        pass
    return c


# ---- the login ---------------------------------------------------------------------------------

def _epoch(v):
    if v in (None, ""): return None
    if isinstance(v, (int, float)): return float(v) / (1000.0 if v > 1e12 else 1.0)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    except ValueError:
        try: return _epoch(float(v))
        except ValueError: return None


def _entry():
    try:
        data = json.load(open(AUTH))
    except FileNotFoundError:
        raise Unavailable("no Grok login on this machine — run: env -u XAI_API_KEY grok login")
    except ValueError:
        raise Unavailable("the Grok login file is unreadable — run: env -u XAI_API_KEY grok login")
    if not isinstance(data, dict) or not data:
        raise Unavailable("the Grok login is empty — run: env -u XAI_API_KEY grok login")
    name = next(iter(data))
    entry = data[name]
    if not isinstance(entry, dict) or not isinstance(entry.get("key"), str):
        raise Unavailable("the Grok login holds no session key — run: env -u XAI_API_KEY grok login")
    return data, name, entry


def _refresh(data, name, entry, now):
    """Standard OIDC refresh against the issuer grok itself signed in with; the rotated tokens are
    written back into grok's own file so the two never hold different logins."""
    issuer, client, rt = entry.get("oidc_issuer"), entry.get("oidc_client_id"), entry.get("refresh_token")
    if not (issuer and client and rt):
        raise Unavailable("the Grok login cannot refresh itself — run: env -u XAI_API_KEY grok login")
    try:
        disc = json.load(_open(issuer.rstrip("/") + "/.well-known/openid-configuration", 30))
        body = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": rt,
                                       "client_id": client}).encode()
        tok = json.load(_open(urllib.request.Request(disc["token_endpoint"], body,
                              {"Content-Type": "application/x-www-form-urlencoded"}), 30))
    except Exception as e:
        raise Unavailable("the Grok login could not refresh (%s) — run: env -u XAI_API_KEY grok login" % str(e)[:120])
    if not tok.get("access_token"):
        raise Unavailable("the Grok login refresh returned no token — run: env -u XAI_API_KEY grok login")
    entry = dict(entry, key=tok["access_token"])
    if tok.get("refresh_token"): entry["refresh_token"] = tok["refresh_token"]
    if tok.get("expires_in"):
        old = entry.get("expires_at")
        new = now + float(tok["expires_in"])
        entry["expires_at"] = (int(new * 1000) if isinstance(old, (int, float)) and old > 1e12 else
                               int(new) if isinstance(old, (int, float)) else
                               datetime.fromtimestamp(new, timezone.utc).isoformat())
    data = dict(data); data[name] = entry
    tmp = AUTH + ".tmp.%d" % os.getpid()
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: json.dump(data, f)
    os.replace(tmp, AUTH)
    return entry


def token(now=None):
    now = now or time.time()
    os.makedirs(os.path.dirname(AUTH) or ".", exist_ok=True)
    with open(AUTH + ".vintos-lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data, name, entry = _entry()
        exp = _epoch(entry.get("expires_at"))
        if exp is not None and exp - now < REFRESH_WITHIN_S:
            entry = _refresh(data, name, entry, now)
        return entry["key"]


# ---- the weekly cap ----------------------------------------------------------------------------

def used(kind, now=None):
    cut = (now or time.time()) - WEEK_S
    n = 0
    try:
        with open(USAGE) as f:
            for line in f:
                try: r = json.loads(line)
                except ValueError: continue
                if r.get("kind") == kind and r.get("at", 0) >= cut: n += 1
    except OSError:
        pass
    return n


def _check_cap(kind, now=None):
    cap = int(config()["%ss_per_week" % kind])
    if used(kind, now) >= cap:
        raise Unavailable("his weekly %s allowance on the subscription (%d) is used up" % (kind, cap))


def _record(kind, model, now=None):
    os.makedirs(os.path.dirname(USAGE) or ".", exist_ok=True)
    fd = os.open(USAGE, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps({"at": now or time.time(), "kind": kind, "model": model}) + "\n")


# ---- the calls ---------------------------------------------------------------------------------

def _post(path, body, timeout=180):
    req = urllib.request.Request(API + path, json.dumps(body).encode(),
                                 {"Authorization": "Bearer " + token(), "Content-Type": "application/json"})
    try:
        return json.load(_open(req, timeout))
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        if e.code in (401, 403):
            raise Unavailable("the subscription refused this (%d): %s" % (e.code, detail))
        raise RuntimeError("xAI %s %d: %s" % (path, e.code, detail))


def _get(url, timeout=60, auth=True):
    h = {"Authorization": "Bearer " + token()} if auth else {}
    return _open(urllib.request.Request(url, headers=h), timeout).read()


def data_uri(path):
    raw = open(path, "rb").read()
    mime = "image/jpeg" if raw[:3] == b"\xff\xd8\xff" else "image/png"
    return "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode())


def _image_bytes(resp):
    d = (resp.get("data") or [{}])[0]
    if d.get("b64_json"): return base64.b64decode(d["b64_json"]), d.get("revised_prompt")
    if d.get("url"): return _get(d["url"], 120, auth=False), d.get("revised_prompt")
    raise RuntimeError("xAI returned no image: %s" % json.dumps(resp)[:200])


def image(prompt, model=None):
    """text -> (image bytes, revised prompt or None)"""
    _check_cap("image")
    model = model or config()["image_model"]
    out = _image_bytes(_post("/images/generations", {"model": model, "prompt": prompt[:4000], "n": 1,
                                                     "response_format": "b64_json"}))
    _record("image", model)
    return out


def edit(prompt, refs, model=None):
    """reference image path(s), in order, + text -> image bytes. One to five references."""
    refs = [r for r in refs if r][:5]
    if not refs: raise ValueError("edit needs at least one reference image")
    _check_cap("image")
    model = model or config()["image_model"]
    imgs = [{"url": data_uri(p), "type": "image_url"} for p in refs]
    body = {"model": model, "prompt": prompt[:4000], "n": 1, "response_format": "b64_json"}
    body.update({"image": imgs[0]} if len(imgs) == 1 else {"images": imgs})
    data, _ = _image_bytes(_post("/images/edits", body))
    _record("image", model)
    return data


def video(prompt, image_path, duration=6, resolution="720p", model=None, poll_s=10, polls=60, sleep=time.sleep):
    """a still + motion text -> mp4 bytes"""
    _check_cap("video")
    model = model or config()["video_model"]
    resp = _post("/videos/generations", {"model": model, "prompt": prompt[:2000],
                                         "image": {"url": data_uri(image_path)},
                                         "duration": max(1, min(int(duration), 15)), "resolution": resolution})
    _record("video", model)   # submitted: the pool is spent whether or not the poll below finishes
    req_id = resp.get("id") or resp.get("request_id")
    url = resp.get("video_url") or resp.get("url") or (resp.get("video") or {}).get("url")
    for _ in range(polls):
        if url or not req_id: break
        sleep(poll_s)
        d = json.loads(_get("%s/videos/%s" % (API, req_id), 30))
        if str(d.get("status", "")).lower() in ("failed", "error", "expired"):
            raise RuntimeError("xAI video failed: %s" % json.dumps(d)[:300])
        url = d.get("video_url") or d.get("url") or (d.get("video") or {}).get("url")
    if not url: raise RuntimeError("xAI video: no url after polling")
    return _get(url, 300, auth=False)


def status(now=None):
    now = now or time.time()
    c = config()
    try:
        _d, _n, e = _entry()
        exp = _epoch(e.get("expires_at"))
        login = {"signed_in_as": e.get("email") or e.get("user_id"),
                 "expires_in_h": round((exp - now) / 3600, 1) if exp else None,
                 "can_refresh": bool(e.get("refresh_token") and e.get("oidc_issuer"))}
    except Unavailable as u:
        login = {"error": str(u)}
    return {"login": login,
            "images_this_week": "%d of %d" % (used("image", now), c["images_per_week"]),
            "videos_this_week": "%d of %d" % (used("video", now), c["videos_per_week"])}


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "status":
        print(json.dumps(status(), indent=1)); sys.exit(0)
    if a[0] == "probe" and len(a) > 1:
        out = "/tmp/grok-sub-probe"
        try:
            if a[1] == "image":
                data, _ = image("a lighthouse at dusk, photoreal"); open(out + ".jpg", "wb").write(data)
            elif a[1] == "edit":
                if len(a) < 3: sys.exit("probe edit <image path>")
                open(out + "-edit.jpg", "wb").write(edit("the same scene at night, lit by the moon", [a[2]]))
            elif a[1] == "video":
                if len(a) < 3: sys.exit("probe video <image path>")
                open(out + ".mp4", "wb").write(video("slow push in, the light shifting gently", a[2], duration=4))
            else:
                sys.exit("probe image | edit <img> | video <img>")
            print("OK — saved under %s*" % out)
        except Unavailable as u:
            print("UNAVAILABLE:", u); sys.exit(2)
        except Exception as e:
            print("FAILED:", e); sys.exit(1)
        sys.exit(0)
    sys.exit(__doc__)
