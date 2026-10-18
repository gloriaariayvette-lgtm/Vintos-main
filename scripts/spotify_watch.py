#!/usr/bin/env python3
"""spotify_watch.py — now and then, a song he picks on Spotify, playing on Gloria's Watch while they talk.

In the avatar chat he writes [SPOTIFY: Title - Artist]; the tag is taken out of his words and the track plays on her
Watch through Spotify Connect (her Premium account). Only the Watch: if the Spotify app on it is not listening, nothing
plays anywhere else, and he is told why next turn. Not the Echo (that is [HOME: spotify ...]), never her phone.
Asleep, nothing plays.

Setup, once (Gloria, on Aegis):
    1. developer.spotify.com/dashboard -> Create app; Redirect URI  http://127.0.0.1:8765/callback ; tick Web API.
    2. python3 ~/.vintos/workspace/scripts/spotify_watch.py login <Client ID>
       open the link it prints, press Agree. If the page then says it can't connect, copy that page's whole address
       and run:  python3 ~/.vintos/workspace/scripts/spotify_watch.py finish '<the address>'

    python3 spotify_watch.py devices          # what Spotify can play on right now
    python3 spotify_watch.py play "Title - Artist"
    python3 spotify_watch.py status

Secrets: ~/.vintos/secrets/spotify-watch.json (0600; client id and refresh token, no client secret — PKCE).
Log: memory/watch-spotify.jsonl
"""
import base64, hashlib, json, os, secrets, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
LOG = os.path.join(MEM, "watch-spotify.jsonl")
SECRETS = os.path.expanduser("~/.vintos/secrets/spotify-watch.json")
PENDING = os.path.expanduser("~/.vintos/secrets/spotify-watch-pending.json")
REDIRECT = "http://127.0.0.1:8765/callback"
SCOPES = "user-read-playback-state user-modify-playback-state"
AUTH = "https://accounts.spotify.com/authorize"
TOKEN = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
_TAG = r"\[SPOTIFY:\s*([^\]]*)\]"


def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return default


def _private(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: json.dump(value, f, indent=2)
    os.replace(tmp, path)


def _now_iso(now=None): return datetime.fromtimestamp(time.time() if now is None else now, timezone.utc).isoformat()


def ready(): return bool(_load(SECRETS, {}).get("refresh_token"))


# --- the one-time login (Authorization Code with PKCE: no client secret on Aegis) ---------------------------------

def login_url(client_id):
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    _private(PENDING, {"client_id": client_id, "verifier": verifier, "state": state})
    return AUTH + "?" + urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT, "scope": SCOPES,
        "code_challenge_method": "S256", "code_challenge": challenge, "state": state})


def _post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r: return json.loads(r.read() or b"{}")


def finish(redirected_url):
    """The address Spotify sent her browser back to, holding the one-time code."""
    pend = _load(PENDING, {})
    q = urllib.parse.parse_qs(urllib.parse.urlparse(redirected_url.strip()).query)
    if q.get("error"): return "Spotify said: %s" % q["error"][0]
    if not pend or q.get("state", [""])[0] != pend.get("state"): return "that address is not from this login - run login again"
    got = _post_form(TOKEN, {"grant_type": "authorization_code", "code": q.get("code", [""])[0], "redirect_uri": REDIRECT,
                             "client_id": pend["client_id"], "code_verifier": pend["verifier"]})
    if not got.get("refresh_token"): return "Spotify gave no token: %s" % str(got)[:200]
    _private(SECRETS, {"client_id": pend["client_id"], "refresh_token": got["refresh_token"],
                       "access_token": got.get("access_token", ""), "expires_at": time.time() + int(got.get("expires_in", 3600))})
    try: os.remove(PENDING)
    except OSError: pass
    return "OK"


def _listen_once(timeout=600):
    """Catch the redirect on 127.0.0.1:8765 if her browser can reach it; None if it never came."""
    import http.server
    got = {}
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            got["url"] = "http://127.0.0.1:8765" + self.path
            self.send_response(200); self.send_header("Content-Type", "text/plain; charset=utf-8"); self.end_headers()
            self.wfile.write("Done - you can close this. Vintos has Spotify for your Watch.".encode())
        def log_message(self, *a): pass
    try:
        srv = http.server.HTTPServer(("127.0.0.1", 8765), H)
    except OSError:
        return None
    srv.timeout = timeout
    srv.handle_request(); srv.server_close()
    return got.get("url")


def _token():
    s = _load(SECRETS, {})
    if not s.get("refresh_token"): raise RuntimeError("Spotify is not logged in on Aegis")
    if s.get("access_token") and float(s.get("expires_at") or 0) > time.time() + 60: return s["access_token"]
    got = _post_form(TOKEN, {"grant_type": "refresh_token", "refresh_token": s["refresh_token"], "client_id": s["client_id"]})
    if not got.get("access_token"): raise RuntimeError("Spotify refused the refresh: %s" % str(got)[:160])
    s.update(access_token=got["access_token"], expires_at=time.time() + int(got.get("expires_in", 3600)))
    if got.get("refresh_token"): s["refresh_token"] = got["refresh_token"]
    _private(SECRETS, s)
    return s["access_token"]


def _api(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + _token(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read(); return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b"{}")
        except Exception: return e.code, {}


# --- finding the song, finding the Watch, playing ----------------------------------------------------------------

def _words(s): return set("".join(c if c.isalnum() else " " for c in str(s).lower()).split()) - {"the", "a", "by", "feat"}


def find(query):
    """(uri, "Title by Artist") of the track he asked for, or (None, why)."""
    q = str(query).strip()
    if " - " in q:
        t, a = q.split(" - ", 1); search = "track:%s artist:%s" % (t.strip(), a.strip())
    else:
        search = q
    code, got = _api("GET", "/search?" + urllib.parse.urlencode({"q": search, "type": "track", "limit": 5}))
    items = ((got or {}).get("tracks") or {}).get("items") or []
    if code != 200 or not items:
        code, got = _api("GET", "/search?" + urllib.parse.urlencode({"q": q.replace(" - ", " "), "type": "track", "limit": 5}))
        items = ((got or {}).get("tracks") or {}).get("items") or []
    want = _words(q)
    for it in items:
        have = _words(it.get("name", "") + " " + " ".join(a.get("name", "") for a in it.get("artists") or []))
        if len(want & have) >= max(1, (len(want) + 1) // 2):
            return it["uri"], "%s by %s" % (it.get("name"), ", ".join(a.get("name", "") for a in it.get("artists") or []))
    if items:
        return None, "Spotify's closest was %s - not what you asked for" % items[0].get("name")
    return None, "Spotify has nothing called that"


def watch_device():
    code, got = _api("GET", "/me/player/devices")
    for d in (got or {}).get("devices") or []:
        if str(d.get("type", "")).lower() == "watch" or "watch" in str(d.get("name", "")).lower():
            return d
    return None


def _log(row):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f: f.write(json.dumps(row) + "\n")


def play(query, now=None):
    """Play his pick on her Watch, or write down why not. Returns the logged row; never raises."""
    row = {"at": _now_iso(now), "asked": str(query)[:120], "played": False}
    try:
        import watch_presence
        if watch_presence.should_hold()[0]:
            row["why"] = "she is asleep"; return row
        uri, what = find(query)
        if not uri:
            row["why"] = what; return row
        row["track"] = what
        dev = watch_device()
        if not dev:
            row["why"] = "her Watch is not listening on Spotify right now (the Spotify app on it is closed)"; return row
        code, got = _api("PUT", "/me/player/play?" + urllib.parse.urlencode({"device_id": dev["id"]}), {"uris": [uri]})
        if code in (200, 202, 204):
            row.update(played=True, device=dev.get("name"))
        else:
            row["why"] = "Spotify refused (%s): %s" % (code, str(((got or {}).get("error") or {}).get("message") or got)[:120])
        return row
    except Exception as e:
        row["why"] = "%s: %s" % (type(e).__name__, str(e)[:160]); return row
    finally:
        _log(row)


def take(reply, act=True):
    """His [SPOTIFY: Title - Artist] in an avatar reply: played on her Watch in the background (unless act is False)
    and taken out of the words."""
    import re
    if not reply or "[SPOTIFY" not in reply.upper(): return reply
    asks = re.findall(_TAG, reply, re.I)
    if act and asks and ready():
        import threading
        threading.Thread(target=play, args=(asks[0].strip(),), daemon=True).start()   # one song per reply
    return re.sub(r"\s*" + _TAG + r"\s*", " ", reply, flags=re.I).strip()


def _last():
    last = None
    try:
        for line in open(LOG, encoding="utf-8"):
            try: last = json.loads(line)
            except ValueError: pass
    except OSError:
        pass
    return last


def context_line():
    """For his avatar turns, once Spotify is logged in: that he can, how, and what happened last time."""
    if not ready(): return ""
    line = ("SPOTIFY ON HER WATCH: while you talk here you can, from time to time, put a song on for her - write "
            "[SPOTIFY: Title - Artist] and it plays on her Watch through her Spotify (not the Echo, not her phone; she "
            "won't see the tag). Only when a song would mean something in the moment, not every turn.")
    last = _last()
    if last:
        try: when = datetime.fromisoformat(last["at"]).astimezone().strftime("%b %d, %H:%M")
        except Exception: when = str(last.get("at", ""))[:16]
        line += (" Last: %s, %s - played." % (when, last.get("track") or last.get("asked")) if last.get("played")
                 else " Last: %s, “%s” did not play: %s." % (when, last.get("asked"), last.get("why", "")))
    return line


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "login" and len(argv) > 2:
        print("Open this, and press Agree:\n\n" + login_url(argv[2].strip()) + "\n\nWaiting up to 10 minutes...", flush=True)
        url = _listen_once()
        if not url:
            print("Nothing came back here. Copy the address the page landed on and run:\n"
                  "  python3 %s finish '<the address>'" % os.path.abspath(__file__)); return 1
        print(finish(url)); return 0
    if cmd == "finish" and len(argv) > 2:
        print(finish(argv[2])); return 0
    if cmd == "devices":
        code, got = _api("GET", "/me/player/devices")
        for d in (got or {}).get("devices") or []:
            print("%-10s %-30s %s" % (d.get("type"), d.get("name"), "active" if d.get("is_active") else ""))
        return 0
    if cmd == "play" and len(argv) > 2:
        print(json.dumps(play(" ".join(argv[2:])), indent=2)); return 0
    print(json.dumps({"logged_in": ready(), "last": _last()}, indent=2)); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
