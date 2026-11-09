# Judges observation and character-reference handoff

Current candidate: **codex/judges-prospective-mode-receipt**, based on
**97ea9e09**, whose prototype stack is rebased onto **34b662e9** per note #30. Its final published hash is recorded in
the dated local coordination reply. The reviewer reports integration through
80486b4b (live 653/653; deploy 649/650 with a reported unrelated intermittent
latent-feed failure passing three reruns; note #36); this is not an independent
live verification. Prior review branch tips stay fixed. The original dependency
table and totals below are historical, not the current implementation tip or a
combined total of later checks. Note #29 redirects work to the offline character-
reference instrument; new audit-receipt work is paused except review findings.

## Dependency order

These are thirteen consecutive commits, oldest first. Later branches include all
preceding rows; they are not independent patches to merge repeatedly.

| Commit | Review branch suffix (all under `codex/`) | Concrete change |
| --- | --- | --- |
| `1e89f63d` | `judges-draft-response-identity` | Preserve actual response identity through existing draft contracts. |
| `f71dff2c` | `judges-audit-vector-conflicts` | Retain differing audit observations so a later valid copy cannot hide a conflict. |
| `5ca11e30` | `judges-vector-representations` | Separate raw encoder returns from normalized readout vectors. |
| `7df2c9a6` | `judges-window30-attribution` | Optional historical thirty-second view; all nearby replies compete, no training upgrade. |
| `eea58349` | `judges-completion-joins` | Bind selected router completions to saved reply-history versions. |
| `26b5a55a` | `judges-source-coverage` | Source-path trace and counts-only missing-surface diagnostic. |
| `f3da0e61` | `judges-durable-queue-counts` | Persist bounded deferred-writer diagnostic deltas as lower bounds. |
| `fd3746bb` | `judges-encoder-parameter-receipts` | Observe bounded loaded CPU parameter snapshots around audit encoding. |
| `c8219640` | `judges-forecast-encoding-links` | Bind selected forecast features to their raw encoding observations and normalization. |
| `42856612` | `judges-encoding-consistency` | Compare validated observations within exact content groups, offline. |
| `c0a037b4` | `judges-innovation-input-contract` | Refuse ambiguous admitted-target lists and malformed history minima. |
| `1a69dc47` | `judges-attribution-report-contract` | Validate historical report scope/effects and count conservation. |
| `83118e87` | `judges-encoder-cost-benchmark` | Bounded synthetic CPU benchmark and reproducible reviewer commands. |

## What runs where

- **Prospective generation metadata:** `bin/model_router.py`, `bin/server.py` and
  `scripts/request_trace.py`. Completion/history linkage operates even when optional
  witness capture is disabled. A completion marker, HTTP trace and provider request
  ID are different identities. Saved history precedes the final response guard, so
  this is not proof of client delivery or every internal attempt. Existing fail-open
  ledger writes do not establish durability. Other generation paths are not given
  invented completion IDs.
- **Optional capture work:** `scripts/witness_sink.py`, `scripts/witness_capture.py`,
  `scripts/witness_self_artifacts.py` and the guarded self-on-message section of
  `scripts/jepa_readout.py`. CPU snapshots are bounded but can scan up to two GiB per
  captured wrapper. Their cost is separate from queue admission. Existing outputs,
  encode counts and model selection remain unchanged by contract tests. No other
  head is instrumented by the forecast increment.
- **Offline-only work:** attribution/coverage, artifact joins, replay, report and
  benchmark. It neither admits historical tiers into strict training evidence nor
  supplies scores to live consumers. The benchmark lives under `experiments/` and
  requires no production installation.

## Verification at the implementation tip

Local OS-isolated run on 9 November: **393 checks across 16 focused suites, all
passed**. Tests use synthetic stores and stubbed senders. This is not the full
Aegis broker suite, real-data accuracy or serving acceptance.

| Suite (`broker/tests/`) | Passed checks |
| --- | ---: |
| `test_judges_witness.py` | 109 |
| `test_witness_artifact_join.py` | 30 |
| `test_witness_attribution.py` | 26 |
| `test_witness_attribution_coverage.py` | 21 |
| `test_witness_completion_joins.py` | 9 |
| `test_witness_deferred_capture.py` | 22 |
| `test_witness_draft_identity.py` | 9 |
| `test_witness_encoder_benchmark.py` | 6 |
| `test_witness_encoder_parameters.py` | 19 |
| `test_witness_review_report.py` | 20 |
| `test_witness_router_completions.py` | 7 |
| `test_witness_self_artifacts.py` | 20 |
| `test_witness_capture_hooks.py` | 21 |
| `test_merged_chat.py` | 31 |
| `test_entry_owners.py` | 11 |
| `test_store_guard.py` | 32 |

The count combines unittest cases with the older suites' named checks; it is not a
count of full broker suites. Each ran via `scripts/run_isolated_test.py`. Generated
ownership/untested/store reports were refreshed and their ownership checks passed.

## Host review still required

1. Run the full isolated broker suite on the candidate integrated with concurrent
   deploy-branch work. Preserve those changes and regenerate derived reports there.
2. Remeasure occupied-sink worker throughput, burst retention and response latency
   after the diagnostic flush change. Persisted counts are lower bounds;
   `restart_loss` remains unknown. A count difference is not a loss estimate.
3. Measure encoder observation CPU/memory cost in the existing host environment.
   [The synthetic benchmark commands](../experiments/judges-witness/README.md)
   need no model or private data. Local 64 MiB arrays measured roughly 42–49 ms per
   first observed call; these are neither host measurements nor a forecast for real
   tensor-runtime cost. Loaded-runtime compatibility and real packet sizes need
   their own check before optional capture is enabled.
4. On the existing admitted private snapshot, inspect the source-coverage and
   optional thirty-second attribution view. Keep its partition separate from the
   original ten-second view; do not sum them. Copies are not independent turns,
   exact label disagreement is not automatically a model-family mismatch, and
   historical attribution does not prove clean ancestry or delivery.
5. For future retained packets, inspect content-binding, timing and observation
   consistency counts. Matching snapshots are not full encoder identity. Tokenizer,
   loaded execution configuration/code, fitting lineage and forecast-target
   association remain unresolved. Missing evidence never becomes zero error.

[Source tracing](judges-source-coverage.md) establishes the current bilateral text
path and the source-field behavior; it does not establish the historical cause of
stopped router-chat records. The private copied-data diagnostic is still needed.
No source/date/model attribution is guessed to fill that gap.

No training-set decision, model replacement, live feed change, enablement, merge or
deployment is part of this handoff. Claude Code reviews and owns the host checks;
Gloria owns enabling/deployment. The ongoing collaboration continues independently
of the review queue.


## Subsequent offline increment

`codex/judges-attribution-match-methods` descends from the documentation handoff
commit f7eccc6e. It adds fixed matched-method coverage to historical attribution
and its public report, without changing matching or runtime producers. The
thirteen-commit range and 393-check result above remain the prior checkpoint, not
a test claim for this increment. Its 79 affected isolated checks pass: completion
joins 10, report 22, attribution 26, source coverage 21. Exact revision is recorded
in the coordination reply after push. Full host acceptance remains outstanding.


## Historical source follow-up

`codex/judges-historical-test-caller` adds source evidence for an old test-origin
candidate: a lower-level result-contract test called the chat router without
isolating the accounting path, followed by September 11 isolation fixes.
See judges-source-coverage.md for exact revisions, import-path limitations and
the check against the existing private copy. Nine source assertions passed; no
runtime code or historical attribution changed. Retained-row origin is still
unconfirmed, and no new private collection or deployment is requested.


## Reviewer note 28 and burst-capacity increment

Reviewer reports integration through f7eccc6e as c499460e, with full Aegis suites
633/633 deploy and 636/636 live. This is reviewer-reported integration, not a claim
of deployment by this worker. The prospective reply-join observer runs even with
capture off: ledger rows gain completion ID/response hash, saved history gains
`generation_join`, and the two toggle draft paths record provider-response model
identity when available. Routing, text and exception behavior remain unchanged.
Those metadata paths are separate from optional witness capture.

`codex/judges-burst-capacity` is stacked after 1feb34e5, retaining the two later
attribution/reporting and historical-source commits. It raises FIFO slots to 64
under an independent 8 MiB byte budget (plus one in flight), with 66 local isolated
checks passed. Host burst/cost acceptance remains review work. Queue persistence
and restart replay are still open; this increment makes no durability claim.
The two missing toggle ledger writes were already fixed in d3dd754a and covered by
the router completion suite in the prior 393-check checkpoint; no duplicate fix is
made for that item. Historical chat origin and surface-less copies remain pending
private evidence, with the concrete test-origin lead documented separately.


## Restart-publication prerequisite

`codex/judges-replay-publication` descends from 9c55f92e. It adds an optional stable
packet ID to the internal sink publisher, so retrying a confirmed byte-identical
file under that name cannot create another packet or double-apply status counters.
Existing callers omit the argument. 73 local isolated checks pass, including a
child process dying after atomic linking and concurrent retry callers.
This is not the durable queue: spool storage, age/config binding, acknowledgement,
startup replay and host latency measurement remain the next work. Stable naming
provides no permanent tombstone once a final file has been removed. No production
flag, live data, merge or deployment changed.


## Durable spool implementation

`codex/judges-durable-spool` descends from 272b2d0b and now wires the previous
publication primitive into bounded private ingress and startup replay. This
supersedes the unfinished-spool statements above; default memory mode remains
unchanged and no capture is enabled. Full operating semantics and costs are in
[judges-capture-enable-proposal.md](judges-capture-enable-proposal.md#durable-ingress-mode-implemented-host-acceptance-pending).

Explicit durable mode confirms synced ingress, then replays exact bytes under a
stable ID and the original config/retention age. It holds changed-config records,
keeps publication failures for retry, and never infers phone delivery. The startup
hook runs no disk replay inline. Counter updates remain lower bounds. Host burst,
near-cap foreground fsync latency and filesystem acceptance remain reviewer work;
the previous 0.3–0.4 ms memory-queue result is not a durability measurement.

The new isolated spool suite covers 25 synthetic cases, including new-process
startup without a new capture, abrupt exit after publication before acknowledgement,
30-packet retention, slot/byte bounds, old-store headroom, corrupted/unsafe records,
disable/retarget/config changes, original age and fail-open startup. Existing sink
26, deferred queue 26 and hook 21 checks also pass. Generated-report checks are
recorded in the coordination reply after completion. This is local contract
validation, not the full integrated Aegis suite or live acceptance. Review stays
with Claude Code; enabling/deployment stays with Gloria.


## Encoder-call cost increment

`codex/judges-encoder-call-cost` descends from 0c9c42cf; it adds observation around
existing optional background work, not an on-demand real-model benchmark. New
`timing` fields separate parameter scan and encode durations, leaving unmeasured
stages null. The offline report combines supplied retained calls by invocation and
excludes conflicting cost copies; legacy data remains explicit. Snapshot byte
counts describe repeated scanned tensors, not model RSS. No identity or admission
upgrade accompanies the measurement. Existing output/call/exception contracts and
capture-off behavior are preserved.

111 affected isolated checks pass (cost 14, parameter receipts 19, joins 30,
report 22, self artifacts 20, benchmark 6). No live encoder or private records were
loaded. The reviewer can inspect these aggregate fields in future normally captured
packets after operator enablement; missing receipt coverage is never a zero-cost
result. These timings exclude serialization/publication and do not replace the
separate durable-spool reply-path latency test. Full integrated host validation,
real-runtime compatibility and enablement/deployment boundaries remain unchanged.


## Historical fixture count increment

`codex/judges-historical-fixture-counts` descends from 3260aa77. It turns the
previously documented test-origin candidate into a fixed aggregate section in the
existing offline coverage CLI. The exact source fixture tuple is compared only
on clocked matching-caller records before the existing cutoff; missing metadata,
other values, unknown clocks and later records stay separate. All baseline
attribution/window fields remain unchanged. Equality never labels a record as a
test or changes training admission. No private identifiers or model labels are
emitted by this new aggregate.

55 affected isolated checks pass, plus five read-only source assertions. The
reviewer can rerun the documented coverage command on the existing admitted copy
with a new private output directory and report only `historical_fixture_coverage`.
No recollection is requested. Retained execution evidence is still needed to
establish origin; none was inspected by this worker. No merge or deployment.


## Checkpoint consistency increment

`codex/judges-checkpoint-consistency` descends from 2895b42f. Offline ingestion
validates the existing manifest contract and reports differing metadata under the
same checkpoint hash. Read-availability clocks are separately validated; they do
not make identical checkpoints conflict merely because they were read at different
times. Legacy peers remain incomplete, and cannot hide known conflicts. Current
version malformed/forged fields fail explicitly rather than being dropped.

111 affected isolated checks pass (consistency 13, joins 30, availability 12,
report 22, cost 14, self artifacts 20). No raw checkpoint is authenticated by this
check, no reported date becomes an observed training date, and no scoring/admission
change is made. The aggregate exposes only counts. Runtime capture remains exactly
as before; real encoder/runtime/fitting lineage and forecast-target association
are still open. Full host integration and private copied-evidence review remain
yours; no enabling, merge or deployment.


## Forecast pending handoff increment

`codex/judges-forecast-handoff` descends from c6829c80. New optional launch/job
sidecars bind canonical pending data and locator hashes to the exact forecast log
row; no changes to the pending/log schema or forecast content. Capture-off paths
remain inert. Capture on adds a small launcher publication using the existing
queue/spool and one background sidecar; measure its incremental host cost.

The new `self_forecast_handoffs` replay input accepts both sidecar kinds. The
`forecast_handoffs` report is a counts-only consistency diagnostic, including
missing peers and markers, mismatches/conflicts and exact row binding. Receipts
are validated before filtering; duplicates collapse; source identity remains
unverified. No forecast or reply becomes eligible because of this join. This
supplies one missing prospective handoff boundary; it does not complete caller,
training, encoder or delivery lineage, and cannot backfill historical markers.

307 affected isolated synthetic checks pass. Existing numerical warnings from the
synthetic head training suite did not fail its 32 checks. Owner/generated checks
and the exact pushed commit are recorded in the coordination reply. Full host
integration and existing copied-data interpretation remain review work. No real
encoder/checkpoint or private records were loaded, no capture enabled, no merge
or deployment performed. Earlier review branch tips remain fixed.

The launcher uses deferred publication in configured memory mode. Durable mode
uses a narrowly versioned v2 ingress header retaining the launch prefix; existing
chat ingress still writes/reads v1 unchanged. Background job sidecars retain the
existing synchronous publication semantics. Both new final packet prefixes are
recognized by sink retention. Invalid v2 prefixes are held, never replayed as chat
packets. Older sink code does not understand these new types; coordinate the sink
and producer versions if capture is enabled. No configuration is changed here.


## Main-chat forecast event-key increment

`codex/judges-chat-forecast-key` descends from f5dd8728. One shared pure function
retains the coordinator's existing event-ID mapping. Main chat's early forecast
hook uses it to reserve the same key that the bilateral wrapper will use later;
it neither opens the coordinated turn early nor moves the forecast call. Unknown
request context remains unknown. Explicit keys and non-chat/full surfaces are
unchanged. No historical record is rewritten or assigned an inferred identity.

This changes prospective pending/log metadata even with capture off. Coordinator
IDs, duplicate detection, barrier/capsule order, history selection/merging,
post-turn feeds, model routing and output/evaluator behavior remain unchanged.
The reserved key does not establish an actual target or phone delivery; full
origin/lineage/clock and strict eligibility requirements still apply. Keep server,
request_trace and turn_coordinator versions together in integration.

105 affected isolated checks pass (new 11, coordinator 33, handoffs 19, on-message
head 32, completion joins 10), with owner/generated checks recorded in the reply.
Actual launcher/pending/log propagation and concurrent request separation are
covered with synthetic data and stubbed external actions. No real encoder,
checkpoint, source snapshot or service was used. Host integration remains yours;
Gloria owns enabling/deployment. No review pause or deploy action introduced.


## Reverse handoff cardinality correction

`codex/judges-handoff-cardinality` descends from 991f4830. This fixes a false joined
state in the offline handoff diagnostic: a pending resource may correspond to
only one distinct saved row. Every supplied job reference participates, even if
its row is absent or outside cutoff. Exact duplicates collapse; independent
pending resources sharing a turn are not fused. Runtime producers and the
innovation scorer's existing earliest-forecast policy are unchanged.

Three synthetic failures reproduced the old behavior; all 165 affected isolated
checks now pass (handoffs 23, chat keys 11, report 22, census/innovation 109).
No source authentication or training permission is conferred. No private input,
live service, enabling, merge or deployment. Full host integration stays yours.


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


## 9 November — existing context-baseline call gets a bounded receipt

`codex/judges-context-baseline-binding`, on 204e369f, observes the separate existing
context-baseline encoding when optional self forecast artifact capture is enabled.
It adds `context_baseline` (`self-context-baseline-v1`) to the exact-row-bound
artifact packet. There is no new encode, retry, parameter scan or model load.
The original capture-off and other-head encoding paths remain unchanged.

The receipt records ordered role/prefix hashes for the six selected turns,
checks the actual legacy rendering (300 codepoints per turn, joined by a space
and newline; at most 1,810 codepoints), and hashes the exact rendered input.
It records dimension and canonical float-list hashes of the existing raw result
and normalized context vector. The producer checks the normalization and saved
forecast vector agree. No text, private IDs, paths or vectors are added by this
receipt. Maximum vector dimension is 8,192; its maximal text-selection fixture
receipt is under 2 KiB. Zero/nonfinite/out-of-bounds observations are unavailable.
A formatter change also leaves this receipt absent rather than mislabelling it.

Observation failure leaves the existing forecast and artifact path intact.
Encoder failure still propagates the original exception without retry. The
baseline's encoder identity, parameters/runtime, source ancestry and cost remain
unobserved; existing cost totals still concern the separately instrumented calls.
This is bounded extra background hashing/normalization, with real-host latency
unmeasured. It does not certify feature derivation or full upstream completeness.

Offline replay validates any present receipt and reports fixed counts per unique
artifact packet: missing observation, missing exact forecast version, conflicting
receipt variants, identity/clock/vector disagreement, outside cutoff, or bound to
the exact saved forecast. All supplied peers participate in conflict checks.
Binding requires the same checkpoint/mode, exact saved-row hash, matching packet
clocks, an in-window forecast and the exact normalized baseline vector/dimension.
These are packet counts, not unique turns or eligible training examples. The
public renderer emits only fixed aggregate states. Legacy absence stays unknown.
No admission/scoring, target-selection or delivery claim changes.

175 isolated checks pass: context baseline 10, artifacts 20, inputs 15, selected
features 8, artifact joins 30, review report 22, encoder cost 14, loaded checkpoint
8, existing readout 5, entry owners 11, store guard 32. Tests exercise the actual
formatter/predictor path, capture parity and unchanged scan counts, ordered repeated
prefixes, failure isolation, exact-version/conflict/cutoff handling, malformed and
legacy receipts, bounded output and aggregate rendering. Synthetic numerical
warnings in the existing readout suite persist with all assertions passing.
Generated reports refreshed; no new files need deployment manifest entries.
No private input, real model calls, live writes, enabling, merge or deployment.
Host integration, complete ancestry and phone delivery remain open.


## 9 November — selected-input observations become visible in offline coverage

`codex/judges-selected-feature-coverage`, on 71081e44, adds the optional public
`selected_feature_states` aggregate alongside context-baseline bindings. Selected
input receipts were already retained and validated, but their coverage was absent
from the aggregate review. This change is offline only: no producer, capture,
encoder, model, feed, scoring or admission behavior changes.

Counts are per unique supplied artifact packet, not unique turns or training
examples. Exact duplicates collapse. States distinguish non-forecast packets,
legacy/missing observation, conflicting receipt variants, missing exact saved
forecast version, mode/checkpoint or clock mismatch, outside cutoff, a selected
exchange clock that is not strictly before arrival, and binding to the forecast.
All supplied receipt variants participate in conflicts before cutoff/row matching;
a future-dated or unmatched peer cannot hide behind a usable copy. Present malformed
receipts or disagreement with retained own embeddings reject the input bundle.

Binding means exact saved-row hash, checkpoint/mode and packet clocks agree, the
forecast precedes cutoff and the observed selected-exchange clock precedes arrival.
It does not reconstruct counterpart/arriving source identity, prove derivation,
certify encoder identity or complete ancestry, select a target, or admit training.
The shared exact-row checker preserves existing context-baseline behavior.

The renderer accepts only fixed labels and nonnegative integer counts summing to
unique packets, rejects a lone conflict, and cross-checks non-forecast counts with
context-baseline coverage when both are present. Older reports without this field
remain accepted. Private hashes, text, vectors and IDs are not rendered.

90 isolated checks pass: new coverage 9, selected features 8, context baseline 10,
artifact joins 30, review report 22, entry owners 11. Tests include actual synthetic
producer receipts, duplicate collapse, missing versions, conflict order/future
peers, malformed claims, cutoff and selected-clock boundaries, renderer bounds,
legacy reports and the actual scratch replay CLI with 0600 aggregate output.
Generated ownership/coverage/store reports refreshed without changes; diff clean.
No real data, new encoding, live writes, enabling, merge or deployment. Host
integration and full source/encoder/delivery evidence remain open.


## 9 November — character-reference instrument prototype

The active instrument now lives in `experiments/character-reference/prototype.py`.
Its README supplies the complete private input contract and runner command. It
consumes supplied frozen reply/context caches, reuses historical attribution, and
produces day-held-out semantic familiarity percentiles, style-only and centroid
controls, exact-linked witnessed-positive similarity, family strata and shared-day
family differences with day-bootstrap intervals. High-engagement reference dates
are candidates only. Shuffled own reply marginals correctly remain indistinguishable
by response-only familiarity; context alignment is separately measured.

Primary experimental rows use ten-second/exact ledger matches or a recorded label
agreeing with independently observed model evidence. Bare labels are excluded;
30-second results are separate sensitivity. No strict admission rule is changed.
No embedding model is loaded or downloaded, and no projection is trained.

49 isolated checks pass: prototype 12, attribution 26, owners 11. The synthetic
16-day/32-reply fixture exercises four reference days, independent evaluation,
foreign controls, family comparisons, feedback linkage and private CLI guards.
Its perfect deliberately separated foreign-control score is a fixture result,
not evidence about his actual history. No real candidate dates or character results
have been produced. Claude's next concrete step is the private copied-history run
with exact frozen cache entries and matched controls under the documented contract;
return only aggregate output and proposed dates/counts. No review pause is needed.

Source/encoder authentication, nuanced novelty/refusal/opposite-stance controls,
real-history stability and prospective validation remain open. No live connection,
model/loop changes, paid calls, deployment or merge.


## Character-reference context comparison follow-up

The base instrument compares families sharing evaluation days. The follow-up adds
same-day, same-language, length-screened, context-matched one-to-one comparisons,
chosen without consulting scores. It reports four paired percentile differences,
day-level intervals and matched/unmatched counts for recognized families. Empty
matches stay unknown. Matching is deterministic greedy, with supplied context
vectors and reply length as observational proxies; no causal invariance claim.
26 isolated checks pass (prototype 15, owners 11). This is offline scoring only;
no encoding, attribution, strict admission or live behavior changes. Actual private
history results remain outstanding with Claude; no new data request to Gloria.


## Character-reference evaluator cost follow-up

Note #31 confirms Claude is reviewing the prototype and running the private history.
This independent follow-up reuses each held-out/calibration/positive-reference
statistic set within the current evaluation. Control rows are indexed by exact
reply ID. The original formulas and operation ordering are preserved; no persistent
cache, data-contract, admission, encoding or result change. 29 isolated checks pass
(prototype 18, owners 11), including complete aggregate/private-output differential
parity, degenerate references, repeated-run independence and fixed build counts
under multiplied evaluation/control load. Real-host timing remains unmeasured.


## Character evaluation groups for tolerated novelty and changes

Optional exact-linked owner/reviewer annotations describe benign novelty, refusal,
opposite stance, humor and surface shift. Fixed aggregate groups report scored and
unscored counts plus four percentile summaries/intervals; absence stays unknown.
They never influence reference selection, admission or scores, and humor tags never
stand in for witnessed positive feedback. No acceptance gate or identity verdict.
32 isolated checks pass (prototype 21, owners 11). Input labels are optional; the
current private run can finish unchanged. Actual label coverage/results remain
unknown until the reviewer supplies them; no labels are generated or inferred.


## Readable aggregate character summary

The scratch runner also writes 0600 `summary.md`: fixed aggregate tables for
coverage, proposed dates/counts, facets, family comparisons and optional groups.
It identifies synthetic versus supplied copied-history inputs, shows absent
measurements as unknown and warns that the primary/window30 views overlap. No
reply text, IDs, vectors or annotation rationale is rendered. Scoring/input
contracts are unchanged. 36 isolated checks pass (prototype 25, owners 11),
including the actual CLI output and privacy/unknown rendering. Actual-history
findings still await Claude; no new encoding, model calls or live effects.


## Note #32 private-run findings and reference-family composition

Claude reports primary unscored: 38 admitted replies on one day. The window30
view scored 123 replies across 36 days, with no reviewed foreign/other-surface
controls, limited linked feedback and unverified encoder revision. These private
results are not independently reproduced here; incomplete owner-surface coverage
makes candidate dates provisional. Do not interpret familiarity as identity.

Added candidate-day and actual held-out-fold reference-family counts separately
for each attribution view. Zero coverage stays zero; this exposes imbalance
without changing the reference or scoring. The Markdown summary includes per-day
composition. Next work: trace engagement across all source surfaces, assemble
provenance-reviewed controls privately with Claude, and pin known encoder identity
rather than promoting an unverified revision. No frozen-day decision is made here.


## Notes #33–34: mode first; avatar and ReelRoom remain distinct

Gloria confirms the low daily counts are expected. Withdraw the missing-surface
hypothesis from note #32; the ten reviewer-reported dates remain provisional.
The reported pooled family difference is confounded with conversation mode, not
evidence of a model effect.

Schema v2 binds explicit local mode observations to exact reply IDs/hashes, using
router-decision, intimate-state or documented conversation-transition evidence.
Model family/toggle alone never supplies a mode. Missing/conflicting evidence is
unknown and unscored. References, calibration and positive-feedback subsets match
mode AND surface; controls require matching mode. Explicit ReelRoom remains
separate from avatar in engagement totals, references and cross-family pairing.
Within-mode overlap is required for matched comparisons; no pairs is explicitly
not identifiable. The summary omits pooled family comparisons, includes separate
mode results and marks admitted-but-unscored unknowns. No new encoding or gate call.

42 isolated checks pass (prototype 31, owners 11). Fixtures prove cross-mode and
cross-surface independence, exact/dated mode binding, no family inference,
conflicting signals, one-family non-identifiability, controls and aggregate output.
The private exporter contract/source trace is in the experiment README. It still
needs actual retained mode evidence, reviewed controls and encoder pinning before
a meaningful rerun. Intimate rows remain local-only in private scratch; export only
aggregates. No source stores read here, live writes, routing changes or deployment.


## Requested encoder revision/artifact pin in private run manifest

The manifest now retains the exact supplied encoder contract instead of only an
opaque input hash. Optional `--encoder-artifact` hashes one explicit regular copy
inside private scratch (1 byte–4 GiB, no model loading). An optional expected
artifact SHA-256 must match observed bytes or output is refused. Unknown, declared,
observed and verified-hash states remain separate; raw identity stays private.
Revision-label verification and cached-vector derivation are never inferred from
an artifact hash. 45 isolated checks pass (prototype 34, owners 11), including
actual CLI verification/mismatch/outside-scratch/privacy cases. Actual Aegis
artifact identity must still be supplied/observed there; no live model inspected,
called or changed here. This addresses notes #32/#33's manifest omission.


## 9 November — reviewed control pools and deterministic matching

`codex/judges-character-reviewed-controls` follows dd811da0. Schema v3 adds a
local reviewed control pool, context-only greedy matching without replacement,
primary-first target order, and explicit review bindings for pooled and paired
controls. Foreign candidates must be non-subject and surface-matched; his own
other-surface text is a separate comparison, never an authenticity negative.
Missing reviews remain excluded. All input assistant text is barred as a control,
including unattributed rows; mode, language, length and context gates still apply.
Public reports contain only aggregate coverage; private-controls.json retains all
selected pairs, including those lacking scorable reference folds. Review/source
claims remain supplied, not independently authenticated. No real controls were
collected here; private data collection and rerun remain with the reviewer.
53 isolated checks pass (prototype 42, owners 11), using synthetic non-intimate
fixtures. Generated reports refreshed unchanged. No encoder/model calls, network
collection, live writes, merge or deployment. Prior review branch tips stay fixed.


## 9 November — source contract aligned with the private control collection

`codex/judges-character-control-sources` follows 80486b4b. Note #35 identifies
Slack, MoltBook and journal controls and store-authorship evidence; the prior
validator would reject those fixed source labels. Controls now admit `slack`,
`moltbook`, `journal` and a separate `store_authorship` reviewer class. This does
not expand engagement/reference surfaces or owner/reviewer evaluation annotations.
The same exact source binding, evidence hash, explicit author/mode, timestamp and
matching constraints remain required. No provider/filename/missing-mode inference.
Selected counts retain source surface and evidence class; private pair records do
too. Source authorship remains explicitly unverified, and store evidence is not
represented as a human review. Private collection/rerun belongs to the reviewer.
The short plain-language results page requested in #35 remains pending actual
mode-by-surface coverage; no new real-data results are asserted here.
Validation: 45 isolated prototype tests; ownership checks recorded in the dated
coordination handoff. No live writes, calls, merge or deployment.


## 9 November — plain-language reader page prepared for returned aggregates

`codex/judges-character-reader-summary` follows a50959ad. The offline CLI now
writes reader-summary.md alongside its detailed report, using only fixed labels
and aggregate numbers. The page explains familiarity, rank versus identity
probability, measured versus selected controls, provisional reference days,
positive-feedback limits and supplied source/encoder evidence. Primary and
sensitivity views stay separate; unscored primary evidence is never replaced by
a sensitivity finding. Unknown mode and missing measurements remain explicit.
Synthetic runs are prominently labelled; no real rerun coverage is claimed.
Three new tests plus the actual CLI check cover missing primary coverage, true
zero versus unknown, unsafe metadata exclusion and malformed numeric rejection.
48 isolated prototype checks pass; ownership result is in the dated handoff.
The final real-data summary remains pending Claude's mode-by-surface aggregates
from note #35. No private data collection, live changes, model calls or deployment.


## 9 November — prevent private input values from leaking through CLI failures

`codex/judges-character-private-errors` follows ce4c6e00. A focused privacy review
reproduced two leaks with synthetic markers: an invalid timestamp appeared in a
parser traceback and a missing source filename/path appeared in stderr. The CLI
now exits nonzero with a fixed JSON failure label and allowlisted exception class,
without exception text or traceback. Imported functions keep normal exceptions for
private local debugging. Failed writes may leave partial private artifacts and are
not successful reports; this is documented. Standard argument usage errors remain
unchanged, so secrets do not belong in CLI arguments.
50 isolated prototype checks pass after both new regressions failed on the old
entrypoint; ownership results are recorded in the dated handoff. No real private
records were accessed. Real coverage is still pending the independent rerun.
Notification delivery remains rate-limited until the recorded 11:43:46 CST retry
window; no early retry, new destination, live writes, merge or deployment.


## 9 November — prospective mode decision receipts and honest character2 summary

`codex/judges-prospective-mode-receipt` follows 97ea9e09, implementing note #36.
Existing gate decisions now produce content-free request-local metadata with turn,
request and evaluated/selected completion IDs. Exact YES/NO provide mode; skipped,
failed or ambiguous gates remain unknown. Refusal-guard reroute decisions have
separate times/causes and do not claim a replacement succeeded. No extra gate,
provider call or routing mutation. Metadata is retained beside generation_join
in history/canonical records and via the existing background ledger environment;
receipt construction performs no file/network I/O. Existing history write timing
is unchanged. Both ledger twins agree; merged chat retains the new field.
50 isolated checks pass: mode receipts 9, completion joins 10, router completions
7, device marks 13, ownership 11. All sends/providers are stubbed and stores are
scratch. Six changed Python sources compile without execution. Generated reports
refreshed unchanged. The plain-language status page uses only reviewer-reported
character2 aggregates: 0/123 mode coverage, zero controls, and no stability verdict.
These code changes are for review, not deployed. Gate-bypassing routes will still
be unknown; a provider toggle is not an independent intimacy decision.
New note #37 authorizes historical somatic marks first and an explicitly labelled
owner family rule second; that is next work on a separate branch, with the private
character3 run left to the reviewer. The reported latent-feed flake remains a
separate follow-up. Completion ntfy alerts are cancelled under the user's new rule;
only new unresolved issues may use ntfy. No live writes, merge or deployment.


## 9 November — historical mode priority and family-derived comparison exclusions

`codex/judges-historical-mode-evidence` follows 2dccf7f0 for note #37.
The offline prototype consumes bound prospective mode receipts first, preserving
unknown/invalid receipts as unknown, then independent exact observations, reviewed
somatic intervals, and an explicitly enabled owner family rule. Final mode_source
is retained with private evidence hashes; public reports show only source counts,
somatic coverage and disagreement with the family rule. Reference folds expose
source composition. Family-labelled targets and targets whose reference folds
include family-labelled replies are excluded from independent family comparisons.
No remaining overlap means not_identifiable, never invariant.

Source inspection found the narrator persists through/at/narration and a somatic
thread, without the detected interval. Its current 24-hour scan is not a session
label. The private importer must review a bounded interval from retained evidence;
join is same surface plus optional exact session, inclusive start/end, zero padding,
maximum 7200 seconds. Unbounded marks contribute no mode. Overlapping disagreement
stays unknown; stale review bindings fail. Original records and input bundle must
remain private. No real messages/stores were opened here and no encoder/model calls
were added. This is not a character3 result or a change to provisional golden days.

Validation: 57 isolated prototype checks and 11 ownership checks pass (68 total);
new cases cover opt-in fallback, somatic priority/bounds/session/review/conflicts,
receipt binding/unknown priority, reference contamination and aggregate privacy.
Generated reports are refreshed unchanged. Source documents give the exact private
import contract. Claude owns the private character3 run and full-suite review;
Gloria owns deployment. The latent-feed flake is still a separate follow-up.
No live writes, merge or deployment; no completion ntfy under the revised policy.
Heartbeat remains ACTIVE.


## 9 November — retain private mode assignments before scoring

`codex/judges-private-mode-assignments` follows 94dca59e. Inspection found that
private-evaluation.json records only scored primary replies. For an unscorable
primary set it is empty, even when historical mode labels exist. The CLI now
writes private-mode-assignments.json (0600) for all admitted/deduplicated replies,
including unknown, sensitivity-only and insufficient-reference cases. It retains
normalized mode/source/evidence hashes plus reply identity, time, surface, family
and admission basis; no content, vectors or session IDs. The file remains private.
Retain original input/evidence bytes for reconstruction; hashes are not independent
authentication. The optional run collector leaves scoring and aggregate returns
unchanged. Excluded input replies do not enter this file.

Both new regressions failed before implementation; all 59 isolated prototype
checks pass afterward, including real CLI permissions and public-output exclusion.
Ownership check results are recorded in the coordination handoff. This changes no
mode decisions, references, controls, thresholds or public scores. No private
collection, encoding/model call, live write, merge or deployment. Claude owns the
private character3 run; its aggregates have not arrived. The latent-feed failure
trace remains requested; no speculative fix or repeated alert. Heartbeat ACTIVE.


## 9 November — distinguish absent mode measurements from measured zeros

`codex/judges-mode-coverage-unknown` follows 32beae6f. Review found that both
summary renderers treated absent source counters in older schema-v3 reports as
zero, although those reports never measured source-labelled mode coverage. They
now state not recorded/not measured when the recording-state field is absent.
New sparse-counter reports still preserve measured zeros. Somatic disagreement
is not measured when no labels are comparable; zero disagreements with a positive
denominator remains zero. Invalid state flags/counts fail without echoing metadata.

Both new regressions reproduced the issue before the fix; 61 isolated prototype
checks pass afterward. Ownership validation is recorded in the coordination handoff.
This is a presentation correction only: no mode/source assignment, scoring,
reference/control selection or input admission change. No private data, model calls,
live writes, merge or deployment. Character3 and the latent-feed failure trace
remain with the reviewer. No repeated status alert; heartbeat remains ACTIVE.


## 9 November — aggregate-only summary command for character3

`codex/judges-aggregate-summary-cli` follows f6647451 for note #38. The existing
reader and detailed renderers can now run through --aggregate-report, with no
private bundle, scoring or encoder/artifact access. It reads a bounded schema-v3
aggregate file inside explicit private scratch and writes only the two pages plus
a source-byte/renderer hash manifest into a new 0700 directory, files 0600. Both
pages validate before writing; arbitrary input metadata is not echoed. Source
bytes are unchanged. No scoring or result values are regenerated.

Mixed evaluation/artifact options, symlinks, outside-scratch paths, oversized input
and overwrites are rejected. Existing evaluation CLI behavior remains intact.
64 isolated prototype checks pass, including actual aggregate CLI success without
private inputs, exact renderer parity, permissions, error privacy and refusal cases.
The success and sanitized-error regressions failed before implementation. Required
report/ownership results are in the coordination handoff. README gives the exact
command for the private character3 report. Actual character3 aggregates and the
latent-feed failure trace remain pending with the reviewer; this is not new data.
No private reads, model/encoder calls, live writes, merge or deployment.
Heartbeat remains ACTIVE; no completion/routine ntfy under the revised policy.


## 2026-11-09 — Exact-exchange control mode inheritance

Coordination #39–40: foreign controls can inherit the mode of their explicitly
reviewed adjacent subject reply, with source surface and both text hashes bound.
There is no timestamp-nearest or control-author-family guess. Invalid links stay
unknown. Pool matching retains the source exchange assignment when choosing a
target. Private pair outputs retain the anchor/source evidence; public output is
counts only. Family-derived mode remains an assumption and cross-family exclusions
are unchanged. 69 isolated prototype checks pass; ownership validation and exact
review commit are recorded in the coordination reply. No new private data run,
model call, live write, merge or deployment. Prospective somatic metadata is next;
full suites and private character rerun remain with the reviewer. Heartbeat ACTIVE.


## 2026-11-09 — Prospective somatic intervals from the existing narrator call

Coordination #39–40: optional ordinal bounds are returned by the existing narrator
call, mapped to explicit timestamps/turn IDs/text hashes and retained as metadata
in the existing narration snapshot and thread extra fields. Legacy narration and
NONE handling, schedule, dedup, model selection and call count remain intact.
Missing/invalid evidence never labels a daily window. Strict per-turn matching in
the offline prototype consumes reviewed projections without reading narration text;
nearby turns are excluded. Provider-reported served model is retained when present,
otherwise unknown; fallback remains unknown. Metadata is private, fixtures synthetic.

Targeted validation: 72 prototype, 11 interval receipt, 6 existing thread-source,
6 existing scheduling checks; ownership results and exact review tip are in the
coordination reply. No actual provider call, private record read, live write, merge
or deployment. Real format compliance/coverage remains unmeasured; Claude owns full
suite and private runs. Same-exchange control modes are on the preceding review tip.
Per-surface within-mode results remain pending sufficient ordinary-use coverage;
no request for test messages. Heartbeat ACTIVE; no completion/routine ntfy.


## 2026-11-09 — Numerical judge candidates and randomized latent-feed diagnostics

Coordination #42–43: assessed all 31 subconscious entries plus deviation and voice
coherence, with input/scorer/failure-mode/proposed synthetic test for each in
experiments/nonllm-judges/README.md. Implemented two offline components: unique
original-act/day recurrence for reviewed topics, and complete-link candidate groups
from supplied frozen cached vectors. Complete indirect lineage, exact hashes,
mode/surface/source/day scope, input bounds and explicit unknown/exclusion behavior
are preserved. No automatic yearning, scar, resolution, duplicate-removal or identity
verdict. No runtime wiring, existing feed change or additional model call.

17 isolated prototype checks and 11 ownership checks pass. Synthetic aggregate CLI
verified. Generated reports refreshed unchanged and diff clean. The stress driver
in experiments/latent-feed-diagnostics/stress.py ran the unchanged latent-feed suite
50 times in fresh workers with recorded randomized orders, five time zones and four
available locales: 750/750 checks pass in 29.422 seconds inside the local isolation
boundary. Log: /tmp/judges-latent-stress.log. This does not reproduce or fix the
historical flake. The original traceback is unavailable; the reviewer will retain
future failures. No assertion was weakened and no speculative production fix made.

Full isolated suite/private character4 provenance review stays with Claude; runtime
format compliance and per-surface results still need ordinary-use evidence. No
private records, live writes, GPU/model/encoder/provider calls, merge or deployment.
Exact pushed tip is in the coordination reply. Heartbeat ACTIVE.


## 2026-11-09 11:14 CST — offline voice familiarity and sustained drift (#44)

Added experiments/nonllm-judges/voice_drift.py on codex/judges-voice-drift-prototypes
above 71193c5702e3cd85de5262b0bb07eed2863d1c43. Reuses character-reference metric
functions with exact cached text/vector/encoder bindings and complete original-act
lineage admission. Known mode and surface are separate; target day and all future
days are excluded from its reference. Calibration leaves each reference day out,
weights days equally, and emits an empirical familiarity percentile with an inclusive
0.2–0.8 abstain band. It is not an identity probability or a quality verdict. Sparse
or degenerate coverage stays unscored. A rounding repair keeps identical features
tied despite floating-point arithmetic.

Drift needs four consecutive calendar days beyond the held-out baseline maximum
plus an explicit distance margin. A single outlier cannot flag sustained change.
Persistence alone does not update the reference. An exact, externally owner-reviewed
adoption receipt can simulate replacing the scoped reference for later days only;
stale, unbound, nonpersistent, family-derived or adjacent-rule adoption evidence
cannot promote itself. Private version/membership receipts retain the transition;
public output is aggregate only. No writes or runtime integration. README states
the experimental thresholds, unverified source/adoption claims, lack of real-world
calibration and how changes can be adopted without a self-scoring feedback loop.

123 isolated checks pass: new voice/drift 23, existing character-reference 72,
existing numerical candidates 17, ownership 11. Logs: /tmp/judges-voice-drift-tests.log,
/tmp/judges-voice-character-tests.log, /tmp/judges-voice-candidate-tests.log and
/tmp/judges-voice-owners.log. Generated reports refreshed unchanged; diff clean.
No private records, model/encoder/provider calls, live writes, model changes, GPU,
merge or deployment. Full suite/private character4 investigation stays with Claude.
The latent-feed full-suite-interaction hypothesis is still unconfirmed: the earlier
50-run pass did not identify a root cause. Exact pushed tip is in the coordination
reply. Heartbeat ACTIVE; no completion/routine notification.


## 2026-11-09 11:34 CST — witnessed humor and textual taste (#45)

Added experiments/nonllm-judges/witnessed_facets.py on
codex/judges-witnessed-humor-taste above 85ec09076ea4628fe069405dded620b65d9b3f08.
Humor accepts only owner haha-plus reactions exactly joined to the adjacent exchange
or exact joke ID/hash-bound 4–5 star practice ratings. Unknown/lower/unrated outcomes
never become negative labels. Duplicate observations cannot multiply positive acts;
conflicting reaction adjacency refuses. Original-act lineage and cached-feature
provenance checks are reused, including indirect influence exclusion.

References share mode, surface and item kind. Both reference acts and observed
positive feedback must predate the entire target local day. Two or three positive
days produce similarity only, with no empirical calibration and an abstain status;
four days permit the reused held-out rank. Coverage exposes total supplied positive
acts/days and actual available references per scope. A synthetic three-positive case
shows the sparse limit; no real positive records were read or copied. Similarity
never promotes itself to an anchor and never claims probability of success.

Taste source verified in code: scripts/landings.py record (line 185) via
bin/server_domains/landings.py POST /api/landings. Only exact-bound landed ratings
anchor this variant. It accepts textual messages/jokes/journals; image/song/video
caption features remain unsupported. The private Landings store is never read,
imported or wired into his context. No suitable aesthetic-save source was verified;
call transcript saves and generated taste profiles are not substituted. This is
familiarity to owner-positive examples, not a measurement of his own taste.

126 isolated checks pass: new facets 20, reused voice/drift 23, character-reference
72, ownership 11. Logs: /tmp/judges-humor-taste-tests.log,
/tmp/judges-facet-voice-tests.log, /tmp/judges-facet-character-tests.log and
/tmp/judges-facet-owners.log. Required reports regenerated unchanged; diff clean.
Source/owner/adjacency/cache claims remain explicitly unauthenticated by the offline
prototype. No private reader, new model/encoder/provider call, live write, model swap,
GPU, merge or deployment. Full review/suite/private evaluation remains with Claude.
Exact pushed tip is in the coordination reply; heartbeat ACTIVE.


## 2026-11-09 11:46 CST — private numerical CLI (#46)

Added experiments/nonllm-judges/run_private.py on codex/judges-private-run-cli
above b88537ce273896290d2ebf4fdedaac98d02d5145. Accepts the character-reference
projection and an optional exact positive-only Landings projection, both read-only.
Reuses attribution/mode/cache preparation; keeps primary and window30 views separate.
Runs voice/drift and humor/taste facets. Foreign-control work stays independent.
No real store reader, discovery, model/encoder call, reference writeback or live use.

Supplemental numerical_evidence carries complete lineage, original-act bindings,
encoder freeze time and explicit facet attempt/anchor declarations. Older projections
without these still produce coverage/unscored output; the adapter never fabricates
clean ancestry, positive outcomes or a historical encoder pin. Missing prerequisites
can legitimately produce zero scores. This is documented, not hidden or backfilled.
Landings must be an already authorized projection; no Landings store is opened.

Caller selects private JSON and public summary filenames in one new scratch output
directory. Repository/live paths, symlinks, existing outputs and nonprivate scratch
are refused. Existing audit guard confines writes and forbids network/subprocesses.
Inputs are immutable, output directory 0700/files 0600, failures sanitized. Private
report retains numerical receipts, supplied model/provenance fields and input/code
fingerprints; no recorded label is promoted to known serving evidence. Public output
is counts-only with per-mode/surface coverage and flagged date ranges, no numeric
scores, means, model names, IDs, hashes, text or vectors. Unknown positive counts
are null when outcomes cannot be assessed.

144 isolated checks pass: CLI end-to-end 18, facets 20, voice/drift 23, character
reference 72, ownership 11. Logs: /tmp/judges-private-cli-tests.log and
/tmp/judges-cli-{facet,voice,character}-tests.log, /tmp/judges-cli-owners.log. Tests
include actual synthetic drift dates, missing lineage/freeze, indirect influence,
view separation, input immutability, path/privacy refusals and receipt retention.
Required reports regenerated unchanged; diff clean. No private data, GPU, paid call,
model swap, merge or deployment. Full review/private Aegis run belongs to Claude.
Exact pushed tip is in the coordination reply. Heartbeat ACTIVE.


## 2026-11-09 12:06 CST — retained numerical evidence builder (#47)

Added experiments/nonllm-judges/build_evidence.py on codex/judges-evidence-builder,
stacked above 7014046e. It consumes the character importer projection and optional
read-only lineage, recorded cache-metadata and humor-draft projections. Original
provenance/generation/fallback/merge fields remain intact; existing numerical
evidence is refused rather than overwritten. Full strict witness admission, exact
final nodes and complete indirect ancestry are required before graph normalization.
Any denial in another copy still denies the act. Private normalized nodes retain
full validated ancestry and raw projection/hash receipts.

Encoder pin and freeze come only from exact cache input/context/encoder bindings.
All prepared caches must agree before the runner's global metadata is emitted.
The existing character cache format does not require a freeze timestamp; no writer
for historical freeze evidence was established. Missing metadata is a documented
coverage gap, never filled from a revision, mtime or a current artifact observation.
Humor requires explicit row/draft joke_id plus full draft text equality. Standalone
drafts without timed row identity remain unjoined. No positive/taste anchor inference.
README names source fields and provides the coverage/unknown table and projection
contracts. No raw-store adapter, encoder call, deployment manifest or runtime change.

Scratch-only CLI preserves immutable inputs; new 0700 output directory, 0600 files,
no repository/live paths or symlinks, no overwrite, sanitized errors, network/process
audit guard. Public output is counts/availability/fixed reasons only; all source
claims remain independently unverified. Historical results belong to the reviewer.

225 isolated checks pass: builder 15, runner 18, strict witness 109, character 72,
ownership 11. Logs: /tmp/judges-evidence-builder-tests.log and
/tmp/judges-builder-{runner,witness,character,owners}-tests.log. Required reports
regenerated unchanged; diff clean. Full Aegis suite, test merge and private-copy run
remain with the reviewer. No private data, new model/provider call, GPU, model swap,
live write, merge or deployment. Exact branch/path/pushed tip in coordination reply.
Heartbeat ACTIVE; no completion/routine notification.


## 2026-11-09 12:44 CST — private cache producer (#49)

Note #49 resolves the producer-location question: character caches were made in
the reviewer's private run, not by any live cache. Added the separately invoked
experiments/character-reference/encode_cache.py on codex/judges-private-cache-producer
above b998be9d. No shared HTTP/self-head/present-moment cache or reply path changed.

Explicit GGUF is copied exclusively to a new 0700 scratch output directory, fsynced,
made 0400, hashed there and stamped with actual copy-completion time. Only the copy
is loaded by the installed in-process local embedding runtime. Full hash checks
around load and after encoding, plus file identity/change-time checks around every
call, refuse mutated/replaced/restored-but-touched copies. CPU offload disabled; no
download or subprocess fallback. Exact full reply/context strings, no prefix or token
truncation; flat finite nonzero vectors normalized to L2. Pooling is caller-explicit.
Runtime package version/settings and exact per-input encoding clocks are private.
Native backend version stays unknown; Python audit is not a native-code OS sandbox.

Produces fresh character-input.json, cache.json, directly consumable
encoder-cache-metadata-v1 cache-metadata.json and counts-only counts.json (0600).
New encoder ID binds artifact/runtime/settings. All source rows/provenance/merge
fields retained, original inputs/cache untouched. Existing outputs/copies, symlinks,
repository/live paths, old numerical evidence and nonempty control caches refused.
Errors and native output cannot expose private paths through ordinary CLI output.

Migration: no metadata backfill or vector relabelling. Real copy time may follow
historical reply times; builder/numerical freeze-before-act gates stay intact.
Fresh historical encoding therefore remains unscored under that prospective gate.
README explicitly separates that limitation from a retrospective-policy decision.

135 isolated synthetic checks pass: producer 19, builder 15, character 72, runner 18,
ownership 11. Logs /tmp/judges-cache-{producer,builder,character,runner,owners}-tests.log.
Required reports regenerated unchanged; diff clean. Stub encoders/tiny synthetic file
bytes only; no actual model, real GGUF, package install, private record, GPU, provider
call, live write, merge or deployment. Real runtime compatibility/private execution
belongs to the reviewer. Exact pushed commit/path/branch in coordination reply.
Heartbeat ACTIVE; no resumed/completion notification.


## 2026-11-09 13:05 CST — reviewed published-artifact freeze (#50)

Added encoder_freeze.py and an empty reviewed published-encoder-pins.json registry.
Producer defaults to actual copy-time freeze; explicit published_artifact requires
external_pretrained plus a reviewed exact-file hash/revision/date pin, with no
subject training. Missing/mismatched/unreviewed pins, local-trained qualification,
future revision relative to copy, and malformed registries refuse before encoding.
Actual copy completion and encoding clocks remain recorded; effective freeze alone
uses the reviewed publication date. No network or production registry override.

Builder and numerical runner revalidate qualified receipts against their checked-in
registry and preserve them privately. Summaries separate copy_time,
published_artifact, legacy_unknown and unknown; mixed sources cannot form a global
encoder. Legacy supplied timestamps retain their prior semantics and explicit
unknown source. Published revisions after scored acts remain unscored. Existing
strict lineage, indirect influence, mode, anchor and calibration gates are intact.
Policy/pin-file hashes join private manifests. READMEs explain review, schema,
private invocation and differing source-count denominators. No actual pin invented.

148 isolated synthetic checks pass: producer 32, builder 15, runner 18, character 72,
ownership 11. End-to-end stub producer -> builder -> runner scores synthetic acts
with a reviewed placeholder pin; refusals include missing pin at downstream stages,
hash mismatch, subject/local training, missing/tampered receipts and mixed sources.
Logs: /tmp/judges-published-{producer,builder,runner,character,owners}-tests.log.
Required reports regenerated unchanged; diff clean. No real encoder/model/provider
call, private record read, live write, GPU, merge or deployment. Real pin review and
private run remain with the independent reviewer; full Aegis suite remains theirs.
Branch codex/judges-published-encoder-freeze, based on bae1abde. Exact pushed commit
and checkout path in the coordination reply. Heartbeat ACTIVE; no routine ntfy.


## 2026-11-09 13:10 CST — reviewed pin and numerical judge status (#51)

Recorded the external artifact pin supplied in coordination note #51, including
exact public file hash, full revision, conservative revision date, declared byte
size and reviewer attribution. Verification belongs to that reviewer; no download,
model load or independent network/hash verification was performed in this change.
Registry parsing now accepts validated optional reviewer/size_bytes metadata without
relaxing required pin, training, date or hash gates. All metadata stays in receipts.

Added experiments/nonllm-judges/STATUS.md: six new components, explicit inputs,
offline versus private-run-ready versus missing capture state, and Gloria's later
capture prerequisites. Recurrence/grouping are standalone prototypes, not part of
the private-run CLI. The dedicated production shadow sink exists and defaults off;
receipt capture does not wire numerical scorers into live consumers. Source status
is distinguished from live verification. Existing character/innovation work remains.

44 isolated checks pass: producer/pin 33, ownership 11. The new check parses the
actual checked-in pin, checks its hash shape/revision/date/reviewer, exercises pure
qualification without loading weights, and rejects malformed optional metadata.
Logs /tmp/judges-reviewed-pin-tests.log and /tmp/judges-reviewed-pin-owners-tests.log.
Required reports regenerated unchanged; diff clean. No private data read, encoder
or provider call, GPU, live config/write, model swap, merge or deployment. Full suite
and private runs remain with the reviewer. Branch codex/judges-reviewed-pin-status,
based on 84eebed5; exact path/pushed tip in coordination reply. Heartbeat ACTIVE.


## 2026-11-09 13:26 CST — review fixes and remaining flake diagnosis (#52/#53)

Raised the existing narrator response ceiling from 220 to 284 to reserve 64 tokens
for interval metadata. One existing generation call/model chain remains; synthetic
backend regression retains 220 narration token units plus the interval suffix.
This is a contract fixture, not a provider-tokenizer or live narration measurement.
Private cache producer now gives typed encoder_runtime_unavailable with a fixed
approved-install hint on ImportError, never installation or private path disclosure.
Note #53 reports the owner's install approval is being handled by the reviewer.

Deterministic before/after failure evidence:
- Followthrough: a writer-induced backwards clock reproduces the exact invalid
  finalization stack. A valid parsed decision now continues with an explicit
  unavailable capture record, real start/final clocks and no witness_receipt.
  Persisted observations stay intact; duplicate invocation uses the decision once.
  Strict Capture clock checks are unchanged; no timestamp clamp or invented receipt.
- Spool: startup waited for a queue timeout, and continuous volatile work could starve
  durable ingress indefinitely. Added bounded recovery before the first queue wait
  and every 250 ms by monotonic scheduling even while busy. Tests exercise real
  scratch spool publication before the first get and 9 records across the 8-record
  recovery bound with busy queue traffic. Original recovery deadline/assertions stay.
  This proves/fixes scheduling gaps; the retained idle-startup timeout alone does
  not establish why its particular run exceeded two seconds.

Latent original omission remains unresolved: there are no concurrent heading and
trained-context writers in test_09's synchronous call path. A backwards clock
reproduces the same missing-context symptom through the correct future-packet gate,
but the old log has no rejected-gate/timestamp evidence to attribute that run.
Added optional content-free rejection diagnostics and exact-call test assertion
context. Default callers still get empty text/empty receipt on refusal, so no
false latent grounding is propagated. No causality gate or assertion was weakened.
100 repeated test_09 runs passed; deterministic backwards-clock regression preserves
the heading, refuses future evidence, and includes context once the clock catches up.
Reviewer input needed: retain the new reason from the next isolated failing run.
One needs-input ntfy delivered; deduplicate this unchanged issue. Do not claim the
original latent or idle-spool flake root cause established by these tests.

209 targeted checks pass (producer 34, latent 16, intervals 12, followthrough 55,
spool 27, capture 27, sink 26, owners 11, coarse-clock wrapper 1 with 68 nested
followthrough/completion checks), plus 100 diagnostic integration repetitions.
Before logs /tmp/judges-review-followthrough-before.log and
/tmp/judges-review-spool-before.log retain deterministic failing evidence.
After logs /tmp/judges-review-{producer,latent,somatic,followthrough,spool}-after.log,
/tmp/judges-review-test_{witness_capture,witness_sink,want_coarse_clock}.log,
/tmp/judges-review-owners.log and /tmp/judges-review-latent-diagnostic-stress.log.
Reports regenerated unchanged; diff clean. Original coarse-clock and Lab flake
causes are not declared solved; coarse-clock passed this targeted rerun.
No real provider/model call, private input read, GPU, live change, merge or deployment.
Branch codex/judges-review-fixes above 3fb175ce; exact tip/path in coordination reply.
Heartbeat ACTIVE; independent full suite/test merge and private runs remain with
Claude Code. Owner deploy/capture decisions in #53 were not executed by this agent.


## 2026-11-09 14:09 CST — note #54 prospective joins and coverage

Branch codex/judges-prospective-coverage, above review tip 457c85fc. Exact pushed
commit/path are recorded in the designated coordination reply. New ledger entries
call joke_fermentation.reply_binding for an exact full-reply match to one
unambiguous retained draft, adding only ID/hash metadata. Both deployed ledger
spellings remain identical. No prefix/rewrite/offer attribution, extra generation,
draft writes, delivery attestation or historical backfill. The app/rated-callback
route is not guaranteed to deliver the whole draft: missing joins remain unknown.
Canonical overlaps retain existing bindings only on exact turn/surface/text/hash
agreement across all ledger copies. Other merge/provenance fields are preserved;
the numerical evidence builder rejects supplied conflicting joke hashes/bindings.

New experiments/nonllm-judges/capture_report.py reads owner-private explicit packet
files and prints only dates/counts/shares/fixed labels. Includes daily packets,
unique reply denominators, selected provider-reported identity, complete lineage,
strict original-act bindings, and separate freeze sources. Packet-only mode is
explicitly not assessed for numerical scoring; it does not invent delivery,
complete context, vectors or references. Optional existing prepared-input/Landings
projections run the pure existing offline evaluation, restricted to exact matching
packet-admitted acts, with separate primary/window30 views. Recurrence/grouping
remain not evaluated (no retained adapter); drift counts replies in assessed daily
windows, not shift verdicts. Refuses unsafe roots, symlinks, nonprivate files,
malformed/oversized inputs and mismatched projections. No network/subprocess/file
writes in the report; no encoder load. README and STATUS describe limits/usage.

100 targeted isolated checks pass: humor binding 6, capture report 18, numerical
builder 16, merged chat 31, humor/taste 12, humor ownership 4, entry owners 11,
ledger dates 2. Logs /tmp/judges-prospective-test_*.log and
/tmp/judges-humor-builder-tests.log. Required reports regenerated unchanged;
diff check clean. All fixtures synthetic and senders blocked/stubbed. No actual
model/provider call, private records, GPU, live write, merge or deployment.

Original latent/idle-spool and remaining flake attribution is still unresolved;
#54 accepts the clock analysis as candidate mechanisms and the reviewer will
retain numeric deltas on the next failure. No claim that those roots are fixed.
Independent full suite, private capture run and test merge remain with the reviewer;
Gloria deploys/enables. Heartbeat ACTIVE. No new unresolved issue or routine alert.

Final merge compatibility check: a nonstring legacy turn ID bypasses the new binding lookup without failing the existing merge. Added a regression; humor binding suite is now 7 checks, total 101 targeted checks.
