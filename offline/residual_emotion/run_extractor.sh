#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORK=${1:?usage: run_extractor.sh WORK_DIR}
LOCK=${VINTOS_RESIDUAL_MODEL_LOCK:-$ROOT/model-lock.json}
MODEL=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["path"])' "$LOCK")
EXPECTED=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$LOCK")
ACTUAL=$(shasum -a 256 "$MODEL" | awk '{print $1}')
[ "$ACTUAL" = "$EXPECTED" ] || { echo "model hash mismatch" >&2; exit 3; }

BIN=${LLAMA_CVECTOR_BIN:-$ROOT/.build/llama.cpp/build/bin/llama-cvector-generator}
GPU_LAYERS=${LLAMA_GPU_LAYERS:-99}
CONTEXT=${LLAMA_CONTEXT:-8192}
BATCH=${LLAMA_BATCH:-8192}
[ -x "$BIN" ] || { echo "extractor missing; run ./build_extractor.sh" >&2; exit 4; }
mkdir -p "$WORK/dumps"
VINTOS_RESIDUAL_DUMP="$WORK/dumps" "$BIN" \
  -m "$MODEL" -ngl "$GPU_LAYERS" -c "$CONTEXT" -b "$BATCH" -ub "$BATCH" --method mean \
  --positive-file "$WORK/target.txt" --negative-file "$WORK/control.txt" \
  -o "$WORK/unused-control-vector.gguf"
cp "$LOCK" "$WORK/extraction-model-lock.json.tmp"
mv "$WORK/extraction-model-lock.json.tmp" "$WORK/extraction-model-lock.json"
