#!/usr/bin/env python3
"""What another agent already answered, her No, the settled list's size, and file reads (Gloria, 18 October).
- The same question to another agent after one answered it is sent back with that answer to weigh: it does not close
  anything, and a NEW: line with what is different lets it through.
- Her No from her phone settles the topic like her word in the channel.
- The settled list keeps every closure that has not expired, not the last 24.
- A file read again within a week, unchanged, is answered from what he read before.
Scratch workspace; nothing reaches Slack, a model or the network."""
import json, os, socket, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="room-answers-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no-secrets")
sys.path.insert(0, os.path.join(REPO, "scripts"))
NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
import room_work as W
import dot_channel as D
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
check("every store is scratch", D.STATE.startswith(HOME) and D.READS.startswith(HOME))

st = {}
W.apply(st, "WORK: find a piezo sensor for the bench | done when: one part named", now=1000)
W.posted(st, "<@dot> can you find a piezo sensor for the bench, with a part number?", ts="1001.0", thread=None, now=1001, to={"dot"})
W.receive(st, {"who": "dot", "ts": "1100.0", "text": "Parked: no piezo sensor fits the bench without a new mount."}, now=1100)
again = W.asking_again(st, "@GrokBot can you find a piezo sensor for the bench, with a part number?", now=1200)
check("the same question to Grok Bot after dot answered: dot's answer is put in front of him to weigh",
      "dot already answered this" in again and "no piezo sensor fits" in again and "change the want or the fix" in again, again)
check("... and it closes nothing: the work is still in hand", W.active(st) and W.active(st)["goal"].startswith("find a piezo"))
check("with what is different on a NEW: line, the other agent may be asked",
      W.asking_again(st, "@GrokBot can you find a piezo sensor for the bench, with a part number?\nNEW: the mount is printed now", now=1200) == "")
check("a different question to Grok Bot is not held", W.asking_again(st, "@GrokBot what load cell fits a 3D-printed arm?", now=1200) == "")

for i in range(40):
    W.settle(st, "topic number %d about thing%d" % (i, i), "x", "vintos", now=2000 + i)
check("forty standing closures are all kept (24 used to push the oldest out early)", len(W.settled(st, 2100)) >= 40)
check("an expired closure is dropped", all(e["until"] > 2000 + 39 for e in W.board(st)["settled"]))

src = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("her No from her phone settles the topic", 'Gloria (?:answered NO: |said NO to buying )' in src and 'room_work.settle(state, no.group(1)' in src)

os.makedirs(os.path.join(HOME, ".vintos", "workspace", "memory"), exist_ok=True)
f = os.path.join(HOME, "comparison.json"); open(f, "w").write('{"msg": "line 4, column 1, character 101"}')
D.allowed = lambda p: f if p.strip() == "comparison.json" else None
D.open_text = lambda arg, cap=None: open(f).read()
first = D.use_tools([("OPEN", "comparison.json")])
second = D.use_tools([("OPEN", "comparison.json")])
check("the first read reads the file", "character 101" in first and "ALREADY READ" not in first, first)
check("the same file, unchanged, is answered from what he read before", "ALREADY READ" in second and "character 101" in second, second)
time.sleep(0.01); open(f, "w").write('{"msg": "changed"}'); os.utime(f, (time.time() + 5, time.time() + 5))
third = D.use_tools([("OPEN", "comparison.json")])
check("a changed file is read again", "ALREADY READ" not in third and "changed" in third, third)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
