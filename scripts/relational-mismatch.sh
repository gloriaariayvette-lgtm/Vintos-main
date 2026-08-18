#!/usr/bin/env bash
# relational-mismatch.sh — cron wrapper.
SCRIPTS="${HOME}/.vintos/workspace/scripts"
export PYTHONPATH="${SCRIPTS}:${PYTHONPATH}"
cd "${SCRIPTS}"
mkdir -p "${HOME}/.vintos/logs"
LOCK=""; [ -f "${HOME}/llm-lock.sh" ] && LOCK="bash ${HOME}/llm-lock.sh"
${LOCK} python3 "${SCRIPTS}/relational_mismatch.py"  >> "${HOME}/.vintos/logs/relational-mismatch.log" 2>&1
