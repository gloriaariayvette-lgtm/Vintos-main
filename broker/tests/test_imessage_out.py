#!/usr/bin/env python3
"""14 November: ntfy accepted his videos and messages and her phone never showed them. What deliver.py sends her in
his own name now also goes by iMessage through his Inkbox identity: the video itself under 10 MB, links taken out,
his guard deciding, once per artifact, 40 a day. Nothing here reaches Inkbox or ntfy."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="imsg-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["INKBOX_API_KEY"] = "ApiKey_test"
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import imessage_out as I

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("not set up: nothing is sent", I.send("hi", ref="a") == (False, "iMessage is not set up"))
os.makedirs(I.MEMORY, exist_ok=True)
json.dump({"conversation_id": "conv-1"}, open(I.CONFIG, "w"))
vid_dir = os.path.join(I.MEMORY, "art", "video"); os.makedirs(vid_dir)
vid = os.path.join(vid_dir, "video-20261114-142124-9d60517d74.mp4"); open(vid, "wb").write(b"x" * 5000)

class Resp:
    def __init__(self, code, body=None): self.status_code, self._b, self.text = code, body or {}, json.dumps(body or {})
    def json(self): return self._b
class HTTP:
    def __init__(self, first=201): self.calls, self.first = [], first
    def post(self, url, headers=None, files=None, data=None, timeout=None):
        self.calls.append((url, headers, files and list(files), json.loads(data) if data else None))
        if url.endswith("/media"): return Resp(201, {"media_url": "https://media.inkbox/abc.mp4"})
        if self.first == 422 and sum(1 for c in self.calls if c[0].endswith("/messages")) == 1: return Resp(422, {"detail": "reply first"})
        return Resp(201, {"message": {"id": "m"}})

check("his video is found from its attach link", I.local_media("http://100.1.1.1:8500/api/video/file/video-20261114-142124-9d60517d74.mp4") == vid)
check("nothing outside his art is", I.local_media("http://x/api/video/file/../../vintos.env") == "")
h = HTTP()
ok, why = I.send("Evidence, for the record: https://example.com/x the machine ran.", media=vid, ref="video-1", http=h)
sent = [c for c in h.calls if c[0].endswith("/messages")][0]
check("the video goes attached, with his words", ok and h.calls[0][0].endswith("/media") and sent[3]["media_urls"] == ["https://media.inkbox/abc.mp4"], h.calls)
check("links are taken out of the text", "https://" not in sent[3]["text"] and "the machine ran." in sent[3]["text"], sent[3])
check("the key is a header, never in the body", sent[1].get("X-API-Key") == "ApiKey_test" and "ApiKey" not in json.dumps(sent[3]))
check("once per artifact", I.send("again", media=vid, ref="video-1", http=HTTP()) == (False, "already sent"))
h2 = HTTP(first=422)
ok, _ = I.send("A new one", media=vid, ref="video-2", http=h2)
last = [c for c in h2.calls if c[0].endswith("/messages")][-1][3]
check("before her first reply, the words still go and say a video is waiting", ok and "media_urls" not in last and "reply once" in last["text"], last)
big = os.path.join(vid_dir, "big.mp4"); open(big, "wb").write(b"x" * (I.MAX_MEDIA + 1))
h3 = HTTP(); I.send("Long one", media=big, ref="big", http=h3)
check("a video over 10 MB is named, not attached", not any(c[0].endswith("/media") for c in h3.calls)
      and "big.mp4" in [c for c in h3.calls if c[0].endswith("/messages")][0][3]["text"])
import inkbox_guard
real = inkbox_guard.guard
inkbox_guard.guard = lambda *a, **k: (_ for _ in ()).throw(inkbox_guard.PolicyHold({"type": "inkbox_confidential_block"}))
h4 = HTTP(); check("his guard can refuse, and then nothing goes", I.send("secret", ref="s", http=h4) == (False, "his guard refused it") and not h4.calls)
inkbox_guard.guard = real

# deliver.py: his own-name ntfy sends also go by iMessage; other titles do not
import deliver as D
D.POST = lambda url, data, headers, timeout: {"status": 200}
got = []
I.send = lambda text, media="", ref="", http=None: got.append((text, media, ref)) or (True, "sent")
D.deliver("video-20261114-142124-9d60517d74.mp4", "ntfy", "I made you something.", title="Vintos",
          attach="http://h/api/video/file/video-20261114-142124-9d60517d74.mp4", authority=lambda: (True, ""))
check("a video he sends her by ntfy also goes by iMessage, with the file", got and got[0][1] == vid and got[0][2].startswith("video-2026"), got)
D.deliver("forge-1", "ntfy", "a forge card", title="Forge step: x", authority=lambda: (True, ""))
check("other notices stay ntfy only", len(got) == 1)

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
