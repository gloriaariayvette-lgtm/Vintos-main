# Aegis Buzz integration

This uses the actual `block/buzz` relay, native client, SDK and ACP harness.
The legacy bench page is not its UI or execution authority.

## Source and verification

- Upstream source: `78618804ec86a014524ad7d1fb55928e8f5c3edf`.
- Native Linux client: official 0.5.23 package on Aegis.
- ACP patch: `owner-signed.patch`, original commit `242f8d6c6` in the separate
  Buzz checkout. Linux ACP library validation: 934 passed, zero failed, one
  pre-existing ignored adapter integration test. Apply with `git am`, activate
  `bin/activate-hermit`, then `cargo test -p buzz-acp --lib` and
  `cargo build -p buzz-acp`.
- `provision.rs` is an explicit installer built as a `buzz-acp` example against
  upstream SDK signing functions. It registered four profiles and owner-signed
  model cards; never run it from a test suite. It creates no model sessions.

## Approval and working context

`--respond-to owner-signed` admits only valid events signed directly by Gloria's
configured owner key. Sibling agents and relay workflows cannot inherit a yes.
Heartbeats and initial prompts are disabled. Each handoff is a proposal in the
shared stream; Gloria must directly address the receiving agent to approve it.
The owner's signature authenticates that instruction; a name in a ledger does not.
No kinds have been preapproved.

The upstream stream, forum, thread sessions and agent memories are the interface.
`agents.json` carries model IDs, roles, delegation instructions, and requirements
for each agent's private CONTEXT.md and append-only task ledger. Those instructions
are not claims that a task has already run or that an outcome has been verified.

## Installation state

The relay listens on Aegis's tailnet address, port 8792. The official native client
connects to it; the four profiles are queryable. Visual native-client verification
and an end-to-end approved channel task/handoff remain unfinished.

`run-local-gemma.py` is the credential-free fallback: bubblewrap mounts only the
published binaries, TLS roots and `~/.local/share/buzz-gemma`. The owner key and
live Vintos filesystem are absent. Its only provider is local LM Studio; it has
no paid credentials or fallback. A separate disposable ACP commissioning call
returned `BUZZ_LOCAL_OK`, 66 input and seven output tokens, normal end of turn.
The local listener runs as `buzz-gemma-local.service` and subscribes to both
channels. It awaits a directly approved task; no channel task has been run.

`install-workers.py` is a prepared **root installer, not yet executed**. Automatic
approval review requires explicit permission for the four service accounts and
scoped provider credentials. It makes independent repository copies, confines
writes to each worker's home, and excludes live Vintos and `agent-room`. Before
switching Gemma to this installation, stop the user-level `buzz-gemma-local` unit
so the same identity cannot have two active harnesses.

Gloria approved the four bot memberships in Build agents and Discussion, with
Claude corrected to Fable 5.1. All eight memberships were accepted by the relay.
Automatic approval review separately rejected the proposed live bot-message
commissioning probe; that probe has not been sent. Membership approval and task
approval are separate. No owner impersonation or automatic approval is permitted.

No paid inference commissioning or further live forge run has been performed.
