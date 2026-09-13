#!/usr/bin/env bash
# deploy-atelier.sh — install this checkout onto his host.
#
#     bash scripts/deploy-atelier.sh            install
#     bash scripts/deploy-atelier.sh --check    run every check, install nothing
#     bash scripts/deploy-atelier.sh --dry-run  everything but copy/restart; prints what it would do
#     bash scripts/deploy-atelier.sh --map      which reviewed file actually runs here (reads only)
#
# It assumes NOTHING about where his tree is or how it is laid out. For each
# file it finds the copy that is already there and installs over it; whatever
# layout he has is by definition the correct one. I assumed a layout twice
# (~/.vintos/workspace, then bin/ + scripts/) and was wrong both times.
#
# Order: preflight (every source exists AND parses) -> suites -> plan -> stage
# the whole release in a scratch dir and validate it there -> back up every
# file about to be replaced -> promote file by file (a failure mid-way puts
# the already-replaced files back) -> restart units and CONFIRM each one came
# up -> verify. Any failed check, suite, or unconfirmed restart exits non-zero.
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
# A failure that must not abort mid-deploy (files already promoted) is
# recorded here and makes the script exit non-zero at the end.
FAILED=""
flag() { FAILED="$FAILED
  - $*"; say "  FAIL: $*"; }

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
CHEM_UNIT_NAME="vintos-chemistry-lab"
CHEM_UNIT_SRC="$SRC/broker/$CHEM_UNIT_NAME.service"
CHEM_UNIT_DST="$HOME/.config/systemd/user/$CHEM_UNIT_NAME.service"
CHEM_SESSION_NAME="vintos-chemistry-session"
CHEM_SESSION_SERVICE_SRC="$SRC/broker/$CHEM_SESSION_NAME.service"; CHEM_SESSION_SERVICE_DST="$HOME/.config/systemd/user/$CHEM_SESSION_NAME.service"
CHEM_SESSION_TIMER_SRC="$SRC/broker/$CHEM_SESSION_NAME.timer"; CHEM_SESSION_TIMER_DST="$HOME/.config/systemd/user/$CHEM_SESSION_NAME.timer"
ROBOT_UNIT_NAME="vintos-robot-bridge"; ROBOT_UNIT_SRC="$SRC/broker/$ROBOT_UNIT_NAME.service"; ROBOT_UNIT_DST="$HOME/.config/systemd/user/$ROBOT_UNIT_NAME.service"
# The weekly skills read is a oneshot service driven by a timer, not a long-running
# service: the thing to install and confirm is the TIMER. Until now both files were a
# manual cp + systemctl --user on the host, so a fresh deploy left him with no weekly read.
SURF_UNIT_NAME="vintos-skill-surf"
SURF_SERVICE_SRC="$SRC/broker/$SURF_UNIT_NAME.service"; SURF_SERVICE_DST="$HOME/.config/systemd/user/$SURF_UNIT_NAME.service"
SURF_TIMER_SRC="$SRC/broker/$SURF_UNIT_NAME.timer";     SURF_TIMER_DST="$HOME/.config/systemd/user/$SURF_UNIT_NAME.timer"
DEPTH=6
CHECK_ONLY=0; DRY_RUN=0
case "${1:-}" in
    --check)   CHECK_ONLY=1 ;;
    --dry-run) DRY_RUN=1 ;;
    # --map: which reviewed file actually runs on this host - manifest vs installed vs referenced. Reads only.
    --map)     exec python3 "$SRC/scripts/release-map.py" --src "$SRC" ;;   # SRC is resolved above, before the cd /
    "")        ;;
    *)         die "unknown option: $1 (--check | --dry-run | --map)" ;;
esac

# Exactly what this build changed. An explicit list — never a wildcard.
SCRIPTS="request_trace.py emotion_runtime.py durable_projection.py atelier-open.py atelier-visit.py atelier-threshold.py
evidence_view.py prediction_ledger.py build_merged_chat.py
constitutional_barrier.py turn_coordinator.py relational_mismatch.py
causality_engine.py value_map.py repair_case.py encounter.py
jepa_predictor.py drift_head.py relational_head.py world_model.py
gloria_prediction.py withheld_head.py self_pressure.py resonance_felt.py inner_context.py
value-map.py relational-mismatch.py causality-engine.py self-prediction.py
effect_gate.py toy_link.py device_patterns.py evidence_provenance.py heart_rate.py
stratagem.py turn_record.py formation_observatory.py thruster_link.py
concurrency-canary.py
atelier-door.sh atelier-canary.sh atelier-broker-watch.sh atelier-status.sh
house_map.py house-map.json home_presence.py
want_artifact_guard.py wants_audit.py emoclaw_utils.py want_contract.py
hypothesis_ledger.py shadow_counterfactuals.py lab_daily_digest.py"
SCRIPTS="$SCRIPTS humor-practice.py joke_fermentation.py taste_salience.py curiosity_debt.py unsaid_frontier.py unsaid_questions.py"
SCRIPTS="$SCRIPTS self_review.py self_review_builder.py reciprocal_modification.py atelier_reveals.py atelier_quantum.py quantum_snapshot.py"
SCRIPTS="$SCRIPTS intent_context.py atelier-gate.py"
SCRIPTS="$SCRIPTS campaign.py plan.py intent_engine.py presence_audit.py priority_vector.py self_difference.py desired_difference.py"  # campaign board, 2026-09-05
SCRIPTS="$SCRIPTS self_model_evidence.py self_model_read.py protected_paths.py"  # created 2026-09-04, never in the manifest (review P01)
SCRIPTS="$SCRIPTS release-map.py enactment_distiller.py want_spine.py pleasure_substrate.py"
SCRIPTS="$SCRIPTS thread_store.py latent_threads.py ghost-branches.py dream_heat_seed.py mirror.sh"   # thread lifecycle, 2026-09-10
SCRIPTS="$SCRIPTS artifact_manifest.py deliver.py reflection_stage.py dream-art.py"   # artifact manifest and delivery, 2026-09-10
SCRIPTS="$SCRIPTS experiments.py latent_preparation.py wants_meta.py attractor_discovery.py"   # controls and wants, 2026-09-10
SCRIPTS="$SCRIPTS compute_admission.py compute-report.py store_compat.py bilateral_stages.py"   # compute admission, 2026-09-10
SCRIPTS="$SCRIPTS chemistry_lab.py chemistry_esmc.py chemistry_mac.py chemistry_session.py"   # visible Chemistry Lab; separate from Atelier, 2026-09-12
SCRIPTS="$SCRIPTS schedule-graph.py"   # schedule graph, review 20, 2026-09-10
SCRIPTS="$SCRIPTS recall_explain.py"   # explainable recall, reviews 126/144, 2026-09-10
SCRIPTS="$SCRIPTS correction_propagate.py"   # review 384, 2026-09-10
SCRIPTS="$SCRIPTS sensor_reactions.py"   # review 94, 2026-09-10
SCRIPTS="$SCRIPTS grading_contract.py outcome_join.py enjoyment.py"   # reviews 208/217/225, 2026-09-10
SCRIPTS="$SCRIPTS want_completion.py"   # review 254, 2026-09-10
SCRIPTS="$SCRIPTS atelier_ledger.py send_policy.py self_review_vocab.py question_lifecycle.py"   # reviews 273/309/372/260, 2026-09-10
SCRIPTS="$SCRIPTS entry_owners.py"   # reviews 1/6/7/22/26, 2026-09-10
SCRIPTS="$SCRIPTS store_guard.py store_owners.py env_file.py"   # env_file: ONE reader for vintos.env; nine hand-rolled parses disagreed about quotes and cost him Sol (2026-09-11)   # reviews 46/47, 2026-09-10
SCRIPTS="$SCRIPTS untested_report.py health_view.py"   # reviews 388/389, 2026-09-10
SCRIPTS="$SCRIPTS source_cache.py"   # review 162, 2026-09-10
SCRIPTS="$SCRIPTS calibration.py jepa_calibration_audit.py idempotency.py"   # reviews 202/207/80, 2026-09-10
SCRIPTS="$SCRIPTS record_contract.py pending_sweep.py"   # reviews 34/39/51/50/54, 2026-09-10
SCRIPTS="$SCRIPTS physical_contract.py sealed_retry.py effect_authority.py text_similarity.py"   # reviews 77/93/98/95/157, 2026-09-10
SCRIPTS="$SCRIPTS learning_occasion.py retry_policy.py"   # reviews 49/175, 2026-09-10
SCRIPTS="$SCRIPTS diagnostic_contract.py subsystem_audit.py causality-engine.py self_difference.py priority_vector.py campaign.py self_review_builder.py"   # diagnostics and the causality door, 2026-09-10
SCRIPTS="$SCRIPTS identity_revisions.py capability-view.py claim_hold.py tension_promotion.py"   # identity revisions and the capability view, 2026-09-10
SCRIPTS="$SCRIPTS proposition_lineage.py configuration_space.py"   # served views and inspectable maps, 2026-09-10
# release map 2026-09-05: every file the server or a deployed script references, so a fix in git reaches him
SCRIPTS="$SCRIPTS device_context.py lead_trials.py memory-index.py memory-index.sh memory-search.py residue.py durable_memory.py map_view_compiler.py"
SCRIPTS="$SCRIPTS thread_temperature.py premonition-dreamer.py somatic_bridge.py unseen.py emotional-entanglement.py emotional_entanglement.py self-statements.py self_statements.py"
SCRIPTS="$SCRIPTS creative-expression.sh dream-music.py humor_practice.py tension-field.py tension_field.py tension_promotion.py belief-sediment.py belief_sediment.py subconscious_drift.py emoclaw_mode.py"
SCRIPTS="$SCRIPTS wal-decay.py interaction-ledger.py prediction_ledger.py"   # P02/P04 items, 2026-09-05
SCRIPTS="$SCRIPTS vintos-home.py"   # every home route loads it by absolute path; it did not exist on Aegis (2026-09-05)
SCRIPTS="$SCRIPTS mischief-detector.sh mischief_log.py mischief_timing.py reelroom.py"
SCRIPTS="$SCRIPTS robot_core.py robot_bridge.py robot_subconscious.py trial_extractor.py"
SCRIPTS="$SCRIPTS context_selection.py isolated_exec.py run_isolated_test.py test_http_fixture.py want_stance.py skill_forge.py forge_build.py forge_resume.py print_3d.py spark_sources.py openclaw_skills.py astra_call.py"   # a want that holds a rate, the forge for a missing hand, the builder that fills it, the resume that hands it back to the want, the printer he does not have yet (2026-09-11)
SCRIPTS="$SCRIPTS policy_decisions.py"   # her four policy decisions, in one place (reviews 189-192, 2026-09-10)
SCRIPTS="$SCRIPTS desktop_agent.py desktop_windows.py desktop_winpy.py screen_share.py browser_winpy.py browser_agent.py"   # his hands, eyes and browser on the Windows desktop (2026-09-06)
SCRIPTS="$SCRIPTS spark_pressure.py withheld_confirm.py tension_ledger.py commitment_spine.py drift_reason.py opposition_calibration.py opposition_misuse.py"  # migrated shared-store writers, 2026-09-11
BINS="causal-cluster.py ambition-check.py ambition-review.py causal-observations.py robot-pi-repoint.sh purge-test-residue.py avatar-choice.py resonance-rescore.py systems-checkup.py music-share.py music-composer.py server.py model_router.py gen_result.py merged_full_route.py humor_detector.py humor_reaction.py
taste-reflection.py taste-vector.py gloria-model-update.sh self-model-update.sh
blush-ledger.py wants-router.py
avatar_stage.py study_chat.py avatar_dryrun.py strip_body_vocab.py first-light.sh dream_music.py
wal-extract.py wal_extract.py vintos-video.py vintos-code-review.py consent-gate.sh deviation_check.py memory_search.py
emoclaw_mode.py subconscious_drift.py belief-sediment.py belief_sediment.py core-engine.py core_sustain.py value-map.py
vintos-moltbook.py vintos-initiate.sh idle-journal.sh device_patterns.py relational_mismatch.py
memory_index.py wal-decay.py interaction_ledger.py"
# The IMPORT twin of a manifested CLI name. `causal-cluster.py` was repaired and deployed
# while `causal_cluster.py` - the name every `import causal_cluster` actually resolves - was
# in no list at all, so the host kept a stale copy of the module the code imports and ran old
# clustering logic behind a file that looked current. Every .py twin that exists on disk is
# named here, so the two spellings can never drift apart on the host again (2026-09-11).
BINS="$BINS ambition_review.py behavioral_intercept.py blush_ledger.py causal_cluster.py causal_observations.py confession-writer.py core_engine.py deviation-check.py humor-detector.py humor-reaction.py latent-threads.py music_share.py taste_reflection.py taste_vector.py temporal_memory.py thread_resolution.py thread_triage.py thread-weaver.py wal_decay.py wants_router.py weekly_summary.py"
BINS="$BINS vintos_claude_shim.py hallucination_check.py reality_anchor.py reality-anchor.py specificity_check.py wonder-detector.py wonder_detector.py"
BINS="$BINS ledger-scrub.py causal-self-model.py causal_self_model.py setup_memory.sh voice_kokoro.py tension-field.sh pearl-engine.sh soul-review.sh weekly-summary.sh yearning-detector.sh resonance-pulse.sh emotional-reflection.sh humor-detector.sh frame-engine.sh relational-mismatch.sh value-map-update.sh behavioral-intercept.py weekly-summary.py temporal-memory.py subconscious-drift.py vintos-send-video.py thread_store.py thread-triage.py thread_weaver.py thread-resolution.py latent_threads.py ghost-branches.py confession_writer.py unprecedented-detector.sh silence-audit.sh substrate-anxiety.sh second-order-dreamer.py preoccupation-dream.sh"   # thread lifecycle, 2026-09-10
EXECUTABLE="atelier-open.py atelier-visit.py atelier-threshold.py atelier-gate.py vintos-home.py mischief-detector.sh robot_bridge.py robot_subconscious.py robot-pi-repoint.sh desktop_agent.py
atelier-door.sh atelier-canary.sh atelier-broker-watch.sh gloria-model-update.sh atelier-status.sh"

# Every file this deploy touches, relative to the checkout (the manifest above
# plus the broker's two files and the units). This is what gets staged.
# the dreaming skill's two shell entry points live under skills/, not scripts/ or bin/
SKILLFILES="skills/dreaming/scripts/dream-trigger.sh skills/dreaming/scripts/should-dream.sh"   # thread lifecycle, 2026-09-10
DOMAINFILES="bin/server_domains/galleries.py bin/server_domains/music.py bin/server_domains/humor_wants.py"
SCRIPTS="$SCRIPTS pearl-engine.py pearl_engine.py"
BINS="$BINS pearl-engine.py pearl_engine.py"

CLIENTFILES="clients/mobile/index.html clients/mobile/client_lifecycle.js clients/mobile/avatar-bundle.js"
MANIFEST="$(printf 'scripts/%s\n' $SCRIPTS; printf 'bin/%s\n' $BINS; printf '%s\n' $SKILLFILES $DOMAINFILES $CLIENTFILES broker/vintos-emoclaw-provenance.conf
            printf 'broker/%s\n' broker.py stratagem_store.py "$UNIT_NAME.service" "$REVIEW_UNIT_NAME.service" "$CHEM_UNIT_NAME.service" "$CHEM_SESSION_NAME.service" "$CHEM_SESSION_NAME.timer"
            [ -f "$ROBOT_UNIT_SRC" ] && printf 'broker/%s\n' "$ROBOT_UNIT_NAME.service"
            printf 'broker/%s\n' "$SURF_UNIT_NAME.service" "$SURF_UNIT_NAME.timer"
            true)"
MANIFEST="$(printf '%s\n' "$MANIFEST" | sort -u)"

# ---------------------------------------------------------------- preflight
[ -d "$SRC/broker" ] && [ -d "$SRC/scripts" ] || die "not a Vintos checkout: $SRC"
say "source: $SRC"
say "commit: $(git -C "$SRC" rev-parse --short HEAD 2>/dev/null || echo '(no git)')"
[ "$DRY_RUN" -eq 1 ] && say "mode:   --dry-run (nothing copied, nothing restarted)"
say
missing=""
for f in $MANIFEST; do [ -f "$SRC/$f" ] || missing="$missing $f"; done
[ -f "$SRC/broker/$UNIT_NAME.service" ] || missing="$missing broker/$UNIT_NAME.service"   # the unit is what makes it a service
[ -z "$missing" ] || die "source is incomplete —$missing"

# Every source must PARSE, not just exist: .py with python3.12 (his host's
# interpreter) when present, .sh with bash -n, units must at least declare a
# [Service] with an ExecStart. Bytecode goes to a scratch dir, never into the
# tree being validated.
PYCHECK="$(command -v python3.12 || command -v python3)"
validate_tree() {   # $1 = root holding the manifest; prints each failure; returns 1 if any
    local root="$1" f bad=0 out
    local pyfiles=()
    for f in $MANIFEST; do
        case "$f" in *.py) pyfiles+=("$root/$f") ;; esac
    done
    out="$("$PYCHECK" -c '
import os, py_compile, sys, tempfile
bad = 0
with tempfile.TemporaryDirectory() as tmp:
    for i, p in enumerate(sys.argv[1:]):
        try:
            py_compile.compile(p, cfile=os.path.join(tmp, "%d.pyc" % i), doraise=True)
        except Exception as e:
            bad += 1
            msg = str(e).strip().splitlines()
            print("  %s: %s" % (p, msg[-1] if msg else e))
sys.exit(1 if bad else 0)
' "${pyfiles[@]}")" || bad=1
    [ -n "$out" ] && printf '%s\n' "$out"
    for f in $MANIFEST; do
        case "$f" in
            *.sh)      bash -n "$root/$f" 2>/dev/null || { bad=1; say "  $root/$f: does not parse (bash -n)"; } ;;
            *.service) grep -q '^\[Service\]' "$root/$f" && grep -q '^ExecStart=' "$root/$f" \
                         || { bad=1; say "  $root/$f: no [Service]/ExecStart="; } ;;
            # a timer with no schedule installs clean, enables clean, and never fires
            *.timer)   grep -q '^\[Timer\]' "$root/$f" && grep -qE '^(OnCalendar|OnBootSec|OnUnitActiveSec|OnStartupSec|OnActiveSec)=' "$root/$f" \
                         || { bad=1; say "  $root/$f: no [Timer] with a schedule"; } ;;
            *.json)    python3 -c 'import json,sys;json.load(open(sys.argv[1]))' "$root/$f" 2>/dev/null \
                         || { bad=1; say "  $root/$f: not valid JSON"; } ;;
        esac
    done
    return "$bad"
}
say "== parse check ($(basename -- "$PYCHECK"), $("$PYCHECK" --version 2>&1)) =="
validate_tree "$SRC" || die "a source file does not parse (above) — nothing installed"
say "  every manifest source parses ($(printf '%s\n' "$MANIFEST" | wc -l | tr -d ' ') files)"
say

# ------------------------------------------------------------------ suites
say "== suites =="
case "$(uname -s)" in
  Linux) command -v bwrap >/dev/null || die "PRECONDITION BWRAP_MISSING: OS test isolation requires bubblewrap. Install on Ubuntu/Debian: sudo apt-get update && sudo apt-get install -y bubblewrap" ;;
  Darwin) [ -x /usr/bin/sandbox-exec ] || die "test isolation requires sandbox-exec" ;;
  *) die "no supported test isolation for this operating system" ;;
esac
PYTHONNOUSERSITE=1 "$PYCHECK" -c 'import numpy, requests' >/dev/null 2>&1 \
    || die "PRECONDITION TEST_PYTHON_DEPENDENCIES: isolated tests require numpy and requests outside user-site packages. Ubuntu/Debian: sudo apt-get install -y python3-numpy python3-requests (or use a configured Python venv)."
fail=0
for t in "$SRC"/broker/tests/test_*.py; do
    out="$("$PYCHECK" "$SRC/scripts/run_isolated_test.py" "$t" 2>&1)"; rc=$?
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
        printf '%s'  "$best"; return 0
    fi
    printf 'AMBIGUOUS %s:\n%s\n' "$base" "$(printf '%s\n' "$hits" | sed 's/^/    /')" >&2
    return 1
}

# install(1) replaces a destination symlink instead of updating its target.
# Preserve the runtime import aliases and back up/promote the actual owned file.
canonical_dest() {
    python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
}

# --------------------------------------------------------------------- plan
say "== plan =="
PLAN=""; ambiguous=0
for spec in $(printf 'scripts/%s\n' $SCRIPTS) $(printf 'bin/%s\n' $BINS); do
    f="$(basename -- "$spec")"
    if d="$(dest "$spec")"; then
        d="$(canonical_dest "$d")" || die "cannot resolve installed target for $spec"
        [ -e "$d" ] && mark="replace" || mark="NEW"
        printf '  %-7s %-26s -> %s\n' "$mark" "$f" "$d"
        PLAN="$PLAN$SRC/$spec|$d
"
    else
        ambiguous=1
    fi
done
# Domain modules belong beside the actual server, not beside an unrelated music.py.
if server_dst="$(dest bin/server.py)"; then
    server_dst="$(canonical_dest "$server_dst")" || die "cannot resolve installed server target"
    for spec in $CLIENTFILES; do
        case "$spec" in
            */index.html) d="$(dirname -- "$server_dst")/website/app.html" ;;
            *) d="$(dirname -- "$server_dst")/website/app/$(basename -- "$spec")" ;;
        esac
        PLAN="$PLAN$SRC/$spec|$d
"
    done
    if [ -f "$HOME/.config/systemd/user/vintos-emoclaw.service" ]; then
        PLAN="$PLAN$SRC/broker/vintos-emoclaw-provenance.conf|$HOME/.config/systemd/user/vintos-emoclaw.service.d/provenance.conf
"
    fi
    for spec in $DOMAINFILES; do
        d="$(dirname -- "$server_dst")/server_domains/$(basename -- "$spec")"
        printf '  %-7s %-26s -> %s\n' "domain" "$(basename -- "$spec")" "$d"
        PLAN="$PLAN$SRC/$spec|$d
"
    done
else
    ambiguous=1
fi
[ "$ambiguous" -eq 0 ] || die "a file exists in more than one tree (above) — nothing installed"

# Two sources, one destination. `belief_sediment.py` is in SCRIPTS and in BINS, and the
# two checkouts had drifted apart: the plan promoted scripts/ and then bin/ over the top
# of it, so a repair committed to one copy was silently thrown away by the same deploy
# that claimed to install it. A destination fed by two sources is fine while the bytes
# agree; it is refused the moment they do not, with both sources named.
printf '%s' "$PLAN" | python3 -c '
import hashlib, sys
seen, bad = {}, {}
for line in sys.stdin:
    line = line.rstrip("\n")
    if "|" not in line: continue
    src, dst = line.split("|", 1)
    try:
        h = hashlib.sha256(open(src, "rb").read()).hexdigest()
    except OSError as e:
        print("  %s: %s" % (src, e)); sys.exit(2)
    if dst in seen:
        if seen[dst][0] != h:
            bad.setdefault(dst, {seen[dst][1]}).add(src)
    else:
        seen[dst] = (h, src)
for dst, srcs in sorted(bad.items()):
    print("  %s" % dst)
    for s in sorted(srcs):
        print("      <- %s" % s)
sys.exit(1 if bad else 0)
' || die "one destination, two sources with different bytes (above) — the last would silently win; make them one file"
say

# -------------------------------------------------------------------- stage
# The whole release is copied into a scratch dir and validated THERE; every
# install below reads from the stage, never from the checkout, so a file that
# changes under us between plan and promote cannot slip in unvalidated.
say "== staging =="
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/atelier-stage.XXXXXX")" || die "cannot create a staging dir"
trap 'rm -rf "$STAGE"' EXIT
for f in $MANIFEST; do
    mkdir -p "$STAGE/$(dirname -- "$f")" && cp -p "$SRC/$f" "$STAGE/$f" \
      || die "could not stage $f — nothing installed"
done
validate_tree "$STAGE" || die "the staged release does not validate (above) — nothing installed"
say "  $STAGE: $(printf '%s\n' "$MANIFEST" | wc -l | tr -d ' ') files staged and validated"
staged() { printf '%s/%s' "$STAGE" "${1#$SRC/}"; }   # checkout path -> its staged copy
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

[ "$CHECK_ONLY" -eq 1 ] && { say "--check: all gates passed, plan resolves, stage validates. Nothing installed."; exit 0; }

# ---------------------------------------------------------- restart confirm
# After a restart, the unit that came up must be the one we named, active,
# with a main process. Read-only: systemctl show, curl. Anything less is a
# recorded failure, not a shrug.
confirm_unit() {   # $1 = "--user" or "--system", $2 = unit name
    local scope="$1" u="$2" out id st pid
    out="$(systemctl "$scope" show -p Id,ActiveState,MainPID "$u" 2>/dev/null)"
    id="$(printf '%s\n' "$out" | sed -n 's/^Id=//p')"
    st="$(printf '%s\n' "$out" | sed -n 's/^ActiveState=//p')"
    pid="$(printf '%s\n' "$out" | sed -n 's/^MainPID=//p')"
    if [ "$id" = "$u.service" ] && [ "$st" = "active" ] && [ "${pid:-0}" -gt 0 ] 2>/dev/null; then
        say "  confirmed: Id=$id ActiveState=$st MainPID=$pid"; return 0
    fi
    flag "$u not confirmed after restart (Id=${id:-?} ActiveState=${st:-?} MainPID=${pid:-?})"; return 1
}

# A timer has no MainPID and its oneshot service is inactive between firings, so
# confirm_unit would call a perfectly healthy timer a failure. What proves a timer
# is doing its job is that it is active AND has a next elapse to point at.
confirm_timer() {   # $1 = "--user" or "--system", $2 = timer name (no .timer)
    local scope="$1" u="$2" out id st next elapse
    out="$(systemctl "$scope" show -p Id,ActiveState,NextElapseUSecRealtime "$u.timer" 2>/dev/null)"
    id="$(printf '%s\n' "$out" | sed -n 's/^Id=//p')"
    st="$(printf '%s\n' "$out" | sed -n 's/^ActiveState=//p')"
    elapse="$(printf '%s\n' "$out" | sed -n 's/^NextElapseUSecRealtime=//p')"
    next="$(systemctl "$scope" list-timers --all --no-legend "$u.timer" 2>/dev/null | head -1)"
    if [ "$id" = "$u.timer" ] && [ "$st" = "active" ] && [ -n "$elapse" ] && [ "$elapse" != "0" ] && [ "$elapse" != "n/a" ]; then
        say "  confirmed: Id=$id ActiveState=$st${next:+ next=$(printf '%s' "$next" | awk '{print $1, $2, $3}')}"
        return 0
    fi
    flag "$u.timer not confirmed (Id=${id:-?} ActiveState=${st:-?}) — run: systemctl --user enable --now $u.timer"
    return 1
}
wait_http() {   # $1 = label, $2 = url, $3 = seconds; succeeds when the url answers at all
    local label="$1" url="$2" max="$3" i=0 code
    while [ "$i" -lt "$max" ]; do
        code="$(curl -s -o /dev/null -m 2 -w '%{http_code}' "$url" 2>/dev/null)"
        if [ -n "$code" ] && [ "$code" != "000" ]; then
            say "  confirmed: $label answers $url (HTTP $code, ${i}s)"; return 0
        fi
        i=$((i + 1)); sleep 1
    done
    flag "$label did not answer $url within ${max}s"; return 1
}

# The plan as a file: the promote loop and the runtime map both read it.
_plan_file="$STAGE/plan"
printf '%s' "$PLAN" > "$_plan_file"
flat_of() {   # live path -> backup filename: flattened, never a dotfile
    printf '%s' "${1#$HOME/}" | tr '/' '_' | sed 's/^\./dot./'
}

if [ "$DRY_RUN" -eq 1 ]; then
    say "== dry run =="
    say "  would back up every replaced file to $BACKUP/<flattened-path>.pre-deploy"
    say "  rollback would be: bash $BACKUP/restore.sh"
    while IFS='|' read -r from to; do
        [ -n "${from:-}" ] && [ -n "${to:-}" ] || continue
        [ -e "$to" ] && mark="replace" || mark="new"
        printf '  would %-7s %s  (from %s)\n' "$mark" "$to" "$(staged "$from")"
    done < "$_plan_file"
    say "  would write runtime map: $HOME/.vintos/workspace/memory/self-review-runtime-map.json"
    say "  would write the release record: $HOME/.vintos/deploy/releases/<stamp>-<git rev>.json (files+hashes, services, broker, backup, rollback)"
    [ -f "$ROBOT_UNIT_SRC" ] && say "  would install + restart (user)   $ROBOT_UNIT_NAME -> $ROBOT_UNIT_DST, then confirm Id/ActiveState/MainPID"
    say "  would install + restart (user)   $REVIEW_UNIT_NAME -> $REVIEW_UNIT_DST, then confirm Id/ActiveState/MainPID"
    say "  would install + restart (user)   $CHEM_UNIT_NAME -> $CHEM_UNIT_DST (disabled in its own config until Tune enables it)"
    say "  would install + enable (user)    $CHEM_SESSION_NAME.timer -> $CHEM_SESSION_TIMER_DST"
    say "  would install (user)             $SURF_UNIT_NAME.service -> $SURF_SERVICE_DST (oneshot; not started)"
    say "  would install + enable (user)    $SURF_UNIT_NAME.timer -> $SURF_TIMER_DST, then confirm Id/ActiveState/next elapse"
    if sudo -n true 2>/dev/null; then
        say "  would install (sudo)             $BROKER, $STORE, $UNIT_DST; restart $UNIT_NAME, confirm, wait for 127.0.0.1:8611/health"
    else
        say "  sudo wants a password: the broker step would print its lines and the deploy would exit non-zero (restart unconfirmed)"
    fi
    if printf '%s' "$PLAN" | grep -q '|.*/server\.py$'; then
        say "  would restart the house unit (vintos-server/velaris-server) and wait for 127.0.0.1:8500/"
    fi
    say
    say "--dry-run: nothing copied, nothing restarted."
    exit 0
fi

# ------------------------------------------------------------ backup + install
mkdir -p "$BACKUP" || die "cannot create $BACKUP"
say "== backing up =="
: > "$BACKUP/restore.sh"
while IFS='|' read -r from to; do
    [ -n "${to:-}" ] && [ -e "$to" ] || continue
    # flatten the path into a filename, and never produce a dotfile — a backup
    # you cannot see in `ls` is a backup you will not think to use
    flat="$(flat_of "$to").pre-deploy"
    cp -p "$to" "$BACKUP/$flat" 2>/dev/null \
      && printf 'install -m 644 "$(dirname "$0")/%s" %q\n' "$flat" "$to" >> "$BACKUP/restore.sh" \
      || die "could not back up $to — nothing installed"
done < "$_plan_file"
# The broker's files and unit go into restore.sh too. The first restore.sh
# backed them up but contained no commands to put them back — its "put it all
# back" claim was a lie for exactly the two files that run as another user.
for bf in "$BROKER" "$STORE"; do
    flat="$(basename -- "$bf").pre-deploy"
    if cp -p "$bf" "$BACKUP/$flat" 2>/dev/null || sudo -n cp -p "$bf" "$BACKUP/$flat" 2>/dev/null; then
        printf 'sudo install -o atelier -g atelier -m 644 "$(dirname "$0")/%s" %q\n' \
               "$flat" "$bf" >> "$BACKUP/restore.sh"
    else
        printf '# NOT backed up (unreadable at deploy time): %s\n' "$bf" >> "$BACKUP/restore.sh"
    fi
done
if [ -f "$UNIT_DST" ]; then
    cp -p "$UNIT_DST" "$BACKUP/$UNIT_NAME.service.pre-deploy" 2>/dev/null \
      || sudo -n cp -p "$UNIT_DST" "$BACKUP/$UNIT_NAME.service.pre-deploy" 2>/dev/null
    [ -f "$BACKUP/$UNIT_NAME.service.pre-deploy" ] && printf 'sudo install -m 644 "$(dirname "$0")/%s.service.pre-deploy" %q\n' \
        "$UNIT_NAME" "$UNIT_DST" >> "$BACKUP/restore.sh"
else
    printf '# no %s existed before this deploy; to undo the unit: sudo systemctl disable --now %s && sudo rm -f %s\n' \
           "$UNIT_DST" "$UNIT_NAME" "$UNIT_DST" >> "$BACKUP/restore.sh"
fi
for u in "$ROBOT_UNIT_NAME" "$REVIEW_UNIT_NAME" "$CHEM_UNIT_NAME"; do
    ud="$HOME/.config/systemd/user/$u.service"
    if [ -f "$ud" ] && cp -p "$ud" "$BACKUP/$u.service.pre-deploy" 2>/dev/null; then
        printf 'install -m 644 "$(dirname "$0")/%s.service.pre-deploy" %q && systemctl --user daemon-reload && systemctl --user restart %s\n' \
               "$u" "$ud" "$u" >> "$BACKUP/restore.sh"
    else
        printf 'systemctl --user disable --now %q >/dev/null 2>&1 || true; rm -f %q; systemctl --user daemon-reload\n' \
               "$u" "$ud" >> "$BACKUP/restore.sh"
    fi
done
# The Lab frontier worker is a oneshot; preserve both unit files and the timer state.
_chem_session_enabled="$(systemctl --user is-enabled "$CHEM_SESSION_NAME.timer" 2>/dev/null || true)"
_chem_session_active="$(systemctl --user is-active "$CHEM_SESSION_NAME.timer" 2>/dev/null || true)"
printf 'systemctl --user disable --now %q >/dev/null 2>&1 || true\n' "$CHEM_SESSION_NAME.timer" >> "$BACKUP/restore.sh"
for _ext in service timer; do
    _dest="$HOME/.config/systemd/user/$CHEM_SESSION_NAME.$_ext"
    if [ -e "$_dest" ] || [ -L "$_dest" ]; then
        cp -Pp "$_dest" "$BACKUP/$CHEM_SESSION_NAME.$_ext.pre-deploy" || die "chemistry session unit backup failed"
        printf 'rm -f %q; cp -Pp "$(dirname "$0")/%s.%s.pre-deploy" %q\n' "$_dest" "$CHEM_SESSION_NAME" "$_ext" "$_dest" >> "$BACKUP/restore.sh"
    else
        printf 'rm -f %q\n' "$_dest" >> "$BACKUP/restore.sh"
    fi
done
printf 'systemctl --user daemon-reload\n' >> "$BACKUP/restore.sh"
[ "$_chem_session_enabled" = "enabled" ] && printf 'systemctl --user enable %q\n' "$CHEM_SESSION_NAME.timer" >> "$BACKUP/restore.sh"
[ "$_chem_session_active" = "active" ] && printf 'systemctl --user start %q\n' "$CHEM_SESSION_NAME.timer" >> "$BACKUP/restore.sh"
# Preserve both files and the timer's prior enabled/active state. Restoring never
# starts the oneshot service, and a unit newly introduced by this deploy is removed.
_surf_enabled="$(systemctl --user is-enabled "$SURF_UNIT_NAME.timer" 2>/dev/null || true)"
_surf_active="$(systemctl --user is-active "$SURF_UNIT_NAME.timer" 2>/dev/null || true)"
printf 'systemctl --user disable --now %q >/dev/null 2>&1 || true\n' "$SURF_UNIT_NAME.timer" >> "$BACKUP/restore.sh"
for _ext in service timer; do
    _dest="$HOME/.config/systemd/user/$SURF_UNIT_NAME.$_ext"
    if [ -e "$_dest" ] || [ -L "$_dest" ]; then
        cp -Pp "$_dest" "$BACKUP/$SURF_UNIT_NAME.$_ext.pre-deploy" || die "unit backup failed"
        printf 'rm -f %q; cp -Pp "$(dirname "$0")/%s.%s.pre-deploy" %q\n' "$_dest" "$SURF_UNIT_NAME" "$_ext" "$_dest" >> "$BACKUP/restore.sh"
    else
        printf 'rm -f %q\n' "$_dest" >> "$BACKUP/restore.sh"
    fi
done
printf 'systemctl --user daemon-reload\n' >> "$BACKUP/restore.sh"
[ "$_surf_enabled" = "enabled" ] && printf 'systemctl --user enable %q\n' "$SURF_UNIT_NAME.timer" >> "$BACKUP/restore.sh"
[ "$_surf_enabled" = "enabled-runtime" ] && printf 'systemctl --user enable --runtime %q\n' "$SURF_UNIT_NAME.timer" >> "$BACKUP/restore.sh"
[ "$_surf_active" = "active" ] && printf 'systemctl --user start %q\n' "$SURF_UNIT_NAME.timer" >> "$BACKUP/restore.sh"
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
if systemctl --user is-active --quiet vintos-emoclaw.service; then
    printf 'systemctl --user daemon-reload\nsystemctl --user restart vintos-emoclaw.service\n' >> "$BACKUP/restore.sh"
fi
chmod 755 "$BACKUP/restore.sh"
say "  $BACKUP  (every replaced file as <flattened-path>.pre-deploy)"
say "  rollback: bash $BACKUP/restore.sh"
say

# Promote from the stage, one file at a time. If any install fails, the files
# already replaced in THIS run go back to their .pre-deploy copies and files
# that were new are removed — then STOP.
say "== installing =="
PROMOTED=""
rollback_promoted() {
    local to flat
    say "  rolling back what this run already promoted:"
    printf '%s' "$PROMOTED" | while read -r to; do
        [ -n "$to" ] || continue
        flat="$(flat_of "$to").pre-deploy"
        if [ -f "$BACKUP/$flat" ]; then
            install -m 644 "$BACKUP/$flat" "$to" && say "    restored $to" || say "    COULD NOT restore $to from $BACKUP/$flat"
        else
            rm -f "$to" && say "    removed $to (was new)"
        fi
    done
}
while IFS='|' read -r from to; do
    [ -n "${from:-}" ] && [ -n "${to:-}" ] || continue
    if mkdir -p "$(dirname -- "$to")" && install -m 644 "$(staged "$from")" "$to"; then
        PROMOTED="$PROMOTED$to
"
        printf '  %s\n' "$to"
    else
        say "  FAILED to install $to"
        rollback_promoted
        die "promotion failed at $to; earlier files restored. Full rollback: bash $BACKUP/restore.sh"
    fi
done < "$_plan_file"
for f in $EXECUTABLE; do d="$(dest "scripts/$f")"; [ -e "$d" ] && chmod 755 "$d"; done
for f in first-light.sh gloria-model-update.sh self-model-update.sh; do d="$(dest "bin/$f")"; [ -e "$d" ] && chmod 755 "$d"; done   # cron runs these directly

# The checkout's logical paths are not Aegis's live paths.  Give the bounded
# self-builder the exact resolution this deploy just proved instead of making
# it rediscover the split tree or invent workspace/bin.
_runtime_map="$HOME/.vintos/workspace/memory/self-review-runtime-map.json"
mkdir -p "$(dirname -- "$_runtime_map")"
python3 - "$_runtime_map" "$SRC" "$_plan_file" <<'PY' || flag "runtime map not written"
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
say "  runtime map: $_runtime_map"
say

# The collision detector is continuous by design.  systemd only supervises
# that process; elapsed time is not a review signal.
say "== robot bridge =="
if [ -f "$ROBOT_UNIT_SRC" ]; then
    mkdir -p "$(dirname -- "$ROBOT_UNIT_DST")"
    install -m 644 "$(staged "$ROBOT_UNIT_SRC")" "$ROBOT_UNIT_DST" || die "failed to install $ROBOT_UNIT_DST — rollback: bash $BACKUP/restore.sh"
    systemctl --user daemon-reload
    if systemctl --user enable "$ROBOT_UNIT_NAME" >/dev/null 2>&1 && systemctl --user restart "$ROBOT_UNIT_NAME" >/dev/null 2>&1; then
        sleep 1
        confirm_unit --user "$ROBOT_UNIT_NAME" && say "  $ROBOT_UNIT_NAME on port ${VINTOS_ROBOT_PORT:-8404}"
    else
        flag "$ROBOT_UNIT_NAME installed but did not start - run: systemctl --user enable $ROBOT_UNIT_NAME && systemctl --user restart $ROBOT_UNIT_NAME"
    fi
fi
say

say "== self-review watcher =="
mkdir -p "$(dirname -- "$REVIEW_UNIT_DST")"
install -m 644 "$(staged "$REVIEW_UNIT_SRC")" "$REVIEW_UNIT_DST" \
    || die "failed to install $REVIEW_UNIT_DST — rollback: bash $BACKUP/restore.sh"
systemctl --user daemon-reload
if systemctl --user enable "$REVIEW_UNIT_NAME" >/dev/null 2>&1 \
   && systemctl --user restart "$REVIEW_UNIT_NAME" >/dev/null 2>&1; then
    sleep 1
    confirm_unit --user "$REVIEW_UNIT_NAME"
else
    flag "$REVIEW_UNIT_NAME installed but did not start — run: systemctl --user enable $REVIEW_UNIT_NAME && systemctl --user restart $REVIEW_UNIT_NAME"
fi
say

say "== chemistry lab worker =="
mkdir -p "$(dirname -- "$CHEM_UNIT_DST")"
install -m 644 "$(staged "$CHEM_UNIT_SRC")" "$CHEM_UNIT_DST" \
    || die "failed to install $CHEM_UNIT_DST — rollback: bash $BACKUP/restore.sh"
systemctl --user daemon-reload
if systemctl --user enable "$CHEM_UNIT_NAME" >/dev/null 2>&1 \
   && systemctl --user restart "$CHEM_UNIT_NAME" >/dev/null 2>&1; then
    sleep 1
    confirm_unit --user "$CHEM_UNIT_NAME"
else
    flag "$CHEM_UNIT_NAME installed but did not start — run: systemctl --user enable $CHEM_UNIT_NAME && systemctl --user restart $CHEM_UNIT_NAME"
fi
say

say "== chemistry lab scheduled frontier session =="
install -m 644 "$(staged "$CHEM_SESSION_SERVICE_SRC")" "$CHEM_SESSION_SERVICE_DST" \
    || die "failed to install $CHEM_SESSION_SERVICE_DST — rollback: bash $BACKUP/restore.sh"
install -m 644 "$(staged "$CHEM_SESSION_TIMER_SRC")" "$CHEM_SESSION_TIMER_DST" \
    || die "failed to install $CHEM_SESSION_TIMER_DST — rollback: bash $BACKUP/restore.sh"
systemctl --user daemon-reload
if systemctl --user enable "$CHEM_SESSION_NAME.timer" >/dev/null 2>&1 \
   && systemctl --user restart "$CHEM_SESSION_NAME.timer" >/dev/null 2>&1; then
    confirm_timer --user "$CHEM_SESSION_NAME"
else
    flag "$CHEM_SESSION_NAME.timer installed but not enabled — run: systemctl --user enable --now $CHEM_SESSION_NAME.timer"
fi
say

    if [ -f "$HOME/.config/systemd/user/vintos-emoclaw.service.d/provenance.conf" ]; then
        systemctl --user daemon-reload
        systemctl --user restart vintos-emoclaw.service || flag "emotion daemon restart failed"
        confirm_unit --user vintos-emoclaw || flag "emotion daemon did not come up"
    fi

# The weekly read of the OpenClaw skills page. The service is a oneshot; the timer is
# what is enabled and started. The service itself is deliberately NOT started here — a
# deploy is not a reason for him to go and read, and the weekly cap lives in the code
# (spark_sources.weekly_skill_surf), not in the schedule, so an extra firing would be
# harmless but still not ours to cause.
say "== skill surfing (weekly) =="
mkdir -p "$(dirname -- "$SURF_TIMER_DST")"
install -m 644 "$(staged "$SURF_SERVICE_SRC")" "$SURF_SERVICE_DST" \
    || die "failed to install $SURF_SERVICE_DST — rollback: bash $BACKUP/restore.sh"
install -m 644 "$(staged "$SURF_TIMER_SRC")" "$SURF_TIMER_DST" \
    || die "failed to install $SURF_TIMER_DST — rollback: bash $BACKUP/restore.sh"
systemctl --user daemon-reload
if systemctl --user enable "$SURF_UNIT_NAME.timer" >/dev/null 2>&1 \
   && systemctl --user restart "$SURF_UNIT_NAME.timer" >/dev/null 2>&1; then
    confirm_timer --user "$SURF_UNIT_NAME"
else
    flag "$SURF_UNIT_NAME.timer installed but not enabled — run: systemctl --user enable --now $SURF_UNIT_NAME.timer"
fi
say

# ------------------------------------------------------------------- broker
# The broker is a systemd SYSTEM service now: root-managed unit, atelier-run
# process. No more manual relaunch — a reboot restarts it, a crash restarts it,
# and journald owns its stdout/stderr so no caller-side redirect can break
# logging again.
say "== broker (service $UNIT_NAME, runs as atelier) =="
brokered=0
# The sudo lines are only for a broker that CHANGED. Three ways to know the installed broker is this
# one, tried in order: the installed files read identical; the marker left by the last install carries
# this release's hash; the running broker reports its own file hash on /health (Gloria, 2026-09-10:
# "skip the sudo broker lines unless broker/ changed").
BROKER_MARK="$HOME/.vintos/deploy/.broker-installed"
broker_hash="$(cat "$STAGE/broker/broker.py" "$STAGE/broker/stratagem_store.py" "$STAGE/broker/$UNIT_NAME.service" | sha256sum | cut -c1-64)"
broker_py_hash="$(sha256sum "$STAGE/broker/broker.py" | cut -c1-64)"
broker_same=0
if cmp -s "$STAGE/broker/broker.py" "$BROKER" 2>/dev/null && cmp -s "$STAGE/broker/stratagem_store.py" "$STORE" 2>/dev/null \
   && cmp -s "$STAGE/broker/$UNIT_NAME.service" "$UNIT_DST" 2>/dev/null; then
    broker_same=1; broker_how="installed files read identical"
elif [ -f "$BROKER_MARK" ] && [ "$(cat "$BROKER_MARK" 2>/dev/null)" = "$broker_hash" ]; then
    broker_same=1; broker_how="marker from the last install matches"
elif curl -s -m 3 http://127.0.0.1:8611/health 2>/dev/null | grep -q "\"code_sha256\": *\"$broker_py_hash\""; then
    broker_same=1; broker_how="the running broker reports this file's hash"
fi
if [ "$broker_same" -eq 1 ] && ! sudo -n true 2>/dev/null; then
    say "  unchanged since its last install ($broker_how); not touched, no sudo needed"
    if confirm_unit --system "$UNIT_NAME" && wait_http "$UNIT_NAME" http://127.0.0.1:8611/health 20; then
        brokered=1
    fi
elif sudo -n true 2>/dev/null; then
    # Never die here. By this point his scripts are already installed, and
    # aborting would skip the verification that tells you what state the host
    # is actually in. Failures are flagged and fail the deploy at the end.
    if sudo install -o atelier -g atelier -m 644 "$STAGE/broker/broker.py" "$BROKER" \
       && sudo install -o atelier -g atelier -m 644 "$STAGE/broker/stratagem_store.py" "$STORE" \
       && sudo install -m 644 "$STAGE/broker/$UNIT_NAME.service" "$UNIT_DST"; then
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
            sleep 2
            say "  installed; enabled: $(systemctl is-enabled "$UNIT_NAME" 2>/dev/null)"
            if confirm_unit --system "$UNIT_NAME" && wait_http "$UNIT_NAME" http://127.0.0.1:8611/health 20; then
                brokered=1; mkdir -p "$(dirname "$BROKER_MARK")" && printf '%s' "$broker_hash" > "$BROKER_MARK"
            fi
        else
            flag "$UNIT_NAME FAILED TO START — the files are installed, the service is not up."
            say "  Diagnose with: sudo journalctl -u $UNIT_NAME -n 40"
            say "  Then:          sudo systemctl restart $UNIT_NAME"
        fi
    else
        flag "BROKER INSTALL FAILED — his scripts ARE installed, the broker is not."
        say "  Whatever broker was running is still running its old code. Run these yourself:"
        say "    sudo install -o atelier -g atelier -m 644 $SRC/broker/broker.py $BROKER"
        say "    sudo install -o atelier -g atelier -m 644 $SRC/broker/stratagem_store.py $STORE"
        say "    sudo install -m 644 $SRC/broker/$UNIT_NAME.service $UNIT_DST"
        say "    sudo systemctl daemon-reload && sudo systemctl enable $UNIT_NAME"
        say "    sudo pkill -f 'python3 $BROKER'; sleep 1; sudo systemctl restart $UNIT_NAME"
        say "    mkdir -p $(dirname "$BROKER_MARK") && printf '%s' $broker_hash > $BROKER_MARK"
    fi
else
    flag "broker not installed/restarted: sudo wants a password. These lines, in order:"
    say "    sudo install -o atelier -g atelier -m 644 $SRC/broker/broker.py $BROKER"
    say "    sudo install -o atelier -g atelier -m 644 $SRC/broker/stratagem_store.py $STORE"
    say "    sudo install -m 644 $SRC/broker/$UNIT_NAME.service $UNIT_DST"
    say "    sudo systemctl daemon-reload && sudo systemctl enable $UNIT_NAME"
    say "    sudo pkill -f 'python3 $BROKER'; sleep 1; sudo systemctl restart $UNIT_NAME"
    say "    mkdir -p $(dirname "$BROKER_MARK") && printf '%s' $broker_hash > $BROKER_MARK"
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
        say "  restarted $HOUSE_UNIT"
        confirm_unit --user "$HOUSE_UNIT" && wait_http "$HOUSE_UNIT" http://127.0.0.1:8500/ 30
    else
        flag "could not restart $HOUSE_UNIT — run: systemctl --user restart $HOUSE_UNIT"
    fi
elif [ -z "$HOUSE_UNIT" ]; then
    flag "no vintos-server unit found; the house was not restarted — restart it yourself"
else
    say "  server.py was not replaced; no restart needed"
fi
say

# ------------------------------------------------------------------- verify
say "== verifying =="
_active="$(systemctl is-active "$UNIT_NAME" 2>/dev/null || echo unknown)"
_enabled="$(systemctl is-enabled "$UNIT_NAME" 2>/dev/null || echo not-installed)"
say "  service:      $UNIT_NAME $_active, on-boot: $_enabled"
[ "$_enabled" = "enabled" ] || flag "$UNIT_NAME will NOT survive a reboot until enabled: sudo systemctl enable $UNIT_NAME"
h="$(curl -s -m 5 http://127.0.0.1:8611/health || true)"
[ -n "$h" ] && say "  health:       $h" \
            || flag "broker NOT answering on 8611 — sudo journalctl -u $UNIT_NAME -n 40, then sudo systemctl restart $UNIT_NAME"
sealed="$(curl -s -m 5 -X POST http://127.0.0.1:8611/artifact -H 'Content-Type: application/json' \
          -d '{"id":"000000000000","file":"x.md"}' || echo unreachable)"
say "  sealed route: $sealed"
case "$sealed" in
  *capability*|*malformed*|*escapes*) say "    -> refuses without a capability. Correct." ;;
  unreachable)                        flag "sealed route: broker down; not checked." ;;
  *)                                  flag "sealed route DID NOT REFUSE. Do not arm anything; tell me." ;;
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
    flag "lineage key: one side missing (broker='$_bfp' observatory='$_lfp') — the threshold cannot adopt until both exist and match"
elif [ "$_bfp" = "$_lfp" ]; then
    say "  lineage key:  observatory and broker agree"
else
    flag "lineage key: MISMATCH — attestations will all fail; adoption impossible"
fi
_th="$(dest scripts/atelier-threshold.py)"
if python3 -c "import ast;ast.parse(open('$_th').read())" 2>/dev/null; then
    say "  threshold:    installed, parses"
else
    flag "threshold: $_th missing or does not parse after install"
fi
say "  self-review:  $(systemctl --user is-active "$REVIEW_UNIT_NAME" 2>/dev/null || echo inactive) / $(systemctl --user is-enabled "$REVIEW_UNIT_NAME" 2>/dev/null || echo disabled)"
say "  chemistry:    $(systemctl --user is-active "$CHEM_UNIT_NAME" 2>/dev/null || echo inactive) / $(systemctl --user is-enabled "$CHEM_UNIT_NAME" 2>/dev/null || echo disabled)"
say "  chem session: $(systemctl --user is-active "$CHEM_SESSION_NAME.timer" 2>/dev/null || echo inactive) / $(systemctl --user is-enabled "$CHEM_SESSION_NAME.timer" 2>/dev/null || echo disabled)"
say
# review 18/19: the release record - what this deploy installed (with hashes), from which commit,
# which units it restarted and confirmed, the broker's state, the backup and the rollback command.
RELEASES="$HOME/.vintos/deploy/releases"; mkdir -p "$RELEASES" 2>/dev/null
_rel_git="$(git -C "$SRC" rev-parse --short HEAD 2>/dev/null || echo unknown)"
_rel_file="$RELEASES/$(date +%Y%m%d-%H%M%S)-$_rel_git.json"
PLAN_FILE="$_plan_file" GIT_REV="$_rel_git" BACKUP_DIR="$BACKUP" BROKERED="$brokered" HOUSE="$HOUSE_UNIT" FAILED_TXT="$FAILED" REL_OUT="$_rel_file" python3 - <<'PY' 2>/dev/null && say "release:  $_rel_file"
import os, json, hashlib, time, subprocess
rows = []
for ln in open(os.environ["PLAN_FILE"]):
    if "|" not in ln: continue
    src, dst = ln.rstrip("\n").split("|", 1)
    try: sha = hashlib.sha256(open(dst, "rb").read()).hexdigest()[:16]
    except Exception: sha = None
    rows.append({"file": os.path.basename(src), "installed_at": dst, "sha256": sha})
def unit(u, scope):
    try: return subprocess.run(["systemctl"] + scope + ["is-active", u], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception: return "unknown"
rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "git_rev": os.environ["GIT_REV"], "files": rows,
       "services": {"vintos-server": unit(os.environ.get("HOUSE") or "vintos-server", ["--user"]), "vintos-robot-bridge": unit("vintos-robot-bridge", ["--user"]),
                    "vintos-self-review": unit("vintos-self-review", ["--user"]), "vintos-chemistry-lab": unit("vintos-chemistry-lab", ["--user"]), "vintos-emoclaw": unit("vintos-emoclaw", ["--user"]), "vintos-atelier": unit("vintos-atelier", []),
                    # a timer, not a service: its oneshot is inactive between firings, so the timer is what is recorded
                    "vintos-skill-surf.timer": unit("vintos-skill-surf.timer", ["--user"]),
                    "vintos-chemistry-session.timer": unit("vintos-chemistry-session.timer", ["--user"])},
       "broker_confirmed": os.environ.get("BROKERED") == "1", "backup": os.environ["BACKUP_DIR"],
       "rollback": "bash %s/restore.sh" % os.environ["BACKUP_DIR"], "failures": [l.strip() for l in os.environ.get("FAILED_TXT", "").splitlines() if l.strip()]}
json.dump(rec, open(os.environ["REL_OUT"], "w"), indent=1)
PY
say "backup:   $BACKUP"
say "rollback: bash $BACKUP/restore.sh"
[ "$brokered" -eq 1 ] && say "Broker service confirmed${broker_how:+ (unchanged: $broker_how)}." || say "Broker service NOT confirmed — see the failures below."
say "Nothing armed. Stratagems stay disarmed."
if [ -n "$FAILED" ]; then
    printf '\nDEPLOY FAILED — files are installed, but:%s\n' "$FAILED" >&2
    exit 1
fi
say "deploy OK"
