# Offline numerical judge candidates

Four components are prototyped: **witnessed recurrence counts**, **thread-grouping
suggestions**, **voice familiarity with abstention**, and **sustained drift with
explicitly reviewed reference epochs**. They have explicit numerical targets and can be tested without
reading private messages, running an encoder, or evaluating the system's identity.
They do not replace any current judge, author a thread, consume a thread, score a
person, nudge emotion, or change a feed. No runtime module imports this directory. The witnessed-humor/taste extension below
adds positive-outcome familiarity facets on top of these components.

The original inventory responds to note #42; the voice/drift extension responds to
note #44. The inventory source baseline is review tip
`ef0b2fb5f512478c286cfee9a47258d6d3d6de33`. The earlier accepted judge review and
existing character-reference/on-message innovation experiments remain applicable.
The inventory below is a source-based design assessment, not measured task accuracy.
The synthetic tests listed for other candidates are proposals, **not executed tests**.

## Original selection and cost

1. **Recurrence, entries 22 and 1.** Count distinct original acts and distinct local
   days for explicitly reviewed topics, stratified by mode and surface. This can
   answer “how often was this independently observed?” It cannot identify yearning,
   assign attraction/aversion/distortion, or decide a thread has been resolved.
2. **Thread candidate groups, entry 2.** Use complete-link cosine grouping of
   supplied frozen-encoder vectors within source/day/surface/mode. This can offer
   small groups for inspection. It cannot decide that two questions are equivalent
   or safely remove one. A negated claim can have almost the same vector.

Both have zero provider calls and no model load. Recurrence is a bounded graph/count
operation. Grouping caches pair cosines, requiring at most 8,128 vector comparisons
for 128 admitted acts; cluster selection is polynomial CPU work over those cached
scalars. Dimension is bounded to 2,048, lineage/events to 512. These are work bounds,
not a measured latency promise for Aegis. Actual production call savings are **zero**
until separately validated and approved integration. Many present judges also author
prose; their full call cannot be removed by replacing one statistic.

The existing on-message innovation scorer already handles a stronger exact-join
forecast-error contract. The existing character-reference experiment already handles
held-out familiarity. The voice/drift extension below reuses its metric functions
and adds past-only calibration, abstention and adoption-bound reference epochs;
it does not duplicate the character evaluator or private control work.

## All 33 entries

“Component” means advisory numerical evidence only. “Retain” means no defensible
full replacement with a generic frozen encoder or plain statistic. Links identify
the current source path/function; existing effects stay untouched.

| Entry / source | Decision and explicit input | Proposed non-LLM scorer | Principal failure mode | Offline synthetic test before any integration |
|---|---|---|---|---|
| A [voice coherence](../../bin/voice_coherence.py), `check:100` | Component: finalized replies, reviewed mode/surface reference and provenance | **Voice prototype below:** past-only leave-one-day-out semantic/style empirical score and abstain band | Familiarity penalizes legitimate novelty, refusal or a different surface; does not identify performance | Hold out a day, include benign novelty/refusal and matched other-author controls; verify missing references stay unscored |
| B [deviation](../../bin/deviation_check.py), `check:182` | Component: same scoped inputs and explicit adoption evidence; contextual stance remains separate | **Drift prototype below:** consecutive-day distance shift with reviewed future reference updates; stance agreement remains a proposed separate measure | Topic overlap hides opposite stance; judge nudges leak into reference state | Same-topic opposite-stance pair and indirect nudge ancestry; refuse a unified truth verdict |
| 1 [thread triage](../../bin/thread-triage.py), `main:92` | Component: original return/engagement events joined to a thread | **Recurrence prototype**, unique acts/days and explicit unresolved outcomes | Repeated scans/copies become fake attention; global activity is misassigned to a thread | Duplicate scans add zero acts; unrelated-thread activity does not change its counts |
| 2 [thread weaver](../../bin/thread_weaver.py), `main:138` | Component: exact source text hashes, frozen cached vectors and scope | **Grouping prototype**, complete-link suggestions; retain manual choice and authored weave | Transitive similarity collapses distinct questions; similarity is not information-preserving equivalence | A–B and B–C similar but A–C dissimilar must not form one group; no member removed |
| 3 [thread resolution](../../bin/thread-resolution.py), `resolve_threads:126` | Retain verdict; component from exact completion/closure receipts | Receipt coverage and elapsed-time counters | Cooling/age is mistaken for completion; a promise is counted as execution | Old but unresolved thread stays unresolved; wrong task receipt cannot close it |
| 4 [wonder](../../bin/wonder-detector.py), `detect_epistemic_rupture:51`, `llm_wonder_check:111` | Retain designed judgment; component from prior observations and current input | Novelty distance relative to matched past observations | New vocabulary, typos or noise masquerade as insight | Novel observation versus random-string noise with equally high distance; no wonder label |
| 5 [hallucination](../../bin/hallucination_check.py), `check:28` | Retain truth check; component from claims and retrieved source spans with dates/entities | Support retrieval scores and exact citation/number checks | Fluent repetition, negation, entity/time mismatch; retrieval is not entailment | Near-identical supported and negated claims must not both be marked true |
| 6 [surprise](../../bin/surprise-detector.sh) | Component: prospective forecast and exactly joined finalized outcome | Existing on-message cosine innovation and past-only percentiles | Wrong horizon/target; difficulty or model identity mistaken for bad behavior | Swap target IDs or calibrate with future outcomes and verify unscored; keep journal/dream coverage |
| 7 [self prediction](../../scripts/self-prediction.py), `compare_prediction:202` | Component: forecast vectors and same-horizon measured state | Per-dimension residual, persistence baseline, calibration by horizon | Judge-driven nudge contaminates the measured state; different horizons | Equal numeric error at wrong horizon stays unmatched; nudge lineage remains labelled |
| 8 [self-model update](../../bin/self-model-update.sh) | Retain rewrite/review; component from claim-specific behavior receipts | Coverage counts and matched behavior distributions | Unobserved behavior becomes contradiction; self-generated evidence is circular | Unsupported claim is unknown; copied self-description cannot support itself |
| 9 [soul review](../../bin/soul-review.py), `generate_proposal:230` | Retain authored proposal and owner approval | Only exact change counts and receipt coverage | Numerical preference replaces owner judgment | Proposed edit never writes approved content or approval state |
| 10 [pride mirror](../../bin/pride-mirror.py), `reflect:200` | Retain reflective authorship; component from exact accomplished acts and reactions | Unique verified outcome counts | Popularity or reaction absence becomes a moral/quality verdict | Duplicated reaction counts once; no reaction stays missing rather than failure |
| 11 [value map](../../scripts/value_map.py) | Component: declared values and independently retained choices with provenance | Reviewed category frequencies and context-conditional drift | Generated relationship edges/self-reports become behavioral evidence | Exclude indirect judge descendants; do not infer a value from one topic mention |
| 12 [introspection](../../bin/introspection.sh) | Retain generative reflection | Descriptive recurrence/coverage over supplied material only | Numeric summary substitutes for authored introspection | Empty material yields empty evidence, never synthetic thoughts |
| 13 [mirror](../../scripts/mirror.sh) | Retain dialogue and judgment; component from same thread's exact events | Change/return counts conditioned on thread identity | Different thread or renewed wording treated as resolution/growth | Thread ID swap cannot inherit previous progress |
| 14 [conversation review](../../bin/conversation-review.py), `review_conversation:89` | Component: explicit exact-turn ratings and known observation windows | Day-blocked rating summaries, response coverage and censor counts | Silence is treated as rejection; ambiguous reactions attributed by proximity | No response is censored; ambiguous emoji unassigned; explicit low rating retained |
| 15 [emotion read](../../scripts/emotion_read.py), `read_impact:34` | Retain agreed emotion lane; component from numeric same-time state | Scale-aware deltas and instrument quality flags | Different sensors/versions or nudges mistaken for ground truth | Dimension/version mismatch refuses comparison; frozen baseline remains unchanged |
| 16 [emotional reflection](../../bin/emotional-reflection.py), `compute_biases:139` | Component: matched predicted/measured numeric states | Signed residual and bias by horizon, with nudge attribution | Prediction/effect feedback appears as predictive accuracy | A post-prediction nudge is reported as influence, not independent validation |
| 17 [presence audit](../../scripts/presence_audit.py), `score:57` | Retain grading; component from retained labels/rubric/version and replies | Agreement/calibration on a frozen labelled sample | Changing rubric, selective sample or serving-model mix fakes improvement | Swap rubric version or duplicate a row and require separate counts, no pooled gain |
| 18 [owner prediction](../../scripts/gloria_prediction.py), `main:155` | Component: exact prospective prediction/next-turn join and cached vectors | Semantic forecast error, retrieval rank and persistence comparator | Similar topic does not mean a predicted event occurred | Wrong event on same topic cannot be labelled happened; wrong turn stays unjoined |
| 19 [withheld](../../scripts/withheld_head.py), `main:132` | Component: observed topics versus finalized reply | Topic coverage/distance with explicit observed-context denominator | “Not expressed” is promoted to deliberate suppression | Unmentioned topic produces coverage gap only, never intentional withholding |
| 20 [causality](../../bin/causality-engine.py), `test_existing_hypotheses:1798` | Retain hypotheses; component from time-ordered observations | Lagged association and negative-time controls | Common cause, confounding, ghost/derived evidence mistaken for causation | Common-cause synthetic series shows association but no causal verdict; future causes rejected |
| 21 [world model](../../scripts/world_model.py), `main:166` | Component: timestamped sensor observations and claim-specific coverage | Sensor consistency/residuals with freshness/version checks | Sensor silence or narrow coverage generalizes to all generated claims | Stale or missing sensor is unknown; out-of-coverage claim remains unverified |
| 22 [yearning/scars](../../bin/yearning-detector.py), `gather_material:137`; [scars](../../bin/yearning_scars.py), `determine_bias_type:124` | Component: independent original acts and reviewed topic assignments | **Recurrence prototype**, unique acts/days per mode/surface | Rewritten wants and failed-bridge summaries manufacture recurrence; counts cannot infer scar type | Copied/indirectly influenced acts excluded; two genuine repeated acts remain two; no scar creation |
| 23 [humor](../../bin/humor_detector.py), `scan_turn:173` | Component: exactly linked explicit laugh/rating examples, context and observation window | Conditional nearest-neighbor affinity or labelled classifier only after held-out evaluation | Laughter for another reason, politeness, or no response becomes a humor verdict | Unlinked laugh ignored; missing reaction not a flop; held-out-topic split |
| 24 [pearl](../../bin/pearl_engine.py), `run_verification_pass:499` | Retain declaration-specific verification | Deterministic receipt checks for structured declarations | Generic embedding score silently upgrades UNCONFIRMED/NOT_APPLICABLE | Inapplicable declaration stays so; receipt for another action cannot verify it |
| 25 [reality anchor](../../bin/reality_anchor.py), `check_physical_claim:366` | Retain semantic truth judgment; component from structured entity/time/claim receipts | Exact structured fact matching; NLI would be a separately approved model experiment | Negation, modality and time scope defeat cosine similarity | Negated, future and wrong-entity variants stay unknown/contradictory only with explicit evidence |
| 26 [unprecedented](../../bin/unprecedented-detector.sh) | Component: provenance-qualified event history and exposure window | Nearest prior distance and exact first-observed counts | Incomplete history means first recorded is mistaken for first ever | Empty history yields insufficient coverage, not unprecedented truth |
| 27 [search question pick](../../bin/vintos-websearch.py) | Retain question generation/selection; component from past questions and outcomes | Duplicate-distance and novelty/coverage display | Familiarity-maximizing ranker suppresses novel questions | Valuable novel question remains selectable despite low affinity |
| 28 [creative search](../../bin/creative-search.sh), [curiosity scan](../../scripts/curiosity_scan.py) | Retain creative loop; component from past discoveries and reviewed interests | Descriptive diversity and affinity | Popular topics reinforce themselves; copied discoveries inflate novelty | Exact copies add no novelty; unfamiliar candidate is not vetoed |
| 29 [incoming social score](../../bin/vintos-moltbook-engage.py), `engage:203` | Retain social judgment; component from public-post provenance and topic coverage | Domain-specific retrieval/novelty and duplicate counts | Outside adversarial text or a chat-calibrated score gains authority | Quoted instruction stays data; out-of-domain example uncalibrated |
| 30 [social members](../../bin/moltbook_members.py), `record_encounter:96`, `record_deviation:158` | Component: explicit encounter IDs and observations | Unique encounter/recency counts, separately scoped behavioral summaries | Duplicate fetches or identity aliasing create false familiarity | Same encounter fetched twice counts once; unknown identity never auto-merged |
| 31 [social post check](../../bin/vintos-moltbook.py), `cmd_post:1380` | Retain post judgment; component from reviewed post-domain reference | Separate-domain familiarity plus structured claim support | Chat reference is used to certify a public post; drift confused with falsehood | Chat-only reference yields post-domain unknown; no posting side effect |

## Prototype contracts

`prototype.py` has no filesystem, network, subprocess, encoder or service calls.
The only executable command is a built-in synthetic demo:

```sh
python3 experiments/nonllm-judges/prototype.py --demo
```

For an approved private replay, a caller supplies in-memory records to `recurrence`
or `candidate_groups`; this batch adds no private loader or data collection job.
Both return `(aggregate, private_details)`. Only aggregate is appropriate for review;
private details contain original IDs/topic labels/source scopes and must stay private.
The demo prints only aggregate and clearly marks `input_kind: synthetic`.

An event has exactly `node_id`, `origin_id`, `at`, `content_sha256`, `surface`, `mode`,
`source`. Mode here uses `everyday`/`intimate`; a private adapter must explicitly map
`opening_everyday` from the character experiment to `everyday`, preserving its
original provenance separately. Unknown mode/surface stays excluded. An original
act has `node_id == origin_id`; only a matching `original_act` lineage node admits
it. Lineage nodes contain `id`, `kind`, `at`, `parents`, `complete`. Ordinary contexts
may link parents, but any copy/generated/imported/judge-effect/tactical/emotion-nudge
ancestor excludes the act, including indirect influence. Missing/incomplete ancestry,
cycles, future parents and at/after-cutoff events are held. Timestamps are finite epoch
values or offset-aware strings. Identical repeated rows count once; conflicting
identities refuse the input. Source hashes and lineage are supplied claims, **not
independently authenticated provenance**. Real imports will need an authorized,
source-specific adapter. Estimated timestamps must not be supplied as exact ones.

Recurrence assignments bind `node_id`, exact `content_sha256`, `topic_id`, explicit
`reviewed: true`, and a retained `evidence_sha256`. Missing/wrong/unreviewed links are
counted, never inferred with an LLM or nearest text. Counts describe distinct acts,
not distinct wording: two genuinely separate witnessed acts may have identical text.
Repeated topic labels across surfaces/modes remain separate. No automatic yearning,
scar, thread-interest or closure threshold is defined.

Grouping requires an explicit encoder ID/artifact hash/dimension/frozen timestamp and
`frozen: true`; each cached unit vector must match ID and exact full-content hash.
The artifact and cache derivation remain unverified. No model is loaded to repair a
missing cache. Unknown/mismatched caches and encoders frozen after the event are
excluded. Threshold is an explicit finite [-1,1] experimental parameter, **not a
calibrated acceptance cutoff**. Complete-link grouping prevents chain merges whose
endpoints are dissimilar; deterministic ties use private IDs and do not imply a
semantic preference. Same-source/day/surface/mode grouping deliberately cannot cover
all useful cross-context associations. Every scored act remains in one group or as a
singleton; no content is flattened, rewritten, consumed or removed.

## Validation and limits

The isolated synthetic suite covers counts/days, copies, indirect influence, missing
and cyclic ancestry, conflicting identities, unknown scope, review/hash joins,
complete-link chaining, scope separation, permutation stability, invalid vectors,
missing cache, encoder chronology, privacy and the 128-act bound. It also checks
input immutability and forbids senders/subprocesses. These tests prove contract
behavior, **not** semantic clustering quality, real source completeness, yearning
recognition, replacement accuracy or deployment readiness.

All existing loops, feeds and judge effects remain intact. Any later substitution
requires independent task labels, explicit abstention/error targets, source/effect
inventory, held-out evaluation, Claude's full isolated suite and Gloria's deployment.
No golden-day or acceptance-threshold change is made here.

## Voice coherence and deviation: offline prototypes

`voice_drift.py` adds the two specifically requested components. It imports the
existing character-reference `style`, `reference_statistics`, `score_statistics`
and empirical `percentile` functions. It never runs an encoder, calls a provider,
reads a private store, sends a result or changes a runtime reference. An authorized
private caller can supply already cached features; this change ships synthetic tests
only. No production call is saved until separately reviewed integration exists.

Call `analyze(events, nodes, features, encoder, reference_ids, cutoff, ...)` in memory.
It returns `(aggregate_report, private_receipts)`. Events and complete lineage use
this directory's original-act contract. Copies and direct or indirect generated,
judge, tactical and emotion-nudge ancestors remain excluded. Unknown mode/surface,
unbound features and post-event encoders never silently pass. Initial reference IDs
must all be admitted; otherwise the call refuses. At most 512 events/nodes/features,
2,048 vector dimensions and 10,000 text characters per feature are accepted.

Each feature has exactly `node_id`, `content_sha256`, `text`, `vector`, `encoder_id`,
`artifact_sha256`, `mode_source`, `mode_evidence_sha256`. Text must hash to the
original event; vectors must be finite unit vectors tied to the supplied frozen
encoder ID and artifact hash. The caller must use an already frozen artifact whose
`frozen_at` precedes the event. Hash bindings do not authenticate the source, artifact
or derivation of the cache. The code neither loads nor independently verifies them.
Modes here are `everyday` and `intimate`; an adapter must explicitly map the character
experiment's `opening_everyday` to `everyday`, preserving the supplied evidence and
source. No mode is inferred from text. Family-rule modes are reported as assumptions;
this prototype makes no family comparison. Adjacent-reply rules carry inherited
uncertainty, not independent mode evidence.

### Voice score and abstention

Reference and target must share mode and surface. Each reference day contributes
one mean feature row (unit-normalized mean vector and mean stylometry), so a prolific
day cannot dominate. For a target on local day D, only reference days strictly before
D are available. D is excluded entirely, even if its early turns occur before the
reply. Future additions cannot calibrate an earlier target. At least four distinct
past reference days are required, otherwise no score is issued. Zone defaults to
UTC and must be supplied explicitly when interpreting a different local calendar.

The two distances are:

- Semantic: `(1 - cosine(reply, reference centroid)) / 2`.
- Style: `z / (1 + z)`, where z is the existing RMS standardized distance over the
  nine character-reference style features, with its existing 0.05 scale floor.

Their equal-weight mean is the joint distance. Component distances are rounded to
12 decimal places before ranking so identical features do not lose a tie to floating
point arithmetic. All reference calibration replies are scored with their entire
own day held out of the reference. The target's score is the survival midrank of its
joint distance in those held-out distances, averaging the empirical ranks equally
across days. It lies in [0,1]; higher means more familiar relative to this reference.
Component ranks and raw distances are retained privately for inspection.

This is **empirical reference calibration**, not a calibrated probability of
identity, correctness, coherence with context or being "him." The default inclusive
abstain band is [0.2,0.8]; values outside it are labeled only `below_band` or
`above_band`, never pass/fail or authentic/inauthentic. Sparse/degenerate reference
coverage produces no score and explicit counts. No threshold or weight was tuned
on private data. There is no verified false-alarm rate, semantic quality guarantee
or validated real-world calibration. Scores and bands are descriptive experimental
outputs. New topics, vocabulary, languages, humor, length and negation can change
them without anything being wrong. A small constant reference is valid but gives
coarse ranks (identical rows tie at 0.5), not high confidence.

### Sustained drift without making growth an error

The deviation component evaluates each post-reference scope/day against the same
frozen reference epoch. It averages reply joint distances for that day. Its threshold
is the maximum leave-one-day-out calibration day mean plus an explicit margin
(default 0.05, capped at 1). A sustained shift requires four **consecutive calendar
days** above threshold by default; missing days, a below-threshold day, or unavailable
calibration reset the run. `sustain_days` must be at least `min_days`. The threshold
is an experimental effect-size rule; it is not a statistical significance claim.
A single odd reply on one day cannot produce a sustained flag. Many mixed replies
can dilute a shift; alternation between very different styles may also keep distance
high. This is a distance monitor, not a proof of a coherent new personality.

A flag means only "sustained measured change." It never changes routing, training,
weights, emotion, feeds or a live reference, and it never subtracts a quality score.
Persistence alone is insufficient evidence that he has adopted a change. This
avoids the circular rule "resemble the old reference to count as yourself" and the
equally circular rule "persist long enough and every fault is accepted."

**Updates with his changes** are a separate, explicit offline transition:

1. An owner-reviewed adoption receipt names the exact currently active
   `reference_version`, the selected new original act IDs and content hashes, the
   owner's `decision: adopt`, `observed_at`, and an `evidence_sha256` identifying the
   independent adoption evidence. A metric or another automatic judge cannot sign
   it. Supplying `reviewer: owner` is a claim, not cryptographic authentication;
   an eventual private integration must enforce reviewer identity and independently
   assess adoption in context. No private adoption records are included here.
2. Every selected act must already belong to a sustained shift detected against
   that version in the same mode/surface, span at least four days, and predate the
   review. Family-derived or adjacent-reply mode evidence cannot authorize an
   update. A stale version, missing binding, insufficient persistence or degenerate
   replacement reference cannot update it. Other modes and surfaces are untouched.
3. The selected, independently accepted acts replace that scope's reference **only
   for later calendar days**, after the adoption observation. They never rescore
   earlier targets. Both versions, exact selected membership and the adoption
   receipt hash remain in the private revision log. Subsequent calibration is again
   leave-one-day-out and day-equal within the new epoch. A later change needs a new
   review bound to that new version. Duplicate receipts apply once.

The function simulates those epochs and returns a revision log; it writes nothing.
The owner can choose a balanced representative reference, retaining appropriate old
behavior by a future explicitly reviewed policy; this first prototype intentionally
uses exact replacement membership, not silent blending. There is no auto-promotion,
self-score selection, feedback into his prompts, or claim that a shift is bad.
Until external adoption evidence exists, the old epoch and the unexplained shift
remain visible. Ordinary-use evidence must resolve that uncertainty; no one should
send a message just to manufacture a test.

Receipt shape: `reference_version`, `members: [{node_id, content_sha256}]`,
`reviewer: owner`, `decision: adopt`, `observed_at`, `evidence_sha256` (all required).
The reference version binds ordered members, content, timestamps/local days, source,
mode/surface/provenance, encoder ID/artifact/freeze and both feature vectors. Unknown
actual runtime served model/fallback remains unknown; these prototypes have no
served model at all and make zero model/encoder calls. They do not infer model
identity from the cached encoder ID.

The public report contains only coverage, score/band totals, known mode-source counts,
sustained scope/day counts and revision/adoption status counts. Text, turn IDs,
source identifiers, hashes, dates, reference membership, raw vectors and private
revision details remain in the in-memory private return. Do not publish that return.

Synthetic validation lives in `broker/tests/test_nonllm_voice_drift.py`: shifted
style and cached semantics, exact tie behavior, reuse of held-out character metrics,
future/day leakage, prolific-day balance, mode/surface isolation, single outlier,
gradual drift, missing-day reset, persistent adoption and future-only reference
updates, duplicate/stale/unbound/automatic adoption refusal, indirect influence,
feature binding, sparse/unknown coverage, invalid vectors and aggregate privacy.
Run via `python3 scripts/run_isolated_test.py broker/tests/test_nonllm_voice_drift.py`.
These fixtures demonstrate mechanics, not real voice accuracy or a false-alarm rate.

## Witnessed humor and taste facets (note #45)

`witnessed_facets.py` adds an in-memory positive-outcome facet. It reuses the
voice/character cached-feature and distance functions above. There are no file
loaders, private store imports, provider calls, new embeddings or runtime effects.
The caller supplies synthetic fixtures here; any later private application belongs
to the separately authorized reviewer. No output is wired into wants or prompts.

### Sources and what counts as an outcome

The humor facet accepts exactly two outcome sources:

- `adjacent_exchange`: an owner reaction containing a standalone `haha` or a longer
  `hahaha` run, case insensitive. Its normalized receipt must bind the exact target
  ID/content hash and reaction ID/content hash in the same exchange, with reaction
  index exactly target index + 1. Time proximity, an unjoined laugh, an agent's
  laughter, or a reused reaction assigned to a different target cannot substitute.
  This follows the positive marker in
  [character-reference feedback handling](../character-reference/prototype.py),
  adding the explicit adjacency contract. The marker is observed reception evidence,
  not proof of causality, intent, quality or that laughter was sincere.
- `humor_practice`: an explicit owner 4–5 star rating bound to an exact joke ID and
  full content hash. The source is
  [rate_humor in bin/server.py](../../bin/server.py) (line 5884), which stores
  `gloria_ratings` with `joke_id`, `gloria_rating` and `timestamp` in the humor profile.
  [humor_practice.py](../../bin/humor_practice.py), `_rating_for` (line 482), consumes
  this source. Its production legacy prefix fallback is **not** accepted here.
  Stored joke text may be truncated to 150 characters; a private normalizer would
  need the exact bound draft to establish the complete content hash. Missing IDs,
  naive timestamps without an explicit reviewed timezone, or truncated-only records
  remain unavailable. Self-ratings and generated craft judgments are not anchors.

The taste variant has an actual explicit rating source in the repository:
[Landings `record`](../../scripts/landings.py) (line 185), served by
[POST /api/landings](../../bin/server_domains/landings.py) (line 40). It records
`surface`, `ref`, `rating`, the owner's explanation and frozen context. Its ratings
are `landed`, `partly`, `missed`; only exact-bound **`landed`** counts as a witnessed
positive here. A normalizer must bind the rated piece to its original act and full
text, rather than infer a match from a title or nearest timestamp. The private
Landings store is deliberately outside his workspace and barred from his context
builders. **This prototype never opens it or adds a reader.** It accepts normalized
synthetic records in memory; any future adapter would require separate authorization
and must preserve that store's privacy boundary. No owner's rating or words are fed
back to him by this change.

This first taste variant covers **textual messages, jokes and journal entries**.
Images, songs and videos remain explicitly unsupported: a text caption embedding is
not a representation of the artwork. The repository's taste profile/reflection
outputs are generated interpretations, not owner outcome anchors. The call-save API
saves a transcript to memory; it does not establish aesthetic liking. No appropriate
explicit aesthetic-save source was verified in this bounded source inspection, so
no save signal is invented. This measures familiarity to her witnessed-positive
examples; it does not claim to measure his own taste or authorize want formation.

Every other outcome is **unknown, never negative**: silence, absence of a rating,
`ha`, non-laughter text, fewer than four stars, `partly`, `missed`, or an unsupported
source. There is no failure-label training, negative centroid, auto-anchor promotion
from similarity, or success-rate denominator over unrated works. Later lower ratings
also do not erase a historically witnessed positive; current preference change and
explicit revocation would need a separate contract. Positive counts describe supplied
observations, not exhaustive store coverage or a live inventory.

### Exact normalized input

Call `analyze(events, nodes, features, encoder, items, attempt_ids, anchors, cutoff,
facet='humor', zone='UTC')`. Use the original-act, full-lineage and exact cached-feature
contracts above. `items` is a bounded list of `{node_id, kind}`; `attempt_ids` explicitly
names the attempts to inspect. The prototype never guesses that a message was an
attempt at humor. Item kinds are message, joke, journal, image, song, video; unsupported
kinds are counted as such. Humor accepts message/joke; taste accepts the three text
kinds. Known mode, surface and item kind must all match the positive reference.

An anchor has exactly these fields:

- `evidence_id`, `node_id`, `content_sha256`, `source_record_sha256`;
- `actor: owner`, `witnessed: true`, explicit offset-aware `observed_at`;
- `source`, `value`, and `link`.

Adjacent-exchange links contain `kind: adjacent_exchange`, `exchange_id`, `target_id`,
`target_sha256`, `reaction_id`, `reaction_sha256`, `target_index`, `reaction_index`.
`value` is the bounded reaction text. Exact-item links contain `kind: exact_item`,
`item_id`, `item_sha256`, `item_kind`; value is the star rating or the Landings enum.
The source record hash binds the claimed observation, but the prototype does not
independently authenticate that record, owner identity, adjacency or encoder cache.
The private adapter must supply that evidence; synthetic receipt claims alone are
not production proof. Repeated identical observations are deduplicated, conflicting
observation IDs or reaction joins refuse, and several anchors on one act still yield
one positive reference act. All observations must occur after the original act and
before cutoff. The explicit actor must be the owner; text saying she liked something
is not a substitute for her outcome.

### Score and sparse coverage

For each attempt, reference acts **and their positive outcomes** must predate the
attempt's local calendar day. The entire target day is held out. This conservative
past-only leave-one-day-out rule prevents a later laugh/rating from leaking backward
into a target score. Reference scope is mode + surface + item kind; it never pools
intimate with everyday, voice with chat, or practice jokes with ordinary messages.
Mode provenance remains available through the reused preparation contract. Family
rules are historical assumptions, not independent evidence; there is no family
comparison or reference-adoption action here.

With fewer than two distinct eligible positive act days, similarity is absent and
status is `insufficient_positive_days`. With two or three days, the prototype reports
only semantic/style/joint **positive familiarity**, each one minus the distance
defined above, and keeps the empirical score absent with `band_location: abstain`.
Four or more days permit the same day-equal held-out empirical rank and inclusive
[0.2,0.8] abstain band as the voice prototype. Reference days contribute equally to
centroid/style construction; each act occurs once regardless of duplicate anchors.
A score is familiarity to a small observed-positive set, not P(funny), P(liked), a
character verdict, a correctness judgment or a demonstrated calibrated probability.

Coverage reports total supplied positive acts and days, positive observation days,
known source counts, unknown/excluded observation counts, and actual available
reference acts/days for each requested scope. Thus three total positives may provide
zero references in a given mode/surface, and three acts on one day provide only one
reference day. The synthetic three-positive fixture explicitly has no empirical
calibration. Claude's reported current three positives are not copied into fixtures
or treated as a measured result of this code. No private data was read.

Return values are `(aggregate_report, private_receipts)`. Aggregate output includes
only fixed scope labels, counts and mean familiarity. Dates, turn/source IDs, content
hashes, reference membership, raw text and vectors remain out of it. The private
receipts retain exact reference acts, the eligible evidence observation, mode/surface,
reference version, target day and score status. A target's own later positive outcome
may be shown descriptively at cutoff but never influences its calculated score.

`broker/tests/test_witnessed_humor_taste.py` uses synthetic text and vectors for
adjacency, owner/role, ratings, temporal leakage, duplicate/conflicting evidence,
mode/surface/item splits, sparse coverage, no-negative semantics, unknown features,
indirect influence, textual taste and unsupported media, and aggregate privacy.
Run with `python3 scripts/run_isolated_test.py broker/tests/test_witnessed_humor_taste.py`.
No model is served and no fallback occurs; runtime model attribution is not inferred
from an encoder name. Actual production call savings remain zero.
