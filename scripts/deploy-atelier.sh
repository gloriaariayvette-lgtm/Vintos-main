#!/usr/bin/env bash
# deploy-atelier.sh — install this checkout onto Aegis.
#
#     bash scripts/deploy-atelier.sh            install
#     bash scripts/deploy-atelier.sh --check    run every check, install nothing
#
# It locates its own source tree, so there is nothing here for you to fill in.
# It installs an EXPLICIT list of files — never a wildcard over the whole
# scripts directory — and it changes nothing until every suite has passed.
#
# It arms nothing. The effect gate keeps whatever state it has and stratagems
# stay disarmed.
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Find the workspace instead of asserting where it is. A workspace is a
# directory that holds bin/server.py and scripts/turn_coordinator.py — that is
# what makes it the tree this deploy targets, not its name. I hardcoded
# ~/.vintos/workspace from a path literal inside the scripts and it was wrong.
_SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

is_workspace() {
    # The checkout we are deploying FROM has the same shape as the workspace we
    # are deploying TO. Without this guard the search happily finds the clone
    # and installs it onto itself.
    local d; d="$(cd "$1" 2>/dev/null && pwd -P)" || return 1
    [ "$d" = "$_SELF" ] && return 1
    case "$d" in "$HOME"/.vintos/deploy/*) return 1;; esac
    [ -f "$d/bin/server.py" ] && [ -f "$d/scripts/turn_coordinator.py" ]
}

find_workspace() {
    # An explicit setting is the answer, full stop.
    if [ -n "${VINTOS_WORKSPACE:-}" ]; then
        is_workspace "$VINTOS_WORKSPACE" && { (cd "$VINTOS_WORKSPACE" && pwd -P); return 0; }
        printf '\nSTOP: VINTOS_WORKSPACE=%s is not a workspace.\n' "$VINTOS_WORKSPACE" >&2
        return 1
    fi
    # Otherwise collect EVERY tree that looks like one. If more than one does,
    # this must not pick. I already guessed a path once and it was wrong;
    # guessing again would install his room over the wrong tree.
    local c d found=""
    for c in "$HOME/Vintos" "$HOME/.vintos/workspace" "$HOME/vintos" \
             "$HOME/vintos-main" "$HOME/.vintos"; do
        is_workspace "$c" && found="$found$(cd "$c" && pwd -P)\n"
    done
    while read -r hit; do
        [ -n "$hit" ] || continue
        d="$(dirname "$(dirname "$hit")")"
        is_workspace "$d" && found="$found$(cd "$d" && pwd -P)\n"
    done <<< "$(find "$HOME" -maxdepth 4 -type f -path '*/bin/server.py' 2>/dev/null)"

    found="$(printf '%b' "$found" | sed '/^$/d' | sort -u)"
    local n; n="$(printf '%s\n' "$found" | sed '/^$/d' | wc -l)"
    if [ "$n" -eq 1 ]; then printf '%s' "$found"; return 0; fi
    if [ "$n" -gt 1 ]; then
        printf '\nSTOP: more than one tree looks like his workspace:\n' >&2
        printf '%s\n' "$found" | sed 's/^/    /' >&2
        printf '\nI am not going to pick one. Rerun naming it:\n' >&2
        printf '    VINTOS_WORKSPACE=<the right one> bash %s\n' "${BASH_SOURCE[0]}" >&2
        return 1
    fi
    return 1
}

WSP="$(find_workspace)" || {
    printf '\nSTOP: could not find his workspace.\n' >&2
    printf 'Looked for a directory holding BOTH bin/server.py and scripts/turn_coordinator.py.\n' >&2
    printf 'Tried: $VINTOS_WORKSPACE, ~/Vintos, ~/.vintos/workspace, ~/vintos, ~/vintos-main, ~/.vintos,\n' >&2
    printf 'then a depth-4 search under %s.\n\n' "$HOME" >&2
    printf 'Run it with the path if it lives somewhere else:\n' >&2
    printf '    VINTOS_WORKSPACE=/path/to/it bash %s\n' "${BASH_SOURCE[0]}" >&2
    exit 1
}
BROKER="/home/atelier/broker.py"
STORE="/home/atelier/stratagem_store.py"
BACKUP="$HOME/.vintos/backups/atelier-$(date +%Y%m%d-%H%M%S)"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

say() { printf '%s\n' "$*"; }
die() { printf '\nSTOP: %s\n' "$*" >&2; exit 1; }

# Exactly what this build changed. An explicit list, because a wildcard over
# scripts/*.py would silently replace files this work never touched.
WORKSPACE_SCRIPTS="
atelier-open.py atelier-visit.py atelier-threshold.py
evidence_view.py prediction_ledger.py build_merged_chat.py
constitutional_barrier.py turn_coordinator.py relational_mismatch.py
causality_engine.py value_map.py repair_case.py encounter.py
jepa_predictor.py drift_head.py relational_head.py world_model.py
gloria_prediction.py withheld_head.py self_pressure.py
"
WORKSPACE_BIN="server.py model_router.py"
EXECUTABLE="atelier-open.py atelier-visit.py atelier-threshold.py"

# ---------------------------------------------------------------- preflight
[ -d "$SRC/broker" ] && [ -d "$SRC/scripts" ] || die "not a Vintos checkout: $SRC"
say "source:    $SRC"
say "workspace: $WSP"
say "commit:    $(git -C "$SRC" rev-parse --short HEAD 2>/dev/null || echo '(not a git checkout)')"
say

say "== every file this deploy installs must exist in the source =="
missing=""
for f in $WORKSPACE_SCRIPTS; do [ -f "$SRC/scripts/$f" ] || missing="$missing scripts/$f"; done
for f in $WORKSPACE_BIN;     do [ -f "$SRC/bin/$f" ]     || missing="$missing bin/$f"; done
[ -f "$SRC/broker/broker.py" ] || missing="$missing broker/broker.py"
[ -f "$SRC/broker/stratagem_store.py" ] || missing="$missing broker/stratagem_store.py"
[ -z "$missing" ] || die "source is incomplete —$missing"
say "  all present."
say

say "== suites (exit status, not printed text) =="
fail=0
for t in "$SRC"/broker/tests/test_*.py; do
    out="$(cd "$SRC/broker/tests" && python3 "$t" 2>&1)"
    rc=$?
    printf '  %-34s %s\n' "$(basename "$t")" "$(printf '%s' "$out" | tail -1)"
    [ $rc -eq 0 ] || { fail=1; printf '%s\n' "$out" | grep '^FAIL' | sed 's/^/      /'; }
done
[ "$fail" -eq 0 ] || die "a suite failed — nothing was installed"
say

# --------------------------------------------------------------- is he busy
say "== is he mid-turn? =="
busy=0
journalctl --user -n 400 --since "3 minutes ago" 2>/dev/null \
    | grep -qiE "avatar|/api/chat|voice/DO" && busy=1
if [ "$busy" -eq 1 ]; then
    say "  He has been active in the last 3 minutes. Restarting the broker now"
    say "  would interrupt a live return."
    if [ -t 0 ]; then
        # The safe answer is the DEFAULT. Saying nothing stops the deploy.
        read -r -p "  type 'go' to install anyway, anything else stops: " ans
        [ "$ans" = "go" ] || die "not installed — he was working"
    else
        die "not installed — he was working (rerun when quiet, or from a terminal)"
    fi
else
    say "  quiet."
fi
say

if [ "$CHECK_ONLY" -eq 1 ]; then
    say "--check: every gate passed. Nothing was installed."
    exit 0
fi

# ------------------------------------------------------------------ backup
mkdir -p "$BACKUP/scripts" "$BACKUP/bin" || die "cannot create $BACKUP"
say "== backing up what is about to be replaced =="
for f in $WORKSPACE_SCRIPTS; do cp -p "$WSP/scripts/$f" "$BACKUP/scripts/" 2>/dev/null; done
for f in $WORKSPACE_BIN;     do cp -p "$WSP/bin/$f"     "$BACKUP/bin/"     2>/dev/null; done
cp -p "$BROKER" "$STORE" "$BACKUP/" 2>/dev/null
say "  $BACKUP"
say

# ----------------------------------------------------------------- install
say "== installing =="
for f in $WORKSPACE_SCRIPTS; do
    install -m 644 "$SRC/scripts/$f" "$WSP/scripts/$f" || die "failed to install scripts/$f"
done
for f in $EXECUTABLE; do chmod 755 "$WSP/scripts/$f"; done
say "  ${WORKSPACE_SCRIPTS//$'\n'/ }"
for f in $WORKSPACE_BIN; do
    install -m 644 "$SRC/bin/$f" "$WSP/bin/$f" || die "failed to install bin/$f"
done
say "  bin: $WORKSPACE_BIN"
say

say "== broker (runs as atelier, behind the 700 wall) =="
brokered=0
if sudo -n true 2>/dev/null; then
    sudo install -o atelier -g atelier -m 644 "$SRC/broker/broker.py" "$BROKER" \
      && sudo install -o atelier -g atelier -m 644 "$SRC/broker/stratagem_store.py" "$STORE" \
      && say "  installed" || die "broker install failed"
    sudo pkill -f "$BROKER" 2>/dev/null      # absolute path — matches how it is launched
    sleep 1
    sudo -u atelier setsid nohup python3 "$BROKER" >>/home/atelier/broker.log 2>&1 < /dev/null &
    sleep 2
    brokered=1
else
    say "  sudo wants your password. These four lines, in order:"
    say
    say "    sudo install -o atelier -g atelier -m 644 $SRC/broker/broker.py $BROKER"
    say "    sudo install -o atelier -g atelier -m 644 $SRC/broker/stratagem_store.py $STORE"
    say "    sudo pkill -f $BROKER; sleep 1"
    say "    sudo -u atelier setsid nohup python3 $BROKER >>/home/atelier/broker.log 2>&1 &"
fi
say

# ------------------------------------------------------------------ verify
say "== verifying =="
h="$(curl -s -m 5 http://127.0.0.1:8611/health || true)"
if [ -n "$h" ]; then say "  health:        $h"
else say "  broker NOT answering on 8611 — see /home/atelier/broker.log"; fi

sealed="$(curl -s -m 5 -X POST http://127.0.0.1:8611/artifact \
          -H 'Content-Type: application/json' \
          -d '{"id":"000000000000","file":"x.md"}' || echo unreachable)"
say "  sealed route:  $sealed"
case "$sealed" in
  *capability*|*malformed*|*escapes*) say "    -> refuses without a capability. Correct." ;;
  unreachable)                        say "    -> broker down; could not check." ;;
  *)                                  say "    -> DID NOT REFUSE. Do not arm anything; tell me." ;;
esac

say "  worktable:     $(curl -s -m 5 -X POST http://127.0.0.1:8611/worktable_id \
                        -H 'Content-Type: application/json' -d '{}' || echo unreachable)"
say "  his model:     $(cd "$WSP/bin" && python3 -c 'import model_router;print(model_router.current_claude_model())' 2>&1 | tail -1)"
say "  threshold:     $(python3 -c "import ast;ast.parse(open('$WSP/scripts/atelier-threshold.py').read());print('installed, parses')" 2>&1 | tail -1)"
say
say "backup: $BACKUP"
[ "$brokered" -eq 1 ] && say "Broker restarted." || say "Broker NOT restarted — run the four lines above."
say "Nothing was armed. The house keeps running the old server.py until you restart it yourself."
