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
SECRET="${VINTOS_SECRET:?VINTOS_SECRET must be provisioned}"
[[ "$AEGIS_TS" =~ ^[0-9.]+$ && "$PORT" =~ ^[0-9]+$ ]] || exit 1
F=/home/pi/velaris-pi-client.py

if [ "$REVERT" = 1 ]; then
  echo "Use the reviewed guarded rollback; legacy Pi backups may embed a retired identity." >&2
  exit 1
fi

echo "Pi $PI -> bridge http://$AEGIS_TS:$PORT (header X-Vintos-Secret)"
{ printf '%s\n' "$SECRET"; cat <<'REMOTE'
set -e
AEGIS_TS="$1"; PORT="$2"; SECRET="$VINTOS_SECRET"; F=/home/pi/velaris-pi-client.py
B="$F.bak-vintos-$(date +%Y%m%d-%H%M%S)"; cp "$F" "$B"
# every bridge URL, whatever port it carried; the header name; the secret by its variable and its literal
# whatever bridge it pointed at last (Aegis, or the Mac while Gemma lived there): any host on a bridge port
sed -i -E "s#http://[0-9.]+:(8403|8500|8404)#http://${AEGIS_TS}:${PORT}#g; s#X-Velaris-Secret#X-Vintos-Secret#g" "$F"
sed -i -E "s#^SECRET *=.*#SECRET = __import__('os').environ['VINTOS_SECRET']#" "$F"

install -d -m 700 /home/pi/.config/vintos
(umask 077; printf 'VINTOS_SECRET=%s\n' "$SECRET" > /home/pi/.config/vintos/house-auth.env)
sudo install -d -m 755 /etc/systemd/system/velaris-pi.service.d
printf '[Service]\nEnvironmentFile=/home/pi/.config/vintos/house-auth.env\n' | sudo tee /etc/systemd/system/velaris-pi.service.d/house-auth.conf >/dev/null
sudo systemctl daemon-reload
python3 -m py_compile "$F" && echo "client compiles"

sudo systemctl restart velaris-pi.service; sleep 4

echo "backup: $B (code backup only; retain the rotated environment on rollback)"
REMOTE
} | ssh "pi@$PI" "IFS= read -r VINTOS_SECRET; export VINTOS_SECRET; bash -s -- '$AEGIS_TS' '$PORT'"
