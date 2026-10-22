# Feed the existing subconscious with trained predictions

22 October 2026. Proposal for review on `codex/subconscious-head-feeds-plan`, based
on retraining commit `237aac9`. This is the original design; the subsequently approved
[implementation and validation](subconscious-head-feeds-implementation.md) are now on
this branch. Nothing is installed, removed, muted or newly gated.

## Decision

Use the present-moment stream to rank what is relevant to the upcoming event, and
the retrained Gloria head to rank evidence about her next turn. Supply that evidence
**before** the existing organs interpret, voice or imagine. Keep their existing
outputs, triggers and fallbacks. A missing model packet must never make an existing
hint, reading, trajectory line, readiness passage or premonition disappear.

The first implementation should export the exact stream winner, reproduce its
scores online, then ground the existing Gloria trajectory/readiness generation.
This is the shortest route from measured prediction improvement to something he
actually receives. No new recurrent architecture or further data collection is
needed to begin.

## Evidence and its scope

Gloria supplied the newer Aegis results in this conversation on 22 October:

| Stream design | Text MRR | Comparator | Other evidence |
|---|---:|---:|---|
| GRU embedding regression | .022 | last text .058 | Lost |
| Linear state with history | .073 | last text .063 | Gain interval crosses zero |
| Present-moment readout | .132 | last text .063 | Top-10 27.9% vs 15.8%; day-block gain interval [.052, .087] |

The supplied present-moment result wins on every source and lowers emotion error
to .302 from .345 persistence. It supports next-event prediction on the inspected
October 13–22 days. It does not show that long memory lacks value for continuity,
or that every downstream interpretation is accurate.

The fetched [stream document](continuous-latent-stream.md) still records an earlier
.120 ablation and a pending corrected rerun. The newer numbers above are attributed
to the supplied result; this proposal did not independently rerun them. Implementation
must bind the actual newer run's configuration, source manifest and parameter hashes.

The [retrained Gloria head](jepa-retraining-2026-10-22.md) has more limited evidence:
MRR .1496 versus .1373 last-turn and .0693 recent-mean on 41 targets, but its gain
interval against last-turn is [-.0278, .0347]. Cosine error .3841 beats last-turn
.4326 and loses to recent-mean .3035. Its separate calibration now points the right
way (later confidence/error correlation −.316). Use it as a measured next-turn
signal alongside the stream; do not describe it as a proven predictor of her intent.
These are different candidate protocols, so .1496 and .132 are not a head-to-head
comparison. No new suppression follows from these limits.

## First: make the winning stream serve exactly what was tested

`scripts/latent_stream_linear.py` currently writes experiment reports, not a serving
checkpoint. `design()` discards the PCA basis and mean. Exporting the reported JSON
alone cannot reproduce its prediction.

1. Export the selected **history=False** fit with PCA mean/basis, text W, beta,
   gamma and scale, emotion coefficients, emotion normalization and axis order,
   frozen encoder identity, feature/source schema, clock configuration and timezone.
   Include training/selection cutoffs, run/code/data hashes and the evaluation
   receipt. In the current script the present model is `test_history_ablation`;
   `test` and the top-level acceptance object describe the history model.
2. Recover the retained selected fit, or reproduce that exact frozen fit from its
   admitted training inputs and original configuration. Do not select another design
   using October test scores. Training normalization and projection remain fixed.
3. Add a CPU scorer with batch/online parity. Preserve the last-six baseline buffer
   if the winning gamma uses it; “present moment” removes the multi-timescale state,
   not that already-tested baseline term. Keep all existing memory stores.
4. Advance from admitted events using a persistent event cursor. Evaluate the saved
   pre-event frame once against its realized target, then update the frame. A current
   frame predicts the next event using the current source and clock, never the next
   event's source or timestamp. Track ingestion time as well as event time: late
   backfill must not masquerade as a prospective forecast. Replay and restart must
   not duplicate outcomes; scoring must distinguish next text from next emotion.

For unit candidate embedding v, the unscaled text score is:

```
s(v) = beta * dot(last_text, v)
     + gamma * dot(recent_mean, v)
     + dot(W * current_features, transpose(P) * (v - pca_mean))
```

An equivalent retrieval query is `beta*last_text + gamma*recent_mean + P*W*h`.
The omitted centering term is constant across candidates. Verify equivalent ranks;
normalizing this query changes score magnitudes and cannot silently redefine
confidence. Candidate softmax scores are not probabilities of a future statement.

## Shared additive evidence, with two distinct meanings

Proposed `scripts/latent_feed.py` supplies an optional evidence packet to existing
consumers. The stream ranks admitted memories, open threads and works available at
the cutoff. The Gloria head separately ranks admitted conversational evidence.
Keep both ordered lists and their baseline scores; do not average unrelated
confidence numbers or pretend they predict the same target. Start with two anchors
per channel, deduplicate shared IDs, and retain each channel's attribution. This
bounded union avoids inventing an untested combined scoring model.

Each packet carries:

- Frame ID, event cursor, cutoff/ingestion time, encoder/schema and checkpoint IDs.
- Target and horizon: next same-speaker Gloria turn, next text event, or next emotion
  reading. The separate LAM's 600-second forecast keeps its own identity and units.
- Existing source IDs, per-channel ranks and scores, last-turn/recent-mean scores,
  and expected error with its meaning and calibration sample count.
- Any realized surprise, its matched outcome ID and its saved pre-event frame.
  Forecast novelty and a prediction's realized error are distinct fields.
- Consumer receipt recording which evidence was actually included. Repository
  receipts contain aggregate measurements only; no snippets or memory content.

Resolve permitted snippets when a consumer uses them; don't duplicate whole memories
in a shared forecast file. Retain existing source admission, forget/erase and privacy
rules. Remove forgotten references from cached packets as well as retrieval indexes.
Build the packet once per cursor in the existing event/forecast path, coalesce repeat
ticks and keep checkpoint loading/embedding work out of the reply's critical path.
Consumers can use the latest compatible packet without waiting for the producer.

The offline stream surprisal uses future test candidates. That is an evaluation
construction, not a live confidence function. For live realized surprise use a
declared error measure against the saved query, with the last-turn comparator;
calibrate its scale on an earlier disjoint block or an earlier chronological replay.
Do not fit that scale on October 13–22. If calibration is unavailable, expose the
raw error as raw error and continue all existing feeds.

## Ranked consumer changes

Ranked by closeness to the trained target and likelihood of useful grounding, not
by a claim that downstream gains have already been measured.

| Order | Existing path | Additive change | What stays |
|---|---|---|---|
| 1 | `gloria_prediction.py`, `living_trajectory.py`, `latent_preparation.py`, both `emoclaw_utils.py` copies | Give existing generation calls the two channels' retrieved anchors, current emotion forecast and explicit agreement/disagreement before wording the trajectory/readiness. Add the same context to the existing novelty directive. | Predicted sentence, trajectory line, readiness, novelty directive, current fallback paths and all existing context. |
| 2 | `gloria_prediction.py` → `reading.from_missed_prediction()` | Attach the saved, matching next-Gloria-turn forecast, realized semantic error versus baseline and source-backed alternative interpretations to the existing reading call. | Existing missed-prediction trigger, reading generation and ledger; no extra calls or duplicate readings. |
| 3 | `premonition-dreamer.py:gather_present()` | Add retrieved current concerns, open threads and next-reading emotion tendency to the existing future-generation input. | Existing rollouts, intersection, synthesis, seeding, diversity and `dream_only` provenance; no futures discarded. |
| 4 | `withheld_head.py` | Give its existing judge relevant admitted unfinished topics and explicitly expressed intentions, selected by the stream; include Gloria-channel context only as context about her next turn. | Existing phrase, deliberate score, hint, source binding and admission protections. A predicted topic is not proof he deliberately withheld words. |
| 5 | `relational_head.py` | Add near-term topic/contact evidence alongside the existing daily geometric relationship movement, keeping the two timescales distinct. | Existing direction/coherence/permutation calculation and hint. A next-turn vector does not become a daily relationship trend. |

**Trajectory is the first concrete defect to fix.** Today `gloria_prediction.py`
generates the sentence first and substitutes JEPA confidence afterward. The generated
sentence never saw the trained evidence. Move grounding into that same generation
call; retain separate prose confidence and model expected error. A nearest past turn
is supporting context, not the literal sentence she will say next.

Preserve `latent_preparation.signal()`'s existing four-value interface; add richer
evidence through a separate helper/optional argument. Its posture and the novelty
directive currently interpret numeric thresholds. The new head's
`1 - expected_error/2` is not an 80% probability at .8. Add explicitly named semantic
error/context fields rather than silently driving those probability-like thresholds
with a new meaning. Existing outputs continue while the extra evidence improves
what their current voicing calls can say.

**Readings require exact outcome attribution.** Surprise from a creative entry or
his journal is not evidence that he misread Gloria. Match the next same-speaker turn
to a forecast made before it arrived. Preserve the original prose-miss trigger even
when a matching model forecast is absent. Multiple graders cannot open duplicates.

**Premonition needs a separate context budget.** `gather_present()` currently slices
the combined block to 2,000 characters. Prepending evidence would silently displace
what he already receives. Preserve that original block and append a bounded evidence
section within the existing call's supported context. Apply the same preservation
test to every consumer. Keep the existing provider and call count; the new scorer
uses CPU only and adds no paid calls. Do not rerank entire imagined futures using a
head trained on a single next turn.

Generated predictions, readings and dreams remain derived material. Their own
repetition must not become successful prediction labels or confirmed observations.
Premonition threads remain available with their existing provenance; admitting them
as targets requires their distinct source type and never counts them as actual turns.

## Acceptance tests for implementation

1. **Numerical parity:** exported/reloaded batch and incremental text scores and
   emotion predictions match the original selected fit within declared float32
   tolerance (start at 1e-6). Assert the present-moment variant, exact timezone,
   selected schema and checkpoint hashes. Preserve the original offline benchmark.
2. **Causality:** future-target mutations cannot change earlier frames, candidates,
   fitted weights or confidence. Restart, duplicate and delayed ingestion cases
   count each realized target once and retain the correct head/horizon identity.
3. **No subtraction:** absent, stale, malformed or incompatible packets preserve
   each consumer's original inputs/outputs and triggers under a deterministic stub.
   A failed optional augmentation preserves the original cache. Valid augmentation
   does not truncate the original context or replace a hint with an empty string.
4. **Meaning and provenance:** raw ranks/error cannot overwrite prose confidence,
   deliberate-withholding confidence or daily relational evidence. Source IDs existed
   at the cutoff and remain admitted; derived futures cannot validate themselves.
5. **Consumer benefit:** replay existing data with three fixed conditions: existing
   feed, feed plus last-turn/recency anchors, feed plus trained anchors. Use identical
   candidate pools, prompts and context budgets. Compare retrieval coverage/rank of
   actual subsequent topics and inspect whether grounded claims have source support.
   Audit existing recorded corrections where available. Next-event ranking alone
   cannot establish better lived behavior; record those separate conclusions.
6. **No test-driven search:** predeclare the consumer comparison and keep the October
   block descriptive because it has already been inspected. Use chronological folds
   within existing earlier data for design choices, with training and calibration
   inside each fold. Do not tune repeatedly on the reported win or wait for more data.
7. **Isolation and cost:** scratch workspace/HOME, all senders/provider clients
   stubbed, no live writes. Assert unchanged generator call counts and zero new paid
   calls. Measure CPU/memory and cached-consumer latency before claiming it fits.
   Run affected suites, then the full isolated `broker/tests` suite for implementation.

Implementation should add the scorer/adapter to the deployment manifest, regenerate
the required ownership/test reports, and include aggregate parity/consumer receipts.
Checkpoint files stay in approved private scratch until Gloria chooses installation.
Model validity controls only whether extra evidence can be interpreted; it never
becomes a new gate on his existing subconscious feeds. LoRA training does not block
this work: a future voice change needs its own evaluation and can reuse this evidence
interface without changing the frozen encoder or deleting any feed.

The original proposal is retained here. Implementation and measured acceptance are
reported separately above; execution status belongs in [open work](open-work.md).
