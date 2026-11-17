#!/usr/bin/env python3
"""file_reach.py - his own files, and the files Gloria points him to, from the main chat and the avatar chat
(Gloria, 17 November 2026: she wanted to point him at the exact file that says what is being tested today and
tomorrow; he could read files only in the Study, and nothing of what he read there stayed with him).

Why he could not before: the Study (study_chat.py) is the one room with READ and GREP, and it is walled off from his
life by design - its reads go to its own log and its own cursor (study-session.json), never into a conversation. The
main chat and the avatar chat are one model call each, with no file tool offered at all.

The boundary is the Study's own, imported, not copied: study_chat.resolve() decides what may be opened (his scripts/,
his house ~/Vintos, the .md documents at the workspace root, and shared/ - what Gloria or Claude put there for him),
with its secret deny list and its text-only rule; study_chat.do_grep() searches. Nothing here writes a file of his,
and nothing here moves the Study's own reading cursor.

    hers(text)     a file Gloria names in her message (shared/X.md, scripts/x.py, a workspace path, or a bare name
                   with "read"/"open"/"look at"), "find/search your files for ...", or "what did we do yesterday" /
                   "today's summary" (shared/DAILY-YYYY-MM-DD.md): done now, in this turn
    read on        a file is whole up to OPEN_CHARS (24 KB); a longer one ends "continues — ask to read on", and her
                   "read on" / "keep reading", or his [READ ON], opens the next page from where it stopped
    take(reply)    his [READ: path] / [READ: path:400] / [FIND: words] in a reply: taken out of his words, done, and
                   in front of him on his next turn
    block()        [FILES YOU HAVE READ ...] for his context: the file he has open in full, then short sourced notes
                   of what else he read, so he can come back to it later in the conversation and across turns

Never in the way (Gloria, 17 November: retrieval from the avatar route must never break the subcons with an error).
Every public call here returns, whatever happens: a missing, forbidden, unreadable, oversized or badly encoded file,
a bad path, a missing or corrupt store, a busy store, a missing Study - each becomes "couldn't open that: <why>" in
his context, and the chat goes on. The file work of a turn has a time budget (BUDGET_S); past it the turn goes on
without it. The store is written whole or not at all (a temporary file, then a rename) under a lock that is waited
on for at most LOCK_WAIT_S; a busy store is skipped, never waited out, and a corrupt one is set aside, not trusted.

Store: memory/file-reads.json - one row a read or a search: when, who asked (her / him), the surface, the file's label,
its fingerprint, and what it said (capped). Kept KEEP rows, KEEP_DAYS days. A row whose file has changed since says so.
"""
import contextlib, hashlib, importlib.util, json, os, re, sys, threading, time
from datetime import datetime, timedelta

STORE_NAME = "file-reads.json"
KEEP = 12                  # rows kept
KEEP_DAYS = 7
OPEN_S = 45 * 60           # the newest read stays open in full this long after it was read
OPEN_CHARS = 24_576        # one read: up to 24 KB of the file's own text, whole (the Study allows 14,000 a read).
#                            17 Nov: a second file of the same turn was cut at 3,000 chars - he lost yesterday's
#                            note partway; a file now reaches him whole up to this, and past it pages ("read on").
OPEN_TOTAL = 40_000        # all files open in full in one context, line numbers included (~10K tokens)
SECOND_CHARS = OPEN_TOTAL  # kept for older callers: a second open file shares OPEN_TOTAL, no fixed smaller cap
NOTE_CHARS = 500           # a note of an older read
FIND_LINES = 25
PER_TURN = 2               # reads/searches a turn, hers or his
NOTES_SHOWN = 5
MAX_BYTES = 2_000_000      # a file larger than this is not opened in a chat
BUDGET_S = 4.0             # the file work of one turn; past it the turn goes on without it
LOCK_WAIT_S = 2.0          # how long a write waits for the store's lock before it gives up (never blocks a turn)
DAILY = "shared/DAILY-%Y-%m-%d.md"   # the day's summary Gloria or Claude leaves him
_TAG = re.compile(r"\[(READ|FIND)\s*(?::\s*|\s+(?=(?:on|more|next)\s*\]))([^\]\n]{1,200})\]", re.I)
_ON_WORDS = ("on", "more", "next", "continue", "read on", "the rest", "rest")
# her "read on" / "keep reading" / "the rest of the note": go on from where the last cut-off read stopped
_READ_ON = re.compile(r"\b(?:read on\b(?!\s+(?:the|a|an|my|your|his|her|our|this|that|it)\b)|keep reading|carry on reading|go on reading|continue reading|read the rest"
                      r"|rest of (?:the|that|it|this) (?:file|note|summary|doc\w*)|(?:from )?where you left off)\b", re.I)
_CONT = re.compile(r"continues .{0,40}?\[READ: ([^\]\n]+?):(\d+)(?::(\d+))?\]")
_CONT_OLD = re.compile(r"continue with \[READ: ([^\]\n]+?):(\d+)\]")   # rows kept before 17 Nov
_EXT = r"(?:md|txt|py|sh|json|yaml|yml|toml)"
_PATHISH = re.compile(r"(?<![\w./~-])((?:~|/home/[\w.-]+)?[\w./~-]*?[\w.-]+\." + _EXT + r")(?::(\d{1,6}))?(?![\w/])", re.I)
_VERB = re.compile(r"\b(read|open|look (?:at|over|through)|check|go through|have a look|see the file|in the file)\b", re.I)
_FIND = re.compile(r"\b(?:find|search|look (?:for|up)|list)\b[^.?!\n]{0,40}?\bfiles?\b[^.?!\n]{0,24}?"
                   r"\b(?:about|on|for|called|named|mentioning|with)\s+[\"“']?([^\"”'.?!\n]{2,60})", re.I)
# "what did we do yesterday", "today's summary", "the summary of yesterday", "yesterday's recap"
_DAY = re.compile(r"\b(today|yesterday)\b", re.I)
_DAILY_ASK = re.compile(r"\bwhat (?:did|have) (?:we|you|i) (?:do|done|get up to|work on)\b|\bwhat happened\b"
                        r"|\bwhat we did\b", re.I)
_DAILY_NAMED = re.compile(r"\b(?:summary|summaries|recap|daily notes?|day'?s notes?)\b", re.I)
_UNABLE = "couldn't open that"


def _ws():
    return os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")


def _store(mem=None):
    return os.path.join(mem or os.path.join(_ws(), "memory"), STORE_NAME)


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


_ROOM = None


def room():
    """The Study's own module (study_chat.py), so its permission boundary is the one that applies (as forge_study and
    dot_channel load it)."""
    global _ROOM
    if _ROOM is not None:
        return _ROOM
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.expanduser("~/Vintos/study_chat.py"), os.path.join(here, "study_chat.py"),
                 os.path.join(here, "..", "bin", "study_chat.py")):
        if os.path.exists(path):
            d = os.path.dirname(os.path.abspath(path))
            if d not in sys.path:
                sys.path.append(d)            # its own neighbours (paid_http)
            spec = importlib.util.spec_from_file_location("study_chat_for_file_reach", path)
            m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
            _ROOM = m
            return m
    raise RuntimeError("the Study (study_chat.py) is not installed")


def _label(r, path):
    return r._label_path(path) or os.path.basename(path)


def daily_label(text, now=None):
    """'yesterday's summary' / 'today's summary' (or a question about what was done that day) -> the label of that
    day's summary in shared/, else None."""
    m = _DAY.search(str(text or ""))
    if not m:
        return None
    day = datetime.fromtimestamp(time.time() if now is None else now)
    if m.group(1).lower() == "yesterday":
        day -= timedelta(days=1)
    return day.strftime(DAILY)


def _resolve(r, arg):
    """A label, a bare name, or an absolute/home path -> (real path, label), through the Study's resolve() only."""
    arg = str(arg or "").strip().strip("`'\"“”")
    if not arg or "\x00" in arg or len(arg) > 1024:
        return None, None
    if arg.startswith(("~", "/")):
        lab = r._label_path(os.path.expanduser(arg))
        if not lab:
            return None, None
        arg = lab
    elif _DAILY_NAMED.search(arg) and _DAY.search(arg) and "/" not in arg:
        arg = daily_label(arg)                # his own [READ: yesterday's summary]
    p = r.resolve(arg)
    return (p, _label(r, p)) if p else (None, None)


def read(arg, cap=OPEN_CHARS):
    """One file, read only: numbered lines from a start line, cut at cap with where to continue. (label, text, sha, n)
    or (None, why, None, 0). Never larger than MAX_BYTES; undecodable bytes are shown replaced, never raised."""
    r = room()
    position = re.search(r":(\d+)(?::(\d+))?\s*$", str(arg or ""))
    path_arg = str(arg)[:position.start()] if position else arg
    start = position.group(1) if position else ""
    offset = int(position.group(2) or 0) if position else 0
    p, lab = _resolve(r, path_arg)
    if not p:
        return None, "%s: %s is not there, or not one of the files you may read" % (_UNABLE, str(arg)[:160]), None, 0
    size = os.path.getsize(p)
    if size > MAX_BYTES:
        return None, "%s: %s is too large to open in a chat (%.1f MB); look inside it with [FIND: words]" % (
            _UNABLE, lab, size / 1e6), None, 0
    with open(p, "rb") as f:
        data = f.read(MAX_BYTES + 1)
    lines = data.decode("utf-8", "replace").split("\n")
    try: a = max(1, int(start or 1))
    except ValueError: a = 1
    if lines and lines[-1] == "":
        lines.pop()                           # the file's last newline is not a line of its own
    out, used, i = [], 0, a - 1
    while i < len(lines):
        # the cap counts the file's own text; the line numbers in front are extra (OPEN_TOTAL covers them)
        segment = lines[i][offset:]
        if out and used + len(segment) + 1 > cap: break
        available = max(1, cap - used)
        out.append("%5d  %s" % (i + 1, segment[:available]))
        if len(segment) > available:
            offset += available
            break
        used += len(segment) + 1
        i += 1
        offset = 0
    body = "\n".join(out)
    if i < len(lines):
        body += "\n" + more_line(lab, i, len(lines), offset)
    return lab, body, hashlib.sha256(data).hexdigest()[:16], len(lines)


def more_line(lab, last, total, offset=0):
    """Where a cut-off read stopped, and how to go on."""
    if offset:
        return "... (line %d continues at character %d; continues — ask to read on, or [READ: %s:%d:%d])" % (last + 1, offset, lab, last + 1, offset)
    return "... (lines %d-%d of %d not shown yet; continues — ask to read on, or [READ: %s:%d])" % (
        last + 1, total, total, lab, last + 1)


def next_of(row):
    """(label, line) a cut-off read row goes on from, else None."""
    if not isinstance(row, dict) or row.get("kind") != "read" or not row.get("label"):
        return None
    if row.get("next"):
        base = (row["label"], int(_num(row["next"])))
        return base + (int(_num(row["next_char"])),) if row.get("next_char") else base
    text = str(row.get("text") or "")
    m = _CONT.search(text) or _CONT_OLD.search(text)
    if not m:
        return None
    base = (m.group(1), int(m.group(2)))
    return base + (int(m.group(3)),) if m.re is _CONT and m.group(3) else base


def read_on_arg(mem=None):
    """'read on': the newest kept read that was cut off -> 'label:line', else None."""
    for row in sorted(_load(mem), key=lambda x: _num(x.get("at")), reverse=True):
        if row.get("kind") == "read" and row.get("label"):
            nx = next_of(row)
            return (("%s:%d:%d" if len(nx) == 3 else "%s:%d") % nx) if nx else None
    return None


def find(query, limit=FIND_LINES):
    """His files by name, then by what is in them (the Study's own search). A root's name alone lists that folder."""
    r = room()
    q = str(query or "").strip().strip("`'\"“”")
    if not q:
        return "nothing to search for"
    words = [w for w in re.findall(r"[\w.-]{2,}", q.lower())]
    named = []
    for label, root in r.ROOTS.items():
        exts = (".md",) if label == "docs" else (".md", ".txt") if label == "shared" else (".py", ".sh", ".md")
        listing = q.lower().rstrip("/") == label
        try:
            if label == "docs":
                names = [f for f in os.listdir(root) if f.endswith(exts)]
            else:
                names = []
                for d, subs, files in os.walk(root):
                    subs[:] = [s for s in subs if not s.startswith((".", "__"))]
                    names += [os.path.relpath(os.path.join(d, f), root) for f in files if f.endswith(exts)]
        except OSError:
            continue
        for n in sorted(names):
            if ".bak" in n or n.startswith("."):
                continue
            if listing or (words and all(w in n.lower() for w in words)):
                if r.resolve("%s/%s" % (label, n)):
                    named.append("%s/%s" % (label, n))
    out = []
    if named:
        out.append("Files named like that (%d):\n%s%s" % (len(named), "\n".join(named[:limit]),
                                                          "\n..." if len(named) > limit else ""))
    if q.lower().rstrip("/") not in r.ROOTS:
        g = r.do_grep(q, max_lines=limit)
        out.append(g.replace("GREP ", "Inside files, ", 1))
    return "\n\n".join(out) or "no file is named like that"


# ---- the store: whole-file writes under a lock that is never waited out --------------------------------------------

def _load_state(mem=None):
    """(rows, state): state is "ok", "missing", "corrupt" (not JSON, not a list, not UTF-8) or "unreadable"."""
    path = _store(mem)
    try:
        f = open(path, encoding="utf-8")
    except FileNotFoundError:
        return [], "missing"
    except (OSError, ValueError):
        return [], "unreadable"
    try:
        with f:
            d = json.load(f)
    except (ValueError, UnicodeError, OSError, RecursionError):
        return [], "corrupt"
    if not isinstance(d, list):
        return [], "corrupt"
    return [dict(x, at=_num(x.get("at"))) for x in d if isinstance(x, dict)], "ok"


def _load(mem=None):
    return _load_state(mem)[0]


@contextlib.contextmanager
def _locked(path, wait=None):
    """The store's lock (flock on <store>.lock): yields True when held, False when another writer kept it past `wait`
    seconds or no lock could be made. Never blocks longer than `wait`."""
    wait = LOCK_WAIT_S if wait is None else wait
    try:
        import fcntl
    except ImportError:                       # not a POSIX host: whole-file renames still keep the store whole
        yield True
        return
    try:
        fd = os.open(path + ".lock", os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        yield False
        return
    got = False
    try:
        end = time.monotonic() + max(0.0, wait)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); got = True; break
            except OSError:
                if time.monotonic() >= end:
                    break
                time.sleep(0.02)
        yield got
    finally:
        if got:
            try: fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError: pass
        os.close(fd)


def _write_atomic(path, rows):
    """The whole store, or nothing: a private temporary file, flushed to disk, renamed over the store."""
    tmp = "%s.tmp.%d.%d.%s" % (path, os.getpid(), threading.get_ident(), os.urandom(3).hex())
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except (OSError, ValueError, TypeError) as e:
        print("[file-reach] not kept: %s" % e, flush=True)
        with contextlib.suppress(OSError):
            os.remove(tmp)
        return False


def _same(a, b):
    return (a.get("kind"), a.get("label") or a.get("asked"), a.get("sha")) == \
           (b.get("kind"), b.get("label") or b.get("asked"), b.get("sha"))


def _keep(new, mem=None, now=None):
    """New rows added to the kept ones; an older row of the same unchanged file (or the same search) gives way, so
    reading a file again moves it to the front instead of keeping it twice. True when kept. A busy store (its lock
    held past LOCK_WAIT_S) or one that cannot be written is skipped; a corrupt one is set aside, then started again."""
    now = time.time() if now is None else now
    path = _store(mem)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _locked(path) as got:
            if not got:
                print("[file-reach] not kept: the store is busy", flush=True)
                return False
            old, state = _load_state(mem)
            if state == "unreadable":
                print("[file-reach] not kept: the store cannot be read", flush=True)
                return False
            if state == "corrupt":
                with contextlib.suppress(OSError):
                    os.replace(path, "%s.corrupt-%d" % (path, int(now)))
                print("[file-reach] the store was not readable JSON; set aside, started again", flush=True)
            old = [x for x in old if not any(_same(x, n) for n in new)]
            rows = [x for x in old + list(new) if now - _num(x.get("at")) <= KEEP_DAYS * 86400][-KEEP:]
            return _write_atomic(path, rows)
    except Exception as e:
        print("[file-reach] not kept: %s" % e, flush=True)
        return False


# ---- doing a read or a search -------------------------------------------------------------------------------------

def _why(e):
    """A plain reason for a failed open, for his context; never a traceback."""
    if isinstance(e, FileNotFoundError):
        return "it is not there any more"
    if isinstance(e, PermissionError):
        return "it is not open to me (permission)"
    if isinstance(e, IsADirectoryError):
        return "it is a folder, not a file"
    if isinstance(e, UnicodeError):
        return "its text could not be read"
    if isinstance(e, MemoryError):
        return "it is too large"
    return "something went wrong opening it"


def _do(kind, arg, by, surface, now, mem=None):
    kind = str(kind or "").upper()
    try:
        if kind == "READ":
            asked = arg
            if str(arg or "").strip().lower() in _ON_WORDS:
                arg = read_on_arg(mem)
                if not arg:
                    return {"at": now, "by": by, "surface": surface, "kind": "read", "asked": "read on",
                            "label": None, "sha": None, "lines": 0,
                            "text": "nothing to read on from: the last file you read was shown to its end"}
            lab, text, sha, n = read(arg)
            m = _CONT.search(text or "") if lab else None
            return {"at": now, "by": by, "surface": surface, "kind": "read", "asked": str(asked)[:200],
                    "label": lab, "sha": sha, "lines": n, "text": text, "next": int(m.group(2)) if m else None,
                    "next_char": int(m.group(3)) if m and m.group(3) else None}
        return {"at": now, "by": by, "surface": surface, "kind": "find", "asked": str(arg)[:200],
                "label": None, "sha": None, "lines": 0, "text": str(find(arg))[:OPEN_CHARS]}
    except (Exception, SystemExit) as e:
        print("[file-reach] %s %r: %s" % (kind.lower(), str(arg)[:80], e), flush=True)
        return {"at": now, "by": by, "surface": surface, "kind": "read" if kind == "READ" else "find",
                "asked": str(arg)[:200], "label": None, "sha": None, "lines": 0,
                "text": "%s: %s" % (_UNABLE, _why(e))}


def _bounded(fn, budget=None):
    """fn() in its own thread, waited on for `budget` seconds: (finished, result). Past the budget the turn goes on
    and fn finishes on its own (what it keeps is in front of him next turn)."""
    budget = BUDGET_S if budget is None else budget
    box = {}

    def run():
        try:
            box["v"] = fn()
        except BaseException as e:            # noqa: B902 - nothing leaves this thread
            box["e"] = e
    try:
        t = threading.Thread(target=run, name="file-reach", daemon=True)
        t.start()
    except RuntimeError:                      # no thread to be had: do it here
        run()
        return "e" not in box, box.get("v")
    t.join(max(0.0, budget))
    if t.is_alive():
        print("[file-reach] past its %.1fs budget; the turn goes on" % budget, flush=True)
        return False, None
    if "e" in box:
        print("[file-reach] %s" % box["e"], flush=True)
    return "e" not in box, box.get("v")


def asks_in(text, now=None):
    """What Gloria's message points him to: [(kind, arg)], at most PER_TURN. A path with a folder of his roots, or a
    home/absolute path, is a pointer by itself; a bare file name needs a word like read/open/look at beside it. A
    rooted path she asks him to read that cannot be opened is still asked, so he can tell her it couldn't be opened.
    'what did we do yesterday' / 'today's summary' asks for that day's shared/DAILY-YYYY-MM-DD.md."""
    text = str(text or "")
    out = []
    r = room()
    verb = bool(_VERB.search(text))
    for m in _PATHISH.finditer(text):
        token, line = m.group(1), m.group(2)
        root_label = token.split("/", 1)[0] in r.ROOTS
        rooted = token.startswith(("~", "/")) or root_label
        if not (rooted or verb):
            continue
        if "/" in token and not rooted:
            continue
        arg = token + ((":" + line) if line else "")
        if ("READ", arg) in out:
            continue
        if _resolve(r, token)[0] or (verb and root_label and "/" in token):
            out.append(("READ", arg))
    for m in _FIND.finditer(text):
        q = m.group(1).strip()
        if q and ("FIND", q) not in out:
            out.append(("FIND", q))
    if not out and _READ_ON.search(text):
        out.append(("READ", "on"))            # "read on" / "keep reading": from where the last cut-off read stopped
    day = daily_label(text, now) if (_DAILY_ASK.search(text) or _DAILY_NAMED.search(text)) else None
    if day and ("READ", day) not in out:
        # named outright ("yesterday's summary"): asked even when it is not there, so he can say so;
        # only a question about the day ("what did we do yesterday"): asked when the summary is there
        if _DAILY_NAMED.search(text) or _resolve(r, day)[0]:
            out.append(("READ", day))
    return out[:PER_TURN]


def hers(text, surface="chat", act=True, mem=None, now=None):
    """Read what her message points him to, now. Kept for later turns unless act is False; returns the new rows."""
    now = time.time() if now is None else now
    try:
        asks = asks_in(text, now)
        rows = [_do(k, a, "her", surface, now, mem) for k, a in asks]
        if rows and act:
            _keep(rows, mem, now)
        return rows
    except (Exception, SystemExit) as e:
        print("[file-reach/hers]", e, flush=True)
        return []


def take(reply, surface="chat", act=True, mem=None, now=None, budget=None):
    """His [READ: ...] / [FIND: ...] taken out of a reply; done and kept (unless act is False) for his next turn.
    Always returns the reply (without the tags); the reads have BUDGET_S, then finish on their own."""
    try:
        if not reply or not _TAG.search(reply):
            return reply
    except (Exception, SystemExit):
        return reply
    if act:
        now = time.time() if now is None else now

        def work():
            try:
                rows = [_do(k, a.strip(), "him", surface, now, mem) for k, a in _TAG.findall(reply)[:PER_TURN]]
                _keep(rows, mem, now)
            except (Exception, SystemExit) as e:
                print("[file-reach/take]", e, flush=True)
        _bounded(work, budget)
    try:
        return re.sub(r"[ \t]*" + _TAG.pattern + r"[ \t]*", " ", reply, flags=re.I).strip()
    except (Exception, SystemExit):
        return reply


def _when(ts):
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%b %d %H:%M")
    except Exception:
        return "at an unrecorded time"


def _changed(row):
    """True when the file a read row names is different now (or gone)."""
    if row.get("kind") != "read" or not row.get("label"):
        return False
    try:
        p = room().resolve(row["label"])
        if p and os.path.getsize(p) > MAX_BYTES:
            return False
        return not p or hashlib.sha256(open(p, "rb").read()).hexdigest()[:16] != row.get("sha")
    except Exception:
        return False


def _who(row):
    return "Gloria pointed you to" if row.get("by") == "her" else "You asked for"


def _by(row):
    return "Gloria pointed you to it" if row.get("by") == "her" else "you read it"


_HOW = ("To read a file: [READ: shared/NAME.md] (or scripts/x.py, house/x.py, docs/NAME.md; add :LINE to go on from "
        "a line). A file up to 24 KB comes whole; a longer one says where it stops, and [READ ON] goes on from there. "
        "To look for one: [FIND: words]. Write the tag on its own in a reply; what it finds is in front of "
        "you on your next turn. Gloria's files for you are in shared/; a summary of what you did together on a day is "
        "shared/DAILY-YYYY-MM-DD.md ([READ: yesterday's summary] works too).")
EMPTY = ("[YOUR FILES - you can read your own files and the ones Gloria leaves for you in shared/, read only. "
         + _HOW + "]")


def render(rows, now=None):
    """The block for these rows, newest first: the newest open in full, the rest as short notes."""
    now = time.time() if now is None else now
    rows = [x for x in rows if isinstance(x, dict)]
    if not rows:
        return ""
    head = ("[FILES YOU HAVE READ - from your own files and the shared folder, read only. What each said is quoted "
            "from the file, not remembered. " + _HOW + "]")
    parts = [head]
    newest = sorted(rows, key=lambda x: _num(x.get("at")), reverse=True)
    opened = [x for x in newest if now - _num(x.get("at")) <= OPEN_S][:PER_TURN]
    left = OPEN_TOTAL                         # every open file shares this; the newest is never cut below its read
    for x in opened:
        try:
            what = x.get("label") or x.get("asked")
            stale = " (it has changed since; read it again for the current text)" if _changed(x) else ""
            kind = "the file" if x.get("kind") == "read" else "a search of your files for"
            text = str(x.get("text") or "")
            if len(text) > left:
                cut = text[:max(0, left)].rsplit("\n", 1)[0] if left > 0 else ""
                shown = re.findall(r"^\s*(\d+)  ", cut, flags=re.M)
                if x.get("kind") == "read" and x.get("label") and shown:
                    last = int(shown[-1])
                    text = cut + "\n" + more_line(x["label"], last, int(_num(x.get("lines"))) or last + 1)
                elif x.get("kind") == "read" and x.get("label"):
                    text = "(not shown this turn, there was no room; ask to read %s again)" % x["label"]
                else:
                    text = cut + "\n... (more found; search again for the rest)"
            left -= len(text)
            parts.append("%s %s %s, %s%s:\n%s" % (_who(x), kind, what, _when(x.get("at")), stale, text))
        except Exception:
            continue
    notes = [x for x in newest if x not in opened][:NOTES_SHOWN]
    if notes:
        lines = ["Earlier reads (notes; read again for the whole text):"]
        for x in notes:
            try:
                stale = " - changed since" if _changed(x) else ""
                if x.get("kind") == "read" and x.get("label"):
                    body = re.sub(r"^\s*\d+  ", "", str(x.get("text") or ""), flags=re.M)
                    lines.append("- %s, %s (%d lines)%s, %s; it begins: %s" % (
                        x["label"], _when(x.get("at")), int(_num(x.get("lines"))), stale, _by(x),
                        json.dumps(body[:NOTE_CHARS], ensure_ascii=False)))
                else:
                    lines.append("- search for %s, %s: %s" % (json.dumps(str(x.get("asked"))), _when(x.get("at")),
                                                              json.dumps(str(x.get("text") or "")[:NOTE_CHARS // 2],
                                                                         ensure_ascii=False)))
            except Exception:
                continue
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def block(now=None, mem=None, extra=None):
    """His file reads for his context: the kept rows, plus `extra` (this turn's, when they were not kept: a test turn,
    or a busy store). The head alone, saying how to read, when he has read nothing yet. Read only; never raises."""
    now = time.time() if now is None else now
    try:
        kept = [x for x in _load(mem) if now - _num(x.get("at")) <= KEEP_DAYS * 86400]
        fresh = [x for x in (extra or []) if isinstance(x, dict)
                 and not any(_same(x, k) and _num(k.get("at")) == _num(x.get("at")) for k in kept)]
        rows = kept + fresh
        return render(rows, now) if rows else EMPTY
    except (Exception, SystemExit) as e:
        print("[file-reach/block]", e, flush=True)
        return EMPTY


def turn_block(her_text, surface="chat", act=True, mem=None, now=None, budget=None):
    """One call for a chat route: read what her message points to (kept unless act is False), then the block.
    Never raises, and never holds the turn past BUDGET_S."""
    now = time.time() if now is None else now
    try:
        done, fresh = _bounded(lambda: hers(her_text, surface, act=act, mem=mem, now=now), budget)
        if not done:
            fresh = [{"at": now, "by": "her", "surface": surface, "kind": "read", "asked": "the file Gloria pointed to",
                      "label": None, "sha": None, "lines": 0,
                      "text": "%s in time%s" % (_UNABLE, "; it is still opening and will be in front of you on your "
                                                         "next turn" if act else "")}]
        return block(now=now, mem=mem, extra=fresh)
    except (Exception, SystemExit) as e:
        print("[file-reach/turn]", e, flush=True)
        return EMPTY


def main(argv):
    if len(argv) > 2 and argv[1] in ("read", "find"):
        print(read(" ".join(argv[2:]))[1] if argv[1] == "read" else find(" ".join(argv[2:])))
    else:
        print(block())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
