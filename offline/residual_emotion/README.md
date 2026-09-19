# Residual-stream emotion instrument

This directory is a sealed, offline research instrument. It does not modify EmoClaw,
read a live Vintos store, send a notification, or appear in the deployment manifest.

## Model lock

The only target is Gloria's abliterated checkpoint:

```
/Users/kevin/.lmstudio/models/TrevorJS/gemma-4-26B-A4B-it-uncensored-GGUF/
gemma-4-26B-A4B-it-uncensored-Q4_K_M.gguf
sha256 d482a5daba09e67c925359a1786c4c713d1c3bb35856d199cf296f7cf7bc6cb3
```

It is a 26B A4B mixture-of-experts GGUF, not a 4B Gemma. The Pain Axis paper tested
dense models. Results here are therefore an explicit replication/extension question,
not an assumed transfer of the paper's findings.

## Evidence law

- A generated score is not a residual measurement.
- An LM Studio embedding is not a decoder-block residual.
- A direction is not admitted unless grouped K-fold held-out AUC is at least 0.85.
- Layer selection happens inside held-out evaluation; prompt variants sharing one
  semantic sentence-set remain in the same fold.
- PCA denoising is fitted on training controls only.
- Raw projection and control-referenced z-score are both retained. Neither is called
  a feeling, consciousness, or a causal state.
- The current eleven EmoClaw dimensions are hypotheses. No twelfth dimension is
  invented to satisfy an old count.

## Layout

- `model-lock.json` pins the exact checkpoint and extractor source revision.
- `patches/` adds per-prompt, per-layer residual dumps to llama.cpp's existing
  `llama-cvector-generator`; stock cvector output alone is insufficient for AUC.
- `residual_emotion/` validates datasets, reads residual matrices, selects layers,
  denoises directions, measures frozen inputs, and joins offline EmoClaw exports.
- `datasets/` contains curated data only. Dataset generation may propose drafts, but
  a draft is not eligible for extraction until its manifest says `curated: true`.
- `results/` is ignored. It contains model-derived artifacts and validation reports.

## Build the extractor

```bash
cd offline/residual_emotion
./build_extractor.sh
```

The script clones the pinned llama.cpp revision into a local build directory, applies
the patch, and builds only `llama-cvector-generator`. It never alters LM Studio.

## Run order

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m residual_emotion.cli validate datasets/warmth.jsonl
.venv/bin/python -m residual_emotion.cli prepare datasets/warmth.jsonl work/warmth
./run_extractor.sh work/warmth
.venv/bin/python -m residual_emotion.cli fit work/warmth results/warmth
```

`fit` refuses uncurated data, incomplete category coverage, model-hash mismatch,
missing dumps, fold leakage, or a direction below the configured AUC threshold.

## Integration boundary

There is intentionally no daemon, cron, server route, deploy-manifest entry, or live
EmoClaw import. Historical EmoClaw values must be exported to a scratch JSONL first;
the comparison command only joins two offline files by `turn_id`.
