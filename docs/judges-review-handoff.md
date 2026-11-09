# Judges observation and character-reference handoff

Current candidate: **codex/judges-character-encoder-pin**, based on
**bc5d784d**, whose prototype stack is rebased onto **34b662e9** per note #30. Its final published hash is recorded in
the dated local coordination reply. The reviewer reports integration through
c779cbf0 (deploy 650/650, live 653/653; note #32); this is not an independent
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
