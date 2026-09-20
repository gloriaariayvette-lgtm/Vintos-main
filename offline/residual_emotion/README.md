# Residual-stream emotion instrument

This directory is a sealed, offline research instrument. It does not modify EmoClaw,
read a live Vintos store, send a notification, or appear in the deployment manifest.

## Model lock

The active target is the pinned abliterated Gemma 4 26B-A4B checkpoint on Aegis:

```
/home/gloria/.vintos/models/residual-validation/
gemma-4-26B-A4B-it-uncensored-Q4_K_M.gguf
sha256 d482a5daba09e67c925359a1786c4c713d1c3bb35856d199cf296f7cf7bc6cb3
```

It is the 26B-total, A4B mixture-of-experts GGUF Gloria identified as the real target,
not the proposal's mistaken “Gemma 4B.” The 12B QAT and Q8 locks remain only as failed
Pain baselines; results from distinct checkpoints must never be pooled. Thinking settings
for a serving route are irrelevant to residual extraction because no text is decoded.

The paper-protocol replication selected the same abliterated lock with
`VINTOS_RESIDUAL_MODEL_LOCK`; it did not relabel the 12B dumps. Its fresh Aegis S2
feel-colon result was AUC 0.90675. The complete Mac dump then passed all six published
prompt ablations independently (AUC 0.86150–0.94425). See
`evidence/2026-09-20-ablit26-q4-paper-protocol.json` and
`evidence/2026-09-20-ablit26-q4-prompt-variants.json`.

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

## Dataset authoring boundary

The eleven content dimensions use a staged, resumable authoring lane. Sonnet 5 and
Grok 4.6 independently produce a three-times candidate pool; GPT-5.6 Sol reviews a
shuffled pool without author identity. A deterministic, versioned selector then narrows
the reviewer-eligible pool using fixed score weights, lexical-diversity pressure, stable
tie-breaking, and adaptive source quotas. Successfully parsed paid calls have local receipts and
each stage has a client-side cost cap. Concept-name leakage, wrong counts, duplicate IDs, incomplete
repairs, source collapse, and attempts to resurrect reviewer-rejected candidates fail
closed. OpenRouter's advertised Sonnet batch model rejected live Batch API submissions,
so the lane uses checkpointed ordinary calls unless that provider door is proven later.

The 20 September author/review pass produced 9,160 machine candidates. Blind review
exposed two defective matched controls rather than merely asking for more prose:
Dominance/3 now contrasts embodied authorship with rehearsed assertive behavior lacking
authorship, and Safety/5 contrasts permission to lower vigilance with fatigue-caused
lowered vigilance lacking protection. Fresh independent pools raised those cells from
11/16 and 5/16 eligible S1/S2 pairs to 66/87 and 84/81. Across the final 55 review
records, every version has at least 28 eligible choices for the required 20.

An attempted Fable adjudication was abandoned as an unnecessary and costly second machine
opinion. Two truncated responses predated transport-failure receipt persistence; OpenRouter's
provider total remains authoritative for that spend, and current code preserves future
paid-but-unparseable responses and their usage as rejected evidence. The reproducible selector
produced 2,200 base pairs at
`drafts/eleven-dimensions-base.jsonl` (SHA-256
`5cc871dbee503b4c5aeb50ca2fbe7b0539cf2f12956793d4ee2ad50e997c4705`). Every row is
still an `unreviewed_machine_draft`; no data is curated.

The final output of this lane is still only `unreviewed_machine_draft`. It cannot enter
extraction until a named human explicitly accepts every base semantic pair. Only then
does `expand-reviewed` create the six person/suffix variants and a curated manifest.
Nifrathir is excluded from this content-dimension authoring pass; its modifier dataset
and predictive validation remain separate.

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
.venv/bin/python -m residual_emotion.cli paper-variant-fit work/pain results/pain-variants.json
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
`paper-variant-fit` is an ablation scorer, not a way around dataset admission. It requires
the extraction-time model lock and scores each S1/S2 × suffix cell independently under
the same person-separated, shuffled sentence-set K-fold protocol.
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
