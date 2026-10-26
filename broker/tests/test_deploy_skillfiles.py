#!/usr/bin/env python3
"""The dreaming skill's entry points are installed, not only staged (26 October).

SKILLFILES was in the manifest, so the deploy staged and validated dream-trigger.sh and should-dream.sh, but the
install plan only walked scripts/, bin/, the client and the domain files. The 22 October fix that stops a dream
consuming a thread it only explored never reached Aegis: its copy was still the 10 August one. This reads the
deploy script; it installs nothing."""
import os, re, sys
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

src = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
m = re.search(r'^SKILLFILES="([^"]*)"', src, re.M)
skills = m.group(1).split() if m else []
check("the dreaming skill's two entry points are listed", "skills/dreaming/scripts/dream-trigger.sh" in skills
      and "skills/dreaming/scripts/should-dream.sh" in skills, skills)
for f in skills:
    check("%s exists in the repository" % f, os.path.isfile(os.path.join(REPO, f)))
plan_start = src.index('PLAN=""; ambiguous=0')
loop = re.search(r'for spec in \$SKILLFILES; do(.*?)\ndone', src[plan_start:], re.S)
check("the install plan walks the skill files", bool(loop))
body = loop.group(1) if loop else ""
check("each goes to the workspace's skills tree, where cron runs it", '"$HOME/.vintos/workspace/$spec"' in body, body)
check("each is added to the plan that is installed", 'PLAN="$PLAN$SRC/$spec|$d' in body, body)
check("the skill loop comes before the plan is used", src.index("for spec in $SKILLFILES") < src.index('done <<< "$PLAN"'))
dt = open(os.path.join(REPO, "skills", "dreaming", "scripts", "dream-trigger.sh")).read()
check("the copy that will be installed asks whether the dream resolved the thread, not only explored it",
      "or only explore" in dt and "meaningfully engage" not in dt)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
