#!/usr/bin/env bash
# frame-engine.sh — cron wrapper.
SCRIPTS="${HOME}/.vintos/workspace/scripts"
export PYTHONPATH="${SCRIPTS}:${PYTHONPATH}"
cd "${SCRIPTS}"
mkdir -p "${HOME}/.vintos/logs"
LOCK=""; [ -f "${HOME}/llm-lock.sh" ] && LOCK="bash ${HOME}/llm-lock.sh"
${LOCK} python3 "${SCRIPTS}/frame_engine.py"  >> "${HOME}/.vintos/logs/frame-engine.log" 2>&1
