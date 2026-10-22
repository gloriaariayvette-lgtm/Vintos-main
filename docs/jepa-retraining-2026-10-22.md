# Trained readouts and restored subconscious feeds — 22 October

This follow-up supersedes the feed restrictions in the earlier JEPA review. It restores
withheld and relational hints, the Gloria trajectory line, readiness, the novelty
directive, readings from missed predictions, and premonition seeding. The attribution,
per-speaker counting, retained presence labels, scheduled self evaluation and corrected
drift residuals remain. No live store, checkpoint, service or prompt was changed.

Actual CPU training completed on Aegis, using its existing frozen encoder, with no
paid calls. The training run denied network calls and writes outside its scratch
directory. Five parameter files were produced and, with Gloria's explicit approval,
copied to private Mac scratch. Parameter hashes match. They are **not in Git**.

## Measurements and limits

Training uses clean admitted exchanges before October 1. Model selection uses October
1–8; confidence fitting uses October 9–12; evaluation uses October 13–22. Targets
actually available in the last block fall on October 14–21. Exact duplicate target
texts count once. This is the previously inspected October benchmark, not a newly
untouched discovery set. Test results did not choose weights, hyperparameters or
confidence direction. Test-target perturbation leaves all selected weights, PCA and
confidence parameters unchanged in the regression suite.

Candidate designs were fixed before evaluation: train-only 16/32-dimensional target
projections; baseline mixtures; ridge penalties 1/10/100; and the latent stream's
anchored contrastive objective at the same penalties. Validation MRR selects the
readout, with cosine error as tie breaker. Ridge won all three selections. There was
no second test-driven parameter search. Confidence is a separate ridge estimate of
cosine error, expressed as `1 - expected_error / 2`; it is **not a probability that a
specific future sentence is correct**.

| Head | Test n | New MRR | Last-turn MRR | Recent-mean MRR | New cosine error | Last-turn error | Recent-mean error |
|---|---:|---:|---:|---:|---:|---:|---:|
| Gloria | 41 | .1496 | .1373 | .0693 | .3841 | .4326 | .3035 |
| Self ahead | 46 | .2459 | .2240 | .0946 | .2262 | .2362 | .2063 |
| Self on-message | 46 | .2544 | .2240 | .0946 | .2214 | .2362 | .2063 |

Ranks use all unique same-speaker targets in the evaluated block, with conservative
ties; they are not directly comparable to six-candidate audit MRR. Each baseline sees
the same preceding history. Model inputs use the preceding event's clock, never the
future target's time. On-message additionally sees the arrived message.

**These are ranking point-estimate gains, not a demonstrated win on every measure.**
The day-block MRR intervals versus last-turn include zero: Gloria [-.0278, .0347],
self ahead [-.0169, .0593], on-message [-.0126, .0652]. Recent-mean still wins cosine
error. Calling all heads decisively accurate would overstate this run.

Before/after: the existing shared Gloria checkpoint scores MRR .1055 and cosine
error .4382 on the same 41 targets, versus .1496 and .3841 for the new readout.
The old independent self checkpoint trained on October 16. Only **four unique target
texts** remain on whole later days (five raw exchanges before exact-text deduplication).
On those four, ahead MRR changes .3958 → .4375, but cosine error worsens .2351 → .2933.
On-message MRR stays .4375 and error worsens .1925 → .2931. The old self checkpoint
therefore remains a serious comparator; this experiment does **not** establish that
its replacement is better. The initial same-day-inclusive comparison is preserved
separately in the receipt, not presented as held-out days.

Confidence/error Spearman on the later evaluation block is **−.316 Gloria, −.088
self ahead, −.163 on-message**: the direction is now correct, but self discrimination
is weak. Gloria's low/middle/high confidence bins have errors .434/.371/.344.
Calibration uses just 14/15 examples; output confidence varies only slightly. Its
error-estimation MSE improves only slightly over a constant. This is a calibrated
error estimate with limited evidence, not a new release claim for the old shared audit.

LAM now forecasts **600 seconds ahead**, accepting a measurement up to 120 seconds
late and skipping larger gaps. Inputs are the state, prior trend, already-observed
conversation and cutoff clock. Targets crossing a split boundary are excluded.
On 520 test transitions, MSE is **.0003323 versus .0003564 persistence** (6.8% lower),
with day-block difference interval **[-.00003673, -.00001024]**. Per-axis calibration
RMSE is fitted only on the separate calibration block and is included in its output.

Presence retains all **15** available rubric labels, without notes or message text.
Fourteen join to admitted outcomes (ID first, otherwise unique same-second match).
Eleven train the fit; validation, calibration and test each contain one later label.
Test MAE .09264 versus training mean .09255 and persistence .10300 does not establish
an accuracy gain. The fitted presence artifact reports this limitation and leaves
confidence null rather than inventing a probability. Missing historic labels were
not reconstructed or treated as measured truth.

## Existing feed wiring

`jepa_predictor.py` loads the new Gloria embedding/confidence from `jepa-readouts/gloria.npz`;
`jepa_self_head.forecast()` loads ahead/on-message replacements through its existing
entrances. Existing checkpoints remain the fallback when replacement files are absent.
Output field names used by trajectory, readiness, novelty, withheld and relational
readers remain intact. The added prompt gates from the previous branch are removed.
The new Gloria receipt is exposed alongside its signal; it does not mute a feed.

New shared-head overrides retain `legacy_gloria`/`legacy_self` with the shared weight
identity. The shared audits evaluate those original weights; separate readout ranking
receipts use the replacement identities. The existing daily ranking task runs both
self evaluation and readout auditing. Copied artifacts cannot silently borrow another
checkpoint's ranking results.

Presence consumes its retained labels and its own scalar readout. The existing JEPA
forecast job also writes the fixed-horizon `lam-forecast.json` when the reviewed LAM
checkpoint is installed; Living Trajectory already reads that path. No new cron is
needed. The real scratch serving check produced Gloria, ahead self, on-message self,
presence and a 600-second cascade through these entry points, with no live writes.
Existing hint behavior is covered by the restored original suites.

The new scripts are in the deployment manifest. **Deploying code alone does not install
these weights.** Review must consider the mixed self/presence results before choosing
which artifacts to install. This branch does not silently promote a weak result, and
it does not remove any existing subconscious feed while a decision is pending.

## Artifacts and reproduction

Aegis scratch: `/tmp/jepa-retrain-20261022-6pqxgl59/checkpoints/`.
Private Mac copies: sibling `review-evidence/retrained-checkpoints/` outside this
checkout. `gloria.npz`, `self_ahead.npz`, `self_on_message.npz`, `presence.npz`, and
`lam-linear.npz` are present in both locations. The retained minimal presence label
history stays in Aegis scratch; a future authorized installation must merge labels,
not replace the live archive. No weight or label archive is committed.

[Aggregate measurements](review-evidence/jepa-retrain-20261022/measurements.json),
[checkpoint hashes](review-evidence/jepa-retrain-20261022/checkpoint-manifest.json), and
[test results](review-evidence/jepa-retrain-20261022/validation.json) contain no live
conversation or memory content. Training-source hashes identify the exact scratch
code used for the fit; later serving and comparison corrections did not change its
text/LAM weights. The corrected presence join produced the final presence checkpoint.

Reproduction uses the existing CPU environment, with source scripts from this branch:
`python3 scripts/jepa_retrain.py --out <new-scratch-directory>`. The command refuses
outputs inside the live workspace or reuse of an already evaluated output directory.
It reads admitted sources through the current evidence adapter, excludes forget/erase
backups, writes weights only to the explicit output and does not install them.

Validation: **469 suites, 466 pass, 3 failures** already reproduced on the parent and
deploy baseline: unavailable PDF utility/form-feed fixture, sandbox-denied unreserved
localhost port, and GNU-only grep syntax on macOS. The 13 affected suites passed, and
four affected suites passed again after the scratch/cutoff safeguards, followed by six
passing final input/identity/report checks. No test
sent anything or accessed live stores. No deployment occurred.
