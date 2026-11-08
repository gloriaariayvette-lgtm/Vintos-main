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
