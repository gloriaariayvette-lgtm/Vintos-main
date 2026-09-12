# September 12 review and actual Buzz installation

## Outcome

The real `block/buzz` repository is cloned on this Mac and Aegis. Its official relay is running on Aegis with dedicated storage and authenticated membership. The official native desktop client is installed, launched, and has established connections to that relay. The `Build agents` stream and `Discussion` forum exist as actual Buzz channels, created with its signed CLI.

This is upstream Buzz, not `bench/server.py`. No `agent-room/` source, store, process or service was changed. No paid agent/model/forge execution was performed.

The four coding-agent runners, approval-preserving handoffs and per-agent configurations are **not yet commissioned**. Upstream installation is now real; that integration must not be represented as complete. The native client's process and connections were verified, but its rendered window was not visually verified through the bridge. A client-location preference question was sent; no response had arrived when this report was written.

## Review scope and findings

Reviewed Claude's designated-branch changes from `22a36ad` through `2c3d9b3`, including the committed handoff, runtime diffs, deployment changes, new bench implementation, and regression coverage. Ran every current suite with OS isolation, found a failure, fixed it, then ran all 118 directly and isolated.

### Critical: the bench does not enforce a human-only approval boundary

`bench/server.py:342` returns authenticated when the token file is absent. On Aegis the token file is actually absent, and the doctor reports an open bench. Anyone who can reach that endpoint can invoke the approval POST. The library's `approve(task_id, by=HERS)` also defaults to Gloria; the name check is a caller-controlled string, not identity proof. A scratch fixture reproduced an agent-created proposal becoming `approved_by: gloria` without any owner credential.

The append/replay code additionally has no complete state-transition transaction. Concurrent claims can both observe an approved task, and multi-ledger writes/handoff creation can partially commit. The handoff's claim that this gate is the part that already works is too strong. **Do not attach a worker to this authorization scheme.** No live approval was issued during review.

### High: budget releases can cancel unrelated reservations

`scripts/compute_admission.py:125–181` subtracts every released row without a reservation identifier, matching proof, or replay protection. Scratch reproduction: reserve one unit for A and one for B; release A once gives 1; replay A's release gives 0, erasing B's reservation. Clamping the aggregate at zero does not fix this. The new test exercises repeated releases but does not preserve unrelated spend. Refunds need identities tied to the original reservation and idempotent settlement. This remains unpatched.

### Medium: the new bench-page suite fails within the existing isolation boundary

Initial full result: **117/118**. `test_bench_page.py:54` bound an arbitrary socket instead of using the reserved fixture listener. It also spawned a second simultaneous listener and asked the copied isolated checkout for Git index metadata that the runner intentionally excludes.

Fixed in **852e6a7**, pushed to the designated branch:

- Use the OS-reserved test port and pass its descriptor into the server subprocess.
- Install the existing fixture adapter inside that subprocess; bind the fixture only to loopback.
- Serialize the two server lifetimes so they reuse the one permitted listener.
- Assert temporary ledger/token paths.
- Run the Git-index assertion in the real direct checkout; explicitly identify its absence in the isolated copy instead of claiming it was tested there.
- Add an optional `BENCH_HOST` binding override, preserving existing production behavior.
- Remove the source's false claim that the custom page is Buzz's layout.

No sandbox/network policy was weakened. Final results: **118/118 direct, 118/118 isolated**. The isolated bench-page suite has 83 applicable checks; the direct run also checks the real Git index.

### Other concrete gaps

- `env_file._unquote` fails a quoted value followed by a comment. Fixture input `"fixture-key" # comment` retains quote and comment text. Some callers still return a raw environment key before consulting the new parser, so the claimed single behavior is not universal.
- `device_patterns.note_refusals` uses one fixed temporary filename and `take_refusals` reads then deletes without a transaction. Concurrent readers/writers can lose feedback. The context text also says nothing fired and the user felt nothing based only on rejected directives; a mixed reply may contain other valid directives, and physical sensation is not measured by this record.
- The earlier nightly causality snapshot writer, graduation ordering and durable projection recovery remain open. Claude's new commits do not implement that missing work.
- The journal changes impose length-retention thresholds; preserving length is not proof that factual corrections were retained. Rejected shorter corrections deliberately keep the earlier text. This is a tradeoff to review, not an evidence guarantee.

### Repairs that are present

The import-twin synchronization and deployment expansion are real. The eight named module families retain the repaired code, and the new test enumerates existing Python and shell copies. Deployment now refuses conflicting sources for the same planned destination. This improves the earlier stale import-target problem; it does not certify every runtime path outside the plan or every other shared-store writer.

The device-menu freshness/name changes and env-reader consolidation have real implementations and passing fixtures, with the limitations above. The bench doctor currently succeeds on Aegis: process, port, health and diagnostics answer. The handoff's claim that it still dies is stale at this observation. That does not fix the missing product or the approval weakness.

## Actual Buzz installation

- Source: `https://github.com/block/buzz`
- Mac checkout: `buzz/` under this workspace.
- Aegis checkout: `/home/gloria/repos/buzz`, clean at `78618804ec86a014524ad7d1fb55928e8f5c3edf`.
- Relay image: `ghcr.io/block/buzz@sha256:1101854b8e80a0869cf644bea886200ed5c3679465bef491f5af0edb84c2c63a`.
- Image's OCI source revision: `e17cdd9d5c7e2b836b4670ae88bb87a79f94337a`. This published image is a different revision from the current Git checkout; both are recorded rather than conflated.
- Upstream Compose bundle: `~/repos/buzz/deploy/compose/compose.yml`.
- Deployment-only override: `~/.config/buzz/compose.aegis.yml`.
- The override uses the same official MinIO release from Quay because the upstream Docker Hub URL refused the pull. MinIO server is pinned to digest `14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`.
- Relay: `ws://100.72.225.119:8792`, bound only to the tailnet address.
- NIP-11 metadata responds; unsigned `/query` returns **401 missing Nostr auth**; owner-authenticated CLI channel reads/writes succeed.
- Dedicated `buzz-prod` containers: relay, Postgres, Redis and MinIO all healthy. Bucket initializer exited successfully. Named Buzz volumes and network are independent of Vintos.
- Native client: official `desktop-v0.5.23` Linux Debian package, extracted under `~/.local/opt/buzz/0.5.23`. It includes `buzz`, `buzz-acp`, `buzz-agent`, `buzz-dev-mcp`, desktop and other upstream tools.
- Installed WebKit runtime dependency. Launcher: `~/.config/buzz/desktop.py`; desktop shortcut: **Buzz — Aegis** at `~/.local/share/applications/buzz-aegis.desktop`.
- Client PID observed: 1281310, surviving startup with two established relay connections. This is connection evidence, not visual verification.
- Native client logged an unavailable AAC decoder and EGL warnings. It remained running and connected; audio/visual behavior still needs actual UI verification.
- Private owner identity: `~/.config/buzz/owner-key.hex`, mode 600. Relay secrets: upstream Compose `.env`, mode 600. Neither secret is in Git or this report.
- Channel IDs: Build agents `9c8a20c4-9d1c-4ebe-8895-6745d38b4515`; Discussion `57ab7a2f-b925-4e7d-bfbd-471c305b8c57`.

Buzz's full Stream/Forum/Agents interface is its native client. Its upstream web surface is a repository browser. Do not describe the relay URL as a replacement browser-based agent-management page or serve mock desktop data as a real client.

## Operating the installed stack

```sh
cd ~/repos/buzz/deploy/compose
docker compose -f compose.yml -f ~/.config/buzz/compose.aegis.yml ps
docker compose -f compose.yml -f ~/.config/buzz/compose.aegis.yml logs --tail=60 relay
```

Stop without deleting data:

```sh
docker compose -f compose.yml -f ~/.config/buzz/compose.aegis.yml stop
```

Restart:

```sh
docker compose -f compose.yml -f ~/.config/buzz/compose.aegis.yml up -d
```

Launch the installed native client with `/usr/bin/python3 ~/.config/buzz/desktop.py` or the Buzz — Aegis shortcut. Check an existing process before launching another instance. Do not print the owner key or Compose configuration with expanded secrets.

## What remains to deliver the complete agent-workspace request

1. Verify the rendered native UI on the chosen client; complete any onboarding needed to see the existing stream/forum. The Mac-versus-Aegis preference question is pending.
2. Configure Claude, Codex, Grok and Gemma with actual models/binaries, isolated work directories, per-agent persistent context and delegation instructions using Buzz's real ACP/MCP interfaces.
3. Bind task execution to authenticated owner approval, including each handoff. Buzz ACP has an owner-only inbound-author gate; automatic tool permission responses are not a substitute for per-task approval. Validate the actual workflow with fixtures before enabling runners. Do not assume its documented workflow approval feature is complete without inspecting the current executor.
4. Fix the verified Vintos budget-release and other runtime defects above before calling Claude's repairs complete. Keep the larger September 11 migration programme open.
5. Do not run another paid forge commissioning attempt without fresh permission.

No new Vintos deployment was performed in this pass. Its Aegis release checkout remains `47e0138`; the independent Buzz install does not imply Vintos source promotion. Vintos server was active/running, PID 1238876, NRestarts 0 at the final observation. The local/designated branch includes fixture repair 852e6a7.

## Evidence

Files under `review-evidence/2026-09-12/`:

- `all-isolated.txt`: initial 117/118 result.
- `bench-page-isolated.txt`: repaired fixture output.
- `final-all-direct.txt`, `final-all-isolated.txt`, `direct-results.json`, `isolated-results.json`: final 118/118 results.
- `review-counterexamples.json`: scratch-only budget replay and env parser counterexamples.
- `buzz-release.json`: official client release asset metadata.
- `buzz-channels.txt`: authenticated channel creation/readback.
- `aegis-buzz-state.txt`: actual containers, checkout, native process/connections and Vintos continuity.
- Bootstrap and launcher scripts contain no credentials; credentials were generated only on Aegis.
