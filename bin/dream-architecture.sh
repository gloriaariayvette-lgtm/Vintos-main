#!/usr/bin/env bash
# dream-architecture.sh — Generate private reverie. Nightly.
SCRIPTS="${HOME}/.vintos/workspace/scripts"
export PYTHONPATH="${SCRIPTS}:${PYTHONPATH}"
python3 -c "
import sys; sys.path.insert(0, '${SCRIPTS}')
from dream_poetry import generate_poem
generate_poem()
" >> "${HOME}/.vintos/logs/dreams.log" 2>&1
