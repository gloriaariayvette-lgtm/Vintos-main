#!/usr/bin/env python3
"""A deployed script never imports a repo script the deploy does not install (Lab fault F-b20d601162, 28 October:
"No module named 'lab_names'". lab_names.py came with the protein-name check on 27 October, but deploy-atelier.sh never
listed it, so every Lab tick that named a protein failed on Aegis while the tests passed against the repo's scripts/).

1. A clean staged layout built only from the deploy's own list imports lab_investigations and its naming helper, with
   the repo's scripts/ off the path. 2. No listed script imports, anywhere in its body, a repo-local module the deploy
   does not list, except the ones already installed some other way (KNOWN, below: a new gap fails). Offline."""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(REPO, "scripts")
R = []


def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (("  ->  " + str(detail)[:400]) if detail and not ok else ""))


SH = open(os.path.join(SCRIPTS, "deploy-atelier.sh")).read()
LISTED = set(re.findall(r"[A-Za-z0-9_\-]+\.py", SH))
HERE = {f for f in os.listdir(SCRIPTS) if f.endswith(".py")}

# Imported by a deployed script but installed by another route before this check existed. Not new: a module added
# here must say how it reaches Aegis.
KNOWN = {"affective_weight.py", "bandwidth_collapse.py", "command_bubble.py", "conflict_surface.py",
         "constitutional_tiers.py", "ghost_lean.py", "image_sight.py", "inclination_engine.py", "model_config.py",
         "nifrathir.py", "reading.py", "resonance_marks.py", "session_map.py", "somatic_felt.py", "truth_lock.py",
         "yearning_scars.py",
         "forge_verification_ack.py"}   # used only inside the Forge, installed there from forge-loop-files.txt


def imports(path):
    try:
        tree = ast.parse(open(path).read())
    except SyntaxError:
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.add(node.module.split(".")[0])
    return out


check("the deploy lists lab_names.py beside lab_investigations.py", "lab_names.py" in LISTED)

gaps = {}
for f in sorted(LISTED & HERE):
    for n in imports(os.path.join(SCRIPTS, f)):
        m = n + ".py"
        if m in HERE and m not in LISTED and m not in KNOWN:
            gaps.setdefault(m, []).append(f)
check("no deployed script imports a repo module the deploy does not install", not gaps, gaps)

stage = tempfile.mkdtemp(prefix="deploy-stage-")
try:
    for f in LISTED & HERE:
        shutil.copy2(os.path.join(SCRIPTS, f), stage)
    probe = ("import sys; sys.path = [p for p in sys.path if not p.startswith(%r)]; sys.path.insert(0, %r); "
             "import importlib; importlib.import_module('lab_names'); import lab_investigations as L; "
             "assert hasattr(L, '_correct_names') and hasattr(L, '_name_notes'); print('ok')") % (REPO, stage)
    env = dict(os.environ, HOME=stage, SPARK_WORKSPACE=os.path.join(stage, "ws"), PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH="")
    run = subprocess.run([sys.executable, "-c", probe], cwd=stage, env=env, capture_output=True, text=True, timeout=120)
    check("a staged layout built only from the deploy list imports the Lab's naming path",
          run.returncode == 0 and run.stdout.strip().endswith("ok"), (run.stdout + run.stderr)[-400:])
    os.remove(os.path.join(stage, "lab_names.py"))
    run = subprocess.run([sys.executable, "-c", probe], cwd=stage, env=env, capture_output=True, text=True, timeout=120)
    check("and without lab_names.py that same layout fails the way Aegis did",
          run.returncode != 0 and "lab_names" in run.stderr, (run.stdout + run.stderr)[-300:])
finally:
    shutil.rmtree(stage, ignore_errors=True)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
