#!/usr/bin/env python3
"""The somatic-session narrator (source of the morning unresolved somatic thread) is
manifested, scheduled at 6am, and points at the deployed causality engine — the three
reasons it had stopped producing threads."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
R = []
def check(name, ok):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name)

svc = open(os.path.join(ROOT, "broker/vintos-somatic-narrate.service")).read()
tmr = open(os.path.join(ROOT, "broker/vintos-somatic-narrate.timer")).read()
dep = open(os.path.join(ROOT, "scripts/deploy-atelier.sh")).read()
org = open(os.path.join(ROOT, "scripts/somatic_narrate.py")).read()

check("service runs the somatic narrator as a oneshot",
      "[Service]" in svc and "somatic_narrate.py" in svc and "ExecStart=" in svc)
check("timer fires in the early morning (06:00)",
      "[Timer]" in tmr and "OnCalendar=" in tmr and "06:00:00" in tmr)
check("the organ is in the deploy SCRIPTS manifest", "somatic_narrate.py" in dep)
check("both units are in the deploy file manifest",
      '"$SOMATIC_NAME.service"' in dep and '"$SOMATIC_NAME.timer"' in dep)
check("the deploy installs AND enables the timer so it actually fires",
      'install -m 644 "$(staged "$SOMATIC_TIMER_SRC")"' in dep
      and 'enable "$SOMATIC_NAME.timer"' in dep and 'confirm_timer --user "$SOMATIC_NAME"' in dep)
check("the organ no longer defaults only to the ~/Vintos orphan causality path",
      "os.path.join(SCRIPTS, \"causality-engine.py\")" in org)

print("\n%d/%d passed" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
