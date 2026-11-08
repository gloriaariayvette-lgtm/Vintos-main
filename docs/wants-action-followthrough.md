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
complete it. No new model endpoint or model selection is introduced.

The request carries source references, previous realized step results, the
literal task and its acceptance requirements. The room retains its existing
capacity, global pause and conversation rules. One new want is handed over per
pass; threads remain watched beyond the ordinary recent-thread window. Existing
work with an exactly matching goal is reused. Agent work may be explicitly paused
or dropped, but a prose `WORK DONE` cannot replace its deliverable receipt.

The agent writes only its own result bundle, then returns its marker in the
bound room thread:

```sh
python3 scripts/want_agent.py result WA-<request-id> \
  --summary "What was actually made" \
  --acceptance "How the literal task was checked, and what remains uncertain" \
  --artifact memory/art/example-score.txt \
  --artifact memory/art/example-audio.wav
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
