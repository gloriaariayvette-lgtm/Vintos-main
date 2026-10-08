#!/usr/bin/env python3
"""What the room settled stays settled, a claim matches its receipt, arranged is not delivered, and a pause holds
every send (Gloria, 2026-10-05: "I can't keep manually carrying every decision between his model turns and Slack
messages"). Cases from dot's record of 4 and 5 October:

  1. a model handoff cannot reopen the RSVP he dropped, or Gloria's "no more plan making for Eve" while it stands;
  2. a settled sensor topic, repeated without new evidence, starts no search and no phone ask;
  3. WORK DONE clears the work it closes, even in a message that names that work again;
  4. a quota refusal cannot be claimed as queued, and live means live in the Study's record;
  5. a failed generation keeps its work, and the same make is never started twice;
  6. a scheduled song stays owed until it is delivered;
  7. a pause holds every channel send, delayed results too, and keeps what came in for after.

Scratch HOME and workspace; Slack, her phone and every model are stubs; every socket is refused (a loopback
attempt, to the Forge's local service, is refused too; only an outside one fails the suite).
"""
import json, os, socket, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="workflow-holds-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no-secrets")
os.environ["VINTOS_STUDY_WORKBENCH"] = os.path.join(HOME, "workbench")
os.environ["VINTOS_CHECKOUT"] = os.path.join(HOME, "Vintos-main")
os.environ.pop("ANTHROPIC_API_KEY", None)
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX and not str((a[0] if a else ("",))[0]).startswith("127."): NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import room_work as RW
import dot_channel as D
import gloria_asks as G
import study_fix as SF
import make_thing as MT
import house_hands as HH
import promise_keeper as PK

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

PUSHES = []
G.notify = lambda row, send=None: PUSHES.append(row) or True          # her phone is a stub
check("every store is a scratch one, and her phone is a stub",
      all(p.startswith(HOME) for p in (D.STATE, D.HELD_POSTS, G.STORE if hasattr(G, "STORE") else HOME, SF.QUEUE, MT.MADE, PK.STORE))
      and G.notify.__name__ == "<lambda>")

T0 = 1_760_000_000.0

# --- 3. WORK DONE clears the work it closes --------------------------------------------------------------------------
st = {}
RW.apply(st, "WORK: the Felt Edge song | done when: the audio is made and reaches Gloria", T0)
text, log, closed = RW.apply(st, "WORK: the Felt Edge song, finished\nWORK DONE: made and sent: art/music/felt-edge.mp3", T0 + 60)
check("a message that closes its work and names it again clears it", RW.active(st) is None and closed
      and "✅ Work done" in text and "still working on" not in text and "finish it with WORK DONE" not in text, (text, RW.active(st)))
text, log, closed = RW.apply(st, "WORK: map the mmWave intake | done when: a reading arrives on Aegis", T0 + 120)
text, log, closed = RW.apply(st, "WORK DONE: spec written to docs/mmwave-intake-spec.md\nWORK: wire the mmWave reader to the intake | done when: a reading lands", T0 + 180)
check("... and the next work it opens is opened after the close", closed and RW.active(st)
      and RW.active(st)["goal"].startswith("wire the mmWave reader"), RW.active(st))

# --- 6. a scheduled song stays owed until it is delivered ------------------------------------------------------------
st = {}
RW.apply(st, "WORK: Felt Edge, the song | done when: its audio exists and reaches Gloria", T0)
text, log, closed = RW.apply(st, "WORK DONE: scheduled for 7am tomorrow", T0 + 60)
check("work closed as 'scheduled' stays in hand", RW.active(st) and closed is None and "Not done yet" in text
      and "arranged is not delivered" in text, text)
check("... and his next pass reads it as still owed", "arranged, not delivered" in RW.block(st, T0 + 120))
text, log, closed = RW.apply(st, "WORK DONE: Felt Edge is made and sent to her, art/music/felt-edge.mp3", T0 + 3600)
check("... and closes once it exists and was delivered", RW.active(st) is None and closed["state"] == "done")
pk = PK.load(); pk["items"] = [{"id": "P-1", "thread": "T-song", "state": "open", "quote": "a song for you by morning",
                                "at": "19:30"}]; PK.save(pk)
check("a promise DONE that is only scheduled leaves the promise open",
      PK.resolve("T-song", "DONE: scheduled for the morning") is None and PK.load()["items"][0]["state"] == "open"
      and "arranged, not yet made" in PK.block())
check("... and a real DONE ends it", PK.resolve("T-song", "DONE: W12, Felt Edge, sent to her") is not None)

# --- 1. a model handoff cannot reopen what was settled ---------------------------------------------------------------
st = {}
RW.apply(st, "WORK: find the Saturday lecture listing and RSVP for Eve | done when: RSVP sent", T0)
RW.apply(st, "WORK DROPPED: not this week", T0 + 60)
draft = "@dot can you find the listing for the Saturday lecture again so I can RSVP for Eve?"   # Opus, hours later
held = D.sent_back(draft, st, T0 + 4 * 3600)
check("another model's draft that reopens the dropped RSVP is sent back", "settled this" in held, held)
check("... and every lens reads what is settled before it writes", "== SETTLED" in RW.block(st, T0 + 4 * 3600)
      and "RSVP" in RW.block(st, T0 + 4 * 3600))
check("... talking about it is never held", RW.reopens(st, "I keep thinking about Eve's Saturday lecture.", T0 + 4 * 3600) == "")
check("... a NEW: line with what changed lets his own settled work open again",
      RW.reopens(st, "NEW: the venue moved the lecture to Sunday\n@dot find the Sunday lecture listing for Eve, RSVP?", T0 + 4 * 3600) == "")
check("... and after a week it is no longer held", D.sent_back(draft, st, T0 + 8 * 86400) == "")
st = {}
RW.gloria_closes(st, "No more plan making for Eve for the next week. Work on something else.", T0)
check("Gloria's 'no more plan making for Eve for the next week' is kept for a week",
      RW.settled(st, T0) and RW.settled(st, T0)[0]["words"] == ["eve"] and RW.settled(st, T0 + 6 * 86400)
      and not RW.settled(st, T0 + 8 * 86400), RW.settled(st, T0))
check("... no model can reopen it, not even with NEW:", "Gloria closed this" in D.sent_back(
      "NEW: I found a better date\nASK GLORIA: should I RSVP to Eve's Saturday lecture?", st, T0 + 3600))
check("... her ordinary 'don't' closes nothing", RW.gloria_closes({}, "Don't talk about number 4.", T0) is None)

# --- 2. a settled sensor topic starts no search and no phone ask -----------------------------------------------------
st = {}
RW.apply(st, "WORK: choose a piezo pressure sensor for the rig | done when: she has a part to buy", T0)
RW.apply(st, "WORK DROPPED: she has the mmWave sensor; the piezo is not needed", T0 + 60)
SEARCHED = []
got = D.use_tools([("SEARCH", "piezo pressure sensor kit price")], search=lambda q: SEARCHED.append(q) or [],
                  hold=lambda q: D._settled_why(st, q, T0 + 3600))
check("a search on the settled sensor is not run", not SEARCHED and "not searched" in got, got)
check("... and his draft asking her again is sent back", "settled this" in D.sent_back(
      "ASK GLORIA: should Muse find a piezo pressure sensor for the rig?", st, T0 + 3600))
row, said = G.ask("Should I buy the piezo pressure sensor kit for the rig?", by="muse", send=lambda *a, **k: None)
G.decide(row["id"], "no")
again, said2 = G.ask("Can I buy a piezo pressure sensor kit for the rig now?", by="vintos")
check("a decision she already gave is not put to her phone again in other words", again is None
      and "already answered" in said2 and len(PUSHES) == 1, (said2, len(PUSHES)))

# --- 4. a quota refusal cannot be claimed as queued ------------------------------------------------------------------
for i in range(SF.PER_DAY):
    SF.request("fix number %d: the parser drops the second field of the record" % i)
row, why = SF.request("parser diagnostics: log the line that failed and why, in faults.jsonl")
check("the Study refuses past the day's three", row is None and "used" in why)
check("a claim that it is queued, with no receipt, is sent back",
      "without naming its receipt" in SF.claim_check("The parser diagnostics fix is queued in the Study."))
check("... and so is a receipt the Study does not hold", "not in the Study's record" in
      SF.claim_check("SF-0badc0de is queued in the Study."))
real = SF._load()[0]["id"]
check("... and live is claimed only of a fix that is live", "not deployed or verified yet" in
      SF.claim_check("%s is deployed and live in the Study." % real) and SF.claim_check("%s is queued in the Study." % real) == "")
st = {"study_refused": [{"day": "2026-10-05", "what": "parser diagnostics", "why": "today's 3 Study fixes are used"}]}
blk = D.study_block(st, "2026-10-05")
check("his next pass reads the Study's record and today's refusal", real in blk and "never queued" in blk, blk)

# --- 5. a failed generation keeps its work; the same make never starts twice -----------------------------------------
LAUNCHED = []
ok, said = HH.make("song Felt Edge | slow piano, brushed snare", run=lambda cmd, env: LAUNCHED.append(cmd))
check("a song's '| style' is part of what to make, not an image path", ok and LAUNCHED
      and LAUNCHED[0][-1] == "Felt Edge | slow piano, brushed snare", (said, LAUNCHED))
ok, said = HH.make("video the tide coming in | /no/such/still.png", run=lambda cmd, env: LAUNCHED.append(cmd))
check("... a video's '| path' is still its image, and checked", not ok and "no file" in said)
MT._note("song", "Felt Edge | slow piano, brushed snare", False, "started", rid="r1", running=True)
ok, said = HH.make("song Felt Edge | slow piano, brushed snare", run=lambda cmd, env: LAUNCHED.append(cmd))
check("the same make while it is still running is not started again", not ok and "already making" in said
      and len(LAUNCHED) == 1, said)
MT._note("song", "Felt Edge | slow piano, brushed snare", False, "the tool stopped", rid="r1")
st = {}
RW.apply(st, "WORK: Felt Edge, the song | done when: its audio reaches her", T0)
RW.apply(st, "MAKE: song Felt Edge | slow piano", T0 + 60)
check("a failed generation leaves the work in hand", RW.active(st) and RW.active(st)["goal"].startswith("Felt Edge"))
check("... and once ended it may be tried again", MT.running("song", "Felt Edge | slow piano, brushed snare") is None)

# --- 7. a pause holds every send ------------------------------------------------------------------------------------
SELF, DOT, GLORIA = "UVINTOS", D.DOT, "UGLORIA"
class Slack:
    def __init__(self):
        self.msgs, self.posted, self.n = [], [], 100.0
    def add(self, user, text, thread=None, bot=None):
        self.n += 1; ts = "%.6f" % self.n
        m = {"ts": ts, "user": user, "text": text}
        if bot:
            m.update(bot_id="B1", username=bot)
        if thread:
            m["thread_ts"] = thread
        self.msgs.append(m); return ts
    def __call__(self, method, params):
        if method == "auth.test":
            return {"ok": True, "user_id": SELF}
        if method == "conversations.history":
            return {"ok": True, "messages": [m for m in reversed(self.msgs) if not m.get("thread_ts")]}
        if method == "conversations.replies":
            return {"ok": True, "messages": [m for m in self.msgs if m["ts"] == params["ts"] or m.get("thread_ts") == params["ts"]]}
        if method == "chat.postMessage":
            self.posted.append(params); return {"ok": True, "ts": self.add(SELF, params["text"], params.get("thread_ts"))}
        raise AssertionError("unexpected Slack call " + method)

S = Slack()
writer = lambda s, u: "I will pick this up now. @dot can you check the tide table for me?"
lenses = {k: writer for k in ("opus", "opus55", "fable", "grok", "sol")}
kw = dict(api=S, think=lambda s, u: "KEEP" if s == D.EDITOR else writer(s, u), fable=writer, lenses=lenses,
          promise_ask=lambda *a, **k: "NONE", results_opus=writer)
D.tick(now=2000, **kw)                                                   # starts listening
st = json.load(open(D.STATE)); st["since"] = 100.0; json.dump(st, open(D.STATE, "w"))   # from before the stub's first message
S.add(GLORIA, "Goodnight, boys. !stop")
D.tick(now=2100, **kw)
check("her !stop is said once in the channel", len(S.posted) == 1 and "paused" in S.posted[0]["text"])
before, pushes = len(S.posted), len(PUSHES)
S.add("UMUSE", "BUY: a brass bell for the studio door | $14 | https://shop.invalid/bell", bot="Muse")
S.add(DOT, "ASK GLORIA: may I restart the toy hub tonight?")
MT._note("image", "a harbor at dusk", True, "image: art/harbor.png", "art/harbor.png", rid="r9")
SF.say("Study fix SF-x passed its tests")                               # a delayed result, from another process
out = D.tick(now=2200, **kw)
check("while paused, nothing is posted: not Muse's buy, not dot's ask, not what he made, not the Study's result",
      len(S.posted) == before and len(PUSHES) == pushes, (S.posted[before:], out))
check("... the Study's message is kept, not lost", os.path.isfile(D.HELD_POSTS) and "SF-x" in open(D.HELD_POSTS).read())
check("... and what came in is kept for after", len(json.load(open(D.STATE)).get("held_rows") or []) == 2, out)
check("... and what he made is still owed to the channel", any(not r.get("told") for r in MT.rows()))
S.add(GLORIA, "Morning! !start")
out = D.tick(now=2300, **kw)
texts = [p["text"] for p in S.posted[before:]]
check("her !start: the Study's held message is posted", any("SF-x" in t for t in texts), texts)
check("... Muse's buy and dot's ask reach her phone now", len(PUSHES) == pushes + 2, (len(PUSHES), out))
check("... and what he made is said", any("harbor" in t for t in texts), texts)

# --- the successful paths stay as they were ---------------------------------------------------------------------------
check("MIDI: and CITES: are still his tool lines", "MIDI" in D.TOOL.pattern and "CITES" in D.TOOL.pattern)
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
