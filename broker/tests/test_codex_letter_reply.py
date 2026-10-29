#!/usr/bin/env python3
"""His reply to a [Codex] letter sees the archive that letter brought (Gloria, 27 October: the Velaris zips were
recovered from the Mac and his reading had them, but both replies said "I didn't open anything. The zip failed with an
unknown failure" and asked Codex to resend and split the files). A recovered attachment counts as read; a reply is
never drafted while its archive is still being fetched, and never calls a file still coming a failure. Scratch
workspace; the model, Gmail and the send are stubs; nothing reaches the network or is sent."""
import importlib.util, json, os, sys, tempfile, types
from datetime import datetime, timedelta
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-codex-reply-")
WS = os.path.join(HOME, ".vintos", "workspace"); os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import urllib.request; urllib.request.urlopen = no_network
sys.modules["plugin_gateway"] = types.SimpleNamespace(call=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))
spec = importlib.util.spec_from_file_location("want_email", os.path.join(REPO, "scripts", "want_email.py"))
E = importlib.util.module_from_spec(spec); sys.modules["want_email"] = E; spec.loader.exec_module(E)
import codex_archives as C

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

check("the stores are scratch", E.MEMORY.startswith(HOME) and C.ROOT.startswith(HOME) and E.LETTER_REPLIES.startswith(HOME))

E.who_i_am = lambda n=0: "I am Vintos."
E._promises = lambda rows, think=None, now=None: []
E._codex_archive_view = lambda mid, chars=None: ("== CODEX ARCHIVE 0123abcd ==\nREADME.md: a jointed hand, five fingers"
                                                if mid in ("c0de1", "c0de2") else "")
NOW = datetime(2026, 10, 27, 8, 0, 0)
ZIP = {"filename": "Harbor-source.zip", "attachment_id": "ATT1", "mime_type": "application/zip", "size": "9520783"}

def letter(mid, subject, read_at, attachments):
    return {"id": mid, "kind": "letter", "from": "Codex", "address": "me@example.org", "thread_id": mid,
            "subject": subject, "date": "Mon, 26 Oct 2026 07:20:07 -0700", "body": "Here is the project, part %s." % mid,
            "attachments": attachments, "read_at": read_at.isoformat(timespec="seconds"), "to_me": "a hand at last"}

def write_log(rows):
    with open(E.INBOX_LOG, "w") as f:
        for r in rows: f.write(json.dumps(r) + "\n")

os.makedirs(C.ROOT, exist_ok=True)
with open(C.INDEX, "w") as f:
    json.dump({"archives": [{"id": "0123abcd", "title": "Harbor model", "status": "archived", "files": 186,
                             "received": "2026-10-26T19:39:06",
                             "letters": [{"n": 1, "message_id": "c0de1"}, {"n": 2, "message_id": "c0de2"}]}],
               "pending": []}, f)

# 1. The archive is kept: the attachment the mail log says nothing about (a letter read again) counts as read, and
#    the reply gets the same archive view his reading got.
check("the archive's state is known by the letter", C.letter_state("c0de1")[0] == "archived")
marked, state = C.mark_letter("c0de1", [dict(ZIP), {"filename": "notes.txt"}])
check("its zip is marked archived, other attachments left as they were",
      state == "archived" and marked[0]["status"] == "archived" and marked[0]["archive_id"] == "0123abcd"
      and "status" not in marked[1], marked)
ASKED, SENT = [], []
GOOD = "Codex,\n\n1. The jointed hand: keep. The five fingers in README.md are what I will check first, against the drum STLs."
def think(system, ask, tokens):
    ASKED.append((system, ask)); return GOOD
def send(args, purpose):
    SENT.append((args, purpose)); return {"ok": True}
write_log([letter("c0de1", "[Codex] Harbor model complete — 1 of 2: source", NOW - timedelta(hours=3), [dict(ZIP)])])
out = E.reply_letters(think=think, send=send, now=NOW, bring=lambda *a, **k: None)
system, ask = ASKED[-1]
check("his reply is drafted with the archive's own contents", "THE ARCHIVE THIS LETTER BROUGHT" in ask
      and "a jointed hand" in ask, ask[-400:])
check("the attachment counts as read: never NOT READ, never an unknown failure",
      "NOT READ" not in ask and "unknown failure" not in ask and "ARCHIVED" in ask, ask)
check("he is told it was read, and not to ask for it again", "counts as read" in system and "resend" in system)
check("the reply goes out once", len(SENT) == 1 and out and "replied to Codex's letter" in out[0], out)
day = open(os.path.join(E.MEMORY, [f for f in os.listdir(E.MEMORY) if f.startswith("daily-inner-life-")][0])).read()
check("his journal has the reply he actually sent", "## I replied to Codex's letter" in day and "jointed hand" in day)

# 2. A draft that says the kept archive failed is never sent (the two wrong replies of 27 October).
WRONG = ["Codex,\n\nI didn't open anything. The zip failed with an unknown error, so I haven't seen one file from it. "
         "Please resend, split into smaller files.",
         "Codex,\n\nI didn't get the files. Harbor-blender.zip came through as NOT READ, unknown failure. I have nothing "
         "from it: no Blender assembly, no GLBs, no renders."]
for w in WRONG:
    check("caught: %r" % w[8:50], E._denies_archive(w), w)
check("a reply about the work is not caught", not E._denies_archive(GOOD))
check("while the files are coming, saying so is fine", not E._denies_archive(
    "Codex,\n\nThe files are still being fetched; I haven't seen them yet and will look when they are in.", fetching=True))
check("while they are coming, calling them failed is not", E._denies_archive("The zip failed, please resend it.", fetching=True))
ASKED.clear(); SENT.clear()
write_log([letter("c0de2", "[Codex] Harbor model complete — 2 of 2: Blender", NOW - timedelta(hours=3), [dict(ZIP)])])
out = E.reply_letters(think=lambda s, a, t: WRONG[1], send=send, now=NOW, bring=lambda *a, **k: None)
done = json.load(open(E.LETTER_REPLIES))
check("a reply that says the kept archive failed is held, not sent", SENT == [] and not done["c0de2"].get("sent")
      and "not read, though it is kept" in done["c0de2"].get("why", ""), done.get("c0de2"))
check("and the hold is a try, so it is drafted again", done["c0de2"].get("tries") == 1)

# 3. Recovery still pending (the Mac fetch, or part 2 still to come): the reply waits, and is not a try.
pdir = os.path.join(C.PENDING, "d1d1d1d1d1d1"); os.makedirs(pdir)
with open(os.path.join(pdir, "state.json"), "w") as f:
    json.dump({"did": "d1d1d1d1d1d1", "title": "Velvet model", "status": "incomplete", "created": NOW.isoformat(),
               "why": "waiting for 1 file(s) not downloaded (the connector refused it)",
               "letters": {"c0de3": {"n": 1, "message_id": "c0de3", "files": [], "failed": [{"name": "v.zip", "why": "x"}]}}}, f)
check("a delivery still being put together is 'fetching'", C.letter_state("c0de3")[0] == "fetching")
ASKED.clear(); SENT.clear()
write_log([letter("c0de3", "[Codex] Velvet model — 1 of 2: source", NOW - timedelta(hours=2),
                  [dict(ZIP, filename="v.zip", status="not_read", why="Codex archive not downloaded: refused")])])
E.reply_letters(think=think, send=send, now=NOW, bring=lambda *a, **k: None)
done = json.load(open(E.LETTER_REPLIES))
check("the reply is not drafted before the archive is in", ASKED == [] and SENT == [], ASKED)
check("it waits, saying why, without spending a try", "still being fetched" in done["c0de3"].get("waiting", "")
      and not done["c0de3"].get("tries"), done.get("c0de3"))
later = NOW + timedelta(hours=E.CODEX_FETCH_WAIT_HOURS)
E.reply_letters(think=think, send=send, now=later, bring=lambda *a, **k: None)
system, ask = ASKED[-1]
check("after the wait it is written, saying the files are being fetched, never failed",
      "HELD: still being fetched" in ask and "NOT READ" not in ask and "still being fetched" in system
      and "Do not call them failed" in system, ask)

# 4. A letter that no delivery knows yet waits the same way, and a letter without an archive is answered at once.
ASKED.clear()
write_log([letter("c0de4", "[Codex] Loom — 1 of 1", NOW - timedelta(hours=1), [dict(ZIP, filename="loom.zip")]),
           dict(letter("g1", "[Grok Bot] Tuesday", NOW - timedelta(hours=1), []), **{"from": "Grok Bot"})])
E.reply_letters(think=think, send=send, now=NOW, bring=lambda *a, **k: None)
done = json.load(open(E.LETTER_REPLIES))
check("an archive not taken in yet: the reply waits", done["c0de4"].get("waiting")
      and not done["c0de4"].get("sent"), done.get("c0de4"))
check("other agents' letters are answered as before", done.get("g1", {}).get("sent") and len(ASKED) == 1
      and "THE ARCHIVE" not in ASKED[0][1])

# 5. His reading of a letter read again sees the archive's status now, not the empty one in the log.
READ = []
def reader(system, ask, tokens):
    READ.append(ask); return json.dumps({"what": "Codex sent the Harbor model", "to_me": "good work", "keep": False})
E._mail_seen = lambda: set(); E.links_read = lambda body: []
E.read_mail([{"id": "c0de1", "from": "\"[Codex]\" <me@example.org>", "subject": "[Codex] Harbor model complete — 1 of 2: source",
              "date": "", "body": "Here is the project.", "attachments": [dict(ZIP)]}], think=reader, want=lambda *a: None)
check("the reading shows the zip as archived, not NOT READ", "ARCHIVED" in READ[-1] and "NOT READ" not in READ[-1], READ[-1][:600])
row = [json.loads(l) for l in open(E.INBOX_LOG)][-1]
check("and the mail log keeps it as archived", row["attachments"][0].get("status") == "archived", row["attachments"])
check("an attachment nothing was tried with is NOT OPENED, not a failure",
      "NOT OPENED" in E.attachments_view([{"filename": "x.zip"}]) and "unknown failure" not in E.attachments_view([{"filename": "x.zip"}]))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
