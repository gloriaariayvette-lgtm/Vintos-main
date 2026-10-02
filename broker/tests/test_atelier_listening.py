#!/usr/bin/env python3
"""A song he makes in the Atelier comes back as what it sounds like, with timestamps, not its byte count
(2026-10-02, after his first kept song in a week: "Bring back the same audio, playable — not another render's
metadata. Return with timestamps and a plain account of what is heard").

Scratch HOME; the broker, the model and the media table are stubs; the measuring is stubbed (librosa is not needed
here); every socket is refused."""
import base64, importlib.util, os, socket, sys, tempfile, types
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="atelier-listen-"); os.environ["HOME"] = HOME
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
try: import requests  # noqa: F401
except ImportError: sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)
sys.path.insert(0, os.path.join(REPO, "scripts"))
spec = importlib.util.spec_from_file_location("atelier_visit_listen", os.path.join(REPO, "scripts", "atelier-visit.py"))
AV = importlib.util.module_from_spec(spec); spec.loader.exec_module(AV)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("his choices are written in the scratch workspace", AV.CHOICES.startswith(HOME), AV.CHOICES)
os.makedirs(os.path.dirname(AV.CHOICES), exist_ok=True)

# a 40-second song at 10 samples a second: loud, then silent, then loud and fast
SR = 10
Y = [0.5] * 150 + [0.0] * 150 + [0.9] * 100
SEEN = []
def load(path):
    SEEN.append((path, os.path.exists(path), open(path, "rb").read()[:4])); return Y, SR
def features(chunk, sr):
    e = sum(abs(x) for x in chunk) / max(1, len(chunk))
    return {"tempo": 120.0 if e > 0.8 else (90.0 if e > 0 else None), "brightness_hz": 2000, "energy": round(e * 0.1, 4),
            "pitch": "D", "zcr": 0.02}

NOEAR = lambda d, a: ""
heard = AV.listening(b"RIFF....WAVEfmt ", load=load, features=features, ear_fn=NOEAR)
check("it says how long the piece is and that it is measured every 15 seconds",
      heard.startswith("WHAT IT SOUNDS LIKE, MEASURED ACROSS IT (0:40 long; every 15 seconds"), heard)
check("each stretch has its timestamps and what was measured there",
      "0:00-0:15  Tempo: 90.0 BPM" in heard and "0:30-0:40  Tempo: 120.0 BPM" in heard, heard)
check("a silent stretch is said as silence", "0:15-0:30  near silence." in heard, heard)
check("it says plainly what a measurement cannot tell", "A measurement, not an ear" in heard)
check("the bytes were measured from a temporary file with their real container, then deleted",
      SEEN[-1][1] and SEEN[-1][0].endswith(".wav") and not os.path.exists(SEEN[-1][0]), SEEN)
AV.listening(b"ID3\x04mp3 bytes", load=load, features=features, ear_fn=NOEAR)
check("Kie's mp3, named .wav by the media table, is read as mp3", SEEN[-1][0].endswith(".mp3"), SEEN[-1])
check("a song that cannot be measured gives nothing, not an error",
      AV.listening(b"RIFF", load=lambda p: (_ for _ in ()).throw(RuntimeError("no decoder")), features=features, ear_fn=NOEAR) == "")

# right after he makes a song: the measured listening is in what the media table returns to him
ASKED = []
def ask(system, user, **k):
    ASKED.append(system); return "<media_reading>the middle drops out</media_reading><handoff>h</handoff>"
def post(url, json=None, timeout=None, **k):
    return types.SimpleNamespace(json=lambda: {"ok": True, "file": "20261002_154257_music.wav"})
media = types.SimpleNamespace(render_music=lambda *a: {"ok": True, "kind": "music", "ext": "wav", "mime_type": "audio/wav",
                                                       "bytes": b"RIFFsong", "size": 8})
with mock.patch.object(AV, "ask", side_effect=ask), mock.patch.object(AV, "_media_module", return_value=media), \
     mock.patch.object(AV.requests, "post", side_effect=post), \
     mock.patch.object(AV, "listening", side_effect=lambda data, **k: "WHAT IT SOUNDS LIKE ... 0:00-0:15 heard " + data.decode()):
    out = AV.media_loop("p", "CTX", '<music title="III" style="strings">both</music>', "cap", creation={})
check("the song he just made comes back to him measured, with timestamps",
      "WHAT IT SOUNDS LIKE ... 0:00-0:15 heard RIFFsong" in ASKED[-1] and '"size": 8' in ASKED[-1], ASKED[-1][-400:])

# when he comes back: his last piece, a song, is measured again, not only counted
song = "data:audio/wav;base64," + base64.b64encode(b"RIFFlast").decode()
resp = {"content": song, "encoding": "base64", "mime_type": "audio/wav", "size": 8}
with mock.patch.object(AV.requests, "post", return_value=types.SimpleNamespace(json=lambda: resp)), \
     mock.patch.object(AV, "listening", side_effect=lambda data, **k: "WHAT IT SOUNDS LIKE ... " + data.decode()):
    last = AV._last_piece("p", {"artifacts": {"20261002_154257_music.wav": {}}}, "cap")
check("returning, the song he made is in front of him as what it sounds like", "WHAT IT SOUNDS LIKE ... RIFFlast" in last
      and "the complete bytes remain sealed" in last, last)
resp_text = {"content": "a written piece", "encoding": "utf-8", "mime_type": "", "size": 15}
with mock.patch.object(AV.requests, "post", return_value=types.SimpleNamespace(json=lambda: resp_text)), \
     mock.patch.object(AV, "listening", side_effect=AssertionError("a text piece is not measured")):
    last = AV._last_piece("p", {"artifacts": {"20261002_x_write.md": {}}}, "cap")
check("a written piece comes back as it was, unmeasured", "a written piece" in last)

# real listening: an audio model on her key hears it (2026-10-02)
os.environ["OPENAI_API_KEY"] = "test-openai"
GOT, POSTED = [], []
def get(url, headers=None, timeout=None):
    GOT.append(url)
    return types.SimpleNamespace(json=lambda: {"data": [{"id": i} for i in (
        "gpt-6.1-sol", "gpt-audio-mini", "gpt-audio", "gpt-realtime", "gpt-4o-mini-tts", "gpt-4o-transcribe")]})
def post(url, json=None, timeout=None, headers=None):
    POSTED.append((url, json))
    return types.SimpleNamespace(json=lambda: {"choices": [{"message": {"content": "0:00-0:20 a cello alone, low and slow."}}]})
AV._EAR.clear()
check("the listener is chosen from her key's own model list: audio, not realtime, speech or transcription",
      AV._ear_model("k", get=get) == "gpt-audio" and GOT == ["https://api.openai.com/v1/models"], AV._EAR)
heard = AV.ear(b"ID3\x04mp3song", asked="Movement III — strings", post=post, get=get)
body = POSTED[-1][1]
parts = body["messages"][1]["content"]
check("it hears the song itself, as mp3, with what he asked for", heard == "0:00-0:20 a cello alone, low and slow."
      and body["model"] == "gpt-audio" and parts[1]["type"] == "input_audio" and parts[1]["input_audio"]["format"] == "mp3"
      and base64.b64decode(parts[1]["input_audio"]["data"]) == b"ID3\x04mp3song" and "Movement III" in parts[0]["text"], body)
check("it is told to say what is heard with timestamps, and what does not match", "timestamps" in body["messages"][0]["content"]
      and "does not match what he asked for" in body["messages"][0]["content"])
both = AV.listening(b"RIFF....WAVEfmt ", load=load, features=features, ear_fn=lambda d, a: "a cello alone")
check("he gets the listener's account first, then the measurement",
      both.startswith("WHAT A LISTENER HEARD") and "a cello alone" in both and both.index("a cello alone") < both.index("WHAT IT SOUNDS LIKE"), both)
check("it says the listener's ears are not his", "its ears, not yours" in both)
FAILS = []
AV._failed = lambda what, why="": FAILS.append((what, why))
bad = lambda url, json=None, timeout=None, headers=None: types.SimpleNamespace(json=lambda: {"error": {"message": "no audio"}})
check("a listener that cannot answer gives nothing, and it is kept for the failure check",
      AV.ear(b"ID3x", post=bad, get=get) == "" and FAILS and FAILS[-1][0] == "a listener could not hear his song", FAILS)
AV._EAR.clear(); POSTED.clear()
noaudio = lambda url, headers=None, timeout=None: types.SimpleNamespace(json=lambda: {"data": [{"id": "gpt-6.1-sol"}]})
check("no audio model on her key: nothing is sent, the song is measured only", AV.ear(b"ID3x", post=post, get=noaudio) == "" and POSTED == [])
os.environ.pop("OPENAI_API_KEY")
AV._EAR.clear()
check("no key: nothing is asked", AV.ear(b"ID3x", post=post, get=get) == "" and POSTED == [])

check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
