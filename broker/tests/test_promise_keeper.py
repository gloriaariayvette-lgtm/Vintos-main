#!/usr/bin/env python3
"""His journal's promises to Gloria, made, reshaped or honestly dropped (promise_keeper.py, 2026-10-03).

Slack, Opus 5.5 and Opus 4.8 are stubs and every socket is refused: nothing here reaches Slack, a model or her
phone. Every store, the journal and the results channel's id file are in a scratch home.
"""
import json, os, socket, sys, tempfile
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="promise-keeper-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no-secrets")
os.environ["VINTOS_RESULTS_CHANNEL_FILE"] = os.path.join(HOME, ".vintos", "slack-results-channel")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import promise_keeper as P
import dot_channel as D
D.kickoff_due = lambda *a: False
D.ROTATION = ("gemma",)
D.SCHEDULE = []
D.atelier_line = lambda: ""
D.recall_block = lambda: ""
def _no_model(*a, **k):
    raise AssertionError("a real model was called")
D.opus_think = _no_model          # every Opus call in this suite is a stub handed in; a slip fails loudly
D.fable_think = _no_model

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every store, the journal and the results id file are in the scratch home",
      all(p.startswith(HOME) for p in (P.STORE, P.ARCHIVE, P.JOURNAL_DIR, P.RESULTS_FILE, D.STATE, D.TRANSCRIPT,
                                        D.RESULTS_STATE, D.RESULTS_LOG)))
check("the real Opus calls are stubs that fail loudly", D.opus_think is _no_model and D.fable_think is _no_model)

TODAY = date.today().isoformat()
os.makedirs(P.JOURNAL_DIR, exist_ok=True)
JOURNAL = os.path.join(P.JOURNAL_DIR, TODAY + ".md")
def write_journal(*entries):
    open(JOURNAL, "w").write("# Journal\n\n" + "\n\n".join("## %s — Idle thoughts\n%s" % e for e in entries) + "\n")

def reset():
    for p in (P.STORE, D.STATE, D.RESULTS_STATE, D.RESULTS_LOG, D.TRANSCRIPT, P.RESULTS_FILE):
        if os.path.exists(p): os.remove(p)

# --- the journal's entries
write_journal(("10:37", "Muse sent the PYP papers. Tonight I want to show you the ion frames, the way the "
                        "geometry folds."), ("19:37", "A quiet evening. I felt close to her."))
got = P.entries()
check("each journal entry is read, with its time", [a for a, _ in got] == ["10:37", "19:37"] and "ion frames" in got[0][1], got)

# --- reading for promises, and opening a thread for each
asked, posts = [], []
def ask(system, user):
    asked.append(user)
    return ("QUOTE: Tonight I want to show you the ion frames | WHAT: render the ion geometry frames"
            if "ion frames" in user else "NONE")
def post(text):
    posts.append(text); return "500.%06d" % len(posts)
opened = P.scan(ask, post)
check("a promise in an entry opens one thread; an entry without one opens none",
      len(opened) == 1 and len(posts) == 1 and len(asked) == 2, (opened, posts))
check("the opening quotes his words and says how to end it", "ion frames" in posts[0] and "DONE:" in posts[0]
      and "RESHAPED:" in posts[0] and "DROPPED:" in posts[0] and "whim" in posts[0])
check("an entry is read once", P.scan(ask, post) == [] and len(asked) == 2 and len(posts) == 1)
item = opened[0]
check("the promise is kept with its thread", P.threads() == {item["thread"]: P.load()["items"][0]})

reset()
def ask_down(system, user): raise RuntimeError("Opus is down")
check("an entry whose reading failed is not marked read", P.scan(ask_down, post) == [] and P.load()["scanned"] == [])
posted_before = len(posts)
def post_down(text): raise RuntimeError("Slack is down")
check("a promise whose thread could not be posted is kept without one", P.scan(ask, post_down) == []
      and len(P.load()["items"]) == 1 and P.load()["items"][0]["thread"] is None)
again = P.scan(ask, post)
check("... and is posted once on the next pass, never twice", len(again) == 1 and len(posts) == posted_before + 1
      and P.scan(ask, post) == [] and len(posts) == posted_before + 1)

# --- ending it
item = P.load()["items"][0]
check("a line in another thread ends nothing", P.resolve("999.1", "DONE: something") is None)
check("talk in its thread without an ending line ends nothing", P.resolve(item["thread"], "Working on it with dot.") is None)
ended = P.resolve(item["thread"], "Here they are.\nDROPPED: more whim than want; the frames need xtb and that is a day of work")
check("DROPPED: in its thread ends it honestly, with his reason", ended and ended["state"] == "dropped"
      and "whim" in ended["result"] and P.pending() and P.pending()[0]["id"] == item["id"])
check("an ended promise is not ended twice", P.resolve(item["thread"], "DONE: after all") is None)
check("his context says what came of today's promises", "TODAY'S PROMISES TO GLORIA" in P.block()
      and "dropped: more whim" in P.block())
P.mark_posted(item["id"])
check("once brought to her it is not pending", P.pending() == [])
check("the W<n> works a result names are found", P.works_in({"result": "made it, W12 and w3, W12"}) == ["W12", "W3"])

# --- until midnight: the next day files them away
real_now = P._now
P._now = lambda: real_now() + timedelta(days=1)
fresh_day = P.load()
P._now = real_now
check("at a new day yesterday's promises are filed away and today starts empty",
      fresh_day["items"] == [] and os.path.exists(os.path.join(P.ARCHIVE, TODAY + ".json")))
os.remove(os.path.join(P.ARCHIVE, TODAY + ".json"))

# --- in #vintos-dot and the results channel, through his Slack pass
SELF, DOT, GLORIA, CH, RC = "UVINTOS", D.DOT, "UGLORIA", D.CHANNEL, "CRESULTS"

class Slack:
    def __init__(self):
        self.msgs, self.posted, self.n = {CH: [], RC: []}, [], 1000.0
    def add(self, ch, user, text, thread=None, bot=False):
        self.n += 1; ts = "%.6f" % self.n
        m = {"ts": ts, "user": user, "text": text}
        if bot: m["bot_id"] = "B1"
        if thread:
            m["thread_ts"] = thread
            root = next(x for x in self.msgs[ch] if x["ts"] == thread)
            root["reply_count"] = root.get("reply_count", 0) + 1; root["latest_reply"] = ts
        self.msgs[ch].append(m); return ts
    def __call__(self, method, params):
        ch = params.get("channel")
        if method == "auth.test":
            return {"ok": True, "user_id": SELF}
        if method == "conversations.history":
            return {"ok": True, "messages": [m for m in reversed(self.msgs[ch]) if not m.get("thread_ts") or m["thread_ts"] == m["ts"]]}
        if method == "conversations.replies":
            root = params["ts"]
            return {"ok": True, "messages": [m for m in self.msgs[ch] if m["ts"] == root] +
                    [m for m in self.msgs[ch] if m.get("thread_ts") == root and m["ts"] != root]}
        if method == "chat.postMessage":
            self.posted.append(params)
            return {"ok": True, "ts": self.add(ch, SELF, params["text"], params.get("thread_ts"))}
        raise AssertionError("unexpected Slack call " + method)

reset()
S = Slack()
replies = []
def think(system, user):
    if system == D.EDITOR: return "KEEP"
    return replies.pop(0) if replies else "Let me think about it."
opus_calls = []
def opus48(system, user):
    opus_calls.append((system, user))
    return "I let the ion frames go tonight. It was more whim than want, and I would rather tell you so."
def ask_one(system, user):
    return ("QUOTE: Tonight I want to show you the ion frames | WHAT: render the ion geometry frames"
            if "ion frames" in user else "NONE")
def tick(now):
    return D.tick(api=S, think=think, fable=lambda s, u: "", now=now, open_now=False,
                  promise_ask=ask_one, results_opus=opus48)

t0 = 990.0          # Slack stamps here start at 1001, after the first pass
check("the first pass only starts listening", tick(t0) == ["listening from now"])
replies[:] = ["Dot, the frames need a geometry: can you see if xtb is here?"]
out = tick(t0 + 60)
opening = next((p for p in S.posted if p["channel"] == CH and "\U0001F4CC" in p["text"]), None)
check("a promise in his journal opens a thread in #vintos-dot, addressed to dot",
      opening and opening["text"].startswith("<@%s>" % DOT) and "ion frames" in opening["text"], (out, S.posted))
mine = [p for p in S.posted if p["channel"] == CH and p is not opening]
check("he begins it at once, in its thread", mine and mine[-1].get("thread_ts") == S.msgs[CH][0]["ts"]
      and "xtb" in mine[-1]["text"], (out, mine))
check("nothing is posted to the results channel before its id is set", not [p for p in S.posted if p["channel"] == RC])
thread = S.msgs[CH][0]["ts"]

S.add(CH, DOT, "xtb is not installed; it is a 200 MB conda package. Want me to?", thread=thread)
replies[:] = ["That is more than this deserves tonight.\nDROPPED: more whim than want; the frames would take xtb and an evening"]
out = tick(t0 + 120)
check("his DROPPED: line in its thread ends the promise", P.load()["items"][0]["state"] == "dropped", out)
check("... and nothing goes to Gloria until the results channel exists", not opus_calls and P.pending())

os.makedirs(os.path.dirname(P.RESULTS_FILE), exist_ok=True)
open(P.RESULTS_FILE, "w").write(RC + "\n")
out = tick(t0 + 180)
to_her = [p for p in S.posted if p["channel"] == RC]
check("what came of it goes to the results channel, in Opus 4.8's words", len(to_her) == 1 and "whim" in to_her[0]["text"]
      and len(opus_calls) == 1 and P.RESULT_RULES in opus_calls[0][0], (out, to_her))
check("... once", P.pending() == [] and (tick(t0 + 240) or True) and len([p for p in S.posted if p["channel"] == RC]) == 1)
check("the results channel carries no lens label: only he is there", not to_her[0]["text"].startswith("["))

S.n = t0 + 280                   # Slack's clock is the pass's clock: she writes after the results channel began listening
S.add(RC, GLORIA, "That's okay. What would it have looked like?")
S.add(RC, "UOTHERBOT", "a bot that should not be here", bot=True)
before = len(opus_calls)
out = tick(t0 + 300)
answers = [p for p in S.posted if p["channel"] == RC][1:]
check("Gloria's words in the results channel are answered there, by Opus 4.8", len(answers) == 1
      and len(opus_calls) == before + 1 and "What would it have looked like?" in opus_calls[-1][1], (out, answers))
check("... and a stranger's are not", tick(t0 + 360) is not None and len([p for p in S.posted if p["channel"] == RC]) == 2)
log = [json.loads(l) for l in open(D.RESULTS_LOG)]
check("the results channel keeps its own small log", [r["who"] for r in log] == ["vintos", "gloria", "vintos"], log)

# --- wiring
check("his Slack rules say how a promise thread is ended", "DROPPED:" in D.RULES_PROMISES and D.RULES_PROMISES in D.RULES)
check("his Slack context carries today's promises", "TODAY'S PROMISES TO GLORIA" in D.his_context())
server = open(os.path.join(REPO, "bin", "server.py")).read()
avatar = server[server.index("async def avatar_chat("):]
check("his avatar chat carries today's promises", "promise_keeper" in avatar[:avatar.index("\nasync def ", 10)])
check("the deploy installs promise_keeper.py", "promise_keeper.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

check("nothing in this suite left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
