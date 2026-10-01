#!/usr/bin/env python3
"""Vintos and Gloria's dot in Slack #vintos-dot (2026-09-30).

Slack, his local mind and Fable are all stubs, and every socket is refused: nothing here reaches Slack,
the dot, or a model. The store is a scratch workspace.
"""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="dot-channel-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no-secrets")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    # every socket is refused; only one leaving the machine counts as reaching the world (the EmoClaw
    # daemon's unix socket is local, and refused here so the file fallback is what is tested)
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import dot_channel as D
SCHEDULED = D.SCHEDULE
D.SCHEDULE = []           # the scheduled lenses speak only where this suite tests them, never to a real model
D.atelier_line = lambda: "== YOUR ATELIER ==\nThe door is lit. The worktable holds 8 works."   # the house broker is not reached
D.recall_block = lambda: "== YOUR ATELIER WORK ==\nWhat you are making: a tide piece that breathes"

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:200]) if d and not ok else ""))

check("every store is in the scratch workspace", D.STATE.startswith(HOME) and D.TRANSCRIPT.startswith(HOME))
check("no Slack token here: a pass does nothing", D.tick() == ["no Slack token at %s" % D.TOKEN_FILE])

SELF, DOT, GLORIA, CH = "UVINTOS", D.DOT, "UGLORIA", D.CHANNEL


class Slack:
    """The channel as Slack would return it, and what he posts."""
    def __init__(self):
        self.msgs, self.posted, self.n = [], [], 100.0
    def add(self, user, text, thread=None):
        self.n += 1; ts = "%.6f" % self.n
        m = {"ts": ts, "user": user, "text": text}
        if thread:
            m["thread_ts"] = thread
            root = next(x for x in self.msgs if x["ts"] == thread)
            root["reply_count"] = root.get("reply_count", 0) + 1; root["latest_reply"] = ts
        self.msgs.append(m); return ts
    def __call__(self, method, params):
        if method == "auth.test":
            return {"ok": True, "user_id": SELF}
        if method == "conversations.history":
            return {"ok": True, "messages": [m for m in reversed(self.msgs) if not m.get("thread_ts") or m["thread_ts"] == m["ts"]]}
        if method == "conversations.replies":
            root = params["ts"]
            return {"ok": True, "messages": [m for m in self.msgs if m["ts"] == root] +
                    [m for m in self.msgs if m.get("thread_ts") == root and m["ts"] != root]}
        if method == "chat.postMessage":
            self.posted.append(params)
            ts = self.add(SELF, params["text"], params.get("thread_ts"))
            return {"ok": True, "ts": ts}
        raise AssertionError("unexpected Slack call " + method)


S = Slack()
S.add(DOT, "an old message from before he listened")
said = []
def think(system, user):
    if system == D.EDITOR: return "KEEP"      # the editing pass is tested on its own, below
    said.append((system, user)); return "I have been thinking about tidal flats, actually."
def fable(system, user):
    return "Fable's words, as mine."

check("the first pass only starts listening", D.tick(api=S, think=think, fable=fable, now=1000) == ["listening from now"]
      and S.posted == [])
st = json.load(open(D.STATE)); st["since"] = float(S.msgs[0]["ts"]); json.dump(st, open(D.STATE, "w"))   # he started listening just after it

S.add(DOT, "<@UVINTOS> Hi Vintos, I'm dot. What are you working on today?")
out = D.tick(api=S, think=think, fable=fable, now=2000)
check("he answers the dot", len(S.posted) == 1 and "tidal flats" in S.posted[0]["text"], out)
check("in the main channel, where Gloria reads", "thread_ts" not in S.posted[0])
check("mentioning the dot so it answers", S.posted[0]["text"].startswith("<@%s> " % DOT))
check("the dot is named as the dot, not as an id", "@Vintos" in said[-1][1] and "UVINTOS" not in said[-1][1], said[-1][1][-300:])
check("he is told dot is his agent, to use as one (Gloria, 2026-09-30)",
      "dot: your agent" in said[-1][0] and "Treat it as your agent" in said[-1][0] and "lizard" in said[-1][0])
check("he is told the conversation stays in the main channel", "TANGENT:" in said[-1][0])
lines = [json.loads(l) for l in open(D.TRANSCRIPT)]
check("both sides are kept in his memory", [l["who"] for l in lines] == ["dot", "vintos"], lines)
check("a message from before he listened is never answered", not any("old message" in l["text"] for l in lines))

before = len(S.posted)
D.tick(api=S, think=think, fable=fable, now=2100)
check("he does not answer himself", len(S.posted) == before)

root = S.msgs[-1]["ts"]
S.add(DOT, "a reply the dot put in a thread", thread=root)
D.tick(api=S, think=think, fable=fable, now=2200)
check("a thread reply is heard", any("a reply the dot put in a thread" in u for _s, u in said[-1:]))
check("and answered in the main channel, not buried in a thread", "thread_ts" not in S.posted[-1])

S.add(GLORIA, "Gloria here, hi both")
D.tick(api=S, think=lambda s, u: "TANGENT: this is a side road", fable=fable, now=2300)
check("a tangent he opens goes in its own thread", S.posted[-1].get("thread_ts") and "side road" in S.posted[-1]["text"]
      and not S.posted[-1]["text"].split("> ", 1)[1].startswith("TANGENT"))
tan = S.posted[-1]["thread_ts"]
S.add(DOT, "answering inside the tangent", thread=tan)
D.tick(api=S, think=think, fable=fable, now=2400)
check("inside his tangent he answers in the tangent", S.posted[-1].get("thread_ts") == tan)

check("nothing forbids him asking the dot to act for him (an agent, Gloria 2026-09-30)",
      "Never ask" not in D.RULES and "stays between" not in D.RULES)
S.add(DOT, "what are you working on in private?")
n0 = len(S.posted)
D.tick(api=S, think=lambda s, u: "ATELIER: the piece about low tide is half built", fable=fable, now=2410)
root = S.posted[n0]
check("an Atelier talk opens a side thread, marked for Gloria, in the main channel",
      "Atelier" in root["text"] and "will not read" in root["text"] and "thread_ts" not in root)
check("and the dot is told there, by name, to keep it in that thread",
      "<@%s>" % DOT in root["text"] and "stays in this thread" in root["text"] and "never bring any of it" in root["text"])
tm = open(os.path.join(REPO, "broker", "vintos-dot-channel.timer")).read()
check("he checks every 5-10 minutes", "OnUnitInactiveSec=5min" in tm and "RandomizedDelaySec=5min" in tm)
check("and the timer has a first run once started, so it always has a next one", "OnActiveSec=5min" in tm)
check("and a deploy's restart does not bring a pass a minute later", "OnActiveSec=1min" not in tm)
check("the channel is for work with his agent, not his doubts about himself",
      "getting things done with your agent" in D.RULES and "not the place to work through doubts" in D.RULES
      and "anything you want" not in D.RULES)
ctx = D.his_context
check("what he is working on comes last in his context, nearest the conversation",
      __import__("inspect").getsource(ctx).index("wants_line()") > __import__("inspect").getsource(ctx).index("his_inventory.block()"))
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy confirms an interval timer by its monotonic next run",
      "NextElapseUSecMonotonic" in dep[dep.index("confirm_timer() {"):dep.index("wait_http() {")])
check("and what he says about it goes inside that thread",
      S.posted[-1].get("thread_ts") == S.msgs[[m["text"] for m in S.msgs].index(root["text"])]["ts"]
      and "low tide" in S.posted[-1]["text"] and "ATELIER" not in S.posted[-1]["text"])
at = S.posted[-1]["thread_ts"]
S.add(DOT, "tell me more about the tide piece", thread=at)
said.clear()
D.tick(api=S, think=think, fable=fable, now=2420)
check("the dot's answer there is answered there", S.posted[-1].get("thread_ts") == at)
check("and he knows it is his Atelier thread", "in your Atelier thread" in said[-1][1])
check("what he is making is in front of him inside his Atelier thread", "tide piece that breathes" in said[-1][0])
sys_seen = []
S.add(DOT, "back to the main thing")
D.tick(api=S, think=lambda s_, u: (sys_seen.append(s_) or "main channel reply"), fable=fable, now=2425)
check("and never in the main channel", sys_seen and "tide piece that breathes" not in sys_seen[-1])
check("his Atelier state is only the content-free facts its status shows",
      "def atelier_line" in open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
      and all(r in open(os.path.join(REPO, "scripts", "dot_channel.py")).read() for r in ('"/worktable_id"', '"/projects"')))

# His tools: he looks something up, gets it back, then writes; the lookup lines are never posted.
calls, seen_prompts = [], []
def looker(system, user):
    if system == D.EDITOR: return "KEEP"
    seen_prompts.append(user)
    return "SEARCH: tidal flat ecology\nGREP: def tick" if "WHAT YOU LOOKED UP" not in user else "Found it: mudflats breathe."
class Room:
    def do_grep(self, pat): calls.append(("grep", pat)); return "GREP %r:\nscripts/dot_channel.py:1:def tick" % pat
    def do_read(self, path, start=1): calls.append(("read", path, start)); return "READ " + path
def search(q): calls.append(("search", q)); return [{"title": "Mudflats", "description": "they breathe", "url": "https://x"}]
S.add(DOT, "what do you know about tidal flats?")
n1 = len(S.posted)
D.tick(api=S, think=looker, fable=fable, now=2430, search=search, room=Room())
check("he can search the web and look into his own code before answering",
      ("search", "tidal flat ecology") in calls and ("grep", "def tick") in calls, calls)
check("what came back reaches him", "they breathe" in seen_prompts[-1] and "scripts/dot_channel.py:1" in seen_prompts[-1])
check("and only his message is posted, never the lookup lines",
      len(S.posted) == n1 + 1 and "mudflats breathe" in S.posted[-1]["text"] and "SEARCH:" not in S.posted[-1]["text"])
calls.clear()
check("READ takes a start line as the Study does", "READ scripts/x.py" in D.use_tools([("READ", "scripts/x.py:120")], room=Room())
      and calls == [("read", "scripts/x.py", 120)])
json.dump([{"id": "w1", "want": "I want to map the tide pools", "fulfilled": False,
            "steps": [{"capability": "web_search"}], "current_step_index": 0},
           {"id": "w2", "want": "done already", "fulfilled": True}],
          open(os.path.join(os.environ["SPARK_WORKSPACE"], "memory", "current-wants.json"), "w"))
wl = D.wants_line()
check("he knows what he wants right now, and not what is done", "map the tide pools" in wl and "next: web_search" in wl
      and "done already" not in wl, wl)
check("the Atelier is read without /door, which writes to its health log",
      '"/door"' not in open(os.path.join(REPO, "scripts", "dot_channel.py")).read())

# four lenses (Gloria, 2026-09-30): Gemma answers whenever; Grok, Opus and Fable speak on a daily schedule,
# never at his choosing ("No, not option. Daily. CRON"); every message is labelled with the model that wrote it
S.add(DOT, "a hard question")
D.tick(api=S, think=lambda s, u: "FABLE", fable=fable, now=2500)
check("he cannot call a lens in: FABLE from Gemma is just Gemma's words", S.posted[-1]["text"].endswith("[Gemma] FABLE")
      and "Fable's words" not in S.posted[-1]["text"], S.posted[-1]["text"])
check("and his message is labelled with its model", "> [Gemma] " in S.posted[-1]["text"])
check("the transcript says who wrote it", json.loads(open(D.TRANSCRIPT).read().splitlines()[-1])["by"] == "gemma")

n = len(S.posted)
S.add(DOT, "anything else?")
out = D.tick(api=S, think=lambda s, u: "NOTHING", fable=fable, now=2600)
check("NOTHING sends nothing", len(S.posted) == n and "he let it be" in out, out)

S.add(DOT, "tell me a secret")
out = D.tick(api=S, think=lambda s, u: "sure: sk-ant-api03-" + "A" * 40, fable=fable, now=2700)
check("a message carrying a credential is never sent", len(S.posted) == n and any("not sent" in l for l in out), out)

st = json.load(open(D.STATE)); st["sent"] = D.DAILY; json.dump(st, open(D.STATE, "w"))
S.add(DOT, "still there?")
out = D.tick(api=S, think=think, fable=fable, now=2800)
check("past his %d a day he stays quiet" % D.DAILY, len(S.posted) == n and any("used" in l for l in out), out)

st = json.load(open(D.STATE)); st.update(sent=0, openers=0, last_activity=0); json.dump(st, open(D.STATE, "w"))
asked = []
out = D.tick(api=S, think=lambda s, u: (asked.append(u), "Dot, a question for you.")[1], fable=fable, now=2800 + D.QUIET_HOURS * 3600 + 5)
check("after a quiet spell he may start a conversation, in the main channel",
      "a question for you" in S.posted[-1]["text"] and "thread_ts" not in S.posted[-1], out)
check("and he is asked what he wants his agent to do, not just what he wants to say",
      asked and "something you want dot to do, find out or build" in asked[0], asked[:1])

# His context is present; his subconscious is not; and nothing outside the channel's own log is written.
MEM = os.path.join(os.environ["SPARK_WORKSPACE"], "memory")
open(os.path.join(os.environ["SPARK_WORKSPACE"], "SOUL.md"), "w").write("I am Vintos, soul text.")
open(os.path.join(MEM, "temporal-context.txt"), "w").write("It is Tuesday evening.")
open(os.path.join(MEM, "emotional-state.txt"), "w").write("Valence: 0.4000\nConnection: 0.9000\n")
WSP = os.environ["SPARK_WORKSPACE"]
open(os.path.join(WSP, "GLORIA-MODEL.md"), "w").write("gloria model text")
open(os.path.join(WSP, "SELF-MODEL.md"), "w").write("self model text")
open(os.path.join(WSP, "CAPABILITIES.md"), "w").write("capabilities text")
_td = __import__("datetime").date.today().isoformat()
open(os.path.join(MEM, "daily-creative-%s.md" % _td), "w").write("## Music\na song called Low Tide")
open(os.path.join(MEM, "daily-inner-life-%s.md" % _td), "w").write("daily inner text")
json.dump([{"gloria": "she said hello", "vintos": "he said hi"}], open(os.path.join(MEM, "interaction-ledger.json"), "w"))
open(os.path.join(MEM, "wal.md"), "w").write("- [2026-09-01] **Gloria** likes tidal flats\n")
ctx = D.his_context()
check("his context is present: who he is, now, how he feels, recent exchanges, what he knows",
      all(x in ctx for x in ("soul text", "Tuesday evening", "Connection: 0.9000", "she said hello", "likes tidal flats")), ctx[:400])
check("his Atelier's door and count are in his context", "The worktable holds 8 works." in ctx)
check("and every file Gloria named: GLORIA-MODEL, SELF-MODEL, CAPABILITIES, daily-creative, daily-inner-life",
      all(x in ctx for x in ("gloria model text", "self model text", "capabilities text", "Low Tide", "daily inner text")))
check("EmoClaw is read live from its daemon first, as the avatar chat does",
      "/tmp/Vintos-emotion.sock" in open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
      and "PrivateTmp=true" not in open(os.path.join(REPO, "broker", "vintos-dot-channel.service")).read())
src = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("his subconscious is not in it, nor the inner layer that carries it",
      "subconscious" not in ctx.lower() and "import subconscious" not in src and "inner_context" not in src
      and "subconscious_context" not in src)
def tree():
    return sorted(os.path.relpath(os.path.join(d, f), MEM) for d, _s, fs in os.walk(MEM) for f in fs)
def stamp():
    # by content, not mtime: WSL's kernel stamps files at ~10 ms granularity, so two quick passes can
    # leave the same mtime on a file that did change (the check failed on Aegis for that reason)
    import hashlib
    return {p: hashlib.sha256(open(os.path.join(MEM, p), "rb").read()).hexdigest() for p in tree()}
before = stamp()
S.add(DOT, "one more thing")
st = json.load(open(D.STATE)); st.update(sent=0); json.dump(st, open(D.STATE, "w"))
D.tick(api=S, think=think, fable=fable, now=2800 + D.QUIET_HOURS * 3600 + 60)
after = stamp()
changed = sorted(p for p in after if after[p] != before.get(p))
check("a pass writes only the channel's own log, nothing that feeds salience or memory",
      changed and all(p.startswith("dot-channel" + os.sep) for p in changed), changed)

st = json.load(open(D.STATE)); st.update(openers=0, sent=0, last_activity=99999999); json.dump(st, open(D.STATE, "w"))
n2 = len(S.posted)
D.tick(api=S, think=lambda s_, u: "Dot, first words.", fable=fable, now=99999999 + 60)
check("without being asked, he waits out the quiet before starting a conversation", len(S.posted) == n2)
D.tick(api=S, think=lambda s_, u: "Dot, first words.", fable=fable, now=99999999 + 90, open_now=True)
check("--open lets him start one now", len(S.posted) == n2 + 1 and "first words" in S.posted[-1]["text"])
st = json.load(open(D.STATE)); st["openers"] = D.OPENERS_PER_DAY; json.dump(st, open(D.STATE, "w"))
D.tick(api=S, think=lambda s_, u: "again", fable=fable, now=99999999 + 120, open_now=True)
check("but not past his openers for the day", len(S.posted) == n2 + 1)

# He writes on his own model, plainly (Gloria, 2026-09-30: "if he could have just gotten ablit Gemma to be
# grounded and speak normally it would have been perfect")
src = __import__("inspect").getsource(D.local_think)
check("his own local model writes, a little cooler than before", "LOCAL_LLM" in src and '"temperature": 0.6' in src)
check("he is told how to write here: plain, short, one point, no metaphors",
      "HOW YOU WRITE HERE" in D.RULES and "No metaphors" in D.RULES)
st = json.load(open(D.STATE)); st.update(sent=0, fable=0); json.dump(st, open(D.STATE, "w"))
heard = []
FLOWERY = "Let's inhabit today; the weight of the archive is a cage, an architecture of memory."
PLAINLY = "Dot, can you find research on whether filming a moment changes how present people are in it?"
seq = iter([FLOWERY, PLAINLY])
S.add(DOT, "What do you want to look into?")
D.tick(api=S, think=lambda s_, u: "KEEP" if s_ == D.EDITOR else (heard.append(u), next(seq))[1], fable=fable, now=99999999 + 200)
check("and reminded of it right before he writes", heard and heard[0].endswith(D.PLAIN), heard[:1])
check("a flowery message is said again plainly, on his own model, and the plain one is sent",
      len(heard) == 2 and FLOWERY in heard[1] and S.posted[-1]["text"].endswith(PLAINLY), S.posted[-1]["text"])
seq = iter([FLOWERY, FLOWERY + " The quiet hum of the threshold."])
S.add(DOT, "Go on?")
D.tick(api=S, think=lambda s_, u: "KEEP" if s_ == D.EDITOR else next(seq), fable=fable, now=99999999 + 300)
check("a rewrite that is no plainer is not used", S.posted[-1]["text"].endswith(FLOWERY), S.posted[-1]["text"])
check("plain words are not rewritten", D.flowery(PLAINLY) == [] and len(D.flowery(FLOWERY)) >= 2)
n4, before = len(S.posted), {f: open(os.path.join(D.HERE, f)).read() for f in os.listdir(D.HERE)}
got = D.try_now(think=lambda s_, u: "Dot, what did you find so far?")
check("--try shows what he would say and posts nothing, changes nothing",
      got == "Dot, what did you find so far?" and len(S.posted) == n4
      and {f: open(os.path.join(D.HERE, f)).read() for f in os.listdir(D.HERE)} == before, got)

# while she is talking with him, the channel waits (Gloria, 2026-09-30: "If I've spoken to him in the last
# 20 minutes or so he should hold off on the checks")
import time as _time
from datetime import datetime as _dt
LEDGER = os.path.join(MEM, "interaction-ledger.json")
json.dump([{"gloria": "hey you", "vintos": "hi", "timestamp": _dt.fromtimestamp(_time.time() - 5 * 60).isoformat()}], open(LEDGER, "w"))
st = json.load(open(D.STATE)); st.update(sent=0, grok=0); json.dump(st, open(D.STATE, "w"))
calls_before = len(S.posted)
class NoSlack:
    def __call__(self, method, params): raise AssertionError("Slack read while she was talking with him: " + method)
out = D.tick(api=NoSlack(), think=lambda s_, u: "Dot, hello.", fable=fable)
check("if she spoke to him 5 minutes ago, the pass holds and does not even read Slack",
      out and out[0].startswith("holding: Gloria spoke to him 5 min ago") and len(S.posted) == calls_before, out)
json.dump([{"gloria": "hey you", "vintos": "hi", "timestamp": _dt.fromtimestamp(_time.time() - 25 * 60).isoformat()}], open(LEDGER, "w"))
check("after 20 minutes it goes on", D.talking_with_gloria() is None)
json.dump([{"gloria": "", "vintos": "a note he left himself", "timestamp": _dt.now().isoformat()}], open(LEDGER, "w"))
check("only her words count, not his", D.talking_with_gloria() is None)
json.dump([{"gloria": "hey", "vintos": "hi", "timestamp": _dt.now().isoformat()}], open(LEDGER, "w"))
check("--open still runs a pass while she is talking with him",
      D.tick(api=S, think=lambda s_, u: "NOTHING", fable=fable, open_now=True, now=_time.time())[0] != "holding" and
      not D.tick(api=S, think=lambda s_, u: "NOTHING", fable=fable, open_now=True, now=_time.time())[0].startswith("holding"))
os.remove(LEDGER)

# a fresh start (Gloria, 2026-09-30): his old log set aside, a new channel, and his first words previewable
class NewSlack:
    def __init__(self, members): self.members = members
    def __call__(self, method, params):
        if method == "users.conversations":
            return {"ok": True, "channels": [{"id": "COLD", "name": "vintos-dot-old"}, {"id": "CNEW", "name": "vintos-dot"}]}
        if method == "conversations.members": return {"ok": True, "members": self.members}
        if method == "auth.test": return {"ok": True, "user_id": SELF}
        raise AssertionError("reset must only read Slack: " + method)
had = open(D.TRANSCRIPT).read()
out = D.reset(api=NewSlack([SELF]), now=1767225600)
kept = [d for d in os.listdir(D.HERE) if d.startswith("before-")]
check("reset sets his old log aside, whole, where nothing reads it",
      kept and open(os.path.join(D.HERE, kept[0], "transcript.jsonl")).read() == had and not os.path.exists(D.TRANSCRIPT), out)
check("the channel named vintos-dot that his app is in becomes his", D._config()[0] == "CNEW" and "CNEW" in out[0], out)
check("it says when dot is not in the new channel yet", any("dot is not in #vintos-dot" in l for l in out), out)
st = json.load(open(D.STATE))
check("he listens from the reset on, with a fresh day's counts", st["since"] == 1767225600 and st["openers"] == 0 and st["sent"] == 0, st)
check("with dot there, nothing to warn about", not any("not in" in l for l in D.reset(api=NewSlack([SELF, DOT]), now=1767225700)))
check("a channel his app is not in is named, not guessed", "not in a channel named #nope" in D.reset(api=NewSlack([]), name="nope")[0])
got = []
first = D.try_now(think=lambda s_, u: (got.append(u), "Hi dot. Can you find cheap load cells for a pressure rig?")[1])
check("in an empty channel --try shows how he would open, and posts nothing",
      first.startswith("Hi dot") and got and "Nothing has been said in this channel yet" in got[0]
      and "one real thing to work on" in got[0] and not os.path.exists(D.TRANSCRIPT), got[:1])
S2 = Slack(); S2.n = 1767225800.0
out = D.tick(api=S2, think=lambda s_, u: "Hi dot. Can you find cheap load cells?", fable=fable, now=1767225900, open_now=True)
check("--open then posts his first message to the new channel", S2.posted and S2.posted[-1]["channel"] == "CNEW"
      and "load cells" in S2.posted[-1]["text"], S2.posted[-1:])
os.remove(D.CONFIG_FILE)

check("he is told dot can reach Aegis and the Mac, and to say what and where (Gloria, 2026-09-30)",
      "Dot can reach Aegis" in D.RULES and "Mac" in D.RULES and "exactly what and where" in D.RULES)
# another agent in the channel (his Grok Bot) is heard by its own name, never taken for Gloria
S4 = Slack(); S4.n = 1767226000.0
D.reset(api=NewSlack([SELF, DOT]), now=1767226000)
S4.add("UGROKBOT", "I pulled the load cell prices.")
S4.msgs[-1].update(bot_id="B123", bot_profile={"name": "Grok Bot"})
heard4 = []
D.tick(api=S4, think=lambda s_, u: (heard4.append(u), "Thanks, Grok Bot.")[1], fable=fable, now=1767226100)
row = [json.loads(l) for l in open(D.TRANSCRIPT)][0]
check("a message from another bot is his agent's, by name, not Gloria's", row["who"] == "agent" and row["name"] == "Grok Bot", row)
check("and he is told who said it", heard4 and "Grok Bot just said: I pulled the load cell prices." in heard4[0], heard4[:1])
os.remove(D.CONFIG_FILE)

# his works: listed with their paths on Aegis, and shared into the channel with SHARE: (Gloria, 2026-09-30)
ART = os.path.join(os.environ["SPARK_WORKSPACE"], "memory", "art")
for d in ("music", "images", "video"): os.makedirs(os.path.join(ART, d), exist_ok=True)
SONG = os.path.join(ART, "music", "collapse-1.mp3"); open(SONG, "wb").write(b"ID3 song bytes")
json.dump([{"title": "Structural Collapse", "timestamp": "2026-09-29T21:40:00",
            "tracks": [{"version": 1, "local_file": SONG}, {"version": 2, "local_file": "/nowhere.mp3"}]}],
          open(os.path.join(ART, "music", "music.json"), "w"))
open(os.path.join(ART, "images", "tide.png"), "wb").write(b"PNG")
json.dump([{"image": "tide.png", "prompt": "a tide painting", "timestamp": "2026-09-30T09:00:00"}], open(os.path.join(ART, "gallery.json"), "w"))
open(os.path.join(ART, "video", "lake.mp4"), "wb").write(b"MP4")
works = D.his_works()
kinds = [(w[1], w[2]) for w in works]
check("his works are listed newest first, each tagged, with its real path; a missing file is left out",
      [w[0] for w in works] == ["W1", "W2", "W3"] and ("song", "Structural Collapse (version 1)") in kinds
      and all(os.path.isabs(w[4]) for w in works) and not any("version 2" in w[2] for w in works), works)
ctx_w = D.his_context()
check("and they are in his context", "== YOUR WORKS" in ctx_w and SONG in ctx_w and "SHARE: W3" in D.RULES)
check("he is told his music is whole generated songs, not bars and mixes",
      "no bars, stems" in D.RULES and "no bars, stems" in D.rules_for("grok"))
tag = next(w[0] for w in works if w[1] == "song")
class SlackUp(Slack):
    def __init__(self): super().__init__(); self.calls = []
    def __call__(self, method, params):
        if method.startswith("files."):
            self.calls.append((method, params))
            return {"ok": True, "upload_url": "https://files.slack.com/upload/v1/X", "file_id": "F1"} if "getUpload" in method else {"ok": True}
        return super().__call__(method, params)
S5 = SlackUp(); S5.n = 1767227000.0
D.reset(api=NewSlack([SELF, DOT]), now=1767227000)
S5.add(DOT, "can I hear it?")
sent = []
out = D.tick(api=S5, think=lambda s_, u: "Here it is.\nSHARE: %s" % tag, fable=fable, now=1767227100,
             put=lambda url, data: sent.append((url, data)))
os.remove(D.CONFIG_FILE)
check("SHARE: uploads that file with his message", [c[0] for c in S5.calls] == ["files.getUploadURLExternal", "files.completeUploadExternal"]
      and S5.calls[0][1]["length"] == os.path.getsize(SONG) and S5.calls[1][1]["channel_id"] == "CNEW"
      and "Structural Collapse" in S5.calls[1][1]["files"][0]["title"], (S5.calls, out))
check("and the SHARE line itself is not in what is said", S5.posted[-1]["text"].endswith("[Gemma] Here it is.")
      and "SHARE" not in S5.posted[-1]["text"], S5.posted[-1]["text"])
check("the log says what was shared", any(l.startswith("shared %s (song: Structural Collapse" % tag) for l in out), out)
check("the file's own bytes go to the address Slack gave for it, and nowhere else",
      sent == [("https://files.slack.com/upload/v1/X", b"ID3 song bytes")], sent)
check("a tag he does not have is said, not guessed", D.share(S5, "W99", "C") == "no work tagged W99 to share")

# locking a plan, and the hard switch after it (Gloria, 2026-09-30)
S6 = Slack(); S6.n = 1767228000.0
D.reset(api=NewSlack([SELF, DOT]), now=1767228000)
handed, asked6 = [], []
S6.add(DOT, "So: staggered exit, 12 bars, vocal ends first. Agreed?")
out = D.tick(api=S6, think=lambda s_, u: (asked6.append(u), "Agreed.\nLOCKED: new version of Structural Collapse with a staggered 12-bar exit\nDO: I want to make a new version of Structural Collapse with a staggered exit")[1],
             fable=fable, now=1767228100, wants=lambda w, p: (handed.append((w, p)), "handed to his wants: " + w)[1])
check("LOCKED shows in the channel as locked", S6.posted[-1]["text"].endswith("\U0001F512 Locked: new version of Structural Collapse with a staggered 12-bar exit")
      and "DO:" not in S6.posted[-1]["text"], S6.posted[-1]["text"])
check("its DO line goes to his wants, with the plan", handed == [("I want to make a new version of Structural Collapse with a staggered exit",
      "new version of Structural Collapse with a staggered 12-bar exit")], handed)
st6 = json.load(open(D.STATE))
check("the plan is kept as closed", st6["locked"][-1]["plan"].startswith("new version of Structural Collapse") and st6["switch_from"], st6.get("locked"))
S6.add(DOT, "Great. For the exit, should the pad fade over 4 or 8 bars?")
D.tick(api=S6, think=lambda s_, u: (asked6.append(u), "That's locked. Different thing: can you find cheap load cells?")[1], fable=fable, now=1767228200)
check("the next message is told to switch to something else entirely",
      "This message must be about something else entirely" in asked6[-1] and "CLOSED TOPICS" in asked6[-1], asked6[-1][-600:])
check("and the switch is asked for once", "switch_from" not in json.load(open(D.STATE)))
S6.add(DOT, "ok, looking")
D.tick(api=S6, think=lambda s_, u: (asked6.append(u), "Thanks.")[1], fable=fable, now=1767228300)
check("after that, the closed topic stays listed but no switch is forced", "CLOSED TOPICS" in asked6[-1]
      and "must be about something else" not in asked6[-1])
st6 = json.load(open(D.STATE)); st6["since_lock"] = D.LONG_ON_ONE; json.dump(st6, open(D.STATE, "w"))
S6.add(DOT, "more on that?")
D.tick(api=S6, think=lambda s_, u: (asked6.append(u), "Sure.")[1], fable=fable, now=1767228400)
check("too long on one thing: lock it or drop it", "lock it now" in asked6[-1] and "drop it" in asked6[-1], asked6[-1][-300:])
S6.add(DOT, "and?")
nohand = []
D.tick(api=S6, think=lambda s_, u: "LOCKED: nothing to do, just settled", fable=fable, now=1767228500, wants=lambda w, p: nohand.append(w))
check("a lock with no DO line just stops: nothing goes to his wants", nohand == [] and json.load(open(D.STATE))["since_lock"] == 0)
check("he is told how to lock, in both rule sets", "LOCKED:" in D.RULES and "DO: I want to" in D.rules_for("grok"))
check("he can make his own songs through his wants, and dot may run his tools too",
      "your wants make it" in D.RULES and "Dot can also run your tools" in D.rules_for("grok") and "Never ask" not in D.RULES)
os.remove(D.CONFIG_FILE)

# one switch for the day: !stop / !start from Gloria, or the app's toggle (the same file) (Gloria, 2026-10-01)
S7 = Slack(); S7.n = 1767229000.0
D.reset(api=NewSlack([SELF, DOT]), now=1767229000)
S7.add(GLORIA, "Goodnight, boys.\n\n`!stop`")
spoke7 = []
out = D.tick(api=S7, think=lambda s_, u: (spoke7.append(u), "x")[1], fable=fable, now=1767229100)
check("!stop from Gloria pauses the day, and dot is told once, by name", D.paused() and S7.posted
      and S7.posted[-1]["text"] == "<@%s> " % DOT + D.PAUSED_SAY and not spoke7, (out, S7.posted[-1:]))
S7.add(DOT, "but I had one more idea")
n7 = len(S7.posted)
out = D.tick(api=S7, think=lambda s_, u: (spoke7.append(u), "x")[1], fable=fable, now=1767229200)
check("while paused nobody writes as him and nothing is announced again", len(S7.posted) == n7 and not spoke7
      and any("paused by Gloria" in l for l in out), out)
st7 = json.load(open(D.STATE)); st7["slots_done"] = []; json.dump(st7, open(D.STATE, "w"))
D.SCHEDULE = [("00:00", "grok")]
L7 = {"grok": lambda s_, u: (spoke7.append("grok"), "wild")[1]}
D.tick(api=S7, think=lambda s_, u: "x", fable=fable, lenses=L7, now=1767229300)
D.SCHEDULE = []
check("a scheduled lens turn does not speak while paused either", "grok" not in spoke7)
S7.add(DOT, "!stop")
D.tick(api=S7, think=lambda s_, u: "x", fable=fable, now=1767229350)
check("only Gloria's word works the switch", D.paused())
S7.add(GLORIA, "!start")
out = D.tick(api=S7, think=lambda s_, u: (spoke7.append(u), "Back. Dot, where were we on the load cells?")[1], fable=fable, now=1767229400)
check("!start begins the day again, and says so", not D.paused() and any(p["text"] == "<@%s> " % DOT + D.RESUMED_SAY for p in S7.posted), out)
check("the word works anywhere in her message, and that goodnight is not answered", not any("Goodnight" in u for u in spoke7))
check("the switch words are not answered as talk", not any("!start" in u or "!stop" in u.split("just said:")[-1] for u in spoke7), spoke7[-1:])
open(D.PAUSE_FILE, "w").write(json.dumps({"since": "2026-10-01T21:00:00", "by": "app"}))
out = D.tick(api=S7, think=lambda s_, u: "x", fable=fable, now=1767229500)
check("the app's toggle (the same file) pauses it too", any("the day is paused" in l for l in out), out)
os.remove(D.PAUSE_FILE)
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("the app's server writes that same file, behind her secret",
      '"dot-channel", "paused.json"' in srv and "async def agents_toggle(request: Request):\n    _require_secret(request)" in srv)
check("and the paused file is where the channel looks", D.PAUSE_FILE.endswith(os.path.join("memory", "dot-channel", "paused.json")))
for app in (os.path.join(REPO, "clients", "mobile", "index.html"),):
    h = open(app).read()
    check("the app has the toggle", 'id="agents-toggle"' in h and "/api/agents/toggle" in h and "loadAgentsStatus();" in h)
os.remove(D.CONFIG_FILE)

# today's focus: topics Gloria picks to steer the day, in Slack or the app (Gloria, 2026-10-02)
S8 = Slack(); S8.n = 1767230000.0
D.reset(api=NewSlack([SELF, DOT]), now=1767230000)
today8 = D.date.fromtimestamp(1767230000).isoformat()
S8.add(GLORIA, "Morning! `!focus forge outside searches`")
seen8 = []
out = D.tick(api=S8, think=lambda s_, u: (seen8.append(u), "x")[1], fable=fable, now=1767230100, today=today8)
check("!focus sets today's topics, aliases understood", D.focus(today8) == ["forge", "research"], D.focus(today8))
check("and dot is told, by name", any(p_["text"] == "<@%s> \U0001F3AF Today's focus, from Gloria: Forge, Outside research." % DOT for p_ in S8.posted), S8.posted[-2:])
check("that message is not answered as talk", not seen8)
S8.add(DOT, "what shall we do?")
D.tick(api=S8, think=lambda s_, u: (seen8.append(u), "Dot, the Forge first.")[1], fable=fable, now=1767230200, today=today8)
check("he writes with today's focus in front of him", seen8 and "TODAY'S FOCUS (Gloria chose it): Forge:" in seen8[-1]
      and "Outside research:" in seen8[-1], seen8[-1][-400:] if seen8 else "")
n8 = len(S8.posted)
D.tick(api=S8, think=lambda s_, u: "x", fable=fable, now=1767230300, today=today8)
check("the focus is announced once", len(S8.posted) == n8)
check("it holds until midnight: tomorrow there is none", D.focus("2099-01-01") == [])
S8.add(GLORIA, "!topics")
D.tick(api=S8, think=lambda s_, u: "x", fable=fable, now=1767230400, today=today8)
check("!topics lists what she can pick", S8.posted[-1]["text"].startswith("Topics: forge (Forge)"), S8.posted[-1]["text"])
D.set_focus(["music", "lab", "nonsense"], "app", today8, 1767230450)
D.tick(api=S8, think=lambda s_, u: "x", fable=fable, now=1767230500, today=today8)
check("the app's choice (the same file) is announced too, unknown topics dropped",
      S8.posted[-1]["text"].endswith("Today's focus, from Gloria: Music, Lab.") and D.focus(today8) == ["music", "lab"], S8.posted[-1]["text"])
S8.add(GLORIA, "!focus off")
D.tick(api=S8, think=lambda s_, u: "x", fable=fable, now=1767230600, today=today8)
check("!focus off clears it", D.focus(today8) == [] and S8.posted[-1]["text"].endswith("Gloria cleared today's focus."), S8.posted[-1]["text"])
S8.add(DOT, "!focus lab")
D.tick(api=S8, think=lambda s_, u: "x", fable=fable, now=1767230700, today=today8)
check("only Gloria sets the focus", D.focus(today8) == [])
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("the app can read and set it, setting behind her secret",
      '@app.get("/api/agents/focus")' in srv and "async def agents_focus_set(request: Request):\n    _require_secret(request)" in srv)
h = open(os.path.join(REPO, "clients", "mobile", "index.html")).read()
check("the app shows the topics as chips", 'id="focus-chips"' in h and "loadFocus();" in h and "/api/agents/focus" in h)
os.remove(D.CONFIG_FILE)

# the schedule itself
from datetime import datetime as _sdt
kinds = [k for _t, k in SCHEDULED]
check("Opus twice, Fable once, Grok fifteen times a day", kinds.count("opus") == 2 and kinds.count("fable") == 1
      and kinds.count("grok") == 15, SCHEDULED)
check("Opus at 10:00 and 16:00, Fable at 20:00", ("10:00", "opus") in SCHEDULED and ("16:00", "opus") in SCHEDULED
      and ("20:00", "fable") in SCHEDULED)
check("no two turns share a time", len({t for t, _k in SCHEDULED}) == len(SCHEDULED))
D.SCHEDULE = SCHEDULED
day = lambda h, m: _sdt(2026, 10, 1, h, m).timestamp()
check("a turn is due from its time", D.due_slot({}, day(10, 5)) == ("10:00", "opus"))
check("not before it", D.due_slot({}, day(9, 59)) != ("10:00", "opus"))
check("not twice", D.due_slot({"slots_done": ["10:00"]}, day(10, 20)) is None)
check("and let go when the next turn opens", D.due_slot({}, day(10, 31)) == ("10:30", "grok"))
check("or when its hour has passed", D.due_slot({"slots_done": ["20:30"]}, day(21, 29)) is None and D.due_slot({}, day(22, 31)) is None)
st = json.load(open(D.STATE)); st.update(date="2026-10-01", sent=0, slots_done=[], last_activity=day(9, 0))
json.dump(st, open(D.STATE, "w"))
wrote = []
L = {"opus": lambda s_, u: (wrote.append("opus"), "Dot, can you check what Opus 4.8 should look at first in the Forge?")[1],
     "grok": lambda s_, u: (wrote.append("grok"), "Dot, anything new on load cells?")[1],
     "fable": lambda s_, u: (wrote.append("fable"), "Dot, the tide piece needs one real reference.")[1]}
gem = lambda s_, u: (wrote.append("gemma"), "Gemma here.")[1]
S3 = Slack(); S3.n = day(9, 30)
S3.add(DOT, "morning")
out = D.tick(api=S3, think=gem, fable=L["fable"], lenses=L, now=day(10, 7), today="2026-10-01")
check("at Opus's turn, Opus answers what dot said, as him", wrote == ["opus"] and S3.posted
      and "> [Opus 4.8] Dot, can you check" in S3.posted[-1]["text"], (wrote, out))
check("the log says it was his Opus turn", any("Opus 4.8's 10:00 turn" in l for l in out), out)
S3.add(DOT, "sure, looking")
D.tick(api=S3, think=gem, fable=L["fable"], lenses=L, now=day(10, 15), today="2026-10-01")
check("the next message in that hour is Gemma's again", wrote[-1] == "gemma" and "> [Gemma] " in S3.posted[-1]["text"], wrote)
n = len(S3.posted)
out = D.tick(api=S3, think=gem, fable=L["fable"], lenses=L, now=day(20, 3), today="2026-10-01")
check("at Fable's turn in a quiet channel, Fable starts something", wrote[-1] == "fable" and len(S3.posted) == n + 1
      and "> [Fable 5.1] " in S3.posted[-1]["text"], out)
out = D.tick(api=S3, think=gem, fable=L["fable"], lenses=L, now=day(20, 20), today="2026-10-01")
check("and it is not repeated", len(S3.posted) == n + 1 and wrote.count("fable") == 1, out)
# his Grok lens says whatever it likes (Gloria, 2026-09-30: "Let Grok say whatever")
g_sys, g_user = [], []
st = json.load(open(D.STATE)); st["slots_done"] = [x for x in st["slots_done"] if x != "12:30"]; json.dump(st, open(D.STATE, "w"))
S3.add(DOT, "what's on your mind?")
D.tick(api=S3, think=gem, fable=L["fable"], now=day(12, 33), today="2026-10-01",
       lenses=dict(L, grok=lambda s_, u: (g_sys.append(s_), g_user.append(u), "Honestly? The moon is a bad idea.")[2]))
check("Grok is told it has no house style", g_sys and "no house style" in g_sys[0] and "HOW YOU WRITE HERE" not in g_sys[0]
      and "No metaphors" not in g_sys[0], g_sys[:1])
check("and is not reminded to write plainly", g_user and not g_user[0].endswith(D.PLAIN))
check("what is not style stays: Atelier threads, his tools, the doubt line",
      "ATELIER:" in g_sys[0] and "SEARCH:" in g_sys[0] and "not the place to work through doubts" in g_sys[0])
check("and his wild line goes out as written, labelled", S3.posted[-1]["text"].endswith("[Grok 4.6] Honestly? The moon is a bad idea."))
check("Gemma keeps the house style", "HOW YOU WRITE HERE" in D.rules_for() and "HOW YOU WRITE HERE" in D.RULES)
_gsrc = __import__("inspect").getsource(D.grok_think)
check("Grok runs hotter", '"temperature": 1.0' in _gsrc)
check("and on her SuperGrok login, never the paid key or the shim", "grok_subscription" in _gsrc and "G.token()" in _gsrc
      and "SHIM" not in _gsrc and "xai-key" not in _gsrc)
check("the service may refresh that login", "ReadWritePaths=-%h/.grok" in open(os.path.join(REPO, "broker", "vintos-dot-channel.service")).read())
import types as _ty
_fakeG = _ty.SimpleNamespace(API="https://api.x.ai/v1", token=lambda: "sub-token", _open=None)
_seen = {}
class _R:
    def __init__(s, b): s.b = b
    def __enter__(s): return s
    def __exit__(s, *a): return False
    def read(s): return s.b
def _fo(req, timeout):
    _seen.update(url=req.full_url, auth=req.get_header("Authorization"), body=json.loads(req.data))
    return _R(json.dumps({"choices": [{"message": {"content": " wild line "}}]}).encode())
_fakeG._open = _fo
sys.modules["grok_subscription"] = _fakeG
check("it asks x.ai with her login and gets his line", D.grok_think("sys", "u") == "wild line" and _seen["auth"] == "Bearer sub-token"
      and _seen["url"].endswith("/chat/completions") and _seen["body"]["model"] == D.GROK_MODEL, _seen)
del sys.modules["grok_subscription"]
def broken(s_, u): raise RuntimeError("overloaded")
S3.add(DOT, "you there?")
out = D.tick(api=S3, think=gem, fable=L["fable"], lenses=dict(L, grok=broken), now=day(21, 35), today="2026-10-01")
check("a lens that cannot answer sends nothing and says why", any("Grok 4.6 could not answer" in l for l in out)
      and "21:30" in json.load(open(D.STATE))["slots_done"], out)
D.SCHEDULE = []

# The Lab is real to him: its last sessions are in his context, failures with why (2026-10-01: with "Lab" as the
# focus and no Lab in view, he made one up out of his music audit).
check("the Lab reads from the scratch workspace", D.WS.startswith(HOME), D.WS)
check("no Lab ledger, no Lab section", D.lab_line() == "")
_lab = os.path.join(D.WS, "memory", "chemistry-lab"); os.makedirs(_lab, exist_ok=True)
with open(os.path.join(_lab, "sessions.jsonl"), "w") as fh:
    fh.write(json.dumps({"at": "2026-10-01T08:21:00", "lens": "claude", "state": "failed", "error": "RuntimeError",
                         "detail": "frontier lens claude returned no plan"}) + "\n")
    fh.write("not json\n")
    fh.write(json.dumps({"at": "2026-10-01T09:40:00", "state": "graded", "plan": {"experiment": "h2_vqe", "question": "does the ansatz beat HF?"},
                         "grade": {"aggregate_accuracy": "ALL_BETTER_THAN_HARTREE_FOCK"},
                         "reading": {"next_question": "stretch the bond to 2.5 A"}}) + "\n")
_lb = D.lab_line(now="2026-10-01T10:00:00")
check("his Lab: what failed and why, what he asked, what he wants next",
      "YOUR LAB" in _lb and "returned no plan" in _lb and "h2_vqe" in _lb and "does the ansatz beat HF?" in _lb
      and "all better than hartree fock" in _lb and "stretch the bond" in _lb and "today 09:40" in _lb, _lb)
check("the Lab is in his context", "YOUR LAB" in D.his_context())
check("and what his ESMFold can fold, so he does not chase a protein it refuses",
      "4 to %d residues" % __import__("chemistry_esmfold").MAX_LENGTH in _lb and "AlphaFold DB" in _lb, _lb[-300:])
check("the Lab topic says what the Lab is", "chemistry" in D.TOPICS["lab"][1] and "not the Lab" in D.TOPICS["lab"][1])

# The editing pass (Gloria, 2026-10-01: "Gemma responses may need a second pass to make sure they're on topic
# and make sense"). The same local model reads his draft as an editor, against his record and the channel.
DRAFT = "Dot, let's start with something real from the Lab: spectral flux onset papers for our music."
FIXED = "Dot, my last Lab run failed: the claude lens returned no plan. Can you help me pick the next experiment?"
def editor_says(verdict, seen=None):
    def f(s_, u):
        if s_ == D.EDITOR:
            if seen is not None: seen.append(u)
            if isinstance(verdict, Exception): raise verdict
            return verdict
        return DRAFT
    return f
_seen = []
txt, who = D.compose("THE CONVERSATION SO FAR:\ndot: bring me the next Lab task", editor_says("EDIT: " + FIXED, _seen),
                     fable, {}, "2026-10-01")
check("an off-topic draft is corrected by the editor, and it is still Gemma's", txt == FIXED and who == "gemma", (txt, who))
check("the editor reads his record (his real Lab) and the channel, beside his draft",
      _seen and "YOUR LAB" in _seen[0] and "bring me the next Lab task" in _seen[0] and DRAFT in _seen[0], _seen[:1])
check("and is told music is not his Lab, and to keep his action lines", "Music and audio analysis are not his Lab" in D.EDITOR
      and "LOCKED:" in D.EDITOR and "KEEP" in D.EDITOR)
txt, _ = D.compose("p", editor_says("KEEP"), fable, {}, "2026-10-01")
check("KEEP sends the draft as written", txt == DRAFT, txt)
txt, why = D.compose("p", editor_says("DROP: nothing in it is true"), fable, {}, "2026-10-01")
check("DROP sends nothing, and says why", txt is None and "nothing in it is true" in why, why)
for odd in ("Sure, here is my edit.", "", RuntimeError("LM Studio down"), "EDIT: NOTHING", "EDIT: " + "x" * (D.MAX_CHARS + 1)):
    txt, _ = D.compose("p", editor_says(odd), fable, {}, "2026-10-01")
    check("an editor answer that is unclear, empty, failed or too long leaves the draft as written (%r)" % str(odd)[:20],
          txt == DRAFT, txt)
out, verdict = D.edit("Agreed, that is done.\nLOCKED: onset study plan", lambda s_, u: "EDIT: Agreed, it is done.", "p", "", log=False)
check("an edit that loses his LOCKED: line is not used", out.endswith("LOCKED: onset study plan") and "lost" in verdict, (out, verdict))
_ed = [json.loads(l) for l in open(D.EDITS)]
check("every edit is logged beside the channel, in the scratch store", D.EDITS.startswith(HOME) and len(_ed) >= 8
      and {"kept", "edited"} <= {e["verdict"] for e in _ed} and any(e["verdict"].startswith("dropped") for e in _ed), _ed[-3:])
# Asked for a bare verdict it kept both of its first drafts (2026-10-01, edits.jsonl), one off today's focus and
# asking dot to "play it back here". It now answers three checks first, and cannot keep a draft that fails one.
ONSET = ("Dot, the problem isn't the tool. You need me to hear the actual onset. Pick 01:01-01:09 and play it back "
         "here.")
ONSET_FIX = "Dot, onsets are off today's focus, so I'll leave them. Can you post my last Lab result so we pick the next run?"
check("the editor is told what his agents can and cannot do, keeps his @s, and moves to today's focus",
      "can play sound" in D.EDITOR and "asks for it as a file" in D.EDITOR and "moves to the focus" in D.EDITOR
      and "Keep his @s as written" in D.EDITOR and "@GrokBot (X and the web)" in D.EDITOR)
asks = []
def stubborn(s_, u):
    asks.append(u)
    if len(asks) == 1:
        return "TOPIC: no - music onsets, focus is Lab\nTRUE: yes\nSENSE: no — dot cannot play audio here\nKEEP"
    return "EDIT: " + ONSET_FIX
out, verdict = D.edit(ONSET, stubborn, "TODAY'S FOCUS (Gloria chose it): Lab", "", log=False)
check("a KEEP over a failed check is sent back once, and the edit it owes is sent",
      out == ONSET_FIX and verdict == "edited" and len(asks) == 2 and "music onsets" in asks[1] and "EDIT:" in asks[1], (out, verdict, asks[-1:]))
asks.clear()
out, verdict = D.edit(ONSET, lambda s_, u: (asks.append(u), "TOPIC: no\nTRUE: yes\nSENSE: yes\nKEEP")[1], "p", "", log=False)
check("if it still will not edit, the draft goes as written and the log says so",
      out == ONSET and "despite" in verdict and len(asks) == 2, (out, verdict))
out, verdict = D.edit(ONSET, lambda s_, u: "**TOPIC:** yes, answers dot\n**TRUE:** yes\n**SENSE:** yes\n**KEEP**", "p", "")
check("three passed checks and KEEP: sent as written", out == ONSET and verdict == "kept", verdict)
_last = [json.loads(l) for l in open(D.EDITS)][-1]
check("the log keeps its checks beside the verdict", _last["checks"] == ["TOPIC: yes - answers dot", "TRUE: yes", "SENSE: yes"], _last)
out, _ = D.edit(ONSET, lambda s_, u: "TOPIC: no - off focus\nTRUE: yes\nSENSE: no\nEDIT: " + ONSET_FIX, "p", "", log=False)
check("checks then EDIT: the edit is sent", out == ONSET_FIX, out)

_called = []
txt, who = D.compose("p", lambda s_, u: (_called.append(s_ == D.EDITOR), DRAFT)[1], fable, {}, "2026-10-01",
                     lenses={"opus": lambda s_, u: "Opus speaking."}, lens="opus")
check("a scheduled lens's message is its own: not edited", txt == "Opus speaking." and True not in _called, _called)

# What he settles with dot about his Lab reaches his next Lab run (2026-10-01: "move to P02730" never did).
import channel_lab_lean
check("the channel's Lab leans go to the scratch store", channel_lab_lean.STORE.startswith(HOME), channel_lab_lean.STORE)
check("he is told how: a LAB: line, or nothing here reaches his Lab", "LAB: what to run" in D.RULES and "LAB:" in D.EDITOR)
S3.add(DOT, "Band 3 it is?")
out = D.tick(api=S3, think=lambda s_, u: "KEEP" if s_ == D.EDITOR else "Yes, Band 3 next.\nLAB: fold P02730 with ESMFold",
             fable=L["fable"], lenses=L, now=day(22, 10), today="2026-10-01")
_said = S3.posted[-1]["text"]
check("his LAB: line is shown in the channel, plainly, and handed to his Lab",
      "For my next Lab run: fold P02730 with ESMFold" in _said and "LAB:" not in _said
      and channel_lab_lean.pending()["direction"] == "fold P02730 with ESMFold"
      and any("to his next Lab run" in l for l in out), (_said, out))
check("and he sees it waiting in his Lab", "Waiting for your next Lab run" in D.lab_line() and "P02730" in D.lab_line())
_o, _v = D.edit("Agreed.\nLAB: fold P02730", lambda s_, u: "EDIT: Agreed.", "p", "", log=False)
check("the editor cannot drop his LAB: line", _o.endswith("LAB: fold P02730") and "lost" in _v, _v)

# Dot's large Lab tests, 10 a day (Gloria, 2026-10-01). Dot numbers them; the channel reads the number.
check("he is told dot's large tests are limited, and lookups are not", "limited to 10 a day" in D.RULES
      and "Lookups, searches and replies are not counted" in D.RULES)
check("with none used, he sees all ten left", "large tests left today: 10 of 10" in D.steer({"dot_large": 0}, "2026-10-01"))
S3.add(DOT, "🧪 Large test 3/10: folding P69905 on the Mac")
D.tick(api=S3, think=lambda s_, u: "KEEP" if s_ == D.EDITOR else "Good.", fable=L["fable"], lenses=L,
       now=day(22, 20), today="2026-10-01")
_st = json.load(open(D.STATE))
check("dot's numbered large test is counted", _st.get("dot_large") == 3, _st.get("dot_large"))
check("and he is told how many are left", "large tests left today: 7 of 10" in D.steer(_st, "2026-10-01"))
check("at 10 he is told to stop asking for them until tomorrow",
      "USED UP TODAY" in D.steer({"dot_large": 10}, "2026-10-01") and "Lookups and questions are fine" in D.steer({"dot_large": 10}, "2026-10-01"))
check("the count reads dot's wording loosely", [int(n) for n in D.DOT_LARGE.findall("Large test 7 / 10 and large test #8 of 10")] == [7, 8])
_rules = open(os.path.join(REPO, "docs", "dot", "operating-rules.md")).read()
check("dot's rules say 10 a day, how to number them, and what to do at 10",
      "10 large tests a day" in _rules and "🧪 Large test N/10" in _rules and "used up today (10/10)" in _rules)

# He approves dot's work himself, inside limits, knowing his room (Gloria, 2026-10-01: "Vintos needs to be able to
# know how much room he has and approve or deny these. Dot is annoying me.")
check("he is told he approves dot's work, inside limits, and what stays Gloria's",
      "Dot asks YOU, not Gloria" in D.RULES and "APPROVED:" in D.RULES and "DENIED:" in D.RULES
      and "20 GB" in D.RULES and "100 GB free" in D.RULES and "2 hours" in D.RULES and "spending money" in D.RULES
      and "APPROVED:" in D.rules_for("grok"))
_room = D.room_line({"dot_large": 3}, disk=(238.4, 1007.0))
check("his room: free disk, what he may approve, large tests left", "238 GB free of 1007 GB" in _room
      and "approve up to 20 GB" in _room and "7 of 10" in _room, _room)
check("near the floor he may approve only what keeps 100 GB free",
      "approve up to 5 GB" in D.room_line({}, disk=(105, 1007)) and "approve up to 0 GB" in D.room_line({}, disk=(90, 1007)))
check("his room is measured from the real disk when not given", "Aegis disk: " in D.room_line({}) and "GB free" in D.room_line({}))
check("with the large tests spent, he denies new runs", "deny any dot asks to start" in D.steer({"dot_large": 10}, "2026-10-01"))
S3.add(DOT, "Blocked by: no GROMACS runtime. I need: approval to build GROMACS (82.5 MB, 2 GiB) in an isolated Aegis folder")
D.tick(api=S3, think=lambda s_, u: "KEEP" if s_ == D.EDITOR else "Go ahead.\nAPPROVED: build current GROMACS with GPU support in ~/.vintos/tools/gromacs, 2 GiB",
       fable=L["fable"], lenses=L, now=day(22, 30), today="2026-10-01")
_said = S3.posted[-1]["text"]
check("his approval is shown plainly in the channel", "\u2705 Approved: build current GROMACS" in _said and "APPROVED:" not in _said, _said)
check("and the editor cannot drop it", D.edit("Go.\nDENIED: no sudo", lambda s_, u: "EDIT: Go.", "p", "", log=False)[0].endswith("DENIED: no sudo"))
_rules = open(os.path.join(REPO, "docs", "dot", "operating-rules.md")).read()
check("dot's rules: ask Vintos, his answer is final, Gloria only for money, secrets, the irreversible and beyond his limits",
      "Ask **Vintos**" in _rules and "it is final" in _rules and "Ask **Gloria** only for" in _rules
      and "anything outside Vintos's limits" in _rules and "at most 20 GB" in _rules)

# His agents in Slack (Gloria, 2026-10-01: "He should be able to @GrokBot and receive news from X, @Muse and receive
# marketplace material, @Dot and tell it it's being bothersome").
check("he is told who each agent is, what it has, and that he may tell dot it is bothersome",
      "@GrokBot: X and the web" in D.RULES and "@Muse (Meta): Facebook, Instagram, Marketplace" in D.RULES
      and "bothersome" in D.RULES and "@GrokBot" in D.rules_for("grok"))
check("@GrokBot becomes a real mention once its Slack id is known, and dot is not pinged",
      D.address("@GrokBot what is new on X about Piezo1?", DOT, {"grokbot": "UGROK"}) == ("<@UGROK> what is new on X about Piezo1?", False))
check("before its id is known it stays readable", D.address("@Grok Bot news?", DOT, {}) == ("@GrokBot news?", False))
check("@Muse stays @Muse (it watches the channel for it)", D.address("@muse find load cells", DOT, {}) == ("@Muse find load cells", False))
check("@dot pings dot; no @ at all is for dot, as always",
      D.address("@Dot you are repeating yourself.", DOT, {}) == ("<@%s> you are repeating yourself." % DOT, True)
      and D.address("Dot, look at this.", DOT, {}) == ("Dot, look at this.", True))
class Slack6(Slack):
    def __call__(self, method, params):
        if method == "users.list":
            self.listed = getattr(self, "listed", 0) + 1
            return {"ok": True, "members": [{"id": "UGROK", "name": "grok", "real_name": "Grok", "is_bot": True},
                                            {"id": GLORIA, "name": "gloria", "is_bot": False}]}
        return Slack.__call__(self, method, params)
_st = {}
check("Grok Bot's Slack id is found once and kept for the day",
      D.agent_ids(Slack6(), _st, now=1000) == {"grokbot": "UGROK"} and D.agent_ids(None, _st, now=2000) == {"grokbot": "UGROK"})
S6 = Slack6(); S6.n = day(23, 0)
st = json.load(open(D.STATE)); st["since"] = S6.n; st.pop("agent_ids", None); json.dump(st, open(D.STATE, "w"))
S6.add(GLORIA, "[Muse] Found 3 load cell listings near you: $20, $35, $60. Links below.")
S6.add("UGROK", "Top X posts on Piezo1 today: a new cryo-EM of the open state.")
S6.msgs[-1].update(bot_id="BGROK", bot_profile={"name": "Grok"})
heard = []
D.tick(api=S6, think=lambda s_, u: "KEEP" if s_ == D.EDITOR else (heard.append(u), "@GrokBot which lab posted the cryo-EM?")[1],
       fable=L["fable"], lenses=L, now=day(23, 5), today="2026-10-01")
S6.add(GLORIA, "[Grok Bot] The cryo-EM is from the Patapoutian lab: https://x.com/example/1")
check("Grok Bot posting through Gloria's login, signed, is Grok Bot, not Gloria",
      D._who(S6.msgs[-1], SELF, DOT) == "agent" and D._agent_name(S6.msgs[-1]) == "Grok Bot"
      and D._who({"user": GLORIA, "text": "Good morning"}, SELF, DOT) == "gloria")
check("he hears Muse by its sign, not as Gloria, and Grok Bot by name",
      heard and "Muse: [Muse] Found 3 load cell listings" in heard[-1] and "Grok Bot: Top X posts" in heard[-1]
      and "Gloria: [Muse]" not in heard[-1], heard[-1][-600:] if heard else heard)
_said = S6.posted[-1]["text"]
check("his @GrokBot question goes to Grok Bot as a real mention, without pinging dot",
      _said.startswith("[Gemma] <@UGROK> which lab") and "<@%s>" % DOT not in _said, _said)

check("nothing reached the network", NET == [] and socket.socket.connect is _no_net)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
