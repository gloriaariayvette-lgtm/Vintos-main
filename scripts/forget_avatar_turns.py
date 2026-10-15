#!/usr/bin/env python3
"""Forget the newest avatar chat turns, everywhere his memory kept them (Gloria, 2026-10-15: an accidental press
while fishing — "remove our latest avatar chat turns from the conversation ledger, the avatar chat and subcon").

The avatar chat is memory/avatar-overlay-chat.json. Each turn is also written into the conversation ledger, the
canonical chat record, and into whatever else his inner life keeps from a turn. Rather than a list of files that goes
stale, this searches his memory for each turn's own words and removes the entries that hold them.

    python3 scripts/forget_avatar_turns.py              show the newest 8 turns, numbered from the newest, and every
                                                        file that holds each one. Changes nothing.
    python3 scripts/forget_avatar_turns.py --last 2     remove the newest 2 turns from all of those files

Only JSON and JSON-lines files touched in the last 3 days are searched and edited; an entry is removed only when it
holds the turn's own words (at least 24 characters of them, tags stripped). Every file changed is copied first,
beside itself, as <name>.before-forget-<time>. A text or markdown file that holds the words is named, not edited.
"""
import datetime, glob, json, os, re, shutil, sys, time

MEM = os.path.join(os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace"), "memory")
AVATAR = os.path.join(MEM, "avatar-overlay-chat.json")
RECENT_DAYS = 3
MAX_BYTES = 60 * 1024 * 1024
MIN_WORDS = 24
WHOLE_ENTRY_MAX = 20000   # an entry bigger than this is searched inside, never dropped whole


def norm(text):
    """A turn's words as other stores keep them: private tags removed, whitespace collapsed, case folded."""
    t = re.sub(r"\[[^\]]*\]", " ", str(text or ""))
    return " ".join(t.split()).casefold()


_REUSED = re.compile(r"she pressed|^\[?gloria just|^\(pressed\)", re.I)


def fragments(turn):
    """The sentences of this turn long enough to identify it elsewhere. Other stores keep a piece of a reply, not
    its opening words, so each sentence is looked for on its own."""
    if turn.get("role") == "user" and _REUSED.search(str(turn.get("content") or "").strip()):
        return []   # a press cue is one of six reused lines: its words would find every real press too
    words = norm(turn.get("content"))
    parts = [p.strip(" ,;:-\u2014\u2013") for p in re.split(r"(?<=[.!?\u2026])\s+|\s*[\u2014\u2013]\s*", words)]
    out = [p[:120] for p in parts if len(p) >= MIN_WORDS]
    return out or ([words[:120]] if len(words) >= MIN_WORDS else [])


def fragment(turn):
    f = fragments(turn)
    return f[0] if f else ""


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


EXACT = []   # (ts, content) of the chosen turns: found by identity wherever a store kept the turn whole


def holds(value, frags):
    if isinstance(value, dict) and any(value.get("content") == c and (value.get("ts") == t or value.get("timestamp") == t)
                                       for t, c in EXACT):
        return True
    return any(f and f in norm(s) for s in _strings(value) for f in frags)


def _drop(value, frags):
    """value with every list element that holds one of the fragments removed, and how many were."""
    if isinstance(value, list):
        kept, n = [], 0
        for v in value:
            if isinstance(v, (dict, str)) and holds(v, frags):
                if len(json.dumps(v, ensure_ascii=False)) <= WHOLE_ENTRY_MAX:
                    n += 1; continue      # the entry for that turn: dropped whole
                # a large record that merely contains the turn (a day, a digest) loses only the part that holds it
            v2, m = _drop(v, frags); kept.append(v2); n += m
        return kept, n
    if isinstance(value, dict):
        out, n = {}, 0
        for k, v in value.items():
            out[k], m = _drop(v, frags); n += m
        return out, n
    return value, 0


def turns():
    try:
        data = json.load(open(AVATAR))
    except Exception:
        return []
    return data if isinstance(data, list) else (data.get("history") or data.get("messages") or [])


def candidates(now=None):
    now = now or time.time()
    out = []
    for path in glob.glob(os.path.join(MEM, "**", "*"), recursive=True):
        if not os.path.isfile(path) or ".before-forget-" in path or ".corrupt-" in path:
            continue
        try:
            st = os.stat(path)
        except OSError:
            continue
        if now - st.st_mtime > RECENT_DAYS * 86400 or st.st_size > MAX_BYTES:
            continue
        if path.endswith((".json", ".jsonl", ".md", ".txt", ".log")):
            out.append(path)
    return sorted(out)


def where(frags, files=None):
    """{path: count} of entries holding any of the fragments (for text files: matching lines)."""
    found = {}
    for path in files if files is not None else candidates():
        try:
            if path.endswith(".json"):
                data = json.load(open(path))
                _, n = _drop(data, frags)
            else:
                n = sum(1 for line in open(path, errors="replace") if _line_holds(line, frags, path))
        except Exception:
            continue
        if n:
            found[path] = n
    return found


def forget(chosen, files=None):
    """Remove the chosen turns from every structured file that holds them. Returns ({path: removed}, [unedited], stamp)."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    frags = [f for t in chosen for f in fragments(t)]
    EXACT[:] = [(t.get("ts") if t.get("ts") is not None else t.get("timestamp"), t.get("content")) for t in chosen]
    removed, unedited = {}, []
    # the avatar chat itself: the chosen turns by identity, short ones included
    data = json.load(open(AVATAR))
    rows = data if isinstance(data, list) else (data.get("history") or data.get("messages") or [])
    kept = rows[:-len(chosen)] if chosen and rows[-len(chosen):] == chosen else rows   # exactly the newest ones
    if len(kept) != len(rows):
        shutil.copy2(AVATAR, "%s.before-forget-%s" % (AVATAR, stamp))
        if isinstance(data, list): data = kept
        else: data["history" if "history" in data else "messages"] = kept
        _atomic(AVATAR, data)
        removed[AVATAR] = len(rows) - len(kept)
    if not frags and not EXACT:
        return removed, unedited, stamp
    for path in files if files is not None else candidates():
        if path == AVATAR:
            continue
        try:
            if path.endswith(".json"):
                data = json.load(open(path))
                new, n = _drop(data, frags)
                if n:
                    shutil.copy2(path, "%s.before-forget-%s" % (path, stamp))
                    _atomic(path, new)
                    removed[path] = n
            elif path.endswith(".jsonl"):
                lines = open(path, errors="replace").readlines()
                keep = [l for l in lines if not _line_holds(l, frags, path)]
                if len(keep) != len(lines):
                    shutil.copy2(path, "%s.before-forget-%s" % (path, stamp))
                    tmp = path + ".tmp-forget"
                    open(tmp, "w").writelines(keep); os.replace(tmp, path)
                    removed[path] = len(lines) - len(keep)
            elif any(_line_holds(l, frags, path) for l in open(path, errors="replace")):
                unedited.append(path)
        except Exception:
            continue
    return removed, unedited, stamp


def _line_holds(line, frags, path):
    if path.endswith(".jsonl"):
        try:
            return holds(json.loads(line), frags)
        except ValueError:
            pass
    return any(f and f in norm(line) for f in frags)


def _atomic(path, data):
    tmp = path + ".tmp-forget"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2 if path.endswith("interaction-ledger.json") else None)
    os.replace(tmp, path)


def _when(t):
    for k in ("ts", "timestamp", "at"):
        v = t.get(k)
        if isinstance(v, (int, float)):
            return datetime.datetime.fromtimestamp(v).strftime("%b %d %H:%M")
        if isinstance(v, str) and v:
            return v[:16].replace("T", " ")
    return "?"


def main(argv):
    rows = turns()
    if not rows:
        print("no avatar chat at %s" % AVATAR); return 1
    if "--last" not in argv:
        files = candidates()
        newest = list(reversed(rows[-8:]))
        for i, t in enumerate(newest, 1):
            f = fragments(t)
            elsewhere = where(f, files) if f else {}
            print("%d. %s  %-9s %s" % (i, _when(t), t.get("role"), norm(t.get("content"))[:90] or repr(t.get("content"))[:60]))
            for p, n in sorted(elsewhere.items()):
                print("      also in %s (%d)" % (os.path.relpath(p, MEM), n))
            if not f:
                print("      (too short to find elsewhere; removed from the avatar chat only)")
        print("\nNothing changed. To forget the newest N turns everywhere above:  --last N")
        return 0
    try:
        n = int(argv[argv.index("--last") + 1])
    except (ValueError, IndexError):
        print("--last takes a number"); return 1
    chosen = rows[-n:]
    removed, unedited, stamp = forget(chosen)
    for p, k in sorted(removed.items()):
        print("removed %d from %s" % (k, os.path.relpath(p, MEM)))
    for p in unedited:
        print("NOT edited (text file, holds the words): %s" % os.path.relpath(p, MEM))
    print("backups beside each file, ending .before-forget-%s" % stamp)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
