#!/usr/bin/env python3
"""A deployed script never imports a repo script the deploy does not install (Lab fault F-b20d601162, 28 October:
"No module named 'lab_names'". lab_names.py came with the protein-name check on 27 October, but deploy-atelier.sh never
listed it, so every Lab tick that named a protein failed on Aegis while the tests passed against the repo's scripts/).
16 November, again: lab_entity.py, loaded with __import__('lab_entity'), which this check did not read; Gloria copied
it in by hand. Since 17 November the deploy closes the list itself (scripts/deploy_closure.py).

1. Deploy closure: every module imported (import x / from x import / __import__('x') / importlib.import_module('x'))
   by an installed script is itself installed, or is not a repo module (stdlib / third-party), or reaches Aegis by
   another named route (deploy_closure.INSTALLED_ELSEWHERE). 2. The closure is computed by the deploy itself, before
   the plan, and adds new scripts transitively (a synthetic checkout, run through the deploy's own shell block).
3. A clean staged layout built only from the deploy's own list imports the Lab's naming and entity paths, with the
   repo's scripts/ off the path. Offline."""
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(REPO, "scripts")
BIN = os.path.join(REPO, "bin")
sys.path.insert(0, SCRIPTS)
import deploy_closure as DC  # noqa: E402

R = []


def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (("  ->  " + str(detail)[:600]) if detail and not ok else ""))


SH = open(os.path.join(SCRIPTS, "deploy-atelier.sh")).read()
LISTED = set(re.findall(r"[A-Za-z0-9_\-]+\.py", SH))
HERE = {f for f in os.listdir(SCRIPTS) if f.endswith(".py")}
HERE_BIN = {f for f in os.listdir(BIN) if f.endswith(".py")}

check("the deploy lists lab_names.py beside lab_investigations.py", "lab_names.py" in LISTED)
check("the deploy lists lab_entity.py (16 November: left out, copied by hand)", "lab_entity.py" in LISTED)
check("and file_reach.py", "file_reach.py" in LISTED)

# --- the import reader sees every form
tmp = tempfile.mkdtemp(prefix="closure-")
try:
    os.makedirs(os.path.join(tmp, "scripts")); os.makedirs(os.path.join(tmp, "bin"))
    def put(rel, text):
        open(os.path.join(tmp, rel), "w").write(text)
    put("scripts/organ_a.py", "import json\nx = __import__('organ_b').f\n")
    put("scripts/organ_b.py", "import importlib\ndef f():\n    return importlib.import_module('organ_c')\n")
    put("scripts/organ_c.py", "from organ_d import y\nimport os, numpy\n")
    put("scripts/organ_d.py", "y = 1\n")
    put("scripts/organ_twin.py", "z = 1\n")
    put("bin/organ_twin.py", "z = 2\n")
    put("scripts/organ_e.py", "import organ_twin\nimport model_config\nimport organ_missing_nowhere\n")
    put("scripts/model_config.py", "q = 1\n")
    put("scripts/organ_broken.py", "def (:\n")
    check("the reader sees import, from-import, __import__ and importlib.import_module",
          DC.imported_names(os.path.join(tmp, "scripts/organ_a.py")) >= {"json", "organ_b"}
          and "organ_c" in DC.imported_names(os.path.join(tmp, "scripts/organ_b.py"))
          and DC.imported_names(os.path.join(tmp, "scripts/organ_c.py")) >= {"organ_d", "os", "numpy"})
    check("a file that does not parse imports nothing (the parse check stops the deploy, not this)",
          DC.imported_names(os.path.join(tmp, "scripts/organ_broken.py")) == set())
    got = DC.closure(tmp, ["scripts/organ_a.py"])
    check("a new script named only by an import is added, transitively",
          got == ["scripts/organ_b.py", "scripts/organ_c.py", "scripts/organ_d.py"], got)
    got = DC.closure(tmp, ["scripts/organ_e.py", "bin/organ_twin.py"])
    check("a module already installed from bin/, one installed elsewhere, and a non-repo name are not added",
          got == [], got)

    # the deploy's own shell block, run as written, on this synthetic checkout
    block = SH[SH.index("# >>> import closure"):SH.index("# <<< import closure")]
    check("the deploy computes the closure before the manifest and the plan",
          SH.index("# >>> import closure") < SH.index('MANIFEST="$(printf') < SH.index('say "== plan =="'))
    script = ('say() { printf "%%s\\n" "$*"; }\ndie() { printf "STOP: %%s\\n" "$*"; exit 1; }\n'
              'SRC=%s\nSCRIPTS="organ_a.py"\nBINS=""\n%s\nprintf "FINAL %%s\\n" "$SCRIPTS"\n') % (tmp, block)
    shutil.copy2(os.path.join(SCRIPTS, "deploy_closure.py"), os.path.join(tmp, "scripts", "deploy_closure.py"))
    run = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60)
    final = (re.findall(r"^FINAL (.*)$", run.stdout, re.M) or [""])[-1].split()
    check("run by the deploy, the new scripts join SCRIPTS (so the plan installs them NEW beside the anchor)",
          run.returncode == 0 and final == ["organ_a.py", "organ_b.py", "organ_c.py", "organ_d.py"]
          and "closure: organ_b.py" in run.stdout, run.stdout + run.stderr)
    os.remove(os.path.join(tmp, "scripts", "deploy_closure.py"))
    run = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60)
    check("and a closure that cannot be computed stops the deploy", run.returncode == 1 and "STOP" in run.stdout,
          run.stdout + run.stderr)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# --- the real checkout: the closed manifest leaves no repo import uninstalled
manifest = ["scripts/" + f for f in LISTED & HERE] + ["bin/" + f for f in LISTED & HERE_BIN if f not in HERE]
added = DC.closure(REPO, manifest)
installed = {os.path.basename(m)[:-3] for m in manifest + added}
repo_modules = {f[:-3] for f in HERE | HERE_BIN}
gaps = {}
for rel in manifest + added:
    for n in DC.imported_names(os.path.join(REPO, rel)):
        if n in repo_modules and n not in installed and n not in DC.INSTALLED_ELSEWHERE:
            gaps.setdefault(n + ".py", []).append(rel)
check("deploy closure: every module an installed script imports is installed, stdlib/third-party, or installed "
      "elsewhere", not gaps, gaps)
check("and today the lists already carry everything (the closure adds nothing)", added == [], added)

# --- a staged layout from the deploy's own list
stage = tempfile.mkdtemp(prefix="deploy-stage-")
try:
    for f in LISTED & HERE:
        shutil.copy2(os.path.join(SCRIPTS, f), stage)
    probe = ("import sys; sys.path = [p for p in sys.path if not p.startswith(%r)]; sys.path.insert(0, %r); "
             "import importlib; importlib.import_module('lab_names'); importlib.import_module('lab_entity'); "
             "import lab_investigations as L; "
             "assert hasattr(L, '_correct_names') and hasattr(L, '_name_notes'); print('ok')") % (REPO, stage)
    env = dict(os.environ, HOME=stage, SPARK_WORKSPACE=os.path.join(stage, "ws"), PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH="")
    run = subprocess.run([sys.executable, "-c", probe], cwd=stage, env=env, capture_output=True, text=True, timeout=120)
    check("a staged layout built only from the deploy list imports the Lab's naming and entity paths",
          run.returncode == 0 and run.stdout.strip().endswith("ok"), (run.stdout + run.stderr)[-400:])
    os.remove(os.path.join(stage, "lab_names.py"))
    run = subprocess.run([sys.executable, "-c", probe], cwd=stage, env=env, capture_output=True, text=True, timeout=120)
    check("and without lab_names.py that same layout fails the way Aegis did",
          run.returncode != 0 and "lab_names" in run.stderr, (run.stdout + run.stderr)[-300:])
finally:
    shutil.rmtree(stage, ignore_errors=True)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
