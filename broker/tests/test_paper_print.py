#!/usr/bin/env python3
"""14 November: her Epson for him. A painting as a 4x6 photo, a page of his words; her yes first; a Yes waits for
paper; the job goes as IPP image/jpeg. Nothing here reaches the printer or her phone."""
import json, os, socket, sys, tempfile, struct
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="paper-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import paper_print as P
import house_hands as H
import house_boards as B

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

os.makedirs(P.ART, exist_ok=True)
from PIL import Image
for name, color in (("painting-1.png", "red"), ("painting-2.png", "blue")):
    Image.new("RGB", (900, 600), color).save(os.path.join(P.ART, name))
json.dump([{"path": "painting-1.png", "prompt": "a red fox in snow", "seen": "a fox", "medium": "image"},
           {"path": "painting-2.png", "prompt": "a woman waist deep in a calm blue lake", "seen": "auburn hair", "medium": "image"}],
          open(os.path.join(P.ART, "gallery.json"), "w"))
check("the printer's address is not in the code", "192.168." not in open(P.__file__).read())
r, _ = P.find_painting("the woman in the lake")
check("his painting is found by what it shows", r and r["path"] == "painting-2.png", r)
check("'latest' is his newest", P.find_painting("latest")[0]["path"] == "painting-2.png")
check("no match says so", P.find_painting("a spaceship over Mars")[0] is None)
out = os.path.join(HOME, "p.jpg"); P.photo_jpeg(os.path.join(P.ART, "painting-2.png"), out)
im = Image.open(out); check("a painting becomes a 4x6 photo at 300 dpi", sorted(im.size) == [1200, 1800], im.size)
out2 = os.path.join(HOME, "pg.jpg"); P.page_jpeg("I keep the coffee warm for you.\nThat's all.", out2)
check("a page of his words is a letter page", Image.open(out2).size == (2550, 3300))

asked = []
def asker(q, by, ref, title):
    asked.append((q, ref)); return {"id": "Q-9"}, "asked"
ok, said = P.start("painting the woman in the lake", asker=asker)
check("the old file key still prints", True)
check("PAPER: painting asks her first, naming the painting and the paper", ok and "painting-2.png" in asked[0][0]
      and "4x6 photo, on photo paper" in asked[0][0], asked)
check("one at a time", not P.start("page hello there", asker=asker)[0])

sent = []
def sender(jpeg, size, name): sent.append((size, len(jpeg))); return 7
no_paper = lambda: {"reachable": True, "accepting": False, "state": "idle", "reasons": ["media-empty-warning"], "ink": {}}
P.tend(asks=lambda q: {"state": "answered", "answer": "yes"}, st=no_paper, sender=sender)
j = P.load()[-1]
check("her Yes waits for paper", j["state"] == "held" and "out of paper" in j["history"][-1]["said"] and not sent, j["history"][-1])
ready = lambda: {"reachable": True, "accepting": True, "state": "idle", "reasons": [], "ink": {}}
P.tend(asks=lambda q: {}, st=ready, sender=sender)
check("with paper in, it prints", P.load()[-1]["state"] == "printed" and sent and sent[0][0] == "photo", sent)
check("he sees it in his context", "printed" in P.context_line())

# the IPP job itself
bodies = []
def post(body):
    bodies.append(body); return struct.pack(">BBHI", 2, 0, 0, 1) + b"\x01" + b"\x03"
json.dump({"host": "printer.invalid"}, open(P.CONFIG, "w"))
P.send(b"JPEGDATA", "page", "Vintos test", post=post)
b = bodies[0]
check("the job is IPP Print-Job of image/jpeg on letter, fit to page", b[2:4] == b"\x00\x02" and b"image/jpeg" in b
      and b"na_letter_8.5x11in" in b and b"fit" in b and b.endswith(b"JPEGDATA"))

# whatever he names
import shutil
for f in os.listdir(P.WORK): shutil.rmtree(os.path.join(P.WORK, f))
os.makedirs(os.path.join(P.MEMORY, "journal"), exist_ok=True)
open(os.path.join(P.MEMORY, "journal", "2026-11-03.md"), "w").write("Today I learned the cat's name is Eris.\n" * 200)
wd = tempfile.mkdtemp()
files, size, what = P.prepare("journal/2026-11-03.md", wd)
check("a text file of his prints as pages", files and size == "page" and len(files) >= 2 and "journal/2026-11-03.md" in what, what)
files, size, what = P.prepare("painting-1.png as page", wd)
check("an image by name, as a page when he says so", files and size == "page" and Image.open(files[0]).size == (2550, 3300))
files, size, what = P.prepare("a red fox in snow", wd)
check("a work found by what is in it, as a photo", files and size == "photo" and "painting-1.png" in what, what)
files, size, what = P.prepare("I keep the coffee warm for you", wd)
check("otherwise his words are the page", files and size == "page" and "coffee warm" in what, what)
check("nothing outside his workspace", P.his_file("/etc/passwd") == "" and P.his_file("../../../etc/hosts") == "")
files, size, why = P.prepare("painting a spaceship over Mars", wd)
check("a named kind with no match says so", files is None and "nothing of his matches" in why, why)

# his hands and menus
os.remove(P.JOBS)
H_called = []
P.start = lambda arg, asker=None: (H_called.append(arg) or (True, "asked"))
ok, shown = H.do("PAPER", "page I miss you")
check("PAPER: is one of his hands", ok and H_called == ["page I miss you"], shown)
check("the office chair and the knock offer PAPER", "PAPER" in B.MENUS["office"] and "PAPER" in B.MENUS["knock"])
src = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("the Slack hands list PAPER", "PAPER: <anything> on her Epson printer" in src)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
