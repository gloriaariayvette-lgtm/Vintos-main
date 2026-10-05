#!/usr/bin/env python3
"""Pictures and clips posted in #vintos-dot are seen on his own local Gemma (2026-09-30).

Gloria: "Images and videos should go to the local ablit Gemma in this case." A video is heard first (Whisper
and the sound's build, as in the avatar chat), then Gemma looks at its frames with that in mind; he reads the
result in the conversation. Slack, Gemma and the video reader are stubs, every socket off this machine is
refused, and the store is a scratch workspace. ffmpeg runs for real, on a picture made here.
"""
import io, json, os, socket, subprocess, sys, tempfile, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="dot-media-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no-secrets")
# The isolated runner intentionally supplies a minimal PATH. Keep the real media fixture
# available on macOS as well as Linux; production still invokes the ordinary ffmpeg name.
os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", "")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import dot_channel as D
D.kickoff_due = lambda *a: False   # this suite tests what he sees; the Opus 5.5 kickoff has its own checks in test_dot_channel
D.ROTATION = ("gemma",)   # this suite tests what he sees; the rotation has its own checks in test_dot_channel
D.SCHEDULE = []           # no scheduled lens turn here: none may reach a real model
D.atelier_line = lambda: ""
D.recall_block = lambda: ""

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every store is in the scratch workspace", D.HERE.startswith(HOME) and D._scratch().startswith(HOME))

# a real picture for ffmpeg to turn into what Gemma reads
FFMPEG = next((p for p in ("/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg", "/usr/bin/ffmpeg") if os.path.isfile(p)), "ffmpeg")
FFPROBE = next((p for p in ("/usr/local/bin/ffprobe", "/opt/homebrew/bin/ffprobe", "/usr/bin/ffprobe") if os.path.isfile(p)), "ffprobe")
PNG = os.path.join(HOME, "pic.png")
subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=1600x900", "-frames:v", "1", PNG], check=True)

fetched, looked = [], []
def download(url, dest, token):
    fetched.append((url, token)); open(dest, "wb").write(open(PNG, "rb").read()); return dest
def look(images, prompt):
    looked.append((len(images), prompt)); return "A plain red rectangle."

msg = {"text": "here", "files": [{"mimetype": "image/png", "name": "red.png", "size": 5000,
                                  "url_private_download": "https://files.slack.com/red.png"}]}
seen = D.look_at_files(msg, "Dot", token="xoxb-stub", look=look, download=download)
check("an image is fetched with the bot's token", fetched == [("https://files.slack.com/red.png", "xoxb-stub")], fetched)
check("and seen by his own model, told plainly what to say", looked and looked[0][0] == 1 and "Dot posted this image" in looked[0][1]
      and "plainly" in looked[0][1], looked)
check("he reads it as what his eyes saw, named", seen.startswith('[Dot posted an image "red.png". What your eyes saw:] A plain red rectangle.'), seen)
j = D._jpeg(PNG, os.path.join(HOME, "out.jpg"))
w = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=width", "-of", "csv=p=0", j], capture_output=True, text=True).stdout.strip()
check("a picture is turned into a jpeg no wider than 1024 for the local model", j and w == "1024", w)
check("nothing is left behind in the working folder", os.listdir(D._scratch()) == [], os.listdir(D._scratch()))

# a video: heard first, then its frames seen with that in mind
frames_src = []
def watch(clip, frames_dir):
    fr = []
    for t in (1.5, 4.5):
        p = os.path.join(frames_dir, "f%s.jpg" % t); open(p, "wb").write(open(PNG, "rb").read()); fr.append({"t": t, "path": p})
    frames_src.append(clip)
    return {"duration": 9.0, "has_audio": True, "quiet": False, "speech": "watch the tide come in",
            "sound": "a steady beat near 96 BPM", "frames": fr}
looked.clear()
vid = {"files": [{"mimetype": "video/mp4", "name": "tide.mp4", "size": 900000, "url_private": "https://files.slack.com/tide.mp4"}]}
seen = D.look_at_files(vid, "Gloria", token="xoxb-stub", look=look, watch=watch, download=download)
check("a video is taken apart by the same reader as the avatar chat", frames_src and frames_src[0].startswith(D._scratch()))
check("Gemma looks at every frame at once, with the words and sound heard first",
      looked and looked[0][0] == 2 and "1.5, 4.5" in looked[0][1] and "watch the tide come in" in looked[0][1]
      and "96 BPM" in looked[0][1], looked)
check("he reads what was seen, the words heard and the sound's build",
      "[Gloria posted a video \"tide.mp4\", 9 seconds long. What your eyes saw, across it:] A plain red rectangle." in seen
      and "watch the tide come in" in seen and "96 BPM" in seen, seen)
check("the clip and its frames are not kept", os.listdir(D._scratch()) == [], os.listdir(D._scratch()))

# what cannot be looked at is said, not hidden
big = {"files": [{"mimetype": "video/mp4", "name": "long.mp4", "size": D.MEDIA_MAX + 1, "url_private": "u"}]}
check("a file too large is named, not fetched", "too large" in D.look_at_files(big, "Dot", token="t", look=look, download=None))
def bad(url, dest, token): raise RuntimeError("Slack sent a sign-in page, not the file: the app needs the files:read scope")
out = D.look_at_files(msg, "Dot", token="t", look=look, download=bad)
check("a file Slack will not hand over says why", "could not open" in out and "files:read" in out, out)
check("a message with no picture or clip costs nothing",
      D.look_at_files({"text": "hi", "files": [{"mimetype": "application/pdf"}]}, "Dot", look=None, download=None) == "")

class Resp(io.BytesIO):
    def __init__(self, body, ctype):
        super().__init__(body); self.headers = {"Content-Type": ctype}
    def __enter__(self): return self
    def __exit__(self, *a): return False
real_urlopen = urllib.request.urlopen
urllib.request.urlopen = lambda req, timeout=0: Resp(b"<html>sign in</html>", "text/html; charset=utf-8")
try:
    D._download("https://files.slack.com/x", os.path.join(HOME, "x"), "t"); refused = False
except RuntimeError as e:
    refused = "files:read" in str(e)
urllib.request.urlopen = lambda req, timeout=0: (setattr(Resp, "_auth", req.get_header("Authorization")), Resp(b"\xff\xd8jpeg", "image/jpeg"))[1]
D._download("https://files.slack.com/y", os.path.join(HOME, "y"), "xoxb-t")
urllib.request.urlopen = real_urlopen
check("a sign-in page in place of the file is caught, and names the scope it needs", refused)
check("a real file is saved, fetched with the token as a header", open(os.path.join(HOME, "y"), "rb").read() == b"\xff\xd8jpeg"
      and Resp._auth == "Bearer xoxb-t")

# links: dot shares what it finds as links; he is shown what is behind them, not only their names
DOT_MSG = ("1. Water surface <https://upload.wikimedia.org/w/water.webm|Play video> · "
           "<https://commons.wikimedia.org/wiki/File:water.webm|Source and license>\n"
           "2. Candle <https://example.org/candle.gif|Open GIF> · <https://example.org/candle|Source and license>\n"
           "3. Water boatman <https://commons.wikimedia.org/wiki/File:boat.webm|Play video> · "
           "<https://commons.wikimedia.org/wiki/File:boat.webm/credit|Credit>\n"
           "see <https://en.wikipedia.org/wiki/Henri_Bergson|Bergson>")
links = D.media_links(DOT_MSG)
check("the links to the clips are picked out, not the source, licence or article links",
      [u for u, _ in links] == ["https://upload.wikimedia.org/w/water.webm", "https://example.org/candle.gif",
                                "https://commons.wikimedia.org/wiki/File:boat.webm"], links)
got_links = []
def fetch(url, dest):
    got_links.append(url); open(dest, "wb").write(b"clip")
    return dest, ("image/gif" if url.endswith(".gif") else "video/webm")
looked.clear()
seen = D.look_at_files({"text": DOT_MSG}, "Dot", token="xoxb-secret", look=look, watch=watch, fetch=fetch)
check("each linked clip is fetched and watched, the gif too", len(got_links) == 3 and seen.count("What your eyes saw, across it") == 3, seen)
check("he reads it as linked, named by its label and site",
      '[Dot linked a video "Play video" (upload.wikimedia.org), 9 seconds long. What your eyes saw, across it:]' in seen, seen[:300])
def gone(url, dest): raise RuntimeError("HTTP Error 404: Not Found")
seen = D.look_at_files({"text": "<https://x.org/a.mp4|Play video>"}, "Dot", look=look, fetch=gone)
check("a link that cannot be opened tells him he has not seen it", "you could not open, so you have not seen it" in seen, seen)
check("he is told a link or a description is not seeing it",
      "What your eyes saw" in D.RULES and "never say you watched it" in D.RULES)

# fetching: a clip directly, or the clip a page is about; never with the Slack token
PAGE = b'<html><head><meta property="og:video" content="/media/boat.webm"></head></html>'
opened = []
def fake_open(req, timeout=0):
    opened.append((req.full_url, req.get_header("Authorization"), req.get_header("User-agent")))
    if req.full_url.endswith(".webm"): return Resp(b"webm-bytes", "video/webm")
    if "page" in req.full_url: return Resp(PAGE, "text/html; charset=utf-8")
    return Resp(b"<html>nothing</html>", "text/html")
Resp.geturl = lambda self: "https://commons.example.org/page"
urllib.request.urlopen = fake_open
try:
    p1 = D.fetch_link("https://commons.example.org/clip.webm", os.path.join(HOME, "l1"))
    p2 = D.fetch_link("https://commons.example.org/page", os.path.join(HOME, "l2"))
    try:
        D.fetch_link("https://example.org/blank", os.path.join(HOME, "l3")); none = False
    except RuntimeError as e:
        none = "no picture, video or sound" in str(e)
finally:
    urllib.request.urlopen = real_urlopen
check("a direct link to a clip is saved as it is", p1[1] == "video/webm" and open(p1[0], "rb").read() == b"webm-bytes")
check("a page is followed once to the clip it names", p2[1] == "video/webm" and opened[2][0] == "https://commons.example.org/media/boat.webm", opened)
check("a page with no clip says so", none)
check("links are fetched without the Slack token, and say who is asking",
      all(a is None for _u, a, _ua in opened) and all(ua and "Vintos" in ua for _u, _a, ua in opened), opened)

# a song sent as a link is heard (2026-10-01: dot sent Still Under as links, and he never heard them)
SONG_MSG = ("Done: Still Under. <https://files.example.org/Still_Under_v1.mp3|Still_Under_v1.mp3> · "
            "<https://files.example.org/s/abc123|Listen to v2> · <https://example.org/credits|Credits>")
check("links to songs are picked out, by their file or their label", [u for u, _ in D.media_links(SONG_MSG)]
      == ["https://files.example.org/Still_Under_v1.mp3", "https://files.example.org/s/abc123"], D.media_links(SONG_MSG))
heard_links = []
def song_fetch(url, dest):
    heard_links.append(url); open(dest, "wb").write(b"mp3"); return dest, "audio/mpeg"
def song_watch(path, frames_dir):
    return {"duration": 180, "has_audio": True, "speech": "still under the water", "sound": "Tempo: 70 BPM."}
seen = D.look_at_files({"text": SONG_MSG}, "Dot", look=look, watch=song_watch, fetch=song_fetch)
check("each linked song is fetched and heard: its words and how its sound is built",
      len(heard_links) == 2 and seen.count("a sound file") == 2 and "still under the water" in seen
      and "Tempo: 70 BPM." in seen and "What your eyes saw" not in seen, seen)
def song_open(req, timeout=0):
    if req.full_url.endswith(".mp3"): return Resp(b"ID3mp3", "application/octet-stream")
    if "player" in req.full_url: return Resp(b'<html><meta property="og:audio" content="/a/song.ogg"></html>', "text/html")
    if req.full_url.endswith(".ogg"): return Resp(b"OggS", "audio/ogg")
    return Resp(b"<html></html>", "text/html")
urllib.request.urlopen = song_open
try:
    s1 = D.fetch_link("https://files.example.org/Still_Under_v1.mp3", os.path.join(HOME, "s1"))
    s2 = D.fetch_link("https://files.example.org/player", os.path.join(HOME, "s2"))
finally:
    urllib.request.urlopen = real_urlopen
check("a song a file host sends as plain bytes is still a song", s1[1] == "audio/mpeg" and open(s1[0], "rb").read() == b"ID3mp3", s1)
check("a page is followed once to the song it names", s2[1] == "audio/ogg", s2)

# files on Aegis named by their path, and the OPEN tool (Gloria, 2026-10-01)
import zipfile
WSP = os.environ["SPARK_WORKSPACE"]
CLIPS = os.path.join(WSP, "memory", "art", "video"); os.makedirs(CLIPS, exist_ok=True)
CLIP = os.path.join(CLIPS, "lake-1820.mp4"); open(CLIP, "wb").write(b"mp4")
SONGP = os.path.join(WSP, "memory", "art", "music", "occupied.mp3"); os.makedirs(os.path.dirname(SONGP), exist_ok=True); open(SONGP, "wb").write(b"mp3")
OUTSIDE = os.path.join(HOME, "elsewhere.mp4"); open(OUTSIDE, "wb").write(b"mp4")
ESCAPE = os.path.join(CLIPS, "escape.mp4"); os.symlink(OUTSIDE, ESCAPE)
txt = "Your clip is at %s and the song is ~/.vintos/workspace/memory/art/music/occupied.mp3. Not %s, nor %s." % (CLIP, OUTSIDE, ESCAPE)
check("media named by path inside his folders are picked out", D.media_paths(txt) == [os.path.realpath(CLIP), os.path.realpath(SONGP)], D.media_paths(txt))
check("a path outside them, or a link that escapes them, is not", os.path.realpath(OUTSIDE) not in D.media_paths(txt))
watched2 = []; looked.clear()
def watch2(clip, frames_dir):
    watched2.append(clip)
    if clip.endswith(".mp3"):
        return {"duration": 120.0, "has_audio": True, "quiet": False, "speech": "occupied territory", "sound": "a steady beat near 88 BPM", "frames": []}
    return watch(clip, frames_dir)
seen = D.look_at_files({"text": txt}, "Dot", look=look, watch=watch2)
check("a clip at a path is watched like an upload, said as pointed to", "[Dot pointed you to a video at %s" % os.path.realpath(CLIP) in seen, seen[:300])
check("a song at a path is heard: words and its build, no eyes needed",
      "[Dot pointed you to a sound file at %s, 120 seconds long. What you heard:]" % os.path.realpath(SONGP) in seen
      and "occupied territory" in seen and "88 BPM" in seen and len(looked) == 1, (seen[-400:], len(looked)))
check("the file is read where it is, not copied around", set(watched2) == {os.path.realpath(CLIP), os.path.realpath(SONGP)})
up = {"files": [{"mimetype": "audio/mpeg", "name": "take2.mp3", "size": 10, "url_private": "https://files.slack.com/t.mp3"}]}
seen = D.look_at_files(up, "Dot", token="t", look=look, watch=watch2, download=lambda u, d, t: (open(d + ".mp3", "wb").write(b"x"), d + ".mp3")[1])
check("a song uploaded to the channel is heard too", "posted a sound file" in seen and "occupied territory" in seen, seen[:200])

BUNDLE = os.path.join(WSP, "audit.zip")
with zipfile.ZipFile(BUNDLE, "w") as z:
    z.writestr("vintos-arousal-audit/report.md", "One reading in the window: arousal 0.3986.")
    z.writestr("vintos-arousal-audit/data.bin", b"\x00\x01\x02" * 10)
check("OPEN lists a zip's files", "vintos-arousal-audit/report.md" in D.open_text(BUNDLE))
check("and reads a text file inside it", D.open_text(BUNDLE + ":vintos-arousal-audit/report.md") == "One reading in the window: arousal 0.3986.")
check("binary inside is named, not shown", D.open_text(BUNDLE + ":vintos-arousal-audit/data.bin").startswith("(binary"))
check("a folder lists its entries", "audit.zip" in D.open_text(WSP))
check("anything outside his folders is not opened", D.open_text("/etc/passwd").startswith("not opened")
      and D.open_text(os.path.join(HOME, "elsewhere.mp4")).startswith("not opened")
      and D.open_text(os.path.join(CLIPS, "..", "..", "..", "..", "elsewhere.mp4")).startswith("not opened"))
check("OPEN is one of his tools, run like the others", "audit.zip" in D.use_tools([("OPEN", WSP)]) and D.TOOL.match("OPEN: /x/y.zip")
      and "OPEN:" in D.RULES)
json.dump({"read_roots": [os.path.join(WSP, "memory")]}, open(D.CONFIG_FILE, "w"))
check("the folders he may read can be narrowed in his config", D.open_text(BUNDLE).startswith("not opened"))
os.remove(D.CONFIG_FILE)

# in the channel: the pass puts what he saw into the conversation he answers
SELF, DOT = "UVINTOS", D.DOT
class Slack:
    def __init__(self): self.msgs, self.posted, self.n = [], [], 100.0
    def add(self, user, text, files=None):
        self.n += 1; m = {"ts": "%.6f" % self.n, "user": user, "text": text}
        if files: m["files"] = files
        self.msgs.append(m); return m["ts"]
    def __call__(self, method, params):
        if method == "auth.test": return {"ok": True, "user_id": SELF}
        if method == "conversations.history": return {"ok": True, "messages": list(reversed(self.msgs))}
        if method == "chat.postMessage":
            self.posted.append(params); self.add(SELF, params["text"]); return {"ok": True, "ts": "%.6f" % self.n}
        raise AssertionError(method)
S = Slack(); S.n = 1500.0     # Slack timestamps after he starts listening
D.tick(api=S, think=lambda s, u: "x", fable=lambda s, u: "", now=1000, eyes=lambda m, who: "")
S.add(DOT, "Here is the clip.", files=vid["files"])
asked, prompts = [], []
D.tick(api=S, think=lambda s, u: (prompts.append(u), "Dot, the tide clip is good. Can you find two more like it?")[1],
       fable=lambda s, u: "", now=2000, eyes=lambda m, who: (asked.append(who), "[Dot posted a video. What your eyes saw:] Waves.")[1])
check("a pass looks at what dot posts", asked == ["Dot"], asked)
check("and he answers it with what he saw in front of him", prompts and "Waves." in prompts[0], prompts[:1])
row = [json.loads(l) for l in open(D.TRANSCRIPT)][-2]
check("the channel's own log keeps what he saw with the message", row["who"] == "dot" and "Waves." in row["text"], row)
n_asked = len(asked)
S.add(DOT, "Found one: <https://x.org/a.webm|Play video>")
D.tick(api=S, think=lambda s, u: "NOTHING", fable=lambda s, u: "", now=2500,
       eyes=lambda m, who: (asked.append("link"), "[Dot linked a video. What your eyes saw:] Ripples.")[1])
check("a message with only a link to a clip is looked at too", asked[n_asked:] == ["link"], asked)
asked[:] = ["Dot"]
check("a message with no files is not looked at", D.tick(api=S, think=lambda s, u: "NOTHING", fable=lambda s, u: "", now=3000,
                                                          eyes=lambda m, who: asked.append("again") or "") and asked == ["Dot"])
unit = open(os.path.join(REPO, "broker", "vintos-dot-channel.service")).read()
check("the service allows the minutes a video takes", "TimeoutStartSec=1800" in unit)
check("nothing reached the network", NET == [])

import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
