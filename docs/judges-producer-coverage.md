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
