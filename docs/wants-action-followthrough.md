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
