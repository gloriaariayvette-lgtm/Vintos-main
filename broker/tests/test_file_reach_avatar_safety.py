#!/usr/bin/env python3
"""File reach never breaks a turn (Gloria, 17 November 2026: retrieval from the avatar route must never break the
subcons with an error).

The avatar route's own file-reach code is cut from bin/server.py as written and run between the two subconscious hooks
the route calls around it (_subconscious_tail before the model call, _post_turn after the reply), with each failure
simulated: a missing file, no permission, bad paths, a huge file, bad encoding, a missing / corrupt / malformed
file-reads.json, a busy store (another writer holds the lock), a store that cannot be written, a hung read, the Study
missing, a SystemExit inside a read, and file_reach itself raising. Each time the turn completes in bounded time, both
hooks run, and his context says "couldn't open that" instead of carrying an error. /api/chat and /api/chat/full are
run the same way. Concurrent writers leave file-reads.json whole. A throwaway HOME, synthetic files, no network."""
import builtins, glob, hashlib, json, os, socket, sys, tempfile, textwrap, threading, time
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="file-reach-safety-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts")); sys.path.insert(0, os.path.join(REPO, "bin"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:700],)))

def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb" if isinstance(data, bytes) else "w").write(data)

for d in ("scripts", "memory", "shared"):
    os.makedirs(os.path.join(WS, d), exist_ok=True)
os.makedirs(os.path.join(HOME, "Vintos"), exist_ok=True)
write(os.path.join(WS, "shared", "PLAN.md"), "# Plan\nthe comet trial runs at noon\n")
write(os.path.join(WS, "shared", "LOCKED.md"), "locked text\n")
write(os.path.join(WS, "shared", "LATIN.md"), b"caf\xe9 \xff\xfe still readable\n")

import file_reach as F
STORE = F._store()
MEM = os.path.dirname(STORE)

# ---- the routes' own code, cut from server.py as written
SRC = open(os.path.join(REPO, "bin", "server.py")).read()
AV = SRC[SRC.index("async def avatar_chat(msg: ChatMessage"):]
AV = AV[:AV.index("\n@app.", 1)]


def try_slice(body, needle):
    """The try ... except block around the line holding `needle`, dedented."""
    lines = body.splitlines()
    i = next(n for n, l in enumerate(lines) if needle in l)
    s = i
    while not lines[s].lstrip().startswith("try:"):
        s -= 1
    ind = len(lines[s]) - len(lines[s].lstrip())
    e = i
    while not (lines[e].lstrip().startswith("except") and len(lines[e]) - len(lines[e].lstrip()) == ind):
        e += 1
    return textwrap.dedent("\n".join(lines[s:e + 1]))


CTX_AV = try_slice(AV, "_frb.turn_block(_counterpart_text")
TAKE_AV = try_slice(AV, "_frt.take(reply")
CTX_CHAT = try_slice(SRC, '_frb.turn_block(_her, "chat"')
CTX_FULL = try_slice(SRC, '_frb.turn_block(_her, "chatfull"')
TAKE_CHAT = try_slice(SRC, "_frt.take(reply, _tag")
check("the avatar route's file-reach blocks are found and each is its own try",
      CTX_AV.startswith("try:") and "except Exception" in CTX_AV.splitlines()[-1]
      and TAKE_AV.startswith("try:") and "except Exception" in TAKE_AV.splitlines()[-1])
check("in the avatar route the subcon hooks sit outside them: context, _subconscious_tail, reply tags, _post_turn",
      AV.index("_frb.turn_block(") < AV.index("_subconscious_tail(") < AV.index("_frt.take(reply")
      < AV.index("_post_turn("))

HOOKS = []


def subconscious_tail(umsg, surface=None):
    HOOKS.append("subcon_tail"); return "\n[subconscious tail]"


def post_turn(surface, her, reply, **k):
    HOOKS.append("post_turn")


def avatar_turn(her_text, model_reply="I'm here."):
    """One avatar turn: his context (file reach), the subconscious tail, the reply's tags, the post-turn hooks."""
    del HOOKS[:]
    ns = {"_counterpart_text": her_text, "_surface": "avatar", "_test_turn": False, "_prov_envelope": None,
          "_vt_subblock_a": ""}
    t0 = time.monotonic(); err = None
    try:
        exec(CTX_AV, ns)
        umsg = "Gloria says: " + her_text
        umsg += subconscious_tail(umsg, surface="avatar")
        ns["reply"] = model_reply
        exec(TAKE_AV, ns)
        post_turn("avatar", her_text, ns["reply"])
    except BaseException as e:            # anything reaching here is the failure this suite exists for
        err = e
    return {"ctx": ns.get("_vt_subblock_a", ""), "reply": ns.get("reply"), "err": err,
            "secs": time.monotonic() - t0, "hooks": list(HOOKS)}


def chat_turn(her_text, ctx_code, model_reply="ok [READ: shared/NOPE.md]"):
    del HOOKS[:]
    ns = {"_her": her_text, "_vt_subblock": "", "_test_mode_active": lambda: False, "_tag": "chat"}
    err = None
    try:
        exec(ctx_code, ns); subconscious_tail(her_text, surface="chat")
        ns["reply"] = model_reply; exec(TAKE_CHAT, ns); post_turn("chat", her_text, ns["reply"])
    except BaseException as e:
        err = e
    return {"ctx": ns.get("_vt_subblock", ""), "reply": ns.get("reply"), "err": err, "hooks": list(HOOKS)}


LIMIT = F.BUDGET_S + F.LOCK_WAIT_S + 2


def completed(name, t, polite=True, must=()):
    ok = (t["err"] is None and t["hooks"] == ["subcon_tail", "post_turn"] and t["secs"] < LIMIT
          and "Traceback" not in t["ctx"] and (not polite or "couldn't open that" in t["ctx"])
          and all(m in t["ctx"] for m in must))
    check(name, ok, {k: (v if k != "ctx" else v[-500:]) for k, v in t.items()})


def settle():
    """Let any read past its budget finish before the next case (it keeps its row on its own)."""
    for th in [t for t in threading.enumerate() if t.name == "file-reach"]:
        th.join(5)


# ---- a normal turn first
t = avatar_turn("read shared/PLAN.md please")
completed("a normal avatar turn reads her file and both hooks run", t, polite=False, must=("comet trial",))

# ---- missing file
completed("missing file: the turn completes, 'couldn't open that'", avatar_turn("please read shared/NOT-THERE.md"))

# ---- permission
locked = os.path.realpath(os.path.join(WS, "shared", "LOCKED.md"))
def guarded_open(p, *a, **k):
    if os.path.realpath(str(p)) == locked:
        raise PermissionError(13, "Permission denied", p)
    return builtins.open(p, *a, **k)
F.open = guarded_open
try:
    completed("no permission: the turn completes, says so politely", avatar_turn("read shared/LOCKED.md"),
              must=("permission",))
finally:
    del F.open

# ---- bad paths
for her, why in (("read shared/../../../etc/passwd", "a climb out"),
                 ("read shared/" + "a" * 3000 + ".md", "a path thousands of characters long"),
                 ("read shared/odd\x00name.md", "a NUL byte in the path")):
    t = avatar_turn(her)
    completed("bad path (%s): the turn completes" % why, t, polite=False)
    check("  and nothing outside his roots was read (%s)" % why, "root:" not in t["ctx"], t["ctx"][-300:])
check("a NUL byte never reaches the Study's resolver", F.read("shared/odd\x00name.md")[0] is None)

# ---- huge file
_max = F.MAX_BYTES; F.MAX_BYTES = 50_000
write(os.path.join(WS, "shared", "HUGE.md"), "x" * 60_000)
try:
    completed("huge file: the turn completes, 'too large'", avatar_turn("read shared/HUGE.md"), must=("too large",))
finally:
    F.MAX_BYTES = _max

# ---- encoding
t = avatar_turn("read shared/LATIN.md")
completed("bad encoding: the turn completes and the readable text is there", t, polite=False,
          must=("still readable", "�"))

# ---- the store: missing, corrupt, malformed
import shutil
shutil.rmtree(MEM)
t = avatar_turn("read shared/PLAN.md")
completed("no memory/file-reads.json (no memory dir at all): the turn completes", t, polite=False, must=("comet",))
check("  and the store is made again, whole", isinstance(json.load(open(STORE)), list))
write(STORE, b"\x00{not json \xff")
t = avatar_turn("read shared/PLAN.md")
completed("corrupt file-reads.json: the turn completes", t, polite=False, must=("comet",))
check("  the corrupt store is set aside, not trusted, and a whole one written",
      glob.glob(STORE + ".corrupt-*") and isinstance(json.load(open(STORE)), list))
write(STORE, '{"not": "a list"}')
completed("a store that is not a list: the turn completes", avatar_turn("read shared/PLAN.md"), polite=False)
write(STORE, json.dumps([{"at": "soon", "lines": "many", "kind": "read", "label": "shared/PLAN.md", "text": 5},
                         5, None, {"kind": "find", "asked": None}]))
completed("malformed rows in the store: the turn completes", avatar_turn("hello"), polite=False)

# ---- a busy store: another writer holds the lock
import fcntl
write(STORE, "[]")
before = open(STORE, "rb").read()
_wait = F.LOCK_WAIT_S; F.LOCK_WAIT_S = 0.2
fd = os.open(STORE + ".lock", os.O_RDWR | os.O_CREAT); fcntl.flock(fd, fcntl.LOCK_EX)
try:
    t = avatar_turn("read shared/PLAN.md")
    completed("busy store (lock held elsewhere): the turn completes and still shows her file", t, polite=False,
              must=("comet",))
    check("  the lock is waited on briefly, never waited out", t["secs"] < 1.5, t["secs"])
    check("  and the store is left as the other writer has it", open(STORE, "rb").read() == before)
finally:
    fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd); F.LOCK_WAIT_S = _wait

# ---- a store that cannot be written (disk full)
_wa = F._write_atomic
def full(*a, **k): raise OSError(28, "No space left on device")
F._write_atomic = full
try:
    completed("store cannot be written: the turn completes and still shows her file",
              avatar_turn("read shared/PLAN.md"), polite=False, must=("comet",))
finally:
    F._write_atomic = _wa

# ---- a read that hangs
_read, _budget = F.read, F.BUDGET_S
def slow(*a, **k):
    time.sleep(2.0); return _read(*a, **k)
F.read, F.BUDGET_S = slow, 0.3
try:
    t = avatar_turn("read shared/PLAN.md")
    completed("a hung read: the turn goes on within its budget", t, must=("in time",))
    check("  well inside a second and a half", t["secs"] < 1.5, t["secs"])
    t = avatar_turn("hi", model_reply="Let me see. [READ: shared/PLAN.md]")
    completed("his own hung read: the reply is out on time, tag removed", t, polite=False)
    check("  his words reach her without the tag", t["reply"] == "Let me see.", t["reply"])
finally:
    settle(); F.read, F.BUDGET_S = _read, _budget

# ---- the Study missing, and a SystemExit inside a read
_room, F._ROOM = F.room, None
def no_room(): raise RuntimeError("the Study (study_chat.py) is not installed")
F.room = no_room
try:
    completed("the Study missing: the turn completes", avatar_turn("read shared/PLAN.md",
                                                                    "ok [READ: shared/PLAN.md]"), polite=False)
finally:
    F.room = _room
def exits(*a, **k): raise SystemExit(3)
F.read = exits
try:
    completed("a SystemExit inside a read: the turn completes, 'couldn't open that'",
              avatar_turn("read shared/PLAN.md"))
finally:
    F.read = _read

# ---- his own tags that fail
t = avatar_turn("hi", model_reply="Sure. [READ: shared/NOT-THERE.md] [FIND: x\x00y]")
completed("his failing [READ]/[FIND]: the turn completes", t, polite=False)
check("  his tags are gone from what she sees", t["reply"] == "Sure.", t["reply"])
check("  and next turn he is told politely", "couldn't open that" in F.block())

# ---- file_reach itself raising: the route's own guard still holds
_tb, _tk = F.turn_block, F.take
def boom(*a, **k): raise RuntimeError("synthetic failure inside file_reach")
F.turn_block = F.take = boom
try:
    completed("file_reach raising: the avatar turn completes, both hooks run",
              avatar_turn("read shared/PLAN.md", "hi [READ: shared/PLAN.md]"), polite=False)
    for name, code in (("/api/chat", CTX_CHAT), ("/api/chat/full", CTX_FULL)):
        t = chat_turn("read shared/PLAN.md", code)
        check("file_reach raising: %s completes, both hooks run" % name,
              t["err"] is None and t["hooks"] == ["subcon_tail", "post_turn"], t)
finally:
    F.turn_block, F.take = _tb, _tk
for name, code in (("/api/chat", CTX_CHAT), ("/api/chat/full", CTX_FULL)):
    t = chat_turn("please read shared/NOT-THERE.md", code)
    check("%s with a missing file: completes, 'couldn't open that'" % name,
          t["err"] is None and t["hooks"] == ["subcon_tail", "post_turn"] and "couldn't open that" in t["ctx"]
          and t["reply"] == "ok", t)

# ---- concurrent writers: the store stays whole, nothing left behind
write(STORE, "[]")
errs = []
def writer(n):
    try:
        for i in range(6):
            F._keep([{"at": time.time(), "by": "him", "surface": "avatar", "kind": "find", "asked": "w%d-%d" % (n, i),
                      "label": None, "sha": None, "lines": 0, "text": "x" * 2000}])
            avatar_turn("read shared/PLAN.md")
    except BaseException as e:
        errs.append(e)
ths = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
[th.start() for th in ths]; [th.join(60) for th in ths]
rows = json.load(open(STORE))
check("eight writers at once: no error, the store is whole JSON within its row limit",
      not errs and isinstance(rows, list) and 0 < len(rows) <= F.KEEP, (errs, len(rows)))
check("  no temporary files left beside it", not glob.glob(STORE + ".tmp.*"), glob.glob(STORE + ".tmp.*"))

check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
