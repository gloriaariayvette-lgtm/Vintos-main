# Offline character-reference prototype

This is an instrument for **familiarity relative to a provisional reference**, not
an authenticity probability, moral verdict, truth detector or live judge. It was
requested in coordination note #29. New receipt work is paused while this instrument
is evaluated. No existing loop, model, feed, admission rule or live store changes.

The runner consumes an explicit private history copy and cached frozen embeddings.
It does not load/download an encoder, fit a projection, call a model, read live
stores, or discover backups. The encoder contract is supplied evidence; matching
cache IDs/hashes do not attest the actual encoder weights or runtime. The requested
reference encoder family is enforced in the input contract. Missing vectors stay
missing. There is no substitute text embedder or silent fallback.

## What it measures

- **Reference selection:** owner-user messages with explicit event IDs are counted
  once per local day. Candidate days reach the top-quarter count threshold and
  exceed the median of observed active days. Ties are included. These are proposed,
  unconfirmed dates, selected without looking at the familiarity results. Calendar
  days without supplied events are not invented as zero-activity days.
- **Day-held-out familiarity:** each evaluation day is excluded from reference and
  calibration. A day is scorable only with at least two other reference days.
  Semantic similarity is maximum cosine to daily reference centroids. Percentiles
  use reference-only leave-one-day-out calibration; no point is its own anchor.
  This is retrospective cross-validation, not a prospective time-forward test.
- **Controls:** all-reference and last-two-reference-day centroids, and a nine-field
  style-only distance (standardization uses reference rows only). The style fields
  are log character/word counts, mean word length, question/exclamation/comma rates,
  uppercase-letter fraction, first-person word rate and newline rate. These are
  descriptive and partly language/genre sensitive, not identity features.
- **Foreign/other-surface comparisons:** explicitly paired control rows must have
  the same supplied language, half to twice the reply length, and context-vector
  cosine at least 0.7. These fixed screening rules are proxies, not certified topic
  matching. Other-surface text is not automatically foreign/non-him. Report paired
  win rates separately for semantic, style and both centroid controls.
- **Shuffle check:** permuting his held-out replies preserves their marginal
  familiarity distribution, so its marginal semantic AUC should be 0.5. Context
  alignment against a cyclic within-day permutation is reported separately. Do not
  sell response-only familiarity as a shuffled-pair detector.
- **Humor/taste facet:** similarity to reference replies with exact-linked,
  witnessed `haha` repetitions or 4–5 ratings. Feedback requires the same reply ID
  and response hash, an explicit exact-reply link, and a post-reply timestamp before
  cutoff. Feedback on the held-out day is excluded from its positive reference.
  Missing/nonpositive feedback is never a flop label. A positive rating is not proof
  that a reply was humorous; the output is `witnessed_positive_similarity`.
- **Model context:** fixed model-family strata, plus differences on evaluation days
  shared by both families. This does not assert model invariance; inspect the
  differences and uncertainty. Unrecognized models remain `other`, absent ones
  `unknown`; no model is changed.

Means weight evaluation days equally. Intervals use 1,000 deterministic day-bootstrap
resamples (seed 17); fewer than two days yields no interval. These are descriptive
intervals on supplied days, not guarantees for new settings. Control observations
are matched pairs; reference/coverage counts are not strict-eligible turns.

## Historical evidence policy

The existing attribution engine is run against the supplied ledger. Primary
experimental rows need a ten-second or exact-ID ledger match, or a recorded label
agreeing with an independently observed response-model label. Label conflicts are
held out. A recorded label alone does **not** establish agreement. The separate
30-second view is sensitivity only. Strict witness admission is never relaxed.

Reply IDs and exact response hashes bind cache entries and feedback. Duplicate
copies collapse; conflicting reply versions or cache records fail the run. Repeated
reply text across different days counts only at its earliest occurrence so it cannot
leak through the day split. All these rules are prototype choices recorded by its
version, not learned acceptance thresholds.

## Private input contract for the copied-history run

One JSON object, with only these sources explicitly assembled by the reviewer:

| Field | Required content |
| --- | --- |
| `input_kind` | `synthetic` or `retained_snapshot`. |
| `timezone` | Explicit IANA timezone for day grouping, e.g. `America/Chicago`. |
| `encoder` | `family: "nomic"`, immutable `id`, exact `revision`, `pooling`, `normalization: "l2"`, integer `prefix_chars`, `frozen: true`. |
| `rows` | History copies with explicit `role`, `turn_id`, offset-aware/numeric `timestamp`, and `content`. User rows must be the owner's messages from the declared scope. Assistant rows also carry `surface`, `language`, exact `context` text, and existing attribution fields such as `served_by`/provider IDs. Preserve final-response receipt fields where present. |
| `historical_attribution` | Existing attribution configuration: explicit `surface_callers`, `window_seconds: 10`, optional source/timezone mapping, and `compute_ledger` records. The runner enables the independent window30 diagnostic. |
| `embeddings` | Each cache entry has `reply_sha256` for full final text; `input_sha256` for its encoder prefix; `context_sha256`; matching `encoder_id`; unit `vector` and `context_vector` with one shared dimension. Context and response features stay separate. |
| `feedback` | Optional exact-linked records: `reply_id`, `reply_sha256`, `link: "exact_reply"`, `witnessed: true`, `timestamp`, `kind: "laugh"` with string `value`, or `kind: "rating"` with numeric `value`. Unlinked reactions are excluded. |
| `controls` | Optional `kind: "foreign"` or `"other_surface"`, `matched_reply_id`, `content`, `context`, `language`, `encoder_id`, `input_sha256`, `context_sha256`, unit `vector` and `context_vector`. Supply provenance-reviewed controls; do not invent foreign status from a model/surface label. |

Limits: 64 MiB input, 10,000 history/cache/feedback records, 4,096 admitted unique
replies and control records, vectors at most 8,192 dimensions. No real data belongs
in this public repository. Raw messages, cached vectors and row-level evaluations
stay in the reviewer's private scratch copy.

```sh
# Use an existing 0700 private scratch directory outside the checkout.
SPARK_WORKSPACE=/private/scratch python3 experiments/character-reference/prototype.py \
  --scratch /private/scratch --input /private/scratch/copied-input.json \
  --output /private/scratch/new-character-run --cutoff 2026-11-09T12:00:00Z
```

Use the actual reviewer's scratch path and intended exclusive cutoff. Paths must
stay inside that scratch, without symlinks. Output must be new. The inherited offline
guard forbids network/subprocesses and confines writes to the output directory.
Outputs are mode 0600 in a 0700 directory:

- `aggregate.json`: fixed facets, strata, uncertainty, exclusions, and candidate
  dates plus message/reply counts. No text, private IDs, model labels, or vectors.
- `private-evaluation.json`: held-out reply IDs, percentiles and reference-day
  membership, for verifying splits locally. Do not publish it.
- `private-run.json`: input/code fingerprints and cutoff, for reproducibility.

## Validation and current boundary

49 isolated checks pass: prototype 12, existing attribution 26, ownership 11.
Synthetic fixture: 16 days, 32 replies across two labelled families, four candidate
reference days. All 32 are held out by day; deliberately separated foreign vectors
score a paired semantic win of 1.0, while shuffled own semantic marginal AUC is 0.5.
These are mathematical fixture checks, **not findings about his character/history**.
Tests cover no-day leakage, nonreference evaluation independence, exact feedback,
primary/sensitivity separation, controls, duplicates/conflicts, encoder/input
contracts, insufficient reference days, interval determinism and scratch-only CLI.

The actual-history result and actual candidate dates are **not yet produced**. Claude
can now assemble the explicit cache bundle above and run it on the private copied
history. Missing cached embeddings/controls must be reported as coverage gaps; no
encoder is silently loaded here. Gloria can then confirm/veto the actual proposed
dates. No approval is needed to continue other authorized prototype implementation.
