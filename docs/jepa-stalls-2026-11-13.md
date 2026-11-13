# JEPA predictor stalls: diagnosis and fixes, 13 November

Scope: `jepa_predictor.py` and its audits only. Persistent carry, the persistence-sprint scoring and the
affective-state model are not touched; no sealed set is scored (the replay below stops on 30 October, before
the sealed week of 31 October). Counts only; no conversation text.

## What was measured (live data, 13 November, read-only)

* Shared checkpoint `7dce0795…`, trained 21 September 04:15. Since then: **159** admitted exchanges, **72**
  forecast rows on that checkpoint. Only **63** of the 159 had a fresh forecast before them.
* Calibration join: 64 rows (gloria 63, self 56). The retrain gate reads the latest third: **21 < 30**.
* Ranking (unchanged instrument): the shared Gloria head's embedding **does** rank the true next turn above
  every control (MRR .436 vs strongest .343, day-block CI [.036, .151], n=63, `EVIDENCE_OF_PREDICTION`).
  What fails is its **confidence**: Spearman(conf, error) −.017 on the 21 held-out rows (control +.092).
* No label leakage: 0 of 63 Gloria targets had arrived before their forecast. Checkpoint identity is
  consistent on every row. The encoder snapshot has not changed since April (no embedding drift).

## Root causes

1. **Retrain starves on forecast cadence, not on conversation.** Forecasts are written only by the two-hourly
   cron (`50 */2`) and only when the window changed (`jepa_predictor.py`, `unchanged_forecast`). Each forecast
   joins one target (`jepa_calibration_audit.py`, `joined_rows`: first turn after the forecast), so the 96
   exchanges with no preceding forecast never become outcomes. The gate needs the latest third ≥ 30, i.e. about
   89 joined outcomes (`jepa_predictor.py`, `retrain_readiness`; `calibration.holdout`).
2. **Gloria confidence is non-monotone.** (a) Wrong target window: because forecasts come from the cron after
   the conversation goes quiet, 57% of joined targets arrive more than 6 h later (median 10.2 h): a later
   sitting's opener, which a six-turn context's variance cannot know. Gap correlates with error (+.21).
   (b) The production head is trained full-batch for 300 epochs with no held-out epoch selection
   (`train`, `validation_fraction=0.0`), so its log-variance can describe training residuals. (c) Since
   22 October the served Gloria triple is the anchored readout, but the daily audit scores only the
   superseded shared head (`legacy_gloria`); the served confidence was never calibration-audited.
3. **Self unmeasured.** `jepa_calibration_audit.py` marked the whole axis unmeasured if any held-out row had a
   placeholder confidence. 9 of 56 do: the shared self confidence is null when the cron forecasts a window
   more than a day old (`_live_in_window`).

## Fixes in this branch

* **After-reply forecasts.** The on-message job the server already launches for each message of hers at the
  chat/full and avatar doors now, after its own forecast and with its lock released, waits (no encoder held
  for the wait; at most 900 s) for his reply to land in the chat record, then makes the production and shadow
  forecasts with the same encoder (`jepa_predictor.after_reply`, `jepa_self_head.after_reply_job`). It skips
  when she has written again. The latent stream and the LAM cascade are left to the cron. A file lock
  serializes forecast writers. History rows record `trigger` and `context_last_role`. Since 1 November 35 of
  40 exchanges came through those doors. No threshold is lowered.
* **Targets she had already sent are not outcomes.** Both joiners skip a Gloria target whose window ended on
  her message, or which the on-message log shows arriving before the forecast (0 such rows today; after-reply
  forecasting makes the race possible).
* **Self measured.** An axis is scored on rows whose confidence was qualified when the forecast was made
  (decided before the outcome); the number left out is reported. Self is now measured.
* **Served Gloria head measured** (`served_gloria` in `jepa-calibration.json`), beside the shared head.
* **Pre-registered evaluations** (below).

## Pre-registration P1 (prospective; binding form is `PREREGISTERED` in `jepa_calibration_audit.py`)

Population: forecasts with `trigger == "after_reply"`, on or after 13 November, distinct Gloria targets she had
not yet sent. The first 30 by time, evaluated once. Heads: the served anchored readout and the shared
checkpoint. Pass: Spearman(confidence, cosine error) ≤ −0.20 and ≤ control − 0.10 (decode similarity; the
calibration criteria v2 numbers). Nothing was tuned on after-reply rows; none exist before deploy.

## Pre-registration R1 (replay, written before it was run)

Question: is the shared head's confidence failure the target window, or its training procedure?
Data: admitted exchanges with her words after 21 September 04:15 and **before 31 October 00:00** (the sealed
persistence week is not touched). One row per distinct Gloria text. Input: the six turns before the exchange,
legacy schema, the one-day rule as in `build_pairs`. This is the after-reply regime (window ends on his reply).
Models: M0 the live 21 September checkpoint, unchanged; M1 a replica trained by the production procedure on
`training_turns()` before 21 September 04:15; M2 the same data with `validation_fraction=0.2` (the
held-out-epoch path the shadow uses). Metric: Spearman(−log-variance, cosine error); control: decode
similarity (best cosine to her last 12 turns). Pass as in P1. Reading: M0 passes → the window was the cause
and after-reply forecasting is the fix; M2 passes and M1 fails → held-out selection belongs in the production
train; neither → the shared head's confidence is not repaired by either, and the served readout is judged by P1.

## Results

(filled in after R1 ran; see below)
