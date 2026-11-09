# Witness slices 1 and 2: offline foundation

Status: offline replay plus disabled request-local capture hooks. The reviewed
capture base and later submitted repairs are distinguished in the current review
map below. Synthetic contracts do not establish live eligibility or head accuracy.
No scheduler, model calls, training, feed substitution or deployment is performed
by this replay. This reader is a separate strict consumer; its exclusions do not
silence an act or remove it from a live store.

## What is implemented

`scripts/witness_receipts.py` defines a versioned, allowlisted receipt for the
final delivered response. It records a stable turn ID, surface, generation and
finalization times, content digest, observed selected generator, failed/discarded
attempts, and a context-receipt reference. Requested generator configuration
never establishes which generator actually served the response. Unknown facts
stay unknown. `evidence_provenance.normalize()` retains a supplied receipt, and
the merged-chat writer carries it and the effect/exclusion fields through.

The lineage graph requires a complete ancestry declaration, with parent times
no later than child times. A receipt read by the value map and subsequently read
in a reply context counts as indirect influence. Missing, cyclic, incomplete,
future or unrecognized ancestry is unknown. This is an evidence contract, not a
claim that a producer can automatically know every input: no producer may mark
`complete: true` until all contributing context inputs have receipts.

The ancestry root must be a `context` node. Reply-to-next-context hops use a
`reply` node with `turn_id`, `context_receipt_id` also listed in `parents`, and
explicit `influence` (`clean`, `influenced`, `unknown`). A clean assertion cannot
clear influencing parents or explicit tactical/character-influenced flags. A
generated-output node cannot use `ordinary_source` to bypass this contract.
Traversal memoizes node standing within its remaining depth budget and checks
every edge's clock independently;
shared ancestry does not cause exponential replay.

`replay.py` accepts only explicitly supplied snapshots of canonical chat, merged
chat, the interaction ledger or private capture packets. It never searches backups or reinstates erased
history. It counts both provenance envelope fields, requires explicit witness
eligibility, and keeps unknown/denied duplicates out. Repeated copies of one
eligible finalized reply count once. Duplicate copies must all qualify: this is
deliberately conservative when a retained older copy lacks the new fields.

Existing `evidence_view.standing()` must be eligible too; unresolved or denied
record ancestry cannot be rescued by a clean new context receipt. Tactical
sources and dream/import/transplant/estimated-time/forgotten/deleted flags are
excluded. The merged projection retains original source and ancestry metadata.
Missing top-level IDs may join agreeing explicit envelope IDs, never guessed
IDs; conflicting or absent identities remain held. Duplicate hold diagnostics
retain the underlying reasons, counted per denied copy.

For stores that append device marks, optional `witness_final_text` and
`witness_final_sha256` preserve the exact producer-attested final response.
Both must agree with each other and the generation receipt. Final text must
equal stored content, except ledger rows may append device marks after it.
Unrelated stored content is held even when the separate digest is valid. They are carried
through the projection and used for scoring; no heuristic stripping or final
payload backfill occurs. Producers still need to capture these at finalization.

The behaviour receipt is currently descriptive: admitted reply count, word
length and question fraction. It assigns no authenticity, emotion or relational
verdict. Counts over input rows and counts over unique identified replies are
separate; their denominators must not be confused.

An explicit ledger `generated_output_witness_eligible: false` also denies new
witness admission even when another envelope claims eligibility. This denial
survives the merged-chat projection.

The innovation reader joins existing **on-message** self forecasts to exact
final responses by stable ID, surface and content digest. It requires an
independently retained checkpoint manifest with encoder identity and training
time, and cached embeddings of those exact responses. It imports no encoder.
Forecasts at/after finalization, context at/after message arrival, incompatible
vectors and ambiguous matches are unscored. One earliest unambiguous forecast
per target/checkpoint/encoder/surface/source counts; ahead forecasts are separate
and not used here. Training time is required before forecasting; file mtime is
not an acceptable substitute when a checkpoint was copied. Message arrival must
not follow response generation start. Equal-time context/arrival batches remain
unscored rather than assuming an order the timestamps do not establish.

Innovation percentiles use only outcomes finalized strictly before the forecast
was made, from this same replay and matching checkpoint/encoder/surface/source
and observed target-model/revision group. A result that became known while the
current reply was being generated cannot calibrate that forecast. Equal-time
outcome/forecast clocks do not establish order.
The default minimum is 20 earlier outcomes; until then the percentile is null.
A percentile is relative prediction error, not calibrated confidence in identity.
Comparator superiority is not presumed. The optional paired controls below require
an explicitly attested forecast-context receipt; missing controls remain unknown.

Rebuilds use the full explicitly supplied snapshot. There is no incremental
checkpoint to become stale when an input is removed; identical inputs reproduce
the same outputs in a new directory. This is not an always-on runtime.

## Snapshot contract and scratch command

One private JSON bundle contains:

- `input_kind`: `synthetic` or `retained_snapshot` (never mix their reports).
- `sources`: objects with `kind` (`canonical`, `merged`, `ledger`, `capture`) and
  `rows`. Canonical/merged rows have `role`, `content`, `turn_id`, `surface`,
  provenance and `witness_receipt`. Ledger adapters read `vintos` as the assistant
  content. Capture packets require `witness-capture-v1`, their explicit `lineage`
  and `reply_node`; reading them never upgrades delivery or incomplete ancestry.
- `lineage`: nodes with unique `id`, `kind`, epoch/offset-aware `at`, `complete`,
  and `parents`. Ordinary kinds are `context`, `ordinary_source`, `value_map`;
  influencing kinds are `character_score`, `behaviour_receipt`, `judge_effect`,
  `tactical`, `emotion_nudge`. Reply nodes have the additional fields above.
- `forecasts`: the existing on-message log shape (`ts`, `arrived_at`, `mode`,
  `turn_id`, `surface`, `self.emb`, `self.mode`, `self.source`,
  `self.checkpoint_id`, `self.context_last_ts`).
- `checkpoints`: a map from checkpoint ID to `encoder_id`, `trained_at` and the
  exact forecast `source` identifier.
- `embeddings`: records with `turn_id`, `response_sha256`, `encoder_id`, `emb`.

The normalized generation receipt shape is exercised by `fixture()` in
`broker/tests/test_judges_witness.py`. These fixtures contain invented content
only. Missing sources produce zero counts, not an automatic fallback to live
stores. Missing identity manifests/embeddings produce explicit unscored counts.

After a bundle has been placed in a private scratch directory outside the repo:

```sh
chmod 700 "$JUDGES_SCRATCH"
SPARK_WORKSPACE="$JUDGES_SCRATCH" PYTHONDONTWRITEBYTECODE=1 \
  python3 experiments/judges-witness/replay.py \
  --scratch "$JUDGES_SCRATCH" --input "$JUDGES_SCRATCH/input.json" \
  --output "$JUDGES_SCRATCH/replay-1" --cutoff '2026-11-09T00:00:00-06:00'
```

The cutoff is exclusive and must contain an explicit timezone. Output must be a
new directory. `.vintos`, `.openclaw`, repository roots/descendants/parents, home,
nonprivate roots and symlink escapes are refused. The replay's audit hook denies
network/subprocesses, rename/link operations and writes outside its new output
directory. This protects this trusted tool against accidental writes; it is not
a sandbox for hostile Python or native extensions. Tests additionally run under
the repository's OS-isolated runner.

`aggregate.json` contains descriptive counts/errors. `private-innovation.json`,
`private-feedback.json`, optional `private-behaviour.json` and `private-run.json`
contain private evidence bindings and must never enter Git. None is automatically
published. Public evidence requires an explicit privacy review; even aggregate
day-by-day activity can be sensitive. No raw text is emitted in these reports.

## Current review map (8 November)

This map supersedes the original next-increment list. It separates implemented
contracts from producer coverage and production acceptance; it does not authorize
any enablement. The append-only [implementation log](../../docs/judges-witness-log.md)
retains review history, measurements and exact earlier tips.

| Part | Implemented and exercised with synthetic fixtures | Still unproved or unfinished |
|---|---|---|
| Strict census | Explicit provenance, both envelope fields, duplicate denials, exact response/version and complete causal ancestry requirements; four source adapters | No historical backfill. Private-copy census reported in note 10 has zero strict-eligible turns; this is not a head-accuracy result. |
| Request and attempt capture | Request-local invocation binding, observed served identity where supplied, explicit selected attempt, repeat/fallback selection and final-return digest | Provider-attempt coverage remains incomplete; configured/relay names cannot fill missing observed identity. |
| Dependency receipts | Known counterpart origins, request inputs, observed router results, finalization boundaries, reply-to-context and indirect-effect contracts | Assembled context/value-map ancestry is not fully attested; no producer may declare completeness just to admit a turn. |
| Delivery | Framework handoff recorded separately | A trustworthy client-delivery acknowledgement producer is not implemented. Return/handoff is not delivery. |
| Shadow behaviour | Explicit window/surfaces, descriptive counts, model/revision groups and private member manifest | No character verdict, golden-day reference, learned identity model or live consumer. |
| On-message innovation | Exact reply/checkpoint/encoder joins, causal earlier-outcome percentiles, paired last-reply/recent-mean controls from attested forecast context | Requires private retained manifests, embeddings and forecast-context receipts. No superiority or accuracy claim follows from synthetic contracts. |
| Witnessed feedback | Exact-origin/adjacency checks, literal laughter and high practice ratings as positives; missing or lower ratings stay unknown | Requires producer-attested events and complete local sequence evidence. Existing weak inference/feed is unchanged. |
| Reproducibility | Private input/code/options/output receipt, deterministic restart fixtures and scratch-only outputs | Not source authentication, complete dependency locking or loaded-runtime attestation. |

Capture hooks and packet replay exist; production capture enablement does not.
The current sink requires `JUDGES_CAPTURE_SCRATCH` and `SPARK_WORKSPACE` to match
an isolated private directory. **Do not set these on production.** The separate
[disabled enablement proposal](../../docs/judges-capture-enable-proposal.md)
describes the future dedicated destination, retention bounds and acceptance.
Capture alone cannot supply missing ancestry or delivery evidence.

Code baseline when this map was prepared: `0ab38cdf`, including the preceding
manifest, embedding-copy and dependency-copy repairs. Its 184 affected local
isolated checks passed; the latest independent note read is #17, which approves
wants through `de2cd7b4`, not these later judges repairs. Their independent review
and full isolated Aegis suite remain pending. Integration, installation and live
acceptance are separate facts; no production state is inferred from a branch.

Remaining work within slices 1 and 2 is complete producer coverage and independently
verified private evidence, not another classifier. The current offline pieces can
be reviewed without weakening holds or enabling a live feed. Keep later character
references and judge replacement outside this slice. The [open-work log](../../docs/open-work.md)
remains the repository task ledger.

Golden days are not needed for these slices. Later they are familiarity
references, not good/bad identity labels. Candidate high-engagement dates require
Gloria's confirmation, and reference turns must stay separate from evaluation.

Claude Code reviews this branch, runs the full isolated broker suite on an Aegis
test merge, and handles reviewed integration. Gloria handles deployment. The
ten-minute coordination heartbeat remains active between batches.


## Implemented capture contract (disabled outside scratch)

`scripts/witness_capture.py` keeps capture state request-local. The avatar handler
observes results at all three router call sites, explicitly selects a raw reply
after fallback/repeat decisions, then finalizes the exact return text after its
last `guard_reply`. A packet records
`handed_to_framework` separately from `delivery: unknown`; it cannot claim
delivery. Context and reply nodes are explicitly incomplete. Attempt-history
coverage remains incomplete until every route/provider attempt is observed.

The shared `bin/gen_result.py` constructor and parsers keep their existing wire
contract. Only the router's direct-response adapter adds observed identity,
separate from its compatibility `model` field. Relay labels are retained as
claims, never as verified served identity; missing identity stays unknown.
The router's optional observer receives a deep copy of stage results, including
cyclic stage lists, without changing its return tuple or fallback behaviour;
observer errors or mutations do not alter the reply. Raw result text is used only for
transient selection hashes; capture copies no provider reason/tool text.
Selection by raw text is accepted only when exactly one observed attempt
matches. Identical text from multiple attempts remains unknown, even when their
model labels agree; explicit selected-attempt identity is still future work.

Capture is disabled by default. The optional sink requires
`JUDGES_CAPTURE_SCRATCH` and `SPARK_WORKSPACE` to name the same existing, resolved,
owner-private scratch directory. Live-store paths, symlinks, repository paths and
their ancestors are refused. Each packet is a new mode-0600 file. It is written
and synced under a temporary name, then published atomically using a hard link
that refuses existing names; temporary files are removed on success or caught
failure. An abrupt process kill can leave a hidden temporary file, which is
never a published capture packet. There is no
live-store writer or background reader. Packets contain the exact final text and
are private artifacts, never Git inputs. Test-mode and supplied generation
provenance are retained; absence remains unknown. Sink failures leave the reply
unchanged. Do not enable this on a serving process: an authorized isolated
harness must repoint all the handler's other stores and stub all senders too.

Synthetic tests execute the actual handler's capture/router/final-guard/return
segments with stubbed routing, and verify placement relative to all retries.
They do **not** run the complete HTTP application or demonstrate live capture.
On the integrated base, `scripts/server.py` is a symlink to `bin/server.py`;
the test checks their content parity. Other chat/voice handlers, complete context
dependency receipts, complete fallback-attempt coverage and source-store
integration remain pending. No production capture is enabled by this branch.

## Replaying scratch capture packets

The offline bundle also accepts a source with `kind: "capture"` whose `rows`
are explicit `witness-capture-v1` packet objects. There is no directory scan or
live discovery: an authorized scratch harness supplies those objects in its
private bundle and uses the same replay command above. The adapter retains each
packet's reply node, incomplete context nodes, provenance and test exclusions.
Identical repeated nodes are allowed across packets; conflicting nodes abort
the replay, including conflicts with the bundle's explicit lineage. Duplicate
identities in the explicit lineage list remain errors.

Current packets have unconfirmed delivery and incomplete ancestry, so they
contribute source/hold counts, **not eligible behaviour or innovation scores**.
The adapter never substitutes framework handoff for delivery or fabricates
missing dependencies. Synthetic integration tests run the private sink through
the real offline CLI twice, preserving the input and reproducing the report.
This is contract validation, not a real-data census or model accuracy result.

## External source leaves

An `ordinary_source` leaf requires an explicit origin from
`counterpart_verbatim`, `sensor_observation`, or `operator_configuration`, plus
the SHA-256 of the exact text version used. `source_node()` constructs this
producer attestation; it never guesses origin from wording. Missing/unsupported
origins, missing digests, generated-reply markers or parents on an external leaf
remain unknown. Generated material must retain its typed dependency graph.
An allowlisted label is a producer contract, not cryptographic authentication;
producer integration still must verify which source it actually read.

This does not backfill origins or make current capture roots complete. Existing
live eligibility/readers are unchanged; stricter ancestry applies only to the
new shadow witness.

## Handler request identity and dependency observation

The scratch avatar hook now assigns a distinct invocation token before each of
its three router call sites. It keeps the token belonging to the result the
handler actually chooses, including repeat acceptance/rejection and replacement
failure. Selection uses both that request token and the observed returned-root
attempt ID; an exact raw-text digest additionally checks the binding. Identical
text in two attempts is no longer ambiguous on this path. A missing, invalidated
or foreign token remains unknown. The older text-only helper still refuses
ambiguous matches and is not used by this handler.

Each request fingerprint covers the exact ordered handler arguments: system,
conversation (including structured message parts), parameters and reasoning flag.
It excludes endpoint/authentication material. This is a **handler-argument**
receipt, not a claim about provider wire serialization or complete internal
fallback/retry history. The packet separately retains all observed attempts,
including when no result is selected, and raw-to-final digest changes after
postprocessing. Request IDs and fingerprints survive provenance normalization
and the merged projection in the generation receipt.

Dependency nodes record every system/history slot, each invocation, observed
result and conditional retry edge. The context-local organ selection receipt is
recorded as **offers, not admission**; its error prose is never copied. An offer
is not proof that material reached the final prompt. Existing tactical generation
provenance adds a direct effect dependency. Unknown origin on any assembled
message remains unknown, even for role=user. Generated/history content is never
promoted to an external leaf from its wording or role.

The turn's aggregate dependency root is finalized after the calls. It deliberately
remains incomplete and is not a pre-generation clean-context attestation. Actual
handler request/result wall clocks are recorded; pure synthetic callers without
a result clock explicitly mark their result timestamp as a request-start lower
bound. Clock regressions invalidate observation, not the reply. Full upstream
value-map/organ ancestry, admission receipts, internal provider attempts and
client-delivery acknowledgement are still missing. These packets therefore do
not certify strict eligibility or enable any feed; all capture remains opt-in to
private scratch and disabled in ordinary serving.

### Explicit counterpart fragments

The scratch avatar producer now uses the authenticated request's explicitly
supplied `original_text` field to attest a counterpart fragment. It never uses
the older fallback from that field to the composed `message`. A fragment must
occur exactly once in the supplied current-message slot, either in its plain
text or in exactly one structured text part. It records a source-version hash,
whole-message hash, slot, text-part index and Unicode-codepoint span; it copies
none of the incoming text or attachments into the receipt.

On each invocation the binding is applied only if that exact message version
is still at that exact slot. A retry's extra instruction is not counterpart
input. Identical history elsewhere, moved/edited messages, absent or empty
markers, ambiguous occurrences and nontext parts cannot borrow the binding.
The full assembled input and turn context remain incomplete/unknown: knowing
one external fragment does not establish the origin of framing, images,
subconscious material or history. This is a producer attestation based on an
explicit client field, not independent authentication of the words. Binding
errors affect observation only; ordinary reply generation and feeds are unchanged.

### Parentless generated ancestry

A complete flag with an empty parent list is insufficient for any generated
node kind, including context and value-map nodes. Such a leaf remains unknown;
only an explicitly attested allowlisted external source can end a clean chain.
An external sibling does not compensate for a missing generated ancestor.
`operator_configuration` means static operator configuration only; generated
self-model/context content must retain its generated parents.

The separate production capture proposal is
[documented here](../../docs/judges-capture-enable-proposal.md). The current
scratch sink must not be enabled on a serving process by changing its workspace.


### Paired forecast-context controls (offline only)

The replay can compare each on-message prediction with the last assistant reply
and normalized recent mean from the **explicit context used by that forecast**.
It never reconstructs that context by selecting nearby rows from a global store.
A forecast may carry `self.context` with this contract:

```json
{"schema":"forecast-reply-context-v1","complete":true,
 "scope":"forecast_context_assistant_replies",
 "as_of":"2026-01-01T00:00:00Z","evaluation_block":"synthetic-block",
 "reply_refs":[{"turn_id":"synthetic-prior","response_sha256":"exact-final-digest"}]}
```

The producer attests that these 1–6 references are the complete assistant subset
of its context, ordered by finalization time. `as_of` must equal
`self.context_last_ts` and precede arrival. Each reference must be strictly
eligible, have the same surface, an exact final-response digest and an embedding
from the forecast checkpoint's encoder. Repeated, target, tied-time, reordered,
future, missing and conflicting references are unavailable. Individual vectors
are normalized before averaging; a zero mean is unavailable.

Missing controls retain the head observation and increment a separate reason
count. Comparisons pair all three errors on the exact same targets and separate
checkpoint/encoder/surface/source and explicit evaluation blocks. The aggregate
uses ordinal comparison/checkpoint groups, never private identifiers; its paired
head mean is distinct from the overall head mean. Positive improvement means
baseline error minus head error. These are descriptive errors, not calibrated
pass verdicts or confidence intervals. Head percentiles use only outcomes finalized strictly before the forecast,
within the same checkpoint and observed target-generator group, across blocks.

No live producer emits this context receipt yet. A supplied receipt is a producer
attestation, not independent proof of prompt contents. Synthetic contract tests
are not a real-data baseline win, and this adds no feed or eligibility backfill.


### Bounded shadow behaviour receipt

The optional summary consumes only the existing strict census's unique admitted
replies. Specify both an inclusive `--behaviour-start` and one or more
`--behaviour-surface` arguments; the existing exclusive `--cutoff` ends the window.
For example, append these arguments to the scratch command above, using an actual
surface name from the retained receipt schema:

```sh
--behaviour-start '2026-11-02T00:00:00-06:00' --behaviour-surface chat
```

`chat` is an example configuration, not an inferred alias for every surface.
Omitting the window/scope leaves this instrument `not_configured`. No store or
surface is discovered automatically. Selecting a surface is analysis scope, not
permission to bypass witness admission. Means are never pooled across surfaces,
observed served models or served revisions. A requested model is not a group
identity. Missing revision stays explicitly unknown rather than guessed.

`aggregate.json.behaviour_receipt` contains ordinal groups, observation counts,
mean/median whitespace-delimited word counts and literal question-mark fractions.
Empty windows have no trait values: no eligible observations is not zero curiosity
or engagement. These counts describe this snapshot only. They do not establish
stream completeness, activity on absent days, character, emotions or relationship
quality. No daily breakdown, text, identity, hash or date is emitted in this new
aggregate object. Group numbers are local to one report, not persistent identities.
The original census-wide descriptive fields remain available for compatibility.

`private-behaviour.json` is mode 0600 and contains the window, explicit scope,
group identities and exact member turn IDs, response digests, generation-receipt
digests, context references and per-member measurements. It contains no raw text
or vectors, but is still private. Its versioned receipt ID hashes this manifest;
the CLI also binds the canonicalized source bundle digest. Preserve that private
bundle to audit admission/ancestry; the output is not an independently sufficient
proof. Reordering admitted rows is deterministic. Removing a member or changing
a contributing receipt/window changes the receipt identity. Rebuilding after
source removal cannot retain a stale incremental reference.

There is no writer into his context or value map. If a later reviewed consumer
reads this summary, it must record a `behaviour_receipt` effect dependency: a
new name or a weekly schedule cannot make its descendants independent evidence.
Current transitive influence checks already exclude such descendants. This
increment is a scratch instrument, not a deployed character judge. Claude owns
retained-data measurement and full isolated Aegis review; synthetic fixture
results do not demonstrate real-world accuracy.


### Explicit feedback joins (shadow only)

The optional bundle `feedback_events` implements the operational labels from
Claude coordination note 2, separately from the existing inferred-laughter feed.
No live humor script, practice store or training input is changed. Missing events
remain missing evidence. `aggregate.json.feedback` reports observations, reasons,
held counts and unique targets with a recorded positive marker, never a flop rate.
A target without positive evidence is unknown, including after a delayed return.

Each event needs `schema: witness-feedback-v1` and a stable `event_id`. Feedback
must explicitly carry `witnessed: true`; inferred, deleted, forgotten, estimated,
imported or transplanted evidence is held. Identical event copies count once;
conflicting copies are all held, with their timeline positions still occupied.
Even a record with a missing or malformed event ID occupies any valid claimed
stream/position; it cannot disappear and make a neighbour look unambiguous.

For chat, provide both timeline events:

- An `assistant_reply`: `turn_id`, `content_sha256`, `surface`, exact `at` equal
  to its finalization time, `stream_id`, integer `position`, and
  `sequence_complete: true` and `witnessed: true`. This timeline attestation must
  itself have no inferred/deleted/forgotten/estimated/imported/transplanted marker;
  an eligible target reply cannot repair missing or denied sequence evidence.
- The immediately following `counterpart_message`: the same surface/stream,
  `position` exactly one larger, `previous_event_id` naming the reply event,
  `sequence_complete: true`, `origin: authenticated_owner_message`, `witnessed:
  true`, offset-aware/epoch `at`, private `text`, and its exact `content_sha256`.

The target must be independently strict-eligible in the census. The predecessor
is resolved from all supplied timeline positions, never the eligible subset.
Intervening excluded replies, gaps, collisions, changed versions/surfaces, missing
sequence evidence and equal/reversed clocks cannot create a positive join.
Private chat observations bind both the feedback event digest and the exact
predecessor event digest; practice ratings have no predecessor digest.
An isolated token `haha` or longer repeated `ha` (case-insensitive, optional final
`h`) is the positive marker. A single `ha`, `lol`, an emoji or no such token stays
unknown under this particular rule. This is literal marker detection, not a
semantic or emotional judgment: quoted or sarcastic uses are not understood.

For a practice, a `practice_rating` carries `origin: authenticated_owner_rating`,
`witnessed: true`, `at`, integer `stars` 1–5, `target_turn_id`, `target_sha256`,
and `surface: humor_practice`. It joins only that exact version of a strict
census-admitted practice output on that surface. No text-prefix join or implicit
mapping from a historical joke string. A 4 or 5 is positive; 1–3 are retained
ratings with an unknown label, never negatives. Distinct repeated ratings remain
separate observations but contribute at most one unique positive target. The
summary says a positive was recorded, not that it is the latest preference.

`private-feedback.json` (0600) contains event/target identities, feedback and
target digests, timestamps, ratings and reason/label. It emits no raw message text
or vector. It must stay outside Git. Aggregate reason counts are not permission
to publish private timing/activity details elsewhere.

Origin, complete sequence and practice surface are **producer attestations**;
this reader does not authenticate an owner from JSON or manufacture a complete
stream from a capped log. No live producer is added by this increment. A reviewed
collector must establish those facts from actual retained sources, and keep
unverifiable historical associations unknown. The old three-hour inference is
preserved as its existing separate channel and is never promoted by this reader.
No positive receipt bypasses target provenance or transitive influence exclusion.


### Forecast-time references and duplicate identity

The causal-innovation revision repairs two shadow-reader errors. Previously, the
reference set was cut at the target reply's finalization rather than at forecast
time; an overlapping reply could therefore enter the reference after the
forecast. Also, duplicate detection compared derived error/control summaries,
so different same-time forecasts with equal cosine error could look identical.

A private `forecast_sha256` now binds the full canonicalized supplied forecast,
including its vector and producer/context claims. Earliest-time records must
agree exactly; different attestations are held even when their numeric errors
coincide. Exact duplicate copies still count once. Later forecast attempts do
not replace the earliest eligible prediction. The digest stays in private output,
not the aggregate; no vector is emitted.

Reference percentiles and paired comparison groups additionally separate the
observed model and revision that produced the target reply. A chat-model switch
cannot silently reuse the old target distribution. Unknown served identity is
held, not inferred from the request. This does not turn a percentile into
calibrated confidence or establish independence between turns. The strict
pre-forecast boundary also does not prove when an embedding was computed: that
requires retained producer evidence. The independent existing self-head audits
are separate tools and are unchanged by this repair.

### Incomplete known influence

A known judge-effect node with missing ancestry is `influenced_incomplete`, not
a clean leaf and not merely unknown. This state propagates through incomplete
contexts and unknown siblings; the census reports `influenced_incomplete_lineage`.
It remains excluded exactly like complete influence and unknown lineage. Invalid
clocks/identities do not become trusted influence attestations. This distinction
improves counts only and changes no live evidence admission.


### Malformed innovation evidence

Forecasts and embeddings must be lists and checkpoints a mapping; a wrong-shaped
container is rejected rather than interpreted as an empty evidence set. Within
valid containers, malformed forecast/head/manifest records receive the existing
`missing_or_invalid_forecast_evidence` count. Embedding records without an explicit
nonempty string turn ID receive `missing_embedding_identity`; no target is guessed.
Identifiable embedding copies remain in conflict checks, including malformed
vectors. A valid duplicate cannot hide an invalid matching target/version copy.

These held counts have different units: the new identity count is per embedding
record, while forecast holds are per forecast. They must not be summed as a count
of distinct replies. Valid records retain the existing causal scoring, checkpoint,
source and served-model grouping. This handles malformed supplied snapshots only;
it neither repairs missing upstream provenance nor expands witness eligibility.


### Strict lineage identity and clock shapes

A reply dependency's turn_id must satisfy the same nonempty, bounded string
contract as a generation receipt. Truthy booleans, numbers, containers and
oversized strings are not identities. Malformed node kinds and root identifiers
return unknown rather than crashing graph traversal. The traversal boundary uses
the shared explicit timestamp parser: booleans, nonfinite values, negative times
and timezone-naive strings are unknown. Valid offset-aware boundary strings are
handled consistently with epoch timestamps. These checks tighten shadow evidence
admission only; they do not rewrite legacy records or alter any live feed.


### Shared ancestry and depth limits

The existing 128-level traversal bound applies to every path, including paths
through cached ancestors. A shorter path cannot lend its cached clean result to
a longer path whose remaining budget cannot reach the same leaves. Memoization
is keyed by node and remaining depth, while each edge's clock and active-cycle
check still run before cache reuse. Over-deep ancestry remains unknown in either
parent order; within-bound shared graphs retain their result without exponential
re-walking. This is a strict shadow-consumer repair, not a new live gating rule.


### Private replay run receipt

The CLI writes `private-run.json` last, with mode 0600 in the explicit scratch
output directory. It binds the exact input bytes, input kind, parsed cutoff,
optional behaviour window/surfaces, innovation history minimum, named local
scoring files, Python implementation/version, and every report's exact bytes.
The run fingerprint is SHA256 of the remaining manifest serialized with sorted
keys, compact separators and no nonfinite numbers. Repeating the same replay
under those recorded conditions yields the same receipt; private input/output
paths and wall-clock run time are deliberately absent.

Before accepting a copied result, recompute its output hashes and sizes, compare
the input hash with the retained bundle, and compare the named code hashes with
the review checkout. The CLI checks code hashes before and after scoring; a
change aborts before creating outputs. A missing, partial or mismatching receipt
is not a verified completed run. Partial output directories are never reused.

Keep this receipt private, even though it contains hashes rather than message
text. It is not a signature, proof of source authenticity, complete dependency
lock, or attestation of the interpreter's loaded runtime. It does not repair
missing lineage or prove that a snapshot is complete. All existing strict holds,
scoring, live feeds and capture enablement remain unchanged.


### Every embedding copy must be valid

All cached copies matching a target's response hash and encoder are validated
individually, including copies that compare numerically equal. Python considers
booleans equal to 0/1, but boolean embedding components are invalid evidence.
A valid first copy cannot hide a later malformed one, and input ordering cannot
change this decision. Matching context copies receive the same check. Invalid
target copies hold the forecast; invalid context copies make paired baselines
unavailable while preserving the independently valid head score. Equal valid
integer/float copies remain usable. This repairs offline scoring only.


### Dependency copies retain JSON identity

Repeated capture dependency nodes must have the same complete JSON attestation,
compared with sorted object keys. A boolean and a number are distinct, including
nested fields; a later copy cannot replace `complete: true` with `complete: 1`,
or vice versa. Numeric spelling changes such as 1 versus 1.0 also conflict under
this exact-copy contract. Object key ordering is irrelevant; array order remains
part of the attestation. Conflicts abort the supplied snapshot, preserving the
existing policy of never choosing a winning dependency claim. Valid identical
copies keep the first node. No live merger or eligibility rule is changed.


### Independent evidence coverage

`census.evidence_coverage` reports independent field counts alongside the existing
first-failure admission reasons. Its denominator is every supplied assistant copy,
including duplicates, excluded acts and copies outside the cutoff. User rows are
not included. Each field's counts sum to `assistant_copies`; empty input has zero
copies and an empty field map. These counts are not unique-turn counts and are
not evidence that a source stream is complete.

Receipt state is `absent`, `unknown`, `conflicting` or `recorded`. Only an agreeing
recorded receipt supplies further field observations: row identity/surface binding,
observed selected generator, selected request/input-hash binding, delivery state,
exact response binding, context-lineage standing, and supplied final-reply lineage. An absent, malformed or
conflicting receipt leaves those fields `not_evaluated`. A recorded request
binding means the receipt names the request and valid hash; it does not verify
the original provider input or claim complete provider-attempt coverage.

For example, a row held for unconfirmed delivery can independently report unknown
served identity, request binding and ancestry. A tactical row can have observed
generator metadata and still be excluded. Coverage never substitutes for the
strict admission result, clears a hold, infers a missing fact or feeds a live
consumer. The report carries statuses/counts only, never the identities or hashes
being assessed. Existing private-artifact and aggregate-review rules still apply.


### Snapshot JSON is checked before evidence admission

The CLI rejects repeated object keys at any nesting level, including duplicates
with equal values. Otherwise the default JSON parser would silently keep the last
value and could erase a provenance denial or input-kind declaration before the
strict census sees it. Object keys are checked after JSON decoding. Reusing a key
in different objects remains valid.

NaN, Infinity, negative Infinity and numeric literals that overflow to infinity
are also rejected, as is a top-level value other than an object. These are bundle
errors: no output directory or report is created, and the input is unchanged.
Duplicate-key diagnostics deliberately omit the key and values. Valid JSON with
malformed evidence records still follows the existing held/counting contracts;
this does not repair records, alter live-store readers or change scoring for
valid evidence. All earlier private snapshot and aggregate-publication rules apply.


### Supplied final-reply ancestry also constrains the strict reader

A clean pre-generation context cannot clear an explicitly supplied influenced or
unknown final reply. When a row contains `reply_node`, the strict reader requires
its ID to resolve to the same complete JSON node in the supplied graph; its turn,
context, response digest and final timestamp must match the generation receipt.
It then evaluates that reply's ancestry through finalization time, separately
from the prompt-context check at generation start. Finalization effects and
unknown editors therefore cannot disappear behind a clean prompt reference.

The scratch capture adds the exact final response digest to its reply node. The
merged projection carries a supplied reply node without rewriting it. Existing
live evidence consumers are unchanged. Missing, stale, malformed or conflicting
supplied nodes remain unknown; influenced descendants remain excluded from this
strict offline reader. Older rows without this optional node retain their previous
admission contract; coverage labels them `not_supplied`, never a proved clean
finalization. Existing captures with incomplete ancestry remain unqualified.


### Raw provenance at the scratch producer boundary

Shadow capture checks the raw envelope before retaining a normalized witness
permission: `may_witness` must be a boolean, the explicit string turn ID must
match the capture, and the envelope must be present. Truthy strings/numbers do
not become permission. Malformed inputs produce an ineligible packet rather
than losing the capture; explicit tactical influence is retained even when
other fields are malformed. This guard is local to scratch capture. It neither
changes the shared legacy normalizer nor certifies complete ancestry or delivery.


### Forecast ordering precedes validity filtering

For an identified target/checkpoint/encoder/surface/source group, the reader
retains the declared forecast clock and complete-record digest before checking
vectors and causal validity. An invalid earliest record cannot be discarded to
score a later prediction. Distinct equal-time earliest copies conflict even if
one is unscorable. An identified record with an invalid/missing clock leaves the
group's order unknown; it does not get guessed after the valid records. A later
invalid record does not displace a valid earliest one. Records without enough
identity to join this group remain separately counted; other groups are unaffected.

`unscorable_earliest_forecast` and `unknown_forecast_order` are selection holds
counted per group that otherwise had a scorable candidate. Raw invalid-record
counts remain separate, so these counters are not additive populations. No
historical scores or private snapshots were recomputed for this synthetic repair.


### Feedback duplicate identity

Repeated feedback event IDs must carry identical JSON attestations, ignoring
object-key order but preserving value types. A numeric `1` cannot stand in for
an explicit `true` witness or sequence flag; an integer rating and a floating
copy cannot let input order decide which is selected. Conflicted predecessors
remain unavailable while their sequence positions stay occupied. Identical
copies still count once. This applies only to the offline feedback reader.


### Context-local rendered fragments (scratch only)

When the existing scratch and workspace settings match, `inner_context` retains
an ephemeral manifest of at most 64 offered fragments and 262144 codepoints per
assembly. A new assembly replaces it. Ordinary mode retains no extra rendered
text; output and persisted offer record shapes are unchanged. The manifest shares
the selection ID and clock of the observed offer metadata; capture requires both
to match. Returned manifests and captured fragments are independent snapshots.

Each invocation compares the retained fragments against its actual system string.
Unambiguous matches record whole-input and full-fragment hashes plus exact Unicode
spans on that invocation's input node. Repeated occurrences or identical text
from multiple offering organs are ambiguous. `not_found` means only that this
exact fragment was not found; it does not distinguish rewriting from omission.
Moving text into history does not borrow a system binding. Every retry is checked
again. Older/missing/failing producer APIs preserve ordinary capture without
fragment bindings. No latest-file read or time-window join is introduced.

Raw fragment text is not added to existing offer stores or persisted capture
packets; capture drops its transient copy on finalization. The producer retains
its bounded context-local copy until the next assembly/context lifetime ends.
The fragment nodes remain generated material with unknown parents and incomplete
ancestry. Exact content presence proves neither clean origin nor provider
consumption, semantic influence or client delivery. Other prompt parts, guard
notes and truncated/over-limit material are outside this bounded manifest. No
production enablement, full-coverage claim or live feed substitution follows.


### Guarded JSON reads during rendering (scratch only)

The rendered manifest optionally carries `guarded-reads-v1` observations from
`store_guard.load_json` calls made inside each existing renderer. The store is
never reopened for observation. Receipts retain a digest of the locator spelling
and a digest of the decoded text actually read, not paths or source text. This is
not a physical-file identity or a digest of the original encoded bytes. Loaded,
missing, empty, invalid and unreadable outcomes remain distinct. Defaults are not
labelled as stored data. No historical generation/source identity is inferred.

Limits are 64 observations and 4194304 hashed Unicode codepoints per renderer
(including nested observation scopes), at most 64 renderer manifests and 256
observations per assembly/capture. Over-budget versions carry `over_limit` without
a fabricated hash; omitted records mark truncation. An omitted entire manifest or
an invalid optional receipt is unavailable. Scratch packets validate the metadata
allowlist independently. Existing fragment bindings survive unavailable read
metadata, and saved offer-record shapes are unchanged.

These are conservative read dependencies: reading a JSON document does not prove
that every field contributed to the rendered result. All such nodes retain
`stored_unknown_ancestry`, `complete=false`; the renderer remains incomplete too.
`clock_basis=selection_completed` is the assembly observation boundary, not file
creation time or a claimed exact read clock. Direct `open`/`json.load` calls and
other I/O are outside `guarded_json_only` coverage; an empty list is not proof of
no dependencies. This increment does not yet capture the value map's generating
prompt or authenticate its upstream effects. Production remains disabled.


### Main-chat value-map read boundary

The main-chat handler can supply `value-map-read-v1` alongside the existing
inner-context manifest. Only explicit validated private scratch enables it.
It hashes the decoded source already read, verifies the existing deterministic
newest-entry/strip/1500-codepoint selection, and binds the selected hash to the
exact offered block. Source observation time is labelled `read_completed`;
a future read cannot attach to an earlier capture. Documents above 4194304
codepoints supply no observation; the existing display selection is unchanged.
No raw source or path enters this receipt, and the temporary full decoded
source is released after selection/observation.

This is a handler-local observation, never a latest-file lookup or time-window
join. A second handler read resets the observation even when the file is missing.
Binding is once before routing; every invocation independently checks actual
system presence, with retries, repeated copies and history movement handled by
the same fragment matcher. Old or failing optional observer/binding APIs do not
change output or disable an otherwise working capture. Generated value-map and
stored-source nodes remain incomplete, with unknown upstream ancestry. Other
surfaces and the map's own generating dependencies remain outside this increment.


### Existing value-map HTTP calls (scratch only)

`value-map-call-v1` observes each existing generator HTTP invocation separately.
Before the call, it hashes the exact constructed payload and ordered system/user
messages. Afterward it records returned/rejected/failed outcome, whole parsed
response hash, normalized returned-text hash when present, and a model identity
only when a returned response supplies a valid model field. The configured model
is recorded separately and never fills unknown served identity. Response metadata
is the server's report, not independent verification of loaded weights.

These are separate private `value-map-call-*.json` files (0600, atomic publication)
and are not chat witness rows or inputs to the strict chat census. No prompts,
response text, exception text, endpoint, credentials or paths enter the packet.
One record is one observed HTTP call, not a claim to observe backend retries or
fallbacks. Calls interrupted before the completion hook have no completed packet;
this is not a durable attempt-intent journal. Unobserved upstream dependencies,
build-level draft selection and the final map-file write remain explicitly
unrecorded. Do not join a call to an entry using timing proximity or text similarity.

All three deployed value-map source copies retain identical code. Prompts,
parameters, number of calls, return processing and existing map writes are
unchanged. Missing, old or failing observer/sink APIs fail open for generation.
Receipt publication reuses the existing private atomic sink; no capture is enabled
in production by this change. All verification uses stubbed HTTP and scratch.


### Build-local draft selection and written entries

An optional `value-map-build-v1` receipt links the existing generator's named
`draft_a`, `draft_b` and `synthesis` stages with an explicit build identity.
Context-local stage scopes attach call IDs as calls are made; there is no latest
receipt lookup or time/similarity join. Synthesis records the two actual draft
output hashes supplied by the builder and binds each to a unique, published,
returned call in its named stage. Identical text from different stages therefore
keeps separate call identities. Missing, duplicate, unpublished, mismatched or
clock-incompatible calls leave that dependency/selection unavailable.

The original selection branch names the selected stage. After the existing three
entry writes and file close succeed, the build receipt records the selected
returned hash, exact entry hash, stripped-entry hash, character count and append
or replace mode. It does not hash or claim the whole resulting file. Storage is
not transactional; file close is not an fsync or proof of lasting visibility.
The receipt explicitly says durability unconfirmed and whole-file state
unverified. A write failure, rejected build, unchanged-context early return or
interruption produces no completed-entry receipt. This is not a complete build
attempt journal. Existing archive and cache writes retain their behavior.

Stage scopes reset on exit and nested disabled scopes mask inherited attribution.
At most eight call objects are retained per build; overflow is marked and cannot
bind selection. Source input ancestry, internal backend attempts and durable
storage remain incomplete. The optional diagnostic below compares write/read observations; it does not
establish a producer identity or complete a source graph. The receipts add no model calls and do not affect existing outputs or
feeds. Missing/old/failed observers preserve normal behavior.


### Optional write/read observation diagnostic

The actual writer and main-chat reader now optionally emit v2 metadata with a
hash of the lexical absolute resource locator and the complete stripped entry.
The reader still records the entire decoded-file version separately. Neither
observer reopens the file, resolves symlinks or records a raw path. A path digest
is not a host/file identity; copied content, reused paths and unobserved writes
remain possible. Legacy v1 calls remain supported without inventing this metadata.

Supply an explicit `value_map_builds` list in the existing private replay input
bundle to request this diagnostic. No directory discovery or extra CLI path is
used. Only v2 writes with the same resource and full entry hashes, closed no later
than the read and before the exclusive replay cutoff, are candidates. Every
matching build is retained; no latest/nearest winner is chosen. Legacy missing
identities stay unavailable. Identical duplicate records are deduplicated;
conflicting identities or malformed supplied write records abort with generic
errors. This validates write observations, not their selected model-call graph.

`aggregate.json` gains only diagnostic counts. Candidate build IDs and read-node
IDs go into `private-value-map-writes.json` (0600), covered by the existing run
manifest alongside the input and scoring-code hashes. With the bundle key absent,
existing reports and output files remain unchanged. This diagnostic never edits
lineage, asserts origin, changes witness admission, or proves complete coverage.
A single match is still only a matching observation. Full producer ancestry and
trusted client delivery remain separate work; production capture stays disabled.


### Direct reads during value-map context assembly

The existing gather function now passes its direct file reads through observation
helpers. Each file is still read once, JSON uses the same default read/loads
operation, and selection, formatting, truncation and error handling are unchanged.
An opt-in build-local scope retains at most 64 observations and hashes at most
4,194,304 decoded codepoints; overflow is explicit. Records contain locator and
decoded-content hashes, completion time and unknown ancestry, never paths/text.
Only the bounded assembled context (up to the existing 60,000-codepoint cap) is
held transiently until the build returns.

Each actual call compares that assembly with its user slot: matched with exact
span/input hash, ambiguous, not_found or unavailable. Matching is per request;
synthesis does not inherit draft context. Packets copy metadata so later build
mutation cannot rewrite them. Repeated assemblies, backward clocks, exceptions
and missing/older APIs cannot supply a stale binding. Nested disabled scopes mask
inherited attribution, and separate contexts do not mix observations.

This is direct-read coverage during assembly, not a complete dependency list.
A read may have been discarded after JSON parsing, filtering or final context
truncation. No field-level contribution is established. Failed opens, directory
selection, evidence-view internals, cached/import-time material, separate temporal
and system reads, source history and effects remain outside this scope. Reads and
assembly ancestry stay incomplete, including when no direct reads were observed.
Early/failed builds without a completed call publish no such packet; this is not
a complete attempt log. No input, output, feed, model call count or admission
behavior changes; production capture remains disabled.


### Separate identity and temporal inputs

The existing system-identity and temporal readers now run in separate optional
read scopes. The identity read closes its existing file handle explicitly; text
and its existing fallback are unchanged. Temporal stripping/300-codepoint
selection is unchanged. Each component records source-version hashes separately
from its returned-text hash, then compares the returned text against the actual
request's intended slot (identity: system; temporal: user). Unique matches carry
spans and exact slot hashes. Missing/changed text, duplicates, future clocks and
repeated component assembly cannot inherit a binding.

A default identity can match the prompt with read_state unavailable: its presence
does not attest a successful file read. Empty or over-60,000-codepoint material
remains unavailable while generation receives the unchanged result. Each scope
uses the existing 64-read/4,194,304-hashed-codepoint bound; only two named auxiliary
components can be retained. Missing/old/failed observers preserve normal readers.
Scopes reset even on reader exceptions and disabled nesting masks attribution.

Both components remain unknown ancestry; field contribution, source history,
evidence-view internals, cached material, effects and delivery are not established.
Their call-packet metadata does not make a chat turn eligible. No source reopen,
new model call or feed change; production capture remains disabled.


### Returned evidence views in the value-map read scope

The existing consumer boundary records which path returned: ledger_view,
history_view, raw_fallback or empty_fallback. Existing filtering, raw fallback
and returned objects stay unchanged. The observer hashes canonical returned JSON,
not source-file bytes; source_version is explicitly unobserved. No file reopen,
additional view computation or provenance normalization occurs.

Returned counts preserve explicit standing, true/false/missing/malformed witness
permission, withheld replies, and named influence markers (tactical, character
influence or stratagem-influenced output provenance). Contradictory permission
and influence markers remain independently visible. These are observations of
returned records, not proof the records contributed or qualify for the census.
Row text/IDs, raw paths and exception text are never retained in these receipts.

Views share the context scope's 64-observation and 4,194,304-character hashing
budget with direct reads; at most 4096 rows are inspected per view. Hashing uses
incremental canonical encoding, and failed/oversized attempts consume their
bounded work budget rather than repeatedly hashing a fresh budget. Unsupported
shapes, non-finite data and oversize results retain an unavailable observation and
a truncated flag, preserving earlier observations and the reader's exact result.
Empty views and empty fallbacks have distinct paths; an empty view does not prove
the source was empty or readable. Context scope now says instrumented reads and
views during assembly. Full source/effect ancestry remains unknown.


### Optional build/call consistency report

Supply an explicit `value_map_calls` list alongside `value_map_builds` to check
the build's selected request and any selected synthesis call's named draft
dependencies. Nothing is discovered on disk. Matching uses the exact request ID,
build ID, stage, returned hash and causal clocks; identical output text cannot
substitute for a missing request. Build-local stage counts, publication/outcome
observations and supplied extra same-stage calls must agree. The checker retains
unavailable, missing_call, inconsistent_call and consistent as distinct states.
Synthesis selection and its draft dependencies are counted separately: a directly
consistent synthesis call with a missing draft does not become complete ancestry.

Exact duplicate packets are deduplicated; conflicting identities and malformed
required records abort generically before temporal filtering. Completed builds
at/after the exclusive cutoff are not counted. Required call/build metadata is
validated, but optional context/read payloads and served identity are not certified
by this consistency checker. An internal match proves neither trustworthy producer
attestation, successful storage, provenance completeness nor chat delivery.

`aggregate.json` gains counts under value_map_build_links. Exact IDs and dependency
states stay in `private-value-map-links.json` (0600), hashed in the existing run
manifest. With no calls key the previous reports/output set remain unchanged.
Neither producer records nor this report are admitted as chat turns; lineage and
census/innovation/behaviour decisions are untouched.


### Producer identity coverage is separate from linkage

The optional build/call report also counts identity coverage over unique completed
call receipts strictly before the cutoff. response_reported requires a returned
outcome, explicit response_metadata identity evidence, a nonblank bounded served
name and a well-formed response hash. It describes what the server reported, not
independently verified weights or authenticated origin.

Explicit unknown plus a null served name remains unknown. Both identity fields
absent is missing; partial, contradictory, claimed, malformed or failed-outcome
identity claims are malformed. Configured names never fill any gap. The aggregate
contains category counts only, never served/configured names. Link consistency
and identity coverage are independent: one cannot rescue the other or complete
ancestry. Existing witness admission and live feeds remain unchanged.


### Self-forecast input sidecars (producer evidence only)

With the existing validated private scratch capture opt-in, an on-message job may
write `self-forecast-inputs-*.json` alongside the other private receipts. Schema
`self-forecast-inputs-v1` binds the complete saved forecast row by canonical JSON
SHA-256, after its existing log close. The optional input subset records up to six
actual normalized reply inputs and their first-400-codepoint encoder versions.
It contains hashes, observed identifiers/clocks and explicit incompleteness,
never reply text or vectors. Close does not establish durable storage.

Replay does not yet consume this schema as `forecast-reply-context-v1`. Existing
control calculations require full reply versions, admitted origin identities and
compatible cached embeddings. Neither normalized text hashes nor exchange times
establish those facts; missing IDs must never be filled by text/time proximity.
The optional join below requires a separately supplied transformed-vector cache
and declared evaluation block. These receipts do not increase census eligibility or establish
forecast accuracy. No new collector/model invocation or live enablement is included.


### Optional controls from observed excerpt inputs

The later `self_input_controls` bundle key enables a separate descriptive report;
it does not convert sidecars into the older complete-context contract. It must be
an object with exactly these three lists:

- `receipts`: explicitly supplied `self-forecast-inputs-v1` sidecars.
- `embeddings`: cached excerpt vectors, each with `turn_id`, `response_sha256`
  (the full final reply), `encoder_id`, `encoder_input_sha256`,
  `transform: "final_reply_first_400_codepoints"`, and `emb`.
- `blocks`: nonoverlapping declarations with `block_id`, `declared_at`, `start`
  and `end`. Timestamps must be numeric instants or offset-aware ISO strings,
  with declaration strictly before start and start strictly before end.

Use the existing replay command and explicit private snapshot; there is no new
collector or encoder invocation. Only already selected/scorable innovation rows
are considered. The exact forecast-row digest must match a sidecar, whose clocks
must agree with that forecast. Each observed input ID must identify a previously
admitted reply on the same surface. This first version requires the captured full
normalized text hash to equal that reply's exact final version: if normalization
changed bytes, it remains unavailable until a separately verified transform exists.
The prefix hash and length are recomputed from the already supplied final text.
The cached vector must match that ID, full version, exact prefix and the encoder
in the existing checkpoint group. Every matching duplicate is validated.

Finalized prior replies must be strictly ordered and no later than the observed
context clock; no exchange timestamp is promoted to a finalization timestamp.
The same original target-vector cache used by innovation supplies the actual
reply. The block must contain arrival through finalization, with its end no later
than replay's exclusive cutoff. An outcome exactly at block end is excluded.
Malformed/conflicting sidecars and overlapping/conflicting blocks abort generically
before filtering, including records after cutoff. Identical copies deduplicate.
Missing evidence yields an unavailable reason without dropping the head score.

`aggregate.json` gains `self_input_baselines` with anonymous per-checkpoint/block
paired counts and mean errors/improvements, plus unavailable counts. Exact block,
turn and forecast identities stay in the optional 0600
`private-self-input-controls.json`, hashed by `private-run.json`. The old census,
innovation and full-reply controls remain unchanged, including when this key is
absent. Positive improvement favours the head; these are descriptive comparisons,
not a pass verdict, authenticity score or proof of held-out accuracy. Declaration
times are supplied evidence, not independently verified preregistration. Existing
checkpoint and prospective-clock requirements still apply; no legacy missing or
naive clock is repaired implicitly. No receipt authenticates its own producer.


### Coverage denominators for excerpt controls

`self_input_baselines.coverage` accompanies the scores. It separately counts
admitted replies, distinct targets with scorable forecasts, selected forecast
rows, paired forecast rows and paired targets before cutoff. Two checkpoints can
forecast one target; that is two forecasts and one target, not two conversations.
Missing and unscorable forecasts are counted as absent coverage, never as zero
error or zero innovation. These counts cover only the supplied admitted snapshot,
not all production activity or all attempted forecasts.

Every supplied block remains visible, even if empty or incomplete. Block source
counts use finalization in `[start, min(end, cutoff))`; a baseline pair additionally
requires arrival inside the completed block. Thus a target can have a scorable
forecast in the source window without qualifying for an in-block comparison.
`targets_without_scorable_forecast` does not distinguish an absent forecast from
one rejected by the existing innovation checks; that report retains its reasons.

Per-checkpoint/block coverage includes zero-pair groups, the scorable denominator,
paired fraction and unavailable reasons. A null `block_group` means the forecast
is outside any complete declared comparison block; no window is invented.
`block_group` is the ordinal of the validated declarations sorted by start, without
publishing block names or times. Empty blocks have counts but no fabricated score
group or fraction. The fraction describes evidence availability, not accuracy.
Scores, matching rules and witness admission do not change.


### Forecast clock diagnostics

The existing innovation report's `invalid_clocks` counts `missing`,
`missing_timezone` and `invalid` values under fixed fields `forecast_at`,
`arrived_at`, `trained_at` and `context_last_at`. Counts are per input record at
the first clock parse that fails, not an exhaustive audit of every field or a
count of unique turns. Earlier identity/shape/serialization failures can prevent
a clock from being parsed. Valid but noncausal times retain the separate existing
`noncausal_forecast` outcome; non-clock failures do not gain a clock label.

The existing generic held counts, candidate ordering, scores and eligibility are
unchanged. A missing/naive earliest forecast still prevents substitution by a later
one. No raw timestamps, IDs or exception strings enter the diagnostic. Missing or
null clocks remain missing; timestamps without offsets never borrow the replay
host's timezone. Source inspection and a synthetic test show the existing self
head's `_iso` helper emits a naive local string. That is a producer-contract risk,
not a measurement of the live history. Correct future producer evidence needs an
explicit observed epoch or offset-aware time; historical clocks must not be
silently reconstructed. This increment only makes the existing rejection legible.


### Prospective source-clock sidecar

A scoped scratch on-message forecast may additionally publish
`self-forecast-clock-*.json` (`self-forecast-clock-v1`). The existing source adapters
observe numeric epochs or offset-aware timestamps before legacy string formatting.
The source value must parse to exactly the epoch already used by the adapter;
naive strings, numeric strings, estimated chat timestamps, mismatches and malformed
values are not made explicit by inference. Outside the scoped scratch forecast,
there is no extra source-clock metadata.

The observation retains only the explicit epoch, source clock kind, source-value
hash and rendered-clock hash. If the existing merger selects an earlier timestamp,
its clock observation follows that timestamp, even though the higher-priority
source's reply text remains selected. An earlier source with unknown time clears
a later known observation; a later duplicate cannot backfill the earlier clock.

Publication requires the existing exact prediction binding and agreement with the
saved row's context-clock string. The sidecar hashes the entire unchanged saved
forecast row. This is source exchange time, not reply finalization or authenticated
source identity. The existing forecast row and `self-forecast-inputs-v1` sidecar
remain unchanged. Clock publication is independent and may fail after the input
sidecar succeeds; neither proves a durable or complete capture set.

This increment supplies prospective evidence only. Replay does not yet accept this
sidecar as a replacement clock, and no legacy forecast or timezone is backfilled.
A future explicit consumer must check the exact row binding, contradictions,
source-clock semantics and all existing prospective/identity requirements. Capture
remains disabled in production; all new writes use the existing private scratch
validation and mode-0600 publication sink. No source is reopened or model called.

### Optional source-clock consistency audit

Supply `self_forecast_clocks` as an explicit list of unchanged
`self-forecast-clock-v1` sidecars alongside `forecasts`. The optional aggregate
`forecast_clock_observations` checks exact canonical full-row hashes, on-message
mode, forecast/arrival instants and the rendered context-clock hash. Explicit
rendered instants are also compared to the observed epoch. A bound but unparseable
rendered clock stays labelled unparsed; the reader does not infer its timezone.
There is no discovery, proximity matching, historical backfill or replacement of
any scoring clock. Census, innovation and baseline selection remain unchanged.

All supplied sidecars are shape/clock validated before cutoff filtering. Identical
copies count once; conflicting records for one row abort with a generic error.
Receipts at or after the exclusive forecast cutoff are counted separately. Counts
of forecasts without receipts cover all supplied unique forecast rows, including
rows outside the cutoff; they are not production-wide coverage. A missing row is
unavailable even if another prediction has identical contents except one field.
The aggregate contains only fixed state labels and counts, and is bound by the
existing private run manifest. No additional private detail output is created.

These are consistency diagnostics, not authenticated source identity, complete
capture, reply finalization, witness admission or a scoring-protocol change. The
raw-source hash cannot be independently reconstructed from these sidecars alone.
The separate producer remains scratch-only; this option does not enable it.

### Private review formatter

`report.py` turns one completed replay's aggregate into a bounded Markdown review.
It does not collect, encode, score or rerun the census. It reads only `aggregate.json`
and `private-run.json` from the explicit run directory; it does not read the input
bundle, message stores, private per-turn outputs, vectors or checkpoints.

With `SPARK_WORKSPACE` already set to the same private scratch root used for replay:

```sh
python3 experiments/judges-witness/report.py \
  --scratch "$SPARK_WORKSPACE" \
  --run "$SPARK_WORKSPACE/replay-output" \
  --output "$SPARK_WORKSPACE/review-output"
```

The output must be a new sibling/separate directory, never inside or above the run.
The existing offline guard prohibits subprocesses, network and writes outside that
new directory. `review.md` and `private-render.json` are 0600 in a 0700 directory.
The latter binds the aggregate, supplied replay manifest, renderer and review bytes.
The formatter verifies aggregate hash/size and the supplied manifest fingerprint,
not the original input, reviewed scoring checkout or other outputs. This limited
check is stated in the report; it is not independent verification of the run.

Only fixed prose and validated numerical fields are rendered. Arbitrary source
labels, reasons, identities, dates, text and added fields are not copied. Synthetic
and retained-snapshot input kinds remain distinct. Per-copy evidence coverage is
separate from unique admitted replies; unconfigured, empty and unscorable outcomes
are distinct. Behaviour groups and checkpoint/block comparisons remain separate.
Full-reply and observed-excerpt controls never combine. A comparison reports the
three errors on its paired targets without a confidence interval or pass claim.
A zero-eligible run is explicitly insufficient, not zero error or proof of absence.

This is report scaffolding, tested on synthetic runs. It can format the reviewer's
counts-only snapshot result without changing that result or enabling any live feed.
No real-data report is bundled. Keep generated reports private until aggregate
publication has been reviewed; the formatter does not publish anything.

The review also renders the optional excerpt-control coverage already computed by
replay: all admitted replies, unique targets with/without scorable forecasts,
forecast rows with/without pairs, paired unique targets, and forecast rows outside
complete declared blocks. Forecast-pair and distinct-target fractions use separate
explicit denominators. A zero denominator is undefined, never 0%; absent coverage
is not filled in. The formatter checks these totals against the census, innovation
and comparison counts and refuses inconsistent evidence. It does not sum comparison
rows to invent a unique-target count. Per-block/day activity and arbitrary nested
coverage labels are omitted; no selection or score is recomputed.

### Historical model attribution (separate from strict witness admission)

The optional `historical_attribution` bundle uses existing labels and compute-ledger
records even when the new witness receipt is absent. The strict census's unknown
served identity does **not** mean that model tracking never existed. The reviewer
confirmed historical `served_by` labels and ledger model/provider fields. This
increment preserves that information without promoting it to observed identity.

Supply unchanged private ledger rows plus an explicit matching contract:

```json
{
  "historical_attribution": {
    "compute_ledger": [],
    "window_seconds": 5,
    "surface_callers": {"fixture-chat": ["router:fixture-chat"]},
    "source_surfaces": {},
    "naive_timezone": null
  }
}
```

This is a synthetic example. Replace the empty list with the explicitly captured
compute-ledger rows and use verified surface/caller mappings. No store discovery,
model call or new capture occurs. `source_surfaces` may supply a reviewed default
only where a source adapter's records omit `surface`; explicit row surfaces are
never overwritten. Do not label a mixed-surface store wholesale without evidence.
`window_seconds` must be greater than zero and at most ten seconds, fixed before
looking at agreement counts. Exact identifier matching does not use that window.

The tiers, in precedence order, are:

- `observed`: an internally consistent receipt binds observed selected model
  metadata to the explicit turn, surface and exact finalized reply version. This
  tier does not itself prove delivery, clean ancestry or witness eligibility.
- `ledger_attributed`: a unique scoped compute-ledger match with model/provider.
  Its private record retains the matching method and ledger hash. Ledger metadata
  can reflect configured/fallback names and does not attest successful generation
  or which output was finally selected.
- `recorded_label`: a nonempty row `served_by` or `model` label, with conflicts
  between those fields kept unresolved. A configured name remains a recorded label.
- `unknown`: none of those usable facts. No model is inferred from date or a
  default setting.

Match `provider_request_id` from the row or its provenance envelopes first. An
explicit invalid, conflicting or unmatched ID never falls back to proximity.
Otherwise choose the uniquely nearest foreground call within the declared window,
with an exact allowed `organ` for that surface. Ties stay unresolved. Outbound
attempt/reservation records are not reply completions. A closest call with missing
model/provider or an explicitly failed/accounting stage cannot promote a farther
candidate. Unknown foreground call clocks for that caller prevent claiming a known
nearest call. Exact duplicate ledger records count once; differing records sharing
one provider ID stay ambiguous. A call used by different/unknown turn identities
or different final reply versions is held for reuse. Duplicate source copies with
the same explicit turn and exact final text may retain the same match.

`compute_admission.record` currently writes naive local `at` strings. No host-local
timezone is borrowed. An explicit `naive_timezone` may interpret such historical
clocks only when its provenance is established by the reviewer; it is recorded in
the input bundle and manifest. Ambiguous DST folds and nonexistent local times
remain unresolved. Missing reply clocks are counted separately; labels on those
copies are still reported but are not claimed to fall before the cutoff. Known
reply clocks at/after cutoff are excluded from tier totals. Calls need usable clocks
before the cutoff even for ID matching. Numeric or offset-aware instants need no
extra interpretation. Conflicting `ts`/`timestamp` fields remain unresolved.

`aggregate.json.historical_attribution` contains fixed tier, join-state and
label/ledger agreement counts only. Denominators are **assistant source copies**,
not distinct training turns; no sum of copy counts becomes a training-set size.
`private-model-attribution.json` retains per-copy model/provider, explicit identity,
reply/ledger hashes and join method, mode 0600 and hash-bound in `private-run.json`.
It contains no message body but remains private. The local scoring-file receipt
includes `scripts/witness_attribution.py`. The review formatter shows the aggregate
tiers beside, never instead of, strict eligibility.

Recommended historical use: use separately labelled tiers for descriptive
model-switch stratification and per-model checks now. Agreement helps check the
recorded attribution, but is not two independent proofs if both labels came from
one configuration. Provider-ID and time-nearest joins should remain separate in
sensitivity checks. This increment makes **no training admission decision** and
changes no existing strict holds, behaviour/innovation scores or live feed. The
reviewer and Gloria still decide any historical character-training contract; that
contract must also handle provenance, final-version conflicts and duplicate turns.

### Private self-readout artifact retention

The optional sink now accepts `self-forecast-artifacts-v1` and
`self-audit-embedding-v1` packets. This is retention of existing computation, not
an additional evaluation, encoder invocation, training job or scoring admission.
The sink is still off unless explicitly configured/enabled. Its existing private
permissions, retention, caps and disable behavior apply to both packet prefixes.

At a scoped on-message forecast, a bounded checkpoint snapshot is parsed from the
same bytes whose hash is retained. The existing returned checkpoint ID must match
that snapshot or no artifact packet is bound to the saved forecast. Publication
follows the existing exact-row/input binding after forecast-log close. An oversized
snapshot falls back to ordinary loading without retention. No weights are copied.
The packet keeps a metadata digest, byte count, source/mode and **reported** fitting,
calibration and encoder-label fields. Reported dates are not a training-completion
receipt; file mtime is never substituted. `trained_at` and `encoder_id` remain null,
with training-completion and encoder-weight identity explicitly unobserved.

The same packet retains the last-six own-reply feature vectors already computed by
the readout, including their exact input hash, normalized full-reply hash, observed
source ID when present and first-400-codepoint transform. These may cover earlier
forecast targets as later conversation arrives; they do not cover every target or
prove a final reply version. Missing IDs remain missing. The prediction row itself
is unchanged. No additional encoder call is made.

The existing anchored **self** ranking audits also retain their already computed
vectors for matching self-text inputs. The wrapper returns the encoder's exact
result and propagates its original errors; retention failures are swallowed. Each
packet declares `ledger_vintos_strip_first_400_codepoints`, includes all bounded
matching source-row/full-text hashes, and never chooses a target from a prefix
collision. It records `target_selection: unasserted`: these inputs include candidates
and controls, not only realized targets. The optional source-identity scope now carries original string turn IDs through
`realized_ledger` when a bound source observation exists. Missing or non-string IDs
remain null rather than being inferred from timestamps. Unscoped/disabled reads
retain their original shape.
The other head uses the original encoder directly and is not instrumented here.
Duplicate inputs are retained once per audit invocation; later invocations can
produce duplicates, subject to the sink's existing cap/expiry. No new schedule.

These private packets deliberately are **not** automatically promoted into replay's
`checkpoints` or `embeddings` fields. That would erase the difference between a
normalized/truncated audit input and an exact final reply, and would invent missing
training/encoder provenance. Next integration must bind original reply versions and
explicit encoder identity, reconcile prefix versus full-target metrics, and retain
unknowns. The legacy scoring/reporting path is unchanged, including its existing
mtime-based cutoff; that cutoff is not copied into the new provenance observation.
No historical accuracy or complete retention claim is made. All packets/vectors and
source IDs stay private; only synthetic fixtures and aggregate checks belong in Git.


### Source identity before normalization and merge

A scoped self forecast or enabled ranking-source read now observes the actual
ledger `vintos` or assistant `content` field before the self reader's `his_words`
cleanup is lost. The private `self-reply-source-v1` observation carries a complete
source-row digest, raw reply digest, normalized reply digest, original string turn
ID/surface when supplied, and explicit `self_reader_his_words` transform. It never
copies message text, source filenames or timestamps. Invalid/oversized source rows
produce no observation; observer failure cannot reject an exchange.

The existing merger keeps its original text selection and chronology. The source
observation travels with the selected text/ID, **not** an earlier timestamp borrowed
from another duplicate. A preferred source with no ID cannot inherit a lower-priority
copy's ID. Original non-string identifiers stay unknown even though the legacy
exchange reader stringifies them. Neither the old deduplication nor its evidence
admission rules change.

`realized_ledger` opens a bounded optional scope around its existing single exchange
read. It keeps the same timestamp/gloria/vintos values, and adds a source observation
and observed turn ID only when the observation matches the selected normalized text
and ID. Source metadata is reset even on exceptions. Existing ranking transforms
ignore those extra fields; scores and model inputs are unchanged. Private forecast
and audit-vector references retain this observation as optional `reply_source`.
Older packets without it remain incomplete, not retroactively upgraded.

This closes the adapter's ID-loss gap for newly observed sources. It does **not**
attest that the source copy is authentic, final, delivered or eligible. Raw ledger
text can include appended device marks; normalized hashes are not substituted for
producer-attested final-text hashes. Joining these observations to independently
admitted finalized replies, preserving conflicts and verifying encoder identity,
remains separate from retention. No time-nearest identity join or scoring promotion
has been introduced.

### Optional exact final-version content joins

Supply `self_artifact_packets` as an explicit list of retained
`self-forecast-artifacts-v1` and/or `self-audit-embedding-v1` packets in the same
private replay bundle. Exact raw source rows must already be present in the
bundle's canonical/merged/ledger sources. The helper does no discovery, source
recovery, time-nearest matching, model invocation or additional scoring.

The join requires the original source-row digest, original string turn ID and
explicit surface; raw reply and normalized hashes must agree with the declared
self-reader cleanup. The exact source copy must independently pass existing
admission, and its receipt and producer-final text must agree with a reply already
admitted by the complete census. Missing or held duplicates remain held. An older
packet without reply_source remains missing rather than gaining identity by text.

The normalized string must equal the producer-attested final reply. Explicit
ledger final-text attestations can therefore handle appended device marks, but
heuristic cleanup of authored final text cannot stand in for that attestation.
The existing 400-codepoint input hash and length must also match. Short exact
inputs count as `bound_full_text`; longer final replies count as `bound_excerpt`.
Neither label proves which forecast selected the target or establishes encoder
weight identity. The helper deliberately does not validate or replace forecast-log
bindings; it only audits retained content references.

Identical packets count once. Different vectors claiming the same checkpoint,
reply/final-version/input identity mark every such content match conflicting;
malformed/nonfinite/boolean/zero vectors abort the audit instead of disappearing
behind another copy. Counts distinguish supplied/unique packets, source references
and unique admitted replies. A reference count is not an outcome count.

`aggregate.json.self_artifact_joins` contains fixed reason counts only. The private
0600 `private-self-artifact-joins.json` records packet/reference/checkpoint and
content hashes plus explicit turn IDs, but no vectors or message text. It is bound
by private-run.json along with the added helper implementation hashes. The review
formatter projects fixed count labels and rejects inconsistent denominators; it
never copies arbitrary source labels or IDs.

All results are content consistency only, including when a complete text matches.
Artifact-observation time, training completion and encoder identity remain
unverified; forecast-target selection is not evaluated. No packet is inserted into
scoring embeddings/checkpoints, no eligibility rule changes, and all pre-existing
census/behaviour/innovation output is unchanged (actual CLI regression tested).
The independent private census and full host suite remain reviewer-owned.

### Observed checkpoint availability, separate from training time

New checkpoint observations optionally carry `checkpoint-availability-v1`. In the
scoped on-message loader, wall and monotonic clocks bracket reading and parsing the
same bounded checkpoint byte snapshot. A successful `parameters_loaded` observation
records `parameters_available_by` at parse completion. The audit path only parses
metadata, so its `metadata_loaded` observation records `bytes_observed_by` but leaves
parameter availability null. This distinction is enforced during revalidation.
Neither stage supplies `trained_at`, an encoder identity or a historical fitting
attestation; old files/packets remain unobserved, with no mtime backfill.

A backward wall clock, or disagreement over one second between wall elapsed and
monotonic elapsed, produces `clock_discontinuity` with no availability bound. Invalid,
negative, nonfinite or boolean clocks and spans over 600 seconds remain unobserved.
Times are not clamped into a favorable order. Clock-observer failures cannot change
ordinary loading or the forecast. Disabled ordinary loading invokes no observer
clocks, and this adds no encoder/model calls or file/weight copies.

The optional artifact replay audit reports checkpoint-availability counts per
unique supplied packet. For a forecast packet it requires its exact saved-row hash,
on-message mode, checkpoint identity and matching arrival/forecast clocks. It then
distinguishes parameters parsed by the logged forecast, parsed later, outside-cutoff
forecasts and missing/inconsistent records. Metadata-only observations cannot count
as a loaded forecast checkpoint. Audit snapshots are reported separately, without
claiming prospective use. The formatter uses fixed labels and validates counts;
private clock values are not rendered.

This is supplied-record timing consistency, not clock authenticity, training-data
provenance or permission to score. Overall artifact/embedding observation time and
encoder identity remain unverified. Existing historical mtime-based audits and
strict scoring inputs are unchanged. The availability bound is retained for a
future reviewed prospective adapter, rather than being renamed a training date.

### Retained attribution coverage diagnosis (private, offline)

`coverage.py` diagnoses missing historical attribution without changing the
10-second rule in `witness_attribution.py`. Supply the same explicit snapshot
bundle (`input_kind`, `sources`, `historical_attribution` including its
`compute_ledger`, exact surface/caller mapping and explicit naive timezone).
For first-retained dates across **all callers**, include the full admitted copied
ledger, not just a router-filtered subset. No source discovery, new capture,
model calls or writes to the copied input occur. Input is bounded to 128 MiB,
250,000 ledger records and 10,000 adapted source rows; larger inputs fail rather
than silently sampling. These limits are not a statement of historical coverage.

Using absolute paths in an existing private scratch workspace outside the repo:

```sh
SPARK_WORKSPACE="$PRIVATE_SCRATCH" python3 experiments/judges-witness/coverage.py \
  --scratch "$PRIVATE_SCRATCH" --input "$PRIVATE_SCRATCH/bundle.json" \
  --output "$PRIVATE_SCRATCH/coverage-new" --cutoff "$CENSUS_CUTOFF"
```

Use the original census's exclusive, offset-bearing cutoff, not today's date.
The output directory must be new. `private-coverage.json` gives first/last retained
UTC timestamps per caller, unknown-clock counts, largest observed inter-call gap,
foreground counts, and per-source surface/mapping/join-state counts. These are
**private activity metadata**, not for Git. A long observed gap may simply be
inactivity; the first retained date is not proof of when logging was installed.
Background calls are inventoried, but cannot become foreground reply evidence.
Missing/empty/invalid surfaces remain distinct; no default is invented.

`aggregate.json` contains the unchanged original attribution report, counts of
unmatched replies before/within/after the mapped retained foreground span, and
fixed 10/30/60/120-second diagnostic windows. Only originally `no_matching_call`
rows enter the sensitivity counts. A sole candidate must have usable metadata;
all nearby replies compete for it, including already matched, exact-ID and
ambiguous rows. Same-ID/same-final copies may share; unknown IDs or changed
versions cannot. A wider-window opportunity is **not recovered attribution**.
Exact-ID failures, unmapped surfaces and bad clocks are never repaired by widening.
Neither model labels nor per-reply IDs/text enter these outputs. Only the private
coverage file contains caller/surface names and clock ranges. All files are 0600
inside a 0700 directory; `private-run.json` binds the input, implementation and
output hashes. The aggregate file alone can be considered for public review;
inspect it before publication, and never publish the private manifest or coverage.

Source findings motivating this probe, not measured explanations of a historical
snapshot: `route_reply()` returns its `route` label, which the avatar handler
stores in `served_by`; this is not necessarily the provider's exact model name.
Two toggle success paths in `route_reply_result()` return before `_ledger()`.
The ledger timestamp is completion recording, while the avatar history timestamp
is written later after guards and reply processing. A time-window miss is therefore
not proof that the model was unrecorded. The merge retains surface only when its
source supplied one; the interaction writer defaults absent environment surface
to an empty string. None of these facts identifies the affected historical rows
without the private diagnostic. No route, feed, logging policy or admission rule
is modified by this probe.

### Explicit configured-only completion metadata

Two successful toggle branches now write the same foreground completion ledger
used by other router paths. Their current draft contract exposes text but no
verified served identity, so these new records carry
`model_identity_evidence: "configured"`. The model field is the configured name;
no provider request ID or response-observed identity is fabricated. Existing
provider calls, return values, fallback order and receipt identity are unchanged.
Ledger failures are swallowed by the existing recorder and cannot trigger a retry.

The offline attribution reader distinguishes this explicit limitation from an old
record that lacks an identity-evidence field. Explicit values other than
`response_metadata` or `runtime_receipt` produce
`call_model_identity_unobserved`; the call is not promoted to ledger-attributed
served identity. Existing row labels remain recorded labels. A nearer call with
this limitation cannot be skipped in favor of a farther call. Wider-window
coverage similarly reports `sole_call_identity_unobserved`, not a recovery
opportunity. These explicit evidence labels are still recorded claims, not source
authentication. Historical unmarked ledger rows retain their previously reviewed
ledger-attributed tier; this change does not fabricate markers on older data.

### Draft response identity propagation

The two draft parsers now offer an optional `identity_observer` keyword while
keeping their original `(text, reasoning)` return contract and request payloads.
The callback receives only bounded provider response model/ID fields and a digest
of the exact stripped text returned. It is per invocation, not a global last-result
slot. Empty output emits no selected identity; observer failures cannot change the
draft. No body, prompt, reasoning or credentials enter the callback packet.

For a successful routed draft, the observation must match the returned text digest
before it can supplement `observed_model`, `identity_evidence` and `request_id`.
Only supplied valid response fields count. Configured names are not substituted.
The completion ledger uses the observed name and response ID when present; otherwise
it retains the explicit configured-only limit. The public route label and existing
result `model` field stay unchanged; identity evidence is separate. Provider metadata
is an observed response claim, not independent proof of underlying model weights.

Optional `provider_request_id` is retained in the private capture's
`observed_attempts`. It is distinct from the instrument's internal request ID and
input binding. It is not added to normalized strict receipt requirements and does
not upgrade unknown context ancestry, attempt completeness or delivery. Failed
requests and earlier attempts discarded inside a draft remain unobserved by this
new callback; complete request accounting is not claimed. Historical rows receive
no backfill. Direct callers that do not request observation keep the original tuple
behavior without a new capture side effect.


### Repeated audit vectors remain observable

The optional self-audit wrapper deduplicates by exact input digest **and observed
vector digest**, not input text alone. A later different vector for the same input
is retained so the existing offline content join can report
`conflicting_vector_observations`. Identical repeats remain one observation;
changed results within a single batch also remain distinct. No extra encoding is
performed, and callers receive the original result object unchanged.

Each wrapper retains at most 8,192 successfully published observation keys in
memory. Further new observations are skipped and increment the process-local
`audit_observation_limit` counter; ordinary sink capacity/retention limits still
apply first to publication. A failed publication does not mark an observation as
retained, so a subsequent existing encode can retry it. Counters and keys do not
survive process exit. These are incomplete observations, not a guarantee that every
conflict was captured. Invalid vectors remain unretained and increment the existing
retention-failure counter even when their input was seen previously.

Vector differences do not establish why an encoder changed: parameters, options,
numerical variation and execution context are not distinguished by this receipt.
Encoder identity stays unverified and no score, admission rule or live audit verdict
changes. This repair cannot recover differing vectors already discarded by older
input-only deduplication.


### Vector representation is separate from encoder identity

Prospective artifact observations explicitly label their stored representation:
`encoder_return_v1` for the audit wrapper's returned vectors, and
`readout_units_v1` for the forecast bank after the existing readout `units` function
(float conversion, norm division with a 1e-12 floor). The label records the existing
producer operation; it does not verify weights, tokenizer, encode defaults,
training provenance or a common embedding space. No vector is newly normalized or
recomputed for this observation.

The offline content join validates each explicit label against its producer schema.
For the same checkpoint, final reply and input, distinct representations are
`mixed_vector_representations`, held out of the content-bound count. This is not an
encoder-conflict verdict, even when the stored numbers differ only by scale, and
identical numbers do not establish matching representation contracts. Differing
vectors within any one explicitly known representation still make the entire group
`conflicting_vector_observations`; a mixed packet cannot hide that conflict.

Older packets have no representation label. Their details retain null rather than
inferring a label from their schema or path. Multiple differing old observations
become `vector_representation_unobserved`; a known/unknown mixture is mixed. A
single consistent old observation can still establish the same text-content binding
as before, with unknown representation and no scoring permission. The report emits
only fixed labels and aggregate counts for these distinctions. Strict eligibility,
forecast scoring and live audit results are unchanged.


### Optional separate 30-second historical attribution

To evaluate the reviewer's requested wider historical tier on an existing private
snapshot, set `historical_attribution.window30_enabled` to the JSON boolean `true`.
Keep the original explicit surface map, naive timezone, exclusive cutoff and
`window_seconds` (at most 10) unchanged, then run the existing scratch replay into
a **new** output directory. There are no default changes and no extra input reads.

The original `historical_attribution.tiers`, joins and label-agreement counts stay
unchanged. Its optional `window30` section gives an **alternative partition of the
same assistant source copies**, with the additional `ledger_attributed_window30`
tier. Never sum the two partitions or treat duplicate source copies as independent
training turns. Private per-copy details keep the original fields plus a separate
`window30` object containing the selected ledger identity and state.

Only original `no_matching_call` copies without an observed identity can enter the
extension. There must be exactly one foreground call in the mapped caller scope
within inclusive +/-30 seconds and before the exclusive cutoff. This is not the
nearest of multiple calls. Missing/invalid call metadata, explicitly configured-only
identity and unordered caller clocks cannot be promoted. Exact-ID failures,
unmapped surfaces and bad reply clocks are not repaired by widening.

All other clocked replies compete for nearby calls, including already matched,
observed, ambiguous and failed-exact-ID replies. An existing exact-ID match outside
the window also reserves its call. Reuse is allowed only for copies with the same
explicit turn ID and final-text hash; different or unidentified replies hold the
candidate. Identical ledger records are deduplicated before this check.

The aggregate report supplies added-copy exact label agreement, disagreement,
conflicting-label and missing-label counts. The agreement denominator excludes
missing/conflicting labels and is explicitly undefined when empty. Route aliases
are not guessed to be model families. These descriptive checks are sensitivity
results, not proof of accuracy or a historical training authorization. The original
strict census, behaviour receipt, forecasts, baselines and scoring do not change.
The real-data tier counts must be measured by the reviewer on the admitted copy;
previous wider-window opportunity counts are not silently relabelled as results.


### Prospective selected-completion joins

Router ledger writes now add a random `generation_completion_id` for each nonempty
completion plus `generation_response_sha256`. The existing ledger `request_id`
remains the HTTP trace ID; it is not a provider request ID, and multiple attempts
can share it. The result carries a content-free `ledger_join` with the completion
ID, trace ID, caller and raw-text hash. These identify an attempted record, not a
confirmed durable write: existing accounting failure handling remains unchanged.

The avatar handler (including its room surface) keeps a separate invocation-local
observer for each first/repeat/replacement router call. Only the accepted call's
metadata is attached to its saved assistant history row as `generation_join`, with
a hash of that exact stored text. Rejected repeats clear selection; failed reroutes
preserve whatever reply the existing handler keeps. This observation works when
private shadow capture is off, composes with capture when on, and degrades to no
join for older/missing helpers. No model calls, tuple contracts, reply text, route
choices, effect parsing or feeds change. Canonical copying preserves the field;
the merged-chat carry list now preserves it as well.

Offline attribution checks the exact completion ID before provider-ID/time matching.
It verifies the raw hash, HTTP trace, caller scope and stored-text hash, then applies
the existing call metadata, cutoff, identity and reuse rules. A supplied provider ID
must agree too. Missing, duplicate, malformed or contradictory completion markers
stay unresolved: neither tight-window nor optional 30-second fallback repairs them.
Unmarked historical rows retain their prior attribution behavior.

This correlates a recorded generation completion with a **saved history version**.
History is written before the final response guard; a join does not prove client
delivery, the final transport version, complete internal attempts or clean ancestry.
It never establishes a model identity that the completion metadata lacks. The
interaction-ledger subprocess and other non-avatar generation paths are not given
invented joins; those remaining producers require separate source tracing.


### Producer/source coverage

`coverage.py` now adds a fixed-label `source_coverage` aggregate, distinguishing
adapter copies from projection sources and absent/empty/invalid declared surfaces.
Same-turn surface evidence requires agreeing explicit IDs, identical stored text
and usable pre-cutoff clocks. It does not repair rows or change attribution.
Private caller summaries also distinguish nonempty model/provider values from
mere key presence and count stages. See `docs/judges-source-coverage.md` for the
source trace, limitations and command for the existing admitted private bundle.


### Audit encoding call and loaded-parameter observations

With private capture enabled, the existing self-audit encoder wrapper now binds
retained raw vectors to an `encoding_observation`: random invocation identifier,
input digest, raw-vector digest, bounded JSON settings digest (or null), and CPU
parameter/buffer snapshots immediately before/after the existing encode call.
No extra encode or model load occurs. The return object and arguments are unchanged.
The shared audit's other head is not wrapped by this observer.

Overhead is bounded to **one before/after snapshot pair per wrapper**, consumed by
the first call containing a retained self-text input. Each snapshot admits at most
8,192 state entries and one GiB of already loaded CPU tensor/array bytes. It hashes
names, dtype, shape and logical contiguous bytes; only the combined digest, tensor
count and byte count are retained. CPU tensors support a byte view without a device
transfer. Non-CPU/sparse/unsupported state, oversized state or observation failures
produce unavailable snapshots. Later calls do not inherit the first call's identity;
they remain unavailable and perform no further parameter reads. No weights, tokens,
parameter names, settings values or source text are added to the private packet.

The first successful matching call can therefore supply `observed_equal` or
`observed_changed`. These mean matching/different loaded-state snapshots around
that call; they do not prove immutability throughout the interval. `unavailable`
is not a match. Output deduplication includes the snapshot/settings evidence, so
an observed receipt and an unavailable receipt are not silently collapsed even
when the same vector was returned. Existing observation count caps still apply.

The offline join validates each supplied receipt's schema, parameter comparison,
input digest and exact raw-vector digest. Contradictory attached evidence is an
input error; older packets with no receipt remain explicitly `missing`. Forecast
feature packets remain `not_instrumented_forecast`. Aggregate review output exposes
only these fixed labels and packet counts; hashes and invocation IDs remain private.
No existing content-binding verdict, witness admission or score is upgraded.

Full `encoder_identity` remains unverified. Parameter bytes omit tokenizer,
pooling/execution configuration, loaded code, training lineage and the forecast's
encoding call. This increment does not close those gaps or make representations
interchangeable. It also does not reinterpret the legacy persisted embedding cache
as a current-runtime observation. The forecast-side readout and live feeds are
unchanged. Host review must check the installed runtime's state types, packet
sizes and audit CPU/memory overhead; synthetic array tests are not that acceptance.


### Forecast feature encoding links

When an on-message self-forecast capture scope is active, its replacement readout
observes the existing feature-batch encoder call with `FeatureEncoder`. The same
raw result object is returned to `Embeddings.fill`; the existing `units` transform
still produces the bank. No extra encoding or model load occurs. The context-copy
control remains a direct call through the original encoder, and other head modes
and the legacy persisted cache are unchanged.

The observer holds at most 256 distinct input records and 65,536 raw vector values,
with at most one before/after CPU parameter snapshot pair for its first call. This
is up to two GiB of bounded parameter hashing per captured forecast, not per vector;
production timing/memory acceptance remains with host review. Only the selected
recent-own references are serialized. Their `encoding_link` contains the raw vector,
its input/output-bound call receipt and the explicit `readout_units_v1` transform.
The private packet already contains the normalized vector; the additional raw
observation allows the offline reader to verify the actual transform rather than
infer it from a model name. No new message text, parameter bytes or settings values
are serialized. Existing private sink packet caps can refuse oversized observations.

Validation requires the exact input hash, raw-vector hash, forecast-call receipt
schema and exact float64 normalized output, including the existing 1e-12 norm
floor. A supplied link with no call receipt or a mismatched transform is rejected.
Missing links remain `not_instrumented_forecast`. The packet-level parameter summary
uses `mixed_forecast_observations` when its references have different observation
states; it never borrows an observed state from one reference for another. Counts
are diagnostic only, with no score/admission or automatic raw/normalized conversion.

This closes the feature-call/normalization observation gap for those captured
references, not complete encoder identity. Tokenizer/code/configuration identity,
checkpoint fitting lineage, observation clocks and target selection remain separate
requirements. The context-copy control has no new encoder receipt in this slice.
No historical vector or legacy cache is attributed to a present runtime by guessing.


### Cross-call encoding consistency

The offline artifact summary now compares validated call observations within each
exact checkpoint, admitted turn, final-reply digest and encoder-input digest group.
Groups are formed after source/final/input binding and before vector-representation
conflict classification. Public output contains only group/reference counts and
fixed categories on three independent axes: parameter snapshots, encode settings
digests and raw-vector digests. Counts on each axis sum to the same group total.

Observed differences remain visible even with missing peers. Matching requires
every reference observed and at least two distinct invocation markers; duplicated
packets/call markers cannot manufacture repeatability. Single-call and incomplete
categories remain explicit. Validated forecast raw-to-normalized links permit raw
output comparisons with audit receipts; legacy normalized vectors are never
converted or relabelled. Parameter changes during a call take precedence over
between-call differences. These categories describe supplied observations, not
causes: different settings, batch context or execution state may affect outputs.

This adds no runtime work and changes no admission, vector-conflict classification,
forecast scoring or feeds. Matching snapshots are still partial evidence, not full
encoder identity, tokenizer/execution-code identity, checkpoint training lineage,
observation-time authentication or forecast-target association. Private copied-data
measurements and the full isolated host suite remain reviewer work.


### Innovation input boundary

Direct innovation() callers must supply a list of admitted records with unique,
nonempty string turn IDs. Repeated IDs are rejected, including identical copies;
use the census to adjudicate source copies first. The percentile history minimum
is a positive integer (booleans and floating-point values are not counts). Invalid
container/identity/minimum contracts raise ValueError before scoring. This does not
replace census eligibility checks or change scores for valid census outputs.


### Historical summary validation

The renderer requires the historical section to declare per-source-copy scope and
no admission/training effect. Tier totals plus cutoff exclusions must equal source
copies; label-agreement and join-state totals each equal the included-copy count.
Unknown tiers, agreement categories or exclusion categories are rejected, and the
missing cutoff-clock count cannot exceed supplied copies. A retained finalized
receipt can establish cutoff membership even without a usable legacy timestamp;
this is correctly counted as a known cutoff clock. It does not create a timestamp
for ledger matching or change historical eligibility.


### Synthetic CPU cost benchmark

`benchmark_encoder.py` times the actual FeatureEncoder wrapper around a synthetic
13-by-768 output and already allocated CPU arrays. It makes no real model calls,
loads no checkpoint, reads no input store and publishes no capture packets. Receipt
helpers and parameter-array allocation are outside the timer. Each iteration uses
a fresh wrapper: bare stub, first observed call (two parameter scans), a same-input
repeat without parameter snapshots, then a fresh-input repeat without parameter
snapshots. The last phase exercises new receipt retention; the same-input phase
keeps the first bank entry and cannot prove a new receipt. Both first/fresh-input
calls must retain equal before/after runtime and Python-entrypoint observations.
First-call parameter bytes/counts and repeat unavailability are checked separately.
A missing observation, changed synthetic state, stale invocation or unexpected
component count fails the run before any report is written.

Version 2 reports include wall/process-CPU medians and maxima, call counts, array
byte counts, code hashes and fixed observation-coverage counts. No vectors,
parameter values, messages, invocation IDs or settings are written. The default
minimal profile observes the root and its code. `--runtime-profile configured`
adds four synthetic modules across two child levels, four stored module settings,
one config and one tokenizer-settings object. This is a bounded fixture, not a
measurement or reconstruction of the real encoder or tokenizer.

Run from the reviewed checkout with an existing CPU Python environment containing
numpy. No install is needed:

```sh
BENCH_SCRATCH="$(python3 -c 'from pathlib import Path; import tempfile; print(Path(tempfile.mkdtemp(prefix="judges-cost-")).resolve())')"
SPARK_WORKSPACE="$BENCH_SCRATCH" PYTHONDONTWRITEBYTECODE=1 python3 experiments/judges-witness/benchmark_encoder.py --scratch "$BENCH_SCRATCH" --output "$BENCH_SCRATCH/contiguous" --mib 64 --tensors 8 --iterations 3 --runtime-profile configured
SPARK_WORKSPACE="$BENCH_SCRATCH" PYTHONDONTWRITEBYTECODE=1 python3 experiments/judges-witness/benchmark_encoder.py --scratch "$BENCH_SCRATCH" --output "$BENCH_SCRATCH/strided" --mib 64 --tensors 8 --iterations 3 --layout strided --runtime-profile configured
```

The CLI refuses live/repository/symlinked roots, existing outputs and paths outside
explicit 0700 scratch. The replay audit hook denies other writes, rename, process
launch and network. Results are 0600 in new 0700 directories. Limits are 1–512 MiB
logical arrays, 1/8/64/128 tensors and 1–10 iterations. Strided arrays allocate twice
the logical parameter bytes and hashing makes temporary contiguous copies; the
reported allocation is not peak RSS. Default is 64 MiB, eight tensors, three runs.

Earlier version 1 synthetic measurement (three repetitions, 64 MiB logical state, eight tensors):
first observed-call wall median/max 42.219/43.999 ms contiguous and 49.465/54.537 ms
strided; repeated-call medians 1.886/1.918 ms respectively. These are measurement
observations, not performance tests with thresholds. They do not establish real
encoder cost, tensor-runtime compatibility, end-to-end response latency or Aegis
acceptance. The benchmark uses numpy buffers, not the loaded tensor library; real
CPU-runtime overhead and packet/sink behavior remain separate reviewer checks.


### Historical match-method coverage

The historical aggregate now includes `matched_methods`, a fixed three-key count
of source copies matched by `generation_completion_id`, `provider_request_id`, or
`nearest_time`. It is computed after conflicting-ledger and call-reuse checks and
excludes copies outside the cutoff. Its sum equals `join_states.matched`.

This is a second view of the same copies, not another attribution tier or a count
of unique requests. An `observed` copy may also match a ledger row. Duplicate
source copies count individually; duplicate identical ledger records do not create
extra matches. Optional window30 additions remain in their separate partition.
The public formatter prints fixed labels and numbers only, validates the exact
keys/counts/total, and marks legacy reports without this field as unavailable.
Exact keys establish correlation, not delivery, clean ancestry or training
eligibility. Matching, strict admission and all runtime producers are unchanged.


### Cost of retained encoder calls

Optional audit/forecast call observations now include `timing` with schema
`encoder-call-timing-v1`: parameter-before, existing encode, and parameter-after
elapsed seconds, read from the monotonic performance clock. Each is a finite
nonnegative duration up to one day, or null when unmeasured/unavailable. Unspent
snapshot stages stay null. Clock errors/reversals/nonfinite readings cannot change
encoding or cause retries. Backend exceptions propagate unchanged; a failed call
has no successful-output receipt. Capture-off paths remain unchanged. No model
loads, additional encodes, GPU transfers or new parameter scans are introduced.

The before/after scan budget remains one pair per wrapper. Times are monotonic
wall time, not process CPU, GPU completion, whole-wrapper overhead or job latency.
They omit serialization, private publication and caller work. Successful snapshot
byte counts describe tensors actually hashed, not full resident model size. An
unsupported/over-limit snapshot may still have measured attempted-scan time while
its byte count remains unavailable. Retention keeps the existing selection and
value-deduplication rules, so these observations are not all runtime calls.

The offline artifact summary adds `encoder_call_cost` over validated supplied
packets, including inputs that do not bind an admitted reply. Packet duplicates
are removed; multiple source references or batch outputs do not multiply a call's
cost. The opaque invocation marker joins copies only within this supplied set.
Different timing, settings or parameter-snapshot metadata under one marker makes that call
conflicting and excludes all its copies from duration/size statistics. Legacy
copies without timing remain valid; mixing missing and present timing for the same
marker is conservatively conflicting. Missing call identity is counted separately.

The report prints fixed stage labels, measured/unavailable call counts, total and
maximum seconds, and observed snapshot count/total/max bytes. Totals are repeated
scan volume, not distinct model bytes. It emits no invocation IDs, parameter
hashes, text, vectors or source labels. Strict validation checks count partitions,
finite bounds and size/duration conservation before rendering. A legacy report
without this section explicitly says cost coverage is unavailable. These numbers
do not establish encoder identity, delivery, fitting lineage, target association
or scoring/training eligibility.

Fourteen isolated synthetic tests cover exact staged clock values, unmeasured
stages, clock failures, backend exceptions, source-observer failure, unchanged
calls/results, batch deduplication, conflicting copies, missing/legacy fields,
forecast links, aggregate validation and public-output privacy. Existing encoder,
audit, join, report and synthetic benchmark suites also pass. No real encoder was
loaded for this change. Real host cost remains unmeasured until the operator enables
capture and ordinary background work retains these observations; no user-generated
test conversation or paid call is needed to collect them.


### Historical fixture metadata diagnostic

`coverage.py` now emits `historical_fixture_coverage` alongside its existing
aggregate fields. The fixed public source profile compares the exact historical
chat-result fixture's caller, class, stage, provider/model tuple and usage object.
It partitions unique supplied ledger rows into fixed counts, retaining cutoff and
unknown-clock exclusions. It does not identify test executions, remap sources,
backfill models or alter attribution/training admission. Existing baseline and
window diagnostics are unchanged. See [the source evidence and comparison contract](../../docs/judges-source-coverage.md#reproducible-metadata-comparison).

Use the existing copied bundle and coverage command with a fresh private output
directory. Report only the fixed aggregate section; keep private caller records,
IDs and timestamps private. A matching pattern requires independent execution
provenance before it can establish origin. The new contract has 55 passing
isolated coverage/attribution checks; no live source was read or model called.


### Checkpoint observation consistency

The offline artifact reader now validates `self-checkpoint-observation-v1`
manifests before using their content references. It requires the producer's
bounded byte count, hash fields, supported mode, bounded reported strings and
explicitly unobserved training/encoder identity. Invented verified identities,
weights-retained flags, malformed current-version fields and unsupported schemas
are rejected; they cannot disappear behind a good copy. Older observations without
availability are accepted. Schemaless legacy manifests with a valid checkpoint
hash remain legacy evidence and never acquire missing identity fields.

The `checkpoint_consistency` aggregate groups one manifest per unique supplied
artifact packet by checkpoint hash. Repeated source references do not multiply it.
It compares the metadata hash, byte count, mode, source and reported fields, while
validating read-availability clocks separately. Different read times for the same
bytes are expected and do not create metadata conflicts. Groups are classified
as consistent observed fields, conflicting observations, incomplete observations,
or legacy only. Observed conflicts remain visible even with missing legacy peers.
Consistent fields may come from a single observation; they do not mean independent
confirmation. These counts describe supplied copies, not unique physical loads.

Only fixed labels/counts are published: manifest copies, checkpoint groups,
validated observation shapes, legacy shapes and the four group states. Hashes,
reported labels/dates, paths and vectors are absent. The formatter checks count
conservation and possible minimum group sizes. Older reports lacking this section
explicitly say consistency coverage is unavailable.

This is an internal consistency check, not authentication of the underlying bytes.
It does not reconstruct weights, certify a training completion date, establish
encoder/tokenizer/runtime identity, choose a forecast target or admit a record for
scoring. Valid conflicting manifests remain visible alongside the separate content
joins; content equality is still a separate question. Existing runtime capture,
forecasts and training/evaluation rules are unchanged. Full fitting-lineage and
forecast-target association remain unresolved.

111 affected local isolated checks pass: consistency 13, artifact joins 30,
checkpoint availability 12, report 22, retained-call cost 14, self artifacts 20.
All inputs are synthetic; no real checkpoint, private snapshot, model or live
store was accessed. Host integration and private retained-data checks remain with
review. No capture is enabled by this change.


### Prospective pending-file handoff receipts

The optional self-forecast capture observes the existing launcher after its runner
returns, and observes the decoded pending record consumed by the background job.
It never reopens that pending file. `self-forecast-launch-v1` records a digest of
the pending locator and canonical decoded value, a message digest, arrival time,
and optional surface/turn marker digests. After the existing forecast-log close,
`self-forecast-handoff-v1` binds that observation to the exact saved forecast-row
digest. Raw text, paths and turn IDs are absent from these new private sidecars.
These hashes still belong in the private snapshot, not public documentation.

No field is added to the pending record or forecast log. Existing process launch,
reply flow, model selection and forecast/feed content remain unchanged. Capture
off produces no sidecars. Observer failure is swallowed; no retry, extra model
load or encoding is introduced. Capture on adds one bounded launcher publication
and one background sidecar. Launcher cost uses the configured queue/spool path and
needs isolated host measurement; earlier latency numbers do not cover it.

Supply both sidecar kinds unchanged in a new explicit `self_forecast_handoffs`
list in the existing replay bundle, alongside the exact original `forecasts`.
The normal replay command and public formatter then report fixed counts for
launches/jobs and their missing peers, plus per-unique-forecast states. Duplicate
copies do not multiply witnesses. Pending content/locator disagreements, multiple
job observations, absent launches, absent origin markers and row-field mismatches
stay separate. Every receipt is validated before cutoff filtering. Cutoff is
exclusive on the supplied forecast time; absent peers do not establish failure or
loss. The new offline module is included in the private run's code hashes.

A `joined` state only establishes supplied-record consistency between these
boundaries. It does not authenticate a source, prove the subprocess executed the
claimed code, prove that her input was fully represented, or associate the
forecast with a delivered reply. No receipt fills in a missing chat turn ID, and
no historical marker is invented. Scoring and strict training admission are
unchanged. Tokenizer/runtime/fitting lineage, caller identity, reply delivery and
complete influence ancestry remain separate work.

307 affected isolated synthetic checks pass (handoffs 19, forecast inputs 15,
source clocks 12, census/innovation 109, existing on-message head 32, public report
22, capture hooks 21, sink 26, deferred queue 26 and durable spool 25). The legacy synthetic head suite emits numerical runtime
warnings while all 32 checks pass; no live encoder or checkpoint was loaded.


### Main-chat prospective forecast key

The existing coordinator's event-key calculation now has one shared pure helper.
For `chat/full` only, the early self-forecast hook can reserve that key from the
current validated HTTP request marker, before the bilateral wrapper opens the
actual turn later. The coordinator uses exactly the same pre-existing mapping;
its no-event random fallback, barrier/capsule ordering and duplicate behavior are
unchanged. The early hook does not open a turn, fetch a capsule or move the
forecast's arrival time. Missing/malformed request markers stay empty. Explicit
turn IDs, other surfaces and test-mode behavior are preserved.

This is prospective metadata active even when optional witness capture is off:
ordinary main-chat pending/forecast rows can now carry the event-derived turn key.
It does not alter history rows or merge/deduplication selection, post-turn feeds,
model routing, reply text, forecast vectors or the existing evaluator. It cannot
backfill historical markers or establish that a future target reply was produced
or delivered. A reserved key is not authenticated evidence or training admission.
Existing exact target/source/lineage/clock requirements still apply.

105 affected isolated synthetic checks pass: new key propagation 11, coordinator
33, handoff capture 19, existing on-message head 32 and completion joins 10. The
new tests exercise concurrent request contexts, shared coordinator key parity,
missing/malformed input, exception behavior and the actual launcher, pending file
and forecast log (including the full 66-character ID). No live inputs, models or
services are used. Full integrated host validation remains with review.


### Handoff cardinality

The offline handoff diagnostic also checks the reverse relation: one pending
resource cannot certify multiple distinct saved forecast rows. All valid supplied
job receipts participate, including references to absent rows and rows outside
the forecast cutoff. A competing row cannot disappear through filtering and make
the remaining one look unambiguous. Such records report `conflicting_receipts`.
Exact copies remain duplicates; separate pending resources sharing a request/turn
marker remain separate observations. This does not alter innovation's existing
earliest-forecast policy or any runtime producer.

Four new synthetic regressions cover conflicting vectors, later/outside-cutoff
peers, missing row peers, order/duplicate invariance and distinct-resource controls.
The first three reproduced the prior false joined results before the fix. All
165 affected isolated checks pass: handoffs 23, chat keys 11, report 22 and
census/innovation 109. No private data or new capture is required for the fix.


## 9 November — observe stored encoder runtime settings

`codex/judges-loaded-runtime` descends from 3d022fb8. Optional self artifact
capture now records before/after fingerprints around each existing encode call
for bounded fields already stored on the encoder and two child-module levels:
training/truncation/prompt settings, primitive stored model configuration,
selected stored tokenizer settings and already-loaded package versions. Child
order is retained. No config/tokenizer methods, vocabulary reads, imports for
version discovery, file loads, device transfers or extra encoding calls are used.
Receipts retain hashes and counts, never the underlying setting values.

These are partial observations, not complete encoder identity. Tokenizer backend
bytes/vocabulary, dynamic properties, deeper module state, executable code,
hardware and fitting lineage remain unobserved. Unsupported components are marked
inside the fingerprint; bounds or observer failures leave evidence unavailable.
Equality means only equality of observed stored fields. Snapshots are not atomic
attestations and do not prove immutability between boundaries. `encoder_identity`
remains unverified; scoring and training admission are unchanged.

Capture-off behavior remains unchanged. With capture on, this adds bounded work
around every wrapped background encode (64 modules, two child levels, 4096 plain
value visits, 65536 string characters, 131072 serialized bytes per snapshot).
It does not change outputs, exception propagation, call arguments or the existing
one-pair parameter sampling limit. Observation cost on the real encoder remains
unmeasured, and existing parameter/encode stage timings exclude this new runtime
observation overhead. The full host cost check remains open.

Legacy receipts without the optional `runtime` field remain valid and unknown on
this axis. Audit retention includes runtime changes even when outputs repeat;
conflicting runtime copies of one invocation are excluded from call-cost totals.
The existing public `encoding_consistency.settings` axis still describes explicit
call arguments only; it does not summarize the new runtime snapshots. Keep the
artifact producer and reader versions together when integrating.

221 isolated synthetic checks pass: runtime 16, parameters 19, costs 14,
self artifacts 20, joins 30, review report 22, encoder benchmark 6, checkpoint
consistency 13, forecast inputs 15, handoffs 23, entry owners 11 and store guard 32.
Tests cover changed settings despite identical parameters/vectors, module order,
loaded versions, unsupported/oversized/cyclic values, forbidden dynamic reads,
legacy/malformed receipts, exceptions, capture off and exact call/result parity.
Generated reports refreshed. No private records, real encoder, model calls,
live writes, enabling, merge or deployment. Full host integration remains open.


## 9 November — local self-fitting completion receipts

`codex/judges-fit-completion` descends from 4353b824. The anchored readout's two
self modes now optionally observe their existing fitting boundaries: ordered
rows, numeric feature/target arrays and index assignments are fingerprinted per
train/validation/calibration/test block before fitting; completed parameters and
metadata are fingerprinted before the unchanged checkpoint save. After save
returns, a bounded readback must match both fingerprints before an immutable
private `self-fit-completion-v1` receipt is published. The receipt includes exact
checkpoint-byte identity, byte count and wall-clock boundary observations. It
contains no row text, raw turn IDs, paths, vectors, weights or raw settings. The existing
private sink whitelist/retention rules cover the new packet type.

Capture off performs no observation imports/reads/writes. With capture enabled,
this adds bounded background hashing and checkpoint readback: at most 4096 rows,
8 MiB serialized row text, 16 feature arrays plus targets, 64 MiB total numeric
input bytes, and a 64 MiB compressed/decompressed checkpoint bound. Runtime cost
on real records is unmeasured. No encoder invocation, training invocation or
checkpoint schema is added; selection, fitting, calibration, reports, save format
and existing consumers remain unchanged. The other head bypasses these hooks.
No existing training run was started; tests use synthetic arrays and stub encoders.

This is a local observation, not source authentication, proof of cache/encoder
origin, a complete dependency graph, atomic checkpoint publication, disk durability
or evidence about an old checkpoint. Exact output readback can be observed even
if a separate writer later replaces the file. Clock reversal makes the receipt
unavailable. Observer failures are passive and save failures still propagate.
Historical training dates remain unknown. The separate offline completion-receipt
reader/join remains to be added; current scoring/admission does not consume or
promote these receipts. Full source/encoder lineage and host integration stay open.

124 isolated checks pass: fitting receipts 14, existing readout acceptance 5,
self artifacts 20, sink 26, runtime 16, entry owners 11 and store guard 32. Actual
fitter tests confirm identical reports/parameters/encoder call counts with capture
off/on, each observer failure is passive, and a failed save cannot publish a
completion. Other tests cover exact metadata/shape/dtype/value binding, separate
test-block changes, partition conflicts, private output, object arrays, symlinks,
size bounds, clocks, dedicated-sink permissions and hot disable. Existing synthetic
numeric code emits matrix-operation warnings; all asserted checks pass. Generated
reports refreshed. No private data, real model, live write, enabling, merge or deploy.


## 9 November — offline fitting-receipt reader

`codex/judges-fit-receipt-reader` descends from 48b29f6a. Replay accepts an optional
`self_fit_completions` list containing retained `self-fit-completion-v1` packets.
It compares these with the existing explicitly supplied `self_artifact_packets`
and adds `fit_completion_observations` to the aggregate. No directory discovery,
checkpoint loading, encoder calls, training or receipt synthesis occurs. The new
reader is included in the private run's scoring-code hash manifest. The existing
review renderer projects only fixed counters and states after validation.

Every supplied receipt and artifact is validated before cutoff filtering. Exact
receipt copies and exact checkpoint-manifest copies collapse, while supplied-copy
counts remain visible. States count unique checkpoint-manifest observations, not
training runs, source replies or unique checkpoints: two reads of the same bytes
at different clocks are separate observations. Orphan receipts are counted
separately and do not prove a failed fit or absent forecast.

Matching requires exact checkpoint digest, metadata digest, mode and byte count.
Legacy manifests, missing receipts, unknown read clocks, mismatch and cutoff states
stay separate. Multiple distinct fitting receipts for one checkpoint are held;
the reader does not select an earlier or preferred one. This includes differing
clock observations that could represent legitimate repeated fits; it is ambiguity,
not a claim of fabrication. Conflicting manifest peers also hold the join. All
supplied peers participate, including outside-cutoff peers, so filtering cannot
hide an alternative claim. These conservative comparisons have no scoring effect.

A single matching completion is classified as observed before the checkpoint read
(start boundary), overlapping the read interval, or observed after parsing. Only
parameter-loaded read clocks qualify for this temporal comparison. Neither a match
nor its timing authenticates sources, establishes encoder/cache ancestry, proves
disk durability, rewrites a historical fitting date or grants training eligibility.
Current census, behaviour, innovation and checkpoint metadata remain unchanged.
Full lineage, real-host cost, delivery evidence and host integration remain open.

178 isolated checks pass: fitting reader 17, review report 22, artifact joins 30
and census/innovation 109. Tests cover exact binding, clock intervals, missing and
legacy evidence, duplicate/order invariance, receipt/manifest conflicts including
future peers, malformed evidence, orphan counts, strict public projection, actual
producer compatibility and the real scratch replay CLI. The CLI verifies private
file permissions/code binding and exact unchanged nonempty census/innovation.
An initial test used the wrong existing run-manifest filename; corrected to
`private-run.json`. Generated reports refreshed. No runtime producer changes,
private records, model calls, live writes, enabling, merge or deployment.


## 9 November — compare retained partial runtime settings

`codex/judges-runtime-comparison` descends from 5283d12b. Existing artifact replay
now adds `runtime_consistency` beside the unchanged call-argument/parameter/vector
axes. It compares the optional stored-runtime snapshots already retained in
forecast and audit encoding receipts, within the existing exact content/checkpoint
groups. The review renderer validates and projects fixed counts only. No new
capture, model load, encoder call or runtime producer behavior is added.

States distinguish changed during a call, different partial snapshots across
calls, incomplete evidence, a single call and matching partial snapshots. Observed
differences survive missing peers. Matching requires every reference to have an
observed equal before/after pair and at least two distinct invocation markers.
Copies of one invocation do not establish repeatability; different checkpoints
remain separate. Legacy receipts/reports stay incomplete/unavailable. Unbound
sources do not enter these content-group counts.

The fingerprints remain partial: selected stored fields and loaded versions are
observed; tokenizer content, executable code, deeper runtime state, fitting and
source authenticity are not established. Equal outputs/arguments/parameters do
not hide a runtime difference, and equal partial snapshots do not establish full
encoder identity. No census, content admission, forecast selection or innovation
score changes. Real-host cost and the remaining evidence/integration work stay open.

187 isolated checks pass: runtime comparison 12, artifact joins 30, review report
22, encoder costs 14 and census/innovation 109. Tests cover differing snapshots
with identical vectors/arguments/parameters, missing peers, changed boundaries,
legacy/unavailable data, duplicate and invocation semantics, cross-representation
comparison, checkpoint partitioning, public-field validation and actual scratch
CLI parity for census/innovation. Generated reports refreshed without changes.
No private input, live writes, model calls, enabling, merge or deployment.


## 9 November — observe and compare the loaded encode entrypoint

`codex/judges-encode-entrypoint` descends from b683b7ce. Optional artifact capture
now fingerprints the already resolved Python encode function before and after its
single existing invocation. Bounded code-object traversal includes bytecode,
constants and nested code, excluding file/line locations. Only hashes and counts
are retained. No source files, model loads or additional encoder calls are used.
The encode attribute is resolved once; its original result or exception survives.
Observer failures remain passive, and native/callable-object implementations stay
unavailable. Legacy receipts remain valid without invented implementation identity.

Audit retention and invocation-conflict checks include the optional observation.
Offline artifact replay and review add fixed entrypoint-consistency counts within
exact content/checkpoint groups. Matching requires all references observed and two
distinct calls; incomplete evidence never conceals an observed difference. These
are partial Python-code observations: globals, defaults, closure contents, helper
functions, native code, tokenizer contents and full encoder identity remain open.
Scoring, eligibility, forecast choice, fitting and all existing feeds are unchanged.

Capture off is unchanged. Capture on adds bounded background inspection whose
real-encoder cost remains unmeasured. With this observer, encode_seconds measures
the resolved callable execution; attribute resolution and runtime/entrypoint
inspection are outside that timer. It is not a total observation/job cost.

Validation covers synthetic Python code changes with unchanged vectors, nested
code, relocation invariance, unsupported/oversized constants, single property
resolution, mutation during the call, original exceptions, observer failures,
legacy receipts, audit retention, cost conflicts and aggregate report validation.
Two fixture issues were corrected: a nested fixture changed the capture root, and
receipt selection depended on directory order. Production failures were not found.
Full encoder ancestry, real-host costs, phone delivery and host integration remain
open. No private records, real model calls, live writes, enabling, merge or deploy.

211 isolated checks pass: entrypoint 14, runtime producer 16, parameters 19,
encoder costs 14, artifact joins 30, runtime comparison 12, review report 22,
self artifacts 20, forecast inputs 15, encoder benchmark 6, entry owners 11 and
store guard 32. Generated ownership/coverage/store reports refreshed without
changes; diff check clean. All inputs synthetic, sends and encoders stubbed.


## 9 November — benchmark observation coverage, version 2

`codex/judges-benchmark-observation-coverage` descends from 7b82f337. The offline
cost tool previously verified parameter snapshots only, allowing runtime/code
observation failures to yield optimistic timing reports. It now refuses results
unless first and fresh-input repeat calls retain the expected runtime/code pairs
and exact synthetic component counts. A separate fourth phase exercises fresh
receipt retention without another parameter scan; the existing same-input repeat
retains first-call bank entries and is not claimed as fresh receipt evidence.
Schema is judges-encoder-cost-v2; version 1 results remain historical measurements.

The configured profile adds four synthetic modules, stored settings, one config
and one tokenizer-settings object, without loading a model or tokenizer. The
minimal profile remains default. Both profiles measure the entire wrapper call,
including inspection and vector/receipt construction, with allocation and receipt
helper preload excluded. Neither includes sink publication or serving latency.

Local configured-profile measurement: 64 MiB logical arrays, eight tensors, three
iterations. First-call wall median/max is 42.572/43.139 ms contiguous and
50.118/51.026 ms strided. Same-input repeat medians are 2.019/1.996 ms; new-input
receipt-retaining repeat medians are 4.415/4.406 ms. Each run makes twelve stub
encodes and six parameter snapshots, checking six distinct retained calls. These
are synthetic observations without pass thresholds, not real-host acceptance.
No production code, encoder behavior, capture defaults, scoring or admission changed.
Real encoder compatibility/cost, full ancestry, delivery and integration remain open.

21 isolated checks pass: benchmark 10 and entry owners 11. Tests include both
layouts/profiles, observation failure on first and fresh repeat calls, invalid
profile/options before allocation, private aggregate output, no overwrite, and
scratch/network/process boundaries. Generated reports refreshed without changes;
diff check clean. Two additional CLI measurements used only synthetic arrays.


## 9 November — conserve launch support in aggregate handoff reports

`codex/judges-handoff-count-conservation` descends from 32c27b20. The underlying
handoff join already refuses one pending resource certifying several distinct
forecast rows. Its aggregate validator previously accepted impossible summaries:
several launch-backed rows with only one paired launch, orphan launches counted as
support, or more paired launches than job receipts. The review renderer used that
validator and could display these inconsistent supplied counts.

Validation now requires the sum of joined, origin-markers-missing and
pending-row-mismatch rows to fit within paired launches (launches minus those
without a job), and paired launches cannot exceed all job receipts. These are
necessary count-conservation checks, not authentication of the receipts. Missing
markers, mismatches and conflicts keep their existing meanings. Valid aggregate
outputs, runtime capture, joins, census, innovation and training admission are
unchanged. No real-data result is inferred from the synthetic regression.

Three regression cases produced six assertion failures before the fix, including
rejection through the actual review renderer. They now pass; the positive case
retains two independent paired launches plus an orphan, and existing duplicate,
conflict, out-of-window and scratch CLI tests remain valid. No private records,
model calls, live writes, enabling, merge or deployment. Full evidence and host
integration requirements remain open.

59 isolated checks pass: forecast handoffs 26, review report 22 and entry owners 11.
Generated ownership, untested and store reports refreshed without changes; diff
check clean. Regression evidence was captured before applying the validator fix.


## 9 November — self forecasts name the checkpoint bytes they parsed

`codex/judges-loaded-checkpoint-binding` descends from 905881ba. The anchored self
forecast previously parsed a checkpoint, computed a prediction, then reopened the
path to label the result. An atomic replacement in between labelled old parameters
with the new file hash; deletion caused an unnecessary late failure. With capture
on, the manifest mismatch correctly suppressed artifacts, but the saved forecast
still carried the wrong checkpoint identity.

Both self modes now ask the loader to parse and hash one in-memory byte buffer.
Their results use that loaded identity; the later path read is gone. The optional
manifest uses the same buffer. This prospective identity correction is active with
capture OFF too. Stable-file output, prediction/confidence and encoder-call counts
are unchanged. Replacement/deletion after parsing no longer relabels or discards a
valid result. The default loader contract and the other head's path are unchanged.
The optional observation size limit still controls retention, not model loading.

This does not certify atomic publication, fitting/source ancestry or durability.
Bytes describe exactly what was parsed; a concurrently modified/corrupt read can
still fail parsing as before. The compressed byte buffer overlaps parsing instead
of being allocated for a later hash; real-host peak memory/latency is unmeasured.
No checkpoint format, parameter value, model selection, loop/feed or eligibility
policy changes. No private input, model calls, live writes, enabling, merge or deploy.

106 isolated checks pass: new binding 8, artifacts 20, checkpoint availability 12,
existing readout 5, forecast inputs 15, handoffs 26, forecast clocks 9, owners 11.
Before the fix, replacement regressions showed wrong IDs and missing artifacts,
and deletion caused a late file error. New tests use valid atomic replacements,
compare predictions/confidence/call counts, and cover capture off without observer
imports, retention limits, malformed inputs and unchanged other-head loading.
The existing replacement test was updated from artifact suppression to exact
loaded binding; the artifact mismatch guard itself remains unchanged. Existing
synthetic matrix-operation warnings in readout tests persist; all assertions pass.


## 9 November — self-audit checkpoint bytes and filesystem cutoff stay together

`codex/judges-audit-checkpoint-clock`, on e9e3221a, fixes a related audit race:
audit hashed checkpoint bytes and later obtained its scoring cutoff from the path.
A replacement could pair the old hash with the new file's modification time;
deletion caused a late exception. Both were reproduced before the fix.

Self audits now read bytes and modification time through one open file descriptor.
The read is rejected before scoring/report publication if observed device, inode,
size, modification or change time differs across it, or the byte count disagrees.
Nonregular observations are rejected. Replacement or deletion after the snapshot
cannot change its cutoff. These checks detect observable mutation; they do not
certify atomic publication or defend against all concurrent filesystem changes.
The existing modification-time cutoff remains a filesystem estimate, not an
attested fitting-completion time or evidence for strict training eligibility.

Active with capture OFF as well as on; stable-file results and encoder-call counts
remain unchanged. The other head retains its existing path. No new model call,
checkpoint format, model selection, feed, admission, enablement, merge or deploy.
80 isolated checks pass: new audit races 6, artifacts 20, checkpoint availability
12, existing readout 5, ranking 26 and entry owners 11. Synthetic tests cover
replacement, deletion, capture off/on, observed metadata mutations, short reads,
nonregular observations, and the unchanged other-head path. Existing synthetic
numerical warnings occur with passing assertions. Real-host integration, source
ancestry and delivery evidence remain open.


## 9 November — record counterpart and arriving forecast inputs

`codex/judges-selected-feature-inputs`, on 2e3962a3, extends optional forecast
artifacts with `feature_inputs` (`self-selected-features-v1`). Previous receipts
covered selected recent-own replies, leaving the counterpart and arriving inputs
unrecorded. The new observation is made directly from the existing selected context
and six computed arrays before prediction; no encoder call or prediction changes.

The receipt preserves ordered input hashes/character counts for up to six own,
six counterpart and one arriving prefix (400 codepoints each), including duplicate
occurrences. It hashes all six numeric arrays: last/mean own, last/mean counterpart,
arriving and clock. It records their dimensions and selected exchange epoch.
Values use canonical float-list JSON hashing, not a dtype/byte representation;
zero arrays are valid. The clock array is the existing host-local computation.
Its hash records the computed values, not a portable timezone/reconstruction proof.
The added receipt contains no message text, private IDs, paths or numeric arrays.

Capture OFF adds no observation work. Capture ON hashes at most 40,963 numeric
values (five arrays of dimension 8,192 plus three clock values); its maximal test
receipt is under 4 KiB. This is bounded additional background CPU/serialization
work; real-host latency remains unmeasured. A failed observation leaves the old
artifact path available, with the new receipt absent. Existing row, payload join,
encoder calls, sink caps and defaults remain unchanged.

Offline artifact readers strictly validate optional receipts and require their
ordered own-prefix hashes, last-own array hash and dimensions to agree with retained
own embeddings. Legacy absence stays unknown; malformed present data is rejected.
These hashes do not prove encoder identity, feature derivation, complete source
ancestry, fitting, final target selection or client delivery. They do not include
the separate context-baseline encoding. Existing `complete_forecast_context` and
`upstream_complete` remain false. No admission/scoring upgrade or historical inference.

148 isolated checks pass: selected features 8, artifacts 20, forecast inputs 15,
artifact joins 30, runtime comparison 12, loaded checkpoint 8, availability 12,
entry owners 11 and store guard 32. Tests exercise actual predictor inputs,
capture parity, truncation/order/repeats, future exclusion, absent counterpart
zero features, failure isolation, malformed claims, legacy data and maximum bounds.
All inputs synthetic and encoders/sends stubbed. No new model calls, private input,
live writes, enabling, merge or deployment. Host integration and remaining ancestry
and delivery evidence are still open.
