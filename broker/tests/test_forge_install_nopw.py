#!/usr/bin/env python3
"""The Forge install runs without her password when she has allowed it (Gloria, 3 November: "passwordless it is"),
and asks her as before when she has not. The deploy's own lines run in bash against a stand-in sudo; nothing real is
installed, restarted or asked for."""
import os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
src = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
a = src.index('        if forge_out="$(sudo -n /usr/bin/bash "$FORGE_SCRIPT" 2>&1)"; then')
b = src.index("        fi\n", src.index('flag "forge not updated (sudo wants a password)', a)) + len("        fi\n")
block = src[a:b]

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))


def run(sudo_body):
    d = tempfile.mkdtemp(prefix="forge-nopw-")
    open(os.path.join(d, "sudo"), "w").write("#!/bin/bash\n" + sudo_body + "\n"); os.chmod(os.path.join(d, "sudo"), 0o755)
    script = ('say() { echo "SAY $*"; }; flag() { echo "FLAG $*"; }\nFORGE_SCRIPT=%s/forge-install.sh\n'
              'forge_changed=" forge_house.py"\n' % d) + block
    env = dict(os.environ, PATH=d + ":" + os.environ["PATH"])
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env).stdout


out = run('[ "$1 $2 $3" = "-n /usr/bin/bash %s" ] || exit 9; echo "Forge updated and running."' % "$(dirname $0)/forge-install.sh")
check("allowed: the install runs by itself and says the Forge is running",
      "Forge updated and running (installed without a password" in out and "FLAG" not in out, out)
out = run('echo "Forge did not come up; old bundle put back."')
check("allowed, but the Forge did not come up: flagged, the old bundle back", "FLAG forge did not come up" in out, out)
out = run('echo "sudo: a password is required" >&2; exit 1')
check("not allowed: she is asked to run it, as before",
      "FLAG forge not updated (sudo wants a password). Run: sudo bash" in out and "Forge updated" not in out, out)
check("only this one command is tried without a password (sudo -n, the script by its path)",
      block.count("sudo -n") == 1 and 'sudo -n /usr/bin/bash "$FORGE_SCRIPT"' in block, block)

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
