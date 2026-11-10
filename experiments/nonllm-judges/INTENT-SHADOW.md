# Offline intent shadow assessor

`intent_shadow.py` is a pure, deterministic assessor plus an explicit private-file
CLI. It imports no runtime organ and has no runtime consumer, model call, encoder,
feedback write or deployment-manifest entry. Native intent-ledger JSON snapshots
can be inventoried immediately; additional evidence and contracts are optional.
Without them, missing evidence is HELD, never a fabricated verdict.

## Meaning and limits

This is a contract prototype for observable mechanical criteria, not a semantic
replacement for the current judge. It reports conditional YES/PARTIAL/NO only
when an independently reviewed, prior contract and exactly bound terminal receipts
satisfy the checks below. A contract supplied alongside evidence is a claim, not
proof of independent review or source authenticity. The report therefore always
says `source_claims_verified=false`, `conditional_on_supplied_contracts=true` and
`semantic_accuracy_measured=false`. No production source adapter, authenticated
review registry or historical backfill is supplied by this change. Existing
free-text intentions may have no admissible mechanical contracts; that is an
explicit coverage limit, not evidence that the intentions failed.

The report is blind to `realized`, priority, pressure, selection_check and old
held reasons while grading. Original verdicts are used only afterward for a
fixed per-axis confusion table. The agreement denominator includes only rows
with YES/PARTIAL/NO on both sides; HELD, NOT_DECLARED, missing and malformed
original verdicts remain separate. An empty denominator returns null. Agreement
with an old judge is not truth or validation of the new assessor. Contract-family
counts describe supplied annotations, including rejected contracts; they are not
counts of independently verified or eligible criteria.

Field, gloria and self remain separate. An explicitly abstained field and absent
secondary axes are NOT_DECLARED. Malformed declarations are HELD. Unsupported
semantic/internal-state criteria are HELD, not guessed from words, punctuation,
reply length, positivity, device events or the selector's confidence. This version
has no mechanical her-response predicate. It can audit an exact response join,
but cannot infer her feelings or preferences from that response.

## Exact joins and observation windows

A delivered ledger row must carry its own intent ID, matching target intent ID,
turn ID, full reply bytes, selection time and delivery time. No last-reply fallback,
proximity join, label-based authorship, legacy ID fabrication or response fan-out
is accepted. Equal JSON rows deduplicate; conflicting rows for one intent and
multiple intents sharing one turn are excluded as ambiguous. Conflicting evidence
IDs or multiple contracts for one intent/axis refuse the entire report.

A delivery evidence record must match the full reply, intent ID and delivery time,
and identify itself as an assistant reply from a delivery receipt. For an axis
observed in her next reply, exactly one explicitly parented user-reply record is
required, with matching full response text and a strictly later time. Unknown
provenance stays unknown: a text label is not a parent link. Device/system sources,
wrong role, absent response and ambiguous children are HELD with separate reasons.

Selection must precede or equal delivery, and observations must be strictly before
the supplied cutoff. Unknown, backward or ambiguous clocks exclude; native naive
ledger timestamps need an explicit source timezone. Sidecar times require explicit
UTC offsets. This-reply/my-move evidence does not require a later user response;
her-next-reply/her-response evidence does. Self supports only the former; gloria
only the latter. This is a shadow distinction, not a change to the live input gate.

## Private sidecars, version 1

All IDs, hashes, text and reviewer records stay in private snapshots. The CLI emits
none of them. The normalized sidecars below are supplied by the source holder;
normalization must retain original records and provenance, never mutate them or
promote configured model names into actual served identity. Preserve actual served
model and fallback receipts when available; otherwise leave them unknown. This
assessor is deterministic and makes no inference calls; it does not establish the
historical selector/old judge's served identity or independence.

`--evidence` accepts `schema: intent-shadow-evidence-v1`, `turns` and `receipts` lists.
Each record has a unique `id`. Turn records contain:

- Delivery: `intent_id`, `role: assistant`, `kind: reply`, `source: delivery_receipt`,
  `source_sha256`, `at`, `text`; its ID equals the ledger's turn ID.
- Response: `reply_to` equal to that delivered turn ID, `role: user`, `kind: reply`,
  `source: canonical_user_turn`, `source_sha256`, `at`, `text`.
- Source SHA values denote the retained original source records, not authenticity
  signatures. The exporter must retain and independently verify those records.

Action receipts contain `intent_id`, `turn_id`, `operation` (`artifact_delivery`
or `action_completion`), `object_sha256`, `source: action_receipt`, `source_sha256`,
`at`, `terminal: true` and `status: succeeded|failed`. The object's digest binds
exact declared bytes, not a mutable title or path. An event only applies to the
exact intended operation/object in that delivered turn, between selection and
delivery. A second distinct matching receipt may be a retry; it is ambiguous,
even if it agrees. Identical copies of one receipt ID add no weight.

`--contracts` accepts `schema: intent-shadow-contracts-v1` and `items`. Each item:

- `id`, `intent_id`, `axis`, integer `version: 1`, and `target_sha256` covering the
  complete original target. Hashing uses SHA-256 of UTF-8 canonical JSON: sorted
  keys, separators comma/colon, ensure_ascii false, allow_nan false.
- `family: mechanical|semantic|internal_state|unspecified`, `observation_window`,
  `evidence_type`, `review_kind: independent_human`, `review_source_sha256` and
  offset-bearing `reviewed_at` no later than the original selection time.
- For a mechanical my-move criterion only: `predicate.kind: terminal_receipts_all`,
  `predicate.conditions` (one to sixteen unique operation/object_sha256 pairs),
  and boolean `predicate.partial_allowed`.

The review establishes that the predicate faithfully expresses the original
criterion; the program cannot derive that semantic mapping. A retrospective rule
written after observing the act does not qualify. Merely tagging a semantic goal
as mechanical does not make it so. Such a source claim needs independent review
before any interpretation beyond this isolated contract prototype.

All conditions require explicit terminal observations. All succeeded means YES;
all explicitly failed means NO. Mixed outcomes mean PARTIAL only when the prior
contract defines partial credit; otherwise HELD. A missing or pending receipt is
HELD, never NO. An unrelated success, unsupported operation, mismatched goal,
late review, duplicate condition or changed observation window cannot grade.

## Run and public output

Only use explicit authorized snapshots outside a repository/live workspace, with
an owned private root (0700) and owned regular files (0600), no symlinks:

```sh
python3 experiments/nonllm-judges/intent_shadow.py \
  --scratch "$SCRATCH" --ledger "$SCRATCH/intent-ledger.json" \
  --cutoff "<timestamp with explicit UTC offset>" \
  --source-timezone America/Chicago
```

Optionally add `--evidence "$SCRATCH/intent-evidence.json"` and
`--contracts "$SCRATCH/intent-contracts.json"`. Do not manufacture these to make
old rows score. Without sidecars the report is an abstention census. Each file is
bounded to 4 MiB, each list to 4096 records. Duplicate JSON keys, nonfinite JSON,
conflicting identities and unsafe paths refuse with only `intent_shadow_refused`.
File mutations, subprocesses and networking are forbidden. Stdout has only fixed
schema keys, counts, rates and limitation flags. No row-level outputs, source text,
IDs, hashes, titles, arbitrary keys or destinations are returned. Aggregate counts
may be published; raw private artifacts remain private.

Original fields, including unknown provenance and concurrent merge fields, are
never rewritten: this tool cannot persist a resolution. It has no path into
`_attempt_context`, priority/receptivity, valence, desired-difference, outcome_join,
pressure reconsideration, anchors, training, policy or campaign state. Tests assert
input equality and unchanged private files including a synthetic campaign store,
forbid I/O around pure assessments, and vary old verdicts/feedback fields to prove
that they do not influence shadow grades. No production import or manifest change
is made. Full independent integration validation remains with the reviewer.

The accompanying [campaign gate design](CAMPAIGN-SHADOW.md) is design only.
