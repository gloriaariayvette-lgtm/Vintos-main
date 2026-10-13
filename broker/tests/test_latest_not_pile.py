#!/usr/bin/env python3
"""Nothing piles up in his prompt (Gloria, 2026-10-13: "Everything should either be rolling with the latest or
swapping completely daily").

- SELF-MODEL.md and GLORIA-MODEL.md keep their fixed base; beneath it his additions are rewritten whole each week
  and replace the last version, instead of every week's entry being kept forever (58 KB and 27 KB on Aegis).
- Five append-only logs were cut to their first few hundred characters before the newest entry was picked, so he
  saw only the oldest; they now give the latest entry. YouTube gives the latest entry only.

Source only: the update scripts would call his model and post to her phone, so nothing here runs them."""
import os, re, sys

REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
src = lambda p: open(os.path.join(REPO, p)).read()

gm = src("bin/gloria-model-update.sh")
write = gm[gm.index('BASE=$(sed -n'):gm.index('date +%s > "$COOLDOWN_FILE"')]
check("the Gloria model keeps its base", 'echo "$BASE"' in write)
check("the Gloria model no longer carries every old addition forward", "ADDITIONS" not in gm)
check("he is told his rewrite replaces his additions", "REPLACES your previous additions" in gm)
check("the old version is still kept in its history first", gm.index("gloria-model-history") < gm.index('> "$MODEL_FILE.tmp"'))

sm = src("bin/self-model-update.sh")
w2 = sm[sm.index("# --- Write: fixed base"):sm.index('} > "$MODEL_FILE.tmp.$$"')]
check("the self-model keeps its base", 'echo "$BASE"' in w2)
check("the self-model no longer carries every old entry forward", "ACCRETED" not in w2)
check("he is told his rewrite replaces his additions", "REPLACES your previous additions" in sm)
check("the old version is still kept in its history first", sm.index("self-model-history") < sm.index("# --- Write: fixed base"))

sv = src("bin/server.py")
for f in ("unprecedented-states.md", "silence-contracts.md", "surprise-log.md", "counterfactual-archive.md",
          "creative-discoveries.md"):
    check("%s gives its latest entry" % f, re.search(r'latest_entry\(os\.path\.join\(MEMORY, "%s"\)' % re.escape(f), sv)
          and not re.search(r'read_file\(os\.path\.join\(MEMORY, "%s"\)' % re.escape(f), sv))
yt = [m.start() for m in re.finditer(r'youtube-discoveries\.md', sv)]
check("every YouTube read in the server gives the latest entry only",
      sv.count("[e.strip() for e in _entries if e.strip()][-1:]") >= 3 and "Your recent YouTube discoveries" not in sv)
check("Slack's YouTube read gives the latest entry only", 'yt[-1][:400]' in src("scripts/dot_channel.py"))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
