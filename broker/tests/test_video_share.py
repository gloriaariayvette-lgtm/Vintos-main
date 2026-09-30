#!/usr/bin/env python3
"""A video to him in the avatar chat, and the music share's tempo read as measured (2026-09-30).

A real clip is made here with ffmpeg (a 440 Hz tone with a click every half second, 120 BPM, under a test
picture), taken apart by video_share, and its sound read by sound_read. Whisper is a stub and nothing may
open a socket: this suite hears and sends nothing outside itself.
"""
import importlib.util, os, shutil, socket, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts"))
TMP = tempfile.mkdtemp(prefix="video-share-")
os.environ["HOME"] = TMP
os.environ["NUMBA_CACHE_DIR"] = os.path.join(TMP, "numba")   # librosa's jit cache, never into a read-only site-packages

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:110]) if d else ""))

NET = []
def _no_net(self, *a, **k):
    NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
socket.socket.connect_ex = _no_net

import video_share as V
import sound_read as S

class Ears:
    """Whisper's shape: one segment it thinks is speech, one it thinks is not."""
    def __init__(self): self.calls = 0
    def transcribe(self, path, **kw):
        self.calls += 1
        return {"segments": [{"text": " the kettle is on", "no_speech_prob": 0.05},
                             {"text": " Thanks for watching!", "no_speech_prob": 0.92}]}

src = open(os.path.join(REPO, "bin", "server.py")).read()
route = src[src.index('@app.post("/api/avatar/video")'):]
route = route[:route.index("@app.get(\"/api/grounding/status\")")]
check("the avatar chat takes a video", "async def avatar_chat_with_video" in route)
check("the video door is guarded by the secret", 'X-Vintos-Secret' in route and "APP_SECRET" in route)
check("the clip is taken apart outside the server", '"video_share.py"' in route and "subprocess.run" in route
      and "--frames-dir" in route)
check("his eyes look at the frames in one look", "_describe_clip(watched.get(\"frames\")" in route)
check("it arrives in the avatar chat as her turn, marked as a video",
      "/api/avatar/chat" in route and '"input_kind": "video"' in route)
check("no picture rides along to be misread as the camera", '"image":' not in route)
for client in ("clients/mobile/index.html", os.path.join("..", "vintos-app", "vintos-app", "src", "index.html")):
    p = os.path.join(REPO, client)
    if not os.path.exists(p):
        continue
    c = open(p).read()
    check("the picture button also picks videos (%s)" % ("vintos-app" if "vintos-app" in client else "mobile"),
          "inp.accept = 'image/*,video/*'" in c and "'/api/avatar/video'" in c and "fd.append(kind, file)" in c)

# --- the route itself, run with every door out of the house stubbed ---
import ast, asyncio, io, json as _json, types
_tree = ast.parse(src)
_want = {"_CLIP_EYES", "_CLIP_HEARD", "_SENT_BARE", "_describe_clip", "avatar_chat_with_video"}
_nodes = [n for n in _tree.body if (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in _want for t in n.targets))
          or (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in _want)]
check("the route's pieces are found in the server", len(_nodes) == len(_want), [getattr(n, "name", "") for n in _nodes])
SEQ = []
class _Resp:
    def __init__(self, d): self._d = d
    def json(self): return self._d
class _Client:
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, headers=None, json=None):
        SEQ.append(("post", url, json))
        if "anthropic" in url: return _Resp({"content": [{"text": "A kitchen at dusk; a kettle steams."}]})
        return _Resp({"reply": "I hear the kettle."})
class _App:
    def post(self, *a, **k): return lambda f: f
class _HTTPExc(Exception):
    def __init__(self, status_code=0, detail=""): self.status_code = status_code
from datetime import datetime as _dt
WS = os.path.join(TMP, "ws"); os.makedirs(os.path.join(WS, "memory"))
ns = {"app": _App(), "Request": object, "HTTPException": _HTTPExc, "httpx": types.SimpleNamespace(AsyncClient=_Client),
      "os": os, "json": _json, "time": __import__("time"), "datetime": _dt, "WORKSPACE": WS,
      "MEMORY": os.path.join(WS, "memory"), "APP_SECRET": "s", "LLM_AUTH_HEADERS": {}, "_anthropic_key": lambda: "k"}
exec(compile(ast.Module(body=_nodes, type_ignores=[]), "server-route", "exec"), ns)
fr = os.path.join(TMP, "route-frame.jpg"); open(fr, "wb").write(b"\xff\xd8" + b"0" * 600)
WATCHED = {"duration": 9.0, "has_audio": True, "quiet": False, "speech": "the kettle is on",
           "sound": "Tempo: no steady beat.", "frames": [{"t": 1.5, "path": fr}, {"t": 4.5, "path": fr}]}
def _fake_run(cmd, **kw):
    SEQ.append(("hear", cmd))
    return types.SimpleNamespace(returncode=0, stdout="RESULT " + _json.dumps(WATCHED), stderr="")
class _Req:
    def __init__(self, message): self.headers = {"X-Vintos-Secret": "s"}; self._m = message
    async def form(self):
        return {"message": self._m, "video": types.SimpleNamespace(file=io.BytesIO(b"clip"), filename="c.MOV")}
_real_run = subprocess.run
subprocess.run = _fake_run
try:
    out = asyncio.run(ns["avatar_chat_with_video"](_Req("")))
finally:
    subprocess.run = _real_run
kinds = [x[0] for x in SEQ]
eyes = [x for x in SEQ if x[0] == "post" and "anthropic" in x[1]]
chat = [x for x in SEQ if x[0] == "post" and "/api/avatar/chat" in x[1]]
check("the sound is heard before the eyes look", kinds[:1] == ["hear"] and len(eyes) == 1 and kinds.index("post") > 0, kinds)
_prompt = eyes[0][2]["messages"][0]["content"][-1]["text"] if eyes else ""
check("the eyes get every frame, in order, with the words and sound heard",
      len(eyes[0][2]["messages"][0]["content"]) == 3 and "Words: the kettle is on" in _prompt
      and "Sound: Tempo: no steady beat." in _prompt and "1.5, 4.5" in _prompt, _prompt[-160:])
body = chat[0][2] if chat else {}
check("he gets what was seen, heard and measured in one turn", all(x in body.get("message", "") for x in
      ("A kitchen at dusk", "the kettle is on", "Tempo: no steady beat.")))
check("a video sent with no words is still her turn, not a room event",
      body.get("original_text") == "[Gloria sent you a video without a message]" and body.get("input_kind") == "video")
check("the clip is kept", any(f.endswith("_avatar.mov") for f in os.listdir(os.path.join(WS, "memory", "videos-from-gloria"))))
check("her reply comes back", out.get("reply") == "I hear the kettle." and out["video"]["speech"] == "the kettle is on")
SEQ.clear()
subprocess.run = _fake_run
try:
    asyncio.run(ns["avatar_chat_with_video"](_Req("look at this")))
finally:
    subprocess.run = _real_run
check("her caption stays her words", [x for x in SEQ if "/api/avatar/chat" in x[1]][0][2]["original_text"] == "look at this")
check("the ledger keeps what he saw and heard for a photo or video turn, not only her caption",
      'ledger_text=(msg.message if getattr(msg, "input_kind", None) in ("photo", "video") else None)' in src
      and '"interaction-ledger.py"), ledger_text or gloria_text, reply]' in src)
check("a photo from the picture button is not described again as his screenshot",
      'if msg.image and getattr(msg, "input_kind", None) != "photo":' in src)
check("a photo sent with no words is her turn too",
      '"original_text": (str(message)[:4000] if str(message or "").strip() else _SENT_BARE % "a photo")' in src)

ms = open(os.path.join(REPO, "bin", "music-share.py")).read()
check("the music share no longer halves a tempo", "raw_tempo / 2" not in ms and "from sound_read import measure" in ms)
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("both organs are deployed", "sound_read.py" in dep and "video_share.py" in dep)

check("frames come from across the whole clip, in order",
      V.frame_times(12) == [2.0, 6.0, 10.0] and len(V.frame_times(600)) == V.FRAMES_MAX
      and V.frame_times(600) == sorted(V.frame_times(600)))

watched = {"duration": 12.0, "has_audio": True, "speech": "the kettle is on", "sound": "Tempo: 120.2 BPM.",
           "quiet": False, "frames": []}
t = V.compose(watched, "A kitchen at dusk.", "look")
check("his turn says what he saw, heard and measured, and her words",
      all(x in t for x in ("A kitchen at dusk.", "the kettle is on", "Tempo: 120.2 BPM.", "[Gloria's message with the video:] look")))
check("a silent clip is said to be silent", "no sound" in V.compose(dict(watched, has_audio=False), "x", ""))

try:
    import librosa, numpy as np, soundfile as sf
    have_ears = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
except Exception as e:
    have_ears = False
    print("SKIP the sound checks: librosa or soundfile is not installed here (%s)" % e)

if have_ears:
    sr = 44100
    def tone(bpm, secs=12.0, amp=1.0):
        tt = np.arange(int(secs * sr)) / sr
        y = 0.2 * np.sin(2 * np.pi * 440.0 * tt)
        n = int(0.03 * sr)
        for k in range(int(secs * bpm / 60)):
            i = int(k * 60.0 / bpm * sr)
            y[i:i + n] += 0.8 * np.sin(2 * np.pi * 1000 * tt[:n]) * np.exp(-np.linspace(0, 8, n))
        return (amp * y).astype(np.float32)

    for bpm in (96, 128, 174):
        w = os.path.join(TMP, "t%d.wav" % bpm); sf.write(w, tone(bpm, 20), sr)
        got = S.measure(w)[1]["tempo"]
        check("a %d BPM song reads as %d, not half" % (bpm, bpm), abs(got - bpm) < 4, got)

    held = os.path.join(TMP, "held.wav"); sf.write(held, (0.2 * np.sin(2 * np.pi * 440.0 * np.arange(12 * sr) / sr)).astype(np.float32), sr)
    check("a held tone with no beat is not given an invented tempo", "Tempo: no steady beat." in S.measure(held)[0], S.measure(held)[0])

    import json as _tj, tempo_check as TC
    check("the tempo check names right, double and half", (TC.verdict(161.5, 80), TC.verdict(80.7, 80),
          TC.verdict(40, 80), TC.verdict(100, 80)) == ("double", "right", "half", "off"))
    _ml = os.path.join(TMP, "music.json")
    _tj.dump({"generated": [{"title": "t128", "authored": {"tempo": "128 BPM, A minor"},
                             "tracks": [{"local_file": os.path.join(TMP, "t128.wav")}]},
                            {"title": "no file", "authored": {"tempo": "90"}, "tracks": [{"local_file": "/nope.wav"}]}]},
             open(_ml, "w"))
    _rows = TC.his_songs(_ml)
    check("the tempo check reads his songs that have a written tempo and a file", [r[:2] for r in _rows] == [("t128", 128.0)])
    _sc = TC.check(_rows)
    check("and scores a song read at its written tempo as right", _sc["beat"]["right"] == 1, _sc)

    spec = importlib.util.spec_from_file_location("music_share_mod", os.path.join(REPO, "bin", "music-share.py"))
    M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
    line = M.analyze_audio(os.path.join(TMP, "t128.wav"), transcribe=False)["acoustic"] or ""
    check("the music share's own reading carries the true tempo", "Tempo: 12" in line and "pitch class: A" in line, line)

    def clip(name, wav=None):
        out = os.path.join(TMP, name)
        cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=12"]
        if wav:
            cmd += ["-i", wav, "-c:a", "aac", "-shortest"]
        subprocess.run(cmd + ["-c:v", "mpeg4", out], check=True, capture_output=True)
        return out

    w120 = os.path.join(TMP, "c120.wav"); sf.write(w120, tone(120), sr)
    ears = Ears()
    fd = os.path.join(TMP, "frames"); os.makedirs(fd)
    got = V.watch(clip("with-sound.mp4", w120), fd, whisper=ears)
    check("the clip's length is read", abs(got["duration"] - 12) < 0.6, got["duration"])
    check("three frames are cut, in order, and exist",
          [f["t"] for f in got["frames"]] == [2.0, 6.0, 10.0] and all(os.path.getsize(f["path"]) > 500 for f in got["frames"]))
    check("the sound pulled from a video reads true: 120 BPM, A",
          "Tempo: 1" in got["sound"] and abs(float(got["sound"].split("Tempo: ")[1].split(" ")[0]) - 120) < 4
          and "pitch class: A" in got["sound"], got["sound"])
    check("Whisper hears the words", ears.calls == 1 and got["speech"] == "the kettle is on", got["speech"])
    check("a line Whisper marks as not speech is dropped", "Thanks for watching" not in got["speech"])

    ears = Ears(); fd2 = os.path.join(TMP, "frames2"); os.makedirs(fd2)
    mute = V.watch(clip("no-sound.mp4"), fd2, whisper=ears)
    check("a clip with no sound track is seen and not heard",
          mute["has_audio"] is False and len(mute["frames"]) == 3 and ears.calls == 0)

    wq = os.path.join(TMP, "quiet.wav"); sf.write(wq, tone(120, amp=0.001), sr)
    ears = Ears(); fd3 = os.path.join(TMP, "frames3"); os.makedirs(fd3)
    q = V.watch(clip("quiet.mp4", wq), fd3, whisper=ears)
    check("near silence is not handed to Whisper to invent words", q["quiet"] is True and ears.calls == 0 and q["speech"] == "")

check("nothing in this suite reached the network", NET == [] and socket.socket.connect is _no_net)
shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
