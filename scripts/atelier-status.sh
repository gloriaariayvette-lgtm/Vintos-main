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
# 7. is he still being offered the room?
say "  scheduled: $(crontab -l 2>/dev/null | grep -c 'atelier-visit') daily visit cron(s)"
