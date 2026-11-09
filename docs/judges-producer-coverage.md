# Remaining producer evidence in witness slices 1 and 2

Source review, 8 November 2026, against `d22d4032`. No live reads, model calls,
installation or runtime measurement. This extends the offline contract work;
it does not authorize capture enablement or replace any existing loop/feed.

## What the existing records establish

| Producer boundary | Evidence present | Evidence still missing |
|---|---|---|
| `inner_context._run` (`scripts/inner_context.py:41`) | Renderer name, offered/no-material/error state, rendered length and short influence identifier | Full rendered-version digest, its exact location in a particular router invocation, and the generated material's own parents |
| `inner_context._note_offers` (`scripts/inner_context.py:23`) | Context-local selection ID/version; existing persisted offer records | Binding to the authenticated turn and each final request; a selection is not itself admission |
| `turn_record.record` (`scripts/turn_record.py:89`) | Marker presence in the supplied prompt snapshot, selected influence IDs and existing turn provenance | Complete rendered boundaries and final router-input identity; its marker/excerpt observations cannot prove a full ancestry chain |
| Avatar turn-record call (`bin/server.py:10843`) | A system-prompt snapshot before history/current-message assembly finishes | Later transformations: for example the conditional assignment at `bin/server.py:10984` occurs after this record |
| Scratch request capture (`scripts/witness_capture.py:134`, invoked by `bin/server.py:11004`) | Exact handler system/messages/parameters fingerprint per invocation, ordered input hashes, retry/result dependencies | Producer-to-fragment bindings for generated context; provider wire transformations and internal attempts remain outside this boundary |
| Scratch selection capture (`scripts/witness_capture.py:113`) | Existing offer metadata, explicitly labelled offers-not-admission | Whether that offer's exact version appears in this invocation; known generated parents/effects are not supplied |

These are different observations at different times. Do not relabel the earlier
turn record as a final-request receipt or infer admission from a familiar marker.
This is a source-level coverage finding, not evidence that a particular live
reply lost or received any block.

## Next implementation increment: exact generated-fragment bindings

1. Retain a bounded, context-local rendering manifest while assembling the
   existing output. Assign the same selection identity to metadata and the
   ephemeral exact rendered fragments. Do not add text to existing offer stores,
   call a renderer twice, or change its output. Absent/failed/older producers
   supply unknown evidence. Clear the local manifest between assemblies.
2. Consume that manifest only in the already opt-in scratch capture path.
   Bind selection identity explicitly; do not load the latest on-disk offer file
   or join by a time window. Copy immutable metadata at capture start so later
   renderer activity cannot rewrite an earlier invocation's evidence.
3. At each actual router invocation, compare the producer's rendered version
   against that invocation's system text. Record a full fragment digest, whole
   input digest, exact span and request identity only for an unambiguous match.
   Distinguish missing, changed and ambiguous material where the evidence permits;
   a missing substring alone cannot distinguish omission from rewriting. History
   copies and retries cannot inherit a system-slot binding after movement/editing.
4. Keep generated-fragment nodes incomplete until the producer supplies all
   upstream dependencies. An exact match proves content presence, not independent
   authorship, causal effect on the reply, provider consumption or clean ancestry.
   Existing known effect markers must survive; missing parents stay unknown.
5. Persist hashes/spans/identities only in private scratch packets. The manifest's
   transient text must not appear in diagnostics, public reports or Git. Capture
   failures must preserve ordinary response generation and existing admission
   side effects. Never repoint production's workspace to activate observation.

Acceptance uses synthetic renderers and captured requests: exact/moved/edited/
repeated fragments, changed retries, two interleaved context-local assemblies,
missing or old producer APIs, exceptions during rendering/observation, and
byte-equivalent output with capture off. A capture-to-replay fixture must retain
unknown ancestry and delivery after successful fragment binding. No new model
calls are needed. Independent Aegis suite/review remains with Claude Code.

## Work after fragment binding

Generated-parent receipts must be emitted at the producer reads that actually
contributed, including value-map dependencies and intervening effects; a static
list of possible inputs is insufficient. Separately, trusted client-delivery
acknowledgement must bind the exact finalized response/version; framework return
remains unconfirmed. Neither gap is solved by relaxing the strict census.

Keep the already submitted offline repairs fixed while implementing this next
increment on a new branch. Production destination/retention/enablement remains
the separate [disabled proposal](judges-capture-enable-proposal.md). Installation
and live acceptance must not be inferred from a reviewed branch.


## Implementation follow-up: rendered fragment bindings

`codex/judges-rendered-fragment-bindings` implements the bounded context-local
manifest and per-invocation system matching above, with hashes/spans in scratch
packets only. Limits are 64 retained fragments / 262144 Unicode codepoints per
assembly; this is partial coverage, not an enumeration of every prompt producer.
Exact missing fragments report `not_found`, never an inferred omission reason.
Identical offers from multiple organs and repeated occurrences are ambiguous.
Generated parent chains, client delivery and production enablement remain open.
The source locations above describe the d22d4032 review baseline, not new line
numbers after this implementation.


## Implementation follow-up: guarded reads inside renderers

`codex/judges-renderer-read-receipts` adds opt-in context-local observation to the
existing `store_guard.load_json` return path and binds its metadata to the renderer
that was executing. This records actual reads instead of a static list of possible
inputs, without reopening stores or rerendering. One synthetic integration uses
the existing compact causal self-model renderer against a scratch store.

Read edges are conservative: individual fields' contribution is not established.
Only guarded JSON reads are covered. Direct file reads (including the value map's
own generation input assembly), cached/in-memory source history and trusted client
acknowledgements remain unfinished. Neither generated material nor its stored
parents becomes complete or clean merely because its hash is known. Version and
resource digests remain private scratch metadata, never public measurement rows.


## Implementation follow-up: main-chat value-map source binding

`codex/judges-value-map-read-binding` covers the value-map read outside
`inner_context` in the main-chat handler. Its already-read decoded document is
hashed at the read boundary; the existing newest-entry/strip/1500-codepoint
selection is checked explicitly. The handler binds that observation to its
existing `Your value map` block before routing. Per-invocation matching then
records exact presence, absence or ambiguity, including retries and later prompt
changes. The original source is not reopened and its text is not persisted in
the receipt. An earlier entry changing remains visible in the document hash even
when the selected newest entry is identical.

This identifies the stored version and deterministic selection, not the map's
upstream generating prompt, model or causal effects. The map node and stored
parent remain incomplete. Other surfaces' value-map reads are not covered by
this main-chat increment. Optional observer failures preserve both the existing
block and any otherwise working capture; production enablement remains separate.


## Implementation follow-up: value-map call boundary

`codex/judges-value-map-call-receipts` observes the generator's existing HTTP
payload before the call and its returned response afterward. Private metadata
records exact input/output hashes, response-reported identity when available,
and explicit failure/rejection outcomes. It neither introduces a model call nor
turns a configured model into served identity. The three existing deployed source
copies stay identical, and the private atomic sink is shared with chat capture.

These are per-call receipts, not a complete generated-artifact graph. Build-local
selection among drafts, final entry/file-write bindings, upstream source ancestry
and backend internal attempts remain unfinished. Completed call receipts exclude
interrupted calls and cannot establish complete attempt coverage. The offline
chat census does not ingest these as assistant turns. No live-data run is claimed.


## Implementation follow-up: build selection and entry-close boundary

`codex/judges-value-map-build-bindings` adds explicit build/stage identities around
the existing calls, declared synthesis dependencies and the actual branch's final
selection. After successful entry writes and close, private metadata records that
entry's hash and append/replace mode. It does not assert whole-file identity,
atomicity, durable storage or completion of archive/cache side effects.

Bindings require one entered stage, one published successful call, an exact
returned hash and causal clocks. Missing/duplicate/truncated evidence remains
unavailable while generation continues. Unchanged-context, rejected, interrupted
or write-failed builds have no completed-entry receipt. Cross-process writer/read
resource-version joins and complete upstream ancestry remain unfinished; no
private snapshot census was rerun here.


## Implementation follow-up: diagnostic write/read comparison

V2 writer/read observations share hashed lexical resource locators and full
stripped-entry hashes. The optional offline bundle diagnostic retains all causal
matches and separates aggregate coverage from private candidate IDs. Legacy
missing identities remain unavailable; malformed/conflicting writes abort.
This closes an observational comparison gap, not cross-process origin proof:
path reuse, copied bytes and unobserved writes remain possible. No read node gets
a writer parent and no turn becomes eligible from this comparison. Full source
ancestry, effect dependencies and delivery remain open. No private rerun here.


## Implementation follow-up: direct assembly reads

The value-map gather function observes its existing direct file reads and binds
the bounded assembled context to each actual request's user slot. It does not
reopen files or change assembly, model calls or outputs. Every read remains
stored_unknown_ancestry; read-set coverage does not establish contribution after
filtering/truncation. Failed opens, directory selection, evidence-view internals,
separate system/temporal reads, cached material and source/effect history remain
outside this increment. Production capture and eligibility are unchanged.


## Implementation follow-up: auxiliary producer inputs

Identity and temporal reads now have their own bounded scopes and per-request
slot bindings. Their returned text is distinguished from source content; fallback
identity has unavailable read evidence, and empty text cannot match every prompt.
This covers those two reader boundaries without completing their upstream history
or granting eligibility. Evidence-view internals, cached material, source/effect
history, trusted delivery and production enablement remain separate work.


## Implementation follow-up: evidence-view return path

The value-map consumer now observes the returned ledger/history view or existing
raw/empty fallback. Bounded canonical view hashes and explicit marker counts
record what returned, without reloading sources, normalizing away missing
permissions or altering filtering. View internals' raw source versions and
ancestry remain unobserved; empty views do not prove empty/readable stores.
Known returned influence markers remain visible as counts, not causal proof
that every returned row reached or affected the generated map. No eligibility
or production enablement changes.


## Implementation follow-up: offline producer linkage checks

Replay can now compare explicitly supplied build/call receipts by their declared
IDs, stages, hashes, publication/outcome records and causal clocks. Synthesis
selection and draft links are counted separately; missing records remain missing
without alternate text/time matches. This is a diagnostic of supplied receipts,
not complete ancestry, served-model verification or admission. No producer or
live path changed in this increment.


## Implementation follow-up: on-message self-forecast inputs

The anchored self readout now has an optional scoped observation of its actual
recent-own input list; the existing job publishes a private sidecar only after
its forecast-log close. Separate normalized-reply and truncated encoder-input
hashes preserve the actual 400-codepoint transform. Missing IDs stay missing.
Observation/prediction mismatch, duplicate observations and legacy paths remain
unavailable. Captured exchange clocks are not promoted to reply-finalization
clocks, and source identity/encoder identity/complete ancestry remain unknown.

The old offline control receipt expects full reply versions. These new observations
use a separate schema and are not silently attached to that contract. Subsequent
work must validate explicit origin identities, exact transformation and compatible
cached vectors, then bind a declared evaluation block. No replay scoring or witness
eligibility changes in this increment; no live capture has been enabled.


## Implementation follow-up: observed-input baseline join

The optional offline `self_input_controls` bundle now joins sidecars to exact
selected forecast hashes and cached first-400-codepoint vectors. Explicit admitted
prior IDs/full reply versions, matching prefix hashes, encoder compatibility and
causal finalization order are required. This first version supports normalization
only when it left full final reply bytes unchanged. Other normalization remains
unavailable, without text/time-nearest substitution. Supplied nonoverlapping blocks
keep descriptive pairs separate; declarations do not certify preregistration.
The old census and innovation output are unchanged. No actual snapshot rerun or
production capture enablement is included; authenticated origins, complete ancestry
and delivery still require their own evidence.


## Implementation follow-up: original source clocks

The self forecast's ledger/chat adapters now preserve explicit numeric or aware
source clocks only during a scoped scratch forecast, before legacy formatting.
Metadata follows the actual earliest-time merge, while text-source priority stays
unchanged. A separate private sidecar binds that observation to the exact saved
forecast and context-clock string. Unknown source clocks remain unknown; this is
exchange timing, not finalization or authenticated origin. The old forecast/input
receipt shapes remain unchanged. Replay consumption and production enablement are
separate; no historical conversion or live-data measurement is included.

## Implementation follow-up: private self artifacts

On-message forecasts now retain a same-byte checkpoint metadata/hash observation
and already computed recent-own feature vectors in the optional private sink.
Anchored self ranking audits retain existing encoded self-text inputs, including
all bounded source references for prefix collisions. No extra encoder invocation,
new schedule or change to forecast/audit output. Other-head instrumentation is not
added. See the replay README's private artifact contract.

Coverage remains explicit: selected recent-own vectors and audit-encoded inputs,
not every finalized target. The current ranking adapter drops turn IDs; those stay
null. Training completion and encoder-weight identity are unobserved; file dates
and configured labels do not fill them. Replay promotion/final-version joins and
prefix-versus-full-target comparability remain open. Production enablement and full
Aegis validation remain separate review steps.

## Implementation follow-up: source identity through the audit adapter

The source-ID loss noted above is now addressed for newly scoped reads. Existing
ledger/chat adapters observe raw and normalized reply hashes plus original string
ID/surface, and the ranking adapter retains these optional observations. They follow
the merger's preferred text source, not an earlier duplicate's clock; missing IDs
are never backfilled. Existing ranking fields, deduplication and scores are unchanged.
The private artifact refs now include optional reply_source; old packets remain
incomplete. Finalization/authentication and strict replay joins are still open.
