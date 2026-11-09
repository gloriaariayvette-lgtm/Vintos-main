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

## 8 November 2026 — ambiguous attempt selection remains unknown

Source review and a pure synthetic reproduction exposed an attribution ambiguity:
two distinct observed attempts with identical raw text were resolved to the last
one. The handler currently supplies text, not a selected attempt ID, so that
choice was unsupported. Capture now requires a unique raw-text match; otherwise
the generation receipt stays unknown. Same-model duplicate attempts are also
ambiguous. No reply, routing, legacy eligibility or feed changes.

This is a conservative stopgap until explicit per-invocation identity is passed
by the handler; it does not claim complete fallback coverage. The prior hook tip
stays fixed for review; this follow-up is on `codex/judges-capture-replay`.
Validation: capture 9/9, hook integration 7/7, offline capture replay 6/6 and
ownership 11/11: **33 OS-isolated checks passed**. Reports regenerated; whitespace
clean. No real data, provider calls or live changes.

## 8 November 2026 — reviewer note 6 repairs

Claude's independent suite found the shared result-contract regression in
01078956: reviewer-reported totals were 592/593 on deploy and 595/596 on live.
The shared constructor had gained observation fields outside its declared keys.
Restored `bin/gen_result.py` exactly to integrated base `1b28c3d4`. Observation
metadata now belongs only to the router adapter, preserving the shim wire shape.
Direct provider metadata and unverified relay claims are distinct; relay claims
never become served identity. Private packets retain those claims separately.

The observer receives a deep copy, with cyclic stage references preserved, so
mutation cannot change the caller's reply or status. The sink writes and syncs
a private temporary file, then atomically publishes by linking to the final name.
This is the no-overwrite equivalent of temporary-plus-rename: a preexisting name
is refused rather than replaced. Caught failures unlink the temporary file.
An abrupt kill can leave a hidden temporary file, not a published JSON packet.

Regression checks include exact shared parser keys, actual direct/relay router
paths, observer mutation of a cyclic stage, partial write/full-disk failure,
sync failure, publish failure and preexisting final-file preservation. No live
calls or stores. Re-review and the full Aegis suite remain Claude's step.
Final local validation: shared contract **52/52**, capture **10/10**, hook/sink
**9/9**, offline adapter **6/6**, witness **35/35**, router **15/15**, ownership
**11/11**: **138 OS-isolated checks passed**. Generated reports and whitespace
checks are current. No merge or deployment.

## 8 November 2026 — approved capture base; explicit source origins

Claude note 7 approves f51b1d3d, reporting full isolated suites 594/594 against
deploy and 597/597 against live, integrated as `6e452ae6`. Started
`codex/judges-context-receipts` from that integrated tip; no merge/deploy by Codex.

Ordinary external leaves now require an explicit allowlisted origin and exact
source-version digest. Added a pure constructor for known counterpart input,
sensor observations and operator configuration. Bare or unsupported origins
remain unknown, including an unmarked generated reply. Generated material must
use its dependency graph; no legacy backfill or live eligibility changes.
Producer hooks and complete context/effect ancestry remain unfinished.

Synthetic Mac scratch benchmark of the full finish_shadow path including fsync:
100 measured calls after 5 warmups, 0.510 ms median, 0.564 ms p95, 0.637 ms max;
105 synthetic packets, private temporary directory removed afterward. This is
one local filesystem sample, not Aegis latency or permission to enable a harness.

The prescribed SSH route failed authentication. No alternate route was used and
no private inputs were read. Real-snapshot census and Aegis latency measurement
remain blocked pending authorized access or Claude's scratch execution. No real
data numbers are claimed. Required blocker notification was delivered.
Focused validation: strict witness 37/37, capture replay 6/6, existing provenance
11/11 and ownership 11/11: **65 isolated checks passed**. Reports regenerated;
whitespace clean. Full Aegis review remains pending for this increment.

## 8 November 2026 — explicit invocation selection and observed dependencies

Continued on `codex/judges-request-dependencies`, stacked on 239c3467; the prior
review tip is untouched. Approved integrated base remains 6e452ae6. No review
wait: further increments use new branches while independent review proceeds.

The avatar handler now carries the exact invocation token through primary,
repeat and replacement paths. The observer identifies the returned-root attempt
by identity, including self-referential stage lists. Handler selection additionally
checks the raw digest. Equal text across attempts no longer guesses identity;
missing/foreign/invalidated tokens remain unknown. Failed replacements retain
the original selected token; discarded repeats clear it. Request ID and exact
handler-argument fingerprint survive the generation receipt, normalization and
merge. The shared result schema and router return tuple remain unchanged.

Private scratch packets now include ordered input fingerprints, invocation/result
nodes, retry dependencies, the existing context-local offer receipt (never
mistaken for admission), a direct tactical-provenance effect edge, observed
attempt metadata even without selection, and the raw-to-final digest change.
No request endpoint/auth material, prompt text or offer-error prose is added.
Existing final reply content remains only in the private packet. Unknown input
origin stays unknown, including user-role history. The finalized aggregate DAG
is explicitly incomplete; it is not a clean pre-generation context attestation.
Full provider-internal retries, upstream organ/value-map ancestry, admission and
client acknowledgement remain open. No feeds, routing choices or models change.

Correction to the previous entry: the authentication failure was for the wrong
login, not a demonstrated lack of access. The already-authorized Mac agent route
passed a constant-output access check; no private records were read or copied.
After reading coordination note 9, left the copied-record census and Aegis timing
measurement to Claude's reviewer, without duplicating that work or running more
remote commands. This is ownership of concurrent work, not a blocker.

Validation: capture 18/18; actual handler segments and sink 12/12; offline adapter
6/6; witness 38/38; shared result contract 52/52; provenance 11/11; router 15/15;
ownership 11/11: **163 OS-isolated checks passed**. Handler tests execute selected
actual AST segments with stubbed routing, not a full HTTP service or model call.
Generated reports are current and whitespace is clean. Claude owns the full
isolated Aegis suites and integration; Gloria deploys. No merge or deployment.

## 8 November 2026 — explicit counterpart fragments on a new producer branch

Continued on `codex/judges-producer-origins` from 113cfc69, leaving the invocation
review tip untouched. The scratch avatar hook now binds the explicitly supplied
original-text field to an exact span of the actual current-message input. It
records the source digest and exact message version/slot/part/span. A missing
origin marker stays unknown; there is no fallback to composed message text.

Repeated/ambiguous spans, changed versions, shifted slots, history matches and
nontext parts do not acquire external origin. Retry instructions remain unknown.
Only the explicit fragment gets the external leaf: the assembled prompt/context
retains incomplete ancestry. Nothing is enabled, sent, merged or deployed, and
no live store or private record is accessed. Claude's copied-record census and
Aegis timing task remain his concurrent work, not duplicated here.

Validation: capture 24/24; actual handler/sink 14/14; capture replay 6/6; witness
38/38; provenance 11/11; ownership 11/11: **104 isolated checks passed**. Cases
include Unicode spans, structured text beside an image, missing and duplicated
originals, stale bindings, retries, and observation failure leaving the reply
unchanged. Reports regenerated; whitespace clean. This validates synthetic
contracts, not real-turn eligibility or a full serving HTTP request.

## 8 November 2026 — parentless generated ancestry repaired

Claude note 10 confirmed the source-origin increment integrated at 239c3467 and
identified a remaining clean-base-case error: a parentless value-map/context
node could still terminate the graph as clean. On the new stacked branch
`codex/judges-ancestry-leaves`, all parentless non-external node kinds now remain
unknown. Only an allowlisted ordinary-source node with its exact source hash can
terminate a clean ancestry chain. An external sibling cannot hide the missing
parents, in either traversal order. Synthetic clean controls now explicitly
include their external source; the memoized deep-DAG and indirect-influence
controls still pass with complete fixtures.

No historical data, served model, delivery or ancestry is fabricated. This only
changes the new shadow reader, not the existing feeds/eligibility rules. Sealed
experiments are untouched. The dedicated production enablement proposal is
`docs/judges-capture-enable-proposal.md`; it explicitly forbids setting the
scratch workspace variables on a serving service. No enablement is performed.
Claude's real-copy census/timing results are attributed to his note, not rerun.

Validation: witness 40/40, replay adapter 6/6, capture 24/24, handler/sink 14/14,
existing provenance 11/11 and ownership 11/11: **106 isolated checks passed**.
Generated reports and whitespace are clean. Full Aegis suite/review remain
Claude's step; no live writes, enablement, merge or deployment.


## 8 November 2026 — paired forecast-context controls

Continued on `codex/judges-innovation-controls-v2` from f34f4c12, preserving
previous review tips. Added causal last-reply and normalized recent-mean controls
using only explicitly attested forecast-context references. Exact versions,
encoder, eligible same-surface replies and strict order are required. No inferred
history or selected substitute baseline. Missing controls keep the head score
and get their own coverage reasons. Paired errors separate evaluation blocks and
checkpoint groups; they assert neither authenticity nor a pass verdict.

Eight synthetic regression cases cover causal ordering, identity/version,
encoder/surface conflicts, missing inputs, zero means, normalization, uncited
newer history and separate paired coverage. No live producer contract or real-data
accuracy claim is introduced. Independent Aegis validation remains Claude's step.

Validation: witness 48/48, replay adapter 6/6 and ownership 11/11: **65 isolated checks passed**. Whitespace clean. No private data read, live writes, model calls, enablement, merge or deploy.


## 8 November 2026 — bounded shadow behaviour receipts

Continued from 788439c9 on `codex/judges-behaviour-windows`, preserving prior
review tips. The strict census now feeds an optional explicit-window/surface
summary, separated by observed served model and revision. Private manifests bind
every measurement to the exact final response and generation receipt/context;
the CLI also binds the retained input bundle. Aggregates contain ordinal group
counts, word-length summaries and literal question-mark fractions only. Missing
observations remain unknown; snapshot coverage is not stream completeness.

Rebuilds are deterministic and source removal changes membership rather than
leaving stale state. Synthetic cases cover positive observations, empty windows,
midnight boundaries, unknown/mismatched identity, duplicate rejection, cross-model
separation and transitive exclusion when a behaviour receipt later influences a
reply. No live feeds, source capture, LLM calls, fitting or real-data claims.

Validation: witness 56/56, replay adapter 6/6 and ownership 11/11: **73 isolated checks passed**. CLI rebuilds reproduce both aggregate and private manifest bytes with 0600 output permissions. Full Aegis suite and retained-data results remain Claude's independent step.


## 8 November 2026 — explicit feedback receipts

Continued on `codex/judges-feedback-joins` from 0d950e7b. Implemented note 2's
literal laughter marker and high practice-rating joins in the offline replay.
Chat adjacency requires exact final-response identity and producer-attested
consecutive timeline positions, including excluded/intervening events. Practice
ratings require an exact eligible practice version. No time-window or text-prefix
inference. Absent laughter, single ha and 1–3 stars remain unknown, not flops.
Conflicting copies cannot select a favourable label; repeated ratings retain
observations but do not multiply positive targets. Raw feedback text stays in the
private input bundle; output receipts contain only private references/digests.

This adds no live collector or authentication claim. Verified origin and complete
sequence are still a producer obligation; historical capped records cannot be
backfilled by assumption. Existing humor scripts, inference and every live feed
remain untouched. Retained-data measurement/full Aegis review stay with Claude.

Validation: witness 65/65, replay adapter 6/6, ownership 11/11: **82 isolated checks passed**. Includes positive and unknown controls, intervening replies, origin/version/clock errors, duplicate conflicts, strict rating joins and private-file restart/permissions. Whitespace clean; no real-data accuracy or installed behavior claim.


## 8 November 2026 — causal innovation reference repair

Audited the shadow scorer while prior tips remain under review. Five synthetic
regressions reproduced: two forecast-time reference leaks (later/equal-time
outcome), equal-error distinct vectors, different producer attestations with the
same derived summary, and pooled target generators/revisions. On
`codex/judges-causal-innovation` from 608eefb5, reference outcomes must now finish
strictly before the forecast. Complete forecast digests distinguish same-time
conflicts; exact copies still deduplicate. Target served-model/revision groups
are kept separate for references and paired comparisons. Requested identity is
never a substitute. Digests and generator identities remain private.

All five regressions now pass. No retained/private input was read; no result from
the independent self-head audit was recomputed or changed. This corrects the
new offline instrument only, with no live feed or model change.

Validation: witness 70/70, replay adapter 6/6, ownership 11/11: **87 isolated checks passed**. Before the repair the five added cases failed; after it they pass along with existing duplicate, causal batch and paired-control cases. Whitespace clean. Full Aegis review remains pending with Claude.


## 8 November 2026 — reply finalization dependency boundaries

Continued from 0a4162b0 on `codex/judges-finalization-lineage`. The scratch
capture producer now records the exact pre-final-guard digest and the returned
digest as ordered dependency nodes, linked to the selected request/attempt. This
distinguishes edits in the handler from edits across the final guard boundary.
The intermediate text is not retained. Missing selection or a failed pre-guard
observation remains explicit unknown; neither boundary claims complete editor
ancestry, effect execution or delivery. Changed=false means equal boundary bytes,
not proof that nothing ran between them. Existing packet fields remain compatible.

Selection and generation observations cannot move after a finalization boundary.
The actual handler hook is failure-isolated and disabled with existing scratch
capture; its new test executes extracted handler code with synthetic providers.
No production enablement, live store, feed, model, private-data read or send.

Validation: capture 27/27, handler hooks 15/15, replay adapter 6/6, witness 70/70,
ownership 11/11: **129 isolated checks passed**. A prior adapter assertion about
the fixed node count was updated to assert exact deduplicated node identities
after the added boundary node. Generated reports and whitespace checks are clean.
Full Aegis validation and review remain Claude's independent step.


## 8 November 2026 — feedback sequence evidence repair

Continued from e59f9d4d on `codex/judges-feedback-evidence`. Three synthetic
regressions reproduced gaps in the new offline feedback reader: unidentified
events vanished before position collision checks; predecessor timeline denials
were ignored; and an un-witnessed predecessor could borrow the target reply's
eligibility. The reader now keeps every valid claimed stream/position occupied,
including missing/malformed event IDs, and requires direct witnessed sequence
evidence for both sides of a chat join. This is a tightening of the new offline
contract, not a change to existing humor labels or live feeds.

Private observations also retain the exact predecessor-event digest alongside
the feedback-event digest. No raw feedback is copied. Unknown rows in unrelated
streams/positions do not suppress a valid local join. No historical witness
backfill is provided; producers must attest facts they actually observed.

Validation: witness 75/75, replay adapter 6/6 and ownership 11/11: **92 isolated
checks passed**. Three new cases failed before the repair; five additions cover
missing IDs at either position, predecessor denials/missing witnesses, unrelated
positions, and version-bound private receipts. Existing literal-marker, low-rating
unknown, restart, permissions and scratch-only checks still pass. Reports were
regenerated and whitespace checked. No retained data, sends, models, merge or
deploy; independent Aegis validation remains with Claude.


## 8 November 2026 — review 13 capture compatibility repairs

On `codex/judges-capture-compatibility` from 41682138, reproduced the review's
missing prepare symbol failure and an analogous older-router signature failure.
The handler now owns a small exception boundary around observation preparation
at all three route sites. Missing/broken setup, invalid observer options and a
router without the observer parameter disable observation, not generation. No
provider call is repeated to recover from capture failure. This also works when
the installed capture module is too old to contain any new helper.

Known judge effects with incomplete ancestry now report `influenced_incomplete`
(and census reason `influenced_incomplete_lineage`) instead of losing their known
influence under unknown. The distinction propagates through incomplete context
and unknown siblings. Every incomplete case remains excluded; invalid clocks
and unmarked material remain unknown. No clean/admitted population expands.

Validation: handler hooks 18/18, capture 27/27, witness 77/77, replay adapter 6/6,
ownership 11/11: **139 isolated checks passed**. The three compatibility additions
failed before the fix and now pass, including original/retry/replacement paths.
Two influence tests cover missing parents, incomplete enclosing contexts, sibling
order and clock rejection. Reports regenerated; whitespace clean.

Review 13 reports integration through 788439c9 and Aegis suites 594/594 and
597/597. Later increments, including this one, still need independent review/full
Aegis validation. The wants stack remains separately blocked on review 13's source
binding, result freshness, continuation and cost-control fixes; not approved or
deployed by this judges repair. No live stores, calls, merge or deployment.


## 8 November — malformed offline evidence accounting

`codex/judges-malformed-evidence` starts from approved integration cb10d8b8,
leaving all previous review tips and the separate wants stack untouched. The
innovation reader previously raised AttributeError/TypeError for malformed
forecast/head/manifest records or unhashable embedding identities, stopping the
whole replay. Wrong-shaped empty containers could also appear to be valid empty
evidence. Added strict container checks and explicit per-record held accounting.
Unidentified embeddings never get guessed targets; identifiable malformed copies
remain in duplicate/conflict checks so a valid copy cannot hide them.

Five synthetic regressions reproduced three assertion failures and 14 errors
before the repair (subcases). Afterward **144 isolated checks pass**: witness 82,
replay adapter 6, capture 27, capture hooks 18, ownership 11. Fixtures cover malformed
mixed records alongside valid data, missing/unhashable IDs, malformed manifests,
invalid matching vectors in either copy order, and wrong top-level shapes.
Reports regenerated and whitespace checked. No retained-data run, model call,
live write, feed change, merge or deploy. The held identity count is per embedding
row, not per unique reply; README documents that denominator. Independent full
Aegis validation remains with Claude. Review 16's separate wants timestamp fix
was already pushed as de2cd7b4 and remains awaiting that independent rerun.


## 8 November — strict lineage shapes

On `codex/judges-lineage-shapes` from 219c2de9, three synthetic regressions exposed
seven assertion failures and eight errors before the repair (subcases). A reply
node with a truthy non-string or oversized turn ID could pass as clean ancestry;
an unhashable node kind/root could crash traversal; and a nonfinite traversal
boundary could silently defeat its clock comparison. The graph reader now checks
root and reply identities with the receipt identifier contract, checks kind type
before set membership, and parses the boundary with the shared timestamp parser.
Malformed evidence stays unknown. Valid source/reply ancestry, indirect influence
propagation and per-edge causal checks remain unchanged.

**147 isolated checks pass:** witness 85, capture 27, replay adapter 6, handler
hooks 18, ownership 11. Tests include valid positive controls and invalid boolean,
container, oversized and clock cases. Generated reports and whitespace checked.
No private snapshot read, model call, live write, feed change, merge or deploy.
Independent full Aegis validation remains with Claude. The earlier wants fix is
left at de2cd7b4 in its own checkout for his Linux rerun; no duplicate remote work.


## Review 17 — combined tip on the approved wants base

Claude's coordination note 17 reports wants de2cd7b4 approved and integrated,
with full Aegis suite results 600/600 on the deploy checkout and 603/603 on the
live checkout; each previously flaky suite also passed five repeated runs. Those
are reviewer-reported results, not a new run by this branch. Installation/live
acceptance remains with Gloria; integration is not proof of installation.

`codex/judges-review-17` rebases the two subsequent judges repairs onto de2cd7b4.
The only conflict was additive docs/open-work.md content, resolved as a union.
Range-diff confirms the implementation/tests are unchanged; previous pushed tips
remain intact. Malformed-evidence accounting is now 30be79e6 and strict lineage
shapes bad77dae. No extra behavior changes are included in this combined review.

Fresh local validation: **173 checks pass** (witness 85, capture 27, replay adapter
6, hooks 18, ownership 11, want controls 26), plus all **67 wants follow-through
and completion checks under the coarse-clock simulation**. Generated reports and
whitespace verified. The combined tip still requires Claude's independent review
and full isolated Aegis suite. No private inputs, model calls, real test sends,
live writes, merge or deploy were performed here.


## 8 November — depth-consistent shared ancestry

`codex/judges-depth-consistency` continues from the submitted combined tip
c7e9638f, leaving it fixed for independent review. A synthetic graph reproduced
order-dependent admission: traversing a shared ancestor by its short path first
cached clean standing, which was then reused along an over-deep path. Reversing
the root's parents correctly returned unknown. The memo now includes remaining
traversal depth; edge clocks and active-cycle checks still precede cache lookup.
The existing 128-level bound is unchanged and cannot be bypassed by cache order.

**148 isolated checks pass:** witness 86, capture 27, replay adapter 6, hooks 18,
ownership 11. The new regression checks both orders of an over-deep shared graph
and both orders of a valid shorter graph, with fewer than 400 node lookups per
case. The previous 60-level diamond performance bound and causal-edge fixtures
still pass. Reports regenerated and whitespace verified. Synthetic evidence only;
no retained-data read, model call, live write, feed change, merge or deployment.
Full Aegis review remains with Claude; no duplicate remote work was started.


## 8 November — private reproducibility receipt

`codex/judges-run-manifest` continues from fa4dad54 while its review tip remains
fixed. Offline replay now writes a private run receipt binding exact supplied
input bytes, four named scoring files, parsed options, Python version and exact
output bytes. The receipt is written last; code changes detected across scoring
abort before output creation. No scoring, admission or live path changes.

**150 isolated checks pass:** witness 88, capture 27, replay adapter 6, hooks 18,
ownership 11. Tests verify independent hashes/sizes against actual CLI artifacts,
restart determinism and permissions, changed-input/code/settings/output identity,
result tampering, and abort-before-write on a simulated scoring source change.
Reports regenerated and whitespace checked. Synthetic fixtures only. The receipt
stays private and proves neither source authenticity nor complete dependencies.
Full isolated Aegis review remains with the independent reviewer. No retained
input reads, model calls, real test sends, live writes, merge or deployment.


## 8 November — validate every matching embedding copy

`codex/judges-embedding-copy-validity` continues from eefb3764 with prior review
tips fixed. Synthetic fixtures reproduced order-dependent acceptance: a numeric
vector first and a boolean-containing duplicate second compare equal in Python,
so only validating the first copy incorrectly admitted the evidence. Reversing
the copies held it. The same issue affected forecast-context baselines.

Every matching copy now passes finite, numeric, dimension and norm validation.
Malformed target copies hold the forecast; malformed context copies hold only
its paired controls. Valid equal integer/float copies remain usable. Two new
regression methods produced four failures before the repair and pass afterward.
152 affected isolated checks pass: witness 90, capture 27, replay adapter 6,
hooks 18, ownership 11. Reports regenerated and whitespace checked. Evidence is
synthetic, not a claim about live data. No model calls, private snapshots, live
writes, feed changes, merge or deployment. Independent Aegis review remains pending.


## 8 November — exact dependency-copy attestations

`codex/judges-lineage-copy-identity` continues from 7f138cea with prior review
tips untouched. The request/attempt retention trace found no new field loss.
A separate synthetic regression showed dependency snapshot merging used Python
dictionary equality: boolean completeness flags and numeric 0/1 compared equal,
then the later copy replaced the first. The new fixture failed before repair.

Repeated dependency nodes now compare complete JSON attestations with sorted
keys and preserve the first identical copy. Conflicting typed flags abort in
both packet orders and when competing with separately supplied lineage. Object
key ordering stays harmless. This is the existing strict conflict policy, not
a new live evidence gate. Exact JSON comparison also distinguishes 1 from 1.0.

184 isolated checks pass: witness 90, capture 27, replay adapter 8, hooks 18,
merge retention 30, ownership 11. Reports regenerated and whitespace checked.
Only synthetic evidence was used; no claim of a live-data occurrence. Full
Aegis validation remains with the reviewer. No private input read, model call,
real test send, live write, feed change, merge or deployment.


## 8 November — current slice review map

`codex/judges-current-review-map` continues from 0ab38cdf without modifying the
submitted code. The replay guide's opening and next-increment list were stale:
they said capture hooks were absent and listed already implemented paired controls
and witnessed-feedback contracts as future work. Updated those sections, listed
all four source adapters and private outputs, and added a component-by-component
map separating implemented contracts from producer coverage and live acceptance.

The actual remaining gaps are explicit: complete assembled-context/indirect
ancestry, provider-attempt coverage, trustworthy delivery acknowledgement,
independently verified retained evidence, and separately approved production
shadow enablement. None can be replaced by passing synthetic tests. Note 17's
wants integration does not approve later judges repairs. No new tests were run
for this documentation-only change; the map attributes 184 passing local checks
to the prior code tip rather than claiming a fresh run. Relative links and
whitespace checked. No production commands, configuration or code changed.


## 8 November — independent evidence coverage counts

`codex/judges-evidence-coverage` continues from af247ebb, keeping prior review tips
fixed. The census's first admission failure is useful for disjoint hold counts
but hides later missing evidence: an unconfirmed delivery can conceal unknown
served identity, request binding and context ancestry. Added independent per-copy
coverage for receipt state, identity/surface binding, observed generator, selected
request/input hash, delivery, response binding and context lineage.

Unknown/malformed/conflicting receipts do not supply selected facts. All supplied
assistant copies, including excluded/duplicate/out-of-cutoff copies, contribute
to coverage; they do not become eligible. User rows do not contribute. Four new
synthetic regressions verify hidden gaps, duplicate/excluded denominators, receipt
conflicts and binding mismatches. Admission and the existing hold reasons remain
unchanged. Coverage reports contain only statuses and counts.

158 isolated checks pass: witness 94, capture 27, replay adapter 8, hooks 18,
ownership 11. Reports regenerated and whitespace checked. No private evidence
was read and no actual-coverage result is claimed. Full isolated Aegis review
remains pending. No model calls, test sends, live writes, feed changes, merge or
deployment. Production capture enablement remains a separate decision.


## 8 November — reject ambiguous snapshot JSON

`codex/judges-strict-snapshot-json` continues from b89743f4, leaving earlier review
tips fixed. Source-to-replay inspection found the standard parser could discard
contradictory evidence before admission: duplicate keys silently kept the last
value. Four synthetic CLI bundles, including opposite provenance-denial orders,
were accepted before the repair and now abort before reports are created.

The loader rejects duplicate keys at any depth (even equal values), nonfinite
constants/overflowing floats and non-object roots. Error text does not echo keys
or values. Valid input bytes and valid-record scoring remain unchanged. Two new
test methods cover CLI refusal/no output/input preservation/error privacy and
finite/unambiguous object contracts. No live-data occurrence is claimed.

160 isolated checks pass: witness 96, capture 27, replay adapter 8, hooks 18,
ownership 11. Reports regenerated and whitespace checked. No private snapshot
read, model call, real test send, live write, feed change, merge or deployment.
Independent review/full Aegis suite remain pending; capture is still disabled
outside explicit scratch.


## 8 November — capture-to-coverage integration acceptance

`codex/judges-capture-coverage-integration` continues from ef2c9c8d without changing
production code. A new synthetic end-to-end test builds two request-local captures,
each with a failed first attempt and selected fallback, through `begin_shadow`,
`prepare_shadow` and `finish_shadow`. One selected result has observed identity;
the other has only a relay claim. Exact request/input hashes and failed-attempt
retention are checked on the persisted private packets before CLI replay.

Replay reports both request bindings, one observed/one unknown generator and two
unknown ancestries. With original unconfirmed delivery, neither reply is admitted.
With explicitly invented delivery attestations, one stays held for unknown served
identity and the other for unknown lineage. No forecast scores are manufactured.
Aggregate/stdout checks exclude synthetic private names and text, and every output
file is mode 0600. All 9 capture/replay integration tests pass. The production code
is unchanged from ef2c9c8d (its earlier 160-check validation is not a new run here).
Reports regenerated and whitespace checked. No private data, model calls, test
sends, live writes, merge or deploy; independent full Aegis review remains pending.


## 8 November — honor explicitly supplied final-reply ancestry

`codex/judges-final-reply-lineage` continues from 8299a02e, keeping earlier review
tips fixed. Two new synthetic regression methods exposed seven failed assertions:
a clean pre-generation context could admit a supplied final reply node whose
own influence, version binding or graph record contradicted that admission.

The strict reader now checks supplied reply nodes against the exact turn, context,
response hash, final timestamp and retained graph, then traverses final-output
ancestry through finalization time. Prompt-context traversal retains its previous
start-time boundary and context-root requirement. The scratch producer records
the reply-node response hash; merged-chat carries the optional node unchanged.
Coverage reports final-reply standing separately; absent optional nodes remain
`not_supplied` and retain their prior admission contract. No missing history is
backfilled and no live consumer's evidence rule is changed.

236 isolated checks pass: witness 98, capture 27, replay adapter 9, hooks 18,
merge retention 31, provenance 11, evidence view 31, ownership 11. Regressions
cover direct/finalization influence, unknowns, stale versions, mismatched graph,
malformed node shapes and the clean control. Reports regenerated and whitespace
checked. No private input read, model calls, real test sends, live-store writes,
merge or deploy. Independent full Aegis review remains pending.


## 8 November — preserve raw provenance types at scratch capture

`codex/judges-shadow-provenance-types` continues from 84582fc3. Synthetic
regressions reproduced two assertion failures and one exception: the shared
legacy normalizer coerced truthy nonboolean witness flags into true and could
raise on a malformed output marker, dropping the private packet.

The scratch producer now requires an actual boolean witness flag and an explicit
matching turn identity in a present envelope before retaining eligibility.
Invalid shapes become malformed/ineligible; normalization errors still produce
an unknown packet. An explicit tactical marker survives even if other envelope
fields are malformed. The shared normalizer and all live evidence rules remain
unchanged. This is a synthetic boundary finding, not a claim about live records.

208 isolated checks pass: witness 98, capture 27, replay adapter 9, hooks 21,
provenance 11, evidence view 31, ownership 11. Tests assert packet counts,
nonboolean/mismatched inputs, valid true/false controls and retained tactical
influence. Reports regenerated and whitespace checked. No private inputs, model
calls, real test sends, live writes, merge or deployment. Independent review and
full isolated Aegis validation remain pending.


## 8 November — select earliest forecast before filtering invalid evidence

`codex/judges-earliest-forecast-evidence` continues from 2ee4053f. Five new
synthetic regression methods exposed eight failed assertions: invalid earliest
predictions were discarded before earliest-selection, permitting later predictions
or valid equal-time copies to be scored instead.

The offline reader now retains ordering claims for each identified group before
causality/vector validation. An invalid earliest forecast holds that selection;
conflicting earliest copies remain conflicted; a missing/invalid clock makes
selection order unknown. Later invalid records do not erase an earlier valid
forecast, and separate checkpoint groups remain independent. No live consumer,
producer, feed or historical record changes.

171 isolated checks pass: witness 103, capture 27, replay adapter 9, hooks 21,
ownership 11. Reports regenerated and whitespace checked. Tests use synthetic
records in both input orders. No private-data accuracy claim, model call, real
test send, live-store write, merge or deploy. Independent Aegis review remains
pending.


## 8 November — exact feedback copy identity

`codex/judges-feedback-copy-types` continues from d39f7a47. Synthetic regressions
showed Python dictionary equality hiding boolean/integer witness and sequence
conflicts, and integer/float rating conflicts. With the valid copy first, the
reader could emit positive feedback; reversed copies could instead be held for a
different reason. Three new methods cover both orders and key-order invariance.

Duplicate feedback IDs now require identical canonical JSON attestations before
any copy is selected. Type conflicts hold the event, including predecessor
conflicts; occupied sequence positions remain retained. Identical copies with
reordered object keys still join. Non-JSON/nonfinite direct-call records are held
without selecting a usable copy. Existing literal marker and rating policies,
unknown labels and all live readers remain unchanged.

126 affected isolated checks pass: witness 106, capture/replay 9, ownership 11.
Reports regenerated and whitespace checked. This is synthetic contract evidence,
not a live-data finding or a new accuracy measurement. No private input read,
model call, real test send, live write, merge or deployment. Independent full
Aegis review remains pending.


## 8 November — source-grounded producer coverage handoff

`codex/judges-producer-coverage-map` continues from d22d4032 with documentation
only. Traced offer assembly, marker-based turn recording, later prompt edits and
the exact per-invocation scratch fingerprint boundary. The new
[judges-producer-coverage.md](judges-producer-coverage.md) identifies which existing
records can be reused and which claims they cannot establish. It specifies the
next bounded generated-fragment binding increment and its synthetic acceptance,
without declaring completeness or enabling capture.

Source references checked against the unchanged implementation. No new tests
were run for this documentation-only change; the preceding 126-check result is
historical, not a fresh suite. No live inputs, model calls, sends from tests,
production changes, merge or deploy. Code implementation of these producer
bindings and independent full Aegis review remain outstanding.


## 8 November — generated fragment bindings per scratch request

`codex/judges-rendered-fragment-bindings` continues from cb861635. The existing
inner-context render path now retains a bounded ephemeral selection manifest only
when scratch settings match. No extra renderer calls or persisted offer fields.
Capture snapshots the exact selection identity/clock and matches offered fragments
against each router invocation's system input. It records hashes/spans, distinguishes
matched/not-found/ambiguous, and does not borrow matches from history or old retries.
Identical offers from different organs stay ambiguous. Generated nodes remain
incomplete with unknown upstream ancestry; delivery remains unconfirmed.

223 affected isolated checks pass: new rendered-fragment suite 11, witness 106,
capture 27, hooks 21, capture/replay 9, existing architecture admission 5, home-map
prompt 8, last-partials 25, ownership 11. Fixtures cover context interleaving,
immutable snapshots, old/failing APIs, mismatch/size limits, renderer errors,
capture-off output, existing offer schema, exact spans, duplicate origins and
persisted packet replay. The initial new-suite failure was a fixture without a
selected generation result; corrected to supply an invented observed result.
Reports regenerated and whitespace checked. No private-data run, model calls,
real test sends, live writes, merge or deploy. Full independent Aegis suite/review,
upstream dependency producers, delivery acknowledgement and enablement remain open.


## 8 November — partial renderer read receipts

`codex/judges-renderer-read-receipts` continues from eb16fce1 while that submitted
tip is independently reviewed (coordination note 18). Existing guarded JSON reads
can now supply bounded context-local version/outcome receipts during rendering.
No extra store reads, renderer calls, saved offer fields or feed changes. Capture
validates optional metadata and adds incomplete stored-parent nodes to the exact
fragment. Source text and locator strings are never persisted in those receipts.

Synthetic acceptance includes actual compact causal rendering against a temporary
store, version changes after rendering, defaults/error outcomes, unchanged
read-only write denial, old/failing APIs, capture-off output, nested/interleaved
contexts, immutable snapshots, size/count limits and invalid optional metadata.
Direct reads remain outside coverage; no full ancestry or census improvement is
claimed. Repeated renderer names retain the first rendered fragment and its own
read version; an earlier empty output cannot donate parents to a later fragment.
Final affected-suite results are recorded below after completion.

323 affected isolated checks pass: renderer reads 12, rendered fragments 11,
store guard 32, capture 27, capture/replay 9, hooks 21, witness 106, architecture
admission 5, lounge 46, journal 18, partials 25, ownership 11. Reports regenerated;
whitespace checked. The final renderer suites were rerun after adding the
same-name/version-binding regression. These are synthetic contract checks, not
private-data eligibility or live performance measurements. No model calls, real
test sends, live writes, merge or deploy. Full independent Aegis suite/review and
remaining upstream producers are still open.


## 8 November — main-chat value-map read binding

`codex/judges-value-map-read-binding` continues from 74b74c4f, preserving submitted
review tips. The handler's direct read now optionally attests the decoded version
and exact existing selection transform. Binding to the existing offered block is
handler-local and per-request matching remains independent for every retry. No
extra source reads, new model calls or feed changes. Missing/old/failing observer
APIs preserve output; over-limit sources supply no observation. The map and its
stored parent stay incomplete/unknown, without inferred generation history.

Tests execute the actual handler read and binding segments, not a second test
implementation of them. Synthetic fixtures cover Unicode truncation, unchanged
selected text over changed source versions, missing-file reset, retry edits,
history movement, duplicates, clocks, limits, old APIs and lifecycle enforcement.
An initial fixture lacked a selected generation result before checking delivery;
the fixture now supplies an invented observed result. No live-data finding is
claimed. Final affected-suite results follow after completion.

264 affected isolated checks pass: new value-map binding 7, capture 27, hooks 21,
capture/replay 9, fragments 11, renderer reads 12, witness 106, value-map day 17,
value-map choices 18, partials 25, ownership 11. The new suite also passes under
installed Python 3.12. The two existing value-map suites use unchanged Python
3.12 f-string syntax: default local Python 3.9 could not import them. Installed
3.12 lacked requests, so their successful isolated runs used the existing 3.9
site-packages directory as a read-only dependency root via the runner's existing
mechanism. No package installation or repository runner change. The first
launcher attempt lacked its scripts import path; corrected before successful
runs. Independent full Aegis validation remains pending.

Reports regenerated; whitespace checked. No private-data read/rescore, model
call, real test send, live-store write, merge or deploy. Generated-map dependency
receipts and other surfaces remain unfinished; this is source-binding evidence,
not a claim of clean lineage or improved eligibility.


## 8 November — value-map HTTP call receipts and reviewed-base continuation

Coordination note 19 approves/integrates the earlier batch through eb16fce1 and
requests base 16c74480. The new branch `codex/judges-value-map-call-receipts` rebases
only its three newer producer commits onto that base; earlier submitted branches
remain fixed. No integration merge or deployment was performed here.

The existing value-map call wrapper now emits optional private per-call hashes,
response-reported identity and returned/rejected/failed outcomes. Source copies
stay identical; request payloads, outputs and call counts are unchanged. There
is no configured-identity fallback. Optional API/sink failures preserve normal
behavior. Shared atomic publication retains 0600/no-replace scratch semantics.
New tests execute the actual wrapper with stub HTTP and verify privacy, identity,
unknowns, rejected/failed calls, exact pre-call snapshots, disabled capture,
observer failures, clocks, private-root validation and once-only completion.

These receipts are not chat turns and do not claim draft selection, final map
writes, complete upstream dependencies or complete backend/interrupted-attempt
coverage. Those remain open. Final rebased-suite results follow after completion.

374 affected isolated checks pass after the rebase: call receipts 9, value-map
read binding 7, capture 27, hooks 21, capture/replay 9, fragments 11, renderer reads
12, witness 106, store guard 32, architecture admission 5, lounge 46, journal 18,
partials 25, ownership 11, value-map day 17 and choices 18. The two existing
value-map suites use installed Python 3.12 with the existing read-only dependency
root; no installation or runner change. Reports regenerated and whitespace
checked. No private-data run, paid/model call, real test send, live write, merge
or deployment. Full independent Aegis validation of this newer batch remains
with the reviewer; earlier batch approval is not claimed for these new producers.


## 8 November — explicit build stages, selection and written-entry receipts

`codex/judges-value-map-build-bindings` continues from aa85ff5e on reviewed base
16c74480; earlier submitted tips stay fixed. Existing calls receive context-local
build/stage IDs, and synthesis names its actual two draft dependencies. The
existing branch records its selected stage. A completed-entry receipt follows
only successful original entry writes and close, with entry hashes and mode;
whole-file state and durability remain unverified. No new source reads or model
calls, and no output/feed changes. Missing receipt publication makes a dependency
unavailable without stopping generation. Duplicate stages, clock mismatches and
bounded overflow cannot silently pick an earlier success.

The new synthetic suite executes the actual builder using stub HTTP and fully
repointed scratch stores. It covers synthesis, either surviving draft, identical
draft text with distinct identities, append versus entry identity, rejected
results, write failures, missing call packets, capture off, older APIs, separate
contexts, disabled nested scopes, duplicate/mismatched selections, limits, clocks
and once-only publication. Existing unclosed-read ResourceWarnings appeared in
the builder's unchanged previous-map read; no unrelated behavior was modified.
Final affected-suite results follow after completion.

284 affected isolated checks pass: build receipts 11, call receipts 9, main-chat
read binding 7, capture 27, hooks 21, capture/replay 9, fragments 11, renderer reads
12, witness 106, value-map day 17, value-map choices 18, partials 25 and ownership
11. The actual builder and existing value-map suites ran with installed Python
3.12; existing external dependencies were exposed read-only where needed. No
installation or runner modification. Reports regenerated and whitespace checked.
No private input read/rescore, model/paid call, real test send, live write, merge
or deploy. Full independent Aegis validation remains pending for this newer batch.


## 8 November — offline value-map write/read observations

`codex/judges-value-map-write-observations` continues from a159af39 on reviewed
base 16c74480, keeping submitted tips unchanged. V2 writer/read metadata adds
opaque locator and full stripped-entry hashes. Optional explicit replay bundles
compare these and retain every causal matching write, never a latest/nearest
producer. No new source read, model call or feed change. Legacy metadata remains
unknown, and the observer wrappers preserve normal behavior on failure.

This is diagnostic coverage only. Same path/content cannot prove which writer
produced a read, especially across copies, hosts or reused paths. No lineage,
origin, admission or completeness upgrade occurs. Aggregate counts are separated
from private candidate IDs, and the private output is hashed into the run manifest.
Conflicting duplicate IDs and malformed records fail closed; no implicit disk
lookup or live-store read is introduced.

295 affected isolated checks pass: write/read diagnostic 11, builds 11, calls 9,
read binding 7, capture 27, hooks 21, capture/replay 9, rendered fragments 11,
renderer reads 12, witness 106, value-map day 17, choices 18, partials 25 and
ownership 11. Fixtures cover full-entry collisions, different locators, retained
multiple matches, future/cutoff exclusion, legacy gaps, conflicting records,
private output permissions/manifests and unchanged census/report behavior.
Actual builder and existing map suites used installed Python 3.12 and existing
read-only dependencies where needed; no installs or runner changes. Independent
Aegis full-suite review and private census remain with the reviewer. No private
input run, model/paid call, real test send, live write, merge or deploy.


## 8 November — direct read observations during value-map assembly

`codex/judges-value-map-context-reads` continues from f19bf795 while earlier review
tips remain fixed. Existing direct text/JSON reads in context assembly now yield
bounded optional metadata without reopening sources. The actual assembled context
is compared to each call's user slot independently, with exact spans/hashes only
for unique matches. Context-local scopes reset after exceptions and mask disabled
nested work. Failed/missing observers preserve assembly and generation.

Read coverage is deliberately distinct from contribution: parsed/discarded data
and sources beyond the final context cap may have been read. No clean ancestry
or eligibility is inferred. Evidence-view internals, failed opens, directory
selection, cached material, separate system/temporal reads and source/effect
history remain open. Limits are 64 reads, 4,194,304 hashed codepoints and the
existing 60,000-codepoint assembled context. No text/raw paths enter packets.

305 affected isolated checks pass: context assembly 10, write/read diagnostics 11,
builds 11, calls 9, read binding 7, capture 27, hooks 21, capture/replay 9, fragments
11, renderer reads 12, witness 106, value-map day 17, choices 18, partials 25 and
ownership 11. New fixtures execute actual assembly and builder functions with
fully repointed stores/stubbed senders, and cover prefix/duplicate matches,
truncation, malformed JSON, clocks, bounds, scope isolation and immutable packets.
Existing unclosed-read ResourceWarnings in the system-context read are unchanged.
Installed Python 3.12/existing read-only dependencies were used for full builder
suites; nothing was installed. No private-data run, model/paid call, real test
send, live write, merge or deploy. Full Aegis review remains with the reviewer.


## 8 November — separate identity and temporal producer inputs

Read reviewer note #20: the stack through aa85ff5e is approved/integrated. The
current branch already descends from that exact commit, so no history rewrite
is needed. `codex/judges-value-map-auxiliary-inputs` continues from 867fd72d and
keeps previously submitted tips fixed.

The separate identity and temporal reads now have optional scoped observations
and request-specific slot binding. Full decoded-version hashes and transformed
returned-text hashes are distinct. Identity fallback may match a system prompt
with file evidence unavailable. Empty/oversized components, repeated assembly,
duplicated text, changed/wrong slots and future clocks cannot claim a binding.
Readers and call counts remain unchanged; the identity read now explicitly closes
its existing handle. No extra read or inference. Each of two named scopes reuses
the bounded read observer and resets even on failure.

314 affected isolated checks pass: auxiliary inputs 9, context 10, write/read 11,
builds 11, calls 9, main-chat read binding 7, capture 27, hooks 21, capture/replay 9,
fragments 11, renderer reads 12, witness 106, map day 17, choices 18, partials 25
and ownership 11. Actual readers/builders use synthetic scratch stores/stub HTTP.
Full builder suites use installed Python 3.12 and existing dependencies read-only;
no installs or runner changes. Reports regenerated and whitespace checked.

This newer increment is not yet independently reviewed. Source/effect history,
evidence-view internals, cached material, complete ancestry and delivery remain
open. No private run, model/paid call, real test send, live write, merge or deploy.
Production capture stays disabled; reviewer owns full Aegis suite/private census.


## 8 November — returned evidence-view boundary

`codex/judges-value-map-view-receipts` continues from ec470e34, preserving prior
review tips. Note #20 remains latest; aa85ff5e is already an ancestor. The actual
consumer boundary now distinguishes filtered ledger/history returns from its
existing raw/empty fallbacks. Observation leaves all filtering, fallback and
feeds unchanged. Canonical returned-view hashes are explicitly not file-version
hashes. Explicit standing/permission/withheld/influence markers survive as counts,
including contradictory permission and influence; no row text or IDs persist.

Views share the direct-read scope's 64-record/4,194,304-character budget and are
capped at 4096 rows. Incremental hashing preserves earlier observations, debits
failed over-budget work and records unavailable/truncated evidence on malformed
or oversized views. No reread, new inference, complete ancestry or eligibility
upgrade. Existing raw-fallback unclosed-file warnings are unchanged.

365 affected isolated checks pass: view receipts 9, auxiliary inputs 9, context
10, write/read 11, builds 11, calls 9, main-chat binding 7, capture 27, hooks 21,
capture/replay 9, fragments 11, renderer reads 12, witness 106, map day 17, choices
18, partials 25, ownership 11, evidence view 31 and evidence provenance 11. The
new suite executes actual consumer/view code on synthetic scratch data, with all
paths repointed and senders stubbed. Rechecked view tests after adding explicit
influence counts. Full builder suites use installed Python 3.12 and existing
read-only dependencies; no installation or runner edit. Reports regenerated;
whitespace checked. No private-data run, model/paid call, real test send, live
write, merge or deploy. Full Aegis review/private census remain with the reviewer.


## 8 November — offline explicit build/call consistency

`codex/judges-build-call-replay` continues from 0c734ea3 without changing submitted
producer branches. The optional replay input now checks a build's exact selected
request and a selected synthesis call's two draft dependencies against supplied
call receipts. IDs, stages, hashes, publication/outcome observations, stage counts
and causal clocks must agree; no text similarity, nearest/latest choice or
substitution. Missing, unavailable and inconsistent evidence remain distinct.

Conflicting duplicate identities or malformed required records fail generically
before filtering. Unique completed builds before the exclusive cutoff contribute
aggregate counts; exact dependency IDs stay private under the run manifest.
Selection consistency and draft-dependency consistency are separate measures.
This is internal receipt consistency, not producer authenticity, certified served
identity, complete source ancestry or delivery. Census/behaviour/innovation and
production remain unchanged.

196 affected isolated checks pass: build/call replay 11, write/read 11, builds 11,
calls 9, context 10, auxiliary inputs 9, view receipts 9, capture/replay 9, witness
106 and ownership 11. The new suite drives actual synthetic producers into replay
and checks missing IDs despite equal text, omitted duplicate stages, wrong hashes
or clocks, missing/future drafts, surviving-draft selection, conflicting copies,
cutoff, private output permissions/manifests and unchanged census/report fields.
Installed Python 3.12 is used for actual builder fixtures; no installs or model
calls. Reports regenerated; whitespace checked. No private-input run, real test
send, live write, merge or deploy. Independent Aegis full suite/private census
remain with the reviewer; producer history and trusted delivery remain open.


## 8 November — explicit producer identity coverage in replay

`codex/judges-producer-identity-coverage` continues from 5f10dc3a with earlier tips
fixed. The optional build/call diagnostic now counts response_reported, unknown,
missing and malformed identity evidence separately from link consistency. Only
returned outcomes with explicit response metadata, a bounded nonblank served
name and a response digest count as response-reported. Configured names never
fill gaps; failed-result identity claims stay malformed. Aggregate output contains
no model names. This is reported metadata, not verified weights or source origin.

200 affected isolated checks pass: build/call replay 15, write/read 11, builds 11,
calls 9, context 10, auxiliary inputs 9, view receipts 9, capture/replay 9, witness
106 and ownership 11. Added cases cover unknown/missing configuration-only
identity, partial/claimed/contradictory fields, blank/oversized/nonstring names,
missing response hashes, failed outcomes and the exclusive cutoff. Actual
producer fixtures remain synthetic and use installed Python 3.12; no installs.
Reports regenerated; whitespace checked. No private input, model/paid call, real
test send, live write, merge or deploy. Full Aegis review/private census remain
with the reviewer. Linkage, ancestry and admission do not gain eligibility from
these coverage counts.


## 8 November — exact self-forecast input observations

`codex/judges-self-forecast-input-receipts` adds an opt-in private sidecar at the
existing on-message forecast log-close boundary. The anchored self readout records
its actual last-six nonempty normalized reply inputs, including separate full
normalized-text and first-400-codepoint encoder-input hashes. Existing exchange
IDs/clocks are explicitly observed/unverified, not finalized-reply origin proof.
The recent-own feature subset is not the entire forecast context; encoder identity,
source ancestry and complete context remain unobserved/incomplete.

The scoped observation must match the exact rounded prediction/metadata ultimately
saved by the job. A changed/fallback prediction cannot inherit another result's
input receipt. The sidecar binds the entire saved row by canonical hash; the
existing row, log, result, encoder calls and feeds stay unchanged. It records
successful close, not durable storage. Missing legacy observations, duplicate
observations, invalid/oversized inputs and failed binding remain unavailable.
No observer work runs without the existing scratch flag; validated private roots
and the existing 0600 publication sink apply. Observer failures are swallowed.

265 affected isolated checks pass: new input receipts 15, self on-message 32,
self source 39, anchored readout 5, capture 27, capture hooks 21, capture/replay 9,
witness 106 and ownership 11. Actual job/readout boundaries use synthetic inputs,
stubbed encoder/model functions and scratch paths. The existing readout suite's
synthetic fitting checks pass with numeric matrix warnings; these are contract
checks, not real-data accuracy evidence. Required reports regenerated; whitespace
checks pass. Initial new-fixture failures were an omitted hash helper and an
incorrect assumption that the existing arrival cutoff excludes every earlier
matching message; corrected fixtures assert the actual unchanged cutoff rule.

The offline controls currently require full finalized-reply version identities.
These producer receipts deliberately do not claim that contract: normalized
truncated inputs cannot silently substitute for full reply embeddings. A separate
verified identity/transform/cache join and predeclared evaluation block are still
needed before paired controls can consume them. No census upgrade, private run,
model/paid call, live write, merge, deployment or Gloria-head change. Full Aegis
validation and private snapshot census remain with the reviewer. Earlier review
tips remain fixed; aa85ff5e is an ancestor of this stack.


## 8 November — paired controls from explicit self-input receipts

`codex/judges-self-input-baselines` joins the producer sidecars to the exact
forecasts already selected by offline innovation. Optional `self_input_controls`
supplies sidecars, separately tagged cached excerpt vectors and declared blocks.
The report pairs head/last-reply/recent-mean errors on identical targets without
changing the existing census, innovation selection or full-reply control output.
No new producer/model calls, input discovery or source reads are introduced.

The join requires explicit input IDs, admitted prior replies, the same surface,
strict finalization order, exact full reply and prefix hashes, compatible encoder
and valid duplicate vectors. Only byte-unchanged normalization is supported;
changed normalization remains unavailable. Full-reply vectors cannot substitute
for truncated inputs. Actual targets reuse innovation's original full-target
cache. Blocks must be complete at cutoff and contain arrival through finalization;
overlapping or conflicting declarations are rejected. Missing evidence and zero
mean geometry stay unavailable. Malformed/conflicting sidecars abort generically,
even beyond cutoff. Supplied declarations do not prove preregistration.

187 affected isolated checks pass: new paired controls 20, witness 106, producer
inputs 15, capture/replay 9, value-map write/read 11, build/call replay 15 and
ownership 11. Synthetic producer packets reach a real offline CLI invocation;
private output mode/hash manifest and unchanged old reports are checked. Tests
cover prefix mismatch, unknown IDs, altered normalization, future/reordered inputs,
wrong cache identity, malformed duplicate vectors, duplicate/conflicting sidecars,
block boundaries/overlap and checkpoint/block separation. The initial CLI fixture
used an unsupported adapter name; corrected it to the existing canonical adapter.
Required reports regenerated; whitespace checks pass. Existing builder resource
warnings remain visible. No real-data measurements, private snapshots, live writes,
model/paid calls, actual test sends, merge or deploy. Full Aegis suite/private census
remain with the reviewer. Source ancestry, delivery and production enablement are
still separate; this does not grant eligibility or claim accuracy.


## 8 November — baseline coverage denominators

`codex/judges-baseline-coverage` adds explicit coverage to the optional observed-input
baseline report. Counts distinguish admitted replies, distinct scorable targets,
selected forecasts and successful pairs. Multiple checkpoints do not inflate the
distinct-target count. Zero-pair groups retain their denominator and missing-evidence
reasons. Empty/future/incomplete declared blocks remain visible with counts, never
fake scores. Source windows use finalization, while pair eligibility also requires
in-block arrival; unmatched complete-block scope is explicit. No dates, IDs or
hashes enter these aggregate coverage fields.

174 affected isolated checks pass: coverage 13, paired controls 20, witness 106,
producer inputs 15, capture/replay 9 and ownership 11. Fixtures exercise half-covered
groups, missing/unscorable forecasts, multiple checkpoints of one target, incomplete
and empty blocks, arrival/finalization boundaries, exclusive cutoff and misaligned
decisions. The report cannot silently truncate its denominator through a mismatched
score/decision list. Required reports regenerated; whitespace checks pass. The
score calculations, selection, old output and witness admission remain unchanged.

This is coverage of supplied admitted data, not a census of all production traffic
or attempted forecasts. No real-data measurements, private rerun, new producer or
model call, live write, send, merge or deploy. Full Aegis validation/private census
remain with the reviewer; earlier branches stay fixed above approved aa85ff5e.


## 8 November — actionable forecast clock diagnostics

`codex/judges-forecast-clock-diagnostics` identifies clock failures inside the
existing innovation report without changing rejection, ordering, scoring or
admission. Fixed field names distinguish missing, timezone-missing and invalid
values when parsed. Counts are per input record's first failing parsed clock;
earlier evidence failures may prevent parsing. Valid but noncausal times retain
the old noncausal reason. No raw times, identifiers or error text are exposed.

Source tracing found a concrete contract risk: the self head's `_iso` uses local
`datetime.fromtimestamp(...).isoformat()` without a timezone, while strict replay
requires explicit time instants. A synthetic test executes that actual formatter
and demonstrates the held outcome. No claim is made about live prevalence, and
no historical clock is guessed or reinterpreted. Future explicit clock evidence
remains producer work, rather than weakening this reader.

183 affected isolated checks pass: clock diagnostics 9, witness 106, paired controls
20, coverage 13, producer inputs 15, capture/replay 9 and ownership 11. Tests retain
unknown forecast order and the hold on an unscorable earliest prediction; later
valid candidates cannot replace it. Numeric and offset-aware equivalents preserve
scores, while non-clock failures stay separate. Required reports regenerated;
whitespace checks pass. No private snapshot run, live write, model/paid call, real
test send, merge or deploy. Independent full Aegis suite/private census remain with
the reviewer; submitted prior branches remain fixed above approved aa85ff5e.


## 8 November — explicit source-clock observations

`codex/judges-source-clock-receipts` retains explicit source times before the self
head's legacy timestamp formatting can lose their offset. Observation runs only
inside an existing scoped scratch forecast. Numeric/offset-aware values must agree
exactly with the adapter's parsed epoch; ambiguous inputs stay unknown. The actual
ledger/chat adapters and existing earliest-time merge carry the observation without
changing their text priority, filtering, selected timestamps or forecast row.
An earlier unknown clock clears the later known one; no duplicate backfill.

A separate private `self-forecast-clock-v1` sidecar requires exact saved prediction
and rendered context-clock binding. It contains clock hashes/epoch/kind and explicit
unverified source identity, not messages or vectors. It records exchange time, not
reply finalization. Existing input-sidecar schema and forecast logs stay unchanged.
Observer/sink failures cannot affect the forecast, and a clock-sink failure preserves
the already published input receipt. The two files do not prove a complete capture
set or durable storage. Replay consumption is still separate work; no implicit
historical conversion or eligibility upgrade is introduced.

271 affected isolated checks pass: source clocks 12, input receipts 15, on-message
32, self source 39, readout 5, clock diagnostics 9, paired controls 20, coverage 13,
witness 106, capture/replay 9 and ownership 11. New fixtures execute actual source
adapters, merger and job against synthetic scratch with stubbed encoder/model
functions. Cases include numeric/aware/naive clocks, off/on equivalence, unscoped
reads, earlier/later/equal duplicate timing, bad metadata and observer/sink failures.
The existing synthetic fitting suite passes with its numeric warnings; no real-data
accuracy claim. Required reports regenerated; whitespace checks pass. No private
snapshot run, paid/model call, real test send, live write, merge or deploy. Full
Aegis suite/private census remain with the reviewer; earlier tips remain fixed.

## 8 November — offline source-clock consistency audit

`codex/judges-clock-receipt-audit` consumes explicitly supplied source-clock
sidecars in the offline replay. It checks exact forecast-row identity, mode,
forecast/arrival clocks, rendered-clock binding and explicit-clock agreement.
Matching unparsed rendered clocks remain unparsed; no host timezone is borrowed.
Malformed/conflicting observations abort before cutoff filtering; identical copies
count once. Missing forecast rows, mismatches and outside-cutoff receipts retain
separate fixed-label counts. Counts cover supplied evidence, not production traffic.

206 affected isolated checks pass: new clock replay 11, source clocks 12, forecast
inputs 15, clock diagnostics 9, witness 106, excerpt controls 20, coverage 13,
capture/replay 9 and ownership 11. The new suite uses actual synthetic producer
packets and the CLI, checks private output modes/manifest binding, and proves all
previous reports unchanged with the optional diagnostic enabled. Senders remain
stubbed and stores private scratch; no actual-data measurements are claimed.
Required reports regenerated. No production or scoring change, paid/model call,
real test send, private census rerun, merge or deploy. The reviewer owns the ready
private census on approved 4a8fc11e and the full Aegis suite; this work does not
hold up that run. Earlier submitted branch tips remain fixed.

## 8 November — shadow review report scaffolding

`codex/judges-shadow-review-report` follows coordination note 22 while the reviewer
runs the private census. New offline `experiments/judges-witness/report.py` formats
one explicit replay aggregate with its supplied run receipt. It checks aggregate
bytes/hash/size and the manifest fingerprint, clearly distinguishing that from
verification of the original input, scoring checkout or other outputs. It reads
no per-turn data and never reruns the census. Both output files are private and
written only to a new separate scratch directory; no network or subprocesses.

The numerical projection omits arbitrary labels, strings, dates and identifiers.
It distinguishes per-copy coverage from unique eligible replies, unconfigured
scope from an empty scope, and missing forecasts from zero innovation. Behaviour
and checkpoint/block groups stay separate; paired full-reply and excerpt controls
remain distinct, without pooled scores, intervals or a pass verdict. Zero eligible
observations produce an explicit insufficient outcome. Real results are pending
with the reviewer, not reconstructed or fabricated here.

165 affected isolated checks pass: formatter 15, witness 106, baseline coverage 13,
excerpt controls 20 and ownership 11. Actual synthetic replay-to-formatter tests
cover empty and populated runs, privacy projection, inconsistent counts, invalid
numbers, manifest/output tampering, scratch/symlink/no-overwrite rules and private
permissions. Reports regenerated. No model/paid call, actual test send, live write,
merge or deployment. Previous submitted tips remain fixed; full Aegis suite and
private census remain with the reviewer.

## 8 November — review coverage denominators

`codex/judges-review-coverage` extends the pending shadow formatter to display the
existing optional excerpt-control coverage beside paired scores. Unique replies,
scorable targets and forecast rows retain different denominators. Missing pairs
and predictions remain visible; multiple checkpoints cannot inflate unique-target
coverage. Zero denominators are undefined, while omitted coverage stays unsupplied.
Cross-report counts must agree with the census, innovation groups and comparison
rows. Private block labels and day activity remain omitted; no scores or selection
are recomputed and no data is collected.

68 affected isolated checks pass: new report coverage 9, formatter 15, excerpt
controls 20, baseline coverage 13 and ownership 11. The new tests use actual
synthetic producer/replay outputs, including one target with two checkpoints,
missing receipts, no forecasts, unfinished blocks and inconsistent counts.
Required reports regenerated; whitespace clean. The reviewer's private census
remains in progress per note 22; no actual measurement is claimed or duplicated.
Full Aegis suite/review remain there. No live writes, model/paid calls, actual test
sends, merge or deployment; submitted previous branch tips remain fixed.

## 8 November — dedicated disabled production sink

`codex/judges-production-sink` implements note 23's independent config/destination,
atomic 0600 packets, 0700 directory, nonblocking writer lock, bounded packet/byte/file
counts, opportunistic expiry, kill switch and rollback contract. Existing capture
hooks accept the explicit config pointer, without repointing SPARK_WORKSPACE or
changing forecasts, value-map output or feeds. No config/environment was installed
or enabled. Existing scratch capture retains precedence and its original guard.

314 affected isolated checks pass, including 19 sink cases, actual synthetic
self-forecast off/on equality and concurrent capacity handling. Required reports
regenerated. A 100-call tiny synthetic local storage benchmark measured median
1.139 ms, p95 1.300 ms and maximum 1.659 ms; Aegis end-to-end/occupancy measurements
remain with review. Persistent status counts only lock-owning operations; other
failures have process-local counters and are not silently claimed complete.

The reviewer reported the strict census had zero eligible replies. Note 24 corrects
its interpretation: historical served_by labels and compute-ledger model fields
exist. Strict observed identity absence is not tracking absence. A separately
labelled historical attribution tier is next; checkpoint/target-vector retention
also remains open. No historical eligibility, delivery or lineage upgrade. Full
Aegis suite, review and Gloria's enable decision remain outstanding; no merge,
deploy, live write, model/paid call or actual test send occurred.

## 9 November — historical model-attribution tiers

`codex/judges-legacy-attribution` implements notes 24/25's corrected distinction:
historical served_by/model labels exist even when strict observed identity is
unknown. Optional offline attribution uses exact provider-request IDs first,
otherwise a uniquely nearest foreground call within an explicit at-most-ten-second
window and exact surface/caller map. Recorded labels, ledger attribution, observed
receipt identity and unknown remain separate tiers. Conflicts, ties, reused calls,
invalid nearest records and unknown chronology cannot silently improve the tier.
Naive historical clocks require an explicit reviewer-supplied timezone; ambiguous
or nonexistent local times remain unresolved. No current-host timezone is guessed.

Aggregate counts are per assistant source copy, with label/ledger agreement and
cutoff coverage made explicit. Model/provider/IDs/hashes and join methods stay in
a private 0600 manifest-bound detail file, not public reports. The formatter shows
the new tiers beside strict eligibility. Existing census and innovation outputs
remain identical with the optional attribution object removed, tested through the
actual CLI. No private census rerun or measured tier counts are claimed here.

167 affected isolated checks pass: attribution 17, strict witness 106, formatter
15, report coverage 9, capture/replay 9 and ownership 11. The new fixtures cover
legacy-only labels, exact-ID priority/no fallback, time/caller scope, ties, bad
nearest records, duplicate/reused calls, explicit timezone/DST, copy-versus-turn
counts, unknown clocks, observed precedence, privacy and unchanged strict results.
Reports regenerated; whitespace clean. Full Aegis suite/private census rerun remain
with the reviewer. Historical model-switch stratification is recommended with tiers
and matching methods labelled; character-training admission is not changed. The
separate sink remains disabled and in review; checkpoint/target retention is next.
No live write, model/paid call, real test send, merge or deployment.

## 9 November — private self artifact retention

`codex/judges-self-artifact-retention` continues above the submitted historical
attribution tip. The guarded on-message path retains checkpoint metadata from the
same bounded bytes it parses and the already computed last-six own-reply feature
vectors, bound to the exact saved forecast. A mid-forecast checkpoint replacement
cannot bind the wrong snapshot. Existing anchored self ranking audits retain their
already computed self-text vectors and all bounded source references for prefix
collisions. The encoder return object and existing scores are unchanged; no new
model call, schedule or other-head hook. Both private packet types use the existing
optional sink, off by default. No weights are copied.

Reported training/calibration dates and encoder labels are kept as reported;
training completion and encoder-weight identity remain unknown. Current audit rows
have lost turn IDs and use 400-character excerpts. These artifacts are therefore
retained without being silently promoted into strict replay evidence or full-reply
vectors. Final-version joins, explicit encoder provenance and target-transform
comparability remain open. This is not an accuracy result or complete-retention
claim. The historical private census remains with the reviewer.

241 affected isolated checks pass: artifacts 16, self input receipts 15, source
clocks 12, forecast clocks 9, sink 19, capture 27, hooks 21, capture/replay 9,
self on-message 32, self source 39, readout 5, ranking 26, ownership 11. The first
regression run exposed an optional-hook absence outside a try boundary; fixed and
the failure case/new artifact suite rerun successfully. A nested sandbox launch
was initially refused; the authorized outer runner then executed the isolated
suite normally. Required reports regenerated; whitespace clean. Full Aegis suite
and independent review remain with the reviewer. No live writes, real test sends,
model/paid calls, merge, deployment or capture enablement.

## 9 November — source identity survives the self audit adapter

`codex/judges-self-source-identity` continues above db7500ac. Scoped adapters now
observe the actual raw ledger/chat reply before cleanup, retaining raw/normalized
hashes, source-row digest and original string ID/surface. The observation follows
the preferred text through existing merge rules; it does not follow an earlier
clock from a different copy. Missing/non-string original IDs remain unknown. The
ranking adapter keeps its original three values and adds optional metadata only
when bound to the selected text/ID. Forecast/audit-vector refs retain it privately.
No additional source read, model call or changed forecast/ranking input.

209 affected isolated checks pass: source identity 13, source clocks 12, artifacts
16, input receipts 15, sink 19, ranking 26, self on-message 32, self source 39,
readout 5, capture hooks 21 and ownership 11. Cases cover actual cleanup/merge,
preferred-source conflicts, missing/malformed IDs, earlier duplicate clocks,
exception restoration, disabled/bad sinks, unchanged ranking streams and private
artifact publication. The existing clock equality fixture now removes both optional
observations before comparing the unchanged source fields. Reports regenerated;
whitespace clean. Full Aegis suite and private census remain with the reviewer.

The ID-loss gap is addressed prospectively, not by upgrading old rows. Exact
producer-final-version joins, encoder-weight/training evidence and excerpt/full
metric comparability remain open; source identity is still labelled unverified.
No live writes, actual test sends, paid/model calls, enablement, merge or deployment.

## 9 November — offline source-to-final content joins

`codex/judges-artifact-final-joins` continues above fdb4d299. Optional replay input
self_artifact_packets now joins retained observations by exact source-row digest,
original string ID, surface, raw/normalized hashes and existing admission. The
source copy and admitted final reply must agree on receipt and final text. Explicit
ledger final attestations handle appended marks; cleanup never substitutes for an
authored final version. Full-text versus 400-codepoint excerpt bindings remain
separate. Duplicate packets count once; conflicting vectors hold every matching
reference; malformed vectors abort. No time/text-nearest identity inference.

Fixed aggregate counts and a private manifest-bound join-detail file are produced,
with no text or vectors in those details. The review formatter reports distinct
packet/reference/reply counts and content-only limits. No artifact enters scored
embeddings/checkpoints and no existing eligibility, score, behaviour or feed changes.
The actual offline CLI verifies identical previous report sections with and without
the new optional input. Training/encoder evidence and causal forecast selection are
not inferred from content agreement.

232 affected isolated checks pass: joins 16, strict witness 106, formatter 15,
report coverage 9, capture/replay 9, self input controls 20, source identity 13,
artifacts 16, attribution 17 and ownership 11. Cases use actual synthetic artifact
producers, final-attested ledger marks, long excerpts, changed final versions,
excluded copies, prefix/hash mismatches, duplicates/conflicts, privacy projection,
actual reader cleanup equivalence and the isolated CLI. Reports regenerated;
whitespace clean. Full Aegis validation/private census remain with the reviewer.
No real records, model/paid calls, actual test sends, live writes, enablement,
merge or deployment.

## 9 November — observed checkpoint availability

`codex/judges-checkpoint-availability` continues above a5b16797. Optional checkpoint
observations now retain wall/monotonic read timing around the same byte snapshot.
Full parameter loads and metadata-only audit reads are distinct; only a completed
parameter load can supply parameters_available_by. No training date is inferred
from fitting-day metadata or file mtime. Clock rollback/discontinuity, invalid
values and observer failures remain explicit without affecting forecasts.

Offline timing diagnostics require the exact saved forecast row, checkpoint and
matching clocks before comparing load completion with logged forecast time. Audit
snapshots, late loads, cutoff exclusions and missing records remain separate.
Fixed aggregate counts are included in the private review report; no private clock
values, IDs, text or vectors are rendered. Admission, scores and feeds are unchanged.
Encoder identity and training-data provenance remain open; this is an availability
bound, not a fabricated historical training-completion attestation.

236 affected isolated checks pass: availability 12, artifacts 16, final joins 16,
input receipts 15, source clocks 12, strict witness 106, formatter 15, report coverage
9, readout 5, sink 19 and ownership 11. Cases cover actual checkpoint loading and
unchanged forecast rows, disabled capture, failed clocks, backward/forward jumps,
metadata-versus-parameter stages, exact-row/hash/clock consistency, cutoff and report
denominators. Reports regenerated; whitespace clean. Full Aegis validation/private
census remain with the reviewer. No real-data reads, model/paid calls, actual test
sends, live writes, enablement, merge or deployment.

## 9 November — historical attribution coverage diagnostic

Review note 26 reports integration of the dedicated sink and historical tiers.
Regenerated the stale store-owner inventory for the sink status file. Added a
separate offline coverage probe: unchanged tight-window attribution, private
per-caller retained date ranges and source/surface counts, and fixed wider-window
ambiguity/reuse diagnostics. No widened attribution, training promotion, source
capture or provider calls. Exact dates and surface names remain private; public
output uses counts. The command and limitations are in the experiment README.

The configured host route rejected authentication, so no retained input was read
and no real-data diagnostic result is claimed. The reviewer can run the probe on
the existing admitted snapshot; use its full copied ledger to measure all callers.
Source tracing found unlogged successful toggle branches and confirms route labels
are not necessarily model names; historical attribution impact remains unmeasured.

179 affected isolated checks pass: coverage 13, attribution 17, strict witness 106,
store guard 32, ownership 11. The coverage CLI initially failed because its file
handle wrapper triggered the existing descriptor-write guard; changed it to the
same guarded path-write pattern with a private umask and re-ran successfully.
No live store, sink enablement, deployment or merge. The reviewer's occupied-sink
measurements supersede the empty-directory estimate: roughly 11 ms/write, p95
13 ms, max 16 ms, up to 24 ms at capacity. Off-path publication remains open.

## 9 November — final capture publication deferred, bounded and volatile

`codex/judges-deferred-capture` addresses the occupied-sink latency noted in review
26, leaving the submitted coverage diagnostic tip fixed. Only the avatar final
production packet requests deferred storage; scratch and other producers retain
synchronous semantics. Immutable bytes enter a per-process eight-slot queue with
one daemon writer. Overflow/busy startup skip, config changes are rechecked at
publication, and fork children discard inherited queue/lock/thread state and
counters. No shutdown flush: accepted work may be lost on exit. No durability or
client-delivery claim follows from enqueue success. Full storage checks and private
atomic publication remain in the worker; final reply content/timestamps remain
unchanged. No existing feed or judge is altered.

122 focused isolated checks pass: deferred capture 14, sink 19, handler hooks 21,
capture replay 9, self artifacts 16, ownership 11, store guard 32. The first queue
fixture lacked a selected generation and was corrected before the successful run.
Tests execute actual handler capture/return segments with a deliberately stalled
writer and stubbed providers, plus fork/exit loss, queue/disk limits, mutation,
concurrent submitters, configuration changes and failures. No actual sends.

At 4,000 synthetic files / about 226 MiB on the Mac, 20 samples of 24,565-byte
packets measured synchronous median/p95/max 12.653/13.211/14.908 ms; enqueue
0.168/0.218/0.236 ms; worker 12.598/13.936/18.997 ms. All 20 queued samples were
confirmed written. Sequential drained-queue measurement, not concurrent or host
acceptance. The dedicated-sink proposal documents measurement and volatile loss.
Full Aegis suite/latency review remains with the reviewer, enablement with Gloria.
The existing authentication blocker for private measurements is unchanged; no
repeat notification. No paid calls, live writes, merge, enablement or deployment.

## 9 November — missing router completion records repaired prospectively

`codex/judges-router-completion-coverage` adds completion recording to the two
successful toggle branches found during coverage source tracing. Both use the
existing recorder, original surface, current configured model and measured stage
elapsed time. They explicitly mark model identity as configured because the draft
return contract does not expose verified response identity. No new provider call,
retry, generation parameter, output text, fallback order or observed witness
identity. Failed/empty drafts retain the existing fallback path. Recorder failures
cannot change the result or cause another model call.

The offline reader now honors the new explicit unknown identity marker: a matching
call with configured/unknown/malformed evidence stays unobserved, with its own
reason count. Wider-window diagnostics cannot promote it. Existing unmarked
historical ledger rows and recorded-label tiers retain the reviewed rules. No
retroactive edits, attribution claims or strict training admission follow.

130 focused isolated checks pass: real router functions with stubbed providers and
ledger 7, compute admission 44, router cache 15, handler capture 21, attribution 18,
coverage 14, ownership 11. Tests prove one completion per successful direct call,
unchanged forced/fallback paths and return values, logger failure isolation, surface
retention, no prompt/reply content in the ledger call, and no configured-to-observed
promotion. Generated reports refreshed. Full host suite and private measurements
remain with the reviewer. No live writes, paid calls, merge or deployment.

## 9 November — response identity survives existing draft contracts

`codex/judges-draft-response-identity` supplements the prior completion repair with
optional invocation-local callbacks in the two existing draft parsers. Bounded
response model/ID metadata is bound to the exact returned-text digest, without
changing payloads, tuple return values, reasoning, route labels or fallback order.
Only present valid response fields become observed identity; missing/invalid data
stays unknown and completion recording remains explicitly configured-only when
appropriate. A known response ID without a known model does not manufacture one.

Successful routed results carry observed identity separately from configured model
fields. The ledger records the observed name/ID when known. Private capture keeps
provider IDs in observed_attempts, separately from internal request/input bindings;
normalized strict receipt requirements are unchanged. Empty output emits no selected
identity, callbacks cannot change a draft, and failed/concurrent calls cannot reuse
another call's metadata. No new model call or historical backfill. Complete internal
draft attempt history and underlying weight identity remain unasserted.

273 focused isolated checks pass: new draft-parser identity 9, completion 7, forced
routes 16, learned cache 15, compute admission 44, reply budget 11, avatar sight 37,
result contract 52, handler capture 21, ownership 11, capture primitives 27, replay 9,
deferred capture 14. Tests execute actual parser/router functions with synthetic
responses and stubbed transports. The first extracted-parser fixture omitted its
module filename; fixed that test namespace and reran. Existing usage-log writes
emit ResourceWarning for unclosed handles; all are redirected to private scratch
and these pre-existing write patterns are unchanged by this work.

No live/provider calls, real inputs, feed changes, enablement, merge or deployment.
Full host suite and private measured coverage remain reviewer steps. The prior
configured-host authentication blocker is unchanged; no repeat alert. Encoder
identity and retained coverage still remain open.


## 9 November — preserve repeated audit-vector conflicts

`codex/judges-audit-vector-conflicts` repairs an observation loss in the optional
self-audit wrapper: input-only deduplication suppressed all later vectors for a
text, including different results that the offline conflict detector should see.
Deduplication now uses input plus vector digests. Identical repeats stay collapsed;
distinct outputs in one or multiple existing calls reach the private sink. The
wrapper preserves output object identity and adds no encoder calls. An 8,192-key
per-wrapper limit bounds retained observation state; skipped observations increment
a process-local counter. Failed publication remains retryable. This does not claim
complete capture, underlying encoder identity or a cause for vector differences.

62 affected isolated checks pass: self artifacts 20, content joins 17, source
identity 13, checkpoint availability 12. New cases execute the actual retention
wrapper through the offline join and produce two conflict references with zero
bound replies; they also cover repeat deduplication, changed outputs in one batch,
invalid later vectors, failed publication retries and bounded observation state.
All fixtures and writes are synthetic/private scratch; external transports are
stubbed. No live data, model calls, feed changes, enabling, merge or deployment.
Full Aegis suite/private measurements remain the independent reviewer steps.


## 9 November — distinguish observed vector representations

`codex/judges-vector-representations` follows the repeated-vector repair with a
source-verified distinction: the forecast bank stores the readout's normalized
vectors, while the audit wrapper stores encoder-return vectors. Prospective private
packets now name those representations without changing numbers or encode calls.
The offline content join distinguishes mixed representations from differing vectors
within a known representation. Unknown legacy representation is never inferred.
All ambiguous groups remain outside content-bound counts, and no strict admission
or scoring threshold changes. Encoder-weight identity remains unverified.

65 affected isolated checks pass: self artifacts 20, artifact joins 21, review
report 15, report coverage 9. Tests use the actual units function for a scaled
synthetic pair, verify mixed versus genuine within-representation conflicts, old
unknown packets, invalid producer labels, fixed-count report output and unchanged
live audit results/call counts. All tests use synthetic data, scratch paths and
stubbed transports. No real inputs, new model calls, live writes, enabling, merge
or deployment. Full host suite and private coverage acceptance remain with review.


## 9 November — opt-in 30-second historical tier

Reviewer note 27 accepted the completion-path repair and measured the deferred
writer on Aegis at median 0.35 ms, p95 0.49 ms, max 0.62 ms at representative
occupancy. A 30-reply burst retained 9; queue loss across restart remains unknown.
Persisted queue-drop diagnostics are follow-up work, not claimed complete here.

`codex/judges-window30-attribution` adds the explicitly requested separate
ledger_attributed_window30 view. Original tight-window fields remain unchanged;
only unmatched copies with a sole in-scope call within 30 seconds can be added.
All nearby replies compete, including existing exact-ID matches outside the window.
Identity, metadata, clock, cutoff and reuse holds are retained. Extra exact-label
agreement counts provide sensitivity evidence without model-family guesses.
Neither strict eligibility nor training admission changes.

162 focused isolated checks pass: attribution 26, coverage 14, review report 16,
strict witness 106. Cases cover original-result preservation, exact window edges,
ambiguity, duplicate copies, competing unknown/different replies, reserved exact
IDs, configured-only/failed calls, bad clocks, cutoff, invalid opt-in, report
partition validation, scratch CLI and unchanged strict outputs. Synthetic only;
real added-tier counts remain for the reviewer on the admitted private snapshot.
No live writes, provider/model calls, enabling, merge or deployment.


## 9 November — selected completion joined to saved history

`codex/judges-completion-joins` adds the reviewer-requested prospective correlation
between router ledger completions and avatar/canonical/merged assistant history.
A random per-completion ID supplements the existing HTTP request trace so repeated
attempts under one request remain distinguishable. The accepted invocation's ID,
caller, raw-text hash and stored-text hash reach history; failures or absent helpers
never invent origin. Provider IDs remain separate. Offline matching validates all
bindings and refuses time fallback for bad explicit completion markers.

The saved row is a pre-final-guard history version, not delivery evidence. The
interaction-ledger subprocess and non-avatar producers remain without this new
marker. Full host suite, live coverage and latency acceptance stay with the reviewer.
Source investigation of stopped chat caller/missing surfaces remains open.

309 focused isolated checks pass: completion joins 9, router completions 7,
handler capture 21, attribution 26, draft identity 9, compute admission 44,
forced routes 16, learned cache 15, merged chat 31, coverage 14, strict witness 106,
ownership 11.
Tests execute real router/handler fragments with stub providers and ledger, including
retry acceptance/rejection/failure and concurrent request traces. No sockets or
live stores. Initial extracted fixture needed a local options initializer; fixed
and reran. One cache-suite invocation used an obsolete filename; corrected to the
existing learned-cache suite, all 15 pass. Existing draft usage ResourceWarnings
remain scratch-only and unrelated. No live writes, paid calls, enabling, merge or
deployment. Full Aegis suite remains the reviewer's responsibility.


## 9 November — producer/source coverage diagnostic

`codex/judges-source-coverage` extends the private coverage runner with fixed-label
source-copy/surface groups and explicit same-ID/exact-stored-text peer evidence;
no automatic repair or eligibility/attribution change. Caller metadata counters
now count nonempty model/provider values and private stage counts. Source history
shows the bilateral chat route predates the reported router-chat tail; it does not
prove why those retained router rows ended. The origin of those rows and the
missing-surface copies remain private-snapshot questions, documented with a runnable
command in `docs/judges-source-coverage.md`. No guessed surface or final-model
identity is installed.

78 focused isolated checks pass: coverage 21, attribution 26, merged chat 31.
Includes bounded private CLI, fixed public labels, cutoff/clock exclusions,
conflicting IDs/text/surfaces and unchanged original attribution. An initially
mistyped merged-suite filename failed before execution; corrected suite passed.
All three generated reports refreshed. No new live reads/writes, sends, model
calls, enabling, merge or deployment. Full host suite/private census remain with
review; next independent work remains durable queue diagnostics and encoder identity.


## 9 November — persisted deferred queue diagnostics

`codex/judges-durable-queue-counts` addresses note 27's volatile queue counters.
The existing background writer persists coalesced, configuration-scoped scalar
counter deltas in status.json.deferred; synchronous writes preserve them and later
processes accumulate them under the sink lock. Counters cover observed admissions,
confirmed/unconfirmed publications, queue-full skips and observed unavailable
workers. Each category is a lower bound, never a subtraction-based loss estimate.
restart_loss is explicitly null. Busy/start/exit failures and unflushed counters
may be absent. Claimed delta batches are not retried after failed/ambiguous writes,
so a replacement followed by failed fsync cannot double-count on retry.

Reply-side changes are bounded in-memory updates under the existing nonblocking
admission lock, with eight diagnostic configuration slots. No foreground disk I/O
added. FIFO remains eight packets plus one in flight; distinct reply packets are
not coalesced. Disable, config retargeting and fork reset include the new deltas.
A final background status flush adds a scan when the queue drains; fresh occupied
Aegis throughput/response measurements remain required. Earlier latency numbers
are not acceptance of this revision.

94 isolated checks pass: deferred capture 22, sink 19, handler hooks 21, store guard
32. Includes fresh-process counter preservation, overflow, ambiguous post-replace
failure, busy flush, packet failure without a false loss balance, bounded scopes,
unsafe status paths, hot disable, fork and process-exit loss. Only synthetic
throwaway stores and stub senders. Three generated reports refreshed and diff
checked. No live-store writes, capture enabling, paid/model calls, merge or deploy.
Full host suite and acceptance remain with review. Encoder identity remains open.


## 9 November — bounded audit encoding parameter receipts

`codex/judges-encoder-parameter-receipts` binds optional private self-audit vectors
to their actual encoding invocation, input/output hashes, bounded settings digest
and one before/after loaded CPU parameter snapshot pair per wrapper. No additional
encode, model load, GPU operation or device transfer. Byte/count caps bound hashing;
unsupported state and later calls remain unavailable. Encoder identity remains
unverified: tokenizer/execution code/configuration and forecast-call binding are
still missing. No learned weights or source text are retained by the new receipt.

Offline validation rejects contradictory receipts and reports fixed parameter
observation counts separately from full encoder identity and scoring. Legacy
packets remain missing, forecast packets not instrumented. Existing content-only
synthetic fixtures now explicitly remove the new receipt before manufacturing
legacy vector conflicts; forged new receipts have independent rejection tests.
Initial run exposed five such fixture contradictions; corrected, no contract
weakened. Removed imported-fixture duplicate discovery from the new test module.

69 isolated checks pass: parameter observer 12, self artifacts 20, artifact join 21,
review report 16. Tests cover parameter content/order/dtype/shape, bounded scans,
non-CPU refusal before transfer, unchanged return identity/call count, mutation
between snapshots, observer failures, missing settings and forged bindings. Actual
self-audit fragments and scratch CLI remain exercised by existing suites. Three
generated reports refreshed. No live reads/writes, new model calls, sends, enabling,
merge or deployment. Full host suite and loaded-runtime overhead remain with review.


## 9 November — forecast feature encoding links

`codex/judges-forecast-encoding-links` binds optional on-message self-readout feature
vectors to the existing encoding call and exact raw-to-normalized transformation.
The helper returns the original result object, observes one bounded CPU parameter
pair, and retains at most 256 inputs/65,536 raw values in process. Only selected
recent-own records enter private artifact packets; no new messages or weight bytes.
Other head modes, legacy cache and context-copy control remain unchanged.

Offline validation checks the forecast-call schema, input/raw hashes and exact
normalization including its floor. Missing links remain not instrumented; mixed
per-reference parameter states stay mixed at packet level. Full encoder identity,
training lineage and scoring remain unverified/unchanged. Host review must measure
up to two GiB of hashing per captured forecast and packet sizes against sink caps.

76 unit cases plus five readout scenario groups pass in isolated scratch:
encoder/feature observations 19, self artifacts 20, artifact joins 21, review report
16, existing readout groups 5. Actual job still makes two encode calls (feature batch
and untouched context-copy control); off/on results remain identical in the existing
contract test. Covers forged input/raw/transform links, null call receipts, small
norm floor, mixed/legacy states, bounds and failures without retries. The readout
suite emitted RuntimeWarnings in untouched fitting/ranking matrix routines while
norm/finiteness assertions passed; no mathematical change or warning suppression
was made. Three reports regenerated. No live data reads/writes, provider calls,
sends, enabling, merge or deployment; full host suite remains with review.


## 9 November — offline cross-call encoding consistency

`codex/judges-encoding-consistency` adds independent aggregate comparisons of
validated parameter, settings and raw-vector observations for exact bound content
groups. Differences survive incomplete peers; equality requires all references and
at least two distinct call markers. Legacy records remain incomplete. Raw forecast
links permit comparisons across representations without changing the existing
mixed/conflicting-vector classification, eligibility or scoring. No runtime path
changes or additional model calls.

65 isolated checks pass: artifact joins 30, review report 16, parameter receipts 19.
New cases cover same-output/different-parameter evidence, changed-during-call with
missing peers, raw versus normalized representations, duplicate invocation markers,
checkpoint partitioning, unbound-source exclusion, order invariance, legacy gaps,
public privacy and count denominators. The first run exposed aliased before/after
snapshots in the synthetic fixture; independent fixture copies fixed the test, with
validation unchanged. Generated reports refreshed. Full Aegis suite and real copied
evidence remain with review; no live writes, sends, enabling, merge or deployment.


## 9 November — innovation input contract

`codex/judges-innovation-input-contract` fixes a reproducible offline boundary gap:
innovation() built a target dictionary without checking uniqueness, so the last
admitted copy silently won. It now requires a list of identified records and
rejects repeated turn IDs, even identical copies. Census remains responsible for
admission/deduplication. The history minimum must be a positive integer; booleans,
floats, NaN/infinity and other malformed values are refused before scoring.

Three new regression cases reproduced the gaps before repair (14 failing and nine
erroring subcases). After repair, 155 isolated checks pass: strict witness 109,
review report 16 and artifact joins 30. Both conflict orders, identical copies,
invalid shapes/IDs and malformed minima are covered; existing valid scores and
causal percentile/control tests pass unchanged. This is a defensive function-input
fix, not evidence that census-produced historical reports had duplicate targets.
Generated reports refreshed. No producers, feeds, model calls, live data, sends,
enabling, merge or deployment changed; full host suite remains reviewer work.


## 9 November — historical attribution report contract

`codex/judges-attribution-report-contract` makes the formatter validate the
historical section's per-copy scope, no-admission/no-training declarations, fixed
tier/agreement/exclusion categories, counter conservation and timestamp-count bound.
Previously it could render contradictory effect declarations or agreement totals
as descriptive evidence. New synthetic regressions reproduced 11 failing subcases
before the repair. No attribution producer or selection rule changed.

A proposed clock-label change was rejected by the added positive-control test:
the producer already includes receipt-based cutoff clocks. Kept the original label
and fixed that test expectation before submission; no producer semantics changed.
The positive control verifies receipt-based exclusions and zero missing clocks.

46 isolated checks pass: report 20, historical attribution 26, including scratch
CLI with the optional 30-second view. Generated reports refreshed. Only synthetic
fixtures and fixed prose/count validation changed; full host suite remains with
review. No live reads/writes, model calls, sends, enabling, merge or deployment.


## 9 November — bounded synthetic encoder-cost benchmark

`codex/judges-encoder-cost-benchmark` provides a scratch-only CLI for the pending
CPU cost review. It exercises the real feature observer over bounded synthetic
CPU state, returning fixed aggregate timing/call/byte counts plus code hashes.
No model load, live store, checkpoint, GPU, network or sink. Guard tests attempt
outside writes, rename, subprocess and network and verify rejection before output.

25 isolated checks pass: benchmark six, parameter receipts 19. Bounds are checked
before allocation; unavailable snapshots cannot become successful timing reports.
CLI permissions, overwrite refusal, live-named roots, symlinks, output privacy,
exact return identity and scan/call counts are tested without latency thresholds.

Local synthetic 64 MiB/eight-tensor/three-repeat results: first observed-call wall
median/max 42.219/43.999 ms contiguous, 49.465/54.537 ms strided; repeat medians
1.886/1.918 ms. Two scans per first call, no extra encoding; 9 stub encodes/6 scans
per layout. This is observer overhead on local arrays, not loaded-model or Aegis
performance. Array initialization/helper imports are outside timing; temporary
copy cost is included, peak RSS is unmeasured. README has exact reviewer commands.
Generated reports refreshed. No producer/feed behavior change, paid calls, sends,
enabling, merge or deployment; full host suite remains reviewer work.


## 9 November — accumulated integration review handoff

`codex/judges-review-integration-handoff` documents the thirteen-commit chain after
the last reviewer-reported integrated base, with exact dependency order, active
metadata paths, optional capture costs and offline-only boundaries. No runtime
code changes. Reran 16 affected/ownership suites together at implementation tip
83118e87: 393 local isolated checks passed. The report distinguishes unittest cases
from older named checks; this is not the full Aegis suite.

`docs/judges-review-handoff.md` consolidates host acceptance work: full integrated
suite, occupied sink throughput/retention, CPU observation cost/compatibility,
private source/attribution counts and future artifact coverage. No historical
training decision or full encoder identity is inferred. No live inputs, sends,
model calls, enabling, merge or deployment. Previous submitted tips remain fixed.


## 9 November — historical exact-key coverage exposed

`codex/judges-attribution-match-methods` adds an offline-only matched-method count
and public fixed-label rendering. Exact completion keys, provider request keys and
bounded timestamp matches no longer disappear inside one aggregate matched count.
Counts are source copies after ambiguity/reuse/cutoff checks and overlap the
attribution tiers; observed copies may also have a ledger match. Legacy aggregates
remain readable with coverage explicitly unavailable. Window30 stays separate.

79 isolated checks pass: completion joins 10, report 22, attribution 26, coverage
21. New regressions first reproduced two missing-field errors and seven validation
failures. Synthetic fixtures cover mixed methods, duplicate copies/ledger records,
conflicting completion records, reused keys, cutoffs, observed-tier overlap,
legacy reports, privacy and nonmutation. No matching algorithm, live producer,
training permission, model call, live input, enablement, merge or deployment
changed. Full integrated Aegis suite and private-data runs remain with review.


## 9 November — historical router-chat test-origin lead

Read-only source tracing found an explicit lower-level router invocation with
chat surface in the old result-contract suite. At d335de72 it faked network calls
but did not isolate the compute ledger. Source commits e9000f2d and 19232935 added
OS-runner and direct-suite isolation on September 11. This is a conditional
source-level contamination path, not confirmed provenance of retained rows.
Accounting had to be importable and the store writable; source timestamps do not
prove deployment. docs/judges-source-coverage.md records exact source pointers,
synthetic fixture discriminators and the bounded check on the existing private
copy. Nine historical source assertions passed; no old module execution, private
inputs or test sends. No production code, matching, admission or stores changed.


## 9 November — byte-bounded burst capacity

Read reviewer note 28: reported integration c499460e, full suites 633/633 deploy
and 636/636 live; host burst still retained 9/30 with the eight-slot queue.
`codex/judges-burst-capacity` raises slots to 64 but independently caps queued
serialized bytes at 8 MiB, plus at most one 1 MiB in-flight packet. Reservations
and releases use the existing queue mutex; overflow skips without eviction or a
storage wait. No disk-format/config/counter-key change. Queue remains volatile.

66 affected isolated checks pass: deferred queue 26, sink 19, hooks 21. New
regressions first failed the thirty-packet burst plus two missing byte-bound APIs.
The stalled-writer fixture now retains all thirty roughly 24 KB packets; concurrent
large submissions hold the 8 MiB bound, and failures/drains release capacity.
These are local synthetic contracts, not host latency acceptance. Durable spool,
restart replay and host cost tests remain open; no claim of restart survival.
No live inputs, enabling, sends, model calls, merge or deployment.


## 9 November — stable packet publication for recovery

`codex/judges-replay-publication` adds optional stable IDs to the internal publisher.
Matching retries verify owner-private exact bytes under the sink lock and sync the
file/directory; conflicts are refused rather than overwritten. Existing producers
omit the new argument, so their publication semantics are unchanged. Replays do
not reset retention age or reapply diagnostic/persisted status counters.

73 isolated checks pass: sink 26, deferred queue 26, hooks 21. The new child-process
crash fixture exits immediately after linking the packet and retries without a
second packet; concurrent writers, malformed IDs, unsafe files, config changes,
capacity and fsync failure are also covered. No hardware power-loss claim. This
is the first restart-recovery prerequisite only: ingress spool, startup replay,
bounded expiry and acknowledgement remain unfinished. No live writes, enabling,
model calls, sends, merge or deployment; full host checks remain with review.


## 9 November — durable ingress and startup replay

`codex/judges-durable-spool` completes optional synchronous private staging plus
background replay, stacked on 272b2d0b. Records preserve exact bytes, config identity
and age; stable publication and acknowledgement handle process exits without
another final packet. 64 spool entry names/8 MiB logical bytes are bounded separately
from final packet count; final capacity reserves the spool budget. New startup
hook recovers enabled durable capture without a new turn. Default memory mode,
reply text/routing and delivery/admission semantics remain unchanged.

25 synthetic spool checks pass, plus sink 26, queue 26 and hooks 21. Includes real
process termination, config/age retention, capacity, privacy, busy locks, immutable
bytes, 30 roughly 24 KB packets and fail-open hook behavior. This is not hardware
power-loss or host latency acceptance. Durable ingress introduces foreground scans
and fsync; the earlier memory-queue latency does not apply. Diagnostics remain
lower bounds and restart loss unknown. No private input/config change, enabling,
sends, model calls, merge or deployment. Host integration and acceptance remain
with review; work continues on independent branches.


## 9 November — retained encoder call costs

`codex/judges-encoder-call-cost` continues from 0c9c42cf while prior tips remain
fixed for review. Optional capture now records monotonic durations for the existing
parameter-before, encode and parameter-after stages. Null denotes unmeasured or
invalid clock evidence, not zero. Existing output objects, exception behavior,
encoder-call counts and once-per-wrapper snapshot budget are preserved. The
capture-off path is unchanged. No real encoder is loaded or timed by this batch.

Offline cost aggregates deduplicate invocation markers across batch outputs and
source references. Conflicting cost/snapshot copies exclude that call; legacy
receipts remain valid and unknown call identity is counted separately. Fixed
numbers-only reports keep partial cost evidence separate from identity/admission.
111 isolated checks pass: new cost 14, parameter receipts 19, artifact joins 30,
review report 22, self artifacts 20, synthetic benchmark 6. Report validation and
fixtures cover malformed counts/durations, privacy and nonmutation. Host cost and
full integration remain reviewer work. No enabling, live inputs/writes, model or
paid calls, merge or deployment.


## 9 November — fixed historical fixture counts

`codex/judges-historical-fixture-counts` follows 3260aa77. The existing offline
coverage report gains a fixed source-fixture metadata comparison, partitioned by
exact caller, complete/missing metadata, clock availability and cutoff. Identical
rows deduplicate; distinct matching records are not collapsed into one imagined
test run. Output contains only fixed labels/counts and the public source revision.
Origin stays unconfirmed and baseline attribution remains unchanged.

55 isolated synthetic checks pass (coverage 29, attribution 26); five additional
source assertions verify the archived fixture and accounting call without running
historical code. Tests cover strict token types, extra fields, all tuple changes,
clock ambiguity, cutoff, duplicate rows, nonmutation, private-label exclusion and
the actual CLI's permissions/hashes. No real-data census or execution evidence was
read. Reviewer owns that check using the already-copied evidence. No live writes,
new model calls, enablement, merge or deployment; heartbeat continues.


## 9 November — checkpoint field consistency

`codex/judges-checkpoint-consistency` follows 2895b42f. Offline artifact ingestion
now validates the existing versioned checkpoint observation contract, rejecting
malformed fields or invented verified identities. Schemaless legacy records with
valid hashes remain unknown. The aggregate compares manifests sharing a checkpoint
hash, excluding separately validated read clocks, and preserves conflicts with
incomplete peers. It emits only fixed counts, not labels, dates, hashes or vectors.

111 affected isolated checks pass: new consistency 13, joins 30, availability 12,
report 22, cost 14, self artifacts 20. Tests cover current and older producer shapes,
read-clock differences, all metadata conflict fields, malformed/forged copies,
legacy mixing, duplicate references/packets, forecast/audit grouping, nonmutation
and public formatter conservation/privacy. Consistency is not authentication or
fitting-lineage verification; content joins and scoring permission stay separate.
No runtime producers, capture flags, private inputs, model calls, live writes,
merge or deployment changed. Host integration remains with review.


## 9 November — pending-to-forecast handoff observations

Continued from fixed submitted c6829c80 on a new branch. Optional capture now
hashes the existing pending value/locator at launcher return and job consumption,
then binds job observation to the exact unchanged saved row. The offline replay
and formatter report only fixed states/counts, with code included in run hashes.
No new origin markers enter the historical or runtime forecast log. Missing or
conflicting evidence never becomes a joined observation or training admission.

307 affected isolated checks pass: new handoffs 19, existing forecast inputs 15,
source clocks 12, census/innovation 109, existing on-message head 32, public report
22, capture hooks 21, sink 26, deferred queue 26 and durable spool 25. New tests use stub process launches/encoders/senders and
synthetic files, including the actual replay CLI and private output permissions.
Observer failures preserve output and previous sidecars. Full integration, real
cost, source authenticity and delivery association remain unverified. No live
writes, model calls, enabling, merge or deployment.


## 9 November — shared main-chat forecast event key

Continued on a new branch from f5dd8728. Main chat previously launched its forecast
before the later bilateral coordinator existed and passed no turn ID. Both can
use the already-existing deterministic request-event mapping without moving any
coordinator or forecast call. The early hook now reserves that key only for a
validated current HTTP marker, only on chat/full and only when the explicit turn
argument is the default empty string. Missing context and observer/helper failures
remain unknown; test mode still exits before either correlation or launch.

105 affected isolated checks pass: key propagation 11, coordinator 33, forecast
handoffs 19, existing on-message head 32 and completion joins 10. The existing
synthetic head suite emits numerical warnings but all 32 checks pass. Tests
include actual pending/log propagation, two interleaved request contexts and
unchanged no-event random coordinator fallback. This metadata operates with
capture off. No history/merge/post-turn feed, model, scoring or training changes;
no private data, live calls/writes, enabling, merge or deployment.


## 9 November — reverse handoff cardinality correction

Source review found that forward uniqueness did not prevent one pending resource
from being claimed by two distinct saved forecast rows. Three new synthetic
regressions reproduced false joined states. The offline index now retains every
supplied job row hash per pending resource before filtering; conflicting, absent
or outside-cutoff peers cannot be hidden. Distinct pending resources sharing a
turn remain separate. No runtime producer, forecast selection or admission change.

165 isolated checks pass: handoffs 23, chat forecast keys 11, report 22 and
census/innovation 109. Fixtures remain synthetic and sender/encoder/launcher
boundaries stubbed. No private data, new capture, model calls, live writes, merge
or deployment. Submitted predecessor branches remain fixed for review.


## 9 November — stored runtime fields around existing encodes

Optional artifact receipts now fingerprint bounded stored settings before/after
each existing encode; no extra encoding, tokenizer calls, configuration methods,
file loads or version-discovery imports. Partial scope and unknown tokenizer/code/
fitting identity are explicit. Runtime changes survive audit deduplication, while
conflicting copies of one call are excluded from cost aggregation. Legacy receipts
remain valid. Capture off is unchanged; capture-on real-host overhead is unmeasured.

221 isolated checks pass: runtime 16, parameters 19, costs 14, artifacts 20, joins
30, report 22, benchmark 6, checkpoint consistency 13, forecast inputs 15, handoffs
23, entry owners 11 and store guard 32. One initial new-test fixture attempted to
assign a read-only namespace dictionary; corrected to clear/update its synthetic
contents. All final tests pass. No private input, model calls, live writes, merge
or deployment. Submitted predecessor tips remain fixed for independent review.


## 9 November — fitting-boundary observations

Source tracing confirmed the anchored readout is preferred by the existing self
forecast entrance. Its self-only optional observer now binds existing ordered
input partitions to completed parameters/metadata and exact matching checkpoint
readback after save returns. No extra encoder calls, training runs or schema
changes. Failures remain passive; source/encoder identity and durability stay
unverified. Historical dates are not reconstructed. The offline completion-reader
is still open and current scoring/admission ignores these receipts.

124 isolated checks pass: new fitting 14, existing readout 5, artifacts 20, sink 26,
runtime 16, owners 11 and store guard 32. Synthetic numerical warnings persist in
existing matrix operations, without assertion failures. Generated reports refreshed.
No private input, real model, live writes, enabling, merge or deployment.


## 9 November — fitting receipts reach the offline review

Added strict offline receipt validation, exact checkpoint/metadata/mode/byte
comparison, conservative conflict handling and before/during/after-read counts.
Replay accepts an explicit optional self_fit_completions list and binds the reader
code in its private run manifest; report renders fixed aggregate fields only.
Malformed peers fail before filtering. Multiple distinct receipts remain ambiguous;
legacy/missing evidence is never upgraded. Census and innovation stay unchanged.

178 isolated checks pass: reader 17, report 22, artifact joins 30, census/innovation
109. Actual CLI checks private permissions, code hashes and unchanged nonempty
scores. Initial fixture filename corrected to the existing private-run.json.
Generated reports refreshed. No private data, runtime producer change, model call,
live write, enabling, merge or deployment. Full evidence and host integration open.


## 9 November — partial runtime comparison reaches the review

Retained forecast/audit runtime snapshots now have their own content-group count
in replay and the public review. Observed changes survive incomplete peers;
matching needs every reference and two distinct calls. Legacy data is unavailable,
not reconstructed. Census and innovation remain exactly unchanged in CLI tests.
187 isolated checks pass: comparison 12, joins 30, report 22, costs 14, census and
innovation 109. Generated reports refreshed without changes. No private input, new
capture, runtime producer change, model call, live write, enabling, merge or deploy.


## 9 November — bounded encode entrypoint observation

Loaded Python code now has optional before/after fingerprints, audit retention,
invocation conflict handling and fixed offline consistency counts. The original
encode method is resolved once and called once. Missing/native implementations
remain unavailable; no source reads or extra model calls. Full implementation and
source identity are not claimed. Two fixture issues (capture-root nesting and
unordered receipt selection) corrected. Real-host cost and integration remain open.

211 isolated checks pass: entrypoint 14, runtime producer 16, parameters 19,
encoder costs 14, artifact joins 30, runtime comparison 12, review report 22,
self artifacts 20, forecast inputs 15, encoder benchmark 6, entry owners 11 and
store guard 32. Generated ownership/coverage/store reports refreshed without
changes; diff check clean. All inputs synthetic, sends and encoders stubbed.


## 9 November — coverage-checked synthetic cost measurement

Version 2 verifies runtime/entrypoint observations as well as parameter snapshots,
checks fresh repeat invocations and separately measures new receipt retention.
Configured synthetic runtime profile measured at 64 MiB/eight tensors/three runs:
first-call medians 42.572/50.118 ms contiguous/strided; new-input repeat medians
4.415/4.406 ms. No real model or tokenizer load, live store, send or deployment.
No production behavior change. Real-host costs remain unmeasured.

21 isolated checks pass: benchmark 10 and entry owners 11. Tests include both
layouts/profiles, observation failure on first and fresh repeat calls, invalid
profile/options before allocation, private aggregate output, no overwrite, and
scratch/network/process boundaries. Generated reports refreshed without changes;
diff check clean. Two additional CLI measurements used only synthetic arrays.


## 9 November — aggregate handoff support cannot reuse a launch

Reproduced six failed assertions in three synthetic regression cases: impossible
launch support counts passed the validator and renderer. Added paired-launch and
job conservation bounds. The producer already refused pending-resource reuse;
this change brings its public aggregate validation into line. Valid duplicate,
orphan and conflict cases remain accepted. No production or admission change.

59 isolated checks pass: forecast handoffs 26, review report 22 and entry owners 11.
Generated ownership, untested and store reports refreshed without changes; diff
check clean. Regression evidence was captured before applying the validator fix.


## 9 November — correct self-forecast checkpoint replacement race

Reproduced old prediction/new checkpoint-ID mismatch, artifact suppression and
late deletion failure. Self modes now parse/hash the same buffer and use its
identity, including capture off. The other head and default loader are unchanged.
106 isolated checks pass (binding 8, artifacts 20, availability 12, readout 5,
inputs 15, handoffs 26, clocks 9, owners 11). Existing replacement expectation now
requires a retained matching artifact. Synthetic numerical warnings persist with
all assertions passing. Host costs and integration remain open; no deployment.


## 9 November — self-audit checkpoint replacement regression

Before the fix, synthetic replacement paired old bytes with a new cutoff (failure)
and deletion after hashing raised a late FileNotFoundError. Self audits now use
one descriptor's bytes/time and reject observable changes during the read.
80 isolated checks pass: audit races 6, artifacts 20, availability 12, readout 5,
ranking 26, owners 11. Capture-off behavior is included; mtime remains an estimate,
not an attested fitting date. No live data, real encoding, enabling or deployment.


## 9 November — counterpart and arriving inputs no longer omitted from observation

Optional artifacts now record ordered selected-input hashes and six computed array
hashes before prediction, without additional encoding. Existing artifacts remain
available when the new observer fails. The offline reader validates optional data
and cross-checks retained own inputs; no complete-ancestry claim or admission change.
148 isolated checks pass: selected 8, artifacts 20, inputs 15, joins 30, runtime 12,
loaded checkpoint 8, availability 12, owners 11, store guard 32. Maximum bounded
receipt is under 4 KiB. Source and host evidence remains open; no deployment.


## 9 November — baseline receipt bound to the exact forecast version

Added bounded hash-only receipt for the existing rendered context and raw/normalized
baseline output. Offline states separate absent, conflicting, mismatched and bound
observations; packet counts do not become eligible turns. 175 isolated checks pass:
baseline 10, artifacts 20, inputs 15, selected 8, joins 30, report 22, cost 14,
loaded checkpoint 8, readout 5, owners 11, store guard 32. Encodes/scans unchanged.
Formatter/observer failure preserves old artifacts; encode failure propagates
without retry. Full source/encoder/delivery evidence and host costs remain open.


## 9 November — selected-input coverage no longer absent from reports

Added offline packet states for selected-feature receipts, preserving duplicates,
conflicts, missing versions and arrival/cutoff distinctions. Shared exact-row
validation leaves baseline semantics unchanged. 90 isolated checks pass: coverage
9, selected 8, baseline 10, joins 30, report 22, owners 11. Actual scratch replay
CLI writes 0600 aggregate-only output. No producer or admission change; full
source/encoder/delivery evidence and host integration remain open.


## 9 November — character-reference prototype, not another receipt batch

Implemented day-held-out reference familiarity, interpretable style, exact-linked
positive-feedback reference, paired controls, model-family strata and day-level
intervals. Reuses historical attribution with a distinct 30-second sensitivity
view. Input vectors are explicitly supplied frozen caches; no encoder calls.
49 isolated checks pass: prototype 12, attribution 26, owners 11. Private CLI writes
0600 aggregate/evaluation/run files in new 0700 scratch output. Synthetic fixture
results are labelled; actual-history results and candidate dates await the private
bundle/run. Full scope and limits are in the new instrument README.


## 9 November — context-matched character-family comparisons

`codex/judges-character-context-comparison` follows d9ab262c without changing its
review tip. Adds outcome-independent same-day/context/language/length matching,
one-to-one family pairs, four percentile differences, uncertainty and explicit
unmatched counts. 26 isolated checks pass (prototype 15, owners 11). Topic-disjoint
shared-day fixtures correctly report no comparable pairs, not model invariance.
Private copied-history evaluation remains Claude's next step. No new model calls,
live changes, deployment or merge; see the character-reference README.


## 9 November — character evaluator reuses fold statistics

`codex/judges-character-fold-reuse` follows c779cbf0 while Claude reviews/runs that
fixed tip (note #31). Reference statistics are reused within each evaluation fold,
including calibration and witnessed-positive references; controls use an exact-ID
index. Complete output parity with the original scorer is tested. 29 isolated
checks pass (prototype 18, owners 11); the synthetic build count remains 92 under
multiplied evaluation/control load. No persistent cache or new encoding. Actual
private results and host timing are still outstanding; no deployment or merge.


## 9 November — character evaluation groups from the accepted review

`codex/judges-character-evaluation-groups` follows 06a18d75. Optional exact-reply
annotations expose novelty/refusal/opposite-stance/humor/surface-shift percentile
summaries, separate declared owner/reviewer sources and missing/unscored coverage.
They do not alter selection, admission, scoring or witnessed-positive references.
32 isolated checks pass (prototype 21, owners 11). No threshold or identity verdict.
Actual private-history groups remain unmeasured; no new encoding, live writes,
merge or deployment. Claude's concurrent private run is not duplicated.


## 9 November — readable aggregate character results

`codex/judges-character-summary` follows 40b4f416. The private scratch CLI adds
0600 `summary.md` with aggregate coverage, candidate dates/counts, measurement
intervals, family comparisons and optional groups. Unknown stays unknown and
synthetic inputs cannot be presented as real-history findings by the renderer.
36 isolated checks pass (prototype 25, owners 11). Private fields are omitted;
no scoring, model or live changes. Claude's actual copied-history run remains
outstanding; this adds a reviewable artifact for its results without duplicating it.


## Note #32 — private exploratory results and family-balance follow-up

Claude reports primary insufficient (38 replies on one day); window30 has 123
replies across 36 days, zero reviewed controls and unverified encoder revision.
Surface-complete engagement counts, reviewed controls and encoder pinning remain
open. Added reference-family composition by candidate day and actual held-out
fold, with primary/sensitivity separation and zero-coverage handling, to expose
rather than silently correct imbalance. Synthetic tests pass; real composition
counts will come from the next private run. No identity conclusion or frozen dates.


## Notes #33–34 — mode-specific character references

`codex/judges-character-mode-strata` follows 97917df6. The missing-surface hypothesis
is withdrawn after Gloria's clarification; preserve avatar/ReelRoom separately and
the ten provisional dates. Mode is bound from independent exact-linked local
observations, never serving family. Unknown/conflicting modes remain unscored;
reference/calibration/positive subsets match both mode and surface. Cross-family
comparisons run within known modes and label absent overlap not identifiable.
Schema v2 and its summary expose mode coverage and omit pooled family effects.
42 isolated checks pass (prototype 31, owners 11), including no cross-mode/surface
influence. Next: actual local mode export, provenance-reviewed controls, encoder
revision/hash pinning, and Claude's private rerun. No model calls or live effects.


## 9 November — explicit encoder identity retained in the private manifest

`codex/judges-character-encoder-pin` follows bc5d784d. The exact declared encoder
contract is preserved; optional bounded hashing reads one supplied regular scratch
artifact without loading it. Expected/observed hashes must agree when both exist;
unknowns remain unknown and raw identity is excluded from aggregate outputs.
45 isolated checks pass (prototype 34, owners 11). A hash does not authenticate
cached-vector derivation, runtime, multi-file completeness or revision labels.
Real identity observation and reviewed control data remain with the private run.
No inference, download, live write, merge or deployment.


## 9 November — reviewed control pools and deterministic matching

`codex/judges-character-reviewed-controls` follows dd811da0. Schema v3 adds a
local reviewed control pool, context-only greedy matching without replacement,
primary-first target order, and explicit review bindings for pooled and paired
controls. Foreign candidates must be non-subject and surface-matched; his own
other-surface text is a separate comparison, never an authenticity negative.
Missing reviews remain excluded. All input assistant text is barred as a control,
including unattributed rows; mode, language, length and context gates still apply.
Public reports contain only aggregate coverage; private-controls.json retains all
selected pairs, including those lacking scorable reference folds. Review/source
claims remain supplied, not independently authenticated. No real controls were
collected here; private data collection and rerun remain with the reviewer.
53 isolated checks pass (prototype 42, owners 11), using synthetic non-intimate
fixtures. Generated reports refreshed unchanged. No encoder/model calls, network
collection, live writes, merge or deployment. Prior review branch tips stay fixed.


## 9 November — source contract aligned with the private control collection

`codex/judges-character-control-sources` follows 80486b4b. Note #35 identifies
Slack, MoltBook and journal controls and store-authorship evidence; the prior
validator would reject those fixed source labels. Controls now admit `slack`,
`moltbook`, `journal` and a separate `store_authorship` reviewer class. This does
not expand engagement/reference surfaces or owner/reviewer evaluation annotations.
The same exact source binding, evidence hash, explicit author/mode, timestamp and
matching constraints remain required. No provider/filename/missing-mode inference.
Selected counts retain source surface and evidence class; private pair records do
too. Source authorship remains explicitly unverified, and store evidence is not
represented as a human review. Private collection/rerun belongs to the reviewer.
The short plain-language results page requested in #35 remains pending actual
mode-by-surface coverage; no new real-data results are asserted here.
Validation: 45 isolated prototype tests; ownership checks recorded in the dated
coordination handoff. No live writes, calls, merge or deployment.


## 9 November — plain-language reader page prepared for returned aggregates

`codex/judges-character-reader-summary` follows a50959ad. The offline CLI now
writes reader-summary.md alongside its detailed report, using only fixed labels
and aggregate numbers. The page explains familiarity, rank versus identity
probability, measured versus selected controls, provisional reference days,
positive-feedback limits and supplied source/encoder evidence. Primary and
sensitivity views stay separate; unscored primary evidence is never replaced by
a sensitivity finding. Unknown mode and missing measurements remain explicit.
Synthetic runs are prominently labelled; no real rerun coverage is claimed.
Three new tests plus the actual CLI check cover missing primary coverage, true
zero versus unknown, unsafe metadata exclusion and malformed numeric rejection.
48 isolated prototype checks pass; ownership result is in the dated handoff.
The final real-data summary remains pending Claude's mode-by-surface aggregates
from note #35. No private data collection, live changes, model calls or deployment.


## 9 November — prevent private input values from leaking through CLI failures

`codex/judges-character-private-errors` follows ce4c6e00. A focused privacy review
reproduced two leaks with synthetic markers: an invalid timestamp appeared in a
parser traceback and a missing source filename/path appeared in stderr. The CLI
now exits nonzero with a fixed JSON failure label and allowlisted exception class,
without exception text or traceback. Imported functions keep normal exceptions for
private local debugging. Failed writes may leave partial private artifacts and are
not successful reports; this is documented. Standard argument usage errors remain
unchanged, so secrets do not belong in CLI arguments.
50 isolated prototype checks pass after both new regressions failed on the old
entrypoint; ownership results are recorded in the dated handoff. No real private
records were accessed. Real coverage is still pending the independent rerun.
Notification delivery remains rate-limited until the recorded 11:43:46 CST retry
window; no early retry, new destination, live writes, merge or deployment.


## 9 November — prospective mode decision receipts and honest character2 summary

`codex/judges-prospective-mode-receipt` follows 97ea9e09, implementing note #36.
Existing gate decisions now produce content-free request-local metadata with turn,
request and evaluated/selected completion IDs. Exact YES/NO provide mode; skipped,
failed or ambiguous gates remain unknown. Refusal-guard reroute decisions have
separate times/causes and do not claim a replacement succeeded. No extra gate,
provider call or routing mutation. Metadata is retained beside generation_join
in history/canonical records and via the existing background ledger environment;
receipt construction performs no file/network I/O. Existing history write timing
is unchanged. Both ledger twins agree; merged chat retains the new field.
50 isolated checks pass: mode receipts 9, completion joins 10, router completions
7, device marks 13, ownership 11. All sends/providers are stubbed and stores are
scratch. Six changed Python sources compile without execution. Generated reports
refreshed unchanged. The plain-language status page uses only reviewer-reported
character2 aggregates: 0/123 mode coverage, zero controls, and no stability verdict.
These code changes are for review, not deployed. Gate-bypassing routes will still
be unknown; a provider toggle is not an independent intimacy decision.
New note #37 authorizes historical somatic marks first and an explicitly labelled
owner family rule second; that is next work on a separate branch, with the private
character3 run left to the reviewer. The reported latent-feed flake remains a
separate follow-up. Completion ntfy alerts are cancelled under the user's new rule;
only new unresolved issues may use ntfy. No live writes, merge or deployment.


## 9 November — historical mode priority and family-derived comparison exclusions

`codex/judges-historical-mode-evidence` follows 2dccf7f0 for note #37.
The offline prototype consumes bound prospective mode receipts first, preserving
unknown/invalid receipts as unknown, then independent exact observations, reviewed
somatic intervals, and an explicitly enabled owner family rule. Final mode_source
is retained with private evidence hashes; public reports show only source counts,
somatic coverage and disagreement with the family rule. Reference folds expose
source composition. Family-labelled targets and targets whose reference folds
include family-labelled replies are excluded from independent family comparisons.
No remaining overlap means not_identifiable, never invariant.

Source inspection found the narrator persists through/at/narration and a somatic
thread, without the detected interval. Its current 24-hour scan is not a session
label. The private importer must review a bounded interval from retained evidence;
join is same surface plus optional exact session, inclusive start/end, zero padding,
maximum 7200 seconds. Unbounded marks contribute no mode. Overlapping disagreement
stays unknown; stale review bindings fail. Original records and input bundle must
remain private. No real messages/stores were opened here and no encoder/model calls
were added. This is not a character3 result or a change to provisional golden days.

Validation: 57 isolated prototype checks and 11 ownership checks pass (68 total);
new cases cover opt-in fallback, somatic priority/bounds/session/review/conflicts,
receipt binding/unknown priority, reference contamination and aggregate privacy.
Generated reports are refreshed unchanged. Source documents give the exact private
import contract. Claude owns the private character3 run and full-suite review;
Gloria owns deployment. The latent-feed flake is still a separate follow-up.
No live writes, merge or deployment; no completion ntfy under the revised policy.
Heartbeat remains ACTIVE.


## 9 November — retain private mode assignments before scoring

`codex/judges-private-mode-assignments` follows 94dca59e. Inspection found that
private-evaluation.json records only scored primary replies. For an unscorable
primary set it is empty, even when historical mode labels exist. The CLI now
writes private-mode-assignments.json (0600) for all admitted/deduplicated replies,
including unknown, sensitivity-only and insufficient-reference cases. It retains
normalized mode/source/evidence hashes plus reply identity, time, surface, family
and admission basis; no content, vectors or session IDs. The file remains private.
Retain original input/evidence bytes for reconstruction; hashes are not independent
authentication. The optional run collector leaves scoring and aggregate returns
unchanged. Excluded input replies do not enter this file.

Both new regressions failed before implementation; all 59 isolated prototype
checks pass afterward, including real CLI permissions and public-output exclusion.
Ownership check results are recorded in the coordination handoff. This changes no
mode decisions, references, controls, thresholds or public scores. No private
collection, encoding/model call, live write, merge or deployment. Claude owns the
private character3 run; its aggregates have not arrived. The latent-feed failure
trace remains requested; no speculative fix or repeated alert. Heartbeat ACTIVE.


## 9 November — distinguish absent mode measurements from measured zeros

`codex/judges-mode-coverage-unknown` follows 32beae6f. Review found that both
summary renderers treated absent source counters in older schema-v3 reports as
zero, although those reports never measured source-labelled mode coverage. They
now state not recorded/not measured when the recording-state field is absent.
New sparse-counter reports still preserve measured zeros. Somatic disagreement
is not measured when no labels are comparable; zero disagreements with a positive
denominator remains zero. Invalid state flags/counts fail without echoing metadata.

Both new regressions reproduced the issue before the fix; 61 isolated prototype
checks pass afterward. Ownership validation is recorded in the coordination handoff.
This is a presentation correction only: no mode/source assignment, scoring,
reference/control selection or input admission change. No private data, model calls,
live writes, merge or deployment. Character3 and the latent-feed failure trace
remain with the reviewer. No repeated status alert; heartbeat remains ACTIVE.


## 9 November — aggregate-only summary command for character3

`codex/judges-aggregate-summary-cli` follows f6647451 for note #38. The existing
reader and detailed renderers can now run through --aggregate-report, with no
private bundle, scoring or encoder/artifact access. It reads a bounded schema-v3
aggregate file inside explicit private scratch and writes only the two pages plus
a source-byte/renderer hash manifest into a new 0700 directory, files 0600. Both
pages validate before writing; arbitrary input metadata is not echoed. Source
bytes are unchanged. No scoring or result values are regenerated.

Mixed evaluation/artifact options, symlinks, outside-scratch paths, oversized input
and overwrites are rejected. Existing evaluation CLI behavior remains intact.
64 isolated prototype checks pass, including actual aggregate CLI success without
private inputs, exact renderer parity, permissions, error privacy and refusal cases.
The success and sanitized-error regressions failed before implementation. Required
report/ownership results are in the coordination handoff. README gives the exact
command for the private character3 report. Actual character3 aggregates and the
latent-feed failure trace remain pending with the reviewer; this is not new data.
No private reads, model/encoder calls, live writes, merge or deployment.
Heartbeat remains ACTIVE; no completion/routine ntfy under the revised policy.


## 2026-11-09 — Exact-exchange control mode inheritance

Coordination #39–40: foreign controls can inherit the mode of their explicitly
reviewed adjacent subject reply, with source surface and both text hashes bound.
There is no timestamp-nearest or control-author-family guess. Invalid links stay
unknown. Pool matching retains the source exchange assignment when choosing a
target. Private pair outputs retain the anchor/source evidence; public output is
counts only. Family-derived mode remains an assumption and cross-family exclusions
are unchanged. 69 isolated prototype checks pass; ownership validation and exact
review commit are recorded in the coordination reply. No new private data run,
model call, live write, merge or deployment. Prospective somatic metadata is next;
full suites and private character rerun remain with the reviewer. Heartbeat ACTIVE.


## 2026-11-09 — Prospective somatic intervals from the existing narrator call

Coordination #39–40: optional ordinal bounds are returned by the existing narrator
call, mapped to explicit timestamps/turn IDs/text hashes and retained as metadata
in the existing narration snapshot and thread extra fields. Legacy narration and
NONE handling, schedule, dedup, model selection and call count remain intact.
Missing/invalid evidence never labels a daily window. Strict per-turn matching in
the offline prototype consumes reviewed projections without reading narration text;
nearby turns are excluded. Provider-reported served model is retained when present,
otherwise unknown; fallback remains unknown. Metadata is private, fixtures synthetic.

Targeted validation: 72 prototype, 11 interval receipt, 6 existing thread-source,
6 existing scheduling checks; ownership results and exact review tip are in the
coordination reply. No actual provider call, private record read, live write, merge
or deployment. Real format compliance/coverage remains unmeasured; Claude owns full
suite and private runs. Same-exchange control modes are on the preceding review tip.
Per-surface within-mode results remain pending sufficient ordinary-use coverage;
no request for test messages. Heartbeat ACTIVE; no completion/routine ntfy.


## 2026-11-09 — Numerical judge candidates and randomized latent-feed diagnostics

Coordination #42–43: assessed all 31 subconscious entries plus deviation and voice
coherence, with input/scorer/failure-mode/proposed synthetic test for each in
experiments/nonllm-judges/README.md. Implemented two offline components: unique
original-act/day recurrence for reviewed topics, and complete-link candidate groups
from supplied frozen cached vectors. Complete indirect lineage, exact hashes,
mode/surface/source/day scope, input bounds and explicit unknown/exclusion behavior
are preserved. No automatic yearning, scar, resolution, duplicate-removal or identity
verdict. No runtime wiring, existing feed change or additional model call.

17 isolated prototype checks and 11 ownership checks pass. Synthetic aggregate CLI
verified. Generated reports refreshed unchanged and diff clean. The stress driver
in experiments/latent-feed-diagnostics/stress.py ran the unchanged latent-feed suite
50 times in fresh workers with recorded randomized orders, five time zones and four
available locales: 750/750 checks pass in 29.422 seconds inside the local isolation
boundary. Log: /tmp/judges-latent-stress.log. This does not reproduce or fix the
historical flake. The original traceback is unavailable; the reviewer will retain
future failures. No assertion was weakened and no speculative production fix made.

Full isolated suite/private character4 provenance review stays with Claude; runtime
format compliance and per-surface results still need ordinary-use evidence. No
private records, live writes, GPU/model/encoder/provider calls, merge or deployment.
Exact pushed tip is in the coordination reply. Heartbeat ACTIVE.


## 2026-11-09 11:14 CST — offline voice familiarity and sustained drift (#44)

Added experiments/nonllm-judges/voice_drift.py on codex/judges-voice-drift-prototypes
above 71193c5702e3cd85de5262b0bb07eed2863d1c43. Reuses character-reference metric
functions with exact cached text/vector/encoder bindings and complete original-act
lineage admission. Known mode and surface are separate; target day and all future
days are excluded from its reference. Calibration leaves each reference day out,
weights days equally, and emits an empirical familiarity percentile with an inclusive
0.2–0.8 abstain band. It is not an identity probability or a quality verdict. Sparse
or degenerate coverage stays unscored. A rounding repair keeps identical features
tied despite floating-point arithmetic.

Drift needs four consecutive calendar days beyond the held-out baseline maximum
plus an explicit distance margin. A single outlier cannot flag sustained change.
Persistence alone does not update the reference. An exact, externally owner-reviewed
adoption receipt can simulate replacing the scoped reference for later days only;
stale, unbound, nonpersistent, family-derived or adjacent-rule adoption evidence
cannot promote itself. Private version/membership receipts retain the transition;
public output is aggregate only. No writes or runtime integration. README states
the experimental thresholds, unverified source/adoption claims, lack of real-world
calibration and how changes can be adopted without a self-scoring feedback loop.

123 isolated checks pass: new voice/drift 23, existing character-reference 72,
existing numerical candidates 17, ownership 11. Logs: /tmp/judges-voice-drift-tests.log,
/tmp/judges-voice-character-tests.log, /tmp/judges-voice-candidate-tests.log and
/tmp/judges-voice-owners.log. Generated reports refreshed unchanged; diff clean.
No private records, model/encoder/provider calls, live writes, model changes, GPU,
merge or deployment. Full suite/private character4 investigation stays with Claude.
The latent-feed full-suite-interaction hypothesis is still unconfirmed: the earlier
50-run pass did not identify a root cause. Exact pushed tip is in the coordination
reply. Heartbeat ACTIVE; no completion/routine notification.


## 2026-11-09 11:34 CST — witnessed humor and textual taste (#45)

Added experiments/nonllm-judges/witnessed_facets.py on
codex/judges-witnessed-humor-taste above 85ec09076ea4628fe069405dded620b65d9b3f08.
Humor accepts only owner haha-plus reactions exactly joined to the adjacent exchange
or exact joke ID/hash-bound 4–5 star practice ratings. Unknown/lower/unrated outcomes
never become negative labels. Duplicate observations cannot multiply positive acts;
conflicting reaction adjacency refuses. Original-act lineage and cached-feature
provenance checks are reused, including indirect influence exclusion.

References share mode, surface and item kind. Both reference acts and observed
positive feedback must predate the entire target local day. Two or three positive
days produce similarity only, with no empirical calibration and an abstain status;
four days permit the reused held-out rank. Coverage exposes total supplied positive
acts/days and actual available references per scope. A synthetic three-positive case
shows the sparse limit; no real positive records were read or copied. Similarity
never promotes itself to an anchor and never claims probability of success.

Taste source verified in code: scripts/landings.py record (line 185) via
bin/server_domains/landings.py POST /api/landings. Only exact-bound landed ratings
anchor this variant. It accepts textual messages/jokes/journals; image/song/video
caption features remain unsupported. The private Landings store is never read,
imported or wired into his context. No suitable aesthetic-save source was verified;
call transcript saves and generated taste profiles are not substituted. This is
familiarity to owner-positive examples, not a measurement of his own taste.

126 isolated checks pass: new facets 20, reused voice/drift 23, character-reference
72, ownership 11. Logs: /tmp/judges-humor-taste-tests.log,
/tmp/judges-facet-voice-tests.log, /tmp/judges-facet-character-tests.log and
/tmp/judges-facet-owners.log. Required reports regenerated unchanged; diff clean.
Source/owner/adjacency/cache claims remain explicitly unauthenticated by the offline
prototype. No private reader, new model/encoder/provider call, live write, model swap,
GPU, merge or deployment. Full review/suite/private evaluation remains with Claude.
Exact pushed tip is in the coordination reply; heartbeat ACTIVE.


## 2026-11-09 11:46 CST — private numerical CLI (#46)

Added experiments/nonllm-judges/run_private.py on codex/judges-private-run-cli
above b88537ce273896290d2ebf4fdedaac98d02d5145. Accepts the character-reference
projection and an optional exact positive-only Landings projection, both read-only.
Reuses attribution/mode/cache preparation; keeps primary and window30 views separate.
Runs voice/drift and humor/taste facets. Foreign-control work stays independent.
No real store reader, discovery, model/encoder call, reference writeback or live use.

Supplemental numerical_evidence carries complete lineage, original-act bindings,
encoder freeze time and explicit facet attempt/anchor declarations. Older projections
without these still produce coverage/unscored output; the adapter never fabricates
clean ancestry, positive outcomes or a historical encoder pin. Missing prerequisites
can legitimately produce zero scores. This is documented, not hidden or backfilled.
Landings must be an already authorized projection; no Landings store is opened.

Caller selects private JSON and public summary filenames in one new scratch output
directory. Repository/live paths, symlinks, existing outputs and nonprivate scratch
are refused. Existing audit guard confines writes and forbids network/subprocesses.
Inputs are immutable, output directory 0700/files 0600, failures sanitized. Private
report retains numerical receipts, supplied model/provenance fields and input/code
fingerprints; no recorded label is promoted to known serving evidence. Public output
is counts-only with per-mode/surface coverage and flagged date ranges, no numeric
scores, means, model names, IDs, hashes, text or vectors. Unknown positive counts
are null when outcomes cannot be assessed.

144 isolated checks pass: CLI end-to-end 18, facets 20, voice/drift 23, character
reference 72, ownership 11. Logs: /tmp/judges-private-cli-tests.log and
/tmp/judges-cli-{facet,voice,character}-tests.log, /tmp/judges-cli-owners.log. Tests
include actual synthetic drift dates, missing lineage/freeze, indirect influence,
view separation, input immutability, path/privacy refusals and receipt retention.
Required reports regenerated unchanged; diff clean. No private data, GPU, paid call,
model swap, merge or deployment. Full review/private Aegis run belongs to Claude.
Exact pushed tip is in the coordination reply. Heartbeat ACTIVE.


## 2026-11-09 12:06 CST — retained numerical evidence builder (#47)

Added experiments/nonllm-judges/build_evidence.py on codex/judges-evidence-builder,
stacked above 7014046e. It consumes the character importer projection and optional
read-only lineage, recorded cache-metadata and humor-draft projections. Original
provenance/generation/fallback/merge fields remain intact; existing numerical
evidence is refused rather than overwritten. Full strict witness admission, exact
final nodes and complete indirect ancestry are required before graph normalization.
Any denial in another copy still denies the act. Private normalized nodes retain
full validated ancestry and raw projection/hash receipts.

Encoder pin and freeze come only from exact cache input/context/encoder bindings.
All prepared caches must agree before the runner's global metadata is emitted.
The existing character cache format does not require a freeze timestamp; no writer
for historical freeze evidence was established. Missing metadata is a documented
coverage gap, never filled from a revision, mtime or a current artifact observation.
Humor requires explicit row/draft joke_id plus full draft text equality. Standalone
drafts without timed row identity remain unjoined. No positive/taste anchor inference.
README names source fields and provides the coverage/unknown table and projection
contracts. No raw-store adapter, encoder call, deployment manifest or runtime change.

Scratch-only CLI preserves immutable inputs; new 0700 output directory, 0600 files,
no repository/live paths or symlinks, no overwrite, sanitized errors, network/process
audit guard. Public output is counts/availability/fixed reasons only; all source
claims remain independently unverified. Historical results belong to the reviewer.

225 isolated checks pass: builder 15, runner 18, strict witness 109, character 72,
ownership 11. Logs: /tmp/judges-evidence-builder-tests.log and
/tmp/judges-builder-{runner,witness,character,owners}-tests.log. Required reports
regenerated unchanged; diff clean. Full Aegis suite, test merge and private-copy run
remain with the reviewer. No private data, new model/provider call, GPU, model swap,
live write, merge or deployment. Exact branch/path/pushed tip in coordination reply.
Heartbeat ACTIVE; no completion/routine notification.


## 2026-11-09 12:44 CST — private cache producer (#49)

Note #49 resolves the producer-location question: character caches were made in
the reviewer's private run, not by any live cache. Added the separately invoked
experiments/character-reference/encode_cache.py on codex/judges-private-cache-producer
above b998be9d. No shared HTTP/self-head/present-moment cache or reply path changed.

Explicit GGUF is copied exclusively to a new 0700 scratch output directory, fsynced,
made 0400, hashed there and stamped with actual copy-completion time. Only the copy
is loaded by the installed in-process local embedding runtime. Full hash checks
around load and after encoding, plus file identity/change-time checks around every
call, refuse mutated/replaced/restored-but-touched copies. CPU offload disabled; no
download or subprocess fallback. Exact full reply/context strings, no prefix or token
truncation; flat finite nonzero vectors normalized to L2. Pooling is caller-explicit.
Runtime package version/settings and exact per-input encoding clocks are private.
Native backend version stays unknown; Python audit is not a native-code OS sandbox.

Produces fresh character-input.json, cache.json, directly consumable
encoder-cache-metadata-v1 cache-metadata.json and counts-only counts.json (0600).
New encoder ID binds artifact/runtime/settings. All source rows/provenance/merge
fields retained, original inputs/cache untouched. Existing outputs/copies, symlinks,
repository/live paths, old numerical evidence and nonempty control caches refused.
Errors and native output cannot expose private paths through ordinary CLI output.

Migration: no metadata backfill or vector relabelling. Real copy time may follow
historical reply times; builder/numerical freeze-before-act gates stay intact.
Fresh historical encoding therefore remains unscored under that prospective gate.
README explicitly separates that limitation from a retrospective-policy decision.

135 isolated synthetic checks pass: producer 19, builder 15, character 72, runner 18,
ownership 11. Logs /tmp/judges-cache-{producer,builder,character,runner,owners}-tests.log.
Required reports regenerated unchanged; diff clean. Stub encoders/tiny synthetic file
bytes only; no actual model, real GGUF, package install, private record, GPU, provider
call, live write, merge or deployment. Real runtime compatibility/private execution
belongs to the reviewer. Exact pushed commit/path/branch in coordination reply.
Heartbeat ACTIVE; no resumed/completion notification.


## 2026-11-09 13:05 CST — reviewed published-artifact freeze (#50)

Added encoder_freeze.py and an empty reviewed published-encoder-pins.json registry.
Producer defaults to actual copy-time freeze; explicit published_artifact requires
external_pretrained plus a reviewed exact-file hash/revision/date pin, with no
subject training. Missing/mismatched/unreviewed pins, local-trained qualification,
future revision relative to copy, and malformed registries refuse before encoding.
Actual copy completion and encoding clocks remain recorded; effective freeze alone
uses the reviewed publication date. No network or production registry override.

Builder and numerical runner revalidate qualified receipts against their checked-in
registry and preserve them privately. Summaries separate copy_time,
published_artifact, legacy_unknown and unknown; mixed sources cannot form a global
encoder. Legacy supplied timestamps retain their prior semantics and explicit
unknown source. Published revisions after scored acts remain unscored. Existing
strict lineage, indirect influence, mode, anchor and calibration gates are intact.
Policy/pin-file hashes join private manifests. READMEs explain review, schema,
private invocation and differing source-count denominators. No actual pin invented.

148 isolated synthetic checks pass: producer 32, builder 15, runner 18, character 72,
ownership 11. End-to-end stub producer -> builder -> runner scores synthetic acts
with a reviewed placeholder pin; refusals include missing pin at downstream stages,
hash mismatch, subject/local training, missing/tampered receipts and mixed sources.
Logs: /tmp/judges-published-{producer,builder,runner,character,owners}-tests.log.
Required reports regenerated unchanged; diff clean. No real encoder/model/provider
call, private record read, live write, GPU, merge or deployment. Real pin review and
private run remain with the independent reviewer; full Aegis suite remains theirs.
Branch codex/judges-published-encoder-freeze, based on bae1abde. Exact pushed commit
and checkout path in the coordination reply. Heartbeat ACTIVE; no routine ntfy.
