#!/usr/bin/env python3
"""Edits made on Aegis never block a pull again (2026-10-14). On 14 October 72 uncommitted lines in
docs/open-work.md stopped `git pull --ff-only`, and Gloria had to stash and merge by hand. aegis_sync commits them,
merges, and pushes. Isolation: the origin is a bare repository in a scratch directory; HOME is scratch; git never
leaves the temporary tree."""
import importlib.util, os, subprocess, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TMP = tempfile.mkdtemp(prefix="vintos-aegis-sync-")
os.environ["HOME"] = TMP
os.environ["GIT_CONFIG_GLOBAL"] = os.path.join(TMP, "gitconfig"); os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
spec = importlib.util.spec_from_file_location("aegis_sync", os.path.join(REPO, "scripts", "aegis_sync.py"))
A = importlib.util.module_from_spec(spec); spec.loader.exec_module(A)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
def git(cwd, *a):
    return subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@t"] + list(a),
                          capture_output=True, text=True, check=True).stdout
DEPLOY, WORK = "deploy", "claude/work"
ORIGIN = os.path.join(TMP, "origin.git"); subprocess.run(["git", "init", "-q", "--bare", ORIGIN], check=True)
SEED = os.path.join(TMP, "seed"); subprocess.run(["git", "clone", "-q", ORIGIN, SEED], check=True)
git(SEED, "checkout", "-q", "-b", DEPLOY)
os.makedirs(os.path.join(SEED, "docs"))
open(os.path.join(SEED, "docs", "open-work.md"), "w").write("# open work\n\n## old entry\n")
open(os.path.join(SEED, "a.py"), "w").write("x = 1\n")
git(SEED, "add", "-A"); git(SEED, "commit", "-q", "-m", "seed"); git(SEED, "push", "-q", "origin", DEPLOY)
AEGIS = os.path.join(TMP, "Vintos-main"); subprocess.run(["git", "clone", "-q", "-b", DEPLOY, ORIGIN, AEGIS], check=True)
KEEP = os.path.join(TMP, "keep")

check("the origin, the checkout and HOME are all scratch", all(p.startswith(TMP) for p in (ORIGIN, AEGIS, KEEP, os.environ["HOME"])))

# upstream work on another branch, and an uncommitted edit on Aegis
git(SEED, "checkout", "-q", "-b", WORK)
open(os.path.join(SEED, "b.py"), "w").write("y = 2\n"); git(SEED, "add", "-A"); git(SEED, "commit", "-q", "-m", "new module")
git(SEED, "push", "-q", "origin", WORK)
with open(os.path.join(AEGIS, "docs", "open-work.md"), "a") as f: f.write("\n## his entry, written on Aegis\n")
r = A.sync(checkout=AEGIS, branch=DEPLOY, source=WORK, keep=KEEP)
check("a dirty checkout syncs instead of refusing", r["ok"], r)
check("the Aegis edit is kept, committed, and its diff saved", r["kept"] == ["docs/open-work.md"]
      and "his entry" in open(os.path.join(AEGIS, "docs", "open-work.md")).read() and os.listdir(KEEP), r)
check("the incoming branch is merged in", os.path.exists(os.path.join(AEGIS, "b.py")) and r["merged"] == [DEPLOY, WORK], r)
check("the result is pushed to the deploy branch", r["pushed"] and git(AEGIS, "rev-parse", "HEAD") == git(AEGIS, "rev-parse", "origin/" + DEPLOY), r)
check("the checkout is clean afterwards (the deploy's dirty guard passes)", git(AEGIS, "status", "--porcelain", "--untracked-files=no") == "")

# a real conflict: aborted, nothing lost
git(SEED, "checkout", "-q", DEPLOY); git(SEED, "pull", "-q", "origin", DEPLOY)
open(os.path.join(SEED, "a.py"), "w").write("x = 'upstream'\n"); git(SEED, "commit", "-qam", "up"); git(SEED, "push", "-q", "origin", DEPLOY)
open(os.path.join(AEGIS, "a.py"), "w").write("x = 'aegis'\n")
before = git(AEGIS, "rev-parse", "HEAD")
r = A.sync(checkout=AEGIS, branch=DEPLOY, keep=KEEP)
check("a conflicting merge is refused and named", not r["ok"] and "a.py" in r["why"], r)
check("the Aegis edit survives the conflict as a commit, and no merge is left half-done",
      open(os.path.join(AEGIS, "a.py")).read() == "x = 'aegis'\n" and git(AEGIS, "rev-parse", "HEAD") != before
      and not os.path.exists(os.path.join(AEGIS, ".git", "MERGE_HEAD")), r)
check("nothing was pushed on a conflict", git(SEED, "ls-remote", "origin", DEPLOY).split()[0] == git(SEED, "rev-parse", "HEAD").strip())

# the wrong branch: untouched
git(AEGIS, "checkout", "-q", "-b", "elsewhere")
r = A.sync(checkout=AEGIS, branch=DEPLOY, keep=KEEP)
check("a checkout on another branch is left alone", not r["ok"] and "not the deploy branch" in r["why"], r)

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
