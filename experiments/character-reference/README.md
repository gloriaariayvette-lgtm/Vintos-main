# Offline character-reference prototype

This is an instrument for **familiarity relative to a provisional reference**, not
an authenticity probability, moral verdict, truth detector or live judge. It was
requested in coordination note #29; mode and surface stratification follow notes #33–34. New receipt work is paused while this instrument
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
  calibration. References match the reply's independently labelled mode and
  surface; a day is scorable only with at least two other days in that same stratum.
  Unknown mode or surface stays unscored; no pooling fallback fills the gap.
  Semantic similarity is maximum cosine to daily reference centroids. Percentiles
  use reference-only leave-one-day-out calibration; no point is its own anchor.
  This is retrospective cross-validation, not a prospective time-forward test.
- **Controls:** all-reference and last-two-reference-day centroids, and a nine-field
  style-only distance (standardization uses reference rows only). The style fields
  are log character/word counts, mean word length, question/exclamation/comma rates,
  uppercase-letter fraction, first-person word rate and newline rate. These are
  descriptive and partly language/genre sensitive, not identity features.
- **Foreign/other-surface comparisons:** reviewed paired controls or a reviewed
  candidate pool must have
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
- **Mode first:** `opening_everyday`, `intimate`, or `unknown` from supplied
  exact-linked observations of a router decision, intimate state or a documented
  conversation transition. Never derive mode from the serving model, a bare model
  switch, text keywords or missing logs. Unknown/conflicting mode stays unknown.
  Each reference, calibration, positive-feedback subset and control comparison
  matches mode. Reference rows and cross-family matched pairs also match surface.
- **Within-mode family checks:** compare recognized families only within a known
  mode, same surface/day/language, reply-length ratio 0.5–2 and context cosine at
  least 0.7. Stable ID order chooses the best available context match, with no
  outcome-based pairing and no reuse within a family pair. This is deterministic
  greedy matching, not optimal matching or causal identification. No matched
  overlap is explicitly `not_identifiable`, never invariant. Model-family means
  and unconditioned differences remain diagnostic JSON fields marked with their
  interpretation; pooled differences are confounded with mode and omitted from
  the readable summary. `per_mode` supplies separate facets and comparisons.
- **Surface and reference composition:** preserve explicit ReelRoom separately
  from avatar, even though both use the same router caller. Engagement counts
  deduplicate owner events and retain fixed surface totals; conflicting/missing
  surface labels stay unknown. Reference-family counts are reported for candidate
  days and actual held-out mode/surface folds, separately in each attribution view.
  No automatic reference reweighting or changes to the engagement-day selection.

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
| `encoder` | `family: "nomic"`, immutable `id`, exact `revision`, `pooling`, `normalization: "l2"`, integer `prefix_chars`, `frozen: true`; optional `artifact_sha256` (64 lowercase hex) for an expected artifact hash. |
| `rows` | History copies with explicit `role`, `turn_id`, offset-aware/numeric `timestamp`, and `content`. User rows must be the owner's messages from the declared scope. Assistant rows also carry `surface`, `language`, exact `context` text, and existing attribution fields such as `served_by`/provider IDs. Preserve final-response receipt fields where present. |
| `historical_attribution` | Existing attribution configuration: explicit `surface_callers`, `window_seconds: 10`, optional source/timezone mapping, and `compute_ledger` records. The runner enables the independent window30 diagnostic. |
| `embeddings` | Each cache entry has `reply_sha256` for full final text; `input_sha256` for its encoder prefix; `context_sha256`; matching `encoder_id`; unit `vector` and `context_vector` with one shared dimension. Context and response features stay separate. |
| `feedback` | Optional exact-linked records: `reply_id`, `reply_sha256`, `link: "exact_reply"`, `witnessed: true`, `timestamp`, `kind: "laugh"` with string `value`, or `kind: "rating"` with numeric `value`. Unlinked reactions are excluded. |
| `evaluation_annotations` | Optional list of exact-linked `reply_id`, `reply_sha256`, `link: "exact_reply"`, `annotator: "owner"` or `"reviewer"`, and `category` in `benign_novelty`, `refusal`, `opposite_stance`, `humor`, `surface_shift`. Duplicate annotations collapse. Unlinked/not-admitted examples are counted as unavailable. No rationale or free text is emitted. |
| `mode_observations` | Optional list with exact `reply_id`, `reply_sha256`, `link: "exact_reply"`, `timestamp` at/before the reply and before cutoff, `mode` in `opening_everyday`, `intimate`, `unknown`, `source` in `router_decision`, `intimate_state`, `conversation_transition`, and a 64-lowercase-hex `evidence_sha256` of the retained observation. Conflicting modes become unknown. Source content remains private. This binds supplied evidence; it does not authenticate the exporter or infer a label. |
| `controls` | Optional paired list; provenance fields below are required; each entry requires explicit matching `mode`, `kind: "foreign"` or `"other_surface"`, `matched_reply_id`, `content`, `context`, `language`, `encoder_id`, `input_sha256`, `context_sha256`, unit `vector` and `context_vector`. Supply provenance-reviewed controls; do not invent foreign status from a model/surface label. |

| `control_pool` | Alternative to nonempty `controls`: up to 4,096 reviewed candidate records with the same cache/provenance fields, without `matched_reply_id`. Selection uses context only. |

Limits: 64 MiB input, 10,000 history/cache/feedback/annotation/mode-observation records, 4,096 admitted unique
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

- `reader-summary.md`: a short plain-language page generated only from aggregate
  values. It separates primary and sensitivity coverage, marks unmeasured values,
  explains percentiles and uncertainty, and distinguishes familiarity from identity.
  Synthetic runs are prominently labelled. It is preparation for the private
  rerun, not a claim that real coverage has already returned.
- `summary.md`: readable aggregate tables for coverage, candidate dates, primary
  and sensitivity facets, family comparisons and supplied evaluation groups.
  Missing measurements are explicitly unknown; overlapping views are never added.
  Synthetic input is prominently labelled as a fixture, not a real-history finding.
  Only fixed labels, finite numbers and validated date strings are rendered.
- `aggregate.json`: fixed facets, strata, uncertainty, exclusions, and candidate
  dates plus message/reply counts. No text, private IDs, model labels, or vectors.
- `private-evaluation.json`: held-out reply IDs, percentiles and reference-day
  membership, for verifying splits locally. Do not publish it.
- `private-controls.json`: every selected pair, including unscorable and sensitivity-only
  pairs; target/candidate IDs, content/review hashes and context cosine. Local only.
- `private-run.json`: input/code fingerprints, cutoff, exact declared encoder
  contract and optional observed artifact hash/byte count, for reproducibility.
  Raw revision/encoder IDs, hashes and paths are not printed in public summaries.

## Preparing reviewed controls locally

Schema v3 enforces the review requirement for both explicit pairs and pools.
Legacy paired controls without review evidence are excluded, not silently treated
as foreign. The selector does not collect text, generate examples, encode anything,
contact another service or examine live stores. The private reviewer supplies
existing authorized records and cached vectors; unavailable controls stay unknown.

Each candidate adds `candidate_id` (nonempty, at most 256 characters), `timestamp`
(the source text's offset-aware creation time, strictly before cutoff), `surface`,
`author`, and `review` to the fields in the table. Known control surfaces use the reply surface vocabulary plus `slack`, `moltbook`
and `journal`. These extra labels apply only to controls; they do not expand the
engagement/reference surface scope. `foreign` requires `author: "non_subject"` and the
same surface as the target. `other_surface` requires `author: "subject"` and a
*different* known surface. This second comparison measures his surface change;
it is not a negative authenticity label. Both need the same explicit known mode.
Do not derive authorship or mode from the serving provider, words, or filenames.

The `review` object requires `reviewed: true`, `reviewer: "owner"`, `"reviewer"` or `"store_authorship"`,
`link: "exact_control"`, `evidence_sha256` (64 lowercase hex identifying the locally
retained source evidence), and `binding_sha256`. Compute the last using
`control_review_binding(candidate)` after reviewing the source: it hashes the
canonical JSON of `candidate_id`, `content`, `context`, `timestamp`, `kind`,
`author`, `mode`, `surface`, and `language`. Changes to those fields invalidate the
review. The review source and any intimate text stay local; never paste them into
a cloud prompt. This is a supplied reviewer claim with an exact binding, **not**
an authenticated author/source assertion. A hash alone cannot verify the claim.
`store_authorship` means the private importer/reviewer supplied retained store
metadata as its authorship evidence. It is not a human review, independently
verified authorship, or a mode label. It needs the same exact binding, evidence
hash, explicit author and mode as other classes. Unknown classes remain excluded.
Selected source surfaces and reviewer classes are reported separately as counts;
private pair records retain those labels. No source paths or store IDs are exported.
Cache contract and prefix/context hashes are checked separately.

Pool selection is deterministic greedy matching: primary-attributed targets first,
then sensitivity-only targets, with target ID order inside each group. For each
kind, choose the remaining candidate with greatest context cosine (at least 0.7),
tie-breaking by candidate ID. Language must agree and character length ratio must
be 0.5–2. Response embeddings, familiarity/style scores, family, feedback and
reference-day membership do not choose the match. No candidate text is reused;
there is at most one pair per target/kind. This is not optimal maximum matching;
order can leave otherwise matchable targets uncovered. Explicit pairs have the
same review/matching/reuse requirements, but are supplied by the reviewer.

All input assistant text, including unattributed/unscored rows, is excluded from
the control pool. Exact candidate copies collapse; conflicting candidate identity
or text provenance fails. Missing/stale reviews and unmatched candidates appear in
coverage. `control_selection.by_mode_surface` reports admitted, matched and
unmatched counts for each control kind. These are selection counts, not scored
observations: the primary/sensitivity metric counts show what was actually scored.
The views overlap and must not be added. Candidate IDs/hashes and full pair mapping
are restricted to private artifacts. Existing own-reply reference scores do not
change merely because a control is absent.

## Pinning a known encoder artifact without loading it

The private run manifest now retains the exact supplied revision, pooling,
normalization, prefix contract and encoder ID. A revision label remains declared,
not independently verified. To observe bytes, optionally add
`--encoder-artifact /private/scratch/encoder-copy.gguf` using an explicitly retained
regular artifact copy inside the same private scratch. No model directory is
scanned, download started, endpoint queried or encoder loaded. The reader hashes
in 1 MiB chunks, accepts 1 byte through 4 GiB, refuses symlinks/nonregular files and
observable mutation/size disagreement, and writes no artifact bytes to output.

If `encoder.artifact_sha256` is supplied, observed bytes must match it or the run
fails before creating its output directory. Without that field, supplied bytes
are observed but not checked against an independent expected hash. Without an
artifact file, an expected hash remains a declaration. With neither a file nor an expected hash, identity stays unknown. The aggregate summary emits only these fixed evidence states.
`revision_verified` and `cache_derivation_verified` remain false: one artifact
hash neither proves the revision label nor authenticates the origin of cached
vectors, runtime/tokenizer settings, or completeness of a multi-file model.
Do not backfill a hash observed today as evidence of yesterday's encoder.

## Validation and current boundary

Schema v2 requires mode evidence for scoring; legacy bundles without it remain
admissible but their replies are unscored (`mode_unknown`). No model label serves
as fallback. Intimate rows and per-reply outputs must remain in local private
scratch; export only aggregates. No cloud prompts or external annotation calls.

Current follow-up: 45 isolated checks pass (prototype 34, ownership 11). The base
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
Mode tests prove no family fallback, exact/dated evidence binding, conflict-to-unknown,
mode/reference isolation, within-mode identifiability, ReelRoom separation and
matching-mode controls. All new fixtures remain synthetic and non-intimate text. Encoder-pin tests cover
unknown/declared/observed/verified states, mismatches, bounds, symlinks, observed
mutation, private contract retention, outside-scratch refusal and aggregate privacy.

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
reviewed controls, mode conditioning and exact encoder identity remained open.
Gloria clarified in note #33 that low counts are expected: avatar and ReelRoom
are the main surfaces. The missing-surface hypothesis is withdrawn. The ten dates
reported by Claude remain provisional; this implementation does not change them.
Note #34 explains the family/mode confound; the earlier pooled family difference
must not be interpreted as a model effect.
The bundle contract above supports the next private run. Missing cached embeddings/controls must be reported as coverage gaps; no
encoder is silently loaded here. Gloria can then confirm/veto the actual proposed
dates. No approval is needed to continue other authorized prototype implementation.


## Existing signal paths for the private exporter

`bin/server.py:10374` keeps ReelRoom distinct from avatar; the same surface reaches
post-turn handling at `bin/server.py:11376`. `bin/server.py:1513` passes the surface
and turn ID into writers; `scripts/interaction_ledger.py:548` retains both.
Use the ledger's explicit surface rather than deriving it from `router:avatar`.

`bin/server.py:11109` has a separate intimacy gate before a refusal-driven reroute.
Its temporary result is not a universal stored mode label. `bin/model_router.py:663`
also has forced/toggle routes for provider choice; those route names alone do not
identify conversation mode. `scripts/intimate_stream.py` preserves typed local
observations (measured events, choices, readings and system state); presence of a
file or a physical event is not automatically a label for every contemporaneous
reply. The private exporter must bind actual retained evidence to an exact reply,
record its mapping, and emit unknown where that link or meaning is unavailable.
This runner does not read those stores or create new gate/latent-model calls.
