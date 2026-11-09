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
  conversation transition, then privately reviewed bounded somatic intervals. The
  explicitly enabled historical owner family rule is a labelled fallback, never
  independent evidence. Bare switches, keywords or missing logs are not observations.
  Unknown/conflicting evidence stays unknown and blocks lower-priority fallback.
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
Runtime failures exit nonzero with a fixed JSON error label and an allowlisted
exception class. They do not print exception messages, tracebacks, malformed field
values or source paths. Imported analysis functions still raise exceptions for
local debugging; do not export those raw exceptions. A failed write can leave a
partial private output directory; `written: false` is not a successful run and
that directory must not be treated as a complete report. Argument-parser usage
errors remain standard CLI usage messages; do not put secrets in CLI arguments.
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
Mode tests prove no implicit family fallback, exact/dated evidence binding, conflict-to-unknown,
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

## Prospective mode evidence

The server can now retain `mode_receipt` beside `generation_join` in its existing
history/canonical rows and in the existing background interaction-ledger writer.
This is a passive observation of the already executed gate, not a new classifier,
mode switch or retrospective inference. It remains active when shadow capture is
off. No new file, queue, sender or model call is added; decision observation only
updates request-local memory. Existing history writers keep their timing, and the
ledger receives the bounded JSON via its existing background process environment.

`turn-mode-decision-v1` contains existing turn/request IDs, surface, a receipt ID,
start/decision times, normalized mode and fixed basis, optional refusal-guard
reroute decision time/reason, the evaluated and selected completion IDs, and raw/stored
response hashes. It contains no prompt, reply, gate answer, model name or vector.
Exact YES maps to intimate; exact NO to opening_everyday. Ambiguous output, gate
failure before a decision, and a skipped gate stay unknown. The existing routing
condition is preserved even if an ambiguous answer contains YES; that cannot
become a known mode merely because a reroute occurred. A later refusal-check
failure does not erase a completed gate decision. A manual provider toggle does
not establish an intimate mode.

The evaluated completion may be the refused first reply while the selected
completion is the replacement. Both IDs remain explicit. A reroute decision is not proof that the replacement
succeeded; after a failed attempt the selected ID can remain the original. History can include
device marks absent from the ledger's reply, so each sink has its own exact stored
text hash. Invalid/missing identities or a selected-response mismatch omit the
receipt. Writer/import validation rejects extra fields, inconsistent labels,
invalid timestamps and wrong turn/surface/text bindings. These are provenance
checks, not cryptographic authentication of a source.

For a private future export, retain `mode_receipt` and `generation_join` on the
original history row plus the matching compute-ledger completion. The prototype
validates the stored response hash, turn, surface, request, selected completion,
raw response hash and cutoff directly. A valid prospective receipt takes priority
over all historical labels, including when its mode is unknown. Invalid supplied
receipts also stay unknown; they cannot silently become family labels. Missing
receipts allow historical evidence. These checks bind supplied metadata, not
cryptographic authentication. The receipt can be created after the request's
history timestamp; it is bound by completion identity rather than nearest time.
The gate's coverage limitation remains visible in the
[plain-language status](../../docs/judges-character-status.md).

## Historical mode evidence for the third private run

Set `historical_family_fallback: true` only for the owner-approved historical run.
Default is false. Priority is (1) bound prospective receipt, (2) existing independent
exact-linked mode observations, (3) reviewed somatic intervals, (4) owner rule,
(5) unknown. The owner rule maps known `grok` family to `intimate` and known `claude`
family to `opening_everyday`; other/unknown families remain unknown. Every admitted
row has `mode_source`. No prompt, model call or keyword classifier is added.

Source inspection, not private-data inspection:

- `scripts/somatic_narrate.py` reads up to the previous 24 hours, then writes
  `memory/somatic-narrated.json` with `through`, `at`, and `narration` (200-character
  prefix). It seeds `source: somatic` / `thread` via `emoclaw_utils.seed_thread`
  into `memory/unfinished-threads.json`. These are overwriteable/current records,
  not proof that a complete historical archive exists.
- Neither the current narration record nor the seeded thread stores the start/end
  of the identified stretch. `through` is the last input turn, not a session end;
  `at`/thread timestamp is recording time. A nonempty narration does **not** label
  the entire preceding day intimate, nor does an empty record identify an everyday
  interval. The old `PAD = 120` declaration is not used by the current narrator main.
- `somatic_bridge.py` writes pending `{dur, ts, ...}` and session-end events, but
  device activity alone does not supply a narration-derived conversational label.
  No bridge/motor signal is silently promoted into this source class.

The private importer may supply up to 4,096 `somatic_marks`. Each needs:

| Field | Contract |
| --- | --- |
| `mode` | `intimate` or `opening_everyday`, explicitly reviewed against retained evidence. |
| `source_field` | `somatic-narrated.json:narration` or `somatic_thread:thread`. |
| `source_record_sha256` | SHA-256 of the retained original record bytes; retain bytes privately. |
| `start`, `end`, `observed_at` | Explicit offset-aware/numeric timestamps; `start <= end <= observed_at < cutoff`. The review may be retrospective. |
| `surface` | One known history surface; never infer all surfaces from one narration. |
| `join`, `session_id` | `session_window` requires the same explicit nonempty session ID on the history row; `surface_window` requires null session ID and matches only the stated surface/time. |
| `review` | `{reviewed: true, reviewer: "owner" or "reviewer", binding_sha256: somatic_review_binding(mark)}`. Binding covers all fields above. |

Join window is **[start, end], inclusive, zero padding, maximum 7,200 seconds**.
This cap is a conservative prototype admission limit, not a claim about actual
session duration. The private reviewer supplies the actual narrow interval; do
not manufacture it from the scan window. A missing start/end is counted as an
unbounded mark and contributes no mode. Overlong/out-of-cutoff marks are counted
and excluded. Session conflicts on copied rows fail; overlapping marks that disagree
make the reply unknown and block family fallback. Supplied review bindings do not
authenticate a reviewer or establish objective intimacy ground truth.

Public coverage reports somatic-covered and conflicting replies, comparable
family-rule labels and disagreements, unresolved/unmatched marks, and final source
counts. Both summaries show source counts, including sensitivity admissions.
Per-mode views and reference folds retain aggregate source composition.
Private evaluation retains source/evidence hashes; retain the original input bundle
and evidence bytes alongside its private-run hash for full reconstruction. No
session IDs, content, source-record hashes or review bindings enter public output.

Family-labelled rows may contribute descriptive familiarity within their assumed
mode. They cannot establish cross-family stability: family comparison excludes any
scored target labelled by the rule **and any target whose reference fold includes
rule-labelled replies**. Exclusion counts are explicit; comparisons without remaining
independent overlap say `not_identifiable`. Historical somatic classifications are
still retrospective observations and should not be read as prospective mode accuracy.
Controls retain their separate reviewed authorship contract. The optional exact-exchange
binding below can inherit a conversation mode; the control author's family never supplies it. No golden-day change or new real-data result is
claimed here. The reviewer runs character3 privately; the existing status page
continues to describe character2 until actual aggregates arrive.


## Retaining mode labels when primary evaluation is unscorable

The CLI also writes `private-mode-assignments.json` (0600) for **every admitted
reply**, including unknown modes, sensitivity-only admissions and replies lacking
sufficient reference days. `private-evaluation.json` remains the scored primary
result; an empty evaluation file does not mean no mode labels were assigned.
The new file retains turn ID, full response hash, timestamp/day/surface, admitted
family, primary flag, attribution basis, mode/source and retained evidence hashes.
It contains no text, embeddings or session IDs. These identifiers/hashes still make
it private: never publish the file. It does not include excluded input replies.

Imported callers can pass `private_mode_assignments=[]` to `run`; this optional
collector leaves returned aggregate measurements and scored details unchanged.
It is populated after admission/deduplication and before evaluation, so reviewing
labels does not require recomputing scores or re-running preparation. Retain the
original input and evidence bytes with the input hash in private-run.json; this
file records normalized assignments, not independently authenticated source data.


Both summary renderers accept older schema-v3 aggregate reports that predate
source-labelled mode coverage. If their mode coverage lacks the
`family_fallback_enabled` recording-state field, source/somatic measurements are
shown as **not recorded/not measured**, never fabricated zeros. On newer reports,
absent sparse counter entries remain genuine zeros. Disagreement requires at least
one comparable label: zero comparable replies is **not measured**, while zero
disagreements among a positive number of comparable replies remains a measured zero.
Invalid recording flags and disagreement counts exceeding the denominator fail.


## Generate pages from an existing aggregate report only

For the character3 handoff, the reviewer can render both pages directly from the
returned schema-v3 `aggregate.json`. No private reply bundle, vectors, artifact
file, scoring or encoding is needed. With `TASK_SCRATCH` naming an existing separate
0700 private scratch directory (outside this checkout and live stores):

```sh
SPARK_WORKSPACE="$TASK_SCRATCH" python3 experiments/character-reference/prototype.py \
  --scratch "$TASK_SCRATCH" \
  --aggregate-report "$TASK_SCRATCH/character3/aggregate.json" \
  --output "$TASK_SCRATCH/character3-pages"
```

The new output directory contains only `reader-summary.md`, `summary.md` and
`render-manifest.json`, all 0600. The manifest records the exact input-byte and
renderer hashes, no source path. The source report is not copied or modified.
Only allowlisted labels/numeric aggregates and validated candidate dates reach
the pages; arbitrary metadata is ignored. The generated pages retain primary
versus sensitivity separation, source assumptions and unknown evidence. The
renderer does not independently verify the input's provenance or measurements.

`--aggregate-report` and `--input` are mutually exclusive. Aggregate rendering
rejects `--cutoff` and `--encoder-artifact`; it does not rerun evaluation or pin an
artifact. It reads at most 8 MiB, rejects symlink/out-of-scratch input/output and
existing output, and uses the same offline guard. Both pages must validate before
the output directory is created. I/O failures can still leave partial output; only
exit zero plus `{"written": true, "render_only": true}` is success. CLI failures
retain the existing fixed, sanitized error contract.

Evaluation mode still uses `--input`, `--cutoff`, and optional artifact verification
with its existing 64 MiB input limit and private outputs. Aggregate rendering is
not a new evaluation, a deployment or a claim that character3 has run. The public
status document remains on the last supplied real results until new aggregates
arrive.


## Same-exchange modes for foreign controls

Foreign owner or room-agent text can inherit the conversation mode of an admitted
adjacent subject reply. Supply `exchange` with exactly `link: "exact_exchange"`,
`reply_id`, `reply_sha256`, `control_sha256`, and `source_record_sha256` (64 lowercase
hex of retained exchange evidence). The private importer must establish the same
exchange from source records; **timestamp proximity is not sufficient**. The source
must be on the same known surface. All anchors and candidate timestamps precede
the cutoff. No interval or nearest-neighbor heuristic is used.

Use `mode: "unknown"` when the control has no separate mode observation. Recompute
`control_review_binding(candidate)` after adding `exchange`: the review now binds
that entire object as well as the existing fields. Existing candidates without an
exchange keep their previous binding. Broken, unreviewed, unknown-anchor,
wrong-surface or conflicting-mode links stay unknown; no family guess repairs them.
`other_surface` controls cannot use this mechanism. All ordinary cache, language,
length, context, authorship and no-reuse rules still apply.

Resolution happens before either explicit-pair validation or pool matching. A pool
candidate keeps its source exchange mode even if context matching chooses a different
target. It never borrows the target's mode just to become eligible. The input bundle
is unchanged. Selected private pairs retain `mode_source: adjacent_reply_rule` and
`mode_binding` with anchor ID/hash, original mode source and source evidence hash.
Public output contains only counts in `control_selection.exchange_modes` and
`selected_mode_sources`. Source adjacency is a bound supplied claim, not independently
authenticated by this experiment. Family-derived conversation labels permit a
conditional within-mode control comparison; they do not make the family comparison
identifiable or independently validate mode.


## Prospective somatic interval receipts

The existing narrator call can now append a final `SOMATIC_INTERVALS: [[first,last],...]`
line referencing the `[tN]` ordinals in that call's input. Narration instructions,
provider selection, temperature, output-token cap, schedule, input truncation,
thread feed and dedup cursor retain their existing behavior. The same call supplies
the optional metadata: no second classifier, retry, encoder or provider call is added.
The ordinal prefixes and metadata instruction add input tokens; there is no claim
that real provider output will satisfy this format until ordinary use supplies it.
Legacy narration still seeds normally. Missing or malformed bounds do not cause a
new call, suppress a valid narration, or manufacture an interval.

`intimacy_evidence` is added to the existing `somatic-narrated.json` record and to
`seed_thread(..., extra=...)`, so the existing thread/held-thread path retains it.
The snapshot remains a last-run cursor, not a permanent interval archive; thread
retention follows existing admission/retention behavior. No new store or timer.
The snapshot is written with mode 0600. Metadata schema is
`somatic-intimacy-intervals-v1`: status, observed time, input/response hashes,
requested model, provider-reported served model (unknown if absent), unknown fallback,
zero padding, interval bounds and source turn references. It contains no narration
or message text. IDs and hashes are still private and must not be published.

Only ordered, non-overlapping selections with explicit per-turn timestamps,
unique turn IDs, one known surface, at most two hours per interval, eight intervals
and 256 selected turns total are accepted. Each interval retains start/end,
input ordinals and each selected turn's ID, timestamp, source, role and text hash.
File-mtime fallback, legacy paired records without separate turn IDs, mixed surfaces,
duplicate IDs, future times, excessive spans and invalid indices yield
`invalid_bounds` with no partial intervals. `missing_bounds` is distinct from
`no_session`; NONE never labels an entire day as everyday. These receipts record
an existing narrator judgment over its truncated input, not independently validated
intimacy ground truth or a prospective prediction before the conversation happened.

A private importer can project a bounded interval into a reviewed `somatic_marks`
entry without reading narration: copy `mode: intimate`, `start`, `end`, `surface`,
the receipt's `observed_at`, `session_id: null`, and `join: exact_turns`. Set
`source_field` to `somatic-narrated.json:intimacy_evidence` or
`somatic_thread:intimacy_evidence`; hash the retained source record into
`source_record_sha256`. Project each interval turn to exactly `turn_id`,
`text_sha256`, `timestamp` under `turns`. The source reviewer then computes the
existing `somatic_review_binding(mark)` (now also binding `turns`). Only an admitted
reply matching that exact ID, text hash, timestamp and surface receives the mode.
Nearby replies are not swept into the interval. This source cannot be widened to a
surface/window join or relabelled everyday. Existing historical marks retain their
old review hashes. Router receipts and independent observations still take priority.

## Repository-owned private cache production (note #49)

`encode_cache.py` is a separately invoked, private CPU embedding producer. It is
not imported by any live loop or reply path. The older prototype above remains a
cache consumer and still does not load an encoder. No live cache writer was found:
the historical character vectors came from the reviewer's private run. The shared
HTTP embedding cache, self-head cache and present-moment feed are unrelated and
remain unchanged. This producer works independently of witness capture settings.

Only an explicitly supplied GGUF file and importer projection are read. All output
is under an existing mode-0700 private scratch root outside repositories/live stores.
The GGUF source may be an explicitly retained regular file outside that root; no
model directories are searched and symlink sources are refused. The input projection
must be inside scratch. Choose a **new** output directory: existing directories and
copies are refused; failed runs may leave an incomplete directory/copy for inspection
and require a different output name. No existing cache is modified or upgraded.

```sh
SPARK_WORKSPACE="$TASK_SCRATCH" python3 experiments/character-reference/encode_cache.py \
  --scratch "$TASK_SCRATCH" --gguf "$TASK_SCRATCH/retained-model.gguf" \
  --input "$TASK_SCRATCH/character-input.json" --output "$TASK_SCRATCH/encoded" \
  --cutoff YOUR_OFFSET_AWARE_CUTOFF --pooling mean --context-tokens 8192 --threads 2
```

The caller must choose pooling (`mean`, `cls` or `last`) appropriate to the retained
artifact, rather than relying on a guessed runtime default. The installed
`llama-cpp-python` in-process runtime is required; no installation/download or
subprocess fallback occurs. The adapter uses `Llama(..., embedding=True)` and
`embed(text, normalize=False, truncate=False)`; explicit token overflow is a failure,
never silent truncation. This API and its pooling/offload options are documented in
the [upstream API reference](https://llama-cpp-python.readthedocs.io/en/latest/api-reference/).
CPU settings explicitly disable layer, K/Q/V and operation offload and flash attention;
context tokens are bounded 128–32768, threads 1–32, with equal context/batch/microbatch sizes (`n_ctx`, `n_batch`, `n_ubatch`).
A runtime lacking those options fails rather than silently selecting a substitute.

The producer creates `encoder-copy.gguf` (0400) inside the new output directory
(0700), hashes that copy, records anchored copy-completion time as default `frozen_at`,
and loads **only that copy**, without mmap. Source mutation during copy is refused.
Copy identity/size/modification/change timestamps are checked around every encoding;
the full copy hash is checked before/after loading, after encoding/closing and before
publishing JSON. Changed, replaced, restored-but-touched or symlinked copies refuse
publication. This is a prospective file-copy boundary, not proof of historical model
training, prior cache derivation or remote serving identity. The artifact is bounded
to 4 GiB; no real weights were loaded during synthetic validation.

The exact full reply text (producer-attested final text where present) and exact
context string are encoded once per distinct string. Nothing is stripped, prefixed,
summarized or truncated. Up to 512 explicit reply IDs are accepted, each string
bounded to 65,536 codepoints; unsupported token lengths fail in the local runtime.
Empty contexts, missing/conflicting IDs and identical reply text with different
contexts refuse because the consumer's cache key cannot represent that ambiguity.
Only pre-cutoff assistant rows are encoded; original rows/provenance are retained,
and cache production does not grant evidence admission. Generated vectors must be
flat, finite, nonzero, dimension-consistent and at most 2,048-dimensional, then are
L2-normalized by the producer. Full-string input hashes and `prefix_chars: 65536`
make the exact input policy explicit in the new encoder contract.

Outputs (JSON files 0600):

- `character-input.json`: the unchanged source rows and other fields with a **new**
  encoder contract and freshly produced embeddings. Source input remains immutable.
  Prior `numerical_evidence` and nonempty control caches are refused before encoding;
  produce controls separately under the same encoder before comparative evaluation.
- `cache.json`: fresh encoder, vectors and private producer manifest. Encoder ID
  binds copied artifact hash, runtime identity and explicit settings. The old encoder
  declaration stays in the manifest, not as a claim about the new vectors.
- `cache-metadata.json`: directly accepted by `build_evidence.py --cache`:
  `encoder-cache-metadata-v1` with `entries`. Each entry includes `reply_ids`, exact
  full-reply/input/context hashes, encoder ID, artifact hash, effective freeze timestamp and qualification receipt,
  runtime name/version, pooling/normalization/input/CPU settings, and actual reply
  and context encoding start/finish clocks, monotonic elapsed values and the run clock
  anchor. Duplicate identical copies retain all
  bound reply IDs without extra encoding.
- `counts.json`: counts only (IDs counted, cache entries, unique encoded strings,
  dimension, replies predating freeze, completion-call count); no IDs/text/hashes,
  vectors, model labels or paths.

Then use `encoded/character-input.json` as the builder's `--input` and
`encoded/cache-metadata.json` as its `--cache`, with optional separately retained
lineage/humor projections and a distinct new builder output directory. The numerical
runner consumes that builder output. No source-store reader or deployment entry is
added. Package version is recorded; the native backend version remains explicitly
unknown unless the installed package exposes independent evidence (not inferred
from its Python package version). No completion generation is called.

**Migration and temporal limit:** old files stay untouched and their missing metadata
stays unknown. Under the default `copy_time` policy, a freshly encoded historical
reply has a freeze time **after** the reply. `build_evidence.py`/the numerical judges still require freeze before the act,
so the new metadata is accepted structurally but those rows remain unscored for that
prospective contract. The summary counts them. The explicit reviewed external-artifact
qualification below is the sole alternative; it preserves the actual copy time. Previously cached vectors
are never reused and relabelled as if this run produced them.

The Python audit guard confines Python writes to the new output directory, with an
explicit producer-only exception for opening the literal character device `/dev/null`
for writing during runtime import. Aliases and other external writes remain denied;
the shared guard defaults to refusing even that exception. It denies network and
**all** subprocesses; only the installed in-process local runtime is used.
Native loader stdout/stderr is suppressed so private paths cannot leak in an error;
CLI errors are fixed, sanitized JSON. This is not an OS sandbox for native extensions:
the installed runtime is trusted, and private execution should retain the reviewer's
OS isolation. The synthetic suite uses a tiny injected interface, tests network and
process refusal, detects copy mutations, and exercises producer→builder metadata
compatibility. Real runtime/artifact compatibility and private-data coverage remain
unverified until the reviewer's separately authorized run; the dependency was not
installed or exercised here.


### Clock semantics for private encoding

One wall-clock reading is bracketed by two monotonic readings at run start. The
receipt records that wall anchor, the midpoint monotonic anchor, the bracket width,
and `cross_process_order: not_attested`. Copy completion and encoding boundaries
are sampled from monotonic time; their epoch estimates are the wall anchor plus
elapsed seconds. The receipt keeps elapsed values beside every estimate, including
copy completion. Wall steps during the run therefore cannot reverse the recorded
encoding order. Nonfinite or backward monotonic readings still refuse the run;
timestamps are never clamped or inferred from artifact modification times.

These estimates establish ordering within this run, not a corrected UTC clock or
causality with another process, boot, host or historical reply. The copy-time
qualifier still uses the new copy boundary; it does not backdate historical acts.
The published-artifact qualifier still uses the separately reviewed revision date.
Neither this change nor a successful encoding supplies missing lineage, delivery,
mode/reference coverage or outcome anchors. Old metadata is not rewritten.

### Reviewed external-artifact freeze qualification

The gate asks whether the exact encoder weights could have been shaped by the acts
being scored. Default `--freeze-source copy_time --artifact-kind local_trained`
continues to use actual copy completion. Every local-trained or subject-tuned artifact
must keep that rule, including self/latent heads. A configured model label, upstream
base model pin, source mtime or an old cache does not establish a published freeze.

For an external pretrained artifact, explicitly add
`--freeze-source published_artifact --artifact-kind external_pretrained --published-pin PIN_ID`
to the producer invocation. `encoder_freeze.py` loads only the checked-in
`published-encoder-pins.json`; there is no CLI registry override, network lookup,
download or automatic approval. The registry contains one external artifact pin supplied by the independent reviewer
in coordination note #51. Its review attribution is recorded; the implementation
agent did not download the artifact or independently repeat that verification.
Tests inject a synthetic registry into the stub process only.

The registry envelope is `{"schema":"published-encoder-pins-v1","pins":[...]}`. Each reviewed
pin requires: unique `id`, `publisher`, `repo`, exact `filename`, immutable full
40/64-hex `revision`, offset-aware `revision_at`, exact file `artifact_sha256`,
`artifact_kind: external_pretrained`, `trained_on_subject_data: false`, and
`reviewed: true`. The pin covers the exact quantized/exported file loaded, not just
upstream weights. Review must establish that neither that file nor its tuning or
conversion was shaped by the subject's scored acts. The flags record that review;
the program cannot independently verify a publisher's training history offline.
Optional `reviewer` and `size_bytes` retain bounded review attribution and declared
file size; exact SHA256 equality remains the artifact identity check. Duplicate
keys/IDs, malformed pins and unreviewed/subject-trained pins are refused.

The producer first copies and hashes the GGUF. Before opening the encoder it requires
exact equality to the selected reviewed hash. Effective `frozen_at` is that pin's
revision timestamp; revision after copy is refused. `copy_completed_at` stays the
actual copy completion, and encoding clocks must still follow it. No old vector or
metadata is backfilled. Existing hash/change-time checks continue throughout encoding.

`freeze_source` and `freeze_receipt` are recorded on every cache entry and the private
manifest. The receipt retains effective freeze, copy time, artifact kind/hash, full
published pin and pin fingerprint. Builder and numerical runner revalidate the
receipt against their own checked-in registry; missing or changed pins, changed
receipt/scalar, missing receipt, hash mismatch, or local-trained qualification refuse
the run. Policy and pin-file hashes appear in private code manifests.

Counts separate `copy_time`, `published_artifact`, `legacy_unknown` and `unknown`.
Producer counts entries; builder counts prepared replies with recorded qualifications,
even if their freeze is too late; runner counts replies by usable global qualification
(or unknown if unavailable). Sources are not silently mixed into one global encoder.
Legacy supplied freeze timestamps retain their old validation and remain explicitly
`legacy_unknown`; they are never promoted to published evidence. A valid published
revision still must precede each act. This exception changes only the freeze gate,
not strict lineage, mode, outcome anchors, calibration, or independence requirements.


Missing local runtime imports now refuse with fixed JSON error
`encoder_runtime_unavailable`, dependency `llama-cpp-python` and an owner-approval
installation hint. No install or subprocess fallback is attempted, and errors expose
no private paths. A failed run may retain its private copied artifact; retry into a
new output directory after the approved environment is ready.
