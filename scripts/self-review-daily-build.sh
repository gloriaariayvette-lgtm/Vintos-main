#!/bin/bash
# self-review-daily-build.sh — build at most ONE eligible self-review proposal per day, only when it
# names no protected file (those stay Gloria's to trigger by hand). Every applied or failed build
# posts one ntfy line so she sees it the same day. Pause with:  touch ~/.vintos/self-review-builder.pause
# (fable-study-p4, 2026-09-05)
#   cron:  15 6 * * *  bash $HOME/.vintos/workspace/scripts/self-review-daily-build.sh >> $HOME/.vintos/logs/self-review-daily-build.log 2>&1
set -u
WS="$HOME/.vintos/workspace"; SCRIPTS="$WS/scripts"; MEM="$WS/memory"
PAUSE="$HOME/.vintos/self-review-builder.pause"
STAMP="$MEM/.self-review-daily-build.stamp"
TOPIC="https://ntfy.sh/vintos-gloria-9kx"
say(){ echo "$(date +%F_%H%M) $*"; }
notify(){ curl -s -m 15 -H "Title: Self-review builder" -d "$1" "$TOPIC" >/dev/null 2>&1 || true; }

[ -f "$PAUSE" ] && { say "paused ($PAUSE present)"; exit 0; }
[ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$(date +%F)" ] && { say "already built today"; exit 0; }

PICK=$(cd "$SCRIPTS" && python3 - <<'PY'
import json, os, sys
sys.path.insert(0, ".")
import self_review_builder as b
try:
    import protected_paths as pp
    prot = set(pp.repo_paths()) | set(b.SELF_PROTECTED)
except Exception:
    prot = set(b.SELF_PROTECTED)
for pid in b.ready():
    p = b.latest_proposal(pid) or {}
    if p.get("gloria_approval_required"): continue
    files = set(p.get("files") or p.get("declared_files") or p.get("allowed_files") or [])
    if any(f in prot for f in files): continue
    print(pid); break
PY
)
if [ -z "$PICK" ]; then say "nothing eligible that avoids protected files"; exit 0; fi
say "building $PICK"
OUT=$(cd "$SCRIPTS" && python3 self_review_builder.py build "$PICK" 2>&1); RC=$?
STATE=$(echo "$OUT" | grep -o '"state": *"[a-z_]*"' | head -1 | sed 's/.*"\([a-z_]*\)"$/\1/')
echo "$OUT" | tail -20
date +%F > "$STAMP"
if [ "$RC" = "0" ] && [ "$STATE" = "applied" ]; then
    notify "Built one of his own proposals today: $PICK (applied). ~/.vintos/workspace/memory/self-review-build-events.jsonl has the record."
else
    notify "Tried to build $PICK today and it did not apply (state: ${STATE:-unknown}, rc $RC). Nothing changed in the live tree unless the record says otherwise."
fi
