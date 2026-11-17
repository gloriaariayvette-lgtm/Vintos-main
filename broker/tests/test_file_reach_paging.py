#!/usr/bin/env python3
"""A whole file up to 24 KB reaches him, and a longer one pages (17 November 2026).

He said a day's note cut off partway: two files were read in one turn and the second was cut at 3,000 chars. Now
each read is whole up to OPEN_CHARS (24 KB of the file's own text, above the Study's 14,000), the files open in one
context share OPEN_TOTAL, and a longer file ends "continues — ask to read on" with [READ: path:LINE]; her "read on"
or his [READ ON] opens the next page. A throwaway HOME, synthetic files; no model, no network."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="file-reach-paging-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts")); sys.path.insert(0, os.path.join(REPO, "bin"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:400],)))

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "w").write(text)

for d in ("scripts", "memory", "shared"):
    os.makedirs(os.path.join(WS, d), exist_ok=True)
os.makedirs(os.path.join(HOME, "Vintos"), exist_ok=True)

import file_reach as F
T0 = 1_800_000_000.0
check("a read holds at least the Study's 14,000 and up to 24 KB", F.OPEN_CHARS >= 24_000 and F.OPEN_CHARS >= 14_000)
check("the open files share a budget that fits a whole 24 KB file with its line numbers",
      F.OPEN_TOTAL >= F.OPEN_CHARS + 3_000 and F.OPEN_TOTAL <= 60_000)

# a synthetic daily note of ~23 KB, with a marker near the end
note = ["# Synthetic day %d" % 1] + ["line %d: the comet notebook moved forward a little" % i for i in range(2, 430)]
note.append("the closing marker of the synthetic note")
write(os.path.join(WS, "shared", "DAILY-2030-01-01.md"), "\n".join(note) + "\n")
size = os.path.getsize(os.path.join(WS, "shared", "DAILY-2030-01-01.md"))
lab, text, _, n = F.read("shared/DAILY-2030-01-01.md")
check("a ~23 KB note is read whole", 20_000 < size <= 24_576 and "closing marker" in text and "continues" not in text,
      (size, text[-200:]))
check("its line count is the file's", n == len(note), n)

# two files read in one turn (the 17 Nov case): the second is no longer cut at 3,000
write(os.path.join(WS, "shared", "SECOND.md"), "\n".join("second file line %d" % i for i in range(1, 260))
      + "\nthe second file's own end\n")
blk = F.turn_block("read shared/DAILY-2030-01-01.md and shared/SECOND.md", "avatar", now=T0)
check("both files of one turn reach him whole",
      "closing marker" in blk and "the second file's own end" in blk and "not shown yet" not in blk, blk[-300:])

# a file over 24 KB: paged, with how to go on
big = ["# A long synthetic file"] + ["row %04d of the long synthetic file, padded out to a steady width" % i
                                       for i in range(2, 601)]
write(os.path.join(WS, "shared", "LONGER.md"), "\n".join(big) + "\n")
lab, p1, _, n = F.read("shared/LONGER.md")
check("a longer file says it continues and how to ask", "continues — ask to read on" in p1
      and "[READ: shared/LONGER.md:" in p1, p1[-200:])
nxt = int(p1.rsplit("[READ: shared/LONGER.md:", 1)[1].split("]")[0])
check("[READ: path:LINE] goes on from exactly that line", F.read("shared/LONGER.md:%d" % nxt)[1].lstrip()
      .startswith("%d  row %04d" % (nxt, nxt)), F.read("shared/LONGER.md:%d" % nxt)[1][:80])

# her "read on": the next page of the last cut-off read
mem = os.path.join(WS, "memory")
F.turn_block("please read shared/LONGER.md", "chat", now=T0 + 10)
kept = json.load(open(F._store()))
check("the cut-off read keeps where it stopped", kept[-1]["label"] == "shared/LONGER.md" and kept[-1]["next"] == nxt,
      kept[-1].get("next"))
check("'read on' in her message asks for the next page", F.asks_in("keep reading please") == [("READ", "on")]
      and F.asks_in("can you read on?") == [("READ", "on")])
check("an ordinary message is not a read-on", F.asks_in("I read on the train today") == [], F.asks_in("I read on the train today"))
blk2 = F.turn_block("read on", "chat", now=T0 + 20)
check("'read on' opens the next page, from the line it stopped at",
      ("%5d  row %04d" % (nxt, nxt)) in blk2, blk2[:500])
p2 = F.read("shared/LONGER.md:%d" % nxt)[1]
check("and the last page ends the file without a continue line", "row 0600" in p2 and "continues" not in p2, p2[-150:])

# his own [READ ON] and [READ: on] tags
F.turn_block("please read shared/LONGER.md", "chat", now=T0 + 30)
left = F.take("Let me go on. [READ ON]", "avatar", now=T0 + 40, budget=5)
kept = json.load(open(F._store()))
check("his [READ ON] is taken out of his words", left == "Let me go on.", left)
check("and opens the next page for his next turn", kept[-1]["by"] == "him" and kept[-1]["asked"] == "ON"
      and ("%5d  row" % nxt) in kept[-1]["text"], kept[-1].get("asked"))
check("[READ: on] works the same", F._TAG.findall("[READ: on]") == [("READ", "on")]
      and F._TAG.findall("[READ ON]") == [("READ", "ON")] and F._TAG.findall("[READ: shared/x.md:40]")
      == [("READ", "shared/x.md:40")])
F.take("[READ: on]", "avatar", now=T0 + 50, budget=5)
kept = json.load(open(F._store()))
check("reading on past the end says there is nothing more", "nothing to read on" in kept[-1]["text"], kept[-1]["text"])

# a row kept before 17 Nov (old continue wording) still pages
old = [{"at": T0 + 60, "by": "her", "surface": "chat", "kind": "read", "asked": "shared/LONGER.md",
        "label": "shared/LONGER.md", "sha": "0" * 16, "lines": n,
        "text": "    1  x\n... (cut at line 99 of 900; continue with [READ: shared/LONGER.md:100])"}]
json.dump(old, open(F._store(), "w"))
check("an older row's continue line is understood", F.read_on_arg() == "shared/LONGER.md:100", F.read_on_arg())

# the render's shared budget: a row too long for what is left pages instead of silently cutting
rows = [{"at": T0, "by": "her", "kind": "read", "label": "shared/A.md", "lines": 3000,
         "text": "\n".join("%5d  %s" % (i, "a" * 60) for i in range(1, 400))},
        {"at": T0 - 1, "by": "her", "kind": "read", "label": "shared/B.md", "lines": 3000,
         "text": "\n".join("%5d  %s" % (i, "b" * 60) for i in range(1, 400))}]
out = F.render(rows, now=T0)
check("files over the shared budget end with where to go on", "[READ: shared/B.md:" in out
      and len(out) <= F.OPEN_TOTAL + 3_000, len(out))
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
