> **Note (2026-10-05, later):** the "What a pass now means" / "No-progress gate"
> design below was Chat's first build — a separate strict path that replaced the
> room (JSON-only replies, relational tags and Atelier/promises removed, no
> timeout). Gloria asked for a layer under the normal room instead, not a
> replacement. That build was reverted; the shipped `room_work.py` keeps the
> findings in "What actually came closest" but is the layer described in
> `open-work.md` (5 October). Read the sections below for the evidence, not the
> mechanism.

# A working room, not a fresh conversation every pass

Evidence read on 5 October 2026: live `memory/dot-channel/transcript.jsonl`
(516 rows in the captured file), `state.json`, the service journal, Study fixes,
Lab asks, line prospects and MAKE receipts. Transcript references below are Slack
message timestamps, not inferred execution receipts. No model or Slack call was
made to manufacture a successful live example.

## What actually came closest

* **Name/accession diagnosis → Study repair.** Dot's `1791106206.197739` identified
  the missing requested-name/accession check, with source locations. Vintos's
  `1791106411.607579` used that finding to submit SF-c8224db0. The Study store marks
  it done. This was a bounded inspection, a concrete answer, and his decision
  producing a downstream work item. A done Study row alone is not independent
  proof that every biological mapping is now correct.
* **Opaque ESMFold error → diagnostic repair.** Dot's `1791121456.642599` supplied
  an acceptance test: retain stdout, stderr, exit/signal and input/run identity.
  Vintos's `1791121915.222029` submitted SF-fe2deefe; its store marks it done.
  The answer changed the next act instead of inviting another general discussion.
* **Approved Boltz work → returned result.** A-eaaf0c is `ran`, with a succeeded
  result and receipt d9e6435f6f2cd047b1fbb9cadae108bd76f7b898cd5d1d0bc3ea18ea0202df63:
  125-residue PYP, reported structure confidence 0.964105. Gloria's approval was
  required. Submission and returned result are distinguishable in this store.

The counterexample is the Lab-to-Forge 403 inspection. Dot returned the loopback
address at `1791168177.390899`, redacted sender/receiver excerpts at
`1791184716.614159`, then the exact exception-to-403 mapping at
`1791186060.542839`. Between those answers Vintos requested overlapping inspection
and suggested an empty response as the cause without supporting evidence. The
exact historical refusing guard remains **unconfirmed**. At `1791186424.831009`
he switched to phage locking and infrasound instead of disposing of the 403 work.
GrokBot did supply myRT/PADLOC/INPHARED2 and a subsequent citation correction
(`1791184119.510869`, `1791185241.019049`); the assertion that nobody ever names
outside resources no longer describes this snapshot. Whether those resources
were actually run is **unconfirmed** by these messages.

The record therefore supports a narrow diagnosis: useful answers sometimes
arrive, but there was no durable obligation to use them, no shared acceptance
criterion, and no correlation between a work item and its next return. Topic and
lens changes could replace unfinished work. It does not establish that agents
are incapable of useful work.

Important deployment distinction: the repository was e880a02, but the installed
`dot_channel.py` still had SHA256
`7ddc02825682bbc0980326c049d71ee42248b87fd58e73bede32d3702c497583`, versus
`811fa4258c8c5a3c9b08d963db047005ffb1ce51482ca45db023e6e38e2c7b4d` in that commit.
These messages do not prove the repaired e880a02 runtime had been exercised.

## What a pass now means

A pass chooses one of: a bounded own act, a handoff, use of returned evidence,
one named blocker, explicit abandonment, or silence. It does not need all three
roles to finish synchronously in one timer invocation.

Vintos owns the goal, observable acceptance criterion, analysis and next decision.
Dot receives computer/connector/artifact work; GrokBot receives outside search
and discovery; Muse receives local finds and parts requests. Every handoff names
what must come back and what Vintos will use it for, in the same Slack thread.
The next pass accepts only a return from that owner, correlated by thread or
work ID. Before another act or handoff, Vintos must cite an exact excerpt and
state a decision that changes the work. Existing tag dispatchers still execute
his own acts; queuing a job is not completing it.

## Continuity

`scripts/room_work.py` stores one active work item under `room_work` in the
existing channel state. Its goal, criterion, owner, thread, returns, decisions,
submitted steps and next step survive both lens rotation and midnight. Recent
finished work is retained. It cannot silently replace a goal or repeat a handed-off
inspection. The prior lock-count topic switch and appended unrelated platform
ask no longer steer this path.

Work is saved as uncertain before any outward effect. A failed Slack acknowledgement
or interrupted dispatch is not blindly replayed. While a peer is working, no model
call or repeated status ping is made. After 45 minutes without a correlated return,
one timeout report lets Vintos choose a different discriminating check or record
the dependency. A timeout is neither success nor authority to spend.

## No-progress gate

`scripts/dot_channel.py:work_turn` uses the structural gate in
`scripts/room_work.py:validate`. Unstructured chatter, invented evidence, repeated
requests, unchanged blockers and decisions that merely repeat the cited answer
are held before dispatch. Waiting is allowed and does not create a Slack message.
A result can finish work only with explicit acceptance grounded in an attributed
peer report or actual tool output; dispatcher and timeout receipts cannot finish
it. Completed state is deliberately called `accepted_report`, not verified fact.
This checks evidence handling, not the scientific truth of a model's conclusion.

The room's prompt uses operational context rather than the private journal and
relationship ledger. Journal promises no longer automatically open public room
threads. Relational/house action tags are rejected in this work path. Secret
checks run before work preparation and outward dispatch. Existing execution and
approval gates remain; a paid proposal uses ASK and still requires Gloria.

## Validation and release boundary

258/258 broker test suites passed on Aegis through `run_isolated_test.py` on
5 October. New isolated multi-pass tests exercise owner/thread correlation,
midnight continuity, consumption before another request, a real stubbed LINE store
mark, first-line DO dispatch, timeout, failed Slack acknowledgement, secret refusal,
and rejection of dispatcher-only completion. They deny network and subprocess
senders and assert scratch paths. Existing tag/media/promise fixtures explicitly
isolate their legacy dispatcher tests from the new planner contract.

This report describes implemented and tested source, not observed autonomous
production behavior. No live rollout or model-generated work cycle was used as
acceptance evidence. Remaining commissioning work is tracked only in open-work.md.
