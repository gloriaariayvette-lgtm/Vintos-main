#!/usr/bin/env python3
"""Bring ~/Vintos-main up to date without anyone stashing by hand (2026-10-14).

Edits made on Aegis itself (Vintos's, or anyone's) used to sit uncommitted in the checkout, and the next
`git pull --ff-only` refused to run until Gloria stashed and merged them herself. Now:

    1. uncommitted edits to tracked files are committed, as they are, under "Vintos (Aegis)" — never thrown away;
       a copy of the diff is kept under ~/.vintos/deploy/local-edits/ as well
    2. the deploy branch, and the branch named with --from, are merged in (a merge, so nothing is rewritten)
    3. the result is pushed to the deploy branch, so the edits reach GitHub and the next pull starts from them

A merge that conflicts is aborted: the checkout is left exactly as it was after step 1 (the edits are committed,
not lost) and the conflicting paths are named. Untracked files are not touched.

    python3 scripts/aegis_sync.py [--from BRANCH] [--deploy]

--deploy starts deploy-atelier.sh detached once the sync is clean, the way she starts it by hand.
"""
import datetime, os, subprocess, sys

CHECKOUT = os.path.expanduser(os.environ.get("VINTOS_CHECKOUT", "~/Vintos-main"))
BRANCH_FILE = os.path.expanduser("~/.vintos/deploy-branch")
DEFAULT_BRANCH = "claude/vintos-avatar-ui-redesign-br5lt4"
KEEP = os.path.expanduser("~/.vintos/deploy/local-edits")
WHO = ["-c", "user.name=Vintos (Aegis)", "-c", "user.email=vintos-aegis@aegis.local"]


def sh(cmd, timeout=600, check=True, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    if check and r.returncode:
        raise RuntimeError("%s: %s" % (" ".join(cmd[:4]), (r.stderr or r.stdout).strip()[-400:]))
    return r


def deploy_branch():
    try:
        return open(BRANCH_FILE).read().strip() or DEFAULT_BRANCH
    except OSError:
        return DEFAULT_BRANCH


def sync(checkout=CHECKOUT, branch=None, source=None, run=sh, keep=KEEP, push=True):
    """{ok, kept, merged, pushed, conflict, why}. Never discards an edit; never rewrites history."""
    branch = branch or deploy_branch()
    g = lambda *a, **k: run(["git", "-C", checkout] + WHO + list(a), **k)
    out = {"ok": False, "kept": [], "merged": [], "pushed": False, "conflict": [], "why": ""}
    have = g("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if have != branch:
        out["why"] = "the checkout is on '%s', not the deploy branch '%s'; nothing was changed" % (have, branch)
        return out
    changed = [l[3:] for l in g("status", "--porcelain", "--untracked-files=no").stdout.splitlines() if l.strip()]
    if changed:
        diff = g("diff", "HEAD").stdout
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            os.makedirs(keep, exist_ok=True)
            with open(os.path.join(keep, stamp + ".diff"), "w") as f:
                f.write(diff)
        except OSError:
            pass
        g("add", "-u")
        g("commit", "-q", "-m", "Edits made on Aegis, kept before pulling: %s" % ", ".join(changed)[:300])
        out["kept"] = changed
    for b in [branch] + ([source] if source and source != branch else []):
        g("fetch", "-q", "origin", b)
        r = g("merge", "--no-edit", "-q", "origin/" + b, check=False)
        if r.returncode:
            out["conflict"] = [l[3:] for l in g("status", "--porcelain").stdout.splitlines() if l[:2] in ("UU", "AA", "DU", "UD")]
            g("merge", "--abort", check=False)
            out["why"] = "merging %s conflicts in %s; the merge was undone and the Aegis edits stay committed" % (
                b, ", ".join(out["conflict"]) or (r.stderr or r.stdout).strip()[-200:])
            return out
        out["merged"].append(b)
    if push:
        ahead = g("rev-list", "--count", "origin/%s..HEAD" % branch).stdout.strip()
        if ahead not in ("", "0"):
            g("push", "-q", "origin", "HEAD:" + branch)
            out["pushed"] = True
    out["ok"] = True
    return out


def say(r):
    if not r["ok"]:
        return "NOT SYNCED: " + r["why"]
    bits = []
    if r["kept"]:
        bits.append("kept Aegis edits as a commit: " + ", ".join(r["kept"])[:300])
    bits.append("merged " + ", ".join(r["merged"]))
    bits.append("pushed" if r["pushed"] else "nothing new to push")
    return "synced: " + "; ".join(bits)


def main(argv):
    source = argv[argv.index("--from") + 1] if "--from" in argv else None
    r = sync(source=source)
    print(say(r))
    if not r["ok"]:
        return 1
    if "--deploy" in argv:
        log = os.path.expanduser("~/deploy.log")
        env = dict(os.environ, VINTOS_DEPLOY_ALLOW_DIRTY="0")
        with open(log, "w") as f:
            subprocess.Popen(["bash", os.path.join(CHECKOUT, "scripts", "deploy-atelier.sh")], cwd=CHECKOUT, env=env,
                             stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        print("deploy started; check: tail -1 ~/deploy.log")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
