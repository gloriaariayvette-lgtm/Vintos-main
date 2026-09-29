#!/usr/bin/env python3
"""The deploy refreshes the Forge's own bundle (/home/atelier/forge-loop) when it differs, and puts the old
one back if the new one does not come up. Nothing refreshed it after 2026-09-21, so her Forge page stayed
overrun by cancelled Lab projects while the fix sat in the repository (2026-09-29).

Runs only the deploy's forge block, against a scratch folder, with fake sudo and systemctl."""
import os, subprocess, sys, tempfile
from pathlib import Path
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  " + str(detail)[:3000]))

repo = Path(__file__).resolve().parents[2]
src = (repo / "scripts/deploy-atelier.sh").read_text()
a = src.index("# -------------------------------------------------------------------- forge")
b = src.index("# -------------------------------------------------------------------- house", a)
block = src[a:b]
check("the real bundle list names the Forge page", "forge_loop_ui.html" in (repo / "scripts/forge-loop-files.txt").read_text())

root = Path(tempfile.mkdtemp())
bindir = root / "bin"; bindir.mkdir()
log = root / "commands"
(bindir / "systemctl").write_text('''#!/bin/sh
printf 'systemctl %s\\n' "$*" >> "$CTL_LOG"
case "$*" in
  cat*) [ "$HAS_UNIT" = 1 ] ;;
  restart*) exit 0 ;;
  is-active*) [ "${ACTIVE:-1}" = 1 ] ;;
esac
''')
# sudo: -n succeeds only when SUDO_OK=1; install loses its -o/-g (no root in a test).
(bindir / "sudo").write_text('''#!/bin/bash
printf 'sudo %s\\n' "$*" >> "$CTL_LOG"
[ "$1" = "-n" ] && { [ "$SUDO_OK" = 1 ] || exit 1; shift; }
[ "$1" = "true" ] && exit 0
if [ "$1" = "install" ]; then
  shift; args=(); while [ $# -gt 0 ]; do case "$1" in -o|-g) shift 2 ;; *) args+=("$1"); shift ;; esac; done
  exec install "${args[@]}"
fi
exec "$@"
''')
for f in ("systemctl", "sudo"): (bindir / f).chmod(0o755)
path = str(bindir) + ":" + os.path.dirname(sys.executable) + ":" + os.defpath

def run(case, has_unit=1, sudo_ok=1, confirm=0, live=None, new=None):
    d = root / case
    srcdir = d / "src"; (srcdir / "scripts").mkdir(parents=True)
    live_dir = d / "forge-loop"; live_dir.mkdir()
    (srcdir / "scripts/forge-loop-files.txt").write_text("forge_loop_runtime.py\n# a note\n\nforge_loop_ui.html\n")
    old = {"forge_loop_runtime.py": "x = 1\n", "forge_loop_ui.html": "<p>all projects</p>"}
    for k, v in (live or old).items(): (live_dir / k).write_text(v)
    for k, v in dict(old, **(new or {})).items(): (srcdir / "scripts" / k).write_text(v)
    stage = d / "stage"; stage.mkdir(); backup = d / "backup"
    log.write_text("")
    script = ("say(){ printf '%%s\\n' \"$*\"; }; flag(){ printf 'FLAG %%s\\n' \"$*\"; }\n"
              "confirm_unit(){ printf 'systemctl confirm %%s\\n' \"$2\" >> \"$CTL_LOG\"; return %d; }\nsleep(){ :; }\n"
              "SRC=%s\nSTAGE=%s\nBACKUP=%s\n" % (confirm, srcdir, stage, backup)) + block
    env = dict(os.environ, PATH=path, CTL_LOG=str(log), HAS_UNIT=str(has_unit), SUDO_OK=str(sudo_ok),
               VINTOS_FORGE_DIR=str(live_dir), HOME=str(d))
    p = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=60)
    return p, live_dir, backup, log.read_text()

p, live, backup, cmds = run("same")
check("an identical bundle is not touched and the Forge is not restarted",
      "unchanged (2 files read identical)" in p.stdout and "restart" not in cmds, p.stdout + cmds)

p, live, backup, cmds = run("changed", new={"forge_loop_ui.html": "<p>open projects only</p>"})
check("a changed Forge page is installed, the old bundle kept, the Forge restarted and confirmed",
      (live / "forge_loop_ui.html").read_text() == "<p>open projects only</p>"
      and (backup / "forge-loop/forge_loop_ui.html").read_text() == "<p>all projects</p>"
      and "systemctl restart atelier-forge-loop" in cmds and "confirm atelier-forge-loop" in cmds
      and "changed: forge_loop_ui.html" in p.stdout and "FLAG" not in p.stdout, p.stdout + cmds)
check("only the changed file is installed", "forge_loop_runtime.py" not in "".join(l for l in cmds.splitlines(True) if "install" in l), cmds)

p, live, backup, cmds = run("fails", confirm=1, new={"forge_loop_runtime.py": "x = 2\n"})
check("a Forge that does not come up gets its old bundle back and is restarted on it",
      (live / "forge_loop_runtime.py").read_text() == "x = 1\n" and "did not come up" in p.stdout
      and sum(l.startswith("systemctl restart atelier-forge-loop") for l in cmds.splitlines()) == 2, p.stdout + cmds)

p, live, backup, cmds = run("broken", new={"forge_loop_runtime.py": "def (:\n"})
check("a bundle that does not compile is never installed",
      (live / "forge_loop_runtime.py").read_text() == "x = 1\n" and "does not compile" in p.stdout and "restart" not in cmds, p.stdout)

p, live, backup, cmds = run("nosudo", sudo_ok=0, new={"forge_loop_ui.html": "<p>new</p>"})
script = root / "nosudo" / ".vintos/deploy/forge-install.sh"
check("without passwordless sudo nothing is touched and she gets one command",
      (live / "forge_loop_ui.html").read_text() == "<p>all projects</p>" and "Run: sudo bash " + str(script) in p.stdout
      and "restart" not in cmds, p.stdout)
fake_root = dict(os.environ, PATH=path, CTL_LOG=str(log), HAS_UNIT="1")
(bindir / "install").write_text('#!/bin/bash\nargs=(); while [ $# -gt 0 ]; do case "$1" in -o|-g) shift 2 ;; *) args+=("$1"); shift ;; esac; done\nexec /usr/bin/install "${args[@]}"\n')
(bindir / "install").chmod(0o755)
log.write_text("")
ran = subprocess.run(["bash", str(script)], env=fake_root, capture_output=True, text=True, timeout=60)
check("that command installs the changed file, keeps the old one and restarts the Forge",
      (live / "forge_loop_ui.html").read_text() == "<p>new</p>" and "Forge updated and running." in ran.stdout
      and (root / "nosudo/backup/forge-loop/forge_loop_ui.html").read_text() == "<p>all projects</p>"
      and "systemctl restart atelier-forge-loop" in log.read_text(), ran.stdout + ran.stderr)
(live / "forge_loop_ui.html").write_text("<p>all projects</p>")
ran = subprocess.run(["bash", str(script)], env=dict(fake_root, ACTIVE="0"), capture_output=True, text=True, timeout=60)
check("and if the Forge does not come up on it, the old bundle is put back",
      (live / "forge_loop_ui.html").read_text() == "<p>all projects</p>" and "old bundle put back" in ran.stdout, ran.stdout + ran.stderr)
(bindir / "install").unlink()

p, live, backup, cmds = run("nounit", has_unit=0, new={"forge_loop_ui.html": "<p>new</p>"})
check("a host without the Forge unit is left alone", "not touched" in p.stdout and "install" not in cmds, p.stdout)

check("the suite ran against scratch folders and fake sudo/systemctl only",
      all(str(root) in str(x) for x in (live, backup)) and (bindir / "sudo").exists() and (bindir / "systemctl").exists())
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
