#!/usr/bin/env bash
# One reload contract for Aegis Gemma. Thinking is an inference setting and is
# enforced by vintos_claude_shim.py; this door fixes the resident artifact.
set -euo pipefail
LMS="${VINTOS_LMS_CLI:-/mnt/c/Users/glori/.lmstudio/bin/lms.exe}"
VARIANT="google/gemma-4-12b-qat@q4_0"
IDENTIFIER="google/gemma-4-12b-qat"
exec "$LMS" load "$VARIANT" --identifier "$IDENTIFIER" --gpu max \
  --context-length 32000 --parallel 1 --no-speculative-draft-mtp --yes
