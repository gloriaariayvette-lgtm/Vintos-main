# Forge → Atelier → dedicated USD wallet: local prototype

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

## Integration boundary

The durable local artifact store models the Atelier side, but it is **not mounted
into the existing broker**. The broker's current HOUSE policy trusts loopback;
it is not an adequate authorization boundary for a money/cancellation controller.
Do not bolt owner-only routes onto it without implementing authenticated ownership.

Next integration must also preserve sealed storage, artifact lineage, reveal/LOOK
rules and visit authority. It needs an idempotent broker import, the model planner
and evaluator with their bounded execution authority, a dedicated USD payer,
recovery/reconciliation commands, notification dispatcher, and an Atelier control
and wallet UI. No daemon, timer or deployment manifest entry is included yet.

Vintos choosing income-producing work remains his decision. This code does not pick
his job, post marketplace listings, contact customers, or claim that a loop earns money.
The canonical remaining-work entry is in `docs/open-work.md`.
