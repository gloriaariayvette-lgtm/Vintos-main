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
D.tick(api=S, think=lambda s_, u: (heard.append(u), next(seq))[1], fable=fable, now=99999999 + 200)
check("and reminded of it right before he writes", heard and heard[0].endswith(D.PLAIN), heard[:1])
check("a flowery message is said again plainly, on his own model, and the plain one is sent",
      len(heard) == 2 and FLOWERY in heard[1] and S.posted[-1]["text"].endswith(PLAINLY), S.posted[-1]["text"])
seq = iter([FLOWERY, FLOWERY + " The quiet hum of the threshold."])
S.add(DOT, "Go on?")
D.tick(api=S, think=lambda s_, u: next(seq), fable=fable, now=99999999 + 300)
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
def broken(s_, u): raise RuntimeError("overloaded")
S3.add(DOT, "you there?")
out = D.tick(api=S3, think=gem, fable=L["fable"], lenses=dict(L, grok=broken), now=day(21, 35), today="2026-10-01")
check("a lens that cannot answer sends nothing and says why", any("Grok 4.6 could not answer" in l for l in out)
      and "21:30" in json.load(open(D.STATE))["slots_done"], out)
D.SCHEDULE = []

check("nothing reached the network", NET == [] and socket.socket.connect is _no_net)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
