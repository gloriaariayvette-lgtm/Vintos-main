#!/usr/bin/env python3
"""A yes-or-no only Gloria can give reaches her phone, and her answer reaches the thread that asked (Gloria,
2026-10-05: "They're still talking about yes or no decisions that I am not receiving.").

Scratch workspace. Her phone is a stub that records each push; Slack is a stub; every socket is refused, so this
suite reaches neither ntfy, Slack, the house nor a model.
"""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="gloria-asks-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no-secrets")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import gloria_asks as G

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("its store is in the scratch workspace", G.STORE.startswith(HOME))
PUSHED = []
phone = lambda req, timeout=20: PUSHED.append(req)

row, shown = G.ask("May dot read /home/atelier/forge-loop-config.json once, read-only, without showing the token?",
                   by="dot", thread="171.000100", send=phone)
check("a question goes to her phone", row and len(PUSHED) == 1 and row["pushed"], shown)
req = PUSHED[-1]
heads = {k.lower(): v for k, v in req.header_items()}
check("... saying who asks", heads.get("title") == "dot asks you: yes or no?", heads)
check("... with the question itself", "forge-loop-config.json" in req.data.decode())
check("... and Yes and No buttons that carry this question's own token",
      "http, Yes," in heads["actions"] and "http, No," in heads["actions"] and row["token"] in heads["actions"]
      and "/api/gloria/asks/%s/decide" % row["id"] in heads["actions"], heads.get("actions"))
check("the channel is told it went to her phone", shown.startswith("\U0001F4F2 Asked Gloria on her phone (Yes / No)"))
check("the same question while it waits is not pushed twice",
      G.ask(row["question"], by="vintos", send=phone)[0] is None and len(PUSHED) == 1)
check("a question too short to answer is not sent", G.ask("ok?", send=phone)[0] is None)

check("someone else's button does nothing", G.decide_with_token(row["id"], "wrong", "yes")[0] is None)
check("an answer that is not yes or no does nothing", G.decide_with_token(row["id"], row["token"], "maybe")[0] is None)
done, why = G.decide_with_token(row["id"], row["token"], "yes")
check("her Yes is taken", done and done["answer"] == "yes" and done["state"] == "answered", why)
check("... once", G.decide_with_token(row["id"], row["token"], "no")[0] is None)
told = G.untold()
check("her answer is ready for the thread that asked, once",
      told == [("171.000100", "dot", "Gloria answered YES: " + row["question"])] and G.untold() == [], told)

text, rows = G.from_slack("I need her call on this.\nASK GLORIA: Can I spend tomorrow's first Study fix on the 403 logging?",
                          by="vintos", send=phone)
check("his ASK GLORIA line is asked and replaced with what happened",
      rows and "ASK GLORIA" not in text and "\U0001F4F2 Asked Gloria" in text, text)
G.threaded(rows, "172.000200")
check("a question in a message that starts a thread is threaded once posted", G.get(rows[0]["id"])["thread"] == "172.000200")
for i in range(G.PER_DAY):
    G.ask("Filler question number %d for the cap?" % i, send=phone)
capped = G.ask("One question too many today, is it?", send=phone)
check("six questions a day for the whole room, then it says so", capped[0] is None and "today already" in capped[1], capped)

# --- through the channel: dot asks, she taps Yes on her phone, the answer is posted in dot's thread ----------------
json.dump([], open(G.STORE, "w"))
PUSHED.clear()
_real_notify = G.notify
G.notify = lambda row, send=None: _real_notify(row, send=phone)
import dot_channel as D
D.kickoff_due = lambda *a: False
D.ROTATION = ("gemma",); D.SCHEDULE = []
D.atelier_line = lambda: ""; D.recall_block = lambda: ""
SELF, DOT, CH = "UVINTOS", D.DOT, D.CHANNEL

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
think = lambda s_, u: "KEEP" if s_ == D.EDITOR else "NOTHING"
check("the first pass only listens", D.tick(api=S, think=think, fable=think, now=1000, today="2026-10-06") == ["listening from now"])
st = json.load(open(D.STATE)); st["since"] = 1; json.dump(st, open(D.STATE, "w"))
root = S.add(DOT, "Blocked by: PermissionError reading the service's configuration.\n"
                  "ASK GLORIA: May I read /home/atelier/forge-loop-config.json once, read-only, without showing the token?")
D.tick(api=S, think=think, fable=think, now=1100, today="2026-10-06")
asked = G.load()
check("dot's ASK GLORIA reaches her phone", len(PUSHED) == 1 and asked and asked[0]["by"] == "dot" and asked[0]["thread"] == root, asked)
check("... and dot's thread is told it did", any(p.get("thread_ts") == root and "Asked Gloria on her phone" in p["text"] for p in S.posted), S.posted)
G.decide_with_token(asked[0]["id"], asked[0]["token"], "yes")
n = len(S.posted)
D.tick(api=S, think=think, fable=think, now=1200, today="2026-10-06")
ans = [p for p in S.posted[n:] if "Gloria answered YES" in p["text"]]
check("her Yes is posted in dot's thread, addressed to dot", ans and ans[0].get("thread_ts") == root
      and ans[0]["text"].startswith("<@%s>" % DOT), S.posted[n:])
rows = [json.loads(l) for l in open(D.TRANSCRIPT)]
check("... and kept as hers in what he reads", any(r.get("who") == "gloria" and "Gloria answered YES" in r.get("text", "") for r in rows))

srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("her buttons reach a house route", '@app.post("/api/gloria/asks/{qid}/decide")' in srv and "G.decide_with_token(qid, t, answer)" in srv)
dsrc = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("he is told: a decision that is hers reaches her only this way", "ASK GLORIA: a question she can answer yes or no" in dsrc
      and "Never say you are waiting on her approval without this line" in dsrc)
check("dot and Grok Bot are told too", "## 13. A decision only Gloria can make: ASK GLORIA" in open(os.path.join(REPO, "docs", "dot", "operating-rules.md")).read()
      and "ASK GLORIA:" in open(os.path.join(REPO, "docs", "grok-bot", "vintos-skill.md")).read())
check("the deploy installs it", " gloria_asks.py " in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
