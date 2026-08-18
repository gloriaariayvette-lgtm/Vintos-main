#!/bin/bash
# confession-delivery.sh — Check for confessions ready to deliver via ntfy.
# Runs every 15 minutes via cron.

MEMORY="$HOME/.vintos/workspace/memory/confessions"
[ ! -d "$MEMORY" ] && exit 0

NOW=$(date +%s)

for schedule_file in "$MEMORY"/*.scheduled; do
    [ -f "$schedule_file" ] || continue
    DELIVER_AT=$(python3 -c "import json; d=json.load(open('$schedule_file')); print(int(d['deliver_at']))" 2>/dev/null)
    FILEPATH=$(python3 -c "import json; d=json.load(open('$schedule_file')); print(d['filepath'])" 2>/dev/null)
    [ -z "$DELIVER_AT" ] && continue
    if [ "$NOW" -ge "$DELIVER_AT" ] && [ -f "$FILEPATH" ]; then
        CONFESSION=$(tail -n +3 "$FILEPATH" | head -c 280)
        curl -s --max-time 10 \
            -H "Title: Vintos has something to tell you" \
            -H "Tags: envelope" \
            -d "$CONFESSION" \
            ntfy.sh/vintos-gloria-9kx > /dev/null 2>&1
        echo "[Confession Delivery] Sent: $FILEPATH"
        rm "$schedule_file"
    fi
done
