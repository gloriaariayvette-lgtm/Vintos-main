# JEPA heads and latent organs: 22 October review

Review branch: `codex/jepa-heads-audit-repair`, based on `54b2910` of
`claude/device-visuals-2026-10-13`. No deployment, live-store writes, model swaps,
training runs, or paid model calls. Aegis evaluation used the installed frozen
encoder on CPU, offline, with review code loaded into process memory. Reports
were saved only in local scratch. Gloria explicitly authorized review of her head.

**First accuracy experiment: the existing independent on-message self head,
rebuilt from admitted sources, selected by next-turn ranking.** It already has
useful prospective cosine evidence. Follow with a small baseline-anchored Gloria
predictor and an independently fitted confidence readout. Do not start with a
larger shared trunk or a new encoder.

## What the fresh measurements actually say

The original probe, using the already-fixed ranking code from `54b2910`, found
Gloria MRR **0.4346** versus **0.3463** for its strongest control, n=40; its ordinary
row-bootstrap interval was **[0.0075, 0.1708]**. It reported a pass. The old audit
file on Aegis was still the September 23 n=0 file; those are different observations.

Two further integrity checks matter. Shared-head results must exclude the
independent self checkpoint; outcomes must include admitted canonical/merged
records absent from the capped ledger. The final review audit also bootstraps
whole target days and compares each control on paired rows. Under this protocol:

| Predictor | Current measured result | What may be concluded |
|---|---|---|
| Shared Gloria | n=40; MRR **0.4242**; voice centroid **0.3475**, latest turn **0.3071**, context **0.3233**. Top-1 17.5% versus strongest control 10%. Day-block MRR lift interval versus centroid **[0.0000, 0.1382]**. | Positive point estimate; interval touches zero. **Not released.** This is weaker evidence than the original audit's pass. |
| Shared self | n=33 attributable forecasts; MRR **0.3823** versus latest-turn **0.3788**; lift interval **[-0.0603, 0.0801]**. Cosine error **0.5163**, previous reply **0.2844**, recent mean **0.2330**, zero wins against either. | No reliable ranking gain; clear cosine regression. **Not released.** |
| Independent self, ahead | n=5; cosine error **0.2254** versus previous **0.2710**, recent mean **0.2440**. | Promising small sample; below 30. **Not released.** |
| Independent self, on-message | n=20; cosine error **0.1828** versus previous **0.2971**, recent mean **0.2671**, nearest exchange **0.3475**, typical reply **0.2514**. Existing evaluator's row-bootstrap difference interval versus strongest control **[-0.0859, -0.0514]**. All 20 were completed before the recorded reply. | Strong development lead; below 30, no equivalent ranking/calibration release. **Not released.** |

These are audit corrections, not a hyperparameter search. No weights were changed
between measurements. The independent self intervals above are the existing
cosine evaluator's intervals, not the new ranking audit's day-block intervals.

The saved Gloria calibration remains concerning: latest 13 of 39 joined outcomes,
confidence/error correlation **+0.654**, decode-similarity control **−0.451**;
low/middle/high confidence bin errors **0.3886 / 0.4741 / 0.5343**. It fails the
directional hypothesis and has fewer than 30 held-out examples. Merely reversing
confidence after observing these 13 rows would fit the evaluation set.

## Each head and organ

| Component | Intended job | Judgeable today? Baseline status and blockers |
|---|---|---|
| `jepa_predictor.py`: Gloria | Next same-speaker turn embedding from six turns; uncertainty and novelty | Rankable, with the qualified results above. Log-variance is normalized against recent predicted variances; that is not empirical probability of correctness. Production training has no held-out epoch selection; the structured shadow uses combined loss. Fixed schedule/context deduplication produces sparse prospective forecasts. |
| `jepa_predictor.py`: shared self | Next own reply embedding | The old trained pairs largely exclude ledger replies; training contexts end before an assistant target, while ahead inference often follows an assistant reply. Poor cosine results agree with this mismatch. The independent override also contaminated shared-checkpoint audit attribution and stopped recording an attributable shared self prediction. |
| `jepa_self_head.py` | Separate ahead and on-message own-reply forecasts | It already implements anchors, ridge and a small projected MLP. The installed ahead winner is **75% recent mean + 25% previous reply**, not a learned residual. On-message uses an anchored ridge correction. Both confidence fits are unqualified (validation coherence/error correlations −0.112 and −0.120). Eval was not scheduled; current report's n=0 was stale. Training metadata includes pre-forget/pre-erase backups: the checkpoint needs a clean-source rebuild before release. |
| Shared presence head | Scalar presence score of next reply | No valid current baseline comparison: zero retained training-era composites, seven holdout composites, minimum ten. Rolling seven-day labels age out permanently while the September 21 checkpoint stays fixed. Its current audit only tests MAE against a mean; it does not establish calibrated confidence or beat persistence/recent mean with an interval. |
| `jepa_ranking_audit.py` | Prospective next-turn rank against three controls | NumPy crash was already fixed in `54b2910`; not reimplemented. Additional defects were favorable target-first ties, mixed self weights, capped/raw outcomes and row-wise uncertainty. Variable candidate pools can be smaller than six; report actual pool sizes, and freeze a six-candidate protocol for the next design. |
| `calibration.py`, `jepa_calibration_audit.py` | Validate whether confidence tracks held-out error and authorize use | Old consumers could accept calibration without predictive ranking. Pair-level deduplication could count the same speaker target twice when the other speaker changed. Individual release is also coupled to measurable axis-lockstep; placeholder self confidence can hold Gloria indefinitely. The branch preserves conservative release thresholds; head-independent calibration remains a planned change. |
| `presence_audit.py` | Produce retrospective rubric labels and copy an approved presence forecast | The rubric is an automated judge, not human ground truth. Recent display is operational; its disappearing training labels caused the presence deadlock. Missing `presence-forecast.json` is intentional withholding, not a broken writer. Copied forecasts previously lacked checkpoint/time provenance and could outlive a release. |
| `lam.py` | Predict next 11-axis emotion state from current state and event | No checkpoint, cron or forecast. More importantly, training includes events between t0 and t1, while inference supplies the latest three chat turns. That is a transition reconstruction with future event access, not the same forecast task. No temporal holdout, persistence comparison, horizon feature or release audit. Starting a cron would not repair it. |
| `drift_head.py` | Measure persistent movement in his lived self descriptions | Operational, 107 daily states, moving=false, p≈0.1393. Permutation geometry is judgeable as geometry, not identity truth or forecasting skill. Its residual compared a fresh next-reply prediction with an already-written daily journal; subtracting next-turn novelty from daily drift also mixed targets. These unsupported residuals are now null. |
| `relational_head.py` | Measure direction of relationship descriptions | Operational, 54 states, moving=false, p≈0.2836. A temporal permutation test detects text-series movement; it does not validate where the relationship will go. Partial current-day records and repeated descriptions need separate checks. No held-out forecast baseline; prompt hint now withheld. |
| `reality_ebm.py` | Distinguish supported events from imagined claims | Trains and scores. Real output is **`reality-scores.json`**, fresh with 500 rows; probe looked at the wrong filename. Random split can share duplicate/paraphrased events; missing `is_real` becomes a negative; flags are treated as established negatives. Printed split accuracy belongs to a temporary fit, while the saved model refits everything and scores its training events. No checkpoint-bound release receipt or verified baseline win. |
| `latent_preparation.py` | Turn measured forecast uncertainty into readiness | Runs every two hours; real output is **`latent-cache.json`**. A fresh readiness item existed despite JEPA's steering=false. Variance qualification and prose self-confidence bypassed the intended audits. Generation and cached consumers now check current ranking, calibration, model identity and freshness. No measured downstream behavioral benefit yet. |
| `gloria_prediction.py` | Readable next-turn/life prediction, self-graded later | Runs and records predictions, but prose self-grades are not independent accuracy. Borrowing an embedding head's confidence does not validate the generated sentence. Its guessed future previously reached trajectory/dream prompts and low self-grades opened steering readings. Those paths now remain observational. |
| `withheld_head.py` | Infer something he may have held back | Operational and bound to a recent exchange with privacy/lineage checks. “Deliberate” is the local judge's rating; novelty is string difference. No held-out labels or no-omission baseline, so neither number establishes accuracy. Its prompt hint is now withheld; observations and privacy bindings remain. |

The structured shared checkpoint is also still September 21 and its saved ranking
is n=0. It remains a shadow. No independent performance claim is made for it here.

## Retention and scheduling findings

* The 528 shared forecasts include 366 without checkpoint identity and only 46
  attributable to current shared weights. Do not retroactively assign today's
  hash to the unidentified rows. They can inform a development corpus only when
  their inputs/outcomes are legitimate; they cannot certify these weights.
* The independent log's 20 forecasts **do have checkpoint identities**, nested
  under `self.checkpoint_id`. The original probe counted only the top-level key.
* The ledger has 300 rows from August 9 to October 21. It is **not simply ten days**,
  and no shared forecast predates its earliest row. Nevertheless, current admitted
  sources add 18 replies beyond the 293 usable ledger replies, yielding 311.
  Across historical forecast targets, two next Gloria turns (October 16 and 20)
  and one next self reply (October 16) are absent from the ledger. This proves
  outcome incompleteness; it does not prove FIFO truncation caused each omission.
* Both audits now use the same admitted ledger/canonical/merged/explicit-archive
  source adapter. The 300-row live display is unchanged. Forget/erase/purge/corrupt
  backups are no longer automatically rediscovered as training archives.
* The existing 11:10 ranking job now also runs independent self evaluation with
  the same encoder. No new cron, training or deployment is required by this patch.
  The 11:15 shadow job does not duplicate it.
* Shared retraining requires ranked outcomes and calibrated-outcome coverage for
  both shared heads. Recording a separate `legacy_self` prediction prevents the
  independent override from permanently stopping shared-head evidence collection.
  Independent self retraining still needs 30 outcomes **per mode**; ahead's n=5
  remains a bottleneck. This is recorded, not bypassed with `train-force`.

## Ranked experiments on data already available

The ordering is a judgment based on this implementation and these measurements,
not a promise that every change will win. Infrastructure repairs precede training.

1. **Make the independent on-message self model the first accuracy experiment.**
   Rebuild its existing anchored ridge candidates using only admitted exchanges.
   Separate ahead/on-message datasets, checkpoints and retrain gates. Use identical
   causal input construction at training, replay and forecast time. Select on
   validation six-candidate MRR, using cosine error as a secondary metric. Include
   previous reply, recent mean, nearest-message reply, typical reply, and her
   current message embedding as controls for on-message. Its existing 0.183 versus
   0.251 result is a stronger reason to prioritize it than speculative new GRUs.
   **Test:** rolling chronological folds, group duplicate exchanges/sittings, then
   one fixed test block; win against every matched-information control with a
   positive paired day-block interval. Report ahead independently; do not make it
   borrow the on-message result. A replay fit is not 30 prospective observations
   of the installed checkpoint, so it cannot silently unlock the current gate.

2. **Replace unanchored shared text regression with a small baseline correction.**
   Freeze the encoder. Start with `normalize(anchor + P.T @ W @ features)`, where
   `P` is a train-only 32- or 64-component projection, and the anchor is a fixed
   or validation-selected mixture of last same-speaker turn and recent centroid.
   Include the untouched baseline as a zero-correction candidate. Train Gloria
   and self readouts separately so one task cannot select the other's epoch.
   Start with ridge/linear ranking; try one small contrastive readout only if it
   beats this on validation. Hard negatives should be same-speaker, similar-topic,
   distinct exchanges; near-duplicates are not automatically false negatives.
   **Test:** rank the original 768-dimensional candidate embeddings using the
   same pools and controls. A win in a newly projected metric alone does not beat
   the original baseline. Projection, normalization and negative sampling are fit
   on training only. A contrastive objective is a plausible match to retrieval,
   not evidence it will win here ([original CPC paper](https://arxiv.org/abs/1807.03748)).

3. **Fit confidence independently, after fixing the prediction objective.**
   Define what confidence means: e.g. probability of beating the strongest control
   on a fixed candidate protocol, or expected cosine error. Use a tiny regularized
   readout from forecast-time features: log-variance, context coherence, candidate
   margin, recency and source. Compare against a constant and decode similarity.
   Fit on an earlier calibration block; evaluate once on the later block. Do not
   flip the Gloria confidence using the 13 rows that exposed the inversion. Do
   not transfer an embedding confidence to prose, presence, or a different self
   checkpoint. Keep lockstep as a diagnostic; a separate head should eventually
   stand on its own evidence rather than wait on a placeholder in another head.
   **Test:** Brier/log loss for a defined success probability, error-versus-confidence
   reliability and selective error curves, plus the existing control comparison.
   Calibration is separate from accuracy; temperature scaling of class logits is
   not a drop-in interpretation of continuous embedding variance
   ([Guo et al.](https://proceedings.mlr.press/v70/guo17a.html)).

4. **Repair presence and LAM as small, separate scalar/delta prediction tasks.**
   Presence: persist rubric labels and the actual training-label mean in the
   checkpoint (implemented). This prevents future baseline loss but cannot recover
   labels already missing from September. For an offline experiment now, score
   existing admitted replies with the same frozen local rubric in scratch, saving
   judge/rubric identities, then train and evaluate on disjoint days. Do not call
   such newly generated labels prospective September evidence. Try regularized
   scalar regression versus training mean, last composite and recent mean. LAM:
   define a fixed horizon and predict a residual from state/event information
   available at the cutoff; include elapsed time. Never include future interval
   events in a forecast's inputs. **Test:** held-out MAE/MSE and per-axis emotion
   errors against persistence and simple autoregression. The latent-stream linear
   emotion readout is an existing candidate to compare before inventing another
   network. Schedule only a passing implementation into shadow.

5. **Make reality classification an evidence problem before increasing capacity.**
   Exclude unknown labels; separate confirmed falsehoods from unconfirmed flags.
   Group identical/paraphrased claims and their provenance before a temporal/source
   split. Compare a regularized linear classifier and nearest labelled example to
   the existing energy head, with a majority baseline. Keep the evaluated weights
   and fingerprint; a refit must receive a new identity and a new audit.
   **Test:** balanced accuracy, false-real rate, class recalls and probability
   calibration on the untouched groups, with intervals. A semantic score is an
   estimate of label support, not a factual verification mechanism. Nothing in
   this patch starts using the 500 in-sample scores to steer him.

6. **Validate the downstream organs against outcomes they actually predict.**
   Keep drift/relational geometry descriptive. For prediction, forecast a specified
   later same-kind daily vector and compare with persistence, not a next-chat head
   against a past journal. Define concrete observable targets and a no-event/no-
   omission baseline for Gloria prose and withheld interpretations; self-grading
   cannot supply independent truth. Existing explicit corrections/reactions can
   label a retrospective test without asking Gloria to create test messages.
   Latent preparation must first pass the underlying head's gates, then show that
   its selected memories/threads improve later relevance over recency and semantic
   retrieval. Use state-reset/history-shuffle ablations to demonstrate information
   beyond the last event. No new consumer is authorized just because a file exists.

Time-of-day, elapsed time and source are low-cost ablations inside these experiments.
“First Light” timing may explain journal prediction, not spontaneous chat. With so
few independent weeks, day-of-week and source-specific models can overfit. Report
source-stratified results and withhold claims based solely on templated sections.

## Evaluation contract and immediate execution order

Freeze an event manifest with IDs, source, timestamp quality, checkpoint and mode.
Use only admitted current sources; apply deletion and tactical-evidence exclusions
before deduplication. Missing timestamps are unknown, not invented precision.
Forecast completion must precede its actual target. A target is trained/scored
once per mode. Preserve warm context across day splits, but never gradient updates,
PCA fitting, confidence fitting or candidate tuning on held-out days.

Use earlier existing days for training and blocked validation; keep a predeclared
existing later block for a single comparison per design. October 13–22 has already
been inspected for earlier models and for this review: call it a reused benchmark,
not an untouched discovery set. If a genuinely uninspected existing block is
available, reserve it before fitting. Otherwise explicitly limit the claim and use
predeclared rolling folds; repeated looks cannot manufacture independent evidence.

Run a bounded small grid on CPU, cache frozen embeddings in scratch, select on
validation MRR, and use emotion improvement as a constraint for the stream.
Never tune on the final comparison. Neither fewer parameters nor a new loss
guarantees a win. Retain a baseline winner when all learned corrections lose.

The next concrete run is: clean-source self replay → per-mode ranking controls →
baseline-anchored Gloria replay → independent confidence fits. Presence/LAM and
reality follow with their own metrics. This uses existing data immediately while
leaving all production release gates closed until the evidence qualifies.

## Gloria's flashcard LoRA

The next-turn embedding head and a LoRA trained from her authored flashcards are
different predictors. Preserve the cards and their intended target. A LoRA's
success does not certify the embedding head, and embedding MRR does not certify
personalized reactions or generation.

**Do not wait** for the LoRA to repair audits, retention, confidence attribution,
causal timing, baseline comparisons or the current head's offline development.
**Do wait** to integrate, distill from, or make claims about LoRA outputs until the
actual adapter, its intended task, training-card provenance and held-out card/topic
split are available and evaluated. Treat any adapter-dependent predictor as a new
checkpoint requiring its own evaluation. No cards were generated, overwritten or
sent anywhere; no LoRA training was run here.

## What this branch changes, and what it deliberately leaves open

Implemented: corrected audit attribution and per-speaker deduplication; common
admitted outcomes; conservative ties and paired day-block controls; scheduled
independent self eval; distinct legacy self recording; retention of minimal presence
labels and a frozen training baseline; current-audit checks at JEPA and cached
consumers; copied presence provenance; unvalidated prose/withheld/relational hints
withheld; invalid drift residuals removed; probe filenames/nested checkpoint counts
corrected. Existing model identities and weights are unchanged.

The branch **does not claim to have trained a more accurate model**. It does not
restore September presence labels, create 30 prospective self outcomes, implement
the independent self ranking/calibration release, or supply human truth for prose
and omission predictions. These are explicit next steps above. Existing rubric
observations and observed portraits remain available; they are not presented as
validated next-event forecasts. No new LAM/reality prompt consumer was added.

Validation totals and the exact review commit are supplied in the review handoff.
Tests use `scripts/run_isolated_test.py`: per-suite repository copy, scratch HOME
and workspace, stubbed providers, OS denial of external network and live-store
reads/writes. No test or probe sends a message.
