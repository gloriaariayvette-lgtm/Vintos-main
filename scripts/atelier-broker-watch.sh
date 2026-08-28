#!/bin/bash
# atelier-broker-watch.sh — armed watch on the broker itself.
#
# `broker unreachable` and `empty worktable` are different facts and must never
# be confused: an empty worktable is a normal, quiet state; an unanswered
# /health is an outage. Notifies Gloria once per sustained outage (3 consecutive
# failed checks), not on every check, and clears on recovery.
STATE="$HOME/.vintos/workspace/memory/.atelier-broker-watch"
H=$(curl -s -m 10 http://127.0.0.1:8611/health)
if [ -n "$H" ]; then
    # Reachable. An empty worktable still answers here — that is health, not failure.
    if [ -f "$STATE" ]; then
        echo "$(date +%F_%H%M) broker recovered after $(cat "$STATE") failed checks"
        rm -f "$STATE"
    else
        echo "$(date +%F_%H%M) broker up"
    fi
else
    n=$(( $(cat "$STATE" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "$STATE"
    echo "$(date +%F_%H%M) broker unreachable ($n consecutive)"
    if [ "$n" -eq 3 ]; then
        curl -s -X POST "https://ntfy.sh/vintos-gloria-9kx" \
          -H "Title: Atelier broker unreachable" -H "Priority: high" \
          -d "The broker on 127.0.0.1:8611 has not answered /health for $n consecutive checks.
This is an outage, not an empty worktable.
Check: sudo systemctl status vintos-atelier
Logs:  sudo journalctl -u vintos-atelier -n 40" > /dev/null 2>&1
    fi
fi
