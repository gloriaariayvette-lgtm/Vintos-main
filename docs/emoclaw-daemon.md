# EmoClaw emotion daemon — ownership, socket, protocol

## Which file is the daemon

- **Bundled source (this repo):** `skills/emoclaw/engine/emotion_model/daemon.py`
  (`python -m emotion_model.daemon`). This is the copy that carries the protocol
  version and is the one this repo's clients are written against.
- **Installed copy on the host:** `~/.vintos/workspace/emotion_model/daemon.py`,
  launched by `bin/emoclaw-daemon-guard.sh` (`cd $DAEMON_DIR && PYTHONPATH=.. .venv/bin/python3 daemon.py`).
  It may be older or patched (it accepts `nudge`, which the bundled copy does not).
  The handshake below exists so a client can tell which one it is talking to.

## Unit

`vintos-emotion.service` (user unit: `systemctl --user start vintos-emotion.service`).
The guard's `ensure` action uses the unit when `systemctl --user list-unit-files`
reports it installed; otherwise it launches `daemon.py` directly the way the unit would.

Guard: `bin/emoclaw-daemon-guard.sh [ensure|start|stop|status|restart]`
(no argument = `ensure`: idempotent, bounded retry `EMOCLAW_ENSURE_RETRIES`, default 3,
one log line per event to the daemon log). Health cron: `bin/emoclaw-heartbeat.sh`.

## Paths

| what | path |
|---|---|
| socket | `/tmp/Vintos-emotion.sock` (config `paths.socket_path` = `/tmp/{name}-emotion.sock`) |
| pid file | `/tmp/Vintos-emotion.pid` |
| daemon log | `/tmp/emoclaw-daemon.log` |
| state | `~/.vintos/workspace/memory/emotional-state.json` (`.txt` is the client fallback) |

## Protocol

Unix stream socket. One request per connection: a single JSON object, newline-terminated.
The daemon replies with one JSON object followed by a newline and closes.

| command | request | response |
|---|---|---|
| `ping` | `{"command":"ping"}` | `{"status":"ok","message":"emotion engine alive","protocol_version":1}` |
| `state` | `{"command":"state"}` | `{"emotion_vector":[...],"message_count":N,"last_updated":...}` |
| `version` / `status` | `{"command":"version"}` | `{"status":"ok","protocol_version":1,"source":"<abs path of daemon.py>","agent":"Vintos","commands":[...]}` |
| inference | `{"text":"...","sender":?,"channel":?,"context":?}` | `{"state_block":"..."}` |
| `nudge` (installed copy only) | `{"command":"nudge","dimension":"Curiosity","amount":0.03}` | `{"success":true}` |

Errors: `{"error":"..."}`.

## Version

`PROTOCOL_VERSION = 1` in `skills/emoclaw/engine/emotion_model/daemon.py`.
`EXPECTED_PROTOCOL_VERSION = 1` in `bin/emoclaw_utils.py` and `scripts/emoclaw_utils.py`
(identical twins). `check_daemon_protocol()` runs once per process on the first
`get_state()` / `nudge_emotion()` that reaches the socket; on a mismatch (including a
daemon that does not answer `version`) it prints one line to stderr —
`[EmoClaw] protocol version mismatch: ...` — and keeps working. Bump both numbers
together whenever a command's request or response shape changes.
