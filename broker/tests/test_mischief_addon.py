#!/usr/bin/env python3
"""Mischief has a trigger: outreach and journals invoke his mischief organ as an add-on.
His felt-gate / timing / cooldowns inside mischief-detector.sh are the y/n."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
R = []
def check(name, ok):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name)

HOSTS = ["bin/vintos-initiate.sh", "bin/idle-journal.sh", "scripts/idle-journal.sh"]
for h in HOSTS:
    src = open(os.path.join(ROOT, h)).read()
    check("%s invokes the mischief organ as an add-on" % h,
          "mischief-detector.sh" in src and "Mischief add-on" in src)
    check("%s never lets mischief fail or block the host task" % h,
          '[ -x "$_MISCHIEF" ] && bash "$_MISCHIEF" || true' in src)

# mischief-detector.sh must be manifested or the add-on calls a file that never deployed.
manifest = open(os.path.join(ROOT, "scripts/deploy-atelier.sh")).read()
check("mischief-detector.sh is in the deploy manifest", "mischief-detector.sh" in manifest)

print("\n%d/%d passed" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
