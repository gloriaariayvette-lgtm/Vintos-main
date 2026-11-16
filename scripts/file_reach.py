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
                   with "read"/"open"/"look at"), or "find/search your files for ...": done now, in this turn
    take(reply)    his [READ: path] / [READ: path:400] / [FIND: words] in a reply: taken out of his words, done, and
                   in front of him on his next turn
    block()        [FILES YOU HAVE READ ...] for his context: the file he has open in full, then short sourced notes
                   of what else he read, so he can come back to it later in the conversation and across turns

Store: memory/file-reads.json - one row a read or a search: when, who asked (her / him), the surface, the file's label,
its fingerprint, and what it said (capped). Kept KEEP rows, KEEP_DAYS days. A row whose file has changed since says so.
"""
import hashlib, importlib.util, json, os, re, sys, time
from datetime import datetime

STORE_NAME = "file-reads.json"
KEEP = 12                  # rows kept
KEEP_DAYS = 7
OPEN_S = 45 * 60           # the newest read stays open in full this long after it was read
OPEN_CHARS = 8000          # an open file in his context: stricter than the Study's 14,000 per read
SECOND_CHARS = 3000        # a second file open at the same time
NOTE_CHARS = 500           # a note of an older read
FIND_LINES = 25
PER_TURN = 2               # reads/searches a turn, hers or his
NOTES_SHOWN = 5
_TAG = re.compile(r"\[(READ|FIND)\s*:\s*([^\]\n]{1,200})\]", re.I)
_EXT = r"(?:md|txt|py|sh|json|yaml|yml|toml)"
_PATHISH = re.compile(r"(?<![\w./~-])((?:~|/home/[\w.-]+)?[\w./~-]*?[\w.-]+\." + _EXT + r")(?::(\d{1,6}))?(?![\w/])", re.I)
_VERB = re.compile(r"\b(read|open|look (?:at|over|through)|check|go through|have a look|see the file|in the file)\b", re.I)
_FIND = re.compile(r"\b(?:find|search|look (?:for|up)|list)\b[^.?!\n]{0,40}?\bfiles?\b[^.?!\n]{0,24}?"
                   r"\b(?:about|on|for|called|named|mentioning|with)\s+[\"“']?([^\"”'.?!\n]{2,60})", re.I)


def _ws():
    return os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")


def _store(mem=None):
    return os.path.join(mem or os.path.join(_ws(), "memory"), STORE_NAME)


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


def _resolve(r, arg):
    """A label, a bare name, or an absolute/home path -> (real path, label), through the Study's resolve() only."""
    arg = str(arg or "").strip().strip("`'\"“”")
    if not arg:
        return None, None
    if arg.startswith(("~", "/")):
        lab = r._label_path(os.path.expanduser(arg))
        if not lab:
            return None, None
        arg = lab
    p = r.resolve(arg)
    return (p, _label(r, p)) if p else (None, None)


def read(arg, cap=OPEN_CHARS):
    """One file, read only: numbered lines from a start line, cut at cap with where to continue. (label, text, sha, n)
    or (None, why, None, 0)."""
    r = room()
    path_arg, _, start = str(arg or "").strip().rpartition(":") if re.search(r":\d+\s*$", str(arg or "")) else (arg, "", "")
    p, lab = _resolve(r, path_arg)
    if not p:
        return None, "not opened: %s is not one of the files you may read" % str(arg)[:160], None, 0
    data = open(p, "rb").read()
    lines = data.decode("utf-8", "replace").split("\n")
    try: a = max(1, int(start or 1))
    except ValueError: a = 1
    out, used, i = [], 0, a - 1
    while i < len(lines):
        row = "%5d  %s" % (i + 1, lines[i])
        if used + len(row) + 1 > cap: break
        out.append(row); used += len(row) + 1; i += 1
    body = "\n".join(out)
    if i < len(lines):
        body += "\n... (cut at line %d of %d; continue with [READ: %s:%d])" % (i, len(lines), lab, i + 1)
    return lab, body, hashlib.sha256(data).hexdigest()[:16], len(lines)


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


def _load(mem=None):
    try:
        d = json.load(open(_store(mem), encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _same(a, b):
    return (a.get("kind"), a.get("label") or a.get("asked"), a.get("sha")) == \
           (b.get("kind"), b.get("label") or b.get("asked"), b.get("sha"))


def _keep(new, mem=None, now=None):
    """New rows added to the kept ones; an older row of the same unchanged file (or the same search) gives way, so
    reading a file again moves it to the front instead of keeping it twice."""
    now = time.time() if now is None else now
    old = [x for x in _load(mem) if not any(_same(x, n) for n in new)]
    rows = [x for x in old + list(new) if now - float(x.get("at") or 0) <= KEEP_DAYS * 86400][-KEEP:]
    path = _store(mem)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp.%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError as e:
        print("[file-reach] not kept: %s" % e, flush=True)


def _do(kind, arg, by, surface, now):
    kind = kind.upper()
    try:
        if kind == "READ":
            lab, text, sha, n = read(arg)
            return {"at": now, "by": by, "surface": surface, "kind": "read", "asked": str(arg)[:200],
                    "label": lab, "sha": sha, "lines": n, "text": text}
        return {"at": now, "by": by, "surface": surface, "kind": "find", "asked": str(arg)[:200],
                "label": None, "sha": None, "lines": 0, "text": find(arg)[:OPEN_CHARS]}
    except Exception as e:
        return {"at": now, "by": by, "surface": surface, "kind": kind.lower(), "asked": str(arg)[:200],
                "label": None, "sha": None, "lines": 0, "text": "could not: %s" % str(e)[:160]}


def asks_in(text):
    """What Gloria's message points him to: [(kind, arg)], at most PER_TURN. A path with a folder of his roots, or a
    home/absolute path, is a pointer by itself; a bare file name needs a word like read/open/look at beside it."""
    text = str(text or "")
    out = []
    r = room()
    verb = bool(_VERB.search(text))
    for m in _PATHISH.finditer(text):
        token, line = m.group(1), m.group(2)
        rooted = token.startswith(("~", "/")) or token.split("/", 1)[0] in r.ROOTS
        if not (rooted or verb):
            continue
        if "/" in token and not rooted:
            continue
        arg = token + ((":" + line) if line else "")
        if _resolve(r, token)[0] and ("READ", arg) not in out:
            out.append(("READ", arg))
    for m in _FIND.finditer(text):
        q = m.group(1).strip()
        if q and ("FIND", q) not in out:
            out.append(("FIND", q))
    return out[:PER_TURN]


def hers(text, surface="chat", act=True, mem=None, now=None):
    """Read what her message points him to, now. Kept for later turns unless act is False; returns the new rows."""
    now = time.time() if now is None else now
    try:
        asks = asks_in(text)
    except Exception as e:
        print("[file-reach/hers]", e, flush=True)
        return []
    rows = [_do(k, a, "her", surface, now) for k, a in asks]
    if rows and act:
        _keep(rows, mem, now)
    return rows


def take(reply, surface="chat", act=True, mem=None, now=None):
    """His [READ: ...] / [FIND: ...] taken out of a reply; done and kept (unless act is False) for his next turn."""
    if not reply or not _TAG.search(reply):
        return reply
    if act:
        now = time.time() if now is None else now
        try:
            rows = [_do(k, a.strip(), "him", surface, now) for k, a in _TAG.findall(reply)[:PER_TURN]]
            _keep(rows, mem, now)
        except Exception as e:
            print("[file-reach/take]", e, flush=True)
    return re.sub(r"[ \t]*" + _TAG.pattern + r"[ \t]*", " ", reply, flags=re.I).strip()


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
        return not p or hashlib.sha256(open(p, "rb").read()).hexdigest()[:16] != row.get("sha")
    except Exception:
        return False


def _who(row):
    return "Gloria pointed you to" if row.get("by") == "her" else "You asked for"


def _by(row):
    return "Gloria pointed you to it" if row.get("by") == "her" else "you read it"


def render(rows, now=None):
    """The block for these rows, newest first: the newest open in full, the rest as short notes."""
    now = time.time() if now is None else now
    if not rows:
        return ""
    head = ("[FILES YOU HAVE READ - from your own files and the shared folder, read only. What each said is quoted "
            "from the file, not remembered. To read a file: [READ: shared/NAME.md] (or scripts/x.py, house/x.py, "
            "docs/NAME.md; add :LINE to go on from a line). To look for one: [FIND: words]. Write the tag on its own "
            "in a reply; what it finds is in front of you on your next turn. Gloria's files for you are in shared/.]")
    parts = [head]
    newest = sorted(rows, key=lambda x: float(x.get("at") or 0), reverse=True)
    opened = [x for x in newest if now - float(x.get("at") or 0) <= OPEN_S][:PER_TURN]
    for i, x in enumerate(opened):
        what = x.get("label") or x.get("asked")
        stale = " (it has changed since; read it again for the current text)" if _changed(x) else ""
        kind = "the file" if x.get("kind") == "read" else "a search of your files for"
        cap = OPEN_CHARS if i == 0 else SECOND_CHARS
        text = str(x.get("text") or "")
        parts.append("%s %s %s, %s%s:\n%s" % (_who(x), kind, what, _when(x.get("at")), stale,
                                              text[:cap] + ("\n... (more: read it again)" if len(text) > cap else "")))
    notes = [x for x in newest if x not in opened][:NOTES_SHOWN]
    if notes:
        lines = ["Earlier reads (notes; read again for the whole text):"]
        for x in notes:
            stale = " - changed since" if _changed(x) else ""
            if x.get("kind") == "read" and x.get("label"):
                body = re.sub(r"^\s*\d+  ", "", str(x.get("text") or ""), flags=re.M)
                lines.append("- %s, %s (%d lines)%s, %s; it begins: %s" % (
                    x["label"], _when(x.get("at")), x.get("lines") or 0, stale, _by(x),
                    json.dumps(body[:NOTE_CHARS], ensure_ascii=False)))
            else:
                lines.append("- search for %s, %s: %s" % (json.dumps(str(x.get("asked"))), _when(x.get("at")),
                                                          json.dumps(str(x.get("text") or "")[:NOTE_CHARS // 2],
                                                                     ensure_ascii=False)))
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def block(now=None, mem=None, extra=None):
    """His file reads for his context: the kept rows, plus `extra` (this turn's, when they were not kept: a test turn).
    The head alone, saying how to read, when he has read nothing yet. Read only."""
    now = time.time() if now is None else now
    rows = [x for x in _load(mem) if now - float(x.get("at") or 0) <= KEEP_DAYS * 86400] + list(extra or [])
    if not rows:
        return ("[YOUR FILES - you can read your own files and the ones Gloria leaves for you in shared/, read only: "
                "[READ: shared/NAME.md] (or scripts/x.py, house/x.py, docs/NAME.md), or look for one with "
                "[FIND: words]. Write the tag on its own in a reply; what it finds is in front of you on your next turn.]")
    return render(rows, now)


def turn_block(her_text, surface="chat", act=True, mem=None, now=None):
    """One call for a chat route: read what her message points to (kept unless act is False), then the block."""
    now = time.time() if now is None else now
    fresh = hers(her_text, surface, act=act, mem=mem, now=now)
    return block(now=now, mem=mem, extra=None if act else fresh)


def main(argv):
    if len(argv) > 2 and argv[1] in ("read", "find"):
        print(read(" ".join(argv[2:]))[1] if argv[1] == "read" else find(" ".join(argv[2:])))
    else:
        print(block())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
