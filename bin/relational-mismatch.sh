#!/usr/bin/env bash
# relational-mismatch.sh — cron wrapper (weekly).
# predict/compare need a message and run from the chat paths; the weekly job is `sweep`, which retires an
# open prediction too old for any reply to answer. Without a command every run printed the usage and failed.
SCRIPTS="${HOME}/.vintos/workspace/scripts"
export PYTHONPATH="${SCRIPTS}:${PYTHONPATH}"
cd "${SCRIPTS}"
mkdir -p "${HOME}/.vintos/logs"
LOCK=""; [ -f "${HOME}/llm-lock.sh" ] && LOCK="bash ${HOME}/llm-lock.sh"
ADMIT=""; [ -f "${HOME}/.vintos/workspace/scripts/compute_admission.py" ] && ADMIT="python3 ${HOME}/.vintos/workspace/scripts/compute_admission.py run background --organ relational-mismatch --"   # bounded admission: yields to a live turn (review 161)
${ADMIT} ${LOCK} python3 "${SCRIPTS}/relational_mismatch.py" sweep >> "${HOME}/.vintos/logs/relational-mismatch.log" 2>&1
