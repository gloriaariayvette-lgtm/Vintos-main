#!/usr/bin/env python3
"""Six defects in what reached his daily-inner file, and one in the link reader (review of 30 October):
an empty Wonder line, a Ghost Branch carrying its cut-off text twice, his own letter replies read back as new
letters, a web search written twice and a question for Gloria searched on the web, a Forge receipt that said
"unreachable" over a list that was only large, a "To Gloria:" line that reached no one, and one DNS blink said
as a dead domain. Scratch HOME; the model, Gmail, ntfy, the Forge and DNS are stubs. All text is synthetic and
nothing here can reach the network."""
import importlib.util, io, json, os, socket, sys, tempfile, types
from datetime import date, datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-daily-inner-fixes-")
WS = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = WS
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no-secrets")

def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request; urllib.request.urlopen = no_network
sys.modules["plugin_gateway"] = types.SimpleNamespace(call=no_network)
sys.modules["emoclaw_utils"] = types.ModuleType("emoclaw_utils")
NET = []
_real_connect = socket.socket.connect
def _no_net(self, a):
    if self.family != socket.AF_UNIX:
        NET.append(a); raise OSError("this suite reaches nothing")
    return _real_connect(self, a)
socket.socket.connect = _no_net
sys.path.insert(0, os.path.join(REPO, "scripts"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, path))
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod)
    return mod


R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:500]) if detail and not ok else ""))


TODAY = date.today().isoformat()

# ── 1. Wonder: a scored pass with no flip found is not a line in his day ─────────────────────────────────────────
X = load("daily_log_extract", "bin/daily-log-extract.py")
check("the extractor writes into the scratch workspace", X.MEMORY.startswith(HOME), X.MEMORY)
json.dump([{"timestamp": TODAY + "T08:15:00", "score": 0.1, "flip_excerpt": ""},
           {"timestamp": TODAY + "T09:30:00", "score": 0.2, "flip_excerpt": "   "},
           {"timestamp": TODAY + "T11:05:00", "score": 0.6, "flip_excerpt": "the lamp was a question, not an answer"},
           {"timestamp": TODAY + "T12:40:00", "score": 0.4, "text": "an older row that kept its text elsewhere"}],
          open(os.path.join(MEM, "wonder-log.json"), "w"))

# ── 4a. Web: a search the journal already holds is not copied into the day again ────────────────────────────────
os.makedirs(os.path.join(MEM, "journal"), exist_ok=True)
Q = "How do paper wasps recognise one another's faces?"
open(os.path.join(MEM, "journal", TODAY + ".md"), "w").write(
    "Some morning lines.\n\n## Web Search — %s\n*Searched at 03:14 PM*\n\nThey learn facial patterns early.\n"
    "\n**Where I stand:** recognition is learned.\n" % Q)
open(os.path.join(MEM, "web-discoveries.md"), "w").write(
    "\n## %s 15:14 — %s\n*Search: paper wasp face recognition*\n\nThey learn facial patterns early.\n\n- [a](https://a.example/x)\n"
    "\n## %s 09:02 — Why do tides lag the moon?\n*Search: tidal lag moon*\n\nFriction and basins.\n"
    "\n## %s 21:40 — %s\n*Search: paper wasp face recognition again*\n\nA second, later search.\n"
    % (TODAY, Q, TODAY, TODAY, Q))
X.build_inner()
day = open(os.path.join(MEM, "daily-inner-life-%s.md" % TODAY)).read()
wonder = day.split("## Wonder", 1)[1].split("\n## ", 1)[0] if "## Wonder" in day else ""
check("a wonder row with a blank excerpt leaves no bare '- [HH:MM] ' line",
      "[08:15]" not in wonder and "[09:30]" not in wonder and all(l.strip() != "-" and not l.rstrip().endswith("]")
                                                                  for l in wonder.splitlines() if l.startswith("- [")), wonder)
check("a real flip is still in the Wonder section", "[11:05] the lamp was a question, not an answer" in wonder, wonder)
check("a row with only 'text' still falls back to it", "[12:40] an older row that kept its text elsewhere" in wonder, wonder)
web = day.split("## Web\n", 1)[1].split("\n## Mirror", 1)[0] if "## Web\n" in day else ""
check("the journal's search is in the day once (Journal), not again under Web",
      day.count("They learn facial patterns early.") == 1 and "15:14" not in web, web)
check("a discovery the journal does not hold is still under Web", "Why do tides lag the moon?" in web, web)
check("the same question searched again hours later is its own discovery and stays", "21:40" in web, web)
check("journal headings are parsed with their 12-hour time", X._journal_web_searches(
      "## Web Search — A question here\n*Searched at 12:05 AM*\n")[0] == ("a question here", 5))

# ── 2. Ghost Branch: the continuation is joined, not glued on after a repeat ──────────────────────────────────────
GB = load("ghost_branches_fixture", "scripts/ghost-branches.py")
J = GB.join_continuation
CUT = "I keep coming back to the same doorway and not going through it because"
rewrite = CUT + " the silence after a question is easier to carry than the answer."
got = J(CUT, rewrite)
check("a continuation that rewrites from the start is kept once", got == rewrite and got.count("I keep coming back") == 1, got)
got = J(CUT, "I keep coming back to the same doorway, and this time I want to name it plainly: I am afraid.")
check("a restart that diverges after the opening is not appended to the cut-off",
      got.count("I keep coming back") == 1 and got.endswith("I am afraid."), got)
got = J(CUT, "The silence is easier.")
check("a real continuation is joined with one space at the seam", got == CUT + " The silence is easier.", got)
check("the old glue ('becauseThe') never appears", "becauseThe" not in got)
got = J("I asked myself what the open window meant", "what the open window meant to me, and why I left it.")
check("a continuation that picks up a few words back drops the repeated words",
      got == "I asked myself what the open window meant to me, and why I left it.", got)
got = J("It felt like nothing moved becau", "because I was holding still.")
check("a partial word at the cut is not doubled", got == "It felt like nothing moved because I was holding still.", got)
check("punctuation at the seam takes no space", J("I said it plainly", ", then waited.") == "I said it plainly, then waited.")
check("a short word followed by a longer one is two words, not a repeat", J("I reached for the", "then let go.") == "I reached for the then let go.")
check("whitespace already at the seam is kept as it is", J(CUT + " ", "and then I did.") == CUT + " and then I did.")
check("an empty continuation leaves the cut-off as it was", J(CUT, "  ") == CUT)

class _SSE:
    def __init__(self, tokens):
        self.buf = b"".join(b"data: " + json.dumps({"choices": [{"delta": {"content": t}}]}).encode() + b"\n" for t in tokens) + b"data: [DONE]\n"
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n=-1):
        out, self.buf = (self.buf, b"") if n < 0 else (self.buf[:n], self.buf[n:]); return out
TOKENS = ["I keep coming back to the ", "same doorway and not going ", "through it because ", "I said I would and then ", "did not, and the hall stays ", "long."]
GB.urllib.request.urlopen = lambda req, timeout=None: _SSE(TOKENS)
GB.detect_reversion = lambda acc, pos: {"trigger_type": "fixture", "reversion_pattern": "softening", "local_context": acc[-20:]} if len(acc) > 80 else None
streamed = "".join(TOKENS[:4])
GB.call_llm = lambda messages, temperature=0.9, max_tokens=300: streamed + " this time I name it: I am afraid of the room."
out = {}
GB.stream_ghost([{"role": "user", "content": "x"}], {"id": "plain", "label": "plainness"}, out, 0)
GB.urllib.request.urlopen = no_network
ghost = out[0]["output"]
check("a ghost resumed after a reversion carries its opening once", ghost.count("I keep coming back") == 1
      and ghost.endswith("I am afraid of the room."), ghost)
src = open(os.path.join(REPO, "scripts", "ghost-branches.py")).read()
check("neither seam concatenates the cut-off and the continuation raw", "stream_cutoff + continuation" not in src
      and src.count("join_continuation(stream_cutoff, continuation)") == 2)

# ── 3. His own reply come back into the inbox is not a new letter ──────────────────────────────────────────────
E = load("want_email", "scripts/want_email.py")
check("the mail stores are scratch", E.MEMORY.startswith(HOME) and E.INBOX_LOG.startswith(HOME))
REPLY = ("1. Keep: the tide table, because I am trying to time the walk. 2. Skip: the second gallery, I have seen it. "
         "Bring more tide and weather, less galleries.")
json.dump({"m-letter-1": {"sent": True, "agent": "Muse", "subject": "Re: [Muse] Three finds", "body": REPLY,
                          "thread_id": "t-1"}}, open(E.LETTER_REPLIES, "w"))
E.who_i_am = lambda n: "I am Vintos."
E.links_read = lambda body: []
THOUGHT = []
def think(system, ask, tokens):
    THOUGHT.append(ask)
    return json.dumps({"what": "a letter", "to_me": "useful", "keep": False, "want": ""})
back = {"id": "m-own-1", "from": "\"Vintos\" <me@example.org>", "subject": "Re: [Muse] Three finds", "thread_id": "t-1",
        "date": "Thu, 29 Oct 2026 21:00:00 -0700", "body": REPLY + "\n\nOn Thu, Muse wrote:\n> three finds", "attachments": []}
lines = E.read_mail([back], think=think, want=lambda *a: None)
check("his own reply is not read by the model", THOUGHT == [], THOUGHT)
inner = os.path.join(MEM, "daily-inner-life-%s.md" % TODAY)
check("nothing about it is written into his day", "## I read" not in (open(inner).read() if os.path.exists(inner) else ""))
logged = [json.loads(l) for l in open(E.INBOX_LOG)]
check("it is marked seen as his own reply", logged and logged[-1]["id"] == "m-own-1" and logged[-1]["kind"] == "own_reply"
      and "m-own-1" in E._mail_seen(), logged)
check("the log line says what happened", lines and "own reply" in lines[0], lines)
check("the next check skips it", E.read_mail([back], think=think, want=lambda *a: None) == [] and THOUGHT == [])
fresh = dict(back, id="m-new-1", subject="[Muse] Two more finds", body="1. A lantern walk on Friday.\n2. A paper on moss.")
E.read_mail([fresh], think=think, want=lambda *a: None)
check("a real letter is still read", len(THOUGHT) == 1 and "A lantern walk" in THOUGHT[0])
import received_mail
check("received mail leaves his own reply out", "m-own-1" not in [r["id"] for r in received_mail.rows(path=E.INBOX_LOG)])
check("reply_letters uses the same recognition", "_is_own_reply(r.get(\"body\"), own_bodies)" in open(os.path.join(REPO, "scripts", "want_email.py")).read())

# ── 6. "To Gloria:" is a line for her, like "For Gloria:" ───────────────────────────────────────────────────────
import gloria_asks as G
check("the asks store is scratch", G.STORE.startswith(HOME))
PUSHED = []
phone = lambda req, timeout=20: PUSHED.append(req)
asked = G.plans_from("1. Keep the tide table.\nTo Gloria: the two-room test, Saturday\n", by="vintos", where="letter to Muse", send=phone)
check("a 'To Gloria:' line in a letter reply becomes his plan question", len(asked) == 1 and asked[0]["kind"] == "plan"
      and "the two-room test, Saturday" in asked[0]["question"] and len(PUSHED) == 1, asked)
asked = G.plans_from("**To Gloria:** the felt-only run, this weekend\n", by="vintos", send=phone)
check("bold 'To Gloria:' is read too", len(asked) == 1 and "the felt-only run, this weekend" in asked[0]["question"], asked)
asked = G.plans_from("For Gloria: the lantern walk on Friday evening\n", by="vintos", send=phone)
check("'For Gloria:' is unchanged", len(asked) == 1, asked)
check("'to Gloria' mid-sentence is not a line for her",
      G.plans_from("I will write to Gloria: later, maybe.\n", send=phone) == [] and not G.FOR.search("I wrote to gloria: hi"))
made, notes = E.promises_to_gloria("To Gloria: the hall sensor build, Friday evening\n", "1. a sensor\n", "Muse", want=lambda *a, **k: None)
check("a 'To Gloria:' plan in his reply is carried to plans_from", made == [] and len(notes) == 1
      and len(G.plans_from("\n".join(notes), send=phone)) == 1, (made, notes))
check("the letter reply prompt asks for a 'For Gloria:' line for anything that involves her",
      "\"For Gloria:\"" in E.LETTER_REPLY and "involves Gloria" in E.LETTER_REPLY)

# ── 4b. A curiosity addressed to her goes to her, never to the web ───────────────────────────────────────────────
W = load("vintos_websearch", "bin/vintos-websearch.py")
check("the searcher's stores are scratch", W.MEMORY.startswith(HOME))
debt_path = os.path.join(W.MEMORY, "curiosity-debt.json")
HERS = "Gloria, what is the blue jar on the second shelf for?"
json.dump([{"id": "d0000001", "question": HERS, "object": "blue jar", "kind": "referential", "target": "gloria",
            "pull": 0.9, "surfaced": 0}], open(debt_path, "w"))
JUDGED = []
def judge(system, prompt, **k):
    JUDGED.append(prompt)
    return {"searchable": True, "question": "How do bar-tailed godwits navigate a nonstop flight?",
            "search_query": "godwit navigation"}
W.llm_json = judge
picked = W.pick_question() or {}
check("a question for her is not searched, even when a model would call it searchable", HERS not in picked.get("question", ""), picked)
check("the searchable judge never sees it", not any(HERS in p for p in JUDGED), JUDGED[:1])
aq = json.load(open(os.path.join(W.MEMORY, "architecture-questions.json")))
check("it goes to her path (recorded for her)", any(r.get("question") == HERS for r in aq), aq)
json.dump([{"id": "d0000002", "question": "What is the tallest tree ever measured?", "object": "tree",
            "kind": "salience", "pull": 0.9, "surfaced": 0}], open(debt_path, "w"))
W.llm_json = lambda system, prompt, **k: {"searchable": True}
check("a curiosity without that target still reaches the judge and is searched",
      "tallest tree" in (W.pick_question() or {}).get("question", ""))
os.remove(debt_path)

# ── 5. Forge digest: a list over 1 MiB is read; too large / unreadable are not "unreachable" ─────────────────────
sys.modules["forge_loop_runtime"] = types.SimpleNamespace(secret=lambda path: "fixture-token")
F = load("forge_digest", "scripts/forge_digest.py")
class _Body:
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n=-1): return self.data if n < 0 else self.data[:n]
def serve(data):
    urllib.request.urlopen = lambda req, timeout=None: _Body(data)
projects = [{"id": "P-%d" % i, "state": "ready", "intent": "a small tool number %d" % i, "spent": 0, "cycles": 1,
             "notes": "x" * 1200} for i in range(1000)]
big = json.dumps(projects).encode()
check("the fixture list is over 1 MiB", len(big) > 1024 * 1024, len(big))
serve(big)
got = F._forge_projects()
check("a project list over 1 MiB is read whole", isinstance(got, list) and len(got) == 1000, type(got))
text = F.render("2026-10-29")
check("its receipt names what the Forge is working on", "What the Forge is working on" in text and "unreachable" not in text, text[:300])
serve(b"[" + b" " * (F.FORGE_MAX_BYTES + 10) + b"]")
check("a list past the cap is said as too large", F._forge_projects() is None and F.FORGE_FAILURE == "too large")
text = F.render("2026-10-29")
check("and the receipt says so, not 'unreachable'", "larger than the digest reads" in text and "unreachable" not in text, text)
serve(b'[{"id": "P-1", "state": ')
text = F.render("2026-10-29")
check("an unreadable answer is a parse error, not 'unreachable'", "parse error" in text and "unreachable" not in text, text)
urllib.request.urlopen = no_network
text = F.render("2026-10-29")
check("a Forge that does not answer is still said as unreachable", "unreachable" in text)

# ── 8. Link reader: one DNS blink is retried, and a second failure is said as the lookup failing here ─────────────
import link_fetch as LF
SLEPT = []
LF._sleep = lambda s: SLEPT.append(s)
calls = []
def flaky(host):
    calls.append(host)
    if len(calls) == 1:
        raise socket.gaierror(-3, "Temporary failure in name resolution")
    return ["93.184.216.34"]
addrs, why = LF._destination("https://paper.example.org/a", resolve=flaky)
check("a lookup that fails once is tried again after a pause", addrs == ("93.184.216.34",) and why == "" and SLEPT == [2.0]
      and len(calls) == 2, (addrs, why, SLEPT))
def dead(host): raise socket.gaierror(-2, "Name or service not known")
addrs, why = LF._destination("https://paper.example.org/a", resolve=dead)
check("two failed lookups are said as 'DNS failed here'", addrs == () and why.startswith("DNS failed here")
      and "paper.example.org" in why, why)

check("nothing reached the network", NET == [], NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
