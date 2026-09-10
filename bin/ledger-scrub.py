#!/usr/bin/env python3
"""ledger-scrub.py - the conversation ledger holds conversations, nothing else.

    python3 ledger-scrub.py                     dry run: what would be removed, and the last six entries
    python3 ledger-scrub.py --apply             remove the rows, with a backup beside the ledger first
    python3 ledger-scrub.py --backfill-reelroom append any ReelRoom session that was saved under
                                                memory/reelroom/ but never reached the ledger
    python3 ledger-scrub.py --tail 10           show the last N entries (timestamp, source, channel, a line)

Removed: rows whose source is "video-outreach" (a clip he sent; the 09-05 append that put those in
the ledger is gone from vintos-send-video.py as of 2026-09-10). Nothing else is touched. The backup
is interaction-ledger.pre-scrub-<stamp>.json; the write is atomic."""
import os, sys, json, time

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
LEDGER = os.path.join(MEMORY, "interaction-ledger.json")
REMOVE_SOURCES = ("video-outreach",)

def load():
    with open(LEDGER) as f:
        d = json.load(f)
    if isinstance(d, dict):
        return d, d.setdefault("entries", [])
    return d, d

def save(d):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = LEDGER.replace(".json", ".pre-scrub-%s.json" % stamp)
    with open(LEDGER) as src, open(bak, "w") as dst:
        dst.write(src.read())
    tmp = LEDGER + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, LEDGER)
    return bak

def line(e):
    if not isinstance(e, dict):
        return str(e)[:80]
    src = e.get("source") or e.get("surface") or e.get("channel") or "?"
    txt = (e.get("narrative") or e.get("summary") or e.get("gloria") or e.get("vintos") or "")
    return "%s  %-18s %-10s %s" % (str(e.get("timestamp", ""))[:19], src, e.get("channel") or "", str(txt).replace("\n", " ")[:70])

def tail(entries, n):
    for e in entries[-n:]:
        print("  " + line(e))

def backfill_reelroom(entries):
    """A session saved under memory/reelroom/ (listed in reelroom-sessions.json) whose file is not
    in the ledger gets one entry: film, narrative from the saved file, and a note that the verbatim
    transcript was not recovered (the app posts it only at summary time)."""
    try:
        rows = json.load(open(os.path.join(MEMORY, "reelroom-sessions.json")))
    except Exception:
        return []
    have = {e.get("reelroom_file") for e in entries if isinstance(e, dict)}
    added = []
    for r in rows:
        f = r.get("file")
        if not f or f in have:
            continue
        try:
            text = open(os.path.join(MEMORY, "reelroom", f)).read()
        except Exception:
            text = ""
        entries.append({"timestamp": str(r.get("at") or r.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%S"))[:19],
                        "channel": "reelroom", "source": "reelroom-session", "reelroom_file": f,
                        "film": str(r.get("film") or r.get("film_title") or "unknown film"),
                        "duration_seconds": int(r.get("elapsed_seconds") or r.get("duration_seconds") or 0),
                        "turns": int(r.get("exchanges") or 0), "transcript": [],
                        "narrative": text[:1200], "summary": text[:1200],
                        "note": "backfilled by ledger-scrub: the session reached memory/reelroom/ but not the ledger; transcript not recovered"})
        added.append(f)
    entries.sort(key=lambda e: str(e.get("timestamp", "")) if isinstance(e, dict) else "")
    return added

def main(argv):
    if not os.path.exists(LEDGER):
        print("no ledger at", LEDGER); return 1
    d, entries = load()
    n = int(argv[argv.index("--tail") + 1]) if "--tail" in argv and argv.index("--tail") + 1 < len(argv) else 6
    bad = [e for e in entries if isinstance(e, dict) and e.get("source") in REMOVE_SOURCES]
    print("ledger: %d entries; %d to remove (%s)" % (len(entries), len(bad), ", ".join(REMOVE_SOURCES)))
    for e in bad:
        print("  - " + line(e))
    changed = False
    if "--apply" in argv and bad:
        keep = [e for e in entries if not (isinstance(e, dict) and e.get("source") in REMOVE_SOURCES)]
        if isinstance(d, dict): d["entries"] = keep
        else: d = keep
        entries = keep; changed = True
    if "--backfill-reelroom" in argv:
        # a night still sitting in the scratch journal (the app never asked for the summary) becomes one session
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(MEMORY), "scripts"))
            import reelroom as _rr
            c = _rr.commit_journal("ledger-scrub backfill")
            if c.get("committed"):
                print("committed the live journal as %s (%d turns)" % (c["file"], c["turns"]))
                d, entries = load()
        except Exception as e:
            print("live journal: not committed (%s)" % str(e)[:120])
        added = backfill_reelroom(entries)
        print("backfilled ReelRoom sessions: %s" % (", ".join(added) if added else "none missing"))
        changed = changed or bool(added)
    if changed:
        bak = save(d)
        print("written; backup at", os.path.basename(bak))
    elif "--apply" in argv:
        print("nothing to remove; ledger unchanged")
    else:
        print("dry run; nothing written (add --apply)")
    print("last %d entries now:" % n)
    tail(entries, n)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
