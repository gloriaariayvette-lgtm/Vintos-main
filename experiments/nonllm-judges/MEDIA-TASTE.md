# Proposed media-taste facet — existing vectors only

Status: offline design and pure synthetic acceptance prototype, not a deployed judge.
`media_taste.py:assess` accepts supplied objects, performs no I/O and calls no encoder.
It is not connected to the runner, UI, Landings, a cron, or his context. No calibration
claim or taste-profile comparison is implemented. That comparison awaits Gloria.

## Evidence contract

The independent private run reported 10 Landings items: four videos, three songs,
three text items, zero text anchors. This establishes a coverage gap, not a measured
media preference model. The existing media index (`scripts/media_embed.py:index`,
`_hit`) supplies kind, full file SHA-256, model, dimension, encoding time and vector.
Its displayed `art:` handle is a truncated digest; titles and paths are mutable.
Use `sha256:<full 64-character file digest>` plus kind as revision identity. Never
join by caption, filename, title, time proximity, nearest vector or truncated ID.

A future snapshot adapter needs an independently supplied exact mapping from each
Landings surface/ref to the rated byte revision, creation/delivery receipt and
existing embedding row. A current file's digest does not prove what she rated in
the past. Missing or changed bytes, conflicting receipts or unknown creation times
remain unsupported. A song task with multiple tracks must identify the actual
rated track/version; no automatic pooling of its alternatives. The current Landings
media records do not provide all of this: no historical binding is asserted here.

The prototype consumes a normalized, already bounded contract, not raw private
stores: items have media_id, sha256, kind, created_at, encoded_at, encoder and vec;
ratings have unique id, media_id, at, value and binding=exact_media_revision.
That marker is a supplied claim, not authentication. A production adapter must
retain source-record hashes, original-act/delivery provenance, mapping receipts,
clock evidence, input/code fingerprints and exact cache-row identity. Metadata
must accompany the original vectors; it cannot be reconstructed from a model name.
No text, vectors, private IDs, hashes or paths leave the private run. Public output
is counts and aggregate documentation. The prototype returns diagnostic numbers
and counts only; `source_claims_verified=false` remains explicit.

## Encoder freeze

EmbeddingGemma's vector width or model string cannot establish a frozen encoder.
Do not mix its space with another encoder merely because dimensions agree.
Qualify the exact artifact manifest (weight files, tokenizer, processor and relevant
configuration), runtime/preprocessing recipe, frame sampling/audio excerpt recipe,
and the per-row encoding receipt. The artifact SHA-256 denotes that immutable
manifest; any component/recipe change requires a separately qualified space.

Two admissible routes, matching the existing judges policy:

- `copy_time`: the recorded actual private copy time of the exact artifact is the
  effective freeze. It must strictly precede every original act used. Local or
  subject-trained variants may only use this route. No current copy timestamp can
  qualify an earlier original act or retroactively attest an old cache.
- `published_artifact`: a separately reviewed registry pin for the exact external,
  pretrained, non-subject-trained artifact may supply its publication freeze date.
  Keep actual copy time and the registry receipt hash. Check artifact, publication
  date and qualification against the independent registry; a self-declared model
  name/date is insufficient. This task adds **no published pin**.

The prototype accepts a caller-supplied reviewed pin mapping and tests these gates;
a production adapter must use the existing independently reviewed registry and
receipt validation, not accept a registry uploaded alongside an untrusted cache.
Current raw media rows lack this full contract. They remain unqualified until
original cache provenance can establish it. No new encoding, cache relabelling,
weights copying, service call or GPU job is authorized by this design.

## Measurement and temporal separation

Freeze an explicit reference cutoff no later than candidate creation. Admit only
ratings and reference encodings strictly before it, and original acts no later
than their rating. All clocks must have explicit offsets. For each exact revision,
the latest prior rating wins: partly/missed cancels a prior landed mark. Equal-time
conflicts abstain; duplicate IDs/rows add no weight; contradictory duplicate IDs
or revisions abstain. Candidate byte identity cannot be its own reference.

Separate image, video and audio pools. Exclude call audio, film frames, sealed
Atelier work and motifs from this initial contract. Even with a shared encoder,
source sampling and modality differences make cross-kind thresholds unjustified.
Require at least three distinct landed revisions on two UTC rating dates as a
conservative design floor, not a calibrated sufficiency claim. Unrated and missing
items supply no negatives. Selected ratings are not representative of all work.

Normalize finite, nonzero, exact-width vectors and report mean and maximum cosine
to the eligible positive reference set, with reference/day counts. These describe
similarity to previously landed media; they do not predict whether a new piece
lands, establish personal identity, prove quality, or supply a binary verdict.
No learned weights or threshold, cross-modal averaging, negative extrapolation,
automatic anchors, feedback writes or preference-profile comparison is added.
Malformed, sparse, mixed-encoder, late-freeze or ambiguous evidence abstains.

## Prospective text binding delivered with this design

`scripts/landings.py:record` optionally adds `reply_binding` only on a new rating.
It requires the frozen whole message/joke/journal text to agree with the existing
`made` field and exactly match one retained reply turn ID in the interaction ledger
or canonical assistant rows. Identical copies of the same ID are deduplicated;
multiple IDs, a matching row without ID, or one ID with different bytes abstains.
No prefix matching, whitespace/marker stripping, timestamp join, client-supplied
ID, generated ID or old-rating backfill. Binding contains schema, turn ID, full
UTF-8 SHA-256 and fixed source label; no extra text copy. Media captions cannot bind.

Both sources are bounded at 8 MiB/50,000 rows; malformed, inaccessible or oversized
present sources abstain, even if another source contains a match. Absent files are
allowed. Matching establishes uniqueness within retained sources only; pruning
prevents any claim of global historical uniqueness. Ratings remain functional
when binding fails. Missing original identity stays missing. Parent rating time
and existing frozen data remain unchanged. The existing projection still requires
an independently supplied original-act binding and its provenance/time gates; the
new stamp is an input to verification, not automatic anchor admission or proof of
clean generation, delivery, actual served model or fallback.

## Synthetic acceptance

`broker/tests/test_landings.py` checks private store isolation, exact persisted
binding, source preservation, canonical/ledger deduplication, assistant-only input,
ambiguity, byte changes, invalid IDs, surface boundaries, bounds and malformed
inputs, fail-open recording and no historical backfill.
`broker/tests/test_media_taste_contract.py` checks exact full revision joins,
angle-sensitive similarity, latest-rating cancellation, cutoff isolation, duplicate
and conflicting evidence, sparse/day/kind gates, invalid vectors, missing cache
provenance, freeze qualification and mixed encoders. File access and sockets are
forbidden around every media assessment. Fixtures are entirely synthetic.

Next: independent review of this contract; any private execution/adapter and UI
integration require their own scoped handoff. Claude owns full isolated integration
validation; Gloria owns deployment. Existing loops, feeds and models are unchanged.
