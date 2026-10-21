# Brief for a new Claude Code thread: why the Chemistry Lab refuses most of its own work

You are reviewing someone else's three weeks of work on this. Your job is an independent diagnosis, not a
continuation. Claude Code in Gloria's main thread wrote most of the commits listed below and has twice claimed to
have found the root cause. Both claims were wrong. Read the code and data cold, and say plainly if the design
itself is the problem: a planner proposing, a gate refusing, and a list growing.

## The problem, in his own records (Aegis, 24 hours to 21 October ~16:30 CDT)

- 362 inquiries. 252 refused before any source was called; 295 more passes ended `evidence_wait`.
- Why turns ended without a source call: **spent subject 317**, same lookup 85, already asked 68, other 63,
  held/unchanged evidence 14, nothing eligible 3.
- Reviews: **19 yes**, 248 no, 35 not assessed, 1 not established. About 6% of reviews say the evidence answered
  the question.
- `spent-subjects.json`: 1,523 subjects ever; **230 held right now** (held 24 h each); ages newest 0.1 h, median
  155 h, oldest 588 h.
- `dead_ends()` reads the notebook's last 512 KB, which is **157 rows covering only ~2 hours**, with 0 answered
  reviews in them. (A hypothesis that the run ratchets across days was tested against this and is **false**; that
  change was reverted, 5500a97 → 35a99c9. Do not re-propose it.)
- Faults are a separate, smaller matter (43 in 24 h, mostly one-offs). They are not the subject here.

Gloria's words: "This is week three now of you not fixing the Lab." The refusal/repeat problem has been worked on
continuously since 30 September. **Over 40 commits** targeted it, among them:

```
849ee7f 10-14 the planner is shown every spent subject, newest first
40a25cb 10-14 a tool or measure is never a spent subject; refusals name the subject
2faeff6 10-12 tell the planner a family is spent
344774a 10-13 held questions expire and the planner sees them all
b51699a 10-16 Lab planner sees the whole week it is refused against
763eb65 10-17 a refused pass falls back to a fresh real protein even while something is held
87df5e0 10-19 a held follow-up no longer takes every pass
396f48f 10-09 Close Lab repeat escapes at final inquiry acceptance
42239bb 10-08 Count refused Lab inquiries toward exhausted-thread recovery
7d43123       a spent subject is held for a day and is not sent a third time
```

Each one fixed a mechanism and the numbers above are what remains. Read `git log --since=2026-09-30 --
scripts/chemistry_lab.py scripts/lab_repeats.py` before proposing anything: **a proposal that repeats one of
these is not useful.** For each idea, say which earlier commit is closest and why yours is different.

## Where it lives

Repository `gloriaariayvette-lgtm/Vintos-main`, branch `claude/device-visuals-2026-10-13`.

- `scripts/chemistry_lab.py`
  - `dead_ends()`: which recent subjects are spent
  - `remember_spent`, `spent_subjects`, `spent_families`, `spent_retrieval`: the 24 h hold
  - `_question_holds()`, `_held_subjects()`: questions waiting on changed evidence
  - `_orient()`: picks the cycle's question and builds the planner prompt (the SPENT FOR TODAY and family text)
  - `_plan()`: the model call
  - `_held_to_plan()`: the refusal gate and one re-plan
  - `review_answered()`: what counts as an answered review
- `scripts/lab_repeats.py`: `repeat()`, `frontier_step()`, `on_frontier()`
- `scripts/lab_lines.py`: lines of inquiry; an open line is exempt from the spent gate (`active_line`)
- Notebook rows: kinds `inquiry`, `inquiry_refused` (with `why`), `evidence_wait`, `reflection` (with
  `answers_question`, which begins yes/no/not assessed)

## The two questions to answer, with evidence

1. **Why does the planner keep proposing subjects it is told are spent (317 times in a day)?** It is given every
   spent name and the spent families, then re-planned once on refusal. Is the list too long to obey, is it being
   ignored, are the subjects matched too broadly (a word in his question matched as a subject), or is the
   re-plan the source of the repeats?
2. **Why do 94% of reviews say no?** Every unanswered question feeds the spent list, so this may be the upstream
   cause. Are the questions ones his instruments (UniProt, PDB, ChEMBL, Europe PMC, NCBI) cannot answer, such as
   broad prose like "What are the specific structural hallmarks, documented cellular roles, and source-backed
   relationships of…", which recurs constantly? Is the review stricter than the evidence warrants? Or is the
   evidence not reaching the review?

## Rules (from the repository's CLAUDE.md; non-negotiable)

- **Investigate before changing.** The deliverable is a diagnosis with evidence (file:line, and what the data
  shows), plus at most one proposed change, a test for it, and the number you expect it to move by how much.
  Say what result would prove you wrong.
- **Nothing on Aegis is reachable from your environment.** Where you need his data, write a short **read-only**
  probe for Gloria to run, saying exactly what each possible answer would mean. She will run it and bring the
  output back.
- **Do not push to `claude/device-visuals-2026-10-13` and do not deploy.** Put any code on a branch of your own
  (named below). Claude Code in her main thread reviews it before anything ships.
- **Do not change which model anything uses.** The Lab planner is Sonnet 5.5 by her choice. No Fable. No new paid
  model calls in the fix.
- **Tests never reach the world.** Any suite under `broker/tests/` repoints every path it writes to a scratch
  HOME, stubs every sender and network call (`socket.socket.connect` refused), and asserts that isolation in the
  suite itself. It runs on the host that serves her, beside her real workspace.
- **Do not weaken a scientific check to get a number down.** Identity checks, the identical-lookup gate and
  evidence requirements stay. Fewer refusals by letting bad science through is not a fix.
- **Do not add gates she didn't ask for.**
- Never ask Gloria to send Vintos a message to produce test data.

## Your branch and your report

- Branch: `claude/lab-refusals-review` (from `claude/device-visuals-2026-10-13`).
- Report, in this order:
  1. The root cause in one paragraph.
  2. The evidence for it.
  3. Why the earlier commits didn't hold.
  4. Any read-only probes for Gloria.
  5. One proposed change, with its test and the expected effect on the numbers above.
  6. What you are unsure of.
- Keep design and root cause yourself. Do not open a large refactor.
