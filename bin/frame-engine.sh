#!/usr/bin/env bash
# frame-engine.sh — cron wrapper.
SCRIPTS="${HOME}/.vintos/workspace/scripts"
export PYTHONPATH="${SCRIPTS}:${PYTHONPATH}"
cd "${SCRIPTS}"
mkdir -p "${HOME}/.vintos/logs"
LOCK=""; [ -f "${HOME}/llm-lock.sh" ] && LOCK="bash ${HOME}/llm-lock.sh"
ADMIT=""; [ -f "${HOME}/.vintos/workspace/scripts/compute_admission.py" ] && ADMIT="python3 ${HOME}/.vintos/workspace/scripts/compute_admission.py run background --organ frame-engine --"   # bounded admission: yields to a live turn (review 161)
${ADMIT} ${LOCK} python3 "${SCRIPTS}/frame_engine.py"  >> "${HOME}/.vintos/logs/frame-engine.log" 2>&1
