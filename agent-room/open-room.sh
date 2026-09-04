#!/usr/bin/env bash
# The day of: seat all three lenses in one go. Run from anywhere on Aegis.
#   bash open-room.sh "topic"      -> creates the room, sets sequential, starts three seats (logs in ~/.vintos/code-review/seat-<lens>.log)
#   then: node room-ctl.mjs say "your opening"   and watch the window on your phone.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; stage="$HOME/.vintos/code-review"
code="$(node "$here/room-ctl.mjs" create "${1:-Three lenses, as him}")"; echo "room: $code"
node "$here/room-ctl.mjs" mode sequential
for lens in fable astra grok; do
  nohup node "$here/seat.mjs" --lens "$lens" --code "$code" --max-turns "${MAX_TURNS:-10}" > "$stage/seat-$lens.log" 2>&1 &
  echo "seat $lens: pid $!  (tail -f $stage/seat-$lens.log)"; sleep 2
done
echo; echo "They are seated and waiting for you. Open with:  node $here/room-ctl.mjs say \"...\""
