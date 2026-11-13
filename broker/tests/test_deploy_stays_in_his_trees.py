#!/usr/bin/env python3
"""The deploy installs only into his trees (2026-11-12). scripts/gloria_judge.py was new to the workspace, and the
only same-name file under $HOME was the gloria-axis shadow loop's own copy in ~/gloria-judge-20261112/bin, so dest()
took that lone hit: three deploys replaced the shadow loop's file (and put a paid_http.py twin beside it) while
intent_engine.py's import of gloria_judge failed in the workspace. Runs the deploy's own functions in bash against a
scratch home; nothing is installed."""
import os, re, subprocess, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="deploy-trees-")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

src = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
fn = lambda name: re.search(r"^%s\(\) \{.*?^\}" % name, src, re.M | re.S).group(0)
home_level = re.search(r"^HOME_LEVEL_FILES=.*$", src, re.M).group(0)
lib = "\n".join([home_level] + [fn(n) for n in ("locate", "count", "live_tree", "tree_score", "dest", "outside_plan")])

def put(rel, text="# x\n"):
    p = os.path.join(HOME, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w").write(text)

put(".vintos/workspace/scripts/turn_coordinator.py")
put(".vintos/workspace/scripts/intent_engine.py")
put("gloria-judge-20261112/bin/gloria_judge.py", "# the shadow loop's own copy\n")
put("gloria-judge-20261112/bin/paid_http.py")
put(".vintos/workspace/scripts/paid_http.py")
put("Vintos/value-map.py")
put("toy_keepalive.py")
put("experiments/toy_keepalive.py")
put("experiments/only_here.py")

def bash(body):
    script = ('HOME="$1"; DEPTH=6; _SELF="$HOME/Vintos-main"; ANCHOR_DIR="$HOME/.vintos/workspace/scripts"\n'
              'SCRIPTS="gloria_judge.py intent_engine.py paid_http.py value-map.py toy_keepalive.py"; BINS=""\n'
              '%s\n%s' % (lib, body))
    return subprocess.run(["bash", "-c", script, "_", HOME], capture_output=True, text=True, timeout=60)

ws = os.path.join(HOME, ".vintos/workspace/scripts")
r = bash("dest scripts/gloria_judge.py")
check("a new script goes beside his scripts, not over a same-name copy elsewhere",
      r.returncode == 0 and r.stdout == os.path.join(ws, "gloria_judge.py"), (r.returncode, r.stdout, r.stderr))
check("the copy outside his trees is named in a warning",
      "WARN" in r.stderr and os.path.join(HOME, "gloria-judge-20261112/bin/gloria_judge.py") in r.stderr, r.stderr)

r = bash("dest scripts/paid_http.py")
check("a script with a live copy and an outside copy is not ambiguous; the live one wins",
      r.returncode == 0 and r.stdout == os.path.join(ws, "paid_http.py"), (r.returncode, r.stdout, r.stderr))

r = bash("dest scripts/value-map.py")
check("a script that lives in ~/Vintos still installs there", r.stdout == os.path.join(HOME, "Vintos/value-map.py"),
      (r.stdout, r.stderr))

r = bash("dest scripts/toy_keepalive.py")
check("a file systemd runs from $HOME itself still installs there, not into an experiment's copy",
      r.returncode == 0 and r.stdout == os.path.join(HOME, "toy_keepalive.py"), (r.returncode, r.stdout, r.stderr))

r = bash("dest scripts/only_here.py")
check("a lone same-name hit outside his trees is never the destination",
      r.stdout == os.path.join(ws, "only_here.py"), (r.stdout, r.stderr))

plan = ("/src/scripts/intent_engine.py|%s/intent_engine.py\n"
        "/src/scripts/gloria_judge.py|%s/gloria-judge-20261112/bin/gloria_judge.py\n"
        "/src/scripts/paid_http.py|%s/gloria-judge-20261112/bin/paid_http.py\n"
        "/src/bin/value-map.py|%s/Vintos/value-map.py\n"
        "/src/scripts/toy_keepalive.py|%s/toy_keepalive.py\n" % (ws, HOME, HOME, HOME, HOME))
r = bash('printf "%%s" "%s" | outside_plan' % plan)
out = [l for l in r.stdout.splitlines() if l.strip()]
check("the plan guard names exactly the destinations outside his trees",
      len(out) == 2 and all("OUTSIDE" in l and "gloria-judge-20261112" in l for l in out), r.stdout)

guard = re.search(r'^_outside="\$\(printf .%s. "\$PLAN" \| outside_plan\)"\n\[ -z "\$_outside" \] \|\| \{.*die ', src, re.M)
check("the deploy refuses the whole plan when the guard finds one", bool(guard))
check("the guard runs after the paid_http twins and before staging",
      bool(guard) and src.index("import paid_http' \"$_paid_src\"") < guard.start() < src.index("== staging =="))
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
