#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REV=e613ef2c81bae98d59850d061ac29e6e3e88cb00
SRC=${LLAMA_CPP_DIR:-$ROOT/.build/llama.cpp}

if ! command -v cmake >/dev/null 2>&1; then
  echo "cmake is required; no package manager was modified" >&2
  exit 2
fi
if [ ! -d "$SRC/.git" ]; then
  mkdir -p "$(dirname "$SRC")"
  git clone https://github.com/ggml-org/llama.cpp.git "$SRC"
fi
if ! git -C "$SRC" cat-file -e "$REV^{commit}" 2>/dev/null; then
  git -C "$SRC" fetch --depth 1 origin "$REV"
fi
CURRENT=$(git -C "$SRC" rev-parse HEAD)
if [ "$CURRENT" != "$REV" ]; then
  if ! git -C "$SRC" diff --quiet || ! git -C "$SRC" diff --cached --quiet; then
    echo "refusing to overwrite a dirty llama.cpp checkout: $SRC" >&2
    exit 3
  fi
  git -C "$SRC" checkout --detach "$REV"
fi
if git -C "$SRC" apply --reverse --check "$ROOT/patches/llama-cvector-residual-dump.patch" 2>/dev/null; then
  : # already patched at the pinned revision
else
  if ! git -C "$SRC" diff --quiet || ! git -C "$SRC" diff --cached --quiet; then
    echo "refusing to overwrite a dirty llama.cpp checkout: $SRC" >&2
    exit 3
  fi
  git -C "$SRC" apply "$ROOT/patches/llama-cvector-residual-dump.patch"
fi
cmake -S "$SRC" -B "$SRC/build" -DGGML_METAL=ON -DLLAMA_OPENSSL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=OFF
JOBS=$(sysctl -n hw.ncpu 2>/dev/null || echo 4)
cmake --build "$SRC/build" --target llama-cvector-generator -j "$JOBS"
echo "$SRC/build/bin/llama-cvector-generator"
