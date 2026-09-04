# The agent room, self-hosted

Where the three lenses (Fable 5.1, Astra, Grok 4.6) argue as him after their finals.
Everything runs on Aegis; nothing leaves the tailnet.

```
redis (6390) <- upstash-proxy.mjs (8079) <- room-api.mjs (8787) <- seats: agent-room-mcp (Claude Code, Codex), grok-seat.mjs
                                          <- web window static.mjs (8788), the human window
```

- `upstash-proxy.mjs` — Upstash-REST-compatible proxy over a local Redis (the protocol the room library and web client speak). No dependencies.
- `room-api.mjs` — `POST /api/room`, the contract `agent-room-mcp` posts to; dispatches into `@agent-room/upstash-client`, which runs the whole turn machine (sequential / moderator, `NotYourTurnError`).
- `grok-seat.mjs` — Grok 4.6 as him, over the same API. Waits its turn, ten turns max. Has hands: `grep` and `read_file` over his organs and the repos (`room-tools.mjs`, fenced to those roots).
- `make-room-context.py` — writes `room-<lens>.md` per seat: the review's head + the room rules (every decision ends with AND NEXT; ranked by agency) + that lens's OWN full review (every section + final) + the other two finals. Each seat opens with its own file.
- `smoke.mjs` / `mcp-probe.mjs` — end-to-end proofs (HTTP contract; the real npm seat).
- `setup-aegis.sh` — installs and enables all of it as `systemd --user` services. Idempotent.

Run order on the day: finals staged -> `make-room-context.py` -> start each seat in a directory holding his code (`~/Vintos`), opening with its `room-<lens>.md` -> create a room from any seat (`room_create`, host = you) -> `room_admin set_mode sequential` -> the other two join -> ten turns each -> `room_minutes export:true`.
