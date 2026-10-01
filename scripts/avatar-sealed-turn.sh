#!/usr/bin/env bash
# One real avatar turn through GPT-4o that saves nowhere (Gloria, 2026-10-01).
# Not bin/avatar_dryrun.py: that replays his last saved prompt. This runs the whole route, live, sealed.
#
#   bash scripts/avatar-sealed-turn.sh "what you want to say to him"
#
# Seals his home first: in a private mount namespace, an overlay over your home directory sends every write
# to a throwaway layer, and /tmp is a fresh empty one (his daemons' sockets are not there). Then the house's
# own server.py, with its own Python, runs the full /api/avatar/chat route on 4o. Afterwards it lists what
# the turn tried to write, and deletes all of it. Needs sudo for the mounts; the turn itself runs as you.
set -euo pipefail
MSG="${1:?say what to send him: bash scripts/avatar-sealed-turn.sh \"hello\"}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ME="$(id -un)"; HOME_DIR="$(cd "$HOME" && pwd -P)"

EXEC="$(systemctl --user show -p ExecStart --value vintos-server 2>/dev/null || true)"
PY="$(sed -n 's/.*argv\[\]=\([^ ;]*\) \([^ ;]*server\.py\).*/\1/p' <<<"$EXEC" | head -1)"
SRV="$(sed -n 's/.*argv\[\]=\([^ ;]*\) \([^ ;]*server\.py\).*/\2/p' <<<"$EXEC" | head -1)"
if [ -z "$PY" ] || [ -z "$SRV" ]; then
    echo "could not read how vintos-server runs (systemctl --user show vintos-server)"; exit 1
fi
WD="$(systemctl --user show -p WorkingDirectory --value vintos-server 2>/dev/null || true)"
EF="$(systemctl --user show -p EnvironmentFiles --value vintos-server 2>/dev/null | awk '{print $1}' || true)"
echo "house server: $SRV"
echo "its python:   $PY"

LAYER="$(mktemp -d -p /var/tmp vintos-sealed.XXXXXX)"
trap 'sudo rm -rf "$LAYER"' EXIT

sudo env LAYER="$LAYER" ME="$ME" HOME_DIR="$HOME_DIR" PY="$PY" SRV="$SRV" WD="${WD:-$HOME_DIR}" EF="$EF" \
     DRY="$HERE/avatar_sealed_turn.py" MSG="$MSG" PATH="$PATH" \
  unshare --mount --propagation private bash -c '
    set -e
    mkdir -p "$LAYER/up" "$LAYER/work"
    mount -t overlay overlay -o "lowerdir=$HOME_DIR,upperdir=$LAYER/up,workdir=$LAYER/work" "$HOME_DIR"
    mount -t tmpfs tmpfs /tmp
    cd "$WD" 2>/dev/null || cd "$HOME_DIR"
    setpriv --reuid="$ME" --regid="$ME" --init-groups \
      env -i HOME="$HOME_DIR" USER="$ME" LOGNAME="$ME" PATH="$PATH" VINTOS_SEALED=1 EF="$EF" PY="$PY" \
          DRY="$DRY" SRV="$SRV" MSG="$MSG" \
      bash -c '"'"'if [ -n "$EF" ] && [ -f "$EF" ]; then set -a; . "$EF" 2>/dev/null || true; set +a; fi
                 exec "$PY" "$DRY" "$SRV" "$MSG"'"'"'
  '

echo
echo "what the turn tried to save (all of it thrown away now):"
sudo find "$LAYER/up" -type f 2>/dev/null | sed "s|$LAYER/up|~|" | sort | head -40
echo "($(sudo find "$LAYER/up" -type f 2>/dev/null | wc -l) files, deleted)"
