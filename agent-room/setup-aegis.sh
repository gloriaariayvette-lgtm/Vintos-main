#!/usr/bin/env bash
# The agent room, self-hosted on Aegis. Nothing leaves the tailnet.
#   redis (6390) <- upstash-proxy (8079) <- room-api (8787) <- the seats (agent-room-mcp / grok-seat)
#                                        <- web window (8788, tailnet)
# Run once:  bash ~/Vintos/agent-room/setup-aegis.sh      Re-run is safe (idempotent).
set -euo pipefail
say(){ printf '\033[1m%s\033[0m\n' "$*"; }
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; SRC="$HOME/agent-room"; ENVF="$HOME/.vintos/agent-room.env"
# ---------- preflight ----------
if ! command -v node >/dev/null || [ "$(node -v | sed 's/v\([0-9]*\).*/\1/')" -lt 20 ]; then
  say "node >= 20 needed; installing via nvm (user-local, touches nothing else)"
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash >/dev/null
  export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; nvm install 22 >/dev/null; nvm use 22 >/dev/null
fi
NODE="$(command -v node)"; say "node: $NODE ($(node -v))"
command -v redis-server >/dev/null || { say "installing redis-server (apt, needs sudo once)"; sudo apt-get install -y redis-server >/dev/null; sudo systemctl disable --now redis-server 2>/dev/null || true; }
command -v git >/dev/null || sudo apt-get install -y git >/dev/null
# ---------- env (token generated once) ----------
mkdir -p "$HOME/.vintos"
if [ ! -f "$ENVF" ]; then
  cat > "$ENVF" <<EOF
UPSTASH_TOKEN=$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 32)
REDIS_ADDR=127.0.0.1:6390
UPSTASH_REDIS_REST_URL=http://127.0.0.1:8079
AGENT_ROOM_SRC=$SRC
AGENT_ROOM_BASE_URL=http://127.0.0.1:8787
EOF
  chmod 600 "$ENVF"; say "wrote $ENVF"
fi
set -a; . "$ENVF"; set +a; export UPSTASH_REDIS_REST_TOKEN="$UPSTASH_TOKEN"
# ---------- the room library + web window ----------
if [ ! -d "$SRC/.git" ]; then git clone -q --depth 1 https://github.com/agent-room-alkl/agent-room.git "$SRC"; else git -C "$SRC" pull -q --ff-only || true; fi
cd "$SRC"; npm ci --no-audit --no-fund --silent
npm run build -w packages/shared --silent && npm run build -w packages/upstash-client --silent
AEGIS_IP="$(tailscale ip -4 2>/dev/null | head -1 || hostname -I | awk '{print $1}')"
say "built: library (the window is ours: $KIT/window, talks only to the room API)"
# ---------- the MCP seat package, installed once into a fixed folder (never re-downloaded mid-room) ----------
SEATDIR="$HOME/.vintos/agent-room-seat"; mkdir -p "$SEATDIR"
( cd "$SEATDIR" && { [ -f package.json ] || npm init -y >/dev/null; } && npm install --no-audit --no-fund --silent agent-room-mcp@latest )
SEATBIN="$SEATDIR/node_modules/.bin/agent-room-mcp"; [ -x "$SEATBIN" ] && say "seat installed: $SEATBIN" || { echo "seat install failed"; exit 1; }
# ---------- systemd --user units ----------
UD="$HOME/.config/systemd/user"; mkdir -p "$UD"
unit(){ cat > "$UD/$1.service" <<EOF
[Unit]
Description=agent room: $1
After=network.target $2
[Service]
EnvironmentFile=$ENVF
Environment=UPSTASH_REDIS_REST_TOKEN=$UPSTASH_TOKEN
Environment=PATH=$(dirname "$NODE"):/usr/local/bin:/usr/bin:/bin
$3
Restart=on-failure
RestartSec=2
[Install]
WantedBy=default.target
EOF
}
unit agent-room-redis ""                 "ExecStart=$(command -v redis-server) --port 6390 --bind 127.0.0.1 --save 60 1 --dir $HOME/.vintos --dbfilename agent-room.rdb --appendonly no"
unit agent-room-proxy agent-room-redis.service "Environment=PORT=8079
ExecStart=$NODE $KIT/upstash-proxy.mjs"
unit agent-room-api agent-room-proxy.service "Environment=PORT=8787
ExecStart=$NODE $KIT/room-api.mjs"
unit agent-room-web agent-room-api.service "Environment=PORT=8788
Environment=WEB_DIST=$KIT/window
Environment=ROOM_API=http://127.0.0.1:8787
ExecStart=$NODE $KIT/static.mjs"
systemctl --user daemon-reload
for u in agent-room-redis agent-room-proxy agent-room-api agent-room-web; do systemctl --user enable "$u" >/dev/null; systemctl --user restart "$u"; done   # restart, so a re-run applies unit changes
sleep 2
say "services:"; for u in agent-room-redis agent-room-proxy agent-room-api agent-room-web; do printf '  %-18s %s\n' "$u" "$(systemctl --user is-active $u)"; done
curl -s http://127.0.0.1:8787/health && echo "  room-api health ok"
# ---------- seats ----------
say ""; say "SEATS — run these once, each on the machine that runs that seat:"
echo "  Claude Code:  claude mcp add --scope user -e AGENT_ROOM_BASE_URL=http://127.0.0.1:8787 agent-room -- $SEATBIN"
echo "  Codex:        add to ~/.codex/config.toml:"
printf '                [mcp_servers.agent-room]\n                command = "%s"\n                [mcp_servers.agent-room.env]\n                AGENT_ROOM_BASE_URL = "http://127.0.0.1:8787"\n' "$SEATBIN"
echo "  Grok 4.6:     node $KIT/grok-seat.mjs --code <ROOM> --persona ~/.vintos/code-review/persona.txt --context ~/.vintos/code-review/room-grok.md"
echo "  (a seat on another tailnet machine uses http://${AEGIS_IP}:8787 instead of 127.0.0.1)"
say ""; say "WINDOW:  http://${AEGIS_IP}:8788/?code=<ROOM>   (your phone, on the tailnet: live transcript, who has the floor, minutes)"
say "SMOKE:   AGENT_ROOM_BASE_URL=http://127.0.0.1:8787 node $KIT/smoke.mjs"
