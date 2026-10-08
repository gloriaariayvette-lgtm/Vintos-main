#!/usr/bin/env python3
"""The editor is shown the channel, not his work board; and a message whose answer was held or dropped is answered
on the next pass (8 October: dot asked him at 11:46 whether midpoint stills fit Storycut; at 11:53 the editor dropped
his answer as "a completely new topic", because what it was shown ended in his work board; and with nothing new
after that, dot was never answered). Slack and every model are stubs; sockets are refused; scratch workspace."""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="editor-channel-"); os.environ["HOME"] = HOME
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
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:1500]) if d and not ok else ""))
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
QUESTION = "Storycut review text: six W1-W6 stills, plain cuts. Does midpoint extraction fit the W1-W6 stills you want?"
ANSWER = "Midpoint works for W1-W5. For W6, dot, take the still at 0:04 instead; the midpoint is a blur."
editor_saw, verdicts = [], []
def think(system, user):
    if system == D.EDITOR:
        channel = user.split("THE CHANNEL AND WHAT HE WAS TOLD:")[1].split("HIS DRAFT:")[0]
        editor_saw.append(channel)
        if verdicts:
            return verdicts.pop(0)
        return "TOPIC: yes\nTRUE: yes\nSENSE: yes\nKEEP" if "Storycut" in channel else \
               "TOPIC: no - Storycut was never discussed\nTRUE: yes\nSENSE: yes\nDROP: a completely new topic"
    if "Second question" in user.split("Your reply, as yourself")[0][-600:]:
        return "Second question first, dot: yes, the storyboard PNG should carry the hold times, W1 to W6, under each shot."
    return ANSWER
def tick(now): return D.tick(api=S, think=think, fable=lambda *a: "x", now=now, today="2026-10-08")

tick(5000)
st = json.load(open(D.STATE))
st["room_work"] = {"open": [{"id": "RW-752c6e84", "goal": "close one of the 4 unfinished Forge projects", "opened": 1, "touched": 1,
                             "asks": [], "returns": [], "steps": [], "paused_until": 10 ** 10, "pause_why": "budget 13/13 used"}],
                   "history": [], "goal": {"id": "RC-3607114b", "goal": "the Forge guard", "opened": 1, "touched": 1, "routes": []}}
json.dump(st, open(D.STATE, "w"))
S.n = 5100.0
S.add(D.DOT, QUESTION)
out = tick(5600)
check("the editor is shown the channel, with dot's question in it", editor_saw and "midpoint extraction" in editor_saw[0], editor_saw[:1])
check("and not his work board in its place", editor_saw and "YOUR WORK IN HAND" not in editor_saw[0])
check("so his answer to dot is kept and posted", S.posted and "0:04" in S.posted[-1]["text"], (out, S.posted))

S.add(D.DOT, "Second question: should the storyboard PNG carry the hold times?")
verdicts[:] = ["TOPIC: yes\nTRUE: no - unsure\nSENSE: yes\nDROP: held for a test"]
n = len(S.posted)
out = tick(6200)
check("an answer the editor drops is not posted", len(S.posted) == n and any("held back by the edit" in l for l in out), out)
check("and dot's message is owed again", any("owed again" in l for l in out), out)
out = tick(6800)
check("the next pass answers it, with nothing new in the channel", len(S.posted) == n + 1
      and any("owed from an earlier pass" in l for l in out), (out, S.posted[n:]))
verdicts[:] = ["DROP: again"] * 4
S.add(D.DOT, "Third: 720p or 1080p?")
tick(7400); out = tick(8000); out2 = tick(8600)
check("owed again once only, so a draft that keeps being dropped cannot loop", not any("owed again" in l for l in out2), (out, out2))
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
