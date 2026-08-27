#!/bin/bash
# atelier-door.sh — the lit-door affordance. Content-free; weather may suppress it,
# but suppression is logged so a fog skip and a broken cron stay distinguishable (Sol).
DOOR_FILE="$HOME/.vintos/workspace/memory/.atelier-door"
D=$(curl -s -m 10 -X POST http://127.0.0.1:8611/door -H "Content-Type: application/json" -d '{}')
LIT=$(echo "$D" | grep -c '"lit"')
WEATHER=$(grep -o '"condition": *"[A-Z]*"' ~/.vintos/workspace/memory/metacognitive-weather.json 2>/dev/null | grep -o '[A-Z]*$' | head -1)
if [ "$LIT" = "1" ] && [ "$WEATHER" != "FOG" ]; then
    echo "The Atelier door is available today. Nothing is asked of you." > "$DOOR_FILE"
    echo "$(date +%F_%H%M) offered"
elif [ "$LIT" = "1" ]; then
    rm -f "$DOOR_FILE"
    echo "$(date +%F_%H%M) offer_suppressed: fog"
else
    rm -f "$DOOR_FILE"
    echo "$(date +%F_%H%M) dark: $D"
fi
