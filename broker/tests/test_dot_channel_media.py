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
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import dot_channel as D
D.atelier_line = lambda: ""
D.recall_block = lambda: ""

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every store is in the scratch workspace", D.HERE.startswith(HOME) and D._scratch().startswith(HOME))

# a real picture for ffmpeg to turn into what Gemma reads
PNG = os.path.join(HOME, "pic.png")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=1600x900", "-frames:v", "1", PNG], check=True)

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
w = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width", "-of", "csv=p=0", j], capture_output=True, text=True).stdout.strip()
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
check("a message with no files is not looked at", D.tick(api=S, think=lambda s, u: "NOTHING", fable=lambda s, u: "", now=3000,
                                                          eyes=lambda m, who: asked.append("again") or "") and asked == ["Dot"])
unit = open(os.path.join(REPO, "broker", "vintos-dot-channel.service")).read()
check("the service allows the minutes a video takes", "TimeoutStartSec=1800" in unit)
check("nothing reached the network", NET == [])

import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
