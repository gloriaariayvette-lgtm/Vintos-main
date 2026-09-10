#!/usr/bin/env bash
# value-map-update.sh — cron wrapper.
SCRIPTS="${HOME}/.vintos/workspace/scripts"
export PYTHONPATH="${SCRIPTS}:${PYTHONPATH}"
cd "${SCRIPTS}"
mkdir -p "${HOME}/.vintos/logs"
LOCK=""; [ -f "${HOME}/llm-lock.sh" ] && LOCK="bash ${HOME}/llm-lock.sh"
ADMIT=""; [ -f "${HOME}/.vintos/workspace/scripts/compute_admission.py" ] && ADMIT="python3 ${HOME}/.vintos/workspace/scripts/compute_admission.py run background --organ value-map-update --"   # bounded admission: yields to a live turn (review 161)
${ADMIT} ${LOCK} python3 "${SCRIPTS}/value_map.py"  >> "${HOME}/.vintos/logs/value-map.log" 2>&1
