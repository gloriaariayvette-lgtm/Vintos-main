#!/usr/bin/env python3
"""The broker must be a service, and the deploy's rollback must be complete.

Two lessons guard here. First: the broker ran for weeks as a manually
nohup-launched process — alive until the first reboot, watched by nobody.
The unit must be root-MANAGED (system unit, survives reboot with no user
manager or lingering assumed) but never root-RUN (User=atelier, always).
Second: the generated restore.sh backed up broker.py and stratagem_store.py
but contained no commands to restore them — its "put it all back" claim was
false for exactly the files that run as another user.

These are static guards over the deploy script, the unit file, and the watch
script; they cannot start systemd, but they can make the regressions
unwritable.
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:90]) if d else ""))

def rd(*p):
    return open(os.path.join(ROOT, *p), errors="replace").read()

# ---------------------------------------------------------------- the unit
unit_path = os.path.join(ROOT, "broker", "vintos-atelier.service")
check("the unit file exists in the checkout", os.path.isfile(unit_path))
unit = rd("broker", "vintos-atelier.service") if os.path.isfile(unit_path) else ""

check("the process runs as atelier, never root",
      re.search(r"^User=atelier$", unit, re.M) and not re.search(r"^User=root$", unit, re.M))
check("it starts the installed broker",
      "ExecStart=/usr/bin/python3 /home/atelier/broker.py" in unit)
check("it restarts on failure", re.search(r"^Restart=(on-failure|always)$", unit, re.M))
check("it starts on boot (system target, no user manager assumed)",
      "WantedBy=multi-user.target" in unit)
check("the legacy duplicate broker unit conflicts mechanically",
      "Conflicts=atelier-broker.service" in unit)
check("restrictive umask", re.search(r"^UMask=00?77$", unit, re.M))
check("filesystem protected, /home/atelier writable",
      "ProtectSystem=strict" in unit and "ReadWritePaths=/home/atelier" in unit)
check("stdout/stderr go to journald",
      "StandardOutput=journal" in unit and "StandardError=journal" in unit)
check("no privilege escalation from inside", "NoNewPrivileges=yes" in unit)
check("the unit adds no listener of its own — the broker's localhost bind stands",
      "ListenStream" not in unit and "Socket" not in unit)

# --------------------------------------------------------------- the deploy
dep = rd("scripts", "deploy-atelier.sh")

check("deploy installs the unit file",
      'UNIT_NAME="vintos-atelier"' in dep
      and re.search(r'install -m 644 "\$SRC/broker/\$UNIT_NAME\.service" "\$UNIT_DST"', dep)
      and "systemctl daemon-reload" in dep)
check("deploy enables the unit (reboot survival)", re.search(r"systemctl enable\s+\"?\$UNIT_NAME", dep))
check("deploy starts/restarts via systemd, not nohup", "nohup" not in dep)
check("deploy retires a leftover manual broker before starting the unit",
      re.search(r"pkill -f .python3 \$BROKER", dep))
check("deploy disables the legacy duplicate broker unit",
      "disable --now atelier-broker.service" in dep)
check("deploy verifies service active and enabled after install",
      "is-active" in dep and "is-enabled" in dep)
check("failed start points at journalctl, not a dead log file",
      "journalctl -u" in dep and "broker.log" not in dep)
check("preflight refuses a checkout missing the unit file",
      re.search(r'\[ -f "\$SRC/broker/\$UNIT_NAME\.service" \]\s*\|\|\s*missing=', dep))

# rollback: restore.sh must contain commands for the broker files, with owner
# and mode, and for the unit — not merely copies of them in the backup dir
check("restore.sh restores broker files with atelier owner and mode",
      re.search(r"printf 'sudo install -o atelier -g atelier -m 644[^']*'.{0,120}?>> \"\$BACKUP/restore\.sh\"", dep, re.S))
check("restore.sh restores the service unit when one was replaced",
      re.search(r"printf 'sudo install -m 644[^']*\.service[^']*'.{0,120}?>> \"\$BACKUP/restore\.sh\"", dep, re.S))
check("restore.sh reloads systemd and restores prior service state",
      "daemon-reload" in dep.split("== backing up ==", 1)[-1].split("== installing ==")[0]
      if "== backing up ==" in dep else False)
check("an unreadable broker file is recorded in restore.sh, not silently skipped",
      "NOT backed up" in dep)
check("prior broker state is recorded honestly",
      "broker state at backup time" in dep and "manual-process" in dep)

# curated list: the live cron scripts are owned explicitly, never by wildcard
for f in ("atelier-door.sh", "atelier-canary.sh", "atelier-broker-watch.sh"):
    check("deploy list owns %s" % f, re.search(r"^SCRIPTS=|\b%s\b" % re.escape(f), dep)
          and f in dep.split("SCRIPTS=", 1)[1].split('"')[1])
    check("%s exists in the checkout" % f, os.path.isfile(os.path.join(ROOT, "scripts", f)))

# ---------------------------------------------------------------- the watch
watch = rd("scripts", "atelier-broker-watch.sh")
check("watch distinguishes unreachable from empty worktable",
      "unreachable" in watch and "/health" in watch and "empty worktable" in watch)
check("watch notifies only after sustained failure, not first miss",
      re.search(r'-eq 3', watch) and "ntfy" in watch)
check("watch clears its failure state on recovery", re.search(r'rm -f "\$STATE"', watch))
check("watch never treats a quiet worktable as an outage",
      re.search(r'\[ -n "\$H" \]', watch))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
