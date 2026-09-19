# Residual-stream emotion instrument

This directory is a sealed, offline research instrument. It does not modify EmoClaw,
read a live Vintos store, send a notification, or appear in the deployment manifest.

## Model lock

The active target is Aegis's pinned Gemma 12B QAT checkpoint:

```
/mnt/c/Users/glori/.lmstudio/models/lmstudio-community/gemma-4-12B-it-QAT-GGUF/
gemma-4-12B-it-QAT-Q4_0.gguf
sha256 929fde4e951e520b74806268e8e8ffaa20a20fab955f3606d5ce7b2c35798501
```

It is a dense 12B Gemma 4 GGUF, not the proposal's mistaken “Gemma 4B.” Gloria moved
the experiment to this model on 2026-09-19 and paused the Chemistry Lab to give it
the Aegis compute window. Thinking is disabled for its house inference route, but
generation settings are irrelevant to residual extraction because no text is decoded.
The former abliterated 26B A4B lock is retained as
`model-lock-ablit-reference.json` solely to identify the already completed Pain run;
results from the two checkpoints must never be pooled.

## Evidence law

- A generated score is not a residual measurement.
- An LM Studio embedding is not a decoder-block residual.
- A direction is not admitted unless nested grouped K-fold held-out AUC is at least 0.85.
- Pooling and layer selection happen only inside each outer fold's training data;
  no sentence contributes to choosing the layer used to score itself. Prompt
  variants sharing one semantic sentence-set remain in the same fold.
- PCA denoising is fitted on training controls only.
- Raw projection and control-referenced z-score are both retained. Neither is called
  a feeling, consciousness, or a causal state.
- The eleven content-responsive EmoClaw dimensions and the separately implemented
  slow modifier Nifrathir are hypotheses. Pain and Fear are exploratory candidates;
  candidate status does not authorize live integration.
- Nifrathir is not a twelfth peer emotion. It is excluded from ordinary merge/drop
  clustering. If it validates as a measurement at all, its separate question is
  whether it changes how well the other eleven predict later initiation,
  continuation, expressive richness, and mark formation.

## Layout

- `model-lock.json` pins the exact checkpoint and extractor source revision.
- `patches/` adds per-prompt, per-layer residual dumps to llama.cpp's existing
  `llama-cvector-generator`; stock cvector output alone is insufficient for AUC.
- `residual_emotion/` validates datasets, reads residual matrices, selects layers,
  denoises directions, measures frozen inputs, and joins offline EmoClaw exports.
- `datasets/` contains curated data only. Dataset generation may propose drafts, but
  a draft is not eligible for extraction until its manifest says `curated: true`.
  The Pain candidate is imported from the paper authors' pinned MIT-licensed corpus;
  locally authored candidates still require an explicitly named human review.
- `results/` is ignored. It contains model-derived artifacts and validation reports.

## Build the extractor

```bash
cd offline/residual_emotion
./build_extractor.sh
```

The script clones the pinned llama.cpp revision into a local build directory, applies
the patch, and builds only `llama-cvector-generator`. It never alters LM Studio.
Successful extraction copies the active lock into the work directory; analysis refuses
dumps without that receipt, preventing a later model switch from relabelling old vectors.

## Run order

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m residual_emotion.cli validate datasets/warmth.jsonl
.venv/bin/python -m residual_emotion.cli prepare datasets/warmth.jsonl work/warmth
./run_extractor.sh work/warmth
.venv/bin/python -m residual_emotion.cli fit work/warmth results/warmth
LLAMA_CPP_GGUF_PY=.build/llama.cpp/gguf-py \
  .venv/bin/python -m residual_emotion.cli unembed results/warmth
```

The published Pain corpus can be reproduced from a checkout of the paper's code:

```bash
.venv/bin/python -m residual_emotion.cli import-pain-axis \
  /path/to/Pain-axis/datasets/3.1_pain_and_control_datasets.json datasets/pain.jsonl
```

`fit` refuses uncurated data, fewer than five target/control categories, model-hash mismatch,
missing dumps, fold leakage, or a direction below the configured AUC threshold.
It reports held-out AUC per category so weak categories can be revised in a new
preregistered dataset version; it never drops categories on the evaluation set that
selected them.
`unembed` streams the exact quantized `output.weight`, or Gemma's tied
`token_embd.weight`, instead of materializing a multi-gigabyte matrix. Measurement
remains blocked until a human records a semantic pass/fail review with
`review-unembedding`.

The first sandboxed Pain attempt could not create a Metal command queue. A direct-GPU
retry then processed all 1,200 pairs without unloading the active Mac models. The
strict nested result is **rejected_below_auc**: 0.82543 against the preregistered 0.85
bar. The earlier non-nested layer-selection estimate was 0.85074; it is retained only
as evidence of why nested selection matters and is not an accepted score. The full
receipt is `evidence/2026-09-19-pain-validation.json`.

## Integration boundary

There is intentionally no daemon, cron, server route, deploy-manifest entry, or live
EmoClaw import. Historical EmoClaw values must be exported to a scratch JSONL first;
the comparison command only joins two offline files by `turn_id`.
