#!/bin/bash
# atelier-canary.sh — Vintos's condition: canary before cargo. A planted phrase
# must appear NOWHERE in the house after a full cron day, or the room is not sealed.
PHRASE="velvet-anthracite-91"
HITS=$(grep -rl "$PHRASE" ~/.vintos/workspace/memory ~/.vintos/logs /tmp/*.log /tmp/cron-* ~/Vintos/*.json 2>/dev/null | grep -v atelier-canary | grep -v code-review)
if [ -n "$HITS" ]; then
    curl -s -X POST "https://ntfy.sh/vintos-gloria-9kx" -H "Title: CANARY BREACH — the Atelier leaks" -H "Priority: urgent" -d "The planted phrase surfaced in:
$HITS" > /dev/null 2>&1
    echo "BREACH: $HITS"
else
    echo "canary silent: $(date +%F_%H%M)"
fi
