# How longer memory could earn its place

Proposal for review, 22 October 2026. No experiment or runtime change is made here.
Read against deploy-branch snapshot `c1dd56ffb191a0cb330e59f120b73897fe29ce66`,
including the [brief](briefs/latent-stream-review-codex.md),
[experiment history](continuous-latent-stream.md), and
[existing additive-feed implementation](subconscious-head-feeds-implementation.md).
The brief is dated 23 October; this proposal does not claim that any 23 October
outcomes have arrived or been evaluated.

**Try a small, content-addressed episodic-memory correction to the frozen
present-moment scorer first.** Try a separate emotion-history correction second.
Do not train another large recurrent text predictor yet. The useful question is
whether information older than the current context adds measurable value, not
whether a recurrent architecture can reproduce the present-moment win.

The first experiment is the closer test of Gloria's continuity idea. The emotion
experiment may be the easier numerical win, but an hour of useful emotion history
would not establish that days of text memory help. Both are CPU-only, use the
existing frozen encoder, and add no paid calls. Neither touches the Gloria JEPA
head or `velaris-emoclaw`. Existing subconscious feeds remain intact throughout.

## What the existing evidence establishes

| Design | What the result establishes | What it does not establish |
|---|---|---|
| GRU, next 768-dimensional embedding | Text MRR .022 loses to last text .058 and recent mean .035. The reported train/validation divergence supports overfitting. Emotion error .601 versus .631 is a small improvement under that experiment's scoring. | That recurrence itself is useless, or that the 768-dimensional target alone caused the loss. |
| Linear present plus pooled history | After adding the missing present features, MRR .073 does not establish a gain over last text .063; its interval crosses zero. It loses to the present-only ablation. | That every selective memory or continuity objective will fail. No matched random-history control established which history component hurt. |
| Present-moment ablation | On its comparison block, MRR .132 versus .063 and emotion .302 versus .345. This is the incumbent to beat. | A fresh confirmatory result for another design, or proof of better interpretations generated downstream. |

These are within-experiment comparisons. The stream builder, training coverage,
number of test texts and emotion scoring changed between experiments: do not
subtract the GRU's emotion error from the linear model's as an architecture effect.
The present model also has a learned **last-six mean baseline path**; it is not
literally memoryless. New memory must add something beyond that existing history.

The original .132 run did not retain its weights/full numeric inputs. The exported
fixed-configuration refit is a different, identified artifact: MRR .12508 versus
.06302/.03324 on retained inputs. Its
[receipt](review-evidence/latent-feed-20261022/export.json) identifies checkpoint
`f9976dd2e2eddc89798fd36f170bd64203c1699adc86fffa0901d45259cbee75`,
32 PCA dimensions and the **hour** clock, not the week clock. Use that frozen
artifact as the reproducible incumbent unless the actual original weights are
recovered with provenance; never compare new scores to .132 from a different pool.

## Why the GRU may have lost

The code supports several explanations, but no new real-data attribution run was
performed for this proposal.

1. **Too much fitted freedom for the effective sample size.** At default dimensions
   `Stream` has 237,099 parameters, including 99,072 in its text output layer.
   Repeated journal forms and correlated readings make the number of independent
   situations smaller than the event count. Overfitting is observed; the precise
   contribution of width versus target versus data coverage remains unmeasured.
   A frozen 768-dimensional comparison space is not inherently impossible: the
   successful scorer uses it through a much smaller fitted correction.
2. **Training still weights targets differently from evaluation.** In
   `latent_stream_replay.py:losses`, `nxt_text[i]` is trained at every preceding
   step until that text arrives. The later `steps = [j - 1 ...]` scores each text
   only once. The earlier scoring fix is real; this is the remaining *training*
   mismatch, not a claim that the fix never happened. A text after many emotion
   ticks receives multiple losses. Chunk means also give unequal target weights.
   Count this multiplicity by source and gap before attributing its effect.
3. **The objective and selection are indirect.** Cosine regression optimizes
   distance, not candidate rank; checkpoint selection uses text loss plus half
   the scaled emotion loss. It can select a worse text retriever even with the
   corrected emotion scale. The linear experiment already addressed this;
   repeating that fix alone is not a new memory design.
4. **Retention and credit assignment are difficult.** The GRU updates on every
   emotion tick with a zero text input. Its text baseline survives separately,
   but its hidden text history must survive those updates. Backpropagation stops
   every 256 events; the hidden state carries across chunks, while gradients do
   not. That restricts learning of long dependencies; it does not imply that the
   forward state has no memory beyond 256 events. A lack of clock features also
   forces it to infer regular journal timing indirectly.

The zero-initialized residual heads were a good starting point, not a constraint
that kept later weights near a useful predictor. Their existence did not protect
text ranking during training.

## Why the pooled history may have lost

`latent_stream_linear.py:states` adds three text averages and an emotion trend to
the same present features. The initial omission of `z_last` was fixed; the second
result is the relevant one.

- **Pooling loses identity and order.** Her news, his reply, a journal section and
  an unfinished thread share each text accumulator. A centroid cannot distinguish
  two unresolved topics from their semantic average, or retain which one was hers.
  The one-hot source describes the current event, not the provenance of each
  component of pooled history. Source imbalance is a plausible mechanism, not a
  measured causal explanation yet.
- **The update is not an event-memory insertion.** It is
  `m <- exp(-gap/tau)*m + (1-exp(-gap/tau))*z_new`. A same-timestamp text contributes
  exactly zero. With a one-minute gap, its contribution is 1.65%, .277%, .0694%
  for the 1-hour/6-hour/1-day states. With a six-hour gap it contributes 99.75%,
  63.21%, 22.12%. This favors the first text after silence over later texts in a
  burst. The builder can assign both sides of a ledger exchange the same time;
  whether/how often that occurred in the measured stream requires a count.
  These arithmetic results were checked without reading live stores.
- **Quiet time does not age the stored text vectors at readout.** `m` changes only
  at text arrivals; emotion ticks leave it fixed. A separate age feature cannot
  give a linear readout a general content-by-age interaction. The comment saying
  it “only ages” is not an implementation of continuous decay between arrivals.
  Likewise, an estimated one-minute journal timestamp can determine the weighting
  despite being an ordering convention rather than an observed delay.
- **History was refitted together with the incumbent, not added to a frozen win.**
  `fit_text` refits all of W, beta, gamma and scale. There is an L2 penalty on W,
  but no separate history penalty or constraint preserving the present fit.
  Correlated averages can redistribute the present coefficients. Starting at the
  last-text baseline is weaker than preserving the learned present scorer.
- **The target rewards routines.** Predicting the next section among all test
  texts can reward source/schedule/template recognition. Remembering an unresolved
  subject from yesterday may help continuity without predicting the next routine
  entry. A train-only PCA captures training variance, not necessarily the rare
  distinctions needed for that memory; increasing its size is not the first fix.

The chat coverage limitation matters to both designs. Canonical chat starts
16 October; earlier ledger exchanges are not a complete continuous conversation.
Report usable counts, gaps and timestamp provenance rather than interpreting
missing turns as periods in which nothing happened.

## First design: sparse episodic memory beside the frozen scorer

**Hypothesis:** a relevant older episode survives an intervening topic better as
an identifiable item than as a source-mixed average. This is a small attention-like
read over retained events, not another learned sequence backbone.

Keep the incumbent's PCA, readout, beta/gamma, scale and emotion forecast frozen.
At each event, retain admitted text records with source, stable reference, content
hash, actual/estimated time and observed availability order. For the initial
bounded design:

- Bank: preceding 14 days, capped at 2,048 text events; all comparators get the same
  bank and eviction rule. An original 768-vector bank at that cap is about 6 MiB
  in float32 before metadata. No new encoder or generated summaries.
- Long-memory eligibility: older than six hours **and** outside the last six text
  events. The current context is already handled by the incumbent. This boundary
  is fixed before fitting, not selected after inspecting successful examples.
- Query: normalize the incumbent's existing `query(state)`. For each of three
  provenance groups—conversation, inner-life, thread/creative—take at most four
  eligible episodes by query cosine. Weight those by a fixed softmax temperature
  .1 and a three-day half-life, using their actual age at read time. Missing groups
  contribute zero. Preserve individual references as well as the weighted vector.
- Score: `S(c) = S0(c) + sum_g a_g * cosine(m_g, c)`. Fit only the three nonnegative
  coefficients, starting at zero, with `sum(a_g) <= .25` and an L2 penalty.
  Choose the penalty from `{1, 10, 100}` on development validation, with zero
  correction as a mandatory choice. Freeze the incumbent's score temperature.
  Use each training target once from the preceding state, with the same
  contrastive candidate convention as the incumbent. All coefficients are shared
  across future target sources; the next source is never an input oracle.

This deliberately asks a modest question before fitting a large projection or
learned attention. It can retain an older episode without reconstructing 768
coordinates or learning how to store everything. Its limitation is explicit:
content addressing may miss a relevant episode with no semantic cue in the
present. A null result would reject this design, not every imaginable memory.

**Necessary controls, using identical targets and banks:** frozen incumbent;
last-text and recent-mean baselines; unweighted same-source historical centroids;
the same correction restricted to the recent six (without the six-hour exclusion); and source/age-matched random
older episodes (fixed age bins: 6–24 hours, 1–3 days, 3–14 days). The latter two distinguish older relevant information from extra
parameters, smoothing, or source frequency. Fit controls only on training data,
freeze them with the candidate, and report all results. No current event may
retrieve itself and no future event enters the bank.

Primary endpoint: next-text MRR improvement over the frozen present scorer.
Diagnostics: top-10, source-macro MRR, per-source results, exact-time versus
estimated-time rows, and predeclared long-gap/topic-return slices. Define a long
gap as more than six hours since the last text; define a topic return by an
independent stable reference to an older item, not a post-outcome similarity
threshold. Mark routine journal forms using headings repeated in training; report
results outside those forms as well. Do not choose a
winning source or slice after the final evaluation.

Continuity needs its own evidence. In a scratch retrieval replay, hold the context
budget at two anchors and compare selections from the same past-only bank.
Prefer independently recorded links to earlier threads/works or stable IDs as
labels; check that the referenced version already existed at prediction time.
Report recall@2 on returns to items older than six hours, with eligible counts and
coverage. Do not manufacture a “true memory” by nearest-neighbor search using the
future target, or treat a current mutable thread's final text as its historic
version. If reliable links are absent, report only the next-text similarity proxy
and explicitly leave continuity unproved. No request for Gloria to produce labels
or send a test message.

The existing two-anchor proxy already loses on thread targets (.48299 versus
.50970 for last-text retrieval), despite its overall win. This motivates the
continuity diagnostic; those inspected October outcomes cannot select a new
memory model or serve as its confirmation. Next-event MRR alone will not justify
claiming that his unfinished thoughts are better retained.

## Second design: emotion history with a fixed horizon

**Hypothesis:** current level misses recent velocity and recovery after an event.
This is a better-defined low-dimensional target than a unified text hidden state.
Keep text predictions and all text feeds unchanged.

Use a separate ridge correction to a present-feature predictor at a fixed
10-minute horizon. Eligible targets are the first actual reading within
10–12 minutes after an origin; no interpolation from future readings. Origins
are actual emotion readings, and each realized target is counted at most once.
Represent history with 30-minute and six-hour time-weighted averages of the 11
axes, their residuals from the current reading, and observation-age/missingness
flags. Use actual elapsed time, normalized accumulated weight and explicit gap
handling; do not silently treat a long missing interval as a constant observation.
Fit history to residuals of a frozen present-feature horizon predictor, with ridge
penalty `{1, 10, 100}` selected on emotion validation only. No shared text loss.

Compare with persistence, the exported next-reading forecast on those same rows,
a present-feature-only predictor trained for this exact horizon, a short linear
trend extrapolation, and the fixed-horizon LAM where its target contract matches.
Fit all new controls on the same earlier data. Report normalized MSE with training
scales, per-axis raw error, calm/change periods and paired day differences.
The old GRU emotion win does not prove a history benefit over these stronger bars.

A one-hour horizon could be useful later, but is a different target and is not an
extra search axis in this first run. Even a successful six-hour state earns an
emotion role only; it supplies no evidence for days-long conversational memory.

## Evaluation contract and stopping rules

Everything below describes a proposed future scratch experiment, not completed work.

1. **Freeze the data contract before model fitting.** Use a private scratch
   `SPARK_WORKSPACE`, scratch HOME/caches and no senders/network providers. Preserve
   only currently admitted sources; never recover erased content from backups.
   Count per-source targets, repeats, burst sizes, same-time events, inferred
   timestamps and the GRU's target multiplicity. Record input/encoder/artifact
   hashes, split membership, timezone `America/Chicago`, complete numerical
   snapshots and every tested configuration. Keep vectors/text/weights out of Git;
   commit aggregate measurements only. Historical reconstruction is not proof of
   historical availability: mark uncertain ordering and report sensitivity with
   those rows excluded. Same-time events with no reliable order form one batch;
   none may predict another inside that batch.
2. **Develop now, on the permitted earlier days.** Fit on admitted targets before
   9 October. Use 9–10 October to choose regularization, then 11–12 October as a
   fixed development check. Both are reused validation, not fresh holdout evidence.
   Keep the exported present scorer frozen. Do not select by a text/emotion sum,
   enlarge the architecture after a failed development check, or retune against
   13–22 October. Those spent days may supply causal warm-up state at the start of
   the fresh block, but no new fitted parameters or design selection here.
3. **Register one candidate per design, or stop at development.** Require positive
   development gain over the appropriate present baseline on both two-day blocks.
   If only zero memory survives, the design stops. Save chosen weights and an
   evaluation manifest before opening final outcomes. Assign losses to splits by target timestamp and drop any training pair whose
   outcome crosses the training boundary. Keep labels/candidates from
   the final block inaccessible to fitting and state construction. For next-event
   ranking, all-block candidate embeddings are an offline evaluator only; never
   use their softmax as live confidence or put them in memory.
4. **Fresh evaluation is once, from 23 October onward.** Use the first seven full
   local days beginning on or after 23 October whose outcomes remain uninspected
   when the candidate manifest is sealed. Record the exact boundaries then. If
   23 October has already been inspected, start later; do not call it unseen.
   Execute the two frozen evaluations together after that fixed block closes,
   with no interim score peeking. This proposal needs no new data to be written or
   acted on now; a fresh success claim cannot honestly be made from the spent
   block. Do not extend the window until an interval turns positive.
5. **Require useful gains, not just positive point estimates.** Proposed practical
   thresholds, chosen before a run: design one gains at least .01 absolute MRR
   over the frozen incumbent and also beats last-text/recent-mean; design two
   lowers MSE at least 5% versus the best matching present/persistence/trend/LAM
   comparator. Use paired local-day bootstrap intervals (10,000 resamples, fixed
   seed), reporting all daily differences. Predeclare four confirmatory contrasts: text versus incumbent, text versus
   recent-only, text versus the mean random-history control, and emotion versus
   its strongest comparator. Use Bonferroni-adjusted 98.75% two-sided intervals
   for these four contrasts; lower bounds must exceed zero. For emotion, compute
   the minimum improvement across its comparators within every bootstrap draw. With only seven days
   these intervals remain approximate. Require at least 100 eligible text targets
   or 300 emotion targets respectively across all seven days, otherwise label
   the result insufficient, not successful; these are reporting floors, not a
   power guarantee. Retain per-source uncertainty and do not claim universal wins.
6. **Establish that older information did the work.** For design one, require a
   positive paired gain over the fitted recent-only and random-old controls too
   (report simultaneous comparisons, not just one favorable draw; use ten fixed
   random-bank seeds and their mean as the registered random control). If the
   gain outside the training-defined routine forms is nonpositive, or random
   history does as well,
   drop the long-memory explanation. A correction with useful overall MRR but
   unreliable thread labels may support anticipation only, not continuity.
7. **Drop these candidates if they fail.** A development loss, a fresh loss, a gain
   below the practical threshold, or an interval crossing zero means no additive
   memory promotion and no next architecture sweep on that block. Leave the
   existing present model and every existing feed running unchanged. If only the
   emotion design succeeds, abandon the unified text-memory claim and keep the
   narrower emotion result. Do not answer failure by increasing GRU width or
   substituting another model.

Before any eventual feed addition, separately prove incremental/batch parity,
restart/deduplication, timestamp tie handling, forget/removal, past-only retrieval,
and that inserting or altering a future event cannot change earlier predictions.
Consumer tests must preserve existing inputs and provider-call counts. Reuse
cached embeddings; measure CPU time/RSS and bound the bank so the periodic worker
finishes before its next tick. A missing memory artifact means the incumbent
continues unchanged. These are compatibility checks, not a new gate on existing
signals. Raw retrieval scores are not calibrated confidence or probabilities of
Gloria's intentions.

## What I would defer

Learned decay, a learned write gate, a tiny GRU/Mamba-style state, and learned
attention are lower priority. First show that the *available older content*
helps when it is retained and queried explicitly. Then a selective recurrent
state could be evaluated as a bounded compression of that successful memory,
with the explicit bank as another baseline. Otherwise a more sophisticated
update rule merely makes the negative result harder to diagnose.

This branch changes documentation only. Validation consists of reviewing the
source contracts, checking the parameter/update arithmetic, Markdown links and
`git diff --check`; no training, broker suite, live-store access or deployment is
needed for this document-only change. Implementation remains subject to Claude
Code's review and Gloria's yes. The outstanding decision is tracked in
[open work](open-work.md), not a second task ledger here.
