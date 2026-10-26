#!/usr/bin/env python3
"""A message left at the door (proposal 19, 26 October): taken, passed through deliver.py, settled only by its
receipt, kept minimally, and known to him as a fact without the visitor's words.

Offline. Scratch HOME and workspace; deliver.py's own HTTP post is a stub that records and answers what the test
says; its backoff sleep is a no-op; every socket is refused and `requests` cannot be imported. The visitor is
synthetic. Nothing here reaches her."""
import importlib, json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="door-messages-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.modules["requests"] = None
sys.path.insert(0, os.path.join(REPO, "scripts"))
import deliver as D
POSTS = []; ANSWER = [200]
def post_stub(url, data, headers, timeout):
    POSTS.append({"url": url, "data": data.decode("utf-8"), "headers": dict(headers)})
    code = ANSWER[0]
    if isinstance(code, Exception): raise code
    return code
D.POST = post_stub
D.SLEEP = lambda s: None
import door_messages as M

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:1200]) if d and not ok else ""))

check("every store is throwaway and the only sender is a stub",
      M.STORE.startswith(HOME) and D.RECEIPTS.startswith(HOME) and D.POST is post_stub and M._sender() is D.deliver)

WORDS = "SYNTHETIC-NOTE the parcel for flat two is behind the pillar, please call back"
NOW = 2_000_000_000.0
def store(): return json.load(open(M.STORE))

# --- one synthetic visitor leaves word, and it reaches the stubbed owner path ----------------------------------------
r = M.take(WORDS, name="SYNTHETIC-NAME", now=NOW)
rec = store()[r["id"]]
check("a taken message is delivered once deliver's receipt says sent", r["state"] == "delivered" and rec["receipt"] == "sent"
      and rec["settled_at"] == NOW and len(POSTS) == 1, (r, rec))
check("it went through deliver's one channel, with the words and the name as given (not checked)",
      POSTS[0]["url"] == D.CHANNELS["ntfy"] and WORDS in POSTS[0]["data"] and "SYNTHETIC-NAME (not checked)" in POSTS[0]["data"]
      and POSTS[0]["headers"]["Title"] == M.TITLE)
check("deliver's own receipt names this message", D.receipt_for("door-message-" + r["id"], "ntfy")["state"] == "sent")
check("only the minimum is kept", set(rec) <= {"id", "taken_at", "text", "name", "key", "state", "attempts",
                                              "last_try_at", "receipt", "settled_at", "why", "cleared_at"}, sorted(rec))
check("take answers with an id and a state, never the words", WORDS not in json.dumps(r))

# --- the same words handed over again on a later turn are the same message, not a second push -----------------------
again = M.take(WORDS.upper() + "!", name="synthetic-name", now=NOW + 60)
check("a repeat within the window is one message and is not sent again", again["repeat"] and again["id"] == r["id"]
      and len(POSTS) == 1 and len(store()) == 1, again)

# --- the send fails: it waits, retries on tend, and settles only from a receipt ---------------------------------------
ANSWER[0] = 503
w = M.take("SYNTHETIC-NOTE two", now=NOW + 120)
check("a failed receipt leaves it waiting, not delivered", w["state"] == "waiting" and store()[w["id"]]["receipt"] == "failed", w)
n_posts = len(POSTS)
ANSWER[0] = OSError("synthetic outage")
check("tend retries, and an exception is another failed attempt", M.tend(now=NOW + 180)[w["id"]] == "waiting"
      and store()[w["id"]]["attempts"] == 2 and len(POSTS) > n_posts)
ANSWER[0] = 200
check("tend settles it once a receipt says sent", M.tend(now=NOW + 240)[w["id"]] == "delivered")

ANSWER[0] = 500
u = M.take("SYNTHETIC-NOTE three", now=NOW + 300)
M.tend(now=NOW + 360); M.tend(now=NOW + 420)
before = len(POSTS); M.tend(now=NOW + 480)
check("after MAX_ATTEMPTS failed receipts it is undelivered, kept, and not tried again",
      store()[u["id"]]["state"] == "undelivered" and store()[u["id"]]["attempts"] == M.MAX_ATTEMPTS
      and store()[u["id"]]["text"] and len(POSTS) == before)

# --- a sender that returns no receipt, or someone else's, does not settle it ------------------------------------------
fake = M.take("SYNTHETIC-NOTE four", now=NOW + 540, sender=lambda *a, **k: None)
check("no receipt is not delivery", fake["state"] == "waiting", fake)
other = M.take("SYNTHETIC-NOTE five", now=NOW + 600,
               sender=lambda *a, **k: {"state": "sent", "artifact_id": "door-message-someone-else"})
check("a receipt for another artifact is not this message's receipt", other["state"] == "waiting", other)
check("his context says when one has not reached her yet", "not reached her yet" in M.block(now=NOW + 610))
# the next take also retries the two still waiting, through the same sender
six = M.take("SYNTHETIC-NOTE six", now=NOW + 630, sender=lambda a, *x, **k: {"state": "sent", "artifact_id": a})
check("a sender's receipt for this very message settles it", six["state"] == "delivered", six)
called = []
refused = M.take("SYNTHETIC-NOTE seven", now=NOW + 660, sender=lambda *a, **k: called.append(1) or {"state": "sent"})
check("past the hourly bound nothing more is taken or sent", refused["state"] == "refused" and not called, refused)
check("an empty message is refused", M.take("  ...  ", now=NOW + 700)["state"] == "refused")

# --- he knows how it went, without the words or the name --------------------------------------------------------------
b = M.block(now=NOW + 720)
check("his context says which reached her and which did not", "reached her phone" in b and "did not reach her" in b, b)
check("his context never carries the visitor's words or name", "SYNTHETIC" not in b, b)
check("the line is offered through his inner layer", ("door_messages", "block") in importlib.import_module("inner_context")._FULL)
check("status carries no words", "SYNTHETIC" not in json.dumps(M.status(NOW + 720)))
check("nothing is in his context a day later", M.block(now=NOW + 720 + M.CONTEXT_S + 1000) == "")

# --- retention: the words are cleared after it settles, the record goes later -----------------------------------------
ANSWER[0] = 200
M.tend(now=NOW + M.KEEP_TEXT_S + 1000)
kept = store()
check("a week after settling the words and name are cleared", kept[r["id"]]["text"] == "" and kept[r["id"]]["name"] == ""
      and kept[r["id"]]["state"] == "delivered")
M.tend(now=NOW + M.KEEP_RECORD_S + 1000)
check("a month on the record is gone", store() == {})

check("no socket was opened", NET == [])
print("%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
