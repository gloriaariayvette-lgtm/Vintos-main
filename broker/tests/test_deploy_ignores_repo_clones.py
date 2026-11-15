#!/usr/bin/env python3
"""A repo checkout is never his install (2026-11-14). Two deploys in one day stopped on "turn_coordinator.py exists in
more than one place": first an experiment's clone in ~/scratch-wants-20261114, then the dream experiment's clones in
~/dream-scratch/*, each with its own scripts/turn_coordinator.py. Runs the deploy's own functions in bash against a
scratch home built from synthetic files; nothing is installed and nothing outside the scratch home is read."""
import os, re, subprocess, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))

src = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
fn = lambda name: re.search(r"^%s\(\) \{.*?^\}" % name, src, re.M | re.S).group(0)
home_level = re.search(r"^HOME_LEVEL_FILES=.*$", src, re.M).group(0)
one_liners = [re.search(r"^abspath\(\) \{.*?; \}$", src, re.M | re.S).group(0), re.search(r"^die\(\) .*$", src, re.M).group(0)]
lib = "\n".join([home_level] + one_liners + [fn(n) for n in ("locate", "count", "live_tree", "repo_clone",
                                                               "find_anchor", "tree_score", "dest")])


def make_home(tag):
    return tempfile.mkdtemp(prefix="deploy-clones-%s-" % tag)

def put(home, rel, text="# x\n"):
    p = os.path.join(home, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w").write(text)

def live(home):
    put(home, ".vintos/workspace/AGENTS.md")                     # his workspace carries these, and is still his
    put(home, ".vintos/workspace/scripts/run_isolated_test.py")
    put(home, ".vintos/workspace/scripts/turn_coordinator.py")
    put(home, ".vintos/workspace/scripts/intent_engine.py")
    put(home, "Vintos/.git/HEAD", "ref: refs/heads/main\n")       # ~/Vintos is a git repo AND one of his trees
    put(home, "Vintos/value-map.py")

def checkout(home, root, git="file", tests=True, deployer=False, sub="scripts"):
    """A synthetic clone or worktree: the repo's shape, with its own copies of his files."""
    if git == "file":
        put(home, root + "/.git", "gitdir: /elsewhere/.git/worktrees/x\n")
    elif git == "dir":
        put(home, root + "/.git/HEAD", "ref: refs/heads/x\n")
    if tests:
        put(home, root + "/broker/tests/test_x.py")
    if deployer:
        put(home, root + "/scripts/deploy-atelier.sh", "#!/bin/sh\n")
    for f in ("turn_coordinator.py", "intent_engine.py", "only_in_clones.py", "value-map.py"):
        put(home, "%s/%s/%s" % (root, sub, f))

def dream_scratch(home):
    for n in ("ccw-c0", "ccw-c1", "ccw-prep", "ccw-w0", "dream-chk", "dream-mk"):
        checkout(home, "dream-scratch/" + n)
    checkout(home, "dream-scratch/ccw-sparse", tests=False)            # a sparse worktree: only its .git file marks it

def scratch_wants(home):
    checkout(home, "scratch-wants-20261114/wt", git="dir")              # a nested clone
    checkout(home, "scratch-wants-20261114/sparse", git="dir", tests=False)   # a clone with no suite checked out
    checkout(home, "scratch-wants-20261114/copy", git=None)             # a copied tree: no .git, its suite marks it
    checkout(home, "scratch-wants-20261114/bare", git=None, tests=False, deployer=True)   # only the deployer marks it

def bash(home, body, scripts=None):
    script = ('set -uo pipefail\nHOME="$1"; DEPTH=6; _SELF="$HOME/Vintos-main"\n'
              'SCRIPTS="turn_coordinator.py intent_engine.py only_in_clones.py value-map.py"; BINS=""\n'
              '%s\n%s' % (lib, body))
    env = dict(os.environ)
    env.pop("VINTOS_SCRIPTS", None)
    if scripts is not None:
        env["VINTOS_SCRIPTS"] = scripts
    return subprocess.run(["bash", "-c", script, "_", home], capture_output=True, text=True, timeout=60, env=env)

ANCHOR = 'ANCHOR_DIR="$(find_anchor)" || exit 1\nprintf "ANCHOR=%s\\n" "$ANCHOR_DIR"\n'

# --- the dream-scratch shape: the deploy finds his one live tree on its own
H = make_home("dream"); live(H); dream_scratch(H)
ws = os.path.join(H, ".vintos/workspace/scripts")
r = bash(H, ANCHOR)
check("dream-scratch clones do not make the anchor ambiguous", r.returncode == 0 and "ANCHOR=%s\n" % ws in r.stdout,
      (r.returncode, r.stdout, r.stderr))
r = bash(H, "locate turn_coordinator.py")
check("locate() leaves every dream-scratch clone out", r.stdout.split() == [os.path.join(ws, "turn_coordinator.py")],
      r.stdout)
r = bash(H, 'ANCHOR_DIR="%s"\ndest scripts/intent_engine.py' % ws)
check("a file in his workspace and in the clones installs into the workspace",
      r.returncode == 0 and r.stdout == os.path.join(ws, "intent_engine.py"), (r.returncode, r.stdout, r.stderr))
r = bash(H, 'ANCHOR_DIR="%s"\ndest scripts/only_in_clones.py' % ws)
check("a file only the clones have goes beside his scripts, never into a clone",
      r.returncode == 0 and r.stdout == os.path.join(ws, "only_in_clones.py"), (r.returncode, r.stdout, r.stderr))
r = bash(H, 'ANCHOR_DIR="%s"\ndest scripts/value-map.py' % ws)
check("~/Vintos is a git repo and still one of his trees",
      r.returncode == 0 and r.stdout == os.path.join(H, "Vintos/value-map.py"), (r.returncode, r.stdout, r.stderr))
r = bash(H, ANCHOR, scripts=ws)
check("with VINTOS_SCRIPTS naming his tree, the dream-scratch clones change nothing",
      r.returncode == 0 and "ANCHOR=%s\n" % ws in r.stdout, (r.returncode, r.stdout, r.stderr))
r = bash(H, ANCHOR, scripts=os.path.join(H, "dream-scratch/ccw-c0/scripts"))
check("VINTOS_SCRIPTS naming a clone's scripts/ is refused",
      r.returncode != 0 and "ANCHOR=" not in r.stdout and "repo checkout" in r.stderr, (r.returncode, r.stdout, r.stderr))

# --- the scratch-wants shape: a nested clone, a copied tree with its suite, a tree carrying only the deployer
H = make_home("wants"); live(H); scratch_wants(H)
ws = os.path.join(H, ".vintos/workspace/scripts")
r = bash(H, ANCHOR)
check("scratch-wants clones and copies do not make the anchor ambiguous",
      r.returncode == 0 and "ANCHOR=%s\n" % ws in r.stdout, (r.returncode, r.stdout, r.stderr))
r = bash(H, "locate only_in_clones.py")
check("no scratch-wants copy is ever a candidate (.git dir, broker/tests, the deployer)", r.stdout.strip() == "",
      r.stdout)
r = bash(H, ANCHOR, scripts=os.path.join(H, "scratch-wants-20261114/copy/scripts"))
check("VINTOS_SCRIPTS naming a copied tree with its suite is refused", r.returncode != 0 and "ANCHOR=" not in r.stdout,
      (r.returncode, r.stdout, r.stderr))

# --- a real second live install is still a question for her
H = make_home("second"); live(H); dream_scratch(H)
put(H, "old-install/scripts/turn_coordinator.py")              # no repo markers: it looks like a live install
ws = os.path.join(H, ".vintos/workspace/scripts")
r = bash(H, ANCHOR)
check("a second live-looking install is still refused, naming both and neither clone",
      r.returncode != 0 and "ANCHOR=" not in r.stdout and "more than one" in r.stderr
      and os.path.join(H, "old-install/scripts/turn_coordinator.py") in r.stderr and ws in r.stderr
      and "dream-scratch" not in r.stderr, (r.returncode, r.stdout, r.stderr))
r = bash(H, ANCHOR, scripts=ws)
check("VINTOS_SCRIPTS settles a real second install", r.returncode == 0 and "ANCHOR=%s\n" % ws in r.stdout,
      (r.returncode, r.stdout, r.stderr))
r = bash(H, ANCHOR, scripts=os.path.join(H, "no-such-dir"))
check("VINTOS_SCRIPTS that is not a directory is refused", r.returncode != 0 and "ANCHOR=" not in r.stdout,
      (r.returncode, r.stdout))

# --- a clone directly under $HOME's own name is judged below $HOME only: a .git in $HOME does not make him a clone
H = make_home("homegit"); put(H, ".git/HEAD", "ref: refs/heads/dotfiles\n")
put(H, "his-install/scripts/turn_coordinator.py")          # an install in no named tree, so only the markers judge it
mine = os.path.join(H, "his-install/scripts")
r = bash(H, ANCHOR)
check("a dotfiles .git in $HOME itself does not hide his install",
      r.returncode == 0 and "ANCHOR=%s\n" % mine in r.stdout, (r.returncode, r.stdout, r.stderr))
r = bash(H, ANCHOR, scripts=mine)
check("nor make VINTOS_SCRIPTS naming it a clone", r.returncode == 0 and "ANCHOR=%s\n" % mine in r.stdout,
      (r.returncode, r.stdout, r.stderr))

# --- the deploy uses find_anchor, and before any destination is chosen
m = re.search(r'^ANCHOR_DIR="\$\(find_anchor\)" \|\| exit 1$', src, re.M)
check("the deploy takes its anchor from find_anchor and stops when it refuses", bool(m))
check("the anchor is settled before the plan", bool(m) and m.start() < src.index('say "== plan =="'))

# --- aegis_sync hands VINTOS_SCRIPTS to the deploy it starts
sys.path.insert(0, os.path.join(REPO, "scripts"))
import io, aegis_sync
d = tempfile.mkdtemp(prefix="deploy-clones-sync-")
fake = os.path.join(d, "scripts", "deploy-atelier.sh"); os.makedirs(os.path.dirname(fake))
open(fake, "w").write('echo "saw=${VINTOS_SCRIPTS:-NONE}"\necho deploy OK\n')
os.environ["VINTOS_SCRIPTS"] = "/synthetic/his/scripts"
out = io.StringIO()
rc = aegis_sync.deploy(log=os.path.join(d, "log"), script=fake, out=out)
check("aegis_sync forwards VINTOS_SCRIPTS to deploy-atelier.sh", rc == 0 and "saw=/synthetic/his/scripts" in out.getvalue(),
      out.getvalue())
check("aegis_sync says which scripts dir it was given", "VINTOS_SCRIPTS=/synthetic/his/scripts" in out.getvalue(),
      out.getvalue())
del os.environ["VINTOS_SCRIPTS"]
out = io.StringIO()
aegis_sync.deploy(log=os.path.join(d, "log"), script=fake, out=out)
check("without it, nothing is invented", "saw=NONE" in out.getvalue(), out.getvalue())

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
