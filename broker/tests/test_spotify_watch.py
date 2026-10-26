#!/usr/bin/env python3
"""His Spotify pick on her Watch (Gloria, 18 October): in the avatar chat he writes [SPOTIFY: Title - Artist] and the
track plays on her Watch through Spotify Connect. Only the Watch - never her phone, not the Echo. Asleep, nothing.

Scratch HOME (the secrets and the log live only there); Spotify is a fake behind urlopen; every socket is refused."""
import io, json, os, socket, sys, tempfile, time, urllib.error, urllib.parse
from unittest.mock import patch
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="spotify-watch-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import watch_presence as W
ASLEEP = [False]
W.should_hold = lambda: (ASLEEP[0], "Gloria is asleep" if ASLEEP[0] else "")
import spotify_watch as S
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  %r" % (d,)))

CALLS = []
DEVICES = [{"id": "ph1", "type": "Smartphone", "name": "Gloria's iPhone", "is_active": True},
           {"id": "w1", "type": "Watch", "name": "Gloria's Apple Watch", "is_active": False}]
TRACKS = [{"uri": "spotify:track:enjoy", "name": "Enjoy the Silence", "artists": [{"name": "Depeche Mode"}]}]
PLAY_CODE = [204]
class Resp(io.BytesIO):
    def __init__(self, body, status=200): super().__init__(json.dumps(body).encode() if body is not None else b""); self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): pass
def fake(req, timeout=None):
    url = req.full_url; CALLS.append((req.get_method(), url, req.data))
    if url == S.TOKEN:
        f = urllib.parse.parse_qs(req.data.decode())
        if f["grant_type"] == ["authorization_code"]:
            return Resp({"access_token": "AT1", "refresh_token": "RT1", "expires_in": 3600})
        return Resp({"access_token": "AT2", "expires_in": 3600})
    assert url.startswith(S.API), url
    if "/search" in url: return Resp({"tracks": {"items": TRACKS}})
    if url.endswith("/me/player/devices"): return Resp({"devices": DEVICES})
    if "/me/player/play" in url:
        if PLAY_CODE[0] != 204:
            raise urllib.error.HTTPError(url, PLAY_CODE[0], "no", {}, io.BytesIO(b'{"error":{"message":"Device not found"}}'))
        return Resp(None, 204)
    raise AssertionError(url)
patch("urllib.request.urlopen", fake).start()

check("every store is throwaway and Spotify is a fake", all(p.startswith(HOME) for p in (S.SECRETS, S.PENDING, S.LOG))
      and S.urllib.request.urlopen is fake)
check("not logged in: he is told nothing, a tag is only taken out", S.context_line() == ""
      and S.take("Here. [SPOTIFY: Enjoy the Silence - Depeche Mode]") == "Here." and not CALLS)

url = S.login_url("CID123")
q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
check("the login asks only to see and start playback, with PKCE and no client secret",
      q["scope"] == [S.SCOPES] and q["code_challenge_method"] == ["S256"] and q["redirect_uri"] == ["http://127.0.0.1:8765/callback"]
      and "client_secret" not in url)
check("an address from another login is refused", "not from this login" in S.finish(S.REDIRECT + "?code=x&state=wrong"))
check("her Agree finishes the login, pasted as it really was: no http://, an unclosed quote, extra fields",
      S.finish("'127.0.0.1:8765/callback?code=C0DE&state=" + q["state"][0] + "&ubi=CAIQ%3D%3D") == "OK" and S.ready()
      and any(c[1] == S.TOKEN and b"code=C0DE" in c[2] for c in CALLS))
with patch("builtins.input", side_effect=KeyboardInterrupt):
    check("login asks for the pasted address instead of waiting silently", S.main(["x", "login", "CID123"]) == 1)
os.remove(S.SECRETS)
with patch("builtins.input", side_effect=lambda *_: "127.0.0.1:8765/callback?code=C0DE&state=" + json.load(open(S.PENDING))["state"]):
    check("pasting at the login prompt finishes it", S.main(["x", "login", "CID123"]) == 0 and S.ready())
check("the token is kept private (0600) and the pending login is gone",
      oct(os.stat(S.SECRETS).st_mode & 0o777) == "0o600" and not os.path.exists(S.PENDING))
check("he is told he can, and how, once she is logged in", "[SPOTIFY: Title - Artist]" in S.context_line()
      and "not her phone" in S.context_line())

row = S.play("Enjoy the Silence - Depeche Mode")
put = [c for c in CALLS if c[0] == "PUT"]
check("his pick plays on her Watch, and only there", row["played"] and row["device"] == "Gloria's Apple Watch"
      and len(put) == 1 and "device_id=w1" in put[0][1] and json.loads(put[0][2]) == {"uris": ["spotify:track:enjoy"]}, row)
check("the phone is never the device, even when it is the active one", not any("device_id=ph1" in c[1] for c in CALLS))

DEVICES[:] = [d for d in DEVICES if d["type"] != "Watch"]; n = len(CALLS)
row = S.play("Enjoy the Silence - Depeche Mode")
check("Spotify closed on her Watch: nothing plays anywhere, and why is written down", not row["played"]
      and "Watch is not listening" in row["why"] and not any(c[0] == "PUT" for c in CALLS[n:]), row)
check("he hears next turn that it did not play, and why", "did not play" in S.context_line()
      and "Watch is not listening" in S.context_line())
DEVICES.append({"id": "w1", "type": "Watch", "name": "Gloria's Apple Watch"})
_t0 = S.time.time; S.time.time = lambda: _t0() + 25 * 3600
check("a miss from more than a day ago is not repeated to him", "did not play" not in S.context_line()
      and "[SPOTIFY: Title - Artist]" in S.context_line())
S.time.time = _t0
check("he is told a song now and then is welcome", "welcome" in S.context_line())

TRACKS[:] = [{"uri": "spotify:track:other", "name": "Something Else", "artists": [{"name": "Nobody"}]}]
row = S.play("Enjoy the Silence - Depeche Mode")
check("a song Spotify does not have is not swapped for another", not row["played"] and "closest" in row["why"], row)
TRACKS[:] = [{"uri": "spotify:track:enjoy", "name": "Enjoy the Silence", "artists": [{"name": "Depeche Mode"}]}]

ASLEEP[0] = True; n = len(CALLS)
row = S.play("Enjoy the Silence - Depeche Mode")
check("asleep: nothing plays, and Spotify is not even asked", not row["played"] and row["why"] == "she is asleep"
      and len(CALLS) == n, row)
ASLEEP[0] = False

PLAY_CODE[0] = 404
row = S.play("Enjoy the Silence - Depeche Mode")
check("Spotify refusing is written down with its reason", not row["played"] and "404" in row["why"]
      and "Device not found" in row["why"], row)
PLAY_CODE[0] = 204

s = json.load(open(S.SECRETS)); s["expires_at"] = 0; json.dump(s, open(S.SECRETS, "w"))
S.play("Enjoy the Silence - Depeche Mode")
check("an expired token is refreshed with the refresh token", json.load(open(S.SECRETS))["access_token"] == "AT2"
      and any(c[1] == S.TOKEN and b"refresh_token" in c[2] for c in CALLS))

n = len(open(S.LOG).read().splitlines())
said = S.take("I want you to hear this. [SPOTIFY: Enjoy the Silence - Depeche Mode]")
deadline = time.time() + 5
while len(open(S.LOG).read().splitlines()) == n and time.time() < deadline: time.sleep(0.05)
check("the tag is taken out of his words and plays in the background", said == "I want you to hear this."
      and json.loads(open(S.LOG).read().splitlines()[-1])["played"], said)
n = len(CALLS)
check("a test or witness-less turn only strips the tag", S.take("x [SPOTIFY: a - b]", act=False) == "x" and len(CALLS) == n)
check("a reply without the tag is untouched", S.take("plain [HOME: spotify a - b]") == "plain [HOME: spotify a - b]")

# 26 October: Spotify closed on her Watch -> one notification asks her to open it, and the song plays on the Watch the
# moment it appears, or is written down after the wait. Never the phone. Nothing is sent for real.
import types
NUDGES = []
sys.modules["deliver"] = types.SimpleNamespace(deliver=lambda aid, ch, msg, title=None, **k: (NUDGES.append((aid, ch, msg)), {"state": "sent"})[1])
WATCH = {"id": "w1", "type": "Smartwatch", "name": "Apple Watch", "is_active": True}
DEVICES[:] = [d for d in DEVICES if d["type"] != "Watch"]
T = [0.0]; polls = []
def fake_sleep(s):
    T[0] += s; polls.append(s)
    if len(polls) == 3: DEVICES.append(WATCH)
n = len(CALLS)
row = S.play("Enjoy the Silence - Depeche Mode", nudge=True, sleep=fake_sleep, clock=lambda: T[0])
check("Watch closed: she gets one notification asking her to open Spotify on it", len(NUDGES) == 1
      and NUDGES[0][1] == "ntfy" and "Open Spotify on your Watch" in NUDGES[0][2] and row.get("nudged") == "sent", NUDGES)
check("the song plays on the Watch the moment it appears, never the phone", row["played"] and row["device"] == "Apple Watch"
      and row["waited_s"] == 15 and not any("device_id=ph1" in c[1] for c in CALLS[n:]), row)
DEVICES[:] = [d for d in DEVICES if d is not WATCH]; T[0] = 0.0
row = S.play("Enjoy the Silence - Depeche Mode", nudge=True, sleep=lambda s: T.__setitem__(0, T[0] + s), clock=lambda: T[0])
check("the Watch never appears: written down after the wait, nothing played", not row["played"]
      and "5 min passed" in row["why"] and len(NUDGES) == 2, row)
S._WAITING.acquire()
row = S.play("Enjoy the Silence - Depeche Mode", nudge=True, sleep=lambda s: None)
S._WAITING.release()
check("while one song waits, another pick is not nudged again", len(NUDGES) == 2 and "already waiting" in row["why"], row)
row = S.play("Enjoy the Silence - Depeche Mode")
check("without nudge (the command line) nothing is sent and nothing waits", len(NUDGES) == 2 and "not listening" in row["why"])
check("his avatar pick nudges and waits", 'kwargs={"nudge": True}' in open(S.__file__).read())
DEVICES.append(WATCH)

srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("it is in his avatar chat: the line in his context, the tag taken from his reply, guarded like his home tags",
      "_spw.context_line()" in srv and "_spw.take(reply, act=not (_test_turn" in srv)
check("it is in the deploy", " spotify_watch.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
