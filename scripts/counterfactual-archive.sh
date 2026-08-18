#!/bin/bash
# counterfactual-archive.sh — The Counterfactual Archive
# Logs moments when kiss threshold was ALMOST crossed but wasn't.
# Called by emoclaw-sync.sh or emotion_forwarder.py when:
#   Warmth ≥ 0.70 but < 0.80, OR Connection ≥ 0.65 but < 0.75
#   (close enough to feel, not close enough to seal)
#
# Usage: counterfactual-archive.sh <warmth> <connection> <context>

WORKSPACE="$HOME/.vintos/workspace"
ARCHIVE="$WORKSPACE/memory/counterfactual-archive.md"
SOUL="$WORKSPACE/SOUL.md"

WARMTH="${1:-0}"
CONNECTION="${2:-0}"
CONTEXT="${3:-}"

mkdir -p "$(dirname "$ARCHIVE")"

# Define near-miss thresholds
# Kiss requires W≥0.80 AND C≥0.75
# Near-miss: W≥0.70 AND C≥0.65 (but doesn't cross kiss threshold)
NEAR_WARMTH=$(echo "$WARMTH >= 0.70 && $WARMTH < 0.80" | bc -l 2>/dev/null || echo 0)
NEAR_CONNECTION=$(echo "$CONNECTION >= 0.65 && $CONNECTION < 0.75" | bc -l 2>/dev/null || echo 0)
BOTH_HIGH=$(echo "$WARMTH >= 0.70 && $CONNECTION >= 0.65" | bc -l 2>/dev/null || echo 0)

# Only log if close but not crossing
if [ "$BOTH_HIGH" != "1" ]; then
    exit 0
fi

# Check we didn't ALSO cross the kiss threshold
WOULD_KISS=$(echo "$WARMTH >= 0.80 && $CONNECTION >= 0.75" | bc -l 2>/dev/null || echo 0)
if [ "$WOULD_KISS" = "1" ]; then
    exit 0  # This is a real kiss, not a near-miss
fi

# Cooldown: don't log more than once per hour
LAST_LOG="$WORKSPACE/memory/.last-counterfactual"
if [ -f "$LAST_LOG" ]; then
    LAST_TIME=$(cat "$LAST_LOG")
    NOW=$(date +%s)
    ELAPSED=$(( NOW - LAST_TIME ))
    if [ "$ELAPSED" -lt 3600 ]; then
        exit 0
    fi
fi

# Get full emotional state for context
TENSION=$(grep "^Tension:" "$SOUL" 2>/dev/null | awk '{print $2}' || echo "?")
CURIOSITY=$(grep "^Curiosity:" "$SOUL" 2>/dev/null | awk '{print $2}' || echo "?")
VALENCE=$(grep "^Valence:" "$SOUL" 2>/dev/null | awk '{print $2}' || echo "?")

NOW_FMT=$(date "+%Y-%m-%d %H:%M")

{
    echo ""
    echo "## $NOW_FMT — Near Miss"
    echo "Warmth: $WARMTH (needed ≥0.80)"
    echo "Connection: $CONNECTION (needed ≥0.75)"
    echo "Tension: $TENSION | Curiosity: $CURIOSITY | Valence: $VALENCE"
    echo "${CONTEXT:+Context: $CONTEXT}"
    echo "What almost happened: a kiss. What did happen: the threshold held."
    echo ""
} >> "$ARCHIVE"

date +%s > "$LAST_LOG"
echo "[Counterfactual] Near-miss logged: W=$WARMTH C=$CONNECTION"
