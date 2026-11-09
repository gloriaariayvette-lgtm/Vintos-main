# Offline numerical judge candidates

Two components are prototyped: **witnessed recurrence counts** and **thread-grouping
suggestions**. They have explicit numerical targets and can be tested without
reading private messages, running an encoder, or evaluating the system's identity.
They do not replace any current judge, author a thread, consume a thread, score a
person, nudge emotion, or change a feed. No runtime module imports this directory.

This responds to coordination note #42. Source baseline is review tip
`ef0b2fb5f512478c286cfee9a47258d6d3d6de33`. The earlier accepted judge review and
existing character-reference/on-message innovation experiments remain applicable.
The inventory below is a source-based design assessment, not measured task accuracy.
The synthetic tests listed for other candidates are proposals, **not executed tests**.

## Selection and cost

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
held-out familiarity. This batch does not duplicate either implementation.

## All 33 entries

“Component” means advisory numerical evidence only. “Retain” means no defensible
full replacement with a generic frozen encoder or plain statistic. Links identify
the current source path/function; existing effects stay untouched.

| Entry / source | Decision and explicit input | Proposed non-LLM scorer | Principal failure mode | Offline synthetic test before any integration |
|---|---|---|---|---|
| A [voice coherence](../../bin/voice_coherence.py), `check:100` | Component: finalized replies, reviewed mode/surface reference and provenance | Existing leave-one-day-out semantic/style percentiles | Familiarity penalizes legitimate novelty, refusal or a different surface; does not identify performance | Hold out a day, include benign novelty/refusal and matched other-author controls; verify missing references stay unscored |
| B [deviation](../../bin/deviation_check.py), `check:182` | Component: same inputs plus independently labelled contextual stance | Separate familiarity from labelled stance agreement; do not blend them into authenticity | Topic overlap hides opposite stance; judge nudges leak into reference state | Same-topic opposite-stance pair and indirect nudge ancestry; refuse a unified truth verdict |
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
