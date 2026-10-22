> AUTH-01 review update (22 October): source implementation and companion clients are prepared for approval, not deployed. Funnel stays on. Exact commands and rollback: [security-auth-rollout.md](security-auth-rollout.md). Complete public GET inventory: [security-public-get-routes.md](security-public-get-routes.md). Existing snapshot evidence below remains dated; source fixes do not imply live enforcement.

# Security validation and regression plan

22 October 2026. Tests must never contact providers, devices, Slack, ntfy or personal apps. Repoint **every** writable store and stub **every** sender; enforce a socket deny in the interpreter as defense in depth. Do not import live service entry points just to see what happens. No model is needed to validate a security gate.

## Completed validation

`broker/tests/test_security_alarm.py`: **29 tests passed** at the recorded run. It creates scratch HOME/workspace, denies sockets, and stubs provider transport, notification transport, system state and journal input. Cases cover:

- Failed and successful attempts counted before transport; no reservations/refunds/completions counted again.
- Exact hostname classification, local/free traffic unaffected, original arguments preserved, no prompt/key/header values logged.
- Sync/async transports, Request objects, concurrent appends, persistence failure holding the paid call.
- Pause/resume and every registered paid-provider host rejected while paused; curl compatibility without launching a real client.
- Rolling-minute boundaries, old/future/invalid rows, reasonable bursts, surge thresholds, baseline poisoning ceiling.
- Per-provider rolling-hour delivery suppression, independent providers, failed delivery retry, delayed-success hourly boundary and concurrent monitor invocation.
- Record-before-send through the existing organ-failure/fault signature path; real `deliver.py` authority and receipt gate exercised with only its HTTP transport stubbed.
- No-write/no-send dry run; unfamiliar SSH versus explicit allowlist; accepted-login parsing; authorized_keys/unit/cron changes; executable receipt mismatches; installation lock and normal deployment association; visible monitor probe failure.
- Manifest presence and byte-identical transport helper twins.

The initial focused compatibility run recorded in `audit/regression-results.json` passed **21/21 suites**, including the new suite, fault sweep, cache, compute admission, three shim suites, delivery, three music suites, device gate/budget, generated ownership, study-fix/twin, browser agent/JEv, deploy timer/branch/workbench guards and websearch quality. These are **suite totals**, not 21 individual assertions. After merging the updated deploy branch, the focused run passed **22/22 suites**, adding the inherited route inventory (**9/9 checks**). The current `audit/regression-results.json` records that post-merge run. Individual logs retain each suite's own check count. The full repository suite and owner-run Aegis scratch commissioning have **not** been run for this branch.

Run the new suite locally:

```sh
python3 broker/tests/test_security_alarm.py
```

Use an interpreter with the repository test dependencies. Existing compatibility suites must run in separate fresh interpreters with temporary HOME and `SPARK_WORKSPACE`; prepend the repository `scripts`/`bin` module paths and deny both `socket.socket.connect` and `socket.create_connection`. Pass only the suite name as `sys.argv` when using `runpy`, so `unittest` does not interpret the launcher path as a test selector. Existing suites' fake provider/sender checks remain enabled. No test expectation was weakened to accommodate this work.

## Reproducible read-only production evidence

Saved collectors in `audit/aegis/` inspect configuration/process metadata and safe routes. They contain no live key values. Review before reuse, because infrastructure paths and routes can change. SSH itself produces an authentication-log event; that is expected audit activity, not an incident.

- Inventory: `ss -H -lntu`, system/user active units/timers, current user cron schedule/script names; record root/firewall permission failures honestly.
- Runtime identity: compare actual process script paths, deploy receipt and hashes; source presence alone does not certify installation.
- Authentication: one GET to read-only desktop/robot status without a credential; record status and discard body. The audit compared wrong versus source-default credentials without printing them, confirming default acceptance. **Do not repeat use of the compromised default as a routine health check.**
- WebSocket: at most one credential-free upgrade and immediate close, recording only status. The audit got 101 on telemetry. Do not collect streamed personal data or flood connections.
- Do **not** call `/api/voice/token` as a production test: it can call paid providers, read private context and spawn a driver. Use an isolated handler fixture with transport/context/spawn sentinels instead.
- Metadata-only secret checks: permissions and credential-presence booleans; no environment/argv/key dump. Source/history secret scanning reports path/line/type only. Model/provider usage logs are summarized as counters/field names, not content.
- Dependency identity: report actual imported module file/version for the service interpreter plus distro revision; avoid stale duplicate distribution metadata.

## Required tests before deploying the alarm candidate

1. Reviewer verifies every changed egress site's original transport arguments, retry behavior, shim attribution, configured provider hosts and local-traffic exclusion. Cover Python aliases, shell heredocs and any externally installed scripts discovered through cron/services. Follow SDK internals and direct client realtime paths before claiming full infrastructure coverage.
2. Prove both recording and pause at each admitted egress adapter with fake transports. Assert each simulated real send generates one attempt, every explicit retry generates another, and nested adapters don't duplicate it. Add wire-level fake redirect/retry tests for transports that do that internally; the candidate's call-site counting alone is not that proof.
3. Reviewer confirms install plan puts helper modules beside **actual** server/shim/bin/script paths, includes service/timer and rollback, and regenerates `docs/untested.md`, `docs/entry-owners.md`, `docs/store-owners.md`.
4. Gloria approves an Aegis **scratch-only** commissioning action separately. Use a throwaway HOME/workspace and extracted branch scripts; use stub deliveries/provider transports, fake release receipts and journal fixtures. No live config/store/sender paths may be inherited. Verify bubblewrap/systemd behavior and resource footprint on its Linux environment without starting the production timer.
5. Run the full repository tests through the established isolation runner. Any failure requires reading its cause; do not label it environment-only by assumption. Confirm generation/ownership report checks after final edits.
6. After review and Gloria's deployment, inspect timer/unit state, installed hashes, real ordinary-usage ledger rows, observed rate versus provider usage and fault-loop recording. No test notification or artificial paid request. Mark delivery acceptance unverified until an ordinary genuine alarm provides a delivery receipt; never equate a sent receipt with human reception.

## AUTH-01 and existing voice-token guard

The deploy branch's `a6e28e9e` guard and `test_house_routes.py` are merged, not rewritten. Rerun the route inventory offline alongside alarm regressions after merging. Source tests are not evidence of production deployment. Default-secret rotation, telemetry/events token admission and private reads are one **unapplied-to-production** AUTH-01 source proposal with `vintos-app` index.html/outreach.js, `scripts/robot_bridge.py`, `bin/wants-router.py`, `bin/server_domains/humor_wants.py`, and `clients/mobile/`; validate all consumers and a joint rollback before production cutover approval.

## Further remediation tests and acceptance boundaries

| Control | Offline regression that must fail before the repair | Acceptance boundary |
|---|---|---|
| Default/auth migration | Missing/default/wrong/audience-mismatched token rejected before effects; enrolled client admitted | All legitimate clients migrated without exposing keys; default no longer accepted |
| Realtime mint gate | Anonymous request causes zero provider calls, private reads and spawns; expiry/scope/session limits work | No unauthorized mint; ordinary owner voice remains functional |
| HTTP flood/body bounds | Per-identity burst accepted; sustained excess rejected; chunked/declared oversize and malformed/slow inputs bounded | No production load test; Linux scratch process limits verified |
| WS auth/caps | Anonymous/expired/mismatched ticket rejected before accept; cap enforced; disconnect releases resources | Known device reconnect works; private data not visible anonymously |
| Tool/env scopes | Scratch unauthorized actor cannot read sentinel secret or invoke adapter; generated worker cannot modify production canary | No privilege escalation against real host; intended task still completes |
| Host monitoring | Synthetic journal, key/unit/cron/code changes, stale lock, unreadable source and missing heartbeat | Independent receiver sees loss/tamper without trusting Aegis |
| Backup/restore | Clean disconnected restore verifies state, permissions, artifact hashes and Atelier custody | Recorded recovery date/result/RPO/RTO; no sealed disclosure or production overwrite |
| Financial boundary | Review provider pages' enforced/soft semantics; confirm owner-selected limits and independent recipients | No deliberate consumption, purchases or automatic account changes |

The audit's production gate checks are bounded observations, not a complete endpoint authorization matrix. Expand that matrix in isolation and commission with ordinary-use evidence after approval.

## Prepared AUTH-01 offline regressions

`broker/tests/test_house_auth.py` has 20 tests: 16 standard-library admission/cutover tests and 4 in-process HTTP/WebSocket compatibility tests requiring the existing FastAPI/test-client dependencies. It uses scratch homes and a stubbed systemctl runner. No sockets or production stores are used. The optional HTTP dependency skip must be reported; this review also ran all 20 using test-only dependencies under `/tmp`.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 broker/tests/test_house_auth.py
node clients/mobile/tests/house_auth_client.test.cjs /path/to/vintos-app/src/runners/outreach.js
```

The companion repo has `vintos-app/tests/house-auth.cjs`, runnable directly from its app directory. Fetch, WebSocket, CapacitorKV and notifications are stubs; its tests never send. HTML inline scripts are syntax-checked separately. The standard isolated runner sets an explicit synthetic identity inside the child; production environment credentials are never test inputs.

30 pre-existing focused suites passed after merging the deploy branch; see `audit/regression-results.json`. The complete Aegis deployment suite and physical/native/background acceptance remain pending approval. No approved rollout is inferred from these offline results.
