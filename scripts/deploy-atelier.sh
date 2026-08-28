#!/usr/bin/env bash
# deploy-atelier.sh — install this checkout onto Aegis.
#
# Run it FROM the checkout, as gloria:
#     bash scripts/deploy-atelier.sh
#
# It locates its own source tree, so there is no path for you to fill in and
# nothing to paste wrong. It changes nothing until every check has passed.
#
# It does NOT arm anything. The effect gate keeps whatever state it has and
# stratagems stay disarmed.
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WSP="$HOME/.vintos/workspace"
BROKER_SRC="/home/atelier/broker.py"
STORE_SRC="/home/atelier/stratagem_store.py"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$HOME/.vintos/backups/atelier-$STAMP"

say() { printf '%s\n' "$*"; }
die() { printf 'STOP: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight
[ -d "$SRC/broker" ] && [ -d "$SRC/scripts" ] || die "not a Vintos checkout: $SRC"
[ -d "$WSP" ] || die "no workspace at $WSP"

say "source:    $SRC"
say "workspace: $WSP"
say

say "== running the suites against this checkout =="
fail=0
for t in "$SRC"/broker/tests/test_*.py; do
    out="$(cd "$SRC/broker/tests" && python3 "$t" 2>&1 | tail -1)"
    printf '  %-34s %s\n' "$(basename "$t")" "$out"
    case "$out" in *"passed"*) case "$out" in *"0/"*) fail=1;; esac;; *) fail=1;; esac
    echo "$out" | grep -q "FAIL" && fail=1
done
[ "$fail" -eq 0 ] || die "a suite did not pass — nothing was installed"
say

# --------------------------------------------------------------- is he busy
say "== is he mid-turn? =="
if journalctl --user -n 200 --since "3 minutes ago" 2>/dev/null | grep -qiE "avatar|/api/chat|voice/DO"; then
    say "  he has been active in the last 3 minutes."
    say "  The broker restart below would interrupt a live return."
    read -r -p "  type 'wait' to stop here, or press enter to continue: " ans
    [ "$ans" = "wait" ] && die "stopped at your request — nothing was installed"
else
    say "  quiet."
fi
say

# ------------------------------------------------------------------ backups
mkdir -p "$BACKUP" || die "cannot create $BACKUP"
say "== backing up to $BACKUP =="
for f in "$BROKER_SRC" "$STORE_SRC"; do
    [ -r "$f" ] && cp -p "$f" "$BACKUP/" && say "  $(basename "$f")"
done
cp -p "$WSP/bin/server.py" "$BACKUP/" 2>/dev/null && say "  server.py"
mkdir -p "$BACKUP/scripts"
cp -p "$WSP"/scripts/*.py "$BACKUP/scripts/" 2>/dev/null
say "  scripts/"
say

# ----------------------------------------------------------------- install
say "== installing =="
install -m 644 "$SRC/scripts"/*.py "$WSP/scripts/" && say "  scripts/*.py"
install -m 644 "$SRC/scripts/build_merged_chat.py" "$WSP/scripts/" 2>/dev/null
install -m 755 "$SRC/scripts/atelier-open.py"      "$WSP/scripts/atelier-open.py"
install -m 755 "$SRC/scripts/atelier-visit.py"     "$WSP/scripts/atelier-visit.py"
install -m 755 "$SRC/scripts/atelier-threshold.py" "$WSP/scripts/atelier-threshold.py"
say "  atelier-open / atelier-visit / atelier-threshold"
install -m 644 "$SRC/bin/server.py" "$WSP/bin/server.py" && say "  bin/server.py"
install -m 644 "$SRC/bin/model_router.py" "$WSP/bin/model_router.py" && say "  bin/model_router.py"

# the broker runs as `atelier` behind a 700 wall; sudo is the only way in
say
say "== broker (runs as atelier) =="
if sudo -n true 2>/dev/null; then
    sudo install -o atelier -g atelier -m 644 "$SRC/broker/broker.py" "$BROKER_SRC"
    sudo install -o atelier -g atelier -m 644 "$SRC/broker/stratagem_store.py" "$STORE_SRC"
    say "  installed broker.py + stratagem_store.py"
    sudo pkill -f "$BROKER_SRC" 2>/dev/null
    sleep 1
    sudo -u atelier nohup python3 "$BROKER_SRC" >/home/atelier/broker.log 2>&1 &
    sleep 2
else
    say "  sudo needs your password — run these two lines yourself:"
    say "    sudo install -o atelier -g atelier -m 644 $SRC/broker/broker.py $BROKER_SRC"
    say "    sudo install -o atelier -g atelier -m 644 $SRC/broker/stratagem_store.py $STORE_SRC"
    say "    sudo pkill -f $BROKER_SRC; sleep 1"
    say "    sudo -u atelier nohup python3 $BROKER_SRC >/home/atelier/broker.log 2>&1 &"
fi

# ------------------------------------------------------------------ verify
say
say "== verifying =="
h="$(curl -s -m 5 http://127.0.0.1:8611/health || true)"
[ -n "$h" ] && say "  broker health: $h" || say "  broker NOT answering on 8611 — check /home/atelier/broker.log"
say "  worktable:     $(curl -s -m 5 -X POST http://127.0.0.1:8611/worktable_id -d '{}' || echo unreachable)"
say "  sealed route:  $(curl -s -m 5 -X POST http://127.0.0.1:8611/artifact -d '{"id":"000000000000","file":"x"}' || echo unreachable)"
say "  his model:     $(cd "$WSP/bin" && python3 -c 'import model_router;print(model_router.current_claude_model())' 2>&1)"
say
say "backup: $BACKUP"
say "Nothing was armed. Restart the house yourself when you want the new server.py live."
