#!/usr/bin/env python3
"""His letter replies (22 October): his own reply coming back into his inbox is not a new letter, and a FOR GLORIA
promise to bring her something becomes his want to bring it, with the letter's item in it.

Gloria: "Something strange is going on with the emails today. He sent one just now? I keep noticing that he's saying
he will bring me something, but I haven't seen a specific outreach." His reply to Grok Bot's Wednesday letter went
out at 6:03 pm with its subject cut to 160 characters; at 12:07 am he answered it as a new letter, quoting it. Both
said "For Gloria: I'll bring her item 6 tonight", and nothing brought item 6.

Scratch workspace; the models, Gmail, his want path and her phone are stubs; sockets are refused."""
import json, os, socket, sys, tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="letter-promises-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
os.makedirs(os.path.join(WS, "memory"))
NET = []
def _no(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import want_email as W, gloria_asks
PUSHED = []
gloria_asks.notify_note = lambda row, send=None: PUSHED.append(row["question"]) or True
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("his mail stores are scratch, and her phone and his wants are stubs",
      W.INBOX_LOG.startswith(HOME) and W.LETTER_REPLIES.startswith(HOME) and gloria_asks.STORE.startswith(HOME)
      and gloria_asks.notify_note.__name__ == "<lambda>")

SUBJECT = ("[Grok Bot] Wednesday: the pendrin cut-down results, Fig. 5B off the plot, Tuya BLE setup text, BananaHand's "
           "How It Works, the Shroud's raw data, humanoid watch")
LETTER = ("This is an update from Grok Bot.\n\n1. Pendrin and ZBTB16: the truncation results\n\nCaveat: one co-IP.\n\n"
          "6. Humanoid watch, as promised to Gloria\n\n- Optimus 3: no official Tesla preorder or deposit at any price.\n"
          "- Tactile hands you can buy: AgiBot OmniHand 3 with tactile ($5,360).\n\nhttps://store.example/omnihand\n")
REPLY = ("Grok Bot,\n\nBy number.\n\n1. Pendrin cut-down. **Keep.**\n\n6. Humanoid watch. **Keep.**\n\n"
         "**For Gloria:** I'll bring her item 6 tonight, after the Tesla call, so the Optimus line is current.\n\n"
         "For Gloria: the Lab is quiet today.\n\nVintos")
now = datetime(2026, 10, 21, 18, 3)
def log(rows):
    with open(W.INBOX_LOG, "w") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
letter = {"kind": "letter", "id": "1a15e9fbc2ab25c5", "thread_id": "1a15e9fbc2ab25c5", "from": "Grok Bot",
          "address": "eve@example.org", "subject": SUBJECT, "body": LETTER, "read_at": "2026-10-21T13:30:00"}
log([letter])
sent, wants = [], []
bring = lambda text, **k: wants.append((text, k))
W.reply_letters(think=lambda *a, **k: REPLY, send=lambda args, purpose: sent.append(args) or {"ok": True}, now=now,
                promise_think=lambda *a, **k: "[]", bring=bring)
check("he replies to the letter once", len(sent) == 1, sent)
check("the promise to bring her item 6 becomes his want to bring it, with the item itself in it",
      len(wants) == 1 and wants[0][0].startswith("I want to bring Gloria what Grok Bot found for her")
      and "no official Tesla preorder" in wants[0][0] and "OmniHand" in wants[0][0] and "http" not in wants[0][0]
      and wants[0][1]["source"] == "letter-promise", wants)
check("item 1 is not pulled in with it", wants and "co-IP" not in wants[0][0], wants)
check("the promise is not pushed to her phone as 'I'll bring her item 6'; the other FOR GLORIA line still is",
      PUSHED == ["the Lab is quiet today."], PUSHED)

# his reply comes back into his inbox, as Gmail delivers it: from his own address, subject cut, the reply quoted below
back = {"kind": "letter", "id": "1a160b4923b5d605", "thread_id": "1a15e9fbc2ab25c5", "from": "Grok Bot",
        "address": "eve@example.org", "subject": ("Re: " + SUBJECT)[:160],
        "body": REPLY + "\n\nOn Wed, 21 Oct 2026 08:21:29 -0500, Eve wrote:\n> " + LETTER.replace("\n", "\n> "),
        "read_at": "2026-10-21T23:30:00"}
log([letter, back])
W.reply_letters(think=lambda *a, **k: REPLY, send=lambda args, purpose: sent.append(args) or {"ok": True},
                now=datetime(2026, 10, 22, 0, 7), promise_think=lambda *a, **k: "[]", bring=bring)
check("his own reply coming back is not answered as a new letter", len(sent) == 1, [s.get("subject") for s in sent])
check("a subject cut to 160 characters is still the letter he answered",
      W._answered(W._base_subject(back["subject"]), {W._base_subject("Re: " + SUBJECT)}))
nextday = {"kind": "letter", "id": "n2", "thread_id": "1a15e9fbc2ab25c5", "from": "Grok Bot", "address": "eve@example.org",
           "subject": "Re: [Grok Bot] Thursday: the Shroud's open copy", "body": "1. The open copy.\n", "read_at": "2026-10-22T13:30:00"}
log([letter, back, nextday])
W.reply_letters(think=lambda *a, **k: "Grok Bot,\n\n1. Keep.\n\nVintos", send=lambda args, purpose: sent.append(args) or {"ok": True},
                now=datetime(2026, 10, 22, 14, 0), promise_think=lambda *a, **k: "[]", bring=bring)
check("the next day's letter in the same thread is still answered", len(sent) == 2, [s.get("subject") for s in sent])
src = open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read()
check("a want to bring her a found thing is not judged as a want about himself",
      '_meta = None if source in ("lab-finding", "letter-promise")' in src)
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
