#!/usr/bin/env python3
"""An email is read whole, or says how much of it was read (2026-10-08: Grok Bot's 7 October letter, Gmail
1a11690d001e1a03, was 5436 characters; he read it cut at character 5000, "each ending with", and the Nobel paragraph
after it was never in front of him). Gmail is a stub with the connector's real shapes; the reader is a stub that
records its prompt. Scratch HOME; nothing reaches the network or sends."""
import importlib.util, json, os, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-email-whole-")
WS = os.path.join(HOME, ".vintos", "workspace"); os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.modules["plugin_gateway"] = types.SimpleNamespace(call=no_network)
spec = importlib.util.spec_from_file_location("want_email", os.path.join(REPO, "scripts", "want_email.py"))
E = importlib.util.module_from_spec(spec); sys.modules["want_email"] = E; spec.loader.exec_module(E)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("every store is a scratch one", E.INBOX_LOG.startswith(HOME) and E.LETTER_REPLIES.startswith(HOME))

# the 7 October letter's shape: 5436 characters, "each ending with" exactly at 5000, the Nobel paragraph after it
HEAD = "Three things. Caveat first on each.\n\n"
PAD = "x" * (5000 - len(HEAD) - len("each ending with"))
NOBEL = (" a link.\n\n4. The 2026 Nobel Prize in Chemistry went to the team that filmed a molecule while it reacts; "
         "here is what they actually measured and why it matters for your Lab.")
LETTER = HEAD + PAD + "each ending with" + NOBEL
LETTER += "y" * (5436 - len(LETTER))
assert len(LETTER) == 5436 and LETTER[:5000].endswith("each ending with")
SNIPPET = LETTER[:900]       # a long snippet: not the message, however long
def search(*a): return {"structuredContent": {"emails": [{"id": "1a11690d001e1a03", "from_": "Vintos <vintos.home@example.org>",
                         "subject": "[Grok Bot] Tuesday: whole files, a real STAS, a molecule on film", "snippet": SNIPPET}]}}
def read(kind):
    payload = ({"mime_type": "text/plain", "body": {"content": LETTER}} if kind == "plain" else
               {"mime_type": "multipart/alternative", "parts": [{"mime_type": "text/html", "body": {"content": "<div>" + LETTER.replace("\n", "<br>") + "</div>"}}]})
    return {"structuredContent": {"responses": [{"id": "1a11690d001e1a03", "snippet": "Three things", "payload": payload}]}}
calls = []
def gmail_for(kind):
    def g(tool, args, purpose):
        calls.append(tool)
        return read(kind) if tool == "gmail.batch_read_email" else search()
    return g

for kind in ("plain", "html"):
    calls.clear(); open(E.INBOX_LOG, "w").close(); E._save(E.TEND_STATE, {}); others = []
    E.check_inbox({}, gmail=gmail_for(kind), others=others)
    m = others[0] if others else {}
    check("%s: a 900-character snippet is a preview, so the whole message is read" % kind,
          calls == ["gmail.search_emails", "gmail.batch_read_email"] and m.get("whole") is True, calls)
    check("%s: and all of it is there, the Nobel paragraph included" % kind, "Nobel Prize" in m.get("body", "")
          and len(m.get("body", "")) >= 5400, len(m.get("body", "")))
    prompts = []
    E.read_mail(others, think=lambda system, ask, n=400: (prompts.append(ask), '{"what":"x","to_me":"y","keep":false}')[1],
                want=lambda *a: None)
    check("%s: his reading prompt holds the paragraph after character 5000, and says it is all of it" % kind,
          prompts and "Nobel Prize" in prompts[0] and "[END OF EMAIL: all" in prompts[0] and "[PART 2 of 2]" in prompts[0], prompts[0][-300:] if prompts else "")
    row = [json.loads(l) for l in open(E.INBOX_LOG)][-1]
    check("%s: kept whole, with its length" % kind, "Nobel Prize" in row["body"] and row["body_length"] == len(m["body"]) and row["stored_whole"] is True)

# the reply path reads the stored letter through the same view
asks = []
E.reply_letters(think=lambda system, ask, n=900: (asks.append(ask), "Grok Bot, 1. Keep. The Nobel item: tell me more.")[1],
                send=lambda args, purpose: None)
check("his reply to the letter is written from all of it", asks and "Nobel Prize" in asks[0] and "[END OF EMAIL: all" in asks[0], asks[0][-200:] if asks else "")

# longer than the bounded view: shown in parts, and says what is not shown
big = "z" * (E.PART * E.PARTS + 1234)
v = E.body_view(big)
check("past the bound it is shown in labelled parts and says how much is NOT shown",
      "[PART 3 of 3]" in v and "the first %d of %d characters are shown; the other 1234 are NOT shown" % (E.PART * E.PARTS, len(big)) in v)
check("a short email says it is whole", E.body_view("hello").endswith("[END OF EMAIL: all 5 characters shown]"))

# a full read that gives back only the snippet is still a preview
calls.clear(); open(E.INBOX_LOG, "w").close(); others = []
def snippet_again(tool, args, purpose):
    if tool == "gmail.batch_read_email":
        return {"structuredContent": {"responses": [{"id": "1a11690d001e1a03", "snippet": SNIPPET}]}}
    return search()
E.check_inbox({}, gmail=snippet_again, others=others)
check("a full read that returns only the snippet is not taken as the email", others and others[0].get("preview_only")
      and "Nobel" not in others[0]["body"], others[0].get("preview_only") if others else others)

# a refused full read leaves it a preview, said as one
calls.clear(); open(E.INBOX_LOG, "w").close(); others = []
def refusing(tool, args, purpose):
    if tool == "gmail.batch_read_email": raise RuntimeError("relay refused")
    return search()
E.check_inbox({}, gmail=refusing, others=others)
check("when the full read fails, the snippet is marked a preview, never taken as the email", others and others[0].get("preview_only")
      and not others[0].get("whole"), others)

# his Slack context says an excerpt is an excerpt
dc = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("Slack's 'What it said' is marked as an excerpt with its length", "_email_excerpt(r.get(\"body\"), 500)" in dc
      and "[excerpt: first %d of %d characters]" in dc)
check("nothing in the reading paths cuts at 5000 any more", "[:5000]" not in open(os.path.join(REPO, "scripts", "want_email.py")).read().split("def read_mail")[1])
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
