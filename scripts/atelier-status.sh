#!/usr/bin/env bash
# atelier-status.sh — is his room functional? Content-free: it reports THAT
# things work and when he last used it, never WHAT he is making.
B="http://127.0.0.1:8611"
say() { printf '%s\n' "$*"; }

say "== Atelier status =="
# 1. the broker service
if systemctl is-active --quiet vintos-atelier 2>/dev/null; then
    say "  service:   vintos-atelier active"
else
    say "  service:   NOT active — run: sudo systemctl restart vintos-atelier"
fi
# 2. reachable + worktable occupied (content-free)
h="$(curl -s -m 5 "$B/health" 2>/dev/null)"
[ -n "$h" ] && say "  broker:    up  $h" || say "  broker:    NOT answering on 8611"
# 3. the seal still bites
sealed="$(curl -s -m 5 -X POST "$B/artifact" -H 'Content-Type: application/json' \
          -d '{"id":"000000000000","file":"x.md"}' 2>/dev/null)"
case "$sealed" in
  *capability*) say "  seal:      holding (sealed content refused without a visit)";;
  *)            say "  seal:      CHECK — $sealed";;
esac
# 4. door state right now (content-free: lit/dark and his own reason)
say "  door:      $(curl -s -m 5 -X POST "$B/door" -H 'Content-Type: application/json' -d '{}' 2>/dev/null)"
# 5. when he last actually used the room (content-free health facts)
last="$(sudo tail -50 /home/atelier/atelier/health.jsonl 2>/dev/null \
        | grep -E 'return happened|door was lit|a project exists' | tail -1)"
if [ -n "$last" ]; then
    say "  last activity: $last"
else
    say "  last activity: (none recorded)"
fi
# 6. content-free proof that real work exists on the worktable
wt="$(curl -s -m 5 -X POST "$B/worktable_id" -H 'Content-Type: application/json' -d '{}' 2>/dev/null | sed -n 's/.*"id": *"\([^"]*\)".*/\1/p')"
if [ -n "$wt" ]; then
    man="$(curl -s -m 5 -X POST "$B/manifest" -H 'Content-Type: application/json' -d "{\"id\":\"$wt\"}" 2>/dev/null)"
    say "  work made:   $man"
    case "$man" in
      *'"all_real": true'*)  say "               -> every artifact is a real, non-empty file";;
      *'"count": 0'*)        say "               -> nothing made on this project yet";;
      *'"all_real": false'*) say "               -> CHECK: an artifact is empty (claimed but not written)";;
    esac
fi
# 6b. everything he has made, every project (content-free: counts and dates). "work made" above is only the project
# on the worktable now; a kept project leaves the table, so a fresh one read "nothing made" while his work stood
# beside it (2026-10-14).
all="$(curl -s -m 5 -X POST "$B/projects" -H 'Content-Type: application/json' -d '{}' 2>/dev/null)"
printf '%s' "$all" | python3 -c '
import json, sys
try: d = json.load(sys.stdin)
except Exception: print("  all work:    (the broker did not list projects)"); raise SystemExit
rows = [r for r in (d.get("projects") or []) if isinstance(r, dict)]
made = [r for r in rows if int(r.get("artifact_count") or 0) > 0]
total = sum(int(r.get("artifact_count") or 0) for r in rows)
print("  all work:    %d pieces across %d projects (%d with work)" % (total, len(rows), len(made)))
for r in made[-5:]:
    print("               %s  %-8s %2d pieces  %s" % (r.get("id"), str(r.get("state", "")).lower(), int(r.get("artifact_count") or 0),
                                                str(r.get("kept_at") or r.get("revealed_at") or r.get("started_at") or "")[:16]))
'
# 6c. what he said at the door, the last five mornings
say "  door answers: $(grep -oE 'he answered [A-Z]+' /tmp/atelier-visit.log 2>/dev/null | tail -5 | sed 's/he answered //' | tr '\n' ' ')"
# 7. is he still being offered the room?
say "  scheduled: $(crontab -l 2>/dev/null | grep -c 'atelier-visit') daily visit cron(s)"
