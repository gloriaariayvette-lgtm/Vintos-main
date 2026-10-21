# Lab refusals: independent review (21 October 2026)

Branch `claude/lab-refusals-review`, from `claude/device-visuals-2026-10-13` at fce3103. Nothing pushed elsewhere,
nothing deployed, no model changed.

## 1. Root cause

The Lab tells itself, in three places, to ask a question no instrument can answer, and then treats the
inevitable "no" as proof the subject is exhausted. The planner prompt (fa96b0a, 11 October), the sourced-record
template `_record_connection_question` and the fresh-protein fallback prompt all ask, in ONE question, for a
structural feature, a documented function **and the source-backed relationship between them**. The coverage
checker (correctly) requires a verbatim quote for every part, and a curated record lists features and a function
but never states the link, so the review says no. `dead_ends()` counts every question since the last *yes* review,
refusals included, so with yes at 6% the run is always three or more, and every subject the Lab touches is written
to the 24-hour spent list. The planner's whole context (lines, journal, asked questions, held questions) is about
those same subjects, so it proposes them, and the gate refuses. The design problem is that two subsystems disagree
about what "no" means: the claim-line work (fa96b0a) made a partial review the normal step of a multi-step
connection, while `dead_ends()` (27 September) reads every non-yes review as a dead end. Forty commits worked on the
gate and the list, which are downstream; none touched the instruction that produces the unanswerable question.

## 2. Evidence

- The mandate: `scripts/chemistry_lab.py:1911` before this branch, "Include three claim types: ... and the
  source-backed relationship between them". The same prompt, 50 lines earlier (2b436e6, 16 Oct), says "Ask ONE
  thing its sources can answer whole". The planner is given both.
- The same three-part form is written by code, not only the model: `_record_connection_question`
  (`:2337`), used by `_next_sourced_record` (`:2356`), `_inquiry` (`:3174`, which rewrites any "curated record"
  question into it) and `_resolve_free_record_discovery` (`:3383`); and the `_fresh_free_inquiry` prompt (`:2391`).
  `_next_sourced_record` is what `_orient` runs after every refused or waiting pass (`:1770`, `:1806`), i.e. most
  passes, so the refusal state routes straight into the template that guarantees the next "no".
- The brief's recurring question ("What are the specific structural hallmarks, documented cellular roles, and
  source-backed relationships of ...") is this mandate in the planner's words.
- The checker demands it: "every ... domain or relationship in the question must be covered" with "verbatim quotes
  at their exact evidence addresses" (`:4210`). That is right and stays.
- The narrower cannot see this form. Run against the three shapes above, `second_ask()` returns `''` and `_narrow()`
  returns each unchanged: `_SECOND_ASK` (`:1265`) looks for "and how / and what / compared to", and `_HALLMARKS`
  (`:1270`) needs "hallmarks of X" with nothing between. Only the bare "hallmarks of X" is rewritten (c151f60).
- The run: `dead_ends()` stops only at a *yes* review (`:563`) and counts `inquiry_refused` rows (`:564`). With 248
  no / 35 not assessed / 19 yes, the run is nearly always past `DEAD_END_RUN = 3`, so `_orient` spends up to six
  subjects every cycle (`:1711`). That matches 230 subjects held at once, roughly every subject asked in a day.
- The repository's own records already pointed here: 16 Oct, "11 of 12 reviews partial, each missing a clause no
  source could return"; 17 Oct, "hallmarks" was 41 of 102 reviews. Each was fixed at the narrower, not the source.

What I could not see: Aegis. The shares above are inferred from code and the brief's totals; probe A settles it.

## 3. Why the earlier commits did not hold

They act after the question exists. 849ee7f, 2faeff6, b51699a, 344774a show the planner more of the list; 40a25cb,
396f48f, 7d43123 sharpen the gate; 763eb65, 87df5e0, 42239bb route around refusals. All assume the list is accurate
and the planner should avoid it. But the list is made of subjects that were never exhausted, only asked in a form
that cannot be answered, so every route around it leads back to a new subject asked the same way, which then joins
the list. 2b436e6 (ask one thing) and c151f60 / 64f4469 (hallmarks rewritten, hard-coded fallback fixed) were the
right idea, but left the generator in the prompt, the template and the LLM fallback prompt untouched, and the
narrower's patterns miss the list form, so the three-part question kept being written and kept being reviewed.

## 4. Read-only probe for Gloria

`bin/lab_refusals_probe.py`: standard library only, imports nothing from the Lab, writes nothing, sends nothing.
On Aegis, from wherever this branch can be read:

```sh
git fetch origin claude/lab-refusals-review
git show origin/claude/lab-refusals-review:bin/lab_refusals_probe.py > /tmp/lab_probe.py
python3 -I /tmp/lab_probe.py        # last 24 h; pass 48 for two days
```

What each answer means:

- **A (verdicts by shape).** If `three-claim` + `structure+function` are most reviews with ~0% yes, and `one-ask`
  is well above 6%: this diagnosis holds. **If `one-ask` is also near 6%, I am wrong** about the upstream cause and
  the change below should not ship; read C.
- **B (origin).** How much review volume comes from the template routes vs the planner, i.e. how much of the
  three-part load is code, not model.
- **C (did evidence arrive).** "no" with quoted supports and "relationship" leading the missing list: the evidence
  reaches the checker and the question is the problem. Supports mostly empty: evidence is not reaching the review,
  a different defect.
- **D (spent refusals).** Matched name in the query field: the planner picked a listed subject. Only in prose: the
  gate matches words, not subjects. This answers the brief's question 1 directly.
- **E (the list).** Held subjects never reviewed in the window: refusals alone are spending subjects.

## 5. The one change

Stop writing the relationship into a first question, at its three sources. Nothing else.

- Planner prompt (`:1911`): the connection is still the goal of a protein line, but it is built one claim per
  question; the relationship is asked later, with a source that states it (a structure's contacts at that feature,
  a paper's finding).
- `_record_connection_question`: asks what the record lists as structural features and function. It still opens a
  claim line (`_relational_question` is still true), so fa96b0a's claim tracking keeps working.
- `_fresh_free_inquiry` prompt: the same.

Not touched: the checker, identity checks, the identical-lookup gate, `dead_ends`, the spent list, any model, any
gate. Closest earlier commit is 2b436e6 / c151f60; the difference is that those filtered the question after it was
written and their patterns miss this form, where this removes the instruction and the template that write it.

Test: `broker/tests/test_lab_answerable_first_question.py` (scratch HOME, `_ask` and `urlopen` replaced by a function
that raises, `socket.connect` refused, all asserted in the suite). 15/15 pass; 4 fail against the base branch.
`test_lab_claim_progress.py` pinned the old template ("relationship" in the question) and is updated to the new
one. Every `broker/tests/test_lab_*.py` and `test_chemistry_lab.py` passes.

Expected effect, 48 hours after deploy: three-claim reviews below 5% of reviews; yes rate from 6% to about the
`one-ask` yes rate probe A reports (I expect 20% or more); spent-subject turn-ends from 317 a day to under 200; held
subjects from 230 to under 150, because an answered review ends a `dead_ends` run. If three-claim reviews fall but
yes stays under 10%, the cause is in the review or the evidence path, not the question, and I was wrong.

## 6. What I am unsure of

- The shares in A–E. I reasoned from code and the brief's totals; the probe is the test.
- The planner text in fa96b0a is committed under Gloria's name. If "include three claim types" was her own wording
  rather than an agent's, this rewrites her design and she should say whether the line-by-line reading keeps her
  intent.
- With the relationship out of the template, an auto-claim line from that template closes "answered" once structure
  and function are quoted (`lab_lines.py:390`), so the relationship is not tracked as an open claim; the planner is
  told to ask it later, but nothing enforces it.
- The planner may still write the three-part form from habit or journal context. If probe A after deploy shows it,
  the next step is teaching `_narrow` the list form, not a gate.
- Even with answerable questions, `dead_ends` counts refusals toward a run. That may still over-spend; I left it,
  since one change is the rule and the probe (E) will show whether it matters once yes rises.
- Default `LLM_MODEL` in the file is local Gemma; the brief says the planner is Sonnet 5.5 via her configuration.
  I did not touch either.
