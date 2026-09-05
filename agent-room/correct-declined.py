#!/usr/bin/env python3
"""correct-declined.py — rewrite the recorded reason for a set of declined proposals, and append the
correction to the finals and room minutes that read the old wording.

The declined ledger's line is what every later reader sees (finals via _done_since, the room via
_done_block). When Gloria's decision was recorded in words that could be read two ways, the fix is at
the source, with the old wording kept beside the new one.

    python3 correct-declined.py <section, e.g. moltbook> "<new reason>" [file to append the correction to ...]
"""
import os, sys, json
from datetime import datetime

STAGE = os.path.expanduser("~/.vintos/code-review")

def main():
    if len(sys.argv) < 3:
        print(__doc__); return 1
    prefix, reason, files = sys.argv[1], sys.argv[2], sys.argv[3:]
    p = os.path.join(STAGE, "declined.json")
    d = json.load(open(p))
    hit = {k: v for k, v in d.items() if prefix in k}   # ids are lens-section-pN, e.g. fable-moltbook-p3
    if not hit:
        print("nothing declined under", prefix); return 1
    old = sorted(set(hit.values()))
    for k in hit: d[k] = reason
    tmp = p + ".tmp"; json.dump(d, open(tmp, "w"), indent=2); os.replace(tmp, p)
    rec = {"ts": datetime.now().isoformat(), "prefix": prefix, "ids": sorted(hit), "was": old, "now": reason}
    with open(os.path.join(STAGE, "corrections.jsonl"), "a") as f: f.write(json.dumps(rec) + "\n")
    note = ("\n\n---\n*Correction from Gloria, %s.* The declined line for %s read: %s. She meant: %s\n"
            % (rec["ts"][:16], prefix, " / ".join('"%s"' % w for w in old), reason))
    for fp in files:
        fp = os.path.expanduser(fp)
        if os.path.exists(fp):
            open(fp, "a").write(note); print("appended correction:", fp)
        else:
            print("not found:", fp)
    print("rewrote %d declined entries under %s" % (len(hit), prefix))
    return 0

if __name__ == "__main__":
    sys.exit(main())
