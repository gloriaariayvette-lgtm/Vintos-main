# JEPA decode-similarity confidence, 14 November

Gloria approved decode similarity as the predictor's confidence signal, on the R1 replay (decode similarity
−.535 / −.770 vs the live confidence +.236 / +.357, docs/jepa-stalls-2026-11-13.md) and the test-time-training
replay (frozen decode similarity −.769, branch `claude/jepa-ttt` 078b4317). Both measured the **shared
checkpoint's** forecast. Since 22 October the served Gloria forecast is the anchored readout, and the served
self forecast is the self head (`self-head-v2`), so the change was replayed on the heads actually served first.
Counts only; no conversation text; nothing at or after 31 October was read (the sealed persistence week).

## Replay RD (pre-registered in 039b3de9 before it ran; [prereg](review-evidence/jepa-decode-confidence-20261114/prereg.json), [result](review-evidence/jepa-decode-confidence-20261114/result.json))

| Head (served) | Rows | Decode similarity vs error | Control | Pass |
|---|---|---:|---:|:-:|
| Gloria: anchored readout | 46, 14–26 Oct (its own test block onward, never fit) | −.117 | readout confidence −.240 | **no** |
| Self: self-head-v2, ahead | 30, 16–26 Oct (after its training) | **−.476** | coherence −.114 | **yes** |

Bars: n ≥ 30, Spearman ≤ −0.20, beats the control by ≥ 0.10, negative slope. MRR of the served forecasts
(.138 Gloria, .139 self) is untouched: the forecast embeddings are byte-identical with and without the change
(also asserted by the test). Self second half: −.277 vs +.025.

Why Gloria fails: the readout's forecast sits on her latest turns (decode similarity median .992), so nearness
to her recent turns no longer separates good forecasts from bad ones. The evidence Gloria approved on is real,
but for a forecast that is no longer served.

## What changed

* **Self confidence is decode similarity** for the tested self checkpoint (sha a0a77ba0…, ahead mode): the
  percentile of the forecast's decode similarity among the 30 replay rows, in [0, 1], higher = more confident,
  the same form as the self head's own confidence (a coherence percentile). The old value stays beside it as
  `legacy_confidence` (null: it was the 0.5 placeholder), with `confidence_source: decode-similarity-v1`, on
  `jepa-prediction.json` and every history row. `confidence_placeholder` is now false and the self
  qualification reads `qualified`. Another self checkpoint keeps its own confidence.
* **Gloria is held.** Top-level and Gloria confidence are exactly what they were.
* Consumers checked: the self confidence's only reader is `emoclaw_utils._novelty_directive` (HI_CONF 0.70, a
  placeholder read as 0.0). It now gets a measured number in the same direction; a percentile keeps 0.70 meaning
  "more certain than usual" (the registered 1 − error/2 form would put every forecast above 0.70; see the
  [addendum](review-evidence/jepa-decode-confidence-20261114/addendum.json)). `latent_preparation`,
  `gloria_prediction`, `calibration.verdict`, the retrain gate and the ranking audits read the Gloria triple, the
  shared-checkpoint rows (`legacy_gloria` / `legacy_self`) or embeddings only: unchanged.

## Prospective test (PREREGISTERED_DECODE, computed by the daily audit into `jepa-calibration.json` → `preregistered_decode`)

* **Self:** the first 30 distinct his-reply targets of forecasts serving the decode confidence (said after the
  forecast), scored once: Spearman ≤ −0.20 and ≤ coherence − 0.10.
* **Gloria (shadow):** the first 30 after-reply targets of rows written by this code: decode similarity against
  the served readout confidence, same bars. A pass is evidence for Gloria to decide on; nothing switches by itself.

## Deploying

Two scripts change, both already in `deploy-atelier.sh`: `jepa_predictor.py`, `jepa_calibration_audit.py`. No
weights, crontab, service or restart. After deploy: `jepa-prediction.json` → `self.confidence_source` reads
`decode-similarity-v1`; `jepa-calibration.json` → `preregistered_decode` reads COLLECTING until 30 targets.
