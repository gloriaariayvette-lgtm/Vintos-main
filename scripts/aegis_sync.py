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
    if "--resumed" in argv:      # the new copy after a sync: the sync is already done, go straight to the deploy
        return deploy() if "--deploy" in argv else 0
    me = os.path.abspath(__file__)
    before = open(me, "rb").read()
    r = sync(source=source)
    print(say(r))
    if not r["ok"]:
        return 1
    # The sync can bring a new version of this very script. Carrying on in the old one is how a fixed deploy view
    # went unseen on 14 October: run the new copy for the rest of the work instead.
    if "--deploy" in argv and "--resumed" not in argv and open(me, "rb").read() != before:
        os.execv(sys.executable, [sys.executable, me, "--resumed"] + list(argv))
    if "--deploy" in argv:
        return deploy()
    return 0


def deploy(log=None, script=None, follow=True, out=sys.stdout):
    """Run the deploy and SHOW it (Gloria, 2026-10-14: "Idk why you thought it's okay to take the visibility of
    the deploys away from me"). It used to start the deploy and print only "deploy started", so seven deploys in
    a row ended in "STOP: a suite failed — nothing installed" and nobody saw it.

    The deploy itself still runs in its own session, so a terminal that closes does not kill it, and ~/deploy.log
    still holds all of it. But this now prints the deploy as it happens, every line, and ends on its verdict: the
    exit code, and the deploy's own last line. Ctrl-C stops the watching, never the deploy."""
    import time
    log = log or os.path.expanduser("~/deploy.log")
    script = script or os.path.join(CHECKOUT, "scripts", "deploy-atelier.sh")
    env = dict(os.environ, VINTOS_DEPLOY_ALLOW_DIRTY="0")
    with open(log, "w") as f:
        proc = subprocess.Popen(["bash", script], cwd=os.path.dirname(os.path.dirname(script)), env=env,
                                stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    print("deploy running (also written to %s):" % log, file=out, flush=True)
    if not follow:
        return 0
    pos, last = 0, ""
    try:
        while True:
            done = proc.poll() is not None
            with open(log, errors="replace") as f:
                f.seek(pos); chunk = f.read(); pos = f.tell()
            if chunk:
                out.write(chunk); out.flush()
                lines = [l for l in chunk.splitlines() if l.strip()]
                if lines: last = lines[-1]
            if done:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n(stopped watching; the deploy is still running. Its result: tail -1 %s)" % log, file=out)
        return 0
    failed = [l for l in open(log, errors="replace").read().splitlines() if " FAIL" in l or l.startswith("FAIL")]
    print("\n" + "=" * 60, file=out)
    head = verdict(proc.returncode, last, open(log, errors="replace").read())
    print(head, file=out)
    if not head.startswith("DEPLOY OK"):
        for l in failed[:12]:
            print("  " + l.strip(), file=out)
    print("=" * 60, file=out, flush=True)
    return 0 if proc.returncode == 0 and "deploy OK" in last else 1


def verdict(returncode, last, log_text):
    """The one line said at the end. A deploy that installed and then named what is left is not "nothing installed"
    (16 October: that was printed under "files are installed, but: forge not updated (sudo wants a password)")."""
    if returncode == 0 and "deploy OK" in last:
        return "DEPLOY OK — installed. (%s)" % last.strip()
    if "files are installed, but" in log_text:
        return "DEPLOY INCOMPLETE — files are installed; still to do: %s" % last.strip().lstrip("- ")
    return "DEPLOY FAILED — nothing installed. exit %s; last line: %s" % (returncode, last.strip())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
