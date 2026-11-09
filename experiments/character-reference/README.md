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
  differences and uncertainty. An additional comparison pairs recognized families
  one-to-one within the same day and language, with reply-length ratio 0.5–2 and
  context cosine at least 0.7. Each left reply in stable ID order selects the
  highest-cosine available right reply (ties by right ID), without looking at
  familiarity/style outcomes. This deterministic greedy assignment is not an
  optimal matching. Reuse is forbidden within each family pair but allowed across
  different family-pair comparisons. It reports paired percentile differences for
  all four facets, context similarity, matched/unmatched counts and day intervals.
  No pairs means unknown, not zero difference or evidence of invariance. Only
  recognized families enter this view; pooled `other`/`unknown` stay in the ordinary
  strata. Supplied context similarity is a topic proxy, and reply length is an
  outcome of generation: these are descriptive associations, not causal effects.
  Reference-family composition is reported per candidate day and per actual
  held-out fold, separately for primary and sensitivity views, including zero
  coverage. This exposes imbalance without automatically balancing or changing
  the reference. Unequal composition may explain apparent family differences.
  Unrecognized models remain `other`, absent ones
  `unknown`; no model is changed.

Optional **evaluation groups** expose the review's benign novelty, refusal,
opposite-stance, humor and surface-shift checks. Explicit annotations must link
an admitted reply ID and exact full-response hash. Reports keep declared owner and
reviewer annotations separate, with counts of scored/unscored examples and all four
facet percentile summaries/intervals. Groups can overlap. They are retrospective
metadata, never inputs to reference selection, calibration, admission, matching or
scores. A humor annotation does not supply witnessed positive feedback. No labels
are inferred from text/model, and no missing annotation becomes a negative. These
summaries support checking whether low familiarity accompanies tolerated changes;
there is no identity verdict, pass rate or new acceptance threshold. Annotator
identity and category correctness are supplied claims, not authenticated evidence.

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
| `evaluation_annotations` | Optional list of exact-linked `reply_id`, `reply_sha256`, `link: "exact_reply"`, `annotator: "owner"` or `"reviewer"`, and `category` in `benign_novelty`, `refusal`, `opposite_stance`, `humor`, `surface_shift`. Duplicate annotations collapse. Unlinked/not-admitted examples are counted as unavailable. No rationale or free text is emitted. |
| `controls` | Optional `kind: "foreign"` or `"other_surface"`, `matched_reply_id`, `content`, `context`, `language`, `encoder_id`, `input_sha256`, `context_sha256`, unit `vector` and `context_vector`. Supply provenance-reviewed controls; do not invent foreign status from a model/surface label. |

Limits: 64 MiB input, 10,000 history/cache/feedback/annotation records, 4,096 admitted unique
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

- `summary.md`: readable aggregate tables for coverage, candidate dates, primary
  and sensitivity facets, family comparisons and supplied evaluation groups.
  Missing measurements are explicitly unknown; overlapping views are never added.
  Synthetic input is prominently labelled as a fixture, not a real-history finding.
  Only fixed labels, finite numbers and validated date strings are rendered.
- `aggregate.json`: fixed facets, strata, uncertainty, exclusions, and candidate
  dates plus message/reply counts. No text, private IDs, model labels, or vectors.
- `private-evaluation.json`: held-out reply IDs, percentiles and reference-day
  membership, for verifying splits locally. Do not publish it.
- `private-run.json`: input/code fingerprints and cutoff, for reproducibility.

## Validation and current boundary

Current follow-up: 36 isolated checks pass (prototype 25, ownership 11). The base
prototype also passed the 26-check attribution suite before this scoring-only
addition; attribution code and admission are unchanged.
Synthetic fixture: 16 days, 32 replies across two labelled families, four candidate
reference days. All 32 are held out by day; deliberately separated foreign vectors
score a paired semantic win of 1.0, while shuffled own semantic marginal AUC is 0.5.
These are mathematical fixture checks, **not findings about his character/history**.
Tests cover no-day leakage, nonreference evaluation independence, exact feedback,
primary/sensitivity separation, controls, duplicates/conflicts, encoder/input
contracts, insufficient reference days, interval determinism and scratch-only CLI.
Context-comparison regressions cover shared-day/topic confounding, one-to-one
assignment, outcome-independent matching, order stability, language/length/day
bounds, tie-breaking, empty comparisons and aggregate privacy. Evaluation-group
tests prove complete existing-score parity, exact links, separate annotators,
primary/window30 separation, unscored coverage, empty intervals, bounded categories,
private-rationale exclusion and independence from witnessed-positive feedback.
Summary tests cover actual 0600 CLI output, deterministic rendering, unknown
measurements, source-type labels, rejected malformed dates and private-field exclusion.
Reference-composition regressions check held-out-day exclusion, family-count
conservation, primary/sensitivity differences and zero coverage without imputation.

Reference means/scales/centroids are built once per held-out day, calibration day
and witnessed-positive subset, then reused for replies and controls. Reuse is
limited to the current evaluation call; there is no persistent cache or encoding.
Differential tests compare every aggregate and private evaluation result exactly
against the original per-reply formula, including cancelling/degenerate vectors.
A synthetic fixture stays at 92 statistic builds after evaluation replies and
controls are multiplied; this is an operation-count check, not a host timing claim.

Claude reports a first private copied-history run in note #32: the primary set
was unscored (38 replies on one day); the 30-second view scored 123 replies across
36 days, but had no provenance-reviewed controls and an unverified encoder
revision. These are reviewer-reported exploratory results, not independently
reproduced here or validation of identity. Engagement surface completeness,
reviewed controls, reference-family balance and exact encoder identity remain open.
The bundle contract above supports the next private run. Missing cached embeddings/controls must be reported as coverage gaps; no
encoder is silently loaded here. Gloria can then confirm/veto the actual proposed
dates. No approval is needed to continue other authorized prototype implementation.
