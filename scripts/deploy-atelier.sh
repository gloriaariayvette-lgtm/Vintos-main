#!/usr/bin/env bash
# deploy-atelier.sh — install this checkout onto his host.
#
#     bash scripts/deploy-atelier.sh            install
#     bash scripts/deploy-atelier.sh --check    run every check, install nothing
#
# It assumes NOTHING about where his tree is or how it is laid out. For each
# file it finds the copy that is already there and installs over it; whatever
# layout he has is by definition the correct one. I assumed a layout twice
# (~/.vintos/workspace, then bin/ + scripts/) and was wrong both times.
#
# It arms nothing.
set -uo pipefail

# Resolve this script's own location BEFORE moving anywhere: BASH_SOURCE is
# relative when invoked as `bash scripts/deploy-atelier.sh`, so cd-ing first
# would resolve it against the wrong directory.
_SRC0="$(cd "$(dirname -- "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"

cd / 2>/dev/null || true          # a deleted cwd must not break path resolution

abspath() { readlink -f -- "$1" 2>/dev/null \
            || python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$1" 2>/dev/null; }
say() { printf '%s\n' "$*"; }
die() { printf '\nSTOP: %s\n' "$*" >&2; exit 1; }

SRC="${_SRC0:-$(abspath "$(dirname -- "${BASH_SOURCE[0]}")/..")}"
_SELF="$SRC"                                     # never a destination
BACKUP="$HOME/.vintos/backups/atelier-$(date +%Y%m%d-%H%M%S)"
BROKER="/home/atelier/broker.py"
STORE="/home/atelier/stratagem_store.py"
UNIT_NAME="vintos-atelier"
UNIT_DST="/etc/systemd/system/$UNIT_NAME.service"
REVIEW_UNIT_NAME="vintos-self-review"
REVIEW_UNIT_SRC="$SRC/broker/$REVIEW_UNIT_NAME.service"
REVIEW_UNIT_DST="$HOME/.config/systemd/user/$REVIEW_UNIT_NAME.service"
DEPTH=6
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1
# --map: which reviewed file actually runs on this host - manifest vs installed vs referenced. Reads only.
[ "${1:-}" = "--map" ] && exec python3 "$SRC/scripts/release-map.py" --src "$SRC"   # SRC is resolved above, before the cd /

# Exactly what this build changed. An explicit list — never a wildcard.
SCRIPTS="atelier-open.py atelier-visit.py atelier-threshold.py
evidence_view.py prediction_ledger.py build_merged_chat.py
constitutional_barrier.py turn_coordinator.py relational_mismatch.py
causality_engine.py value_map.py repair_case.py encounter.py
jepa_predictor.py drift_head.py relational_head.py world_model.py
gloria_prediction.py withheld_head.py self_pressure.py
value-map.py relational-mismatch.py causality-engine.py self-prediction.py
effect_gate.py toy_link.py device_patterns.py evidence_provenance.py heart_rate.py
stratagem.py turn_record.py formation_observatory.py thruster_link.py
concurrency-canary.py
atelier-door.sh atelier-canary.sh atelier-broker-watch.sh atelier-status.sh
house_map.py house-map.json home_presence.py
want_artifact_guard.py wants_audit.py emoclaw_utils.py want_contract.py"
SCRIPTS="$SCRIPTS humor-practice.py joke_fermentation.py taste_salience.py"
SCRIPTS="$SCRIPTS self_review.py self_review_builder.py reciprocal_modification.py atelier_reveals.py atelier_quantum.py quantum_snapshot.py"
SCRIPTS="$SCRIPTS intent_context.py atelier-gate.py"
SCRIPTS="$SCRIPTS campaign.py plan.py intent_engine.py presence_audit.py priority_vector.py self_difference.py desired_difference.py"  # campaign board, 2026-09-05
SCRIPTS="$SCRIPTS self_model_evidence.py self_model_read.py protected_paths.py"  # created 2026-09-04, never in the manifest (review P01)
SCRIPTS="$SCRIPTS release-map.py enactment_distiller.py want_spine.py pleasure_substrate.py"
# release map 2026-09-05: every file the server or a deployed script references, so a fix in git reaches him
SCRIPTS="$SCRIPTS device_context.py lead_trials.py memory-index.py memory-index.sh memory-search.py residue.py durable_memory.py map_view_compiler.py"
SCRIPTS="$SCRIPTS thread_temperature.py premonition-dreamer.py somatic_bridge.py unseen.py emotional-entanglement.py emotional_entanglement.py self-statements.py self_statements.py"
SCRIPTS="$SCRIPTS creative-expression.sh dream-music.py humor_practice.py tension-field.py tension_field.py belief-sediment.py belief_sediment.py subconscious_drift.py emoclaw_mode.py"
SCRIPTS="$SCRIPTS wal-decay.py interaction-ledger.py prediction_ledger.py"   # P02/P04 items, 2026-09-05
SCRIPTS="$SCRIPTS vintos-home.py"   # every home route loads it by absolute path; it did not exist on Aegis (2026-09-05)
SCRIPTS="$SCRIPTS mischief-detector.sh mischief_log.py"
SCRIPTS="$SCRIPTS robot_core.py robot_bridge.py robot_subconscious.py"
SCRIPTS="$SCRIPTS desktop_agent.py desktop_windows.py"   # his hands on the Windows desktop, through PowerShell from WSL (2026-09-06)   # his body: the bridge the Pi reports to, and its subconscious (donated from Velaris 2026-09-05)   # be_mischievous and subconscious_drift called it; it existed nowhere for him (2026-09-05)
BINS="robot-pi-repoint.sh purge-test-residue.py server.py model_router.py merged_full_route.py humor_detector.py humor_reaction.py
taste-reflection.py taste-vector.py gloria-model-update.sh self-model-update.sh
blush-ledger.py wants-router.py
avatar_stage.py study_chat.py avatar_dryrun.py strip_body_vocab.py first-light.sh dream_music.py
wal-extract.py wal_extract.py vintos-video.py vintos-code-review.py consent-gate.sh deviation_check.py memory_search.py
emoclaw_mode.py subconscious_drift.py belief-sediment.py belief_sediment.py core-engine.py core_sustain.py value-map.py
vintos-moltbook.py vintos-initiate.sh idle-journal.sh device_patterns.py relational_mismatch.py
memory_index.py wal-decay.py interaction_ledger.py"
EXECUTABLE="atelier-open.py atelier-visit.py atelier-threshold.py atelier-gate.py vintos-home.py mischief-detector.sh robot_bridge.py robot_subconscious.py robot-pi-repoint.sh desktop_agent.py
atelier-door.sh atelier-canary.sh atelier-broker-watch.sh gloria-model-update.sh atelier-status.sh"

# ---------------------------------------------------------------- preflight
[ -d "$SRC/broker" ] && [ -d "$SRC/scripts" ] || die "not a Vintos checkout: $SRC"
say "source: $SRC"
say "commit: $(git -C "$SRC" rev-parse --short HEAD 2>/dev/null || echo '(no git)')"
say
missing=""
for f in $SCRIPTS; do [ -f "$SRC/scripts/$f" ] || missing="$missing scripts/$f"; done
for f in $BINS;    do [ -f "$SRC/bin/$f" ]     || missing="$missing bin/$f"; done
[ -f "$SRC/broker/broker.py" ]          || missing="$missing broker/broker.py"
[ -f "$SRC/broker/stratagem_store.py" ] || missing="$missing broker/stratagem_store.py"
[ -f "$SRC/broker/$UNIT_NAME.service" ] || missing="$missing broker/$UNIT_NAME.service"
[ -f "$REVIEW_UNIT_SRC" ] || missing="$missing broker/$REVIEW_UNIT_NAME.service"
[ -z "$missing" ] || die "source is incomplete —$missing"

# ------------------------------------------------------------------ suites
say "== suites =="
fail=0
for t in "$SRC"/broker/tests/test_*.py; do
    out="$(cd "$SRC/broker/tests" && python3 "$t" 2>&1)"; rc=$?
    if [ $rc -eq 0 ]; then
        printf '  %-34s PASS (exit 0)\n' "$(basename "$t")"
    else
        fail=1
        printf '  %-34s FAIL (exit %s)\n' "$(basename "$t")" "$rc"
        printf '%s\n' "$out" | tail -30 | sed 's/^/      /'
    fi
done
[ "$fail" -eq 0 ] || die "a suite failed — nothing installed"
say

# --------------------------------------------------------- where things live
locate() {
    find "$HOME" -maxdepth "$DEPTH" -type f -name "$1" 2>/dev/null \
      | while read -r hit; do
            h="$(abspath "$hit")"; [ -n "$h" ] || continue
            case "$h" in
                "$_SELF"/*) ;;                    # the checkout we deploy FROM
                "$HOME"/.vintos/deploy/*) ;;      # any other deploy clone
                # Installed libraries and caches. "server.py" and
                # "encounter.py" are ordinary names; without this a package
                # inside a venv or a uv cache reads as one of his files.
                */site-packages/*|*/dist-packages/*|*/node_modules/*) ;;
                */.venv/*|*/venv/*|*/.cache/*|*/.git/*|*/__pycache__/*) ;;
                */.local/lib/*|*/.tox/*|*/build/*|*/.mypy_cache/*) ;;
                # Not deploy targets: snapshots of the past, and other
                # checkouts of the same code. His host has several of each,
                # and installing into one of them would change nothing while
                # looking like it worked.
                *backup*|*backups/*|*/.graduation-review-backups/*) ;;
                "$HOME"/repos/*|*/.openclaw/*) ;;
                *) printf '%s\n' "$h" ;;
            esac
        done | sort -u
}
count() { printf '%s\n' "$1" | sed '/^$/d' | wc -l | tr -d ' '; }

# turn_coordinator.py is part of the running system, so it anchors the tree.
# New files with no copy yet are placed beside it.
if [ -n "${VINTOS_SCRIPTS:-}" ]; then
    ANCHOR_DIR="$(abspath "$VINTOS_SCRIPTS")"
    [ -d "$ANCHOR_DIR" ] || die "VINTOS_SCRIPTS=$VINTOS_SCRIPTS is not a directory"
else
    hits="$(locate turn_coordinator.py)"; n="$(count "$hits")"
    if [ "$n" -eq 0 ]; then
        printf '\nSTOP: turn_coordinator.py is nowhere under %s (depth %s).\n' "$HOME" "$DEPTH" >&2
        printf 'Name the directory his scripts are in:\n' >&2
        printf '    VINTOS_SCRIPTS=/that/dir bash %s\n' "${BASH_SOURCE[0]}" >&2
        exit 1
    elif [ "$n" -gt 1 ]; then
        printf '\nSTOP: turn_coordinator.py exists in more than one place:\n' >&2
        printf '%s\n' "$hits" | sed 's/^/    /' >&2
        printf '\nI am not going to pick. Rerun naming the live one:\n' >&2
        printf '    VINTOS_SCRIPTS=%s bash %s\n' "$(dirname -- "$(printf '%s\n' "$hits" | head -1)")" "${BASH_SOURCE[0]}" >&2
        exit 1
    fi
    ANCHOR_DIR="$(dirname -- "$hits")"
fi
say "his scripts: $ANCHOR_DIR"
say

# How many of the files this deploy installs already live in a directory?
# That is what makes a directory one of his trees rather than a coincidence.
tree_score() {
    local d="$1" f n=0
    for f in $SCRIPTS $BINS; do [ -e "$d/$f" ] && n=$((n + 1)); done
    printf '%s' "$n"
}

dest() {
    local base hits n beside best bestn d sc
    base="$(basename -- "$1")"
    hits="$(locate "$base")"; n="$(count "$hits")"
    [ "$n" -eq 1 ] && { printf '%s' "$hits"; return 0; }
    [ "$n" -eq 0 ] && { printf '%s/%s' "$ANCHOR_DIR" "$base"; return 0; }
    # a copy sitting beside the anchor is his by definition
    beside="$(printf '%s\n' "$hits" | grep -x -- "$ANCHOR_DIR/$base" || true)"
    [ -n "$beside" ] && { printf '%s' "$beside"; return 0; }
    # otherwise the tree holding the most of these files wins, and only if it
    # wins outright — a tie is still a question for her, not a guess by me
    best=""; bestn=-1; tie=0
    while read -r h; do
        [ -n "$h" ] || continue
        d="$(dirname -- "$h")"; sc="$(tree_score "$d")"
        if [ "$sc" -gt "$bestn" ]; then best="$h"; bestn="$sc"; tie=0
        elif [ "$sc" -eq "$bestn" ]; then tie=1; fi
    done <<< "$hits"
    if [ -n "$best" ] && [ "$tie" -eq 0 ] && [ "$bestn" -gt 0 ]; then
        printf '%s' "$best"; return 0
    fi
    printf 'AMBIGUOUS %s:\n%s\n' "$base" "$(printf '%s\n' "$hits" | sed 's/^/    /')" >&2
    return 1
}

# --------------------------------------------------------------------- plan
say "== plan =="
PLAN=""; ambiguous=0
for spec in $(printf 'scripts/%s\n' $SCRIPTS) $(printf 'bin/%s\n' $BINS); do
    f="$(basename -- "$spec")"
    if d="$(dest "$spec")"; then
        [ -e "$d" ] && mark="replace" || mark="NEW"
        printf '  %-7s %-26s -> %s\n' "$mark" "$f" "$d"
        PLAN="$PLAN$SRC/$spec|$d
"
    else
        ambiguous=1
    fi
done
[ "$ambiguous" -eq 0 ] || die "a file exists in more than one tree (above) — nothing installed"
say

# --------------------------------------------------------------- is he busy
say "== is he mid-turn? =="
if journalctl --user -n 400 --since "3 minutes ago" 2>/dev/null \
     | grep -qiE "avatar|/api/chat|voice/DO"; then
    say "  Active in the last 3 minutes; a broker restart would interrupt a live return."
    if [ -t 0 ]; then
        read -r -p "  type 'go' to install anyway, anything else stops: " ans
        [ "$ans" = "go" ] || die "not installed — he was working"
    else
        die "not installed — he was working (rerun when quiet, or from a terminal)"
    fi
else
    say "  quiet."
fi
say

[ "$CHECK_ONLY" -eq 1 ] && { say "--check: all gates passed, plan resolves. Nothing installed."; exit 0; }

# ------------------------------------------------------------ backup + install
mkdir -p "$BACKUP" || die "cannot create $BACKUP"
say "== backing up =="
: > "$BACKUP/restore.sh"
printf '%s' "$PLAN" | while IFS='|' read -r from to; do
    [ -n "${to:-}" ] && [ -e "$to" ] || continue
    # flatten the path into a filename, and never produce a dotfile — a backup
    # you cannot see in `ls` is a backup you will not think to use
    flat="$(printf '%s' "${to#$HOME/}" | tr '/' '_' | sed 's/^\./dot./')"
    cp -p "$to" "$BACKUP/$flat" 2>/dev/null \
      && printf 'install -m 644 "$(dirname "$0")/%s" %q\n' "$flat" "$to" >> "$BACKUP/restore.sh"
done
# The broker's files and unit go into restore.sh too. The first restore.sh
# backed them up but contained no commands to put them back — its "put it all
# back" claim was a lie for exactly the two files that run as another user.
for bf in "$BROKER" "$STORE"; do
    flat="$(basename -- "$bf")"
    if cp -p "$bf" "$BACKUP/$flat" 2>/dev/null || sudo -n cp -p "$bf" "$BACKUP/$flat" 2>/dev/null; then
        printf 'sudo install -o atelier -g atelier -m 644 "$(dirname "$0")/%s" %q\n' \
               "$flat" "$bf" >> "$BACKUP/restore.sh"
    else
        printf '# NOT backed up (unreadable at deploy time): %s\n' "$bf" >> "$BACKUP/restore.sh"
    fi
done
if [ -f "$UNIT_DST" ]; then
    cp -p "$UNIT_DST" "$BACKUP/$UNIT_NAME.service" 2>/dev/null \
      || sudo -n cp -p "$UNIT_DST" "$BACKUP/$UNIT_NAME.service" 2>/dev/null
    [ -f "$BACKUP/$UNIT_NAME.service" ] && printf 'sudo install -m 644 "$(dirname "$0")/%s.service" %q\n' \
        "$UNIT_NAME" "$UNIT_DST" >> "$BACKUP/restore.sh"
else
    printf '# no %s existed before this deploy; to undo the unit: sudo systemctl disable --now %s && sudo rm -f %s\n' \
           "$UNIT_DST" "$UNIT_NAME" "$UNIT_DST" >> "$BACKUP/restore.sh"
fi
# Record the service/process state honestly, and restore it as best we can.
if systemctl is-active --quiet "$UNIT_NAME" 2>/dev/null; then _BSTATE="unit-active"
elif pgrep -f "$BROKER" >/dev/null 2>&1; then _BSTATE="manual-process"
else _BSTATE="down"; fi
{
    printf '# broker state at backup time: %s\n' "$_BSTATE"
    printf 'sudo systemctl daemon-reload\n'
    if [ "$_BSTATE" != "down" ]; then
        printf 'sudo systemctl restart %s || echo "restore: %s did not start — sudo journalctl -u %s -n 40"\n' \
               "$UNIT_NAME" "$UNIT_NAME" "$UNIT_NAME"
    else
        printf '# broker was down at backup time; not starting it for you\n'
    fi
} >> "$BACKUP/restore.sh"
chmod 755 "$BACKUP/restore.sh"
say "  $BACKUP"
say "  put it all back with: bash $BACKUP/restore.sh"
say

say "== installing =="
_plan_file=/tmp/.atelier-plan.$$
printf '%s' "$PLAN" > "$_plan_file"
while IFS='|' read -r from to; do
    [ -n "${from:-}" ] && [ -n "${to:-}" ] || continue
    mkdir -p "$(dirname -- "$to")"
    install -m 644 "$from" "$to" || die "failed to install $to — restore from $BACKUP"
    printf '  %s\n' "$to"
done < "$_plan_file"
for f in $EXECUTABLE; do d="$(dest "scripts/$f")"; [ -e "$d" ] && chmod 755 "$d"; done
for f in first-light.sh gloria-model-update.sh self-model-update.sh; do d="$(dest "bin/$f")"; [ -e "$d" ] && chmod 755 "$d"; done   # cron runs these directly

# The checkout's logical paths are not Aegis's live paths.  Give the bounded
# self-builder the exact resolution this deploy just proved instead of making
# it rediscover the split tree or invent workspace/bin.
_runtime_map="$HOME/.vintos/workspace/memory/self-review-runtime-map.json"
mkdir -p "$(dirname -- "$_runtime_map")"
python3 - "$_runtime_map" "$SRC" "$_plan_file" <<'PY'
import json, os, sys
dst, src, plan = sys.argv[1:]
mapping = {}
for line in open(plan):
    if '|' not in line: continue
    frm, live = line.rstrip('\n').split('|', 1)
    rel = os.path.relpath(frm, src)
    if rel.startswith(('scripts/', 'bin/')):
        mapping[rel] = os.path.realpath(live)
tmp = dst + '.tmp'
with open(tmp, 'w') as f:
    json.dump({'schema': 1, 'generated_by': 'deploy-atelier', 'paths': mapping}, f, indent=2)
    f.flush(); os.fsync(f.fileno())
os.replace(tmp, dst)
PY
rm -f "$_plan_file"
say "  runtime map: $_runtime_map"
say

# The collision detector is continuous by design.  systemd only supervises
# that process; elapsed time is not a review signal.
say "== robot bridge =="
ROBOT_UNIT_NAME="vintos-robot-bridge"; ROBOT_UNIT_SRC="$SRC/broker/$ROBOT_UNIT_NAME.service"; ROBOT_UNIT_DST="$HOME/.config/systemd/user/$ROBOT_UNIT_NAME.service"
if [ -f "$ROBOT_UNIT_SRC" ]; then
    mkdir -p "$(dirname -- "$ROBOT_UNIT_DST")"
    [ -f "$ROBOT_UNIT_DST" ] && cp -p "$ROBOT_UNIT_DST" "$BACKUP/$ROBOT_UNIT_NAME.service" 2>/dev/null || true
    install -m 644 "$ROBOT_UNIT_SRC" "$ROBOT_UNIT_DST" || die "failed to install $ROBOT_UNIT_DST"
    systemctl --user daemon-reload
    if systemctl --user enable "$ROBOT_UNIT_NAME" >/dev/null 2>&1 && systemctl --user restart "$ROBOT_UNIT_NAME" >/dev/null 2>&1; then
        say "  $ROBOT_UNIT_NAME active: $(systemctl --user is-active "$ROBOT_UNIT_NAME" 2>/dev/null) (port ${VINTOS_ROBOT_PORT:-8404})"
    else
        say "  bridge installed but did not start - run: systemctl --user enable $ROBOT_UNIT_NAME && systemctl --user restart $ROBOT_UNIT_NAME"
    fi
fi
say

say "== self-review watcher =="
mkdir -p "$(dirname -- "$REVIEW_UNIT_DST")"
if [ -f "$REVIEW_UNIT_DST" ]; then
    cp -p "$REVIEW_UNIT_DST" "$BACKUP/$REVIEW_UNIT_NAME.service" 2>/dev/null || true
fi
install -m 644 "$REVIEW_UNIT_SRC" "$REVIEW_UNIT_DST" \
    || die "failed to install $REVIEW_UNIT_DST — restore from $BACKUP"
systemctl --user daemon-reload
if systemctl --user enable "$REVIEW_UNIT_NAME" >/dev/null 2>&1 \
   && systemctl --user restart "$REVIEW_UNIT_NAME" >/dev/null 2>&1; then
    say "  $REVIEW_UNIT_NAME active: $(systemctl --user is-active "$REVIEW_UNIT_NAME" 2>/dev/null)"
else
    say "  watcher installed but did not start — run: systemctl --user enable $REVIEW_UNIT_NAME && systemctl --user restart $REVIEW_UNIT_NAME"
fi
say

# ------------------------------------------------------------------- broker
# The broker is a systemd SYSTEM service now: root-managed unit, atelier-run
# process. No more manual relaunch — a reboot restarts it, a crash restarts it,
# and journald owns its stdout/stderr so no caller-side redirect can break
# logging again.
say "== broker (service $UNIT_NAME, runs as atelier) =="
brokered=0
if sudo -n true 2>/dev/null; then
    # Never die here. By this point his scripts are already installed, and
    # aborting would skip the verification that tells you what state the host
    # is actually in.
    if sudo install -o atelier -g atelier -m 644 "$SRC/broker/broker.py" "$BROKER" \
       && sudo install -o atelier -g atelier -m 644 "$SRC/broker/stratagem_store.py" "$STORE" \
       && sudo install -m 644 "$SRC/broker/$UNIT_NAME.service" "$UNIT_DST"; then
        sudo systemctl daemon-reload
        sudo systemctl enable "$UNIT_NAME" >/dev/null 2>&1
        # The old unit launches this same broker on this same port. Retire it;
        # Conflicts= in the installed unit keeps it retired thereafter.
        sudo systemctl disable --now atelier-broker.service >/dev/null 2>&1 || true
        # A leftover manually-launched broker holds 8611 and would make the
        # unit's first start fail; retire it before starting the service.
        sudo systemctl stop "$UNIT_NAME" 2>/dev/null
        sudo pkill -f "python3 $BROKER" 2>/dev/null; sleep 1
        if sudo systemctl start "$UNIT_NAME"; then
            sleep 2; brokered=1
            say "  installed; $UNIT_NAME $(systemctl is-active "$UNIT_NAME" 2>/dev/null), enabled: $(systemctl is-enabled "$UNIT_NAME" 2>/dev/null)"
        else
            say "  $UNIT_NAME FAILED TO START — the files are installed, the service is not up."
            say "  Diagnose with: sudo journalctl -u $UNIT_NAME -n 40"
            say "  Then:          sudo systemctl restart $UNIT_NAME"
        fi
    else
        say "  BROKER INSTALL FAILED — his scripts ARE installed, the broker is not."
        say "  Whatever broker was running is still running its old code. Run these yourself:"
        say "    sudo install -o atelier -g atelier -m 644 $SRC/broker/broker.py $BROKER"
        say "    sudo install -o atelier -g atelier -m 644 $SRC/broker/stratagem_store.py $STORE"
        say "    sudo install -m 644 $SRC/broker/$UNIT_NAME.service $UNIT_DST"
        say "    sudo systemctl daemon-reload && sudo systemctl enable $UNIT_NAME"
        say "    sudo pkill -f 'python3 $BROKER'; sleep 1; sudo systemctl restart $UNIT_NAME"
    fi
else
    say "  sudo wants a password. These lines, in order:"
    say "    sudo install -o atelier -g atelier -m 644 $SRC/broker/broker.py $BROKER"
    say "    sudo install -o atelier -g atelier -m 644 $SRC/broker/stratagem_store.py $STORE"
    say "    sudo install -m 644 $SRC/broker/$UNIT_NAME.service $UNIT_DST"
    say "    sudo systemctl daemon-reload && sudo systemctl enable $UNIT_NAME"
    say "    sudo pkill -f 'python3 $BROKER'; sleep 1; sudo systemctl restart $UNIT_NAME"
fi
say

# -------------------------------------------------------------------- house
# server.py is the unit's own file, so installing it changes nothing until the
# unit restarts. Leaving that to be remembered every time is how a deploy ends
# up half-applied — the new broker enforcing against the old house.
say "== the house =="
HOUSE_UNIT=""
for u in vintos-server velaris-server; do
    systemctl --user cat "$u" >/dev/null 2>&1 && { HOUSE_UNIT="$u"; break; }
done
# only the unit that actually runs a file we just replaced
if [ -n "$HOUSE_UNIT" ] && printf '%s' "$PLAN" | grep -q '|.*/server\.py$'; then
    if systemctl --user restart "$HOUSE_UNIT" 2>/dev/null; then
        sleep 3
        say "  restarted $HOUSE_UNIT ($(systemctl --user is-active "$HOUSE_UNIT" 2>/dev/null))"
    else
        say "  could not restart $HOUSE_UNIT — run: systemctl --user restart $HOUSE_UNIT"
    fi
elif [ -z "$HOUSE_UNIT" ]; then
    say "  no vintos-server unit found; restart the house yourself"
else
    say "  server.py was not replaced; no restart needed"
fi
say

# ------------------------------------------------------------------- verify
say "== verifying =="
_active="$(systemctl is-active "$UNIT_NAME" 2>/dev/null || echo unknown)"
_enabled="$(systemctl is-enabled "$UNIT_NAME" 2>/dev/null || echo not-installed)"
say "  service:      $UNIT_NAME $_active, on-boot: $_enabled"
[ "$_enabled" = "enabled" ] || say "    -> will NOT survive a reboot until enabled: sudo systemctl enable $UNIT_NAME"
h="$(curl -s -m 5 http://127.0.0.1:8611/health || true)"
[ -n "$h" ] && say "  health:       $h" \
            || say "  broker NOT answering on 8611 — sudo journalctl -u $UNIT_NAME -n 40, then sudo systemctl restart $UNIT_NAME"
sealed="$(curl -s -m 5 -X POST http://127.0.0.1:8611/artifact -H 'Content-Type: application/json' \
          -d '{"id":"000000000000","file":"x.md"}' || echo unreachable)"
say "  sealed route: $sealed"
case "$sealed" in
  *capability*|*malformed*|*escapes*) say "    -> refuses without a capability. Correct." ;;
  unreachable)                        say "    -> broker down; not checked." ;;
  *)                                  say "    -> DID NOT REFUSE. Do not arm anything; tell me." ;;
esac
say "  worktable:    $(curl -s -m 5 -X POST http://127.0.0.1:8611/worktable_id \
                       -H 'Content-Type: application/json' -d '{}' || echo unreachable)"
_mr="$(dest bin/model_router.py)"
say "  his model:    $(cd "$(dirname -- "$_mr")" 2>/dev/null \
                       && python3 -c 'import model_router;print(model_router.current_claude_model())' 2>&1 | tail -1)"
[ -n "$HOUSE_UNIT" ] && say "  house:        $HOUSE_UNIT $(systemctl --user is-active "$HOUSE_UNIT" 2>/dev/null) / $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8500/ 2>/dev/null)"
# The observatory and the broker must share a lineage key or the threshold can
# never adopt. Compared by digest — neither key is ever read out or printed.
_bfp="$(curl -s -m 5 -X POST http://127.0.0.1:8611/lineage/fingerprint \
        -H 'Content-Type: application/json' -d '{}' 2>/dev/null \
        | python3 -c 'import sys,json;print((json.load(sys.stdin) or {}).get("fingerprint",""))' 2>/dev/null)"
_lfp="$(python3 - <<'PY' 2>/dev/null
import hashlib, os
p = os.path.expanduser("~/.vintos/.lineage-key")
try:
    print(hashlib.sha256(open(p, "rb").read().strip()).hexdigest()[:16])
except Exception:
    print("")
PY
)"
if [ -z "$_bfp" ] || [ -z "$_lfp" ]; then
    say "  lineage key:  one side missing (broker='$_bfp' observatory='$_lfp')"
    say "                the threshold cannot adopt until both exist and match"
elif [ "$_bfp" = "$_lfp" ]; then
    say "  lineage key:  observatory and broker agree"
else
    say "  lineage key:  MISMATCH — attestations will all fail; adoption impossible"
fi
_th="$(dest scripts/atelier-threshold.py)"
say "  threshold:    $(python3 -c "import ast;ast.parse(open('$_th').read());print('installed, parses')" 2>&1 | tail -1)"
say "  self-review:  $(systemctl --user is-active "$REVIEW_UNIT_NAME" 2>/dev/null || echo inactive) / $(systemctl --user is-enabled "$REVIEW_UNIT_NAME" 2>/dev/null || echo disabled)"
say
say "backup: $BACKUP"
[ "$brokered" -eq 1 ] && say "Broker service restarted." || say "Broker service NOT restarted — run the lines above."
say "Nothing armed. Stratagems stay disarmed."
