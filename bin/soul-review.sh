#!/usr/bin/env bash
# soul-review.sh — cron wrapper.
SCRIPTS="${HOME}/.vintos/workspace/scripts"
export PYTHONPATH="${SCRIPTS}:${PYTHONPATH}"
cd "${SCRIPTS}"
mkdir -p "${HOME}/.vintos/logs"
# the reviewer that reads his new half before it is written is the self-model's: the subconscious flag's model
_subcon=$(python3 "${SCRIPTS}/subcon_target.py" route "" "" 2>/dev/null) || _subcon=""
SUBCON_URL=$(printf '%s\n' "$_subcon" | sed -n 1p); SUBCON_MODEL=$(printf '%s\n' "$_subcon" | sed -n 2p); export SUBCON_URL SUBCON_MODEL
LOCK=""; [ -f "${HOME}/llm-lock.sh" ] && LOCK="bash ${HOME}/llm-lock.sh"
ADMIT=""; [ -f "${HOME}/.vintos/workspace/scripts/compute_admission.py" ] && ADMIT="python3 ${HOME}/.vintos/workspace/scripts/compute_admission.py run background --organ soul-review --"   # bounded admission: yields to a live turn (review 161)
${ADMIT} ${LOCK} python3 "${SCRIPTS}/soul_review.py"  >> "${HOME}/.vintos/logs/soul-review.log" 2>&1
