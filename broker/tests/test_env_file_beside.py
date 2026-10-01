#!/usr/bin/env python3
"""His keys are found when another agent runs his scripts as itself (2026-10-01).

Dot ran his music on Aegis with its own home and was told "no KIE_API_KEY in vintos.env". The reader now looks
in VINTOS_ENV_FILE, then the caller's own ~/.vintos/vintos.env, then the one beside the install. Scratch homes
and a scratch install hold made-up keys; nothing real is read and nothing is sent.
"""
import os, shutil, subprocess, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:200]) if d and not ok else ""))

ROOT = tempfile.mkdtemp(prefix="env-beside-")
HIS = os.path.join(ROOT, "gloria")                     # the owner's home, with his install and his keys
DOTS = os.path.join(ROOT, "dot")                       # another agent's home: no vintos.env of its own
SC = os.path.join(HIS, ".vintos", "workspace", "scripts"); os.makedirs(SC); os.makedirs(DOTS)
for f in ("env_file.py", "dream-music.py"):
    shutil.copy(os.path.join(REPO, "scripts", f), SC)
open(os.path.join(HIS, ".vintos", "vintos.env"), "w").write('KIE_API_KEY="kie-made-up-123"\n')
check("the keys here are made up, in a scratch install", ROOT.startswith(tempfile.gettempdir()))

def read(home, extra=None, name="KIE_API_KEY"):
    env = {"HOME": home, "PATH": os.environ.get("PATH", "")}
    env.update(extra or {})
    code = "import sys; sys.path.insert(0, %r); import env_file; print(env_file.value(%r))" % (SC, name)
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True).stdout.strip()

check("run as the owner, his own file is read", read(HIS) == "kie-made-up-123")
check("run as another agent with no file of its own, the one beside the install is read", read(DOTS) == "kie-made-up-123")
other = os.path.join(ROOT, "other.env"); open(other, "w").write("KIE_API_KEY=from-explicit\n")
check("VINTOS_ENV_FILE wins when it is set", read(DOTS, {"VINTOS_ENV_FILE": other}) == "from-explicit")
os.makedirs(os.path.join(DOTS, ".vintos")); open(os.path.join(DOTS, ".vintos", "vintos.env"), "w").write("KIE_API_KEY=dots-own\n")
check("an agent with its own file keeps reading its own", read(DOTS) == "dots-own")
code = ("import sys, os; sys.argv=['x']; sys.path.insert(0, %r); "
        "src=open(os.path.join(%r, 'dream-music.py')).read(); "
        "start=src.index('def _env('); end=src.index('# Kie.ai Suno v6'); ns={'os': os, '__file__': os.path.join(%r, 'dream-music.py')}; exec(src[start:end], ns); "
        "sys.modules.pop('env_file', None); sys.path[:] = [p for p in sys.path if p != %r]; "
        "print(ns['_env']('KIE_API_KEY'))") % (SC, SC, SC, SC)
shutil.rmtree(os.path.join(DOTS, ".vintos"))
r = subprocess.run([sys.executable, "-c", code], env={"HOME": DOTS, "PATH": os.environ.get("PATH", "")}, capture_output=True, text=True)
check("his music script finds the key too, run by another agent", r.stdout.strip() == "kie-made-up-123", r.stdout + r.stderr[-300:])
shutil.rmtree(ROOT, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
