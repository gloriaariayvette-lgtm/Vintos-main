# Wants from reading and journaling: action follow-through

8 November 2026. Review branch `codex/wants-action-followthrough`, based on
`6e452ae6`. Source implementation and isolated synthetic evidence; not deployed.
Claude Code reviews and runs the full isolated Aegis broker suite; Gloria deploys.

## Trace and verified gap

| Stage | Existing code | Finding / change |
|---|---|---|
| Email reading | `want_email.read_mail`, `email_commitments` | Reading, attachments, sent-letter commitments and the room already exist. Keep them; attach exact source receipts to newly formed email wants. |
| Journal admission | both `idle-journal.sh` copies | The old explicit extractor admitted only 10–120 characters after the opening words. A literal operational sentence missed it; the blanket `bridge` metaphor filter also rejected musical usage. Keep complete bounded sentences and explicit operational wording instead of rewriting them into an inferred desire. |
| Scheduling | journal seed, wants router | The journal already sets `timer_bypass=True`. Preserve it; recognize specific older journal rows without that flag too. Other wants keep their incubation. |
| Planning | `emoclaw_utils.generate_steps` / `fit_steps_to_hands` | Non-Forge sources lost unavailable actions from their plans. Keep those obligations. Existing Forge source authorization remains unchanged. |
| Agent action | `dot_channel`, `room_work`, `want_board` | Join exact wants to this existing room, not another agent service. An agent request is not fulfillment, an elapsed timer is not progress, and agent work is not silently aged away. |
| Purchases | room's Muse / `BUY` / `gloria_asks` | Reuse Muse and the existing owner decision. No spending authority is added. Downloads, accounts and changes go through the agent's existing permissions; deployment stays with Gloria. |
| Return | `want_artifact_guard`, `want_completion`, `deliver` | Bind a result to the requested goal, verify files, upload them to the existing results channel, send its link through the existing ntfy receipt path, then use the existing completion door. |
| Awareness | full/compact subconscious context, room context, mail reading and agent-letter drafting | Retain factual completion receipts. Agent letters see the result instead of treating it as a future promise. Exact linked email commitments close; related topics are never bulk-closed. The generic identity prompt for external email is unchanged. |

Read-only task-specific live inspection found: the missed literal want was 141
characters; eight related email commitments were still open; no matching work
was open in the room. One related active want had a two-step music/reflection
plan, neither step being the requested transcription/analysis. A related archived
want also did not literally ask for that analysis: its completion is **not**
evidence of falsely completing this exact task. No private text or source IDs
are reproduced here.

The inspected system interpreter did not expose the requested transcriber as a
Python module. That bounded check does not establish that no host, environment
or binary has it. No download, installation, paid call, live write or real
music analysis was performed during this repair.

## Runtime contract

`want_agent.py` stores a request on its existing source want, with a deterministic
request ID and hash of the exact goal. Specific operational journal/email wants
and concrete unavailable actions reach dot through the room's existing transport.
A purchase request addresses Muse; other setup work addresses dot. A signed
reviewer reply may finish work only when the room authenticates its owner account.
Unknown signatures, unrelated agents, wrong threads and changed goals cannot
complete it. The dedicated working route is described in the review 14 section below.

The request carries source references, previous realized step results, the
literal task and its acceptance requirements. The room retains its existing
capacity and conversation rules. Only the source-bound lane is exempt from the
global room pause; its dedicated stop switch and task-specific pauses still apply. One new want is handed over per
pass; threads remain watched beyond the ordinary recent-thread window. Existing
work with an exactly matching goal is reused. Agent work may be explicitly paused
or dropped, but a prose `WORK DONE` cannot replace its deliverable receipt.

The agent writes only its own result bundle, then returns its marker in the
bound room thread:

```sh
python3 scripts/want_agent.py result WA-<request-id> \
  --summary "What was actually made" \
  --acceptance "How the literal task was checked, and what remains uncertain" \
  --artifact memory/want-artifacts/requests/WA-<request-id>/example-score.txt \
  --artifact memory/want-artifacts/requests/WA-<request-id>/example-audio.wav
```

`SPARK_WORKSPACE` selects scratch for development. The CLI refuses unknown
requests, private non-artifact paths, traversal, symlinks, missing/empty files,
more than eight files and over-budget outputs. The manifest binds actual file
hashes to the goal. Its result marker alone does nothing until it arrives from
the trusted agent in the exact request thread. The mechanical checks prove
file existence and identity; the agent's acceptance statement is an attestation,
not an automatic proof of transcription or scientific accuracy.

Files are uploaded through the existing Slack sharing adapter, to the configured
results channel (the existing work channel if no separate results channel is
configured). Only after upload acknowledgment and a permalink does ntfy receive
the completed deliverable link. The source want retains publication progress,
notification receipts and result. A failed notification retries without uploading
again; failed file uploads retain per-file progress. Stable Slack client message
IDs aid transport retry deduplication, but no distributed exactly-once guarantee
is claimed for a process crash between a remote success and its local receipt.

The existing `deliver` artifact key prevents routine duplicate notifications.
`sent` means transport accepted it, not that Gloria opened it. Completion still
passes the artifact guard and existing ending door. Archive reconciliation can
finish exact linked commitment/room closure after an interrupted ending.

Completed receipts are supplied to his ordinary context and agent correspondence.
This is factual recall, not a promise that a generative model can never repeat a
sentence. Only explicit commitment IDs or identical task text establish closure;
shared subjects, tools or one common email do not establish that two promises
were the same. Legacy commitments without that identity remain unresolved until
their actual result is linked.

## Bounded local work

`local_analysis.py` adds a small execution lane using the existing OS sandbox.
The planner can use named copies of artifacts, installed Python dependencies and
declared JSON/CSV/WAV/text outputs. A child gets no network, credentials or live
stores, and has a 45-second wall budget. Inputs are capped at 32 MiB and outputs
at 16 MiB. Exact success is reused only while output hashes still match. Failed
or interrupted exact jobs are not blindly rerun. The router retains the failure
and hands the task to the room for dependency/setup help; it never substitutes
another journal entry. This is not a general model installer or a transcriber.

A real synthetic sandbox run produced an audio excerpt, score and bar table.
Those are fixture outputs, not results on his music. No existing model, live
feed, agent service or paid provider was invoked or replaced.

## Validation and acceptance still owed

The new suites cover causal source identity, long literal wants, the existing
timer bypass, exact goal/thread joins, forged/unbound result rejection, real
sandbox execution, file/path isolation, wrong output shapes, changed results,
partial failure/restart, durable room/commitment closure, and receipt recall in
email and context. Every transport/model call in tests is a stub, every writer
uses scratch, and suites run behind `run_isolated_test.py`.

863 checks passed across 24 affected suites on macOS, including 41 new checks.
[Aggregate validation](wants-action-validation.json) records the suite counts. The full Aegis suite and
review are still required before integration. Live acceptance after Gloria's
deploy: one genuine journal task should reach its agent, produce the named files,
notify the deliverable, close the same want/linked commitment and appear as
completed in his next agent-letter context. The music example has not yet been
executed by this branch. No live want was backfilled or rewritten during review.


## 8 November follow-up: persistent working conversation and explicit route

`codex/wants-working-thread` is stacked on ad88092f, preserving that review tip.
A concrete want now gets one private `working-thread.json` beside its existing
request artifacts. It retains the exact goal/source references, initial identity
context, prior steps, all ingested authenticated agent replies, working decisions,
transport acknowledgements and final delivery. A restart reloads this record.
Nothing silently truncates or summarizes its history; a malformed/conflicting
record fails visibly instead of resetting it. The file is mode 0600 under a 0700
request directory. It contains private context and must never enter Git.

The dedicated lane explicitly requests `claude-sonnet-5-5` for initial planning
and agent request, subsequent replies, result review and completion wording.
It bypasses the generic room composer and its local rewrites. Request-local
capture records the response's actual model field when present; missing identity
or a subscription string stays unknown. Requested identity is never substituted
for served identity. Other model routes are unchanged. The capture's lineage and
delivery remain unknown for judge eligibility; this is not a clean witness.

Working decisions are cached by event. Polls without new messages/results make no
model call. The reviewed cost-control implementation below supersedes the earlier
per-pass-only bound and expiring call lease. A response-observed event is parsed
locally after restart; an interrupted call is held for reconciliation, not resent.
Context is retained in full, with explicit summary continuations instead of silent
truncation. No paid call was made for implementation or tests.

The room switch no longer stops this bound-want lane. Ordinary messages still
obey it. The exemption requires the current want's exact goal hash, an open RW
item and the stored Slack thread, plus an authenticated participant for replies.
A copied `[want:...]` label establishes nothing. Task-specific pauses/cancellation
remain effective. Bound messages are persisted and handled by this lane once,
not answered again by the rotating room composer. Existing room capacity and
other task execution/approval limits remain. The separate hold while Gloria is
actively chatting is unchanged; this is specifically the room-switch exemption.

Muse BUY and credential/owner questions reuse the existing owner-request doors,
including while room conversation is stopped. Requests retry from the saved
thread after an interruption. Results first pass exact file/hash checks, then
Vintos reviews the manifest and stated acceptance. A deficient result returns
for correction in the same thread; it is not a completed want. This review does
not listen to audio or independently run the analysis: the agent must provide
real acceptance evidence, and the model must not claim inspection it did not do.
Accepted completion wording goes through the existing file upload, delivery and
ending doors and remains in the working conversation and fulfilled-want record.

The three checked-in agent instruction files now describe the same exception and
read-only `want_agent.py binding REQUEST_ID --thread THREAD_TS` verification.
**External agent instructions are not installed by this code change.** Claude
must include their update in the review handoff; Gloria's deployment and agent
configuration are distinct acceptance steps. No settings, services or live
records were changed here. Full isolated Aegis suite and real-want acceptance
remain Claude/Gloria's steps; the original music task is still not executed.

Validation for this increment: **916 checks across 26 isolated affected suites**,
including direct paused-room, spoof-tag, task-pause, persistent-context, served
identity, correction/delivery and owner-request restart cases. All model and
transport calls were stubs. The matrix is recorded separately in
`wants-working-thread-validation.json`; the original 863-check result is retained.


## Review 13 repair batch: source binding and result freshness

`codex/wants-review-repairs` rebases both wants commits onto 788439c9, preserving
the old review branches. Both additive open-work conflicts were resolved by
keeping the judges and wants sections. The obsolete comment-based incubation
test now checks pause ordering against the actual incubation assignment.

The agent lane now requires an operational journal/email want with an exact
goal digest, source reference and matching source-event receipt. Dream, curiosity,
room-derived and unmarked sources cannot request work, enter intake or reuse a
queued request/working-thread exemption. The stored row is checked again under
its update lock. All router fallback sites use the same predicate. No historical
source receipt is invented; these checks affect the new agent lane only.

Result files must be inside the exact request directory and have a modification
time at or after its creation, bounded by the current clock. Old and unrelated
shelf files are refused even with matching content hashes. Request control files
(including the private working thread) are never deliverables. Hash checks and
authenticated thread arrival still apply. These are filesystem provenance checks,
not proof that an agent performed an adequate scientific or musical analysis.

**Integration remains blocked:** context-limit continuation and owner notification,
per-want/global daily budgets, dedicated kill switch, subscription-only default
without paid fallback, and crash-repeat protection remain to be implemented. The
previous 916-check matrix records the earlier tip, not acceptance of these repairs.
No live stores, model calls, sends from tests, merge or deployment.

This repair batch passes **408 isolated checks** across six suites: agent
follow-through 37, room channel 320, thread doors 22, journal extraction 7,
artifact guard 11 and entry ownership 11. Negative fixtures cover dream, curiosity,
room-derived, absent/malformed/stale sources and existing queued work; positive
fixtures cover bound journal and email tasks. Result fixtures reject old timestamps,
foreign fresh shelves, future timestamps and private working-thread records.
All transports/models were stubs. Full Aegis validation remains Claude's step.


## Reviews 13 and 14: bounded attempts, authorized fallback and continuation

Implemented on `codex/wants-budget-continuation`, stacked on eab31339. This is a
review candidate; Claude's full isolated Aegis suite and Gloria's deployment are
still required. No live want or provider has been exercised.

### Working route and cost accounting

The dedicated lane calls `claude_sub.ask` directly for `claude-sonnet-5-5`, then
uses the existing `astra_call.call` (`gpt-6-astra`) only if that subscription call
fails or is unavailable, as Gloria chose in review 14. It never enters the paid
Anthropic API route. The same system/context strings reach the fallback; identity,
goal, source receipts and retained conversation do not restart on a lane switch.
Other callers' routes are unchanged.

The existing OpenAI reservation/release accounting and worker deadline are reused.
Its optional private observer packet takes served identity only from response
metadata. Subscription text does not expose served identity, so it stays unknown.
The generation capture separately records the actual selected lane. The normal
string-returning provider API remains compatible for existing callers. A malformed
working decision is retained for review, not automatically retried through another
paid call. The fallback spends credits; this is not a free path.

`memory/want-work-policy.json` can set these conservative defaults:

```json
{"per_want_calls": 8, "daily_calls": 16, "context_chars": 60000}
```

The per-want limit covers the entire request lifetime. The daily limit is global
to this lane on the America/Chicago calendar. Both count **each provider attempt**
(subscription and fallback separately), including failed/uncertain attempts. Zero
call limits stop new calls. Configurable upper bounds are 1000 calls and 250000
context characters; changing a limit is an owner/operator decision, never a model
action. The room's existing two-decisions-per-pass limit also remains; a decision
can consume two provider attempts. Only the fallback has an explicit 1800 output
token parameter; the subscription adapter does not expose that parameter.

Reservations are locked, private and fsynced in
`memory/want-work-control/calls.json`; malformed state is refused, never reset.
An intent is persisted before each call. The working thread records responses
before parsing/finishing. After a crash, recorded responses finish locally, while
an intent with no recorded response stays held for manual reconciliation; elapsed
time cannot license a repeat. Even a persistence failure at the observer boundary
cannot cause an automatic repeat. This deliberately trades availability for
protecting against uncertain repeat spending. It does not cancel a remote call
already underway or promise exactly-once remote billing/Slack delivery.

### Stop and explicit context continuation

The existence of `memory/want-work.stop` stops new lane calls, posts, uploads and
owner-request handling. Incoming authenticated agent messages are still retained.
Removing it permits work again within the same caps; it does not reset counters
or authorize an uncertain call. Ordinary room traffic retains its existing rules.

Context/cap/uncertain-response holds notify through the existing `deliver` door,
with a stable receipt and a persisted notice key. Failed notifications retry;
unchanged successful notices do not poll the owner. Provider retry-backoff polls
are quiet. Completed deliverables continue through the existing result notification.

For an over-budget thread, an authorized operator/agent supplies a bounded summary
file inside that request's private directory, preferably named
`.continuation-summary.txt`, and an exact retained event key:

```sh
python3 scripts/want_agent.py continue-context "$REQUEST_ID" \
  --summary-file "$SPARK_WORKSPACE/memory/want-artifacts/requests/$REQUEST_ID/.continuation-summary.txt" \
  --through-event "$EVENT_KEY"
```

The command makes no model call and sends nothing. It retains all original events
and earlier summaries, binds the summary to a hash of the covered prefix, and
uses the summary plus subsequent events in future prompts. Exact goal/source and
identity remain. It does not erase unanswered work, reset caps, release a task
pause or retry any response-observed/uncertain call. If identity/instruction alone
exceeds the limit, summarizing events cannot cure it; the owner must review the
explicit context budget. There is no automatic lossy reset.

Validation: 614 counted checks across 13 affected isolated suites, plus the
Slack-cost regression suite (which reports pass without a numeric total). The
new 17-test control suite covers atomic limits, both lanes, exact observed
identity, crash/observer failures, concurrent identical events, continuation CLI,
retained history and notification deduplication. The existing want suite now has
39 tests, including stop-switch message retention and actual room-boundary alerts.
See `wants-budget-validation.json`. Full independent Aegis review remains pending.


## Completion delivery follow-through

`codex/wants-completion-delivery`, stacked on 31ec539a, repairs two failures
reproduced through the actual delivery module with a synthetic HTTP transport.
The default completion adapter previously omitted the required authority callback,
so every completion notification was refused. It now supplies the existing task
acceptance: this pass accepted this exact result and summary, and the retained
publication still belongs to the unique current source-bound working thread.
The dedicated stop switch is checked again at dispatch, including when it appears
during upload. This adds no blanket permission for other notifications.

A successful notification followed by a failed local ending also exposed a
restart conflict: the delivery door's repeat metadata differed from the saved
working-thread event. Local ending retries now reuse the first persisted successful
receipt. Failed sends still retry through deliver without repeating file uploads;
no send is represented as evidence that the owner read it.

Five new integration fixtures cover the default adapter's successful send/local
ending retry, HTTP failure/retry, stop arriving during publication, a source
receipt changing before dispatch, and a result that the working review rejects.
All store paths and outbound transports are explicitly isolated. Three tests
failed against the parent; after the authority repair the ending retry reproduced
the second failure, then passed with stable receipt reuse.

Validation: 464 checks across seven isolated suites (follow-through 44, room 320,
working controls 17, artifact delivery 39, artifact guard 11, thread doors 22,
ownership 11). Full Aegis suite and independent review remain Claude's work.
No real want, provider, upload or notification was exercised by these tests;
external agent rules and production integration remain uninstalled.


## Exact result versions through publication and completion

`codex/wants-result-revisions`, stacked on c9545a6f, addresses two reproduced
revision errors: a changed result reused the previous uploaded files after a
failed notification, and a changed result reused the previous successful send
receipt while its local ending was pending.

Authenticated result admission now records a canonical manifest digest. A revised
result atomically retains the preceding manifest and publication/delivery stages
in private `result_revisions`, then begins its own stages. Request identity,
working conversation and spending caps do not reset. Duplicate arrivals of the
same result retain progress. Upload message IDs, notification receipt IDs and
working-thread delivery events include the result digest, so one version cannot
stand in for another. A newly revised deliverable may therefore produce its own
notification; retries of the same version still do not resend it.

Progress writes compare the expected result digest under the existing store
lock, refusing stale writes after a new result arrives. The delivery callback
also checks this version. Existing publication records without a matching version
are retained for reconciliation; they are never silently labelled as the current
result or erased by a new arrival. This is not a production migration, and no
live records were read or rewritten. The remote transport can still complete a
request before a local write fails; these guards do not promise exactly-once
remote uploads or atomicity across the remote service and the local ending door.

Five added fixtures cover both reproduced errors, retained partial upload history
and stale writers, duplicate arrivals, and unknown-version publication retention.
The working-thread assertion now checks a versioned delivery event. Validation:
469 checks in seven isolated suites (follow-through 49, room 320, controls 17,
artifact delivery 39, artifact guard 11, thread doors 22, ownership 11). All
provider/network calls were stubbed. Full Aegis validation and review remain
pending with Claude; nothing has been merged, deployed or installed.


## Bind the final ending to the delivered result

`codex/wants-completion-binding`, stacked on efe9bec5, checks the exact source want,
request and canonical result version inside `want_completion.complete`'s existing
current-wants lock. It applies to the dedicated `agent-work` fulfillment caller.
The current result must still have its matching publication stage and successful
delivery. Missing/ambiguous identity, a late revision, missing version evidence or
changed manifest returns a refusal before archive, relief or plan reopening.
Other ending callers retain their existing behavior.

The new ten-test suite invokes the actual fulfillment/archive function with a
throwaway HOME and workspace, stubbed emotion/worker/plan side effects, and a
redirected worker log. Six initial fixtures failed on the parent. The positive
case archives the exact version through the existing path. A concurrent writer
cannot enter between comparison and archival; it proceeds afterward without its
unrelated update being overwritten. No test reached a live store or service.

Validation: 523 checks across nine isolated suites: completion binding 10,
follow-through 49, room 320, artifact guard 11, thread doors 22, ownership 11,
existing endings 50, moves-on 26, policy decisions 24. The moves-on suite first
hit an existing nested-f-string quote syntax error on the default Python 3.9;
the installed Python 3.12 lacked requests. A one-line quoting-only compatibility
fix in `bin/wants-ambitions-log.py` lets the existing suite pass on Python 3.9
without installation or output changes. Both failed attempts are recorded here;
all final listed checks pass. Generated metadata was refreshed.

This is local synthetic acceptance only. Claude owns the independent full Aegis
suite/review. Production services, feeds, installed instructions and live wants
remain untouched; no merge or deploy is authorized by these checks.


## End-to-end local acceptance without replacement completion callbacks

`codex/wants-end-to-end-acceptance`, stacked on 36c886f6, changes tests and
documentation only. Three integrated fixtures now enter through the actual room
adapter, use the default deliver and completion functions, and continue through
the actual fulfillment/archive function and completion-context readers. Only
providers, external transports, emotion/worker/plan effects and evidence side
channels are stubbed; every store and worker log is in temporary scratch.

The successful flow starts with a newly timestamped journal want, opens its bound
agent thread immediately, verifies/uploads a real synthetic file, receives a
synthetic HTTP success, archives the exact want, closes only its matching email
commitment, closes the room work, and exposes completion in full/compact context.
Repeating the same result causes no second upload, generation, notification or
fulfillment side effect. A failed HTTP send preserves the open want and promises;
retry uses the saved review/upload and completes after success. A simulated crash
after archival but before source cleanup is reconciled on the next pass without
repeating prior effects or closing an unrelated promise.

Validation for this test-only increment: 13 completion-binding/integration tests
and 11 ownership checks pass (24 checks). The parent's 523-check matrix remains
its own earlier result; it has not been relabelled as a new full run. These tests
establish local plumbing, not output quality or live provider/agent availability.
Full isolated Aegis validation, instruction installation, deployment and acceptance
of an actual want remain with the reviewer and owner. No new production code,
service change, real send, model call or private data was used.


## Review 15 repair and rebase

`codex/wants-review-15` rebases the complete wants stack, including final completion
binding and full synthetic acceptance, onto approved deploy base cb10d8b8. The
open-work conflict was resolved as a union. All prior pushed review tips remain
unchanged. The extracted local-analysis branch now imports its own source
predicate, so it does not depend on an import performed elsewhere in the router
loop. Its 15 isolated tests pass, including the reviewer-reported failure.

Interrupted calls have an explicit operator recovery command:

```sh
python3 scripts/want_agent.py reconcile "$REQUEST_ID" --call "$CALL_ID" \
  --outcome observed --confirm-stopped \
  --evidence-file "$REQUEST_DIRECTORY/.reconciliation-evidence.txt" \
  --response-file "$REQUEST_DIRECTORY/.recovered-response.txt"
```

For a confirmed failed call, use `--outcome failed` and omit `--response-file`.
The operator must first stop the lane, ensure the worker is no longer running,
and leave `memory/want-work.stop` present. The stop file alone does not cancel an
in-flight request; `--confirm-stopped` is the operator's explicit attestation.
`CALL_ID` is the retained generation request_id, not a model name or task ID.
Inputs must be bounded nonlinked files inside the private request directory.
Only running/uncertain calls without an observed response are eligible. Conflicting
reconciliations are refused; the same action is idempotent. Prior state/evidence
is retained, including after a subsequent retry. Observed recovery finishes
locally and records unknown served identity rather than treating supplied text
as independently observed provider metadata. Failed recovery permits a later
attempt after the operator removes the stop, within the same consumed budgets.
The command sends nothing, calls no model, changes no policy and prints no
response or evidence. Agents must not use it to clear uncertainty themselves.

Result verification also checks recorded sha256 values in the existing artifact
ledgers, fulfilled wants, other current requests, prior revisions and other
request manifests. Freshly copying known bytes into a request directory cannot
pass. Metadata reads are bounded and linked/oversized history is refused.
Same-version retries remain valid. This only checks recorded identities: it does
not prove originality, scientific correctness or detect unrecorded old files or
modified copies. A revision fixture that previously changed only acceptance
prose now supplies changed synthetic output, as the stricter requirement demands.

Validation: **602 checks across 12 isolated suites** pass: local analysis 15,
working controls 20, follow-through 51, completion integration 13, room 320,
artifact guard 11, thread doors 22, ownership 11, artifact delivery 39, endings 50,
moves-on 26 and policy decisions 24. Recovery fixtures verify unchanged consumed
limits, preserved history, local-only observed completion, refusal to reopen a
completed call and private CLI output. Freshness fixtures cover shelf copies,
earlier request output and prior revisions. No private inputs, model calls,
real sends, installs, merge or deploy. Independent full Aegis review remains open.


## 8 November — durable call inputs and honest recovery provenance

The next stacked branch, `codex/wants-call-input-receipts`, preserves the review-15
tip. Each new generation now retains its exact system and user arguments in its
existing private working-thread record before invoking the writer. Final capture
hashes those retained inputs and links adapter observations to that invocation;
it never rebuilds them from context that arrived after the call. This is a
writer-argument receipt, not a complete wire retry ledger or proof of upstream
provenance. Input nodes and delivery remain unknown/incomplete. Private prompt
snapshots stay in the private store; capture nodes contain hashes, not prompts.
Old response records without retained inputs remain unbound, without guessing.

An operator-recovered response is explicitly marked operator_recovery and keeps
both lane and served identity unknown. The attempted lane is preserved in prior
state but cannot attest the origin of supplied response text. Its capture keeps
the original request if available, without linking the supplied answer as an
independently observed result of that invocation. This also handles previously
reconciled records. Budgets and completion/retry behavior are unchanged.

Validation: **125 checks across five isolated suites** pass: working controls 23,
follow-through 51, completion integration 13, capture 27 and ownership 11. Three
new fixtures prove pre-call persistence, recovery after a local crash with changed
context and no repeated call, legacy unknown inputs, and operator-origin handling.
Two initial test assertions expected a null request_id where the receipt contract
omits unknown optional fields; corrected to test absence or null. No production
behavior was altered to satisfy those assertions. Reports regenerated. Synthetic
inputs and stubbed effects only; no live reads/writes, model calls, merge or deploy.
Independent full Aegis validation remains with the reviewer.


## 8 November — new blocked calls remain visible

`codex/wants-blocked-call-notices` fixes a source-level notification gap: the old
reason-plus-continuation key could suppress a later interrupted call after the
first had been reconciled. The room adapter now supplies the exact phase/trigger;
interrupted/response-review notices use that generation's retained call ID.
Repeated polls or a context-summary edit do not re-alert the same unresolved call.
A later call has its own receipt and includes its call ID for operator review.
Failed delivery retries with the same identity; provider backoff remains silent.
Context-limit notices hash the whole continuation, so a revised summary at the
same boundary can receive a fresh notice if it still exceeds the limit.

Validation: **421 checks in five isolated suites** pass: controls 26, room 320,
follow-through 51, completion integration 13, ownership 11. Three synthetic
fixtures cover a second interruption after explicit reconciliation, same-call
poll/summary deduplication, revised-summary limits, retry identity and silent
backoff. Existing capture/model routes, budgets, feeds and completion logic are
unchanged. This is not evidence that a live notification was missed; no private
records or live services were inspected. Full Aegis review remains independent.


## Review 16 — filesystem timestamp granularity

Claude's Aegis measurements found file mtimes as much as 4.2 ms before a request
clock read, even when the file was written afterward. The strict lower bound
rejected fresh results, reproducibly in completion and intermittently in
follow-through. This branch, `codex/wants-review-16-clock`, remains based on
cb10d8b8 and includes all subsequent review fixes without rewriting pushed tips.

The artifact window now permits `created_at - 2 <= mtime <= now + 1`. The lower
allowance is solely for filesystem clock granularity; request-directory binding,
known recorded-byte rejection, changed-byte checks, size and link checks remain.
This window cannot prove a file was authored after the request; the other checks
still cannot detect unrecorded old bytes. No wider provenance claim is made.
Positive artifact fixtures now set explicit mtimes with os.utime. Added regressions
cover 4.2 ms lag, both window limits, invalid request clocks and rejection of known
copied bytes even within the slack.

Before the production fix, the new lag/window tests failed (two failures and one
error), and the full two-suite coarse-clock simulation failed with 21 failures and
seven errors across 67 checks. After the fix: **130 normal isolated checks pass**
(follow-through 54, completion 13, controls 26, artifact guard 11, local analysis 15,
ownership 11). The new `test_want_coarse_clock.py` additionally runs all **67
follow-through/completion checks under simulated 10 ms mtime truncation**, passing.
These are repeated checks under a different clock condition, not 67 new scenarios.
The simulation changes only synthetic request artifact stat results, verifies its
scratch paths, and asserts actual lag was exercised. Existing stores/senders stay
repointed/stubbed. Generated reports and whitespace checked.

No real inputs, model calls, sends from tests, installs, merge or deploy. Claude's
independent full Linux rerun is still needed before integration; this local
simulation does not replace it. The previous Linux failures are recorded rather
than dismissed as environmental.
