#!/usr/bin/env python3
"""His Claude calls cache what does not change (Gloria, 2026-10-05: "I want Anthropic to have what it can cached. He
is expensive."): claude_cache.py, his Slack prompts in dot_channel, and the Study fix's Fable rounds.

Scratch HOME and workspace; the Anthropic endpoint is a stub that records each request; every socket is refused (a loopback attempt is refused too; only an outside one fails the suite).
"""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="claude-cache-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_STUDY_WORKBENCH"] = os.path.join(HOME, "workbench")
os.environ["VINTOS_CHECKOUT"] = os.path.join(HOME, "Vintos-main")
os.environ.pop("ANTHROPIC_API_KEY", None)
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX and not str((a[0] if a else ("",))[0]).startswith("127."): NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import claude_cache as C

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("the usage log is a scratch file", C.USAGE.startswith(HOME), C.USAGE)

SENT = []
class Reply:
    def __init__(self, usage): self.usage = usage
    def json(self): return {"content": [{"type": "text", "text": "the words"}], "usage": self.usage}
def post(url, timeout=None, json=None, headers=None):
    SENT.append({"url": url, "body": json, "headers": headers})
    return Reply({"input_tokens": 40, "cache_read_input_tokens": 9000 if len(SENT) > 1 else 0,
                  "cache_creation_input_tokens": 0 if len(SENT) > 1 else 9000, "output_tokens": 120})

def marks(body):
    blocks = list(body.get("system") or []) + [b for m in body["messages"] for b in m["content"]]
    return [bool(b.get("cache_control")) for b in blocks]

# --- the request ----------------------------------------------------------------------------------------------------
sys_p = C.Prompt("everything in its usual order", ["the rules, unchanged", "the time and today"])
usr_p = C.Prompt("the room and now write", ["the room", "now write"])
b = C.body("claude-opus-5-5", sys_p, usr_p, 100)
check("each system piece is a cache point; every user piece but the last", marks(b) == [True, True, True, False], marks(b))
check("Claude is sent the pieces, other models the plain words", b["system"][0]["text"] == "the rules, unchanged"
      and str(sys_p) == "everything in its usual order")
plain = C.body("claude-opus-5-5", "a one-off system", "a one-off ask", 100)
check("a plain string is sent unmarked (a one-off call would only pay the write)", marks(plain) == [False, False], marks(plain))
many = C.body("claude-opus-5-5", C.Prompt("s", ["a", "b", "c", "d", "e"]), C.Prompt("u", ["f", "g", "h"]), 100)
check("never more than the API's four cache points", sum(marks(many)) == 4, marks(many))

text = C.ask("claude-opus-5-5", sys_p, usr_p, 100, caller="slack:test", post=post, key="k-test")
check("ask returns Claude's text and sends to the Messages API", text == "the words" and SENT[0]["url"] == C.URL)
row = json.loads(open(C.USAGE).read().splitlines()[-1])
check("what the call used is logged, never its words", row["caller"] == "slack:test" and row["cache_write"] == 9000
      and "the words" not in open(C.USAGE).read() and "the room" not in open(C.USAGE).read(), row)
try:
    C.ask("claude-opus-5-5", "s", "u", 1, post=post); check("no key raises", False)
except RuntimeError as exc:
    check("no key raises, as the callers it replaced did", "no Anthropic key" in str(exc))
C.ask("claude-opus-5-5", sys_p, usr_p, 100, caller="slack:test", post=post, key="k-test")
summary = C.today()
check("today's summary says calls, cache reads and an estimated cost", "slack:test: 2 calls" in summary
      and "read from cache" in summary and "$" in summary, summary)

# --- his Slack prompts ----------------------------------------------------------------------------------------------
import dot_channel as D
WS = os.environ["SPARK_WORKSPACE"]
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos. " * 40)
open(os.path.join(WS, "CAPABILITIES.md"), "w").write("I can paint. " * 40)
ctx = D.his_context()
check("his context reads the same for every model", ctx.startswith("== NOW ==") and "== SOUL.md ==" in ctx)
check("... and keeps apart what changes rarely", ctx.stable.startswith("== SOUL.md ==") and "== CAPABILITIES.md ==" in ctx.stable
      and "== NOW ==" not in ctx.stable and ctx.live.startswith("== NOW =="), (ctx.stable[:80], ctx.live[:80]))

SEEN = []
def lens(system, user):
    SEEN.append((system, user))
    return "SEARCH: cats" if len(SEEN) == 1 else "I looked it up and I want to paint a cat."
out, who = D.compose("THE ROOM: Gloria said hello.", lambda s, u: "", None, {}, "2026-10-05",
                     search=lambda q: [{"title": "Cats", "description": "cats are cats", "url": "https://cats.invalid"}], lenses={"opus55": lens, "haiku55": lens}, lens="opus55")
check("a Slack turn with a look-up still writes", out and who == "haiku55", (out, who))
(s1, u1), (s2, u2) = SEEN
check("other models read the prompt as before: the time, his context, then the rules",
      str(s1).startswith("== NOW ==") and str(s1).endswith("\n\n---\n\n" + D.rules_for("opus55"))
      and str(s1).index("== SOUL.md ==") < str(s1).index("\n\n---\n\n"))
check("Claude is sent the rules and what changes rarely first, the time after",
      s1.pieces[0].startswith(D.rules_for("opus55")) and "== SOUL.md ==" in s1.pieces[0] and "== NOW ==" not in s1.pieces[0]
      and s1.pieces[1].startswith("== NOW =="), s1.pieces[0][:120])
check("his look-up sends the same start again, so it is read from cache",
      s1.pieces == s2.pieces[:1] + s1.pieces[1:] and s1.pieces[0] == s2.pieces[0]
      and u1.pieces[0] == u2.pieces[0] == "THE ROOM: Gloria said hello." and "cats are cats" in u2.pieces[1], (u1.pieces, u2.pieces))
SENT.clear()
D_ask = C.ask
C.ask = lambda model, system, user, max_tokens, caller="", **k: D_ask(model, system, user, max_tokens, caller=caller, post=post, key="k-test")
D.opus_think(s1, u1, "claude-opus-5-5")
check("Slack caches only its stable prefix, not the changing day and room",
      marks(SENT[0]["body"]) == [True, False, False, False], marks(SENT[0]["body"]))

# --- the Study fix's Fable rounds -----------------------------------------------------------------------------------
import study_fix as S
check("the Study's paths are scratch ones", all(p.startswith(HOME) for p in (S.QUEUE, S.WORKBENCH)))
os.makedirs(S.WORKBENCH, exist_ok=True)
open(os.path.join(S.WORKBENCH, "CLAUDE.md"), "w").write("Repoint every path; stub anything that sends.")
open(os.path.join(S.WORKBENCH, "thing.py"), "w").write("x = 1\n")
ASKED = []
def fable(system, user):
    ASKED.append(user)
    return '{"read": ["thing.py"]}' if len(ASKED) == 1 else '{"refuse": "fixture"}'
plan, context = S.plan_fix({"what": "make x two"}, ask=fable, root=S.WORKBENCH)
check("every Fable round of one fix starts with the same rules, ask and file list, marked for cache",
      len(ASKED) == 2 and ASKED[0].pieces[0] == ASKED[1].pieces[0] and "make x two" in ASKED[0].pieces[0]
      and "WHAT YOU READ SO FAR" in ASKED[1].pieces[1], [a.pieces[0][:60] for a in ASKED])
check("... and the context a repair is given keeps that same start", context.pieces[0] == ASKED[0].pieces[0])

check("the deploy installs claude_cache.py", " claude_cache.py " in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
