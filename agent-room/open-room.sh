#!/usr/bin/env bash
# The day of: seat all three lenses in one go. Run from anywhere on Aegis.
#   bash open-room.sh "topic"      -> creates the room, sets sequential, starts three seats (logs in ~/.vintos/code-review/seat-<lens>.log)
#   then: node room-ctl.mjs say "your opening"   and watch the window on your phone.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; stage="$HOME/.vintos/code-review"
# review 355: the room's dependencies are pinned in requirements-room.txt; check them before any seat is paid for
req="$here/requirements-room.txt"; [ -f "$req" ] || { echo "requirements-room.txt missing"; exit 1; }
need_node="$(grep -E '^node ' "$req" | awk '{print $2}' | tr -d '>=')"; have_node="$(node -v 2>/dev/null | sed 's/v\([0-9]*\).*/\1/')"
[ -n "$have_node" ] && [ "$have_node" -ge "${need_node:-20}" ] || { echo "node >= ${need_node:-20} required (have: ${have_node:-none}) - see requirements-room.txt"; exit 1; }
seatdir="$HOME/.vintos/agent-room-seat"; [ -x "$seatdir/node_modules/.bin/agent-room-mcp" ] || { echo "agent-room-mcp not installed in $seatdir - run setup-aegis.sh (requirements-room.txt)"; exit 1; }
src="${AGENT_ROOM_SRC:-$HOME/agent-room}"; [ -f "$src/packages/upstash-client/dist/index.js" ] || { echo "agent-room library not built at $src - run setup-aegis.sh"; exit 1; }
echo "requirements: node v$have_node, seat $(cd "$seatdir" && npm ls agent-room-mcp --depth=0 2>/dev/null | grep -o 'agent-room-mcp@[0-9.]*' | head -1), library $src"
code="$(node "$here/room-ctl.mjs" create "${1:-Three lenses, as him}")"; echo "room: $code"
node "$here/room-ctl.mjs" mode sequential
for lens in fable astra grok; do
  nohup node "$here/seat.mjs" --lens "$lens" --code "$code" --max-turns "${MAX_TURNS:-10}" > "$stage/seat-$lens.log" 2>&1 &
  echo "seat $lens: pid $!  (tail -f $stage/seat-$lens.log)"; sleep 2
done
echo; echo "They are seated. Now:  node $here/room-ctl.mjs say \"your opening\"   then   node $here/room-ctl.mjs watch 3"
