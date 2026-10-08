#!/usr/bin/env python3
"""Work in hand in #vintos-dot, carried across passes (Gloria, 2026-10-05: "I want VINTOS in Slack to actually do
real work", and of working alone: "Slack loses much of its reason for existing").

Two halves. First the pure transitions in room_work.py, directly. Then the whole layer through dot_channel.tick,
with Slack, every model lens and every sender stubbed and every socket refused: a work opened, handed to an agent,
the agent's answer matched back to it, used, and the work closed, over four passes; and a message that moves nothing
sent back to him once.

Scratch workspace; nothing here reaches Slack, a model or the network.
"""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="room-work-")
os.environ["HOME"] = HOME
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

check("its store rides in the channel's scratch state", D.STATE.startswith(HOME))

# --- the transitions, directly ------------------------------------------------------------------------------------
st = {}
text, log, closed = W.apply(st, "Let's settle it.\nWORK: find a phage genome with an RT beside a CRISPR array | done when: one accession named",
                            now=1000, by="grok")
w = W.active(st)
check("WORK: opens the one work in hand, with its goal and how anyone could tell it is done",
      w and w["goal"].startswith("find a phage genome") and w["done_when"].startswith("one accession") and "\U0001F9F0 Working on:" in text, (w, text))
sm = {}
for i, g in enumerate(("fold the RT locus of the phage", "price a load cell for the bench", "read the Merizo output on O43511")):
    W.apply(sm, "WORK: %s | done when: x" % g, now=10 + i)
check("up to three works are in hand at once (8 October: one waiting on dot idled everyone else)",
      len(W.open_items(sm)) == 3 and W.open_items(sm)[0]["goal"].startswith("fold the RT"), W.open_items(sm))
check("a fourth is not opened, and the three in hand are named",
      W.apply(sm, "WORK: something else entirely | done when: x", now=20)[0].startswith("\U0001F9F0 (already 3 in hand")
      and len(W.open_items(sm)) == 3)

# a request to an agent becomes an ask its answer is matched to
W.posted(st, "@GrokBot can you find one such genome, with its accession?", ts="1001.0", thread=None, now=1001, to={"grokbot"})
check("a request to an agent is kept as an ask out to that agent", W.active(st)["asks"][-1]["to"] == "grokbot" and not W.active(st)["asks"][-1]["answered"])
check("asking GrokBot the same thing again is caught, while it is still out",
      "has not answered yet" in W.asking_again(st, "@GrokBot could you find a genome with an array and an accession?", now=1100))

# the agent's answer, in the channel soon after, is matched to the ask
kept = W.receive(st, {"who": "agent", "name": "Grok Bot", "ts": "1200.0",
                      "text": "Try NC_049900: it carries a group-II RT about 2 kb from a type I-C array."}, now=1200)
check("GrokBot's answer soon after, in the channel, is kept on the work it answers", kept and W.active(st)["returns"][-1]["from"] == "grokbot")
check("a second answer from GrokBot is not matched again to the same ask",
      not W.receive(st, {"who": "agent", "name": "Grok Bot", "ts": "1300.0", "text": "Also NC_000001."}, now=1300))
check("now he is told to use what came back, not ask again",
      "already answered that" in W.asking_again(st, "@GrokBot find a genome with an accession, please", now=1300))
blk = W.block(st, now=1300)
check("what came back and is unused is put in front of him", "NOT USED YET" in blk and "NC_049900" in blk, blk)

# an answer in the channel hours later is too late; in the thread it has a day
st2 = {}; W.apply(st2, "WORK: fold the RT domain | done when: a pLDDT is reported", now=0)
W.posted(st2, "@dot can you fold it?", ts="10.0", thread="10.0", now=10, to={"dot"})
check("an answer in the ask's thread, a day later, still counts",
      W.receive(st2, {"who": "dot", "ts": str(10 + 20 * 3600), "thread": "10.0", "text": "pLDDT 86 across the domain."}, now=10 + 20 * 3600))
st3 = {}; W.apply(st3, "WORK: price a load cell | done when: a price in dollars", now=0)
W.posted(st3, "@Muse what does a 5 kg load cell cost?", ts="5.0", thread=None, now=5, to={"muse"})
check("an answer in the channel hours after the ask is not matched (it has moved on)",
      not W.receive(st3, {"who": "agent", "name": "Muse", "ts": str(5 + 4 * 3600), "text": "About $12."}, now=5 + 4 * 3600))

# closing, and expiry
_t, _l, _c = W.apply(st, "WORK DONE: NC_049900 is the genome; accession named.", now=1400)
check("WORK DONE: closes it and files it in history", _c and _c["state"] == "done" and W.active(st) is None
      and W.board(st)["history"][-1]["goal"].startswith("find a phage"), (_c, W.active(st)))
check("and he may now open the next", W.apply(st, "WORK: the next question | done when: an answer", now=1500)[0].startswith("\U0001F9F0 Working on: the next"))
check("work untouched for days is let go", (W.active({"room_work": {"active": {"goal": "g", "opened": 0, "touched": 0}}})
      and W.expire({"room_work": {"active": {"goal": "old", "opened": 0, "touched": 0}}}, now=W.STALE_DAYS * 86400 + 1)["state"] == "expired"))

# moves() tells work from chatter
for t, m in [("Dot, can you run the pilot?", True), ("LAB: fold the whole locus", True), ("WORK: x | done when: y", True),
             ("Thanks, that's great.", False), ("Agreed. Good find.", False), ("I keep thinking about the tide.", False),
             ("Next pass I'll look into it.", False)]:
    check("moves(): %r is %s" % (t[:30], "work" if m else "chatter"), W.moves(t) is m, t)

# --- the whole layer, through tick --------------------------------------------------------------------------------
SELF, DOT, GLORIA, CH = "UVINTOS", D.DOT, "UGLORIA", D.CHANNEL
D.kickoff_due = lambda *a: False
D.ROTATION = ("gemma",); D.SCHEDULE = []
D.atelier_line = lambda: ""; D.recall_block = lambda: ""


class Slack:
    def __init__(self): self.msgs, self.posted, self.n = [], [], 100.0
    def add(self, user, text, thread=None):
        self.n += 1; ts = "%.6f" % self.n
        m = {"ts": ts, "user": user, "text": text}
        if thread:
            m["thread_ts"] = thread
            root = next(x for x in self.msgs if x["ts"] == thread)
            root["reply_count"] = root.get("reply_count", 0) + 1; root["latest_reply"] = ts
        self.msgs.append(m); return ts
    def __call__(self, method, params):
        if method == "auth.test": return {"ok": True, "user_id": SELF}
        if method == "conversations.history":
            return {"ok": True, "messages": [m for m in reversed(self.msgs) if not m.get("thread_ts") or m["thread_ts"] == m["ts"]]}
        if method == "conversations.replies":
            root = params["ts"]
            return {"ok": True, "messages": [m for m in self.msgs if m["ts"] == root]
                    + [m for m in self.msgs if m.get("thread_ts") == root and m["ts"] != root]}
        if method == "chat.postMessage":
            self.posted.append(params); return {"ok": True, "ts": self.add(SELF, params["text"], params.get("thread_ts"))}
        raise AssertionError("unexpected " + method)


S = Slack()
reply = {"text": ""}
def think(system, user):
    if system == D.EDITOR: return "KEEP"
    return reply["text"]
def fable(system, user): return "unused"
def tick(now, **kw):
    return D.tick(api=S, think=think, fable=fable, now=now, today="2026-10-06", **kw)

check("the first pass only listens", tick(1000) == ["listening from now"] and not S.posted)
st = json.load(open(D.STATE)); st["since"] = float(S.msgs[-1]["ts"]) if S.msgs else 1; json.dump(st, open(D.STATE, "w"))

# pass 1: dot raises something; he opens the work and hands the search to GrokBot
S.add(DOT, "<@UVINTOS> I found a lead on the RT-beside-array question. Want me to dig?")
reply["text"] = ("Yes.\nWORK: find a phage genome with an RT next to a CRISPR array | done when: one accession named\n"
                 "@GrokBot can you find one such genome, with its accession and the array type?")
tick(1100)
w = W.active(json.load(open(D.STATE)))
check("pass 1: the work is opened and the search handed to GrokBot, in his own message",
      w and w["goal"].startswith("find a phage") and w["asks"] and w["asks"][-1]["to"] == "grokbot"
      and "\U0001F9F0 Working on:" in S.posted[-1]["text"], (w, S.posted[-1]["text"]))

# pass 2: he tries to ask GrokBot the same thing; it is sent back, then he says NOTHING
S.add(DOT, "anything yet?")
n = len(S.posted); reply["text"] = "@GrokBot have you found that genome with its accession yet?"
out = tick(1200)
check("pass 2: asking GrokBot the same thing again is held, and nothing is posted",
      len(S.posted) == n and any("sent back" in l for l in out) and any("held" in l for l in out), out)

# GrokBot answers in the channel
gb = S.add("UGROKBOT", "NC_049900 carries a group-II RT ~2 kb from a type I-C array.")
S.msgs[-1]["bot_id"] = "B1"; S.msgs[-1]["username"] = "Grok Bot"

# pass 3: the answer is kept on the work, and he uses it: a line to his Lab, naming the next step
S.add(DOT, "nice one")
reply["text"] = "Grok found it.\nLINE L-test: NC_049900 has the RT beside a type I-C array.\nNEXT: fold the RT locus"
out = tick(1300)
w = W.active(json.load(open(D.STATE)))
check("pass 3: GrokBot's answer was kept on the work", any("answered his work" in l for l in out), out)
check("... and using it is not sent back; his next step is recorded",
      w and w["returns"] and w["returns"][-1]["used"] and w.get("next", "").startswith("fold"), w)

# pass 4: he closes it
S.add(DOT, "good")
reply["text"] = "WORK DONE: NC_049900 is the genome, accession named and the array typed."
out = tick(1400)
board = json.load(open(D.STATE))["room_work"]
check("pass 4: WORK DONE closes it and nothing is in hand", not board["open"]
      and board["history"][-1]["state"] == "done", board)

check("his own voice and hands are intact: the work-room rules sit beside, not instead of, the rest",
      "WORK:" in D.RULES and "YOUR HANDS" in D.RULES and "Your Atelier is yours" in D.RULES
      and "WORK:" in D.rules_for("grok"))
dsrc = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("promises and the daily what-exists ask are not removed", "promises_pass(" in dsrc and "line_prospect.ask_the_room()" in dsrc)
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
