#!/usr/bin/env python3
"""The projector's media server serves one media file by its path, and nothing else.

No directory listing, nothing hidden, nothing that is not media, nothing outside the art
store; ranged requests still get 206 (cast receivers will not play video without it).
Requests go over a socketpair: no port is opened, no network is touched.
"""
import io, os, socket, sys, tempfile, threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTD = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="scenes-")
os.environ["HOME"] = TMP
ART = os.path.join(TMP, "art"); os.makedirs(os.path.join(ART, "video")); os.makedirs(os.path.join(ART, ".private"))
os.environ["VINTOS_SCENES_ROOT"] = ART
sys.path.insert(0, os.path.join(ROOTD, "scripts"))
import scenes_server as SS

open(os.path.join(ART, "video", "wall.mp4"), "wb").write(b"0123456789")
open(os.path.join(ART, "poem.md"), "w").write("words")
open(os.path.join(ART, ".private", "x.png"), "wb").write(b"png")
open(os.path.join(TMP, "outside.png"), "wb").write(b"png")

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:110]) if d else ""))

check("the suite serves its own scratch, not his art", os.path.realpath(SS.ROOT) == os.path.realpath(ART), SS.ROOT)

def get(path, rng=None):
    a, b = socket.socketpair()
    req = "GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n%s\r\n" % (path, ("Range: %s\r\n" % rng) if rng else "")
    a.sendall(req.encode())
    class S: pass
    t = threading.Thread(target=lambda: SS.H(b, ("127.0.0.1", 0), S())); t.start(); t.join(5)
    a.shutdown(socket.SHUT_WR); data = b""
    a.settimeout(2)
    try:
        while True:
            c = a.recv(65536)
            if not c: break
            data += c
    except socket.timeout: pass
    a.close(); b.close()
    status = data.split(b"\r\n", 1)[0].decode(errors="replace")
    return status, data.split(b"\r\n\r\n", 1)[-1]

s, body = get("/video/wall.mp4")
check("a media file by its path is served", " 200 " in s and body == b"0123456789", s)
s, body = get("/video/wall.mp4", "bytes=2-4")
check("a byte range gets 206 and only those bytes", " 206 " in s and body == b"234", (s, body))
for path, why in (("/", "the root is not listed"), ("/video/", "a directory is not listed"),
                  ("/poem.md", "a non-media file is not served"), ("/.private/x.png", "a hidden path is not served"),
                  ("/../outside.png", "nothing outside the art store")):
    s, body = get(path)
    check(why, " 404 " in s and b"wall.mp4" not in body, s)

src = open(os.path.join(ROOTD, "broker", "vintos-scenes.service")).read()
check("the unit runs the deployed copy, not a hand-placed one", "%h/.vintos/workspace/scripts/scenes_server.py" in src)
dep = open(os.path.join(ROOTD, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs it", "scenes_server.py" in dep and "vintos-scenes" in dep)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
