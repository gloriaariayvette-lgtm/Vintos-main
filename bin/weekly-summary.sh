#!/usr/bin/env bash
# weekly-summary.sh — cron wrapper.
SCRIPTS="${HOME}/.vintos/workspace/scripts"
export PYTHONPATH="${SCRIPTS}:${PYTHONPATH}"
cd "${SCRIPTS}"
mkdir -p "${HOME}/.vintos/logs"
LOCK=""; [ -f "${HOME}/llm-lock.sh" ] && LOCK="bash ${HOME}/llm-lock.sh"
ADMIT=""; [ -f "${HOME}/.vintos/workspace/scripts/compute_admission.py" ] && ADMIT="python3 ${HOME}/.vintos/workspace/scripts/compute_admission.py run background --organ weekly-summary --"   # bounded admission: yields to a live turn (review 161)
${ADMIT} ${LOCK} python3 "${SCRIPTS}/weekly_summary.py"  >> "${HOME}/.vintos/logs/weekly-summary.log" 2>&1
