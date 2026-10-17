# Chemistry Lab completion diagnostics — 17 October 2026

Implemented from `claude/device-visuals-2026-10-13`, base
`f715dd607b1f9bcb7a4e5615f8670b809895b9f2`. A fresh origin fetch and a history
search across all fetched refs found no subsequent `finish_reason` or
`token_limit_reached` implementation in `scripts/chemistry_lab.py`.

The inspected installed Lab matched this branch's Lab source exactly. The running
proxy also matched the branch's proxy source. No historical diagnostic was rewritten;
this cannot recover the stopping condition for evidence `72f5b73e8d754476a446382e778ca1ce`.

## What changed

`_ask()` returns a string-compatible reply carrying its own bounded completion
metadata. Every parser evidence update keeps that metadata under `completion` in
the existing `<evidence_id>.events.json`, including strict success, escape repair,
truncation repair, and terminal failure. Replies parsed out of order and planner
retries retain their own metadata and evidence IDs.

The actual deployed route is
`http://127.0.0.1:8599/gemma-aegis-local/v1/chat/completions`. Its proxy invokes
LM Studio's native `/api/v1/chat` endpoint with reasoning off and storage disabled.
It previously manufactured `finish_reason="stop"` for every native response.
The adapter now preserves an actual `stats.stop_reason`, `stop_reason`, or
`finish_reason` when supplied, and records which field supplied it. Missing reasons
remain null through the OpenAI-compatible wrapper. Other provider routes retain
their existing behavior. A Lab receiving an older Aegis adapter's fabricated stop
without provenance also treats it as unknown.

| Field | Meaning |
| --- | --- |
| `finish_reason` | Actual provider value, null when absent or invalid; string capped at 256 characters. |
| `finish_reason_source` | Native field path on the Aegis route, null when absent. |
| `token_limit_reached` | True for `length` / `maxPredictedTokensReached`; false for recognized non-limit stops; null for missing or unfamiliar reasons. |
| `requested_max_tokens` | The original request's output budget. |
| `usage` | Available nonnegative integer prompt, completion and total token counts. |
| `token_budget_exhausted` | Whether a reported completion count reaches the requested budget; a separate observation, not proof of why generation stopped. |
| `id`, `model` | Available response ID and model, each capped at 256 characters. |

For missing native stopping metadata, the diagnostic can establish budget
exhaustion from counts while leaving the stopping condition unknown. It does not
claim that a complete JSON object means a normal stop or that malformed JSON means
truncation. LM Studio's documented native v1 response includes usage statistics but
does not promise a stopping-reason field; the OpenAI-compatible interface has a
different response envelope. References: [native chat](https://lmstudio.ai/docs/developer/rest/chat),
[OpenAI-compatible chat](https://lmstudio.ai/docs/developer/openai-compat/chat-completions),
[OpenAI-compatible response example](https://lmstudio.ai/docs/developer/openai-compat/tools).

Raw and repaired replies remain in private diagnostics (directory 0700, files
0600). General faults/errors retain opaque evidence IDs without response text or
storage-error text. No new evidence files were added. The existing 64 KiB per-file
limit, 200 ordinary files, 60 terminal files, 14-day terminal retention, group
eviction, eviction ledger, and partial-write pruning are unchanged.

Model URLs, model names, request parameters, thinking settings, parser variants,
planner retry limits, and scientific workflows are unchanged.

## Validation

All 11 affected suites passed with the repository's `run_isolated_test.py` OS
boundary on macOS and Aegis Linux. The final diagnostics suite passed 12 tests on
both hosts, including again from Aegis's installed source checkout. Together the
suites report 209 assertions/tests:

| Suite | Passed |
| --- | ---: |
| `test_lab_completion_diagnostics.py` | 12 |
| `test_lab_parser_diagnostics.py` | 7 |
| `test_lab_terminal_evidence.py` | 3 |
| `test_lab_json_parser.py` | 20 |
| `test_lab_json_boundary.py` | 17 |
| `test_lab_plan_contract.py` | 11 |
| `test_chemistry_lab.py` | 43 |
| `test_chemistry_tracing_prerequisites.py` | 24 |
| `test_shim_result_contract.py` | 50 |
| `test_shim_learned_cache.py` | 15 |
| `test_shim_mends_surrogates.py` | 7 |

Providers, sockets and subprocesses are stubbed in the new regression suite; all
workspace paths are repointed to temporary stores and isolation is asserted.
Coverage includes normal completion, length-limited complete and repaired JSON,
irreparable JSON, missing/null/unfamiliar metadata, native adapter-to-Lab metadata,
legacy adapter provenance, out-of-order replies, unchanged retry count, permissions,
size bounds, and diagnostic/fault-store failures. Existing suites verify pruning
and terminal retention. No new paid model calls or folding jobs were run.

## Installation and runtime verification

Installed on Aegis at **2026-10-17 15:30:48 UTC** after verifying each original file's
hash. The Lab was waiting for compute before the targeted restart. Only the Lab
and proxy services were restarted; Lab config, state, notebook and source receipts
were not rewritten by the installer. No branch switch or broad deployment was run
on Aegis; its source checkout was on `claude/vintos-avatar-ui-redesign-br5lt4` and
the affected files were byte-identical to the requested branch before this update.

| Component | Installed SHA-256 |
| --- | --- |
| `chemistry_lab.py` | `3f4b6b4a1cbbe4db91d9ee9d2d2b3ff067a0933d5f6b183f21254997411240e7` |
| `vintos_claude_shim.py` | `65c4c034355fb7089f707656183ba7dc5f8df3b364ab4f2b7b84847e2c70e8cf` |

The Lab source and workspace copy were updated. Both proxy copies were updated:
the service runs `/home/gloria/Vintos-main/bin/vintos_claude_shim.py`, while the
workspace's script symlink resolves to `/home/gloria/Vintos/vintos_claude_shim.py`.
The new regression suite was installed in the source checkout too. Both modules
already belong to the existing deployment manifest.

Restart verification: Lab PID `1633016` → `1642143`; proxy PID `412` → `1642141`.
Both services reported active and the proxy's `/health` returned `ok: true`.
The Lab resumed ordinary source work after restart.

Original files and a hash/PID receipt are retained privately at
`/home/gloria/.vintos/deploy/lab-completion-diagnostics-20261017/` (`receipt.json`
maps each target to its backup). No automatic GitHub push was performed.

**Remaining runtime evidence:** at the initial post-install check, ordinary work
had not yet produced a new parser record. A one-token local-only smoke was deferred
by the existing background compute-admission gate; no model request was sent.
Passing fixtures and a healthy restarted service establish source/installation
correctness, not a fresh observed provider stop condition.

No installation remains. To verify the first ordinary post-install parser record
without printing raw replies, run this from a host with authorized SSH access:

```sh
ssh gloria@aegis 'python3 -' <<'PY'
import json, pathlib
home = pathlib.Path.home()
receipt = json.loads((home / '.vintos/deploy/lab-completion-diagnostics-20261017/receipt.json').read_text())
root = home / '.vintos/workspace/memory/chemistry-lab/diagnostics'
for path in sorted(root.glob('*.events.json'), key=lambda p: p.stat().st_mtime, reverse=True):
    if path.stat().st_mtime < receipt['installed_at']:
        continue
    row = json.loads(path.read_text())
    if 'completion' in row:
        print(json.dumps({k: row[k] for k in ('evidence_id', 'events', 'terminal', 'completion')}, indent=2))
        break
else:
    print('No post-install completion evidence yet')
PY
```

The remote installed-source regression command is:

```sh
ssh gloria@aegis 'cd ~/Vintos-main && python3 -B scripts/run_isolated_test.py broker/tests/test_lab_completion_diagnostics.py'
```
