# Gloria's three criteria: pre-registered evaluation

Written 2026-11-14, before any network of this benchmark was generated. It supersedes the first benchmark
(`PREREGISTRATION.md`, scored once as `results-test.json`, which stays as the record of that attempt) as the
core measure, because Gloria sharpened what "real accuracy" means:

1. **Localization.** A contradiction is traced to the EARLIEST faulty inference, not the last step.
2. **Revision.** That inference is repaired and ONLY the conclusions that depend on it are recomputed;
   the final conclusions are correct.
3. **Preservation.** Unrelated valid reasoning is left intact.

## Data

Synthetic only (`bench_criteria.py`; the repository is public). Every network has valid premises, a main
inference structure, side branches hanging off it, and one or two independent side chains on premises of
their own. One inference step is planted faulty (its premises are right, its conclusion is not), at a depth
drawn uniformly from the main structure's depths; everything that depends on it only through that step is false.

- **chain**: one inference chain three to seven steps deep.
- **dag**: three to six layers, two or three nodes wide, some nodes with an alternative justification.
- **noisy**: a dag with checks of accuracy 0.85, a check that wrongly passes a false conclusion (30%), and a
  wrong witness contradicting something true (50%); contradictions reported at reliability 0.9.
- **two_faults**: a dag with a second faulty step that is neither ancestor nor descendant of the first.

Evidence the method sees: each false conclusion is contradicted (by her or an observation) with chance 0.4,
and at least the deepest one always is; valid conclusions are checked and pass with chance 0.3 (side-branch
leaves 0.6), because valid conclusions get used elsewhere and work out.

- **Development seeds** 0-119 per scenario: used to find and fix failures, as many times as needed.
- **Held-out seeds** 5000-5149 per scenario (600 networks): scored **once**, at the end. The script refuses a
  second scoring.

## Metrics (pooled over all held-out networks, and reported per scenario)

1. **Localization**: over contradictions raised against a false conclusion by a true witness, the share where
   the single most-blamed node is the earliest planted faulty step among that conclusion's ancestors.
   Baseline: **blame the last step** (the step that produced the contradicted conclusion).
2. **Revision**: the recomputed set (the conclusions the method re-derives) against the true dependent set
   (every conclusion made false by a planted fault): precision and recall. **Conclusions correct**: the share
   of all conclusions whose final status (held, or withdrawn) matches the truth.
3. **Preservation**: of the valid nodes (premises and conclusions) that do not depend on a planted fault, the
   share left unchanged: not retracted or lowered, their step not retracted or lowered, not recomputed.
   Reported for **side** nodes (unrelated to the faults) and **upstream** nodes (ancestors of a fault).
   A flag changes nothing in a store and does not count as a change.

## Bars

| Criterion | Metric | Bar |
|---|---|---|
| Localization | top-1 earliest faulty step | >= 0.80, and >= 0.20 above blame-the-last-step |
| Revision | precision of the recomputed set | >= 0.90 |
| Revision | recall of the recomputed set | >= 0.90 |
| Revision | conclusions correct | >= 0.95 |
| Preservation | all independent valid nodes unchanged | >= 0.98 |
| Preservation | side (unrelated) valid nodes unchanged | 1.00 |

## Working rule (Gloria)

When a criterion fails on development seeds, look at the failing cases, find the root cause, fix it, retest on
development, and repeat until the idea is worked through. The held-out seeds are scored once, at the end.
Each iteration and its root cause is logged below as it happens.

## Iteration log

All iterations on development seeds 0-119 (480 networks). Numbers are TMS-Bayes, all scenarios pooled.

**Iteration 1 - the module as first built (passive: it uses only the evidence already recorded).**
Localization 0.59 (blame-the-last-step 0.37); revision precision 0.80, recall 0.92; conclusions correct 0.92;
preservation 0.95, side 0.977, upstream 0.87. Misses (look at the failing cases): about 70% of localization misses
were ties - one contradiction at the end of a line, nothing checked in between, so every step on the line is
equally suspect and the earliest-first rule blamed a valid ancestor. That one wrong blame also caused most of the
precision and preservation losses (the valid ancestor, and what hangs off it, recomputed). Root cause: no rule can
localize what the record does not distinguish. Fix: the module asks the one check that best splits the suspects
- the belief on the contradiction's line whose standing is closest to even, a bisection like git bisect - adds the
answer as evidence and repeats (at most 6 checks per network). In the benchmark the answers come from the truth,
flipped with the scenario's check noise (10%, or 15% in noisy). The passive module stays in the results.

**Iteration 2 - with bisection checks.** Localization 0.79; revision precision 0.94, recall 0.89; conclusions 0.96;
preservation 0.987, side 0.993; 2.5 checks per network. Root causes: (a) two_faults recall: 105 of the missed
dependents were silent - the second planted fault never produced a single contradiction, a generator defect (no
method can recompute what nothing reveals; "at least the deepest one is contradicted" was meant per fault). The
generator now guarantees one contradiction per planted fault. (b) 41 misses blamed a premise: checks only tested
derived beliefs, never the recorded sources under them, so a premise and the first step stayed tied. Checks may now
test recorded sources (never an inference step directly, never her words). (c) One wrong answer could end the search
at 0.80 blame; the search now continues until the culprit holds 0.90 (LOCALIZED_AT).

**Iteration 3 - one contradiction per fault, checks on recorded sources, 0.90 stop.** Localization 0.83 (last step
0.40); revision precision 0.93, recall 0.94; conclusions 0.97; preservation 0.983, side 0.991; 3.6 checks per network.
Every bar passes except side preservation (target 1.00). Failing cases: the side nodes changed were recomputed
because something they rest on (a shared premise, or an ancestor on the faulty line) was wrongly revised; in
two_faults and noisy most such networks had spent the whole budget of 6 checks (two contradictions, or a noisy
answer, need more than 6). Root causes: (a) one budget for the whole network starves the second contradiction;
(b) the "most probable explanation" lowering (added for the first benchmark) still changes suspects that the
checks have not localized. Fixes tried as two variants side by side: a budget of 3 checks per contradiction (12 in
all) in both; variant B also stops lowering unlocalized suspects (they are flagged, and their question logged).

**Iteration 4 - per-contradiction budget; variant B without explanation-lowering.** A: localization 0.83, revision
0.93 / 0.95, conclusions 0.97, preservation 0.984, side 0.991. B: localization 0.83, revision 0.94 / 0.92,
conclusions 0.96, preservation 0.985, side 0.992. Neither fixed side preservation, so both hypotheses were wrong.
Looking at every failing case instead (40 side changes): **all 40 followed a wrong check answer** - a check that
said a valid conclusion failed (10-15% of answers are wrong by design). A single "it fails" answer pushed that
step's blame to 0.5-0.87, the module revised it, and everything resting on it was recomputed. 13 of them also had a
wrong witness. Root cause: one answer was trusted enough to change a source. Fix: corroborate before revising - when
no question is left, every source about to be lowered or retracted gets one more check of something the revision
predicts (the nearest unchecked conclusion resting on that source in every justification, which must fail too if
the source is wrong), or failing that a second, separate opinion on the same conclusion.

**Iteration 5 - corroborate before revising.** A (explanation-lowering kept): localization 0.84, revision 0.96 /
0.94, conclusions 0.97, preservation 0.991, side 0.995; 5.3 checks per network. B (without it): recall fell to 0.89
(noisy 0.76), so explanation-lowering stays. Side preservation halved its error but still misses 1.00. The 19
remaining side changes: every one again began with a wrong answer, and in most the corroborating check could not
tell the difference - it tested a conclusion that was also downstream of the real faulty step, so it failed for the
real fault's sake and "confirmed" the wrong suspect. Root cause: the corroboration did not discriminate between
rival suspects. Fix: the corroborating check must rest on the suspect and on none of its rivals (the other
suspects of the same contradiction).

**Iteration 6 - discriminating corroboration.** Localization 0.86 (noisy 0.77); revision 0.97 / 0.94; conclusions
0.97; preservation 0.993, side 0.9965 (chain 1.00, dag 0.998, two_faults 0.997, noisy 0.993); 5.4 checks per network.
The 12 remaining side changes (8 networks): each still rested on one wrong answer that nothing contradicted - either
no discriminating conclusion existed, or the budget went on another contradiction, and in five of them a wrong
witness was also present. Root cause: a revision could still stand on a single check answer. Fix, as a rule he can
say out loud: no single answer changes his mind on its own. At the end, every revision is re-tested with each check
answer left out in turn; one that would fall below 0.50 without some single answer is held back as a flag, its
question left open, and nothing downstream is recomputed for it.

**Iteration 7 - the single-answer rule.** Preservation 0.998, side 0.9991 (chain and dag 1.00), but revision recall
collapsed to 0.64 and conclusions correct to 0.92: correct revisions were held back too. Failing cases: most held
revisions were right, and fragile only because the search had stopped once the culprit reached 0.90 - one answer
had localized it, and nothing had been asked to back it up. Root cause: the rule was applied after the search
instead of steering it. Fix: while budget remains, a revision that is still fragile gets another corroborating
check (at most two per source), and is held back only if it is still fragile when the checks run out.

**Iteration 8 - corroborate fragile revisions.** Recall only rose to 0.69 (side 0.999). Failing cases (chains mostly):
the corroborating check went to a conclusion further down the line, which fails whether the culprit is this step or
the next one, so it could never remove the fragility; the answer the revision actually hinged on - the check of the
culprit's own conclusion - was never repeated. Root cause: corroborating the wrong thing. Fix: find the single
answer the revision hinges on (the one whose removal breaks it) and ask a second, separate opinion on exactly that.

**Iteration 9 - second opinion on the hinge.** Localization 0.87; revision 0.99 / 0.80; conclusions 0.95;
preservation 0.998, side 0.999. Recall still short. Failing cases (240 networks inspected): every missed dependent
sat in a network with a wrong answer; most were real faults held back because the first and second opinions
disagreed (one of the two was the wrong answer), so the rule correctly refused to act on a 1-1 split. Root cause:
a split vote was left unresolved. Fix: two answers that disagree get a third (at most three opinions on a hinge).

**Iteration 10 - a third opinion.** Localization 0.90 (last step 0.40); revision precision 0.99, recall 0.86;
conclusions 0.96; preservation 0.997, side 0.9988; 6.4 checks per network. Variant B (no explanation-lowering) is
worse on every criterion here and is dropped.
Failing cases for recall (chain especially): the third opinion was asked and went 2-1 the right way, yet the
revision was still held - dropping one of the two agreeing answers leaves a 1-1 tie, so a leave-one-out test can
never be passed by a majority. Root cause: the robustness test was stricter than the rule it stands for. Fix: the
rule is now stated directly - a revision may rest on a check only when at least two separate answers on that belief
agree and outnumber the ones that disagree.

**Iteration 11 - the majority rule.** Localization 0.90 (last step 0.40); revision precision 0.97, recall 0.93;
conclusions 0.97; preservation 0.994, side 0.9975 (chain 1.00, dag 0.9995, two_faults 0.997, noisy 0.994);
6.1 checks per network. Every bar passes except side preservation, still short of 1.00.
Failing cases: the 10 side changes left come from 8 networks, and in every one of them at least two wrong answers
agreed with each other - the same valid conclusion wrongly "failed" twice (2-0), or two of three times (2-1), or two
different wrong answers pointed the same way. The majority rule did what it says; the answers it was given were
wrong. Root cause: the noise floor of a two-answer majority at 10-15% wrong answers. The only lever left is how
much agreement a revision needs, which trades preservation against recall and the number of questions asked.
Iteration 12 measures that trade: a strict variant needing the agreeing answers to lead by two (up to four opinions).

**Iteration 12 - how much agreement.** Strict (lead of two, up to four opinions): side 0.9978 against 0.9975,
recall 0.91 against 0.93, 6.3 checks against 6.1. Asking for more agreement barely moves preservation and costs
recall, because the remaining errors are runs of agreeing wrong answers that a stricter vote also accepts. The
two-answer majority (iteration 11) is kept.

**Where it stands before the held-out run.** All bars pass on development except side preservation (0.9975 against
1.00). Every remaining side error needs two or more wrong check answers that agree. With answers wrong 10-15% of the
time that is the floor for any rule that acts on checks at all; more reliable answers make such runs rarer. The module
is frozen here and the held-out seeds are scored once.

## Held-out result (seeds 5000-5149, 600 networks, scored once at commit c370b3bb)

| Criterion | Metric | TMS-Bayes with checks | Passive (no checks) | Blame the last step | Bar | Met |
|---|---|---|---|---|---|---|
| Localization | earliest faulty step, top-1 | **0.89** | 0.61 | 0.42 | >= 0.80, +0.20 | yes |
| Revision | precision of recomputed set | **0.99** | 0.80 | 0.91 | >= 0.90 | yes |
| Revision | recall of recomputed set | **0.94** | 0.95 | 0.74 | >= 0.90 | yes |
| Revision | conclusions correct | **0.98** | 0.93 | 0.93 | >= 0.95 | yes |
| Preservation | independent valid nodes unchanged | **0.997** | 0.952 | 0.987 | >= 0.98 | yes |
| Preservation | side (unrelated) nodes unchanged | **0.9987** | 0.982 | 0.984 | 1.00 | **no** |

Checks asked: 5.9 per network on average (chain 4.6, dag 4.3, noisy 6.7, two_faults 8.1). By scenario,
localization was chain 0.93, dag 0.91, noisy 0.86, two_faults 0.87; side preservation was 1.00 on chains.
