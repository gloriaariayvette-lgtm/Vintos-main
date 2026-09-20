# Forge / Atelier experiment history and parked financial prototypes

The maintained non-financial report loop now lives in `scripts/forge_loop*.py`.
See [current implementation and commissioning guide](../../docs/forge-lab-local.md).
`controller.py` is a compatibility import used by these fixture demonstrations.
The historical prototype description below is not the current integration status.

20 September 2026. Local branch `codex/forge-atelier-wallet-local`, based on
`f756972`. No Aegis connection, deployment, account opening, credentials, payments,
provider model calls, or live notifications. Separate worktree preserves the other
active task's checkout. This is executable local groundwork, **not a commissioned
live loop or a real wallet**.

## What works locally

`Controller` owns a durable SQLite project/cycle/artifact/event store. All writes
are transactions; concurrent workers cannot claim the same project. The worker
feeds the last accepted artifact and evaluation into the next cycle without a
schedule or per-cycle approval. Completion is an explicit evaluator decision.
The project-level mandate names allowed capabilities and a total USD-cent ceiling;
a request beyond it holds for authorization. Existing Forge installation and
invocation permissions are not changed.

`ForgeSandboxBuilder` reuses the actual Forge generator, reviewer parser and
OS-contained verification. It requires explicitly supplied model adapters; it
never loads the household provider defaults. Review or test refusal becomes retained
feedback for the next cycle. Infrastructure exceptions hold for reconciliation.
Nothing is installed into the house. The demo uses fixture models and real OS tests.

Cancellation uses a separate random project-scoped capability. POST cancels;
GET does nothing. It cannot authorize spending or read work. Cancellation while a
cycle runs preserves the result and prevents another cycle. It cannot undo a
provider request already sent. Restart does not reclaim an uncertain in-flight
cycle. Manual recovery tooling is still needed; no timeout silently replays a charge.

Private-in-progress projects require an explicit expiry (currently at most 31 days).
That maximum is a **local design choice, not a rule inferred from the handoff**.
Expiry is evaluated on each controller operation. Private notifications are
suppressed, with the cancel receipt available from creation regardless of privacy.
Reveal, owner audit, cancellation, abandonment, or expiry ends privacy. Audit is
an explicit authenticated operation and keeps every artifact. Ordinary owner status
is content-free. Privacy is an application boundary, not protection against the
machine administrator reading the database.

Ntfy payloads have View and HTTP POST Cancel actions, completion priority 3 and
authorization priority 4. No owner credential appears in a payload. The dedicated
cancel capability is necessarily entrusted to the notification service/device.
A failed/unconfirmed send remains pending; a crash after delivery can duplicate a
notification. No live publisher or subscription is configured. `ControlWSGI` is a
mountable authenticated status/cancel surface, tested without opening a socket.
The View URL currently returns authenticated JSON status, not an artifact UI.

The format follows [ntfy's official action-button documentation](https://docs.ntfy.sh/publish/#action-buttons).
Device action support and one-tap cancellation still need real-device acceptance.

## The real wallet decision

Gloria chose a **separate USD account/payment wallet**. `UnconnectedUSDWallet`
reports no account and no balance. The local reservations and spending ceiling are
control records, not money. Paid execution is explicitly refused even if an injected
adapter supplies a balance: account provisioning, enforceable payment reservations,
provider receipts/reconciliation and a dedicated funded payer are not implemented.
There is no fallback to Gloria's budget. No stock/trading capability is introduced.

A real financial institution/payment provider must provision the dedicated account.
Provider selection, onboarding, authorized account holder, incoming-payment method,
withdrawal/spend authority and secure credentials remain to be established. This
prototype creates neither account nor keys and asserts no income.

## Run locally

Use Python 3.12. These commands create temporary test stores only:

```sh
python3 experiments/forge-loop/test_controller.py
python3 experiments/forge-loop/demo.py
```

The demo needs the existing Forge OS sandbox (sandbox-exec on macOS or bubblewrap
on Linux). Its three fixture-generated artifacts are actually tested, then the
throwaway Atelier is removed. No paid generation or live review is implied.

See `test-result.txt` and `demo-result.json` for recorded checks. Production suites
were not rerun for this isolated prototype; existing deployed code is unchanged.

## Current integration boundary

The maintained loop has an authenticated owner UI and separate Lab-intake authority,
a worker/service entry point, recovery tooling, notification dispatch, and idempotent
projection into new sealed Atelier projects. Existing broker writes cannot bypass
loop ownership. This experiment's `ControlWSGI` remains a minimal fixture surface;
the runtime serves the actual control page. Live credentials, service deployment,
resource admission and device acceptance remain uncommissioned. Paid capability
building and wallet/Taskmarket work remain separate and unavailable here.

## Taskmarket / Gemma work-session extension

`taskmarket.py` implements read-only discovery/detail requests and admission for
local trials. It keeps micro-USDC separate from USD cents. Gemma's recommendation
must be accompanied by a task-bound fresh probe, matching runtime fingerprint,
available tools, an explicit acceptance check, a cost estimate and deadline margin.
No actual capability is pre-certified. Marketplace text and command suggestions
are untrusted data, never shell commands or authority. Initially only public,
zero-cost, no-stake bounty work is admitted locally; competitions do not guarantee
payment. This is a conservative pilot choice, not Taskmarket's full feature set.

`work_session.py` wraps a 1–3-task / at-most-30-minute pilot with a durable Lab
restore obligation written before pausing. Its adapter must acknowledge a quiescent
checkpoint owned by that session. It restores after cancellation and exceptions;
a restore failure is retained for explicit restart recovery. It must preserve a
separate operator OFF. Worker adapters must enforce the supplied absolute deadline;
this Python harness alone cannot preempt a hung callback. It executes local work
only, never claims, signs or submits. A Lab adapter is not yet connected.

The local Chemistry Lab source already checks a cooperative stop flag between
bounded turns. It has no pause-owner/restoration contract yet. Simply toggling OFF
then ON would risk overriding an independent manual stop or overlapping an active
turn. No live Lab was stopped, and no Gemma model was loaded/unloaded for these tests.

Ntfy events cover pause, local work completion, session completion/cancellation,
failure, successful restoration and failed restoration. Events persist before send;
unconfirmed sends remain pending. `ntfy_transport.py` provides an explicit-topic,
authenticated HTTPS publisher. It is not configured or invoked against a real server.
Every work-session notification carries the session's scoped cancellation action;
the receiving endpoint still needs live mounting and device verification.

### Verified platform facts (20 September 2026)

- Production uses USDC on **Base, chain 8453**, with six-decimal integer amounts.
  [Network](https://docs.taskmarket.dev/reference/network)
- Search/view and submission are free; claims may require a deposit. Pitch/proof/bid
  operations cost 0.001 USDC. The documented default payout fee is **7.5%**; read
  each task's actual fee and settled award. [Fees](https://docs.taskmarket.dev/concepts/fees-payments)
- Work requires a signing identity. A Coinbase receiving address and the Taskmarket
  signing account need not be the same role. Withdrawals use a registered destination;
  do not infer it from a job. [Wallet](https://docs.taskmarket.dev/reference/withdrawal-address)
- Submission is not payment. Record the worker's actual settled award and transaction
  hash; do not credit the advertised reward or infer success from a submitted file.
  [Schema](https://docs.taskmarket.dev/reference/task-schema)
- The quoted “192 tasks / perfect success” claim was not independently established.
  Neither marketplace liquidity nor repeatable profit has been demonstrated here.
- USDC does not remove income/disposal recordkeeping. Preserve units, USD values at
  receipt/disposal, dates, fees and transaction receipts. Coinbase reporting is not a
  complete substitute for own records. [IRS](https://www.irs.gov/filing/digital-assets)

Needed from Gloria: Coinbase product name, public receiving address and selected
network. No seed phrase, private key, recovery code, password or API secret in chat.
Before any funded pilot, establish the signer, explicit spend/stake limits and
review any required marketplace terms. Nothing here auto-accepts terms or moves funds.
