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
Traversal memoizes node standing and checks every edge's clock independently;
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

Innovation percentiles use only strictly earlier finalized outcomes from this
same replay and matching group. Same-time outcomes cannot calibrate each other.
The default minimum is 20 earlier outcomes; until then the percentile is null.
A percentile is relative prediction error, not calibrated confidence in identity.
No comparator superiority is claimed: baseline vectors are not yet supplied.

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

`bin/gen_result.py` preserves observed response model metadata separately from
the compatibility `model` field, which existing callers may fill from config.
Configured names never become observed identity. The router's optional observer
receives stage results without changing its return tuple or fallback behaviour;
observer errors do not interrupt the reply. Raw result text is used only for
transient selection hashes; capture copies no provider reason/tool text.
Selection by raw text is accepted only when exactly one observed attempt
matches. Identical text from multiple attempts remains unknown, even when their
model labels agree; explicit selected-attempt identity is still future work.

Capture is disabled by default. The optional sink requires
`JUDGES_CAPTURE_SCRATCH` and `SPARK_WORKSPACE` to name the same existing, resolved,
owner-private scratch directory. Live-store paths, symlinks, repository paths and
their ancestors are refused. Each packet is a new mode-0600 file; there is no
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
