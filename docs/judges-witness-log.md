# Judges witness implementation log

## 8 November 2026 — first offline contracts

Branch `codex/judges-witness-slices`, based on shared branch commit `2ec82c5c`.
Accepted coordination notes 1 and 2. Scope is the offline foundation of slices
1 and 2; it does not claim completed production instrumentation.

- Added strict admission and allowlisted generation/context-effect receipt
  contracts. Actual served identity is never filled from requested configuration.
- Preserved supplied receipts through provenance normalization and merged-chat
  carrying. Existing global legacy eligibility remains unchanged.
- Added explicit snapshot adapters, duplicate-safe evidence census, descriptive
  behaviour receipt and a causal on-message innovation reader using supplied
  frozen embeddings. Missing evidence is counted, not guessed.
- Protected scratch execution and covered indirect effects, unknown evidence,
  temporal boundaries, repeatability, rename/subprocess/network and write limits.
- No real-data run, fit, model call, production write, scheduled worker or feed
  substitution. Synthetic fixture errors are contract checks, not accuracy results.

The detailed contract, runnable command and outstanding capture hooks are in
[the experiment README](../experiments/judges-witness/README.md). The next step
is independent review of these contracts before hooking producer paths. Full
Aegis suite and test merge belong to Claude Code; neither is claimed here.

Validation on the Mac through `scripts/run_isolated_test.py`: witness 21/21,
provenance 11/11, merged chat 26/26, entry owners 11/11: **69 checks passed across
four focused suites**. Generated ownership/untested reports refreshed; diff
whitespace check passed. Scratch restart produced byte-identical aggregate
reports from the same synthetic input. These are correctness/isolation checks,
not evidence of real-data predictive accuracy.

## 8 November 2026 — follow-up contract hardening

While independent review remains pending, source reconnaissance identified the
ledger's explicit `generated_output_witness_eligible` denial field. Preserve it
through merged chat and honor false in the new strict reader even alongside a
permissive provenance envelope. Tighten causal joins: past context must precede
the current message arrival, and that arrival cannot follow generation start.
This changes neither live legacy eligibility nor the underlying turn feeds.

Re-ran the two affected OS-isolated suites: witness **23/23**, merged chat
**27/27**. Synthetic-only; no provider hooks or real-data run added. Earlier
provenance/ownership results remain as recorded above; the full Aegis suite is
still Claude Code's review step.

## 8 November 2026 — independent review fixes

Addressed review note 3 against the first batch, preserving the intervening
causal/denial fixes. New witness admission now also requires existing evidence
standing and honors tactical origins plus all named exclusion flags. Added
dependency fallback to explicit unknown and included the pure receipt module in
future persistence-sprint bundles. Existing sealed bundles/artifacts were not
changed or re-evaluated.

Context ancestry now memoizes shared nodes, validates each edge's time, requires
a context root, and includes reply nodes that propagate direct and inherited
influence. Added agreeing envelope-ID joins, per-copy duplicate hold reasons,
and separately attested final text/digest support for device-annotated stores.
The projection carries these optional fields and original ancestry/exclusions;
production finalization capture remains pending.

Claude reports independent test merges for the earlier 4432b711 revision:
591/591 against deploy and 594/594 against live. These are reviewer-reported
results for that earlier revision, not results for this fix commit. Locally,
the affected isolated suites passed: witness 33/33, provenance 11/11, merged
chat 30/30 and persistence sprint 21/21 (**95 checks**). No private inputs,
model calls, live writes, merge or deployment. Re-review remains with Claude.


## 8 November 2026 — offline approval and capture primitives

Claude's note 4 approves c6591481 for the offline slice, reporting 591/591 and
594/594 test-merge suites. Integration belongs to Claude; this checkout has not
merged or deployed. The next increment is on `codex/judges-capture-hooks`, based
on c6591481.

The reviewer checked key presence only and reports that newly retained ancestry
and exclusion keys are absent in live stores today. Once producers emit them,
existing latent-feed/self-head evidence readers will exclude corresponding
ineligible rows. That is the intended protection effect of preserving metadata;
it is not a claim that those future exclusions have no downstream effect.

Implemented the two carry-forward low findings: exact final text must agree with
stored content (ledger-only suffix allowed), and reply-shaped ordinary-source
nodes are held. Added a pure request-local capture object, observed identity
metadata in response parsers, and an optional noninterfering router observer.
Finalization keeps transport separate; context/reply ancestry and attempt
coverage remain incomplete. No sink or server hook enabled yet.

Focused OS-isolated checks: capture 8/8, witness 35/35, router regressions 15/15,
entry owners 11/11 (**69 checks**). All fixtures/senders synthetic. Next: attach
the request-local object and exact finalization to the handler after its final
guard, test the complete path against stubs, and keep both server spellings in
parity. No paid calls, real messages or live writes.
