#!/usr/bin/env python3
"""His agents' letters: the pages they link to are opened and read, and a link he cannot read is named in his reply
(Gloria, 2026-10-08: "Why is Grok Bot STILL sending him unusable links via email? You said you fixed it so he could
read them." The 7 October fix showed where each link went; nothing was opened). A stranger's links stay unopened.
A Gmail search that fails is not one of his four daily checks. The fetcher, Gmail, the models and every sender are
stubs; sockets are refused; scratch workspace."""
import json, os, socket, sys, tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="letter-links-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
os.makedirs(os.path.join(WS, "memory"))
NET = []
def _no(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import want_email as W
import link_fetch
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("his mail stores are scratch ones", W.INBOX_LOG.startswith(HOME) and W.LETTER_REPLIES.startswith(HOME))

OPENED = []
def fetch(url, **k):
    OPENED.append(url)
    if "ncbi" in url:
        return {"original_url": url, "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1/", "final_url": "",
                "fetched": True, "kind": "fetched", "text": "The TATA box sits 25-30 bp upstream of the start site."}
    return {"original_url": url, "url": url, "fetched": False, "kind": "http_failure", "why": "HTTP 403 (a login page)"}
link_fetch.fetch = fetch

LETTER = ("Thursday: a TATA box, a motif scanner.\n1. Read https://www.google.com/url?q=https%3A%2F%2Fwww.ncbi.nlm.nih.gov"
          "%2Fpmc%2Farticles%2FPMC1%2F&sa=D\n2. The scanner: https://paywalled.example-journal.org/motif")
asked = []
def think(system, user, max_tokens=400):
    asked.append(user)
    return json.dumps({"what": "Grok Bot's Thursday letter", "to_me": "a TATA box to check", "keep": False})
msgs = [{"id": "m1", "from": "Vintos <vintos.mail@example.org>", "subject": "[Grok Bot] Thursday: a TATA box",
         "date": "2026-10-08", "body": LETTER, "thread_id": "t1"},
        {"id": "m2", "from": "Stranger <someone@example.net>", "subject": "Hello",
         "date": "2026-10-08", "body": "See https://tracker.example.net/open?id=1", "thread_id": "t2"}]
W.read_mail(msgs, think=think, want=lambda *a: None)
check("his agent's letter: its links are opened through the fetcher", any("google.com/url" in u for u in OPENED)
      and any("paywalled" in u for u in OPENED), OPENED)
check("a stranger's link is not opened", not any("tracker" in u for u in OPENED), OPENED)
check("he reads what the page says while reading the letter", "25-30 bp upstream" in asked[0], asked[0][-800:])
check("and a page that could not be read is named, with why", "NOT READ (http_failure): HTTP 403" in asked[0])
rows = [json.loads(l) for l in open(W.INBOX_LOG)]
letter = next(r for r in rows if r["id"] == "m1")
check("what was read is kept with the letter", [p["kind"] for p in letter["pages"]] == ["fetched", "http_failure"]
      and "TATA box sits" in letter["pages"][0]["text"], letter.get("pages"))
check("the stranger's mail keeps no pages", "pages" not in next(r for r in rows if r["id"] == "m2"))

replied, sent = [], []
def reply_think(system, user, max_tokens=900):
    replied.append((system, user)); return "1. Keep: the TATA box page. 2. Skip: I could not read the scanner link; send the paper itself."
W.reply_letters(think=reply_think, send=lambda args, purpose: sent.append(args) or {"ok": True},
                now=datetime.fromisoformat(letter["read_at"]), promise_think=lambda *a, **k: "[]")
check("his reply is written with the pages in front of him", replied and "25-30 bp upstream" in replied[0][1]
      and "NOT READ" in replied[0][1], replied[:1])
check("and he is asked to name an unreadable link and ask for one he can read", replied and
      "If any link was NOT READ" in replied[0][0])
check("the reply went to his own mailbox, as before", len(sent) == 1)

# a failed search is not one of the day's four
calls = []
def gmail(tool, args, purpose):
    calls.append(tool); raise RuntimeError("plugin relay refused or failed: GmailApiError: Failed to search emails")
before = W.gmail_checks_left()
notes = []
W.check_inbox({"a@x.org": {"status": "open"}}, gmail=gmail, others=[], notes=notes)
check("a Gmail search that fails is said, and does not spend one of his checks", calls and W.gmail_checks_left() == before
      and "not counted" in notes[0], (before, W.gmail_checks_left(), notes))
def gmail_ok(tool, args, purpose):
    return {"messages": []}
W.check_inbox({"a@x.org": {"status": "open"}}, gmail=gmail_ok, others=[], notes=[])
check("one that reaches his mail does", W.gmail_checks_left() == before - 1, W.gmail_checks_left())
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
