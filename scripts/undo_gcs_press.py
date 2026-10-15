#!/usr/bin/env python3
"""Take back a GCS press she did not mean (Gloria, 2026-10-15: she pressed it by accident, fishing).

A press is recorded as a turn of hers (input_kind "gcs") and his reply to it, in three places:
    memory/avatar-chat-history.json     the avatar chat he reads back
    memory/chat-canonical.jsonl         the whole record the chat history is cut from
    memory/interaction-ledger.json      the conversation ledger
It also leaves gcs-state.json (the press, live) and an entry in gcs-saved-patterns.json.

    python3 scripts/undo_gcs_press.py                 list the presses of the last 24 hours, numbered; changes nothing
    python3 scripts/undo_gcs_press.py --hours 6       a different window
    python3 scripts/undo_gcs_press.py --apply 1       remove press 1 (and his reply) everywhere it was recorded
    python3 scripts/undo_gcs_press.py --apply all     remove every press listed

Every file it changes is copied first, beside itself, as <name>.before-undo-<time>. It cannot take back what the press
already did to his feeling state; that fades on its own.
"""
import datetime, json, os, shutil, sys, time

MEM = os.path.join(os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace"), "memory")
HISTORY = os.path.join(MEM, "avatar-chat-history.json")
CANON = os.path.join(MEM, "chat-canonical.jsonl")
LEDGER = os.path.join(MEM, "interaction-ledger.json")
GCS_STATE = os.path.join(MEM, "gcs-state.json")
SAVED = os.path.join(MEM, "gcs-saved-patterns.json")
LEDGER_WINDOW = 300      # seconds after her press within which the ledger entry for that exchange is written


def _when(value):
    try:
        t = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return t.timestamp() if t.tzinfo else time.mktime(t.timetuple())
    except Exception:
        return None


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _rows(data, key="entries"):
    return data if isinstance(data, list) else (data.get(key) or data.get("history") or []) if isinstance(data, dict) else []


def _is_press(entry):
    return isinstance(entry, dict) and entry.get("role") == "user" and entry.get("input_kind") == "gcs"


def presses(hours=24, now=None):
    """The presses in the window, oldest first: her turn, his reply, and the ledger entries for that exchange."""
    now = now or time.time()
    history = _rows(_load(HISTORY, []))
    ledger = _rows(_load(LEDGER, []))
    out = []
    for i, entry in enumerate(history):
        if not _is_press(entry):
            continue
        at = _when(entry.get("timestamp"))
        if at is None or now - at > hours * 3600:
            continue
        reply = history[i + 1] if i + 1 < len(history) and history[i + 1].get("role") == "assistant" else None
        said = str(entry.get("original_text") or entry.get("content") or "")
        matches = []
        for j, row in enumerate(ledger):
            t = _when(row.get("timestamp")) if isinstance(row, dict) else None
            if t is None or not (at - 5 <= t <= at + LEDGER_WINDOW):
                continue
            g = str(row.get("gloria") or "").lower()
            if "pressed" in g or (said and said.strip("[] ").lower()[:40] in g) or g.startswith("[she spoke with her body"):
                matches.append(j)
        out.append({"at": at, "timestamp": entry.get("timestamp"), "her": said[:120],
                    "his": str((reply or {}).get("content") or "")[:160],
                    "history_turn": entry, "history_reply": reply, "ledger_rows": matches[:1]})
    return out


def _backup(path, stamp):
    if os.path.exists(path):
        shutil.copy2(path, "%s.before-undo-%s" % (path, stamp))


def _write_json(path, data):
    tmp = path + ".tmp-undo"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2 if path == LEDGER else None, ensure_ascii=False)
    os.replace(tmp, path)


def remove(chosen):
    """Remove the chosen presses from every place they were recorded. Returns what was removed, per file."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    done = {"avatar chat": 0, "canonical record": 0, "ledger": 0, "saved patterns": 0, "live press": 0}
    turns = [p["history_turn"] for p in chosen] + [p["history_reply"] for p in chosen if p["history_reply"]]
    stamps = {(t.get("role"), t.get("timestamp"), t.get("content")) for t in turns}

    data = _load(HISTORY, None)
    if data is not None:
        rows = _rows(data)
        kept = [r for r in rows if (r.get("role"), r.get("timestamp"), r.get("content")) not in stamps]
        if len(kept) != len(rows):
            _backup(HISTORY, stamp)
            if isinstance(data, list): data = kept
            else: data["history" if "history" in data else "entries"] = kept
            _write_json(HISTORY, data)
            done["avatar chat"] = len(rows) - len(kept)

    if os.path.exists(CANON):
        with open(CANON) as f:
            lines = f.readlines()
        kept = []
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:
                kept.append(line); continue
            if (r.get("role"), r.get("timestamp"), r.get("content")) in stamps:
                continue
            kept.append(line)
        if len(kept) != len(lines):
            _backup(CANON, stamp)
            tmp = CANON + ".tmp-undo"
            with open(tmp, "w") as f:
                f.writelines(kept)
            os.replace(tmp, CANON)
            done["canonical record"] = len(lines) - len(kept)

    data = _load(LEDGER, None)
    if data is not None:
        rows = _rows(data)
        drop = {j for p in chosen for j in p["ledger_rows"]}
        if drop:
            _backup(LEDGER, stamp)
            kept = [r for j, r in enumerate(rows) if j not in drop]
            if isinstance(data, list): data = kept
            else: data["entries"] = kept
            _write_json(LEDGER, data)
            done["ledger"] = len(drop)

    lib = _load(SAVED, None)
    if isinstance(lib, list):
        kept = [x for x in lib if not any(abs(float(x.get("at") or 0) - p["at"]) < 120 for p in chosen)]
        if len(kept) != len(lib):
            _backup(SAVED, stamp)
            _write_json(SAVED, kept)
            done["saved patterns"] = len(lib) - len(kept)

    if os.path.exists(GCS_STATE):
        _backup(GCS_STATE, stamp)
        os.remove(GCS_STATE)
        done["live press"] = 1
    return done, stamp


def main(argv):
    hours = float(argv[argv.index("--hours") + 1]) if "--hours" in argv else 24
    found = presses(hours)
    if not found:
        print("no GCS press in the last %g hours" % hours); return 0
    for n, p in enumerate(found, 1):
        print("%d. %s\n   hers: %s\n   his:  %s\n   ledger entries matched: %d"
              % (n, p["timestamp"], p["her"], p["his"] or "(no reply recorded)", len(p["ledger_rows"])))
    if "--apply" not in argv:
        print("\nNothing changed. To remove: --apply 1   (or --apply 1,2  or  --apply all)")
        return 0
    which = argv[argv.index("--apply") + 1] if argv.index("--apply") + 1 < len(argv) else ""
    if which == "all":
        chosen = found
    else:
        try:
            chosen = [found[int(x) - 1] for x in which.split(",") if x.strip()]
        except (ValueError, IndexError):
            print("--apply takes the numbers above, or all"); return 1
    done, stamp = remove(chosen)
    print("\nremoved:", ", ".join("%s %d" % (k, v) for k, v in done.items()))
    print("backups beside each file, ending .before-undo-%s" % stamp)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
