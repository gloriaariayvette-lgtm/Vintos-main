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

## Installation and commissioning

The relay listens on Aegis's tailnet address, port 8792. The official native client
connects as Gloria. Its launcher uses the upstream `--safe-rendering` option for
WSLg. Both Build agents and Discussion include all four agents with bot membership.
Forums are enabled under Settings → Experiments → Forum Channels.

Gloria explicitly approved service accounts, corresponding provider credentials,
and local commissioning. `install-workers.py` installs `buzz-codex`, `buzz-claude`,
`buzz-grok` and `buzz-gemma` as separate system users/units with independent clones,
private workspaces, persistent CONTEXT.md and ledger.jsonl, and no owner identity
or live-house access. It does not start model work. Stop the four units before
upgrading installed binaries. Model IDs come from the checked-out `agents.json`;
Claude additionally receives the required `ANTHROPIC_MODEL=claude-fable-5-1`.

`register-native.py`, run as Gloria while Desktop is closed, backs up the native
store and links the existing identities to their matching definitions. No new
keypair is minted. The native registry and backup are mode 0600. Deploy receipts
are created by actual provider success, not inferred from relay presence.

Install `buzz-backend-aegis` executable at `~/.local/bin/buzz-backend-aegis`.
It implements Buzz's provider-v1 interface and validates the exact installed
identity, owner, model, prompt and runtime before starting its fixed systemd unit.
The accompanying polkit rule permits Gloria to start only those four units.
Configuration changes outside the reviewed installation are rejected; keys and
provider requests are never printed. Shutdown uses the upstream relay control.
The native client retains deployment receipts independently of Offline presence.

All four native launch controls were exercised successfully. All four units are
active/running, with zero automatic restarts. The older `buzz-gemma-local` user
service is disabled. It remains a credential-free fallback, not a second listener.

Local live commissioning passed: a bot-signed handoff was dropped by the actual
owner-signed gate before model work; an owner-approved task made Gemma create and
read `commissioning-approved-20260912.txt` containing `BUZZ_CHANNEL_OK`, update
private context and JSONL history, and post its result in the originating thread.
Actual namespace probes confirmed each own workspace is writable and the house,
owner key, house credentials and Windows home are inaccessible. No test suite
performs this commissioning; those were separately approved live actions.

Offline regression command: `python3 buzz-integration/test_native_provider.py`.
Seven checks pass on macOS and Linux using temporary stores and stubbed service
execution. The full Vintos suites also pass 119/119 directly and 119/119 isolated.

Paid inference and cross-model implementation handoffs remain untested. The three
paid listeners initialized no model sessions during commissioning. No additional
live forge run was performed.
