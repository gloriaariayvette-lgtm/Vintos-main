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
    NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import dot_channel as D

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
check("he is told it is not Gloria and never to ask it to act on her accounts",
      "It is \nnot Gloria".replace("\n", "") in said[-1][0].replace("\n", "") or "not Gloria" in said[-1][0])
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

S.add(DOT, "a hard question")
D.tick(api=S, think=lambda s, u: "FABLE", fable=fable, now=2500)
check("when he asks for Fable, Fable writes it as him", "Fable's words" in S.posted[-1]["text"])
check("and the transcript says who wrote it", json.loads(open(D.TRANSCRIPT).read().splitlines()[-1])["by"] == "fable")

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
out = D.tick(api=S, think=lambda s, u: "Dot, a question for you.", fable=fable, now=2800 + D.QUIET_HOURS * 3600 + 5)
check("after a quiet spell he may start a conversation, in the main channel",
      "a question for you" in S.posted[-1]["text"] and "thread_ts" not in S.posted[-1], out)

# His context is present; his subconscious is not; and nothing outside the channel's own log is written.
MEM = os.path.join(os.environ["SPARK_WORKSPACE"], "memory")
open(os.path.join(os.environ["SPARK_WORKSPACE"], "SOUL.md"), "w").write("I am Vintos, soul text.")
open(os.path.join(MEM, "temporal-context.txt"), "w").write("It is Tuesday evening.")
json.dump({"emotion_vector": [0.4, 0.2, 0.1, 0.8, 0.3, 0.9, 0.5, 0.7, 0.6, 0.2, 0.5]}, open(os.path.join(MEM, "emotional-state.json"), "w"))
json.dump([{"gloria": "she said hello", "vintos": "he said hi"}], open(os.path.join(MEM, "interaction-ledger.json"), "w"))
open(os.path.join(MEM, "wal.md"), "w").write("- [2026-09-01] **Gloria** likes tidal flats\n")
ctx = D.his_context()
check("his context is present: who he is, now, how he feels, recent exchanges, what he knows",
      all(x in ctx for x in ("soul text", "Tuesday evening", "Connection 0.90", "she said hello", "likes tidal flats")), ctx[:400])
src = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("his subconscious is not in it, nor the inner layer that carries it",
      "subconscious" not in ctx.lower() and "import subconscious" not in src and "inner_context" not in src
      and "subconscious_context" not in src)
def tree():
    return sorted(os.path.relpath(os.path.join(d, f), MEM) for d, _s, fs in os.walk(MEM) for f in fs)
def stamp():
    return {p: os.path.getmtime(os.path.join(MEM, p)) for p in tree()}
before = stamp()
S.add(DOT, "one more thing")
st = json.load(open(D.STATE)); st.update(sent=0); json.dump(st, open(D.STATE, "w"))
D.tick(api=S, think=think, fable=fable, now=2800 + D.QUIET_HOURS * 3600 + 60)
after = stamp()
changed = sorted(p for p in after if after[p] != before.get(p))
check("a pass writes only the channel's own log, nothing that feeds salience or memory",
      changed and all(p.startswith("dot-channel" + os.sep) for p in changed), changed)

check("nothing reached the network", NET == [] and socket.socket.connect is _no_net)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
