#!/usr/bin/env python3
"""Which of his scripts the deploy never installs, and how the copy on the host compares (2026-09-30).

deploy-atelier.sh installs only what its SCRIPTS/BINS manifest names. A fix to a script outside it never
reaches Aegis: the 2026-09-24 change keeping poems out of his journal sat undeployed for a week that way.
Read-only: this changes nothing. Run it on Aegis from the checkout:

    python3 scripts/manifest_gap.py            the summary and every script that differs or is missing
    python3 scripts/manifest_gap.py --all      every unlisted script, the same ones too

For a script that differs it says which side is newer: if the host's copy is an older committed version,
the checkout is ahead and installing it is safe; if the host's copy matches no commit, it was edited on
the host and installing would overwrite that edit.
"""
import filecmp
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLED = (os.path.expanduser("~/.vintos/workspace/scripts"), os.path.expanduser("~/Vintos"))


def manifest(path=os.path.join(REPO, "scripts", "deploy-atelier.sh")):
    s = open(path).read()
    names = set()
    for m in re.finditer(r'^(?:SCRIPTS|BINS)="((?:[^"\\]|\\.)*)"', s, re.M | re.S):
        names |= {w for w in m.group(1).split() if not w.startswith("$")}
    return names


def unlisted(names=None):
    names = manifest() if names is None else names
    out = []
    for d in ("bin", "scripts"):
        for f in sorted(os.listdir(os.path.join(REPO, d))):
            p = os.path.join(REPO, d, f)
            if not f.endswith((".py", ".sh")) or not os.path.isfile(p):
                continue
            real = os.path.basename(os.path.realpath(p))
            spell = {f, real, f.replace("_", "-"), f.replace("-", "_"), real.replace("_", "-"), real.replace("-", "_")}
            if not spell & names:
                out.append((d, f, p))
    return out


def compare(rows, roots=INSTALLED):
    """(state, repo path, installed path): same | differs | not installed."""
    seen, res = set(), []
    for d, f, p in rows:
        key = os.path.realpath(p) + "|" + f
        if key in seen: continue
        seen.add(key)
        live = next((os.path.join(r, f) for r in roots if os.path.isfile(os.path.join(r, f))), "")
        state = "not installed" if not live else "same" if filecmp.cmp(p, live, shallow=False) else "differs"
        res.append((state, "%s/%s" % (d, f), live))
    return res


def history(repo_path, live):
    """'checkout ahead (host has <commit> <date>)' when the host's copy is an older committed version of the
    file, 'edited on the host' when it matches none."""
    def git(*a):
        return subprocess.run(["git", "-C", REPO] + list(a), capture_output=True, text=True).stdout.strip()
    want = git("hash-object", live)
    real = os.path.relpath(os.path.realpath(os.path.join(REPO, repo_path)), REPO)
    for path in dict.fromkeys((repo_path, real)):
        for line in git("log", "--format=%h %ad", "--date=short", "--", path).splitlines()[:400]:
            h = line.split()[0]
            if git("rev-parse", "%s:%s" % (h, path)) == want:
                return "checkout ahead (host has %s)" % line
    return "EDITED ON THE HOST (matches no commit)"


if __name__ == "__main__":
    res = compare(unlisted())
    counts = {}
    for st, _r, _l in res:
        counts[st] = counts.get(st, 0) + 1
    print("scripts the deploy never installs: %d  (%s)" % (len(res), ", ".join("%s %d" % kv for kv in sorted(counts.items()))))
    for st, r, live in res:
        if "--all" in sys.argv or st != "same":
            print("  %-13s %-45s %s" % (st, r, history(r, live) if st == "differs" else live))
