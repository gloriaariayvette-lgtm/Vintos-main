#!/usr/bin/env python3
"""Root installs the Forge bundle the deploy staged (4 November), so the Study's sandboxed deploy needs no sudo.
The installer runs here as a plain user in its test mode, on scratch folders, with a stand-in for systemctl; nothing
real is installed or restarted. Checks: it installs exactly the named files with their hashes, refuses links, odd
names and wrong hashes, puts the old bundle back if the Forge does not come up, answers each request once, and the
deploy stages a request and reads the answer instead of asking sudo."""
import hashlib, json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
INSTALLER = os.path.join(REPO, "scripts", "vintos-forge-install")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

T = tempfile.mkdtemp(prefix="forge-root-")
REQ, DEST, STATE = (os.path.join(T, x) for x in ("request", "forge-loop", "state"))
os.makedirs(DEST)
open(os.path.join(DEST, "forge_house.py"), "w").write("OLD = 1\n")
fake = os.path.join(T, "systemctl"); log = os.path.join(T, "systemctl.log")
open(fake, "w").write('#!/bin/bash\necho "$*" >> %s\n[ "$1" = is-active ] && exit "$(cat %s/active 2>/dev/null || echo 0)"\nexit 0\n' % (log, T))
os.chmod(fake, 0o755)
ENV = dict(os.environ, VINTOS_FORGE_INSTALL_TEST="1", VINTOS_FORGE_OWNER_UID=str(os.getuid()), VINTOS_FORGE_REQUEST=REQ,
           VINTOS_FORGE_DIR=DEST, VINTOS_FORGE_STATE=STATE, VINTOS_FORGE_SYSTEMCTL=fake)


def stage(rid, files, hashes=None):
    import shutil
    shutil.rmtree(REQ, ignore_errors=True); os.makedirs(os.path.join(REQ, "bundle"))
    for n, body in files.items():
        if body is not None:
            open(os.path.join(REQ, "bundle", n), "w").write(body)
    hs = hashes or {n: hashlib.sha256(b.encode()).hexdigest() for n, b in files.items() if b is not None}
    json.dump({"id": rid, "files": hs}, open(os.path.join(REQ, "request.json"), "w"))
    open(os.path.join(REQ, "ready"), "w").close()


def run():
    out = subprocess.run([sys.executable, INSTALLER], env=ENV, capture_output=True, text=True, timeout=60)
    try: return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception: return {"raw": out.stdout + out.stderr}


check("the installer runs as root only; its paths move only in test mode, never as root",
      'os.geteuid() != 0 and os.environ.get("VINTOS_FORGE_INSTALL_TEST") == "1"' in open(INSTALLER).read())
stage("r1", {"forge_house.py": "NEW = 2\n", "forge_new.py": "X = 1\n"})
r = run()
check("it installs exactly the named files and says the Forge is running",
      r.get("ok") and open(os.path.join(DEST, "forge_house.py")).read() == "NEW = 2\n" and os.path.exists(os.path.join(DEST, "forge_new.py")), r)
check("the ready mark is taken, so the path unit fires again only for a new request", not os.path.exists(os.path.join(REQ, "ready")))
check("it restarted the Forge and asked if it came up", "restart atelier-forge-loop" in open(log).read() and "is-active" in open(log).read())
check("its answer is where the deploy reads it", json.load(open(os.path.join(STATE, "result.json")))["id"] == "r1")
check("a request already answered is not installed twice", run().get("id") == "r1" and open(log).read().count("restart") == 1)

stage("r2", {"forge_house.py": "EVIL = 1\n"}, hashes={"forge_house.py": "0" * 64})
r = run()
check("a file that is not the one the request names is refused", not r.get("ok") and "not the file" in r.get("message", "")
      and open(os.path.join(DEST, "forge_house.py")).read() == "NEW = 2\n", r)
stage("r3", {"../escape.py": "X\n"}, hashes={"../escape.py": "0" * 64})
check("a name with a path in it is refused", "refused name" in run().get("message", ""))
stage("r4", {"run.sh": "X\n"}, hashes={"run.sh": hashlib.sha256(b"X\n").hexdigest()})
check("an extension outside the Forge's own is refused", "refused name" in run().get("message", ""))
stage("r5", {"forge_house.py": None}, hashes={"forge_house.py": hashlib.sha256(b"x").hexdigest()})
os.symlink("/etc/hostname", os.path.join(REQ, "bundle", "forge_house.py"))
r = run()
check("a link in the bundle is never followed", not r.get("ok") and open(os.path.join(DEST, "forge_house.py")).read() == "NEW = 2\n", r)

open(os.path.join(T, "active"), "w").write("3")
stage("r6", {"forge_house.py": "BROKEN = 1\n", "forge_brand_new.py": "Y = 1\n"})
r = run()
check("a Forge that does not come up gets its old files back", not r.get("ok") and "put back" in r.get("message", "")
      and open(os.path.join(DEST, "forge_house.py")).read() == "NEW = 2\n" and not os.path.exists(os.path.join(DEST, "forge_brand_new.py")), r)
os.remove(os.path.join(T, "active"))

# ---- the deploy's side ----------------------------------------------------------------------------------------
src = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
a = src.index('    elif [ -x /usr/local/sbin/vintos-forge-install ]'); b = src.index("    else\n        # One command for her", a)
block = src[a + len("    el"):b].replace("if [ -x /usr/local/sbin/vintos-forge-install ] && systemctl is-enabled --quiet vintos-forge-install.path 2>/dev/null; then", "if true; then", 1) + "    fi\n"
home = os.path.join(T, "home"); stage_dir = os.path.join(T, "stage"); os.makedirs(stage_dir)
open(os.path.join(stage_dir, "forge_house.py"), "w").write("FROM_DEPLOY = 1\n")
answerer = os.path.join(T, "answer.sh")   # stands in for root: answers the request the deploy staged
open(answerer, "w").write('#!/bin/bash\nfor i in $(seq 1 50); do [ -f "$1/ready" ] && break; sleep 0.1; done\n'
                          'id=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))[\'id\'])" "$1/request.json")\n'
                          'printf \'{"id": "%s", "ok": true, "message": "Forge updated and running."}\' "$id" > "$2"\n')
os.chmod(answerer, 0o755)
script = ('say() { echo "SAY $*"; }; flag() { echo "FLAG $*"; }\nHOME=%s\nFORGE_STAGE=%s\nforge_changed=" forge_house.py"\n'
          'FORGE_MARK=$HOME/.vintos/deploy/.forge-installed\nforge_mark_lines="abc  forge_house.py"\n'
          'VINTOS_FORGE_RESULT=%s/result.json\nVINTOS_FORGE_WAIT=10\n%s "$HOME/.vintos/deploy/forge-request" %s/result.json &\n' % (home, stage_dir, T, answerer, T)) + block
out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60).stdout
req = json.load(open(os.path.join(home, ".vintos/deploy/forge-request/request.json")))
check("the deploy stages the changed files with their hashes and asks no sudo",
      req["files"] == {"forge_house.py": hashlib.sha256(b"FROM_DEPLOY = 1\n").hexdigest()} and "sudo -n" not in block and "sudo install" not in block and "sudo bash" not in block, req)
check("and reports root's answer, keeping what was installed",
      "Forge updated and running (installed by root's own installer)" in out and "FLAG" not in out
      and open(os.path.join(home, ".vintos/deploy/.forge-installed")).read().strip() == "abc  forge_house.py", out)
os.remove(os.path.join(T, "result.json"))
script2 = script.replace(answerer, "true").replace("VINTOS_FORGE_WAIT=10", "VINTOS_FORGE_WAIT=1")
out = subprocess.run(["bash", "-c", script2], capture_output=True, text=True, timeout=60).stdout
check("no answer from root is said plainly", "FLAG forge not updated: root's installer did not answer" in out, out)
units = [open(os.path.join(REPO, "broker", u)).read() for u in ("vintos-forge-install.path", "vintos-forge-install.service")]
check("the units: fired by the ready mark; the installer sandboxed to the three folders it touches",
      "PathExists=/home/gloria/.vintos/deploy/forge-request/ready" in units[0]
      and "ProtectSystem=strict" in units[1] and "ReadWritePaths=/home/atelier/forge-loop /var/lib/vintos-forge /home/gloria/.vintos/deploy/forge-request" in units[1])
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
