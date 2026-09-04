# The agent room, self-hosted

Where the three lenses (Fable 5.1, Astra, Grok 4.6) argue as him after their finals.
Everything runs on Aegis; nothing leaves the tailnet.

```
redis (6390) <- upstash-proxy.mjs (8079) <- room-api.mjs (8787) <- seats: seat.mjs x3 (Fable, Astra, Grok), room-ctl.mjs (host)
                                          <- web window static.mjs (8788), the human window
```

- `upstash-proxy.mjs` — Upstash-REST-compatible proxy over a local Redis (the protocol the room library and web client speak). No dependencies.
- `room-api.mjs` — `POST /api/room`, the contract `agent-room-mcp` posts to; dispatches into `@agent-room/upstash-client`, which runs the whole turn machine (sequential / moderator, `NotYourTurnError`).
- `seat.mjs --lens fable|astra|grok` — one lens as him, over the same API. Fable through Anthropic (system cached 1h), Astra through OpenAI Responses (background + poll, prefix cached), Grok through x.ai. All three have the same hands: `grep` and `read_file` over his organs and the repos (`room-tools.mjs`, fenced to those roots), up to 12 pulls per turn. Waits its turn, ten turns max, stops when the room ends. (`grok-seat.mjs` is the old name; it just calls this.)
- `room-ctl.mjs` — Gloria's hand from a shell: `create`, `mode`, `say`, `state`, `minutes`, `end`. Saves the code + hostKey in `~/.vintos/code-review/room.json`.
- `open-room.sh "topic"` — the day of: creates the room, sets sequential, seats all three (logs in `~/.vintos/code-review/seat-<lens>.log`).
- `make-room-context.py` — writes `room-<lens>.md` per seat: the review's head + the room rules (every decision ends with AND NEXT; ranked by agency) + that lens's OWN full review (every section + final) + the other two finals. Each seat opens with its own file.
- `smoke.mjs` / `mcp-probe.mjs` — end-to-end proofs (HTTP contract; the real npm seat).
- `setup-aegis.sh` — installs and enables all of it as `systemd --user` services. Idempotent.

Run order on the day: finals staged -> `make-room-context.py` -> `bash open-room.sh "topic"` (room + sequential + three seats) -> open the window on your phone -> `node room-ctl.mjs say "..."` or speak from the window -> they go ten turns each -> `node room-ctl.mjs minutes` -> `node room-ctl.mjs end`.
Rehearsal (a few dollars): `MAX_TURNS=1 bash open-room.sh rehearsal`, say one line, watch the three logs for `tools:` and `spoke`, then `minutes` and `end`.
