#!/usr/bin/env bash
# robot-pi-repoint.sh -- point the Pi client at Vintos's bridge instead of Velaris's. Run from Aegis, by Gloria.
#   bash robot-pi-repoint.sh [pi-address]         (default 192.168.1.89)
#   bash robot-pi-repoint.sh --revert [pi-address]
# Backs up the client first, rewrites only the bridge address, port and header name, compiles, restarts the
# client service, and tails its log. Never edits anything else on the Pi. Her LiDAR and listener services
# are not touched.
set -euo pipefail
REVERT=0
if [ "${1:-}" = "--revert" ]; then REVERT=1; shift; fi
PI="${1:-192.168.1.89}"
AEGIS_TS="$(tailscale ip -4 2>/dev/null | head -1 || true)"; AEGIS_TS="${AEGIS_TS:-100.72.225.119}"
PORT="${VINTOS_ROBOT_PORT:-8404}"
SECRET="${VINTOS_SECRET:-vintos-aegis-2026}"
F=/home/pi/velaris-pi-client.py

if [ "$REVERT" = 1 ]; then
  ssh "pi@$PI" "set -e; B=\$(ls -t $F.bak-vintos-* | head -1); cp \"\$B\" $F; python3 -m py_compile $F; sudo systemctl restart velaris-pi.service; echo reverted from \$B"
  exit 0
fi

echo "Pi $PI -> bridge http://$AEGIS_TS:$PORT (header X-Vintos-Secret)"
ssh "pi@$PI" bash -s -- "$AEGIS_TS" "$PORT" "$SECRET" <<'REMOTE'
set -e
AEGIS_TS="$1"; PORT="$2"; SECRET="$3"; F=/home/pi/velaris-pi-client.py
B="$F.bak-vintos-$(date +%Y%m%d-%H%M%S)"; cp "$F" "$B"
# every bridge URL, whatever port it carried; the header name; the secret by its variable and its literal
# whatever bridge it pointed at last (Aegis, or the Mac while Gemma lived there): any host on a bridge port
sed -i -E "s#http://[0-9.]+:(8403|8500|8404)#http://${AEGIS_TS}:${PORT}#g; s#X-Velaris-Secret#X-Vintos-Secret#g" "$F"
sed -i -E "s#^SECRET *= *['\"][^'\"]*['\"]#SECRET = \"${SECRET}\"#" "$F"
sed -i -E "s#'velaris-aegis-2026'#'${SECRET}'#g" "$F"
python3 -m py_compile "$F" && echo "client compiles"
grep -nE "AEGIS *=|X-Vintos-Secret|:${PORT}" "$F" | head -8
sudo systemctl restart velaris-pi.service; sleep 4
tail -5 /home/pi/velaris-pi.log
echo "backup: $B   (revert: bash robot-pi-repoint.sh --revert)"
REMOTE
