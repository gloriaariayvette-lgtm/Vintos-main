#!/usr/bin/env python3
"""The deploy never takes the Study's workbench for his live scripts (2026-10-03). The workbench is a whole clone of
the repository at ~/.vintos/study-workbench, so the deploy found turn_coordinator.py twice, refused to pick, and the
Study's first fix was reverted. Runs the deploy's own locate() in bash against a scratch home; nothing is installed."""
import os, re, subprocess, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="deploy-workbench-")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

src = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
fn = re.search(r"^locate\(\) \{.*?^\}", src, re.M | re.S).group(0)
for d in (".vintos/workspace/scripts", ".vintos/study-workbench/scripts", "Vintos-main/scripts"):
    os.makedirs(os.path.join(HOME, d), exist_ok=True)
    open(os.path.join(HOME, d, "turn_coordinator.py"), "w").write("# his\n")
out = subprocess.run(["bash", "-c", 'HOME="$1"; DEPTH=6; _SELF="$HOME/Vintos-main"\n%s\nlocate turn_coordinator.py' % fn,
                      "_", HOME], capture_output=True, text=True, timeout=60).stdout.split()
check("the scratch home is all it looks in", all(p.startswith(HOME) for p in out), out)
check("only his live copy is found, not the Study's workbench or the checkout",
      out == [os.path.join(HOME, ".vintos/workspace/scripts/turn_coordinator.py")], out)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
