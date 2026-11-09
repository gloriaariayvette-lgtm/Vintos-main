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
