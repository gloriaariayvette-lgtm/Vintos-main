#!/usr/bin/env python3
"""He carries his work on when nobody writes, and a restart between passes still starts the day (Gloria,
2026-10-08: "I stopped and restarted the day, but nothing moved in Slack"). Slack, the lenses and every sender
are stubs; sockets are refused; scratch workspace."""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="work-turns-"); os.environ["HOME"] = HOME
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
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the channel's stores are scratch ones", D.STATE.startswith(HOME) and D.RESUME_FILE.startswith(HOME))

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
asked = []
def think(system, user):
    if system == D.EDITOR: return "KEEP"
    asked.append(user)
    return "Packing next.\nRUN: {\"skill\": \"fold_read\", \"model\": \"Q86SQ4\", \"range\": [41, 149]} for RW-0000cafe"
def tick(now): return D.tick(api=S, think=think, fable=lambda *a: "x", now=now, today="2026-10-08")

tick(5000)                                   # starts listening
st = json.load(open(D.STATE))
st["room_work"] = {"open": [{"id": "RW-0000cafe", "goal": "ESMFold Q86SQ4 CUB 41-149 packing", "done_when": "packing assessed",
                             "opened": 4000, "touched": 4000, "asks": [], "returns": [], "steps": [], "next": "compare to 6V55"}],
                   "history": [], "goal": {"id": "RC-00000001", "goal": "the CUB domain of ADGRG6, folded and judged",
                                            "done_when": "a packing verdict", "opened": 4000, "touched": 4000, "routes": []}}
st["last_activity"] = 5000; json.dump(st, open(D.STATE, "w"))

n = len(S.posted)
out = tick(5000 + 5 * 60)
check("too soon after the last activity: no work turn yet", len(S.posted) == n, out)
out = tick(5000 + 25 * 60)
check("nobody has written, his work is due: he takes a work turn and posts the step", len(S.posted) == n + 1
      and any("work turn" in l for l in out) and "RUN" in S.posted[-1]["text"] + str(out) and "due its next step" in asked[-1], (out, S.posted[-1:]))
n = len(S.posted)
out = tick(5000 + 30 * 60)
check("not again within twenty minutes", len(S.posted) == n, out)
st = json.load(open(D.STATE)); st["room_work"]["open"][0]["paused_until"] = 10 ** 10; st["room_work"]["goal"]["touched"] = 1
json.dump(st, open(D.STATE, "w"))
n = len(S.posted)
tick(5000 + 90 * 60)
check("a work paused for a cause is not pressed; with a place free he is asked for the campaign's next work beside it",
      "waits on something outside you" in asked[-1] and "due its next step" not in asked[-1].split("== YOUR WORK")[0], asked[-1][-800:])
out = tick(5000 + 97 * 60)
check("that turn was held, so the very next pass tries again (8 October: held at 04:26, next try 04:54)",
      any("tried again" in l for l in out), out)
out = tick(5000 + 104 * 60)
check("once: held again, it waits for the usual spacing", not any("work turn" in l for l in out), out)

# a stop and a start between two passes, from the app (the switch removes paused.json and leaves resumed.json)
D.set_paused(True, "app", now=20000); D.set_paused(False, "app", now=20010)
check("switching the day back on leaves a mark", json.load(open(D.RESUME_FILE))["at"] == 20010)
n = len(S.posted)
out = tick(20100)
check("the restart is seen on the next pass: the day is said to have started", any("started the day again" in p["text"] for p in S.posted[n:])
      and any("stopped and started again" in l for l in out), (out, S.posted[n:]))
n = len(S.posted)
tick(20200)
check("and said once", not any("started the day again" in p["text"] for p in S.posted[n:]))
# Opus 5.5 always thinks; at 1500 tokens its answer could be all thinking and no text, read as "he let it be"
import claude_cache
calls = []
def all_thinking(model, system, user, max_tokens, caller="", effort=None, **k):
    calls.append((model, max_tokens, effort)); claude_cache.LAST.clear(); claude_cache.LAST.update(stop="max_tokens", out=max_tokens)
    return ""
claude_cache.ask = all_thinking
try:
    D.opus_think("s", "u", D.KICKOFF_MODEL); raised = ""
except RuntimeError as e:
    raised = str(e)
check("Opus 5.5 is asked to think as little as it can, with room to write after", calls and calls[-1] == (D.KICKOFF_MODEL, 6000, "low"), calls)
check("an answer that was all thinking is a failure said as such, not 'nothing to say'", "all thinking" in raised, raised)
D.set_paused(True, "app", now=30000); D.set_paused(False, "app", now=30010)
n = len(S.posted)
out = tick(30100)
check("a kickoff Opus 5.5 could not write is written by Gemma instead, so the restart is not silent",
      any("could not answer" in l for l in out) and len(S.posted) >= n + 2 and "[Gemma]" in S.posted[-1]["text"], (out, S.posted[n:]))
src = open(os.path.join(REPO, "bin", "server.py")).read()
check("the app's switch leaves the same mark", "resumed.json" in src)
# 8 October, after 08:13: LM Studio answered without a reply, four Gemma turns went silent, nothing stood behind it
import requests
class _NoReply:
    def json(self): return {"error": "model not loaded"}
_post = requests.post; requests.post = lambda *a, **k: _NoReply()
try:
    D.local_think("s", "u"); said = ""
except RuntimeError as e:
    said = str(e)
requests.post = _post
check("LM Studio with no reply is said plainly, not as 'choices'", "model not loaded" in said, said)
def dead_gemma(system, user):
    if system == D.EDITOR: return "KEEP"
    raise RuntimeError("LM Studio gave no reply: model not loaded")
D.ROTATION = ("gemma",)
st = json.load(open(D.STATE)); st["room_work"]["open"][0].pop("paused_until", None); st["last_work_turn"] = 0
st["last_activity"] = 1; json.dump(st, open(D.STATE, "w"))
n = len(S.posted)
out = D.tick(api=S, think=dead_gemma, fable=lambda *a: "x", now=60000, today="2026-10-08",
             lenses={"grok": lambda s_, u_: "Grok here: RUN: {\"skill\": \"fold_read\"} for RW-0000cafe"})
check("when Gemma cannot answer, Grok writes his turn", len(S.posted) == n + 1 and "Gemma could not answer" in " ".join(out)
      and "Grok" in S.posted[-1]["text"], (out, S.posted[n:]))
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
