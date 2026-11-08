# Witness slices 1 and 2: offline foundation

Status: review branch, synthetic contracts only. No live capture hooks, scheduler,
model calls, training, feed substitution or deployment. Existing legacy evidence
consumers and all feeds retain their behaviour. This reader is a separate, strict
consumer; its exclusions do not silence an act or remove it from a live store.

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
chat or the interaction ledger. It never searches backups or reinstates erased
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
- `sources`: objects with `kind` (`canonical`, `merged`, `ledger`) and `rows`.
  Canonical/merged rows have `role`, `content`, `turn_id`, `surface`, provenance
  and `witness_receipt`. Ledger adapters read `vintos` as the assistant content.
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

`aggregate.json` contains descriptive counts/errors; `private-innovation.json`
contains private turn IDs/digests and must never enter Git. Neither file is
automatically published. Public evidence requires an explicit privacy review;
even aggregate day-by-day activity can be sensitive. No raw text is emitted.

## Next review increment: what is not done

1. Trace each actual chat provider/fallback and final-delivery path. Capture
   served identity from observed response/runtime receipts; leave it unknown
   when unavailable. Bind only the final response, including postprocessing.
2. Add complete context/effect receipts at assembly time, including indirect
   value-map inputs. Persistent context influence must not be cleared merely
   because the immediate nudge ended. Persist these through canonical/ledger
   writers, not just the merged view.
3. Independently verify checkpoint/encoder manifests and adapters against
   private retained source shapes, without copying private records into Git.
   No real-data accuracy claim has been made by this slice.
4. Add explicitly witnessed reaction receipts: her `haha` (or longer) tied to
   the immediately preceding reply ID, and 4–5-star practice ratings tied to
   that practice. A single `ha`, 1–3 stars, absence or delayed return remains
   unknown, not a negative label. Retain old inferred laughter separately.
5. Build paired last-reply/recent-mean comparisons from the same causal context;
   keep checkpoint groups and evaluation blocks separate. Existing head audit
   qualifications are not replaced by this descriptive reader.

Golden days are not needed for these slices. Later they are familiarity
references, not good/bad identity labels. Candidate high-engagement dates require
Gloria's confirmation, and reference turns must stay separate from evaluation.

Claude Code reviews this branch, runs the full isolated broker suite on an Aegis
test merge, and handles reviewed integration. Gloria handles deployment. The
ten-minute coordination heartbeat remains active between batches.


## Capture increment in progress

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
