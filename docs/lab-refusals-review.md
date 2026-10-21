# Lab refusals: independent review (21 October 2026, revised for the novel-findings goal)

Branch `claude/lab-refusals-review`, on `claude/device-visuals-2026-10-13` at d62737f. Nothing deployed, no model
changed, no gate added. The first version of this review (e51f1df) made the lookup template answerable; by the
goal in the updated brief that is a fix that cuts refusals while leaving him running lookups, so it is withdrawn.

## 1. Root cause, against the goal

The continuous Lab is built as a lookup machine and graded as one, so it cannot produce novel findings, and its
failures to look things up become refusals. Every turn starts with a UniProt browse (`chemistry_lab.py` browse
phase); the only computation on the default path is an ESM-C embedding the notebook itself labels
"model_derived_representation_not_biological_finding"; and the review asks only "is every part of the question
supported by a verbatim quote from the sources" (`_coverage_request`). That contract can say yes only to something
already written down. A lookup the records cover whole gets yes and finds nothing new; one they do not cover gets no,
`dead_ends()` spends its subject (it counts every question since the last yes, refusals included), and the planner is
pushed to the next lookup. 94% no, 317 spent-subject refusals and 230 held subjects are that loop. The instruments
that would produce findings exist (reference_compare: his model against an experimental structure, TM-score and
RMSD; fold_read; sequence alignment; ESM-C mutation landscape; the genome-locus screen), run locally, and are even
exempt from the spent gate (`spent_retrieval`: "a new instrument can advance an exhausted subject"), but no question
generator produces them except one regex-shaped saved line step. The prediction-then-experiment shape she wants
exists only in the four-a-day frontier sessions (`chemistry_session.py`), and their next step is handed back to the
lookup engine for six cycles (`lab_repeats.frontier_step`).

## 2. Evidence (file:line on this branch)

- Generators, all retrieval:
  - planner `task` (`_orient`, ~`:1860`–`:1934`): a 70-line menu of sources; the instrument menu is appended at the
    end, and `instrument_query` is missing from "Return keys in this order" (browse_lane, uniprot_query, question,
    why_now, source_query, plugin_query, material_terms). The three-claim instruction (`:1915`) asks for documented
    feature, documented function and their documented relationship: a lookup by construction.
  - `_record_connection_question`, `concrete_ask`, `_fresh_free_inquiry` (with its 40-protein list), and `_inquiry`
    (rewrites any "curated record" question into the template): record lookups.
  - `_next_sourced_record` strips `instrument_query` from its inquiry and sends it straight to review
    (browse phase, "exact_previously_sourced_record"). It is the recovery after every refused or waiting pass,
    and 547 passes in the day ended refused or waiting, so it is the path most passes take.
  - The only measurement generator, `_next_assigned_model_step`, fires only for a line whose `next_step` matches
    `fold_read N-M on ACC-hash` exactly.
- Instruments are hidden: `lab_instruments.menu_block` lists 5 recent files; runs are capped at 25 a day
  (`DAILY_RUNS`), against 362 inquiries.
- The review cannot see novelty: nothing in `_reflect` or the coverage contract asks what this turn found that was
  not known; the only novelty clause is a prohibition ("Do not infer novelty from missing literature coverage").
  An instrument receipt is quotable (`source: instrument:<skill>`), so a measurement can be reviewed yes, but a quote
  from UniProt scores the same. The brief asked whether the review asks the right question: it does not.
- The narrower cannot catch the three-claim form (`_SECOND_ASK`, `_HALLMARKS` both return it unchanged; checked).

## 3. Why the earlier commits did not hold

All 40 acted on the list, the gate or the wording of lookups: more names shown (849ee7f, 2faeff6, b51699a, 344774a),
sharper gating (40a25cb, 396f48f, 7d43123), routes around refusals into other lookups (763eb65, 87df5e0, 42239bb),
narrower lookups (2b436e6, c151f60, 64f4469). None changed what kind of question is generated, so each route around
a refusal led to another lookup, which the records covered partly, which spent another subject.

## 4. Read-only probe for Gloria

`bin/lab_refusals_probe.py` (standard library only; reads, never writes or sends):

```sh
git fetch origin claude/lab-refusals-review
git show origin/claude/lab-refusals-review:bin/lab_refusals_probe.py > /tmp/lab_probe.py
python3 -I /tmp/lab_probe.py        # last 24 h; 48 for two days
```

- **F (the baseline that matters):** inquiries by what they ran (instrument vs source vs record lookup), yes reviews
  resting on an instrument's output, instrument runs today of 25, frontier sessions. I expect instrument inquiries
  near zero and measured yes reviews at most a handful a day. If instruments already run most days' 25 and most
  yes reviews rest on them, I am wrong about the root cause.
- **G (does the change have work):** his ESMFold models, and how many pair today with a deposited structure the
  Lab has already saved receipts for. Dozens: the change fills the day's runs. Near zero: it does nothing until he
  folds proteins that have structures, and the next change belongs there.
- **A–E** (kept from the first pass): verdicts by question shape, where reviewed questions come from, whether
  evidence reached the checker, what the spent gate matched, what the spent list is made of.

## 5. The one change

`_next_held_measurement` (`chemistry_lab.py`), tried before `_next_sourced_record` in both free-pass recoveries of
`_orient`. When the Lab holds his ESMFold model of a protein and has already saved an archive receipt mapping a PDB
entry to that protein and a structure receipt with that chain's residue range, the pass compares them with
`reference_compare` (local, on Aegis): "What TM-score and RMSD does his ESMFold model of X give against deposited
structure Y chain C, residues a-b?" That is a prediction tested against a measured structure, his instrument's
output, quotable in review.

- No search to find the pair: only saved receipts and artifacts. One structure file is read by the compare itself.
- Inside the existing 25 runs a day; an identical comparison is refused by the existing repeat gate; admission goes
  through `_held_to_plan` unchanged. Identity checks, the checker and the spent list are untouched. No model call
  is added; the planner and its model are unchanged.
- Closest earlier commit: `_next_assigned_model_step` (saved fold_read steps). Difference: that only runs a step a
  line wrote in one exact form; this finds measurable pairs in what the Lab already holds, on the path most passes
  take. 763eb65 / 64f4469 also changed the after-refusal fallback, but to another lookup.

Test: `broker/tests/test_lab_held_measurement.py` (scratch HOME; `_ask`, `urlopen` and `lab_instruments.run`
replaced by a function that raises; `socket.connect` refused; all asserted). 17/17. Every Lab suite passes.

Expected effect, judged by novel findings: measured reviews from probe F's baseline (I expect ~0 to a few a day) to
up to the day's 25 runs, bounded by probe G's pair count, with most comparisons reviewed yes because the receipt
states the numbers asked for. Refusals fall somewhat, as a side effect: those passes run instead of waiting.
**Wrong if** G shows pairs but F, two days after deploy, shows fewer than 5 measured yes reviews a day: then
the comparisons are failing (compare errors, review not crediting the receipt) and that is where to look.

## 6. What I am unsure of, and what comes next

- The pair count. If he rarely folds proteins with deposited structures, this has little to work on; the next
  change is to fold the proteins the Lab already has structure receipts for, which is a Mac cost she would choose.
- The planner itself still generates lookups. Making `instrument_query` part of its output contract and telling it
  what the Lab is for (measure, compare, test a prediction) is the second change; I kept to one.
- The review still cannot say "this was new". A finding field that separates instrument output from quoted
  documentation would let the Lab count novel findings itself instead of a probe.
- `dead_ends()` still spends subjects on lookups that fail. With measurements exempt from the spent gate this
  matters less; I left it.
- 25 runs a day caps novel findings from the continuous Lab at 25. That limit is hers; I did not touch it.
- Default `LLM_MODEL` in the file is local Gemma; the brief says the planner is Sonnet 5.5 by her configuration.
