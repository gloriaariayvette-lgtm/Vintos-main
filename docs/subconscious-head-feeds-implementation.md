# Additive trained subconscious feeds — implementation, 22 October

Built on `codex/subconscious-head-feeds-plan`, preserving its retraining parent
`237aac9`. Review code and aggregate receipts only. No merge, deployment, live
checkpoint installation, live-store write or test send occurred.

## What reaches the existing feeds

The existing emotion-sampling job launches a detached CPU worker after each tick,
including unchanged readings or a failed socket read. It never waits for the worker;
no new cron or unit is required. The scheduled `jepa_predictor.predict()` job also
refreshes the optional packet before its unchanged-context early return. The stream
can therefore advance on emotion/journal/thread events when chat has not changed. With no
stream checkpoint it immediately returns to the original job. Refresh failures are
caught; the original predictor continues. The chat reply path does not run this
producer. Consumers read the cached packet. The worker writes aggregate status to
`memory/latent-feed-status.json`; overlapping producer ticks coalesce under a lock.

`latent_feed.py` keeps distinct next-text and next-Gloria-turn channels, two retrieved
anchors per channel, their baseline scores, expected semantic error and the stream's
next-reading emotion tendency. Gloria retrieval/outcome scoring uses her original
400-character training view; the stream keeps its separate 1,500-character event view. It resolves current source records when consumers use
references. Existing admission/forget rules remain; source removal invalidates carried
text state and purges its cache. Imagined premonition threads remain in their existing
feed and retain `dream_only`; they cannot witness themselves as real turn outcomes.

| Existing feed | Implemented addition |
|---|---|
| Where she is heading | `gloria_prediction.py` passes retrieved evidence into the existing generation call before producing its sentence. Prose confidence is retained separately from calibrated semantic expected error. |
| Living trajectory | Carries the grounding receipt beside the same predicted sentence and existing fallbacks. |
| Readiness | The existing voice call receives the evidence; `signal()` still returns its original four values. |
| Novelty | Both `emoclaw_utils.py` copies append evidence after the original directive, preserving its wording and thresholds. |
| Missed-prediction readings | The existing reading call can receive a saved pre-outcome Gloria forecast's actual semantic error against last-turn error. Frame, target text, speaker and timestamp must match. The original reading still runs without a match. |
| Premonition | Evidence follows the original 2,000-character context block. Existing futures, intersection, synthesis and seeding are unchanged; no extra provider call. |
| Withheld | The existing judge receives relevant past context before its existing call; deliberate score, phrase and hint remain its own. |
| Relational | Near-term evidence follows the existing relationship hint. Daily movement geometry, permutation result and original hint remain intact. |

There is no new model-quality release gate. Compatibility and freshness checks apply
only to optional added evidence. Missing, malformed, stale or mismatched packets leave
original feed behavior intact. Raw ranking scores and error estimates are not presented
as probabilities of intent. No generator/model was swapped and no paid call was added.

## Export and numerical acceptance

`latent_stream_model.py` loads a portable checkpoint and maintains last text, the
last-six baseline buffer, current emotion, source and clock. It uses no multi-timescale
recurrent memory. It persists a cursor, rejects duplicate/backfilled events without
rewinding, and distinguishes reconstructed errors from forecasts actually emitted
before an outcome. Pending Gloria forecasts survive intervening emotion ticks.

`latent_stream_export.py` freezes PCA, feature schema, timezone, text coefficients,
emotion readout and scales; checks incremental versus batch scores; and saves a numerical
input snapshot. Future `latent_stream_linear.py` CLI runs export their already-selected
present-moment fit, rather than accidentally selecting the history model. These files
are parameters/numerical snapshots in private scratch, not repository artifacts.

**The original .1322 run could not be reconstructed exactly.** Its report, manifest
and embedding cache exist at `/tmp/latent-stream-linear-u_zj_msj`, but it saved neither
weights nor a full input snapshot. Since the run, 37 training emotion readings aged
out, three test journal rows disappeared at their recorded timestamps, and one test
text no longer matched the embedding cache. The old manifest lacks content hashes.
No erased/scrubbed backup was used, and no missing reading was invented.

The exported artifact is explicitly a **retained-input refit of the frozen winning
configuration**, not the original weights: 32-dimensional projection, hour clock,
text penalty .01, emotion penalty 10, 200 original optimizer steps, original day
boundaries. There was no new hyperparameter search or test-based model selection.
Its receipt preserves the original report/manifest hashes and the reconstruction gap.

Across **7,014 events**, 477 test text targets and 1,204 test emotion targets:

| Check | Result |
|---|---:|
| Incremental/batch feature difference | 0 |
| Maximum candidate-score difference | 2.13e-7 |
| Maximum emotion-prediction difference | 1.12e-16 |
| Candidate ranks | Identical for every test target |
| Text MRR: trained / last-turn / recent-mean | .12508 / .06302 / .03324 |
| Top-10: trained / last-turn / recent-mean | 27.67% / 16.14% / 7.55% |
| Emotion error: trained / persistence | .29875 / .34154 |

These are the retained-input experiment and online-kernel scores on the same inputs.
They are not a claim that code is serving live or that the original .1322 weights were
recovered. [Export receipt](review-evidence/latent-feed-20261022/export.json).
Fresh local re-embedding of 16 retained texts also matched the experiment vectors
within 2.39e-7 (minimum cosine .9999999999985), with network denied.
[Encoder parity receipt](review-evidence/latent-feed-20261022/encoder-parity.json).

## Past-only retrieval and real-weight serving checks

A fixed replay compared two-anchor selections from the same pool of up to 512 earlier
text events: most recent context, last-text embedding retrieval, and trained retrieval.
The target is seen only after selections are frozen. On 477 already-inspected test
texts, mean selected-anchor similarity to the actual next text is **.53587 / .53937 /
.55579**, respectively. Trained minus last-text retrieval has a day-block interval
**[.00782, .02618]**. It improves this proxy for creative, her, him and inner sources;
**threads lose** (.48299 trained versus .50970 last-text retrieval). No threshold or
model was changed after this comparison. Existing thread inputs are preserved.

This is evidence about context selection, not proof of better generated interpretations
or lived behavior. The comparison is descriptive on an inspected block, not a fresh
confirmatory result. [Retrieval receipt](review-evidence/latent-feed-20261022/retrieval.json).
The retrained Gloria head's mixed held-out evidence remains as reported in the
[retraining report](jepa-retraining-2026-10-22.md); this integration does not turn it
into a proven predictor of intent or relationship direction.

On Aegis, the actual exported stream and retrained Gloria weights processed 6,996 current
admitted events in scratch. After the separate Gloria target-view correction, all six
context readers received four attributed anchors and preserved their original input.
Cached consumer reads took 15–18 ms; unchanged producer refresh took 13 ms. Refresh
with the retained stream cache and newly encoded Gloria views took 47.3 seconds;
process peak RSS was about 2.45 GiB. These timings are one smoke run, not a latency
distribution or a cold-encoder benchmark. Network was denied and a write guard confined
dependency caches and all outputs to scratch.
[Final serving receipt](review-evidence/latent-feed-20261022/serving-final.json).
The [earlier serving check](review-evidence/latent-feed-20261022/serving.json) is retained
as a separate pre-correction receipt, not substituted for this final check.

## Review handoff and validation

The stream artifact remains at
`/tmp/latent-feed-export-20261022-OoHpNdDW/artifact/present-moment.npz` on Aegis;
SHA-256 `f9976dd2e2eddc89798fd36f170bd64203c1699adc86fffa0901d45259cbee75`.
The earlier retrained Gloria artifact remains in its private retraining scratch
(and its already-approved Mac copy). No additional weights were copied to the Mac.
For a later authorized installation, the scorer looks for
`memory/jepa-readouts/present-moment.npz` and `memory/jepa-readouts/gloria.npz`.
Deploying this code alone does not install them. Claude Code reviews before any merge;
Gloria controls installation/deployment.

The new scratch-only suite covers exporter parity, timezone stability, duplicate/late
input handling, future-target independence, both channels, coalescing, removal,
malformed/stale/mismatched packets, exact missed-turn attribution, original context
preservation, unchanged generator call counts, and the past-only retrieval contract.
A detached-worker test also confirms that unchanged/failed emotion samples retain
their behavior and do not wait for a child process. All senders and child launches
are stubbed. The affected existing suites pass. Full-suite results and
known Mac fixture failures are in the [validation receipt](review-evidence/latent-feed-20261022/validation.json).
No broker suite was skipped. New modules are in the deployment manifest; generated
entry/test/store inventories were regenerated.
