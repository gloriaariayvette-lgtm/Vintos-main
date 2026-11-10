# Synthetic latent-feed stress runner

Coordination note #43 requested at least 50 randomized suite runs across time zones
and locales because the original intermittent failure traceback was not retained.
This runner preserves every existing assertion in `broker/tests/test_latent_feed.py`.
It launches a fresh Python worker per iteration, imports that suite, shuffles its
15 test methods with a recorded seed, and reapplies the selected `TZ` before each
fixture setup. It also sets an available locale. The existing suite still controls
its export timezone explicitly; the harness does not pretend that changing the
parent environment alone tests a suite that resets its own timezone.

Run only through the OS-isolated harness:

```sh
python3 scripts/run_isolated_test.py experiments/latent-feed-diagnostics/stress.py
```

Default seeds are 20261109 through 20261158. Time zones cycle UTC,
America/Chicago, Europe/London, Pacific/Auckland and Asia/Tokyo. Available locales
are selected from C, en_US.UTF-8, C.UTF-8 and en_GB.UTF-8; the summary records what
actually ran. All fixture stores and synthetic fit artifacts are temporary; the
existing suite stubs provider/sender calls and uses its deterministic fake encoder.
No real model or encoder inference, GPU job, live store, paid call or service test.
The small numerical synthetic fit already performed by the suite is unchanged.

On the first failure, the runner stops and prints the iteration, seed, time zone,
locale, exact randomized method order, full test name, assertion and traceback.
On success it reports 50 runs/750 checks. Passing runs do not identify or prove a
fix for the historical failure. Keep any saved logs outside the public repository.
The existing suite may emit unclosed-file ResourceWarnings; warnings are not silently
reclassified as assertion failures. No production code or existing assertion changes.

The current clock-gate inventory and scoped interval changes are documented in
[CLOCK.md](CLOCK.md). Backward-step regressions are in the ordinary isolated latent
and capture suites; passing them does not establish every historical flake cause.
