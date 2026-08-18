#!/usr/bin/env bash
# soul-review.sh — cron wrapper.
SCRIPTS="${HOME}/.vintos/workspace/scripts"
export PYTHONPATH="${SCRIPTS}:${PYTHONPATH}"
cd "${SCRIPTS}"
mkdir -p "${HOME}/.vintos/logs"
LOCK=""; [ -f "${HOME}/llm-lock.sh" ] && LOCK="bash ${HOME}/llm-lock.sh"
${LOCK} python3 "${SCRIPTS}/soul_review.py"  >> "${HOME}/.vintos/logs/soul-review.log" 2>&1
