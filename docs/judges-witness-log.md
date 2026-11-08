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

## 8 November 2026 — avatar capture hook, private scratch only

Rebased the capture increment onto Claude's integrated deploy tip `1b28c3d4`
as requested in note 5. The primitives commit is now `78e2800c`. The only rebase
conflict was generated ownership documentation, resolved by regeneration.

Attached one request-local capture to all three avatar router calls. Selection
follows retry decisions; finalization follows the final reply guard and binds
the exact returned text. The optional sink is disabled by default, requires a
matching private scratch workspace, rejects live/repository/symlink roots and
creates owner-only packets. Supplied provenance and test mode are retained.
Observer and sink errors do not alter the reply. Transport remains distinct
from delivery, and incomplete context/attempt history is still explicit.

The integrated tree uses a server symlink; editing its bin target preserves
both spellings. Tests execute actual capture-related handler segments with a
stubbed provider, including postprocessing and final-guard text changes. This
is not a full HTTP application test, real capture, or evidence of completeness
on other surfaces. Existing feeds and stores remain unchanged.

Validation: capture hooks 7/7, capture primitives 8/8, strict witness 35/35,
router regressions 15/15, canonical avatar 6/6, avatar lifecycle 29/29 and
entry ownership 11/11: **111 checks passed**. Generated reports and whitespace
checks are current. All are
OS-isolated synthetic checks. Full Aegis suite and independent review remain
Claude Code's step. Context dependencies, source-store integration and remaining
surfaces are still pending; no production activation, merge or deployment.

## 8 November 2026 — scratch capture to offline census

Kept capture-hook review tip `01078956` fixed. Continued on the separate stacked
branch `codex/judges-capture-replay`. The offline replay now accepts explicitly
supplied capture packets and merges their context/reply nodes without overwriting
conflicting attestations. Existing canonical/merged/ledger adapters and strict
admission are unchanged. Current packets remain held: a framework handoff is
not delivery, and incomplete ancestry is not clean evidence.

Synthetic private-sink-to-CLI replay, restart equality, source immutability,
provenance exclusions and conflicting-node checks pass. Capture replay **6/6**
and existing witness **35/35**, OS-isolated: **41 checks passed**. No model calls
or real snapshots. Full Aegis suite remains with Claude Code. No live reader,
serving edit, merge or deployment in this increment.

Source tracing confirms that on-message forecasts already carry the turn ID,
surface, arrival time, completion time and checkpoint ID. Their completion can
lag the reply, so the strict join must continue rejecting late forecasts. The
canonical avatar writer runs before the handler's last reply guard: a future
source-store integration cannot blindly attach a later final-text receipt to
earlier stored content. Exact binding and a separate delivery receipt remain
required. These are source findings, not measurements of private records.
