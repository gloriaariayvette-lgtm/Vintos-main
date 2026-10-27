#!/usr/bin/env python3
"""A [Codex] letter is read as his agent's letter, with the archive it brought in front of him (Gloria, 27 October:
the two Velaris letters were read as plain mail, a line each, before Codex was one of his agents). Scratch workspace;
the model, Gmail and the archive store are stubs; nothing reaches the network."""
import importlib.util, json, os, sys, tempfile, types
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-codex-letter-")
WS = os.path.join(HOME, ".vintos", "workspace"); os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request; urllib.request.urlopen = no_network
sys.modules["plugin_gateway"] = types.SimpleNamespace(call=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))
spec = importlib.util.spec_from_file_location("want_email", os.path.join(REPO, "scripts", "want_email.py"))
E = importlib.util.module_from_spec(spec); sys.modules["want_email"] = E; spec.loader.exec_module(E)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

check("the stores are scratch", E.MEMORY.startswith(HOME) and E.INBOX_LOG.startswith(HOME))
codex = {"id": "c0de1", "from": "\"[Codex]\" <me@example.org>", "subject": "[Codex] Harbor model complete — 1 of 2: source",
         "date": "Mon, 26 Oct 2026 07:20:07 -0700", "body": "Here is the project.", "attachments": []}
check("a letter whose subject begins [Codex] is his agent Codex's", E._agent(codex) == "Codex")
check("a reply that only quotes it is not", E._agent(dict(codex, subject="Re: [Codex] Harbor model complete",
                                                           body="thanks")) == "")

ASKED = []
E._codex_archive_view = lambda mid, chars=None: "== archive 0123 ==\nREADME.md: a jointed hand, five fingers" if mid == "c0de1" else ""
E.who_i_am = lambda n: "I am Vintos."
E.links_read = lambda body: []
def think(system, ask, tokens):
    ASKED.append((ask, tokens))
    return json.dumps({"what": "Codex sent the Harbor model, part 1", "to_me": "x" * 2000, "keep": True, "want": ""})
lines = E.read_mail([codex], think=think, want=lambda *a: None)
ask, tokens = ASKED[-1]
check("he reads it as his agent's letter, with the archive's own contents", "YOUR AGENT CODEX" in ask
      and "a jointed hand" in ask and "what you think of the work itself" in ask, ask[:300])
check("he is given room to say what he thinks", tokens == E.CODEX_READ_TOKENS)
row = [json.loads(l) for l in open(E.INBOX_LOG)][-1]
check("kept as a letter from Codex, his reading whole", row["kind"] == "letter" and row["from"] == "Codex"
      and len(row["to_me"]) == 2000, row)
day = open(os.path.join(E.MEMORY, [f for f in os.listdir(E.MEMORY) if f.startswith("daily-inner-life-")][0])).read()
check("his journal says he read Codex's letter, and what it is to him", "## I read Codex's letter: [Codex] Harbor" in day
      and "What it is to me: " in day, day[-300:])

E._mail_seen = lambda: {"c0de1"}
E._messages = lambda result: [codex]
ASKED.clear()
out = E.reread(["c0de1"], gmail=lambda tool, args, why: {}, think=think)
check("reread reads a letter already seen, once", len(ASKED) == 1 and out and "Codex" in out[0], out)
check("and the ordinary reader still skips it afterwards", E.read_mail([codex], think=think) == [])

plain = {"id": "p1", "from": "someone@example.org", "subject": "hello", "date": "", "body": "hi", "attachments": []}
ASKED.clear(); E._mail_seen = lambda: set()
E.read_mail([plain], think=think, want=lambda *a: None)
check("other mail is read as before", ASKED[-1][1] == 400 and "archive" not in ASKED[-1][0].lower())
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
