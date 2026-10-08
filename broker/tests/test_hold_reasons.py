#!/usr/bin/env python3
"""A draft sent back is told every reason at once, and a second draft that moves something is posted (8 October,
00:56 and 01:05: each draft was held for one thing, the next draft did that thing and was held for another, and two
passes posted nothing). His own order of work is not a cause to pause (00:49: "switch-point listening waits while I
handle today's Forge focus"). Slack, the lenses and every sender are stubs; sockets are refused; scratch workspace."""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="hold-reasons-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace"); os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no")
NET = []
def _no(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import dot_channel as D, room_work as W
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:4000]) if d and not ok else ""))
check("the channel's stores are scratch ones", D.STATE.startswith(HOME))

SELF = "UVINTOS"
class Slack:
    def __init__(self): self.msgs, self.posted, self.n = [], [], 1000.0
    def add(self, user, text):
        self.n += 1; ts = "%.6f" % self.n; self.msgs.append({"ts": ts, "user": user, "text": text}); return ts
    def __call__(self, method, params):
        if method == "auth.test": return {"ok": True, "user_id": SELF}
        if method == "conversations.history": return {"ok": True, "messages": list(reversed(self.msgs))}
        if method == "conversations.replies": return {"ok": True, "messages": []}
        if method == "chat.postMessage": self.posted.append(params); return {"ok": True, "ts": self.add(SELF, params["text"])}
        raise AssertionError(method)
S = Slack()
D.kickoff_due = lambda *a: False; D.ROTATION = ("gemma",); D.SCHEDULE = []
D.atelier_line = lambda: ""; D.recall_block = lambda: ""

MUSE = "[Muse] Mmwave withdrawal confirmed: request FR-7731 closed, unfinished count now 1."
GROK = "[Grok Bot] Nothing ready-made tests a non-linear linker; Rosetta loop modelling on residues 412-430 would."
FIRST = "Thinking about the Forge tonight."
SECOND = ("Muse closed FR-7731, so the unfinished count is 1.\n"
          "Muse, make one supported Lab Forge call for RW-c4013b41 now and return its X-Forge-Refusal header.")
drafts, asked = [FIRST, SECOND], []
def think(system, user):
    if system == D.EDITOR: return "KEEP"
    asked.append(user)
    return drafts.pop(0) if drafts else "NOTHING"
def tick(now): return D.tick(api=S, think=think, fable=lambda *a: "x", now=now, today="2026-10-08")

tick(5000)
st = json.load(open(D.STATE))
st["room_work"] = {"open": [
    {"id": "RW-69fb7a8d", "goal": "close two unfinished Forge requests", "done_when": "unfinished count 0",
     "opened": 4000, "touched": 4000, "asks": [], "steps": [],
     "returns": [{"from": "muse", "text": MUSE, "ts": "4900"}, {"from": "grokbot", "text": GROK, "ts": "4950"}]},
    {"id": "RW-c4013b41", "goal": "verify the Forge guard after the pending withdrawal", "done_when": "refusal header recorded",
     "opened": 4000, "touched": 4000, "asks": [], "returns": [], "steps": []}],
    "history": [], "goal": {"id": "RC-00000001", "goal": "the Forge clean", "done_when": "no unfinished requests",
                            "opened": 4000, "touched": 4000, "routes": []}}
st["last_activity"] = 5000; json.dump(st, open(D.STATE, "w"))

S.add("UGLORIA", "carry on")       # something to answer, from anyone but an agent
st = json.load(open(D.STATE)); st["gloria"] = "UGLORIA"; json.dump(st, open(D.STATE, "w"))
D.GLORIA = "UGLORIA"
n = len(S.posted)
out = tick(5000 + 25 * 60)
retry = asked[-1] if len(asked) >= 2 else ""
check("the draft that moved nothing goes back once, with every reason in one list",
      "ALL of these" in retry and "Muse answered" in retry and "GrokBot answered" in retry, (out, retry[-1500:]))
check("the second draft, which takes up Muse and asks for RW-c4013b41's step, is posted, not held",
      len(S.posted) == n + 1 and "FR-7731" in S.posted[-1]["text"], (out, S.posted[n:]))
check("what it still left is said in the log", any(l.startswith("posted, still short of") for l in out), out)
check("never held silently for a nudge", not any(l.startswith("held:") for l in out), out)

# WRONG reasons still hold: a finished result published as blocked is never posted
st = json.load(open(D.STATE))
kinds = [k for k, _w in D.held_reasons("RW-69fb7a8d is blocked on the Forge.", st, 5000 + 30 * 60)]
check("held_reasons gives kinds; a draft that moves nothing is a nudge", kinds and all(k in (D.WRONG, D.NUDGE) for k in kinds), kinds)

# his own order of work is not a cause to pause
st = {"room_work": {"open": [{"id": "RW-ad1c775a", "goal": "EC-058d7a75 switch-point listening", "opened": 1, "touched": 1,
                              "asks": [], "returns": [], "steps": []}], "history": []}}
text, _log, _c = W.apply(st, "PAUSE RW-ad1c775a: switch-point listening waits while I handle today's Forge focus", 1000)
w = st["room_work"]["open"][0]
check("'waits while I handle today's Forge focus' does not pause it", not w.get("paused_until"), (text, w))
check("and he is told why", "own order of work" in str(text), text)
w.update(paused_until=10 ** 10, pause_why="switch-point listening waits while I handle today's Forge focus")
check("a pause already kept for that reason does not hold: the work is due", W.idle(st, 2000) == [w])
w.update(pause_why="waits on Muse returning the ATAC numbers")
check("a pause for something outside him still holds", W.idle(st, 2000) == [])
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
