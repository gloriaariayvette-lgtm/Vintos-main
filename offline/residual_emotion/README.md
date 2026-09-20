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
The Aegis Gemma 12B path has a completed 12-pair functional smoke receipt at
`evidence/2026-09-19-gemma12-smoke.json`: all 48 final/mean target/control dumps
were finite with shape `[12, 48, 3840]` and nonzero target/control separation.
That proves extraction functionality, not a direction. Aegis currently has no CUDA
compiler, so its pinned extractor builds CPU-only. The deliberately long full run has
now also completed: Pain was rejected at nested held-out AUC `0.51330 ± 0.15155`
against the `0.85` bar. Pooling/layer choices varied across outer folds and exact
unembedding was semantically diffuse. See
`evidence/2026-09-19-gemma12-pain-validation.json`.

The requested Q8 replication also completed all 1,200 pairs. Every one of its
4,800 residual dumps passed the 48 x 3,840 shape, finite-value, and nonzero checks.
Nested grouped validation again rejected Pain: `0.66649 ± 0.18394`, below the
same `0.85` bar, with outer-fold AUCs ranging from `0.37457` to `0.93601` and
pooling/layer selection varying across folds. This is higher than the QAT-Q4
result, but it is not a clean quantization experiment: the available Q8 GGUF is
converted from standard Gemma 4 12B Instruct while the Q4 baseline is Google's
QAT-source checkpoint. The delta therefore cannot be attributed to precision
alone. See `model-lock-gemma12-q8.json` and
`evidence/2026-09-19-gemma12-q8-pain-validation.json`.

A known-good Mac replication then isolated the extraction path.  Native arm64
PyTorch/Transformers loaded `google/gemma-2-2b` revision `c5ebcd40...` at fp16 on
Metal and read each decoder block's final-token output directly from
`output_hidden_states=True`; the full 2,400 sentences extracted in 10.3 seconds.
The pinned paper protocol replicated at AUC `0.96700` (layer 23; first person
`0.96550`, third person `0.96850`).  Our stricter, different experiment still
failed at `0.68030 ± 0.19466`: it combines S1/S2, both persons, and all suffix
ablations into one direction and nests layer selection.  The paper instead scores
S2 colon prompts separately by person and averages their five-fold layer curves.
Therefore llama.cpp/quantization were not the sole cause, and the stricter score
must not be described as a failure to reproduce the paper.  See
`evidence/2026-09-20-gemma2-2b-native-replication.json`.

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
