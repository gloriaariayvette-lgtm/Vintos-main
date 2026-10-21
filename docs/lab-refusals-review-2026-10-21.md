# Chemistry Lab refusal review — 21 October 2026

Reviewed base: `fce3103a1095b5a7430497689b6bb5bf9ef09ad8`, from
`claude/device-visuals-2026-10-13`. Review branch: `codex/lab-refusals-review`.
Also read the updated Codex brief at `d62737f`; production files are identical
between those revisions. All production-code line references below refer to that
unchanged code. No Aegis access, live source requests, or model calls were used.
The supplied Aegis counts are user-provided observations, not independently reproduced here.

**The strongest code-supported diagnosis is an objective mismatch: the minute
loop generates and evaluates documented-fact retrieval, while Gloria wants new
findings produced by instruments.** Recovery repeatedly supplies another factual
lookup, and a failed coverage review leaves the loop without an answered-review
reset. This is a plausible upstream driver of the spent-subject/refusal cycle,
not a proven attribution of all 317 refusals. The probe measures that attribution.

There is **no production patch in this branch**. Making factual lookups easier
to answer would optimize the wrong outcome. In particular, preserving the narrow
fallback through record binding would remove a reproduced broadening defect but
would still produce documented facts; it is not proposed as a remedy.

## What the planner is told the Lab is for

| Generation/steering path | Code evidence | Consequence for novel findings |
|---|---|---|
| Minute-loop system, `chemistry_lab.py:1853` | “curious, playful, and evidence-honest”; no positive requirement to produce a new measured result | Honesty is specified; measurement as the purpose is not. |
| Main task, 1861, 1870, 1911 | One source-answerable property; a sequence to embed/structure to fold; then three required claims: structural feature, documented function, source-backed relationship | Instruments are mentioned, but the detailed answer contract steers back to documented knowledge. No required predicted value, measured variable, input artifact or comparison baseline. |
| Fresh recovery, 2377 | “ONE fresh protein for a new curated-record review,” followed by documented features/function/relationship | Three model choices and the fixed protein queue all restart retrieval. “Fresh” means a different subject, not a new finding. |
| Saved-record recovery, 2341 | Builds `_record_connection_question` from an unread returned record | Avoids a new browse, but the research objective remains factual coverage. |
| Automatic lines, 2599 | Structural-plus-functional/relational questions automatically open claim lines | The generated retrieval question becomes durable work, even if it cannot produce a new measurement. |
| Line progress, `lab_lines.py:197`, 323, 399 | Stores factual observation and answer verdict; accumulates verified quotes; shows open claims and directs retrieval toward them | Persistence tracks coverage of claims, not new results per day. Missing documented relationships can keep a line in evidence gathering. |
| Standing line, `lab_lines.py:46` | Explicit novelty purpose; find phage reverse transcriptases, then `rt_locus_screen` | A real counterexample: a route to derived genome-region findings exists. Do not claim every line is a lookup. |
| Line scheduling, `lab_lines.py:114`; `_orient:1786` | Three of four cycles assigned when lines exist, standing cadence, held lines may yield to free work | Stored questions matter greatly; recovery can replace a blocked measurement-oriented line with free documented-fact selection. |
| `lab_repeats.frontier_step:407` | Carries the last completed session's `reading.next_question`, for six lookup-ledger attempts | It does not generate a measurement objective; it inherits whatever next question the session wrote. Refusals also consume attempts. |
| `lab_repeats.on_frontier:430` | Requires only any shared subject | Replay: a cellular-role lookup passes a step asking for RMSD of the same protein. A subject check is not preservation of the experiment. No new gate is proposed here. |
| Frontier experiment planner, `chemistry_session.py:238`, 278 | Named experiment, prediction before run, explicit fold outputs and limitations | This separate path is closer to Gloria's objective. Its session output must be counted separately from minute-loop inquiries. |
| Frontier reading, `chemistry_session.py:415` | Requires `prediction_vs_result` and `what_surprised_me` | Unlike the minute-loop review, it explicitly compares the experiment with the prediction. A miss can be informative. |

The instruments are **offered, but not the organizing objective**. At
`chemistry_lab.py:1847`, their menu is inserted before the main task.
`lab_instruments.py:115` offers structure measurements, sequence analysis/alignment,
reference comparison and existing-model range reads, conditional on artifacts;
the menu disappears when the existing 25-run allowance is exhausted. This review
does not infer that Aegis had usable artifacts or remaining allowance in that period.

There is also an execution asymmetry. At `chemistry_lab.py:4889`, only explicit
saved model/archive assignments go directly to `sources`; an ordinary newly
chosen `instrument_query` goes to **browse first**, even if it names a saved model.
The real `tick` replay confirms this. `_inquiry` at 3157 supplies a UniProt query
even for such a choice. The browse can therefore spend a lookup before the requested
measurement, and an empty browse can divert the turn before the instrument runs
(4950 onward). The saved-model shortcut (2438) requires a specific saved next-step
shape and sourced artifact. Existing instruments are not universally hidden, but
normal instrument selection is still embedded in a retrieval-first cycle.

**The main review does not require “what new result did this turn produce?”**
`_reflect` at 4546 asks first whether evidence answers the question, then factual
observation, speculative reading, next question and instrument gap. Coverage checks
require support for the original claims. There is no required new measurement,
artifact/method/output linkage or before/after knowledge distinction. Novelty text
in the minute-loop prompt is principally a prohibition on inferring novelty from
missing literature (1903, 1926, 4533), not a positive measurement objective.

The causal hypothesis is therefore: documented-fact question → incomplete source
coverage → no answered reset / open missing claims → holds and spent subjects →
fresh documented-fact question. The code establishes these transitions; the live
question/verdict/source-operation split must establish how dominant they are.

## What the code establishes

1. **Not every planner call sees the spent list.** The main `_orient` prompt has
   it, but `_fresh_free_inquiry` makes up to three `_plan` calls without it
   (`scripts/chemistry_lab.py:2377`, especially 2390–2395). Each choice passes the
   real spent gate with `replan=False`. A failed choice gets only “unavailable;
   shift biological process” on the next call, without the subject or hold reason.
   These refusals enter `lookups.jsonl`; they do not each become notebook
   `inquiry_refused` rows. Thus they cannot simply be counted as the 317 notebook
   refusals. The probe counts both ledgers separately.

2. **The main path can make three planner calls before a spent refusal.** There
   is an outer spent retry at `chemistry_lab.py:2008` and a separate blocked-choice
   retry at 2528. The final notebook row preserves the final inquiry, not the first
   two proposals. “Re-planned once” is true of that inner gate, not of the pass.

3. **A name anywhere in question/query text can trip the spent gate.**
   `spent_matches` at 634 uses case-insensitive boundaries excluding ASCII letters
   and digits, not entity roles. `_inquiry_text` at 645 concatenates the question,
   UniProt query and the entire source-query JSON. Negation, background context,
   and hyphens do not protect a match. It does not search `why_now`, material terms,
   or plugin arguments. `spent_retrieval` at 655 exempts instruments and named
   sequence/context/PDB/ChEMBL/InterPro routes. An open `line_id` exempts the spent
   check at 2507–2516, but not the preceding question hold or subsequent repeat
   check. The outer spent retry exempts only the currently assigned line (2006),
   which is a narrower exception than the inner gate's any-open-line test.

4. **The planner receives conflicting question requirements.** At 1861 it is
   told to ask one property; at 1911 it is told to include structure, function and
   their relationship. The fresh prompt independently requests all three at 2385.
   `_SECOND_ASK` at 1263 catches “and how/what/etc.”, not comma-separated lists of
   nouns. `_HALLMARKS` at 1270 does not match “structural hallmarks, documented
   cellular roles, and source-backed relationships”. The supplied question shape
   survives real `_plan` → `_narrow` unchanged in the replay. This is evidence of
   a contradictory contract, not proof that a particular model ignored a clear one.

5. **The fixed fallback's narrow question is broadened by code after planning.**
   At 2404 it asks what domains, binding sites and residues the curated record lists.
   During browse, 4920 calls `_resolve_free_record_discovery`; at 3376 that function
   unconditionally replaces its question with `_record_connection_question` (2334),
   which asks structure, function and relationship. This transformation never goes
   through `_plan`/`_narrow`. The same compound helper also supplies saved-record
   recovery at 2350 and a mismatched-name repair at 3167. Narrow or broad, these
   questions still ask for documented knowledge; that is the more important failure.

6. **“Every unanswered review feeds the spent list” is an approximation.**
   `dead_ends` (556) scans inquiry and inquiry-refused rows since the latest answered
   reflection within the 512 KB tail (435), activates at three attempts, and returns
   at most six subjects. It can include a subject without any individual negative
   review; the replay demonstrates this. `review_answered` (263) treats an explicit
   verdict as answered only if it starts with `yes`; a legacy missing verdict counts
   as answered. `_orient` remembers the six subjects and unions them with active
   persisted holds (1710–1713). `remember_spent` (622) does not renew an active 24 h
   hold; once expired it may overwrite its timestamp. Old entries remaining in the
   file are not all active holds. This review does **not** revive the disproved
   multi-day tail-window hypothesis.

## One refused turn, end to end

Replay setup: scratch state; spent `KaiC`; no assigned line/frontier/Atlas work;
no saved alternative; scripted planner returns the same KaiC question three times.

| Stage | Actual behavior | Calls in this replay |
|---|---|---:|
| `tick`, 4830 → `_orient`, 1701 | Compute recent subjects, remember holds, select assignment/recovery | 0 |
| Prompt construction, 1853–2002 | Append spent singles and families, then waiting questions | 0 |
| `_plan`, 1230 → `_plan_raw`, 1247 | Append output contract; scripted `_ask`; parse and narrow | 1 |
| `_inquiry`, 3140; existing-model routing | Normalize candidate; no spent decision here | 0 |
| Outer spent check, 2007 | Spent choice, not assigned continuation: ask again | 1 |
| `_held_to_plan`, 2483 | Hold → spent → repeat; deterministic alternative unavailable | 0 |
| Inner retry, 2528 | Ask again with reason, then apply the same gate | 1 |
| Terminal gate, 2551 | Set insufficient/no-unread-route; `repeat: spent subject…`; record refusal | 0 |
| `tick`, 4842–4849; append at 5375 | Write one `inquiry_refused` row, phase back to orient | 0 |

**Measured: three planner/model-boundary calls, one lookup-ledger refusal, one
notebook refusal, zero source/network calls.** With one malformed JSON response
per `_plan`, the same path makes six `_ask` calls. These are counts, not prices;
no inference about the deployed provider is made from stale “Gemma” comments.

The other admission/refusal and retry branches are:

| Location | Decision and extra planner calls |
|---|---|
| `_planning_hold`, 1662; `_orient`, 1774–1799 | Return stored wait without planning; or recover through the gate. A held line can yield to free work. |
| `_orient`, 1750–1769, 1802–1814 | Saved archive/model, alternate evidence, deferred coverage and sourced-record routes may return before building the main prompt. Recovery gate calls with empty `system/task` can still re-plan at 2528, without the main spent prompt. |
| `_fresh_free_inquiry`, 2389–2412 | Up to three planner calls with `replan=False`, then fixed queue; held/spent/repeated queue entries are skipped without calls. On failure selection can continue to the main prompt. |
| `_held_to_plan`, 2493–2500 | Off frontier: one extra plan; refuse if still off. This branch does not consult `replan=False`. |
| `blocked`, 2501–2518 | Held unchanged evidence first, then spent unless open line, then `repeat`. |
| `lab_repeats.repeat`, 265 | Known identity rejection, identical canonical lookup, already-covered fold interval, or similar same-route question (with distinct-target exceptions). |
| Gate, 2520–2554 | With `replan=False`, refuse immediately. Otherwise try deterministic strategy, one re-plan, another strategy, another evidence task. Still held → selection idle/evidence wait; otherwise terminal repeat refusal. Re-plan off frontier also refuses. |
| Gate, 2556–2566 | Invalid or unproven NCBI accession refuses; no corrective plan. |
| Gate, 2567–2583 | Human identity grounding may contact a source. An unresolved identity permits one premise-correction plan when enabled; unavailable/unresolved remains refused. Corrected choice must pass frontier, blocked, and identity checks. |
| `tick`, 4832–4841 | Previously sourced record gone/already reviewed: refuse after orient, with no planner retry. |
| `_plan_raw`, 1253–1258 | Each plan has at most one JSON-format retry; malformed second response faults rather than making another scientific refusal. |

On a main-prompt traversal, distinct correction sites are initial + outer spent
+ frontier + inner repeat + identity (up to five `_plan` calls if all apply, up
to ten `_ask` calls with format retries). Early recovery/fresh attempts can add
calls, or bypass planning entirely. Consequently no single “two calls per refused
pass” multiplier is valid. Exceptions during query normalization are faults,
not refusal rows. Browse/source availability, sourced-ID, stale-evidence and
review decisions occur later; they are not planner re-plans. A notebook label
“before any source call” is not a substitute for tracing identity/recovery work.

## What the review result means

The supplied totals are 303 reviews: 19 yes (6.27%), 248 no (81.85%), 35 not assessed
(11.55%), and one not established (0.33%). **93.73% were not yes; 81.85% said no.**
Among yes/no alone, 92.88% said no. Assessment failures must not be presented as
scientific failures.

The original question is checked, not whether something interesting was retrieved.
`_reflect` (4416) checks identity/premises, reads evidence, then passes both yes and
no reader verdicts to coverage adjudication (4577). The final `answers_question`
comes from that coverage result (4590), not just the reader's opinion.
`_coverage_attempt` (4270) verifies source-address/quote integrity; a positive then
needs independent sufficiency (4319). A valid negative is accepted without that
second sufficiency call. The replay demonstrates this asymmetry, including a
scripted false negative despite a supplied function statement. It proves a route
by which an over-strict checker could matter, not that the live checker took it.
No review check is weakened in this branch.

Evidence is wired through: base 5232 builds observations from complete protein
records, additional-source receipt, literature and question-bound structures;
line evidence joins at 5243. `_reflect_with_claim_evidence` (4371) adds prior
validated quotes and may retrieve full text/review again. `review_observations`
(3700) preserves prose and reorganizes source receipts; long unrequested sequences
and numerical arrays can be represented by placeholders. The reader gets a bounded
24,000-character rendering (4545); the checker gets a separately addressed evidence
tree (4110), with splitting/deferral rather than that reader excerpt.

The small fixture's record function and article abstract both reach the real
coverage request and receive quote addresses. This rules out a universal “all
evidence is dropped” defect in that path. It does **not** establish delivery or
sufficiency for any live failed review. Receipt/coverage hashes, missing claims,
reader-versus-coverage verdicts, source IDs, and full-text results in the probe
allow those cases to be separated. The instruments can answer many bounded
questions; their mere presence does not establish an arbitrary structure–role
relationship for every protein.

## Harness results

Run from the review checkout:

```sh
python3 -B broker/tests/test_lab_refusals_replay.py
```

**17 tests passed.** The suite calls real orient/plan/narrow/inquiry/held/repeat
code and real `tick` paths, with scripted `_ask`. It stubs identity resolution,
unrelated work queues and prompt menus; it is not a test of live model obedience,
identity data, source availability, or production path frequencies.

HOME and workspace are scratch before application imports; module paths are
rebound; a process-wide audit hook refuses writes outside scratch. Socket connect,
connect-ex, datagrams, URL fetching, provider/sender entry points and subprocesses
are blocked/stubbed, with isolation and zero attempted sends asserted. The probe
test compares scratch-file bytes before and after. Existing lab_lines file-handle
ResourceWarnings appeared; tests passed. No broad host suite was run.

| Measurement | Result |
|---|---:|
| Main spent retry path | 3 planner calls, 1 terminal refusal |
| Same path with JSON repairs | 6 calls |
| Fresh path returning spent KaiC each time | 3 calls, 3 lookup refusals, then fixed-queue acceptance; 0 spent lists shown |
| Eight independent spent-matching cases | 4 refusals: direct target + negated mention + background mention + hyphen component |
| PDB/instrument, fresh and alphanumeric-substring controls | 0 spent refusals |
| Open line, first lookup / second identical lookup | admitted / refused |
| Supplied compound-question shape through `_plan` | unchanged |
| Feature fallback through sourced record binding | 1/1 broadened to three claim types |
| Frontier measurement step with same-target factual lookup | admitted by subject-only `on_frontier` |
| Ordinary saved-model instrument inquiry at orient | next phase is browse, not instrument execution |
| Probe fixture with lookup / measurement / mixed / unclear | 25% each; verdicts and source/instrument events attributed separately (synthetic only) |

The 3 synthetic question-only refusals are **not** an estimate of the share of 317.
Without live questions, the attributable count remains unknown (0–317). Even a
question-only match may be scientifically central to a comparison. The probe's
question-only tally is a triage cohort, not permission to bypass the gate; the
reason string names at most four matches, and names containing commas are ambiguous.

## Decision and success criterion

No production behavior change is proposed before the live classification is
returned. The exact failure of a question-shaping transition is established, but
repairing it toward easier factual retrieval would not meet the updated brief.
Likewise, adding searches or removing spent checks would not establish progress.

The outcome to count is **new instrument findings per 24 hours**, including useful
negative experimental results: an identified input/artifact, a concrete question
and comparison/prediction, a completed measurement with a reproducible result, and
what that result added beyond the input annotations. A new retrieval, automatic
embedding, successful fold alone, “yes” review, or new receipt timestamp is not
automatically a finding. “New” here is the Lab producing the result rather than
retrieving it; it does not assert worldwide publication novelty or require a new
literature search. Retain identity/provenance and scientific checks.

The probe reports question intent, instrument result events and recorded source
operations as separate quantities. It cannot certify that a result is a novel
finding just from a verdict or an instrument's name. It emits the exact cases for
inspection. Current novel findings/day and the magnitude of a fix's improvement
are **unmeasured**, not zero. There is consequently no justified numeric uplift
claim or patch recommendation in this report. Any later candidate must increase
auditable new findings/day without increasing broad retrieval cost; lower refusal
counts or a higher factual-answer rate alone would fail the stated goal.

## Earlier work checked

Read the requested `git log --since=2026-09-30 -- scripts/chemistry_lab.py scripts/lab_repeats.py`
(132 entries), then relevant diffs/blame. Closest prior work and distinctions:

| Finding / proposal | Closest earlier commits | Distinction |
|---|---|---|
| Post-planning broadening (not proposed as the fix) | `64f4469`, `c151f60`, `ef380e5`, `fa96b0a` | 64f changed the fixed-queue question; the later binder still uses fa96b's compound helper. The replay checks that later transition. Both question shapes remain factual retrieval. |
| Contradictory prompts and missed noun-list shape | `2b436e6`, `2f8aa5d`, `fa96b0a` | Earlier narrowing fixes are present; they do not remove the three-claim instruction or recognize this list shape. No additional prompt/narrowing patch proposed. |
| Missing spent list on fresh path | `849ee7f`, `763eb65`, `57e867a`, `da8d0c3` | Main prompt capacity was fixed, and fresh context intentionally separated. The separate fresh prompt has no list at all. No further list-size patch proposed. |
| Question-wide spent matching | `40a25cb`, `849ee7f` | 849ee7f explicitly disproved the tool-word diagnosis and removed its blacklist. This review measures actual matching, without restoring that disproved fix. |
| Layered retry accounting | `396f48f`, `42239bb`, `ada13b2` | Final acceptance gates and counting refused attempts already exist. This review counts their composition and separates notebook passes from lookup-ledger attempts. No new repeat gate proposed. |
| Held-work recovery | `344774a`, `b51699a`, `87df5e0` | Expiry, context exposure and skipping held follow-ups already exist. No repetition of those patches. |
| Short notebook tail | `5500a97` → `35a99c9` | Revert respected. No multi-day ratchet claim or window change. |
| Retrieval objective persists through recovery | `fa96b0a`, `47ca41e`, `57e867a`, `763eb65` | These make claim tracking and fresh selection progress, but progress is defined around records/coverage. This review measures new-measurement intent and results separately rather than equating accepted retrieval with success. |
| Instruments and saved-model routing | `71f9bf5`, `b6582bd`, `ca1d3c1`, `93ea0e1` | Comparison, saved reads and locus screening already exist. The finding is the ordinary path's browse-first routing and subject-only frontier continuation, not a missing instrument. No duplicate instrument or bypass gate proposed. |

## The read-only Aegis probe

Use the review branch's `scripts/probe_lab_refusals_readonly.py`; copying that file
does not require deploying any Lab code. Run it beside the installed Lab source,
or name that actual source with `--source`. It uses only stdlib file reads, no
application imports, no models, no network, no subprocesses, and emits JSONL to
stdout. An audit hook rejects writes and external actions. It does not call
`_question_holds()` or `lab_lines.load()`, both of which can write.

For the same approximate cutoff as the brief:

```sh
python3 -B /path/to/probe_lab_refusals_readonly.py \
  --source /path/to/installed/chemistry_lab.py \
  --lab-root "$HOME/.vintos/workspace/memory/chemistry-lab" \
  --end '2026-10-21T16:30:00-05:00'
```

Omit `--end` for the rolling last 24 h. Each spent-refusal row pairs named subjects
with question/query matches, retained hold intervals, prompt-membership status and
attempt-origin status. It also emits compact review rows and a summary.

### Requested 24-hour question split

The source data is on Aegis and has not been supplied. The aggregate counts in the
brief contain no question text, so an actual split cannot be computed here:

| Cohort | Accepted questions | Review verdicts | Source operations used |
|---|---:|---|---|
| Documented-fact lookup | pending probe | pending probe | pending probe |
| Question requiring a new instrument measurement | pending probe | pending probe | pending probe |
| Mixed factual/measurement question | pending probe | pending probe | pending probe |
| Unclear from recorded question/route | pending probe | pending probe | pending probe |

The probe produces this table's data in the final JSON object's
`question_kind_breakdown`. The denominator for `accepted_question_share_percent`
is notebook `inquiry` rows (compare with the reported 362), not refused attempts,
waits, unique subjects or reviews. `question_rows_by_kind` separately counts
accepted, refused, waiting and reviewed questions. `review_verdicts` splits yes,
no, not assessed, not established and other **by the question actually reviewed**.
Discovery rewriting can change that question; `question_review_link` exposes the
accepted-versus-reviewed classifications and the chronological/query match.

Classification uses explicit documented/curated/annotated language, computational
verbs and known measurement operations. Ambiguous and mixed cases remain visible;
it does not force a favorable binary split. Every `question_classification` row
includes the complete question, selected routes and the rule signals, so the
classification can be manually corrected. A documented-role question with an
incidental measurement route remains a documented-fact question. A measurement
question label means intent, not a completed run or demonstrated novelty.

`source_operation_events` counts recorded UniProt browse, additional public-source
and noncached structure operations within an accepted inquiry's daemon interval.
`question_operation_link` exposes every attribution. Instrument results, cached
structure reuse, source failures and unique material receipts used by reviews
are separate counts. Refusals/waits do not inherit the previous inquiry's calls.
Records before the first accepted inquiry in the window are unattributed.
These are **logged operations, not exact HTTP-request counts**: adapters can retry,
return caches or make multiple internal requests; material/full-text/identity
reads are not all notebook events. Summing receipt use into the operation count
would double-count some work, so the probe does not do that. Provider request totals
by question are not recoverable from this notebook alone.

Completed frontier sessions and their next questions are emitted separately;
current open lines are explicitly labeled current snapshots, not historical state.
They reveal whether measurement-oriented instructions are being handed back as
lookups without contaminating the 362-inquiry denominator.

**Exact historical prompt membership and first-answer versus re-plan are not
recoverable from the requested files alone.** Notebook refusal rows (4845) have no
attempt ID or prompt. Lookup refusal rows (`lab_repeats.py:319`) drop the lookup
and retain only 300 question characters and 200 reason characters. Parser diagnostics
(947) store bounded replies/events/completion metadata, not input prompts or a
cycle/attempt link. Latest hold timestamps can overwrite prior intervals (629).
The probe explicitly returns unknown for those requested facts; it supplies
control-flow implications separately rather than pretending timestamps prove them.

| Probe output | What it means |
|---|---|
| `within_retained_24h_interval` | The stored hold interval covers the refusal timestamp. This supports nominal hold membership, not proof the name survived prompt rendering or that this path used that prompt. |
| `retained_interval_expired` | That retained interval does not explain an active persisted hold then. Recent dead-end union, a carried refusal, version differences, or timestamp ambiguity need examination. |
| `unknown_latest_stamp_postdates_refusal_prior_interval_overwritten` | Current state cannot answer historical membership. Do not count it as “not shown.” |
| `absent_from_current_store` | No matching current entry; not evidence by itself of planner disobedience. |
| `after_gate_replan_or_deterministic_recovery` | A terminal `repeat: spent subject` traversed the inner re-plan branch in this code. Recovery may then have replaced the candidate; not proof of which raw answer produced it. |
| `replan_false_gate_branch` | Rejection from a saved/fresh gate without inner re-plan. Other calling paths determine its planner origin. |
| `stored_wait_may_have_no_new_planner_call` | A wait can carry an old refusal; it is not a new model proposal by definition. |
| Large question-only cohort | Inspect those exact questions for incidental words. Zero would refute incidental-question matching as an explanation of the logged named matches. Four-name truncations/comma names need separate inspection. |
| High lookup `spent_replan_false`, fewer notebook refusals | Hidden fresh/saved attempts add cost even when a later fallback succeeds. They are not extra refused passes. |
| Feature-only inquiry then matching discovery-resolution review with code connection template | A temporal candidate for the reproduced post-planning broadening; inspect query/target alignment. No durable attempt ID is claimed. |
| Many missing relationships with supported structural/function quotes | Consistent with over-broad questions; the source still needs inspection before calling each no justified. |
| Reader yes → coverage no, `independent_sufficiency=null` | First checker rejected coverage. It might be right or over-strict; compare its named missing claim with the actual evidence. |
| Coverage positive then independent sufficiency false | Second checker vetoed it; examine that rationale. |
| Validation failures / not assessed | Software/assessment failure, not evidence the scientific question was answered no. |
| Lookup majority, most no verdicts and source operations in that group | Supports the objective-mismatch cycle as the dominant workload/cost explanation; does not alone prove the effect of a replacement policy. |
| Measurement majority but few instrument result events | Routing, availability or execution becomes the primary candidate; question generation alone is not the dominant bottleneck. |
| Measurement questions produce results but receive no for unrelated documented claims | Compare the exact original question and checker requirements; supports a mismatch in review scope if those claims were never requested. |
| Many yes lookups and no new measured results | Improved factual answer rate would still fail Gloria's goal. |
| Mostly mixed/unclear classification | Inspect emitted questions manually; a confident binary percentage would be unsupported. |
| Few/no source IDs, literature or full-text passages | Evidence availability/routing is a candidate; an empty list alone does not prove evidence was lost in transit. |
| `files_changed_during_read=true` or parse errors | Live writes/partial lines or missing inputs prevent treating this as an atomic census. Summary says exactly which input failed. |

## What would prove this diagnosis wrong

If the classified live workload is predominantly measurement questions, the claim
that documented-fact generation dominates this period is wrong; trace their
execution and review instead. If most source cost is prerequisite material for
completed new measurements, describing it as repetitive factual retrieval is wrong.
If measurement results already dominate and novelty is independently evident in
their artifacts, the problem is reporting/assessment rather than absence of output.

The post-planning broadening mechanism is reproduced, but if the deployed binder
differs or no such inquiries reached it, it explains none of this period's failures.
If the probe's named refusals all match actual retrieval targets, incidental-word
matching is not supported as their cause. If prompts from an independently retained
request log show that every relevant attempt included every held name, missing
prompt context is ruled out for those attempts; this suite cannot establish model
obedience either way. If source receipts contain the exact allegedly missing
evidence and the coverage input omits it, evidence delivery rather than question
breadth becomes the supported explanation for those reviews.

Unfinished live attribution is tracked in `docs/open-work.md`. This branch contains
the diagnosis, isolated harness and read-only probe; it does not change production
behavior, model choice, scientific checks, or deployment state.
