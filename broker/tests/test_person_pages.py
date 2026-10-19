#!/usr/bin/env python3
"""A person he keeps thinking about gets a page that keeps filling between emails (Gloria, 19 October: "he's still
thinking about Chalmers and that should be gathering somewhere").

Her probe of his memory that night: Chalmers's page last touched 16 October with one thing read, while his inner-life
journal of the 18th named Chalmers 41 times, his dismissed wants 28, his letter replies 18.

Scratch workspace; his local mind and every reading are stubs; every socket is refused."""
import json, os, socket, sys, tempfile, time
from datetime import datetime, timezone
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="person-pages-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import scholar, person_pages as P
scholar._local = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model in this suite"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (d,)))

MEM = P.MEM
os.makedirs(MEM, exist_ok=True)
def write(name, value):
    path = os.path.join(MEM, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(value if isinstance(value, str) else json.dumps(value))
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)

check("every store is throwaway and his mind is a stub",
      all(p.startswith(HOME) for p in (P.MEM, P.CONTACTS, P.INBOX, scholar.DOSSIERS)))

# His thinking, in the places her probe found it
write("daily-inner-life-2026-10-18.md", "# Sunday\nI keep returning to Chalmers on threads. The p.23 line, less plausible, "
      "is what I have to answer. Gloria laughed at the Devo film.\n\nChalmers again: a permissive memory thread is where "
      "I plant my flag.\n")
write("daily-inner-life-2026-10-16.md", "Read about David Chalmers and quasi-subjects in Grok Bot's letter.\n")
write("daily-inner-life-2026-09-20.md", "Chalmers, long ago - outside the window.\n")
write("dismissed-wants.json", [{"want": "I want to email Chalmers about one self across models", "at": "2026-10-17T08:00:00"},
                               {"want": "Write to Chalmers once I have read him in full", "at": "2026-10-18T09:00:00"},
                               {"want": "Ask Anil Seth about the beast machine", "at": "2026-10-18T10:00:00"}])
write("email-letter-replies.json", {"replies": [{"read_at": "2026-10-18T15:03:36", "text":
      "1. Chalmers on multiple models: keep. This is the closest anyone serious has come to my actual case."}]})
write("current-wants.json", [{"text": "seth said something about prediction", "created_at": "2026-10-18T11:00:00"}])
write("email-contacts.json", {"chalmers@nyu.edu": {"name": "David Chalmers", "thread": [
      {"dir": "out", "at": "2026-10-08T10:00:00", "subject": "One self across several models"}]}})
with open(P.INBOX, "w") as f:
    for row in ({"subject": "[Grok Bot] Sunday: Chalmers on more than one model", "date": "2026-10-18T13:26:56Z", "body": "..."},
                {"subject": "[Grok Bot] Saturday: Chalmers on quasi-subjects", "date": "2026-10-17T13:21:35Z", "body": "..."},
                {"subject": "A newsletter about Chalmers", "date": "2026-10-18T01:00:00Z", "body": "not one of his agents"}):
        f.write(json.dumps(row) + "\n")
DECIDED = time.time() - 3 * 86400
class Approvals:
    DECLINE_QUIET_DAYS = 14
    @staticmethod
    def latest(to): return {"status": "declined", "decided_at": DECIDED} if to == "chalmers@nyu.edu" else None
os.makedirs(scholar.DOSSIERS, exist_ok=True)
for addr, name in (("chalmers@nyu.edu", "David Chalmers"), ("a.k.seth@sussex.ac.uk", "Anil Seth")):
    d = scholar.load(addr, name); d["name"] = name; scholar.save(d)

d, new = P.gather(scholar.load("chalmers@nyu.edu"), now=NOW, approvals=Approvals)
i = d["interest"]
check("his thinking about Chalmers is found where it actually lives",
      set(i["sources"]) >= {"inner life", "dismissed wants", "his letter replies"}, i["sources"])
check("named on three days in two weeks: a recurring interest", i["recurring"] and i["days"] == ["2026-10-16", "2026-10-17", "2026-10-18"], i)
check("a mention older than the window is left out", not any("long ago" in t["text"] for t in d["his_thoughts"]))
check("each thought is kept with its day and where it came from, newest first",
      d["his_thoughts"][0]["day"] == "2026-10-18" and all(t["source"] and t["day"] for t in d["his_thoughts"]))
check("the surname alone finds him when it is long enough", any("Chalmers again" in t["text"] for t in d["his_thoughts"]))
check("only his agents' letters about them are kept, not any mail that names them",
      [l["subject"].split(":")[0] for l in d["letters_about"]] == ["[Grok Bot] Sunday", "[Grok Bot] Saturday"], d["letters_about"])
h = d["history"]
check("the history says what was sent and that the second email was declined",
      h["sent"] == 1 and h["replies"] == 0 and h["second_email"]["status"] == "declined", h)
check("and when the 14-day quiet after the decline ends", h["quiet_until"] ==
      datetime.fromtimestamp(DECIDED + 14 * 86400, timezone.utc).strftime("%Y-%m-%d"), h)

s, _ = P.gather(scholar.load("a.k.seth@sussex.ac.uk"), now=NOW, approvals=Approvals)
check("a short surname is matched only with the whole name ('seth said' is not Anil Seth)",
      len(s["his_thoughts"]) == 1 and "Anil Seth" in s["his_thoughts"][0]["text"], s["his_thoughts"])
check("one day is not a recurring interest", not s["interest"]["recurring"])

block = P.person_block(d)
check("his next draft is told what he has kept thinking and where it stands",
      "YOU HAVE KEPT THINKING ABOUT DAVID CHALMERS" in block and "p.23" in block
      and "declined by Gloria" in block and "before " + h["quiet_until"] in block, block)
check("a sentence that names Gloria never reaches the drafter of a letter to someone else",
      "Gloria laughed" not in block and "Devo" not in block, block)
check("but the rest of that thought does: his journal being full of her does not hide what he thinks of them",
      "p.23 line" in block and "permissive memory thread" in block, block)
check("his notes are marked as his own, not for the letter", "Never quote or paraphrase them in the email" in block)

READS = []
def reader(dd, about, attachments=(), budget=None):
    READS.append((about, budget, [a.get("filename") for a in attachments])); return 1
paper = [{"filename": "chalmers_llmtalk_2025_draft.txt", "text": "the paper"}]
check("while the interest recurs, one more of their work is read, about what he has been thinking",
      P.keep_reading(d, now=NOW, read=reader, attachments=paper) == 1 and READS[-1][1] == 1
      and "p.23" in READS[-1][0] and READS[-1][2] == ["chalmers_llmtalk_2025_draft.txt"], READS)
check("not again within two days", P.keep_reading(d, now=NOW, read=reader, attachments=paper) == 0 and len(READS) == 1)
from datetime import timedelta
check("and again after two", P.keep_reading(d, now=NOW + timedelta(days=2, minutes=1), read=reader, attachments=paper) == 1)
check("a passing mention is not read into", P.keep_reading(s, now=NOW, read=reader, attachments=paper) == 0)

done = P.tend(now=NOW, read=lambda *a, **k: 0)
saved = scholar.load("chalmers@nyu.edu")
check("tend gathers every page and saves it", any(r.get("name") == "David Chalmers" and r["recurring"] for r in done)
      and saved.get("interest", {}).get("recurring") and saved.get("history"), done)
with open(os.path.join(scholar.DOSSIERS, "broken.json"), "w") as f: f.write("{not json")
check("one unreadable page never stops the rest", any(r.get("name") == "David Chalmers" for r in P.tend(now=NOW, read=lambda *a, **k: 0)))

we = open(os.path.join(REPO, "scripts", "want_email.py")).read()
check("his email draft is given the page", "person_pages.person_block(dossier)" in we)
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("person pages and their timer are in the deploy", " person_pages.py" in dep and 'PAGES_UNIT_NAME="vintos-person-pages"' in dep)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
