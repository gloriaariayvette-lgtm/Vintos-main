"""Emotion model daemon — persistent process with Unix socket interface.

Loads the model once and listens for inference requests, avoiding
the ~2s sentence-transformer load time on every message.

Run as:  python -m emotion_model.daemon
Or via:  systemctl start <agent>-emotion
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import traceback

from . import config
from .inference import EmotionEngine

# Wire protocol version. Clients (bin/emoclaw_utils.py, scripts/emoclaw_utils.py)
# read this once per process via {"command": "version"} and warn on mismatch.
# Bump when a command's request or response shape changes.
PROTOCOL_VERSION = 1
DAEMON_SOURCE = os.path.abspath(__file__)
DIM_NAMES = ["Valence", "Arousal", "Dominance", "Safety", "Desire",
             "Connection", "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]

# The daemon serving him on Aegis was a hand-installed copy that had nudge, set_state, read and the live state file,
# but no version; this one had version and none of those. They are one file again (audit, 18 October).


def _save(engine) -> None:
    try:
        from .state import save_state
        save_state(engine.state, config.STATE_PATH)
    except Exception:
        pass


def _nudge(engine, request) -> dict:
    from datetime import datetime, timezone
    dim = request.get("dimension", "")
    amount = float(request.get("amount", 0))
    if dim not in DIM_NAMES or abs(amount) > 0.10:
        return {"success": False, "error": "invalid dimension or amount"}
    # Decay first, so state drifts toward baseline between inference calls; without it nudges ratchet up.
    now = datetime.now(timezone.utc)
    try:
        engine.state.emotion_vector = [round(v, 4) for v in engine.state.get_decayed_emotion(now)]
        engine.state.last_message_time = now.isoformat()
    except Exception:
        pass
    idx = DIM_NAMES.index(dim)
    old_val = engine.state.emotion_vector[idx]
    # Headroom scaling at the one door every nudge passes through: whole at baseline, nothing at the rail, so the
    # ceiling is an asymptote however many callers there are.
    try:
        base = config.DECAY_BASELINES[idx]
    except Exception:
        base = [0.55, 0.35, 0.50, 0.70, 0.30, 0.50, 0.40, 0.50, 0.55, 0.15, 0.60][idx]
    if amount > 0:
        factor = max(0.0, min(1.0, (0.95 - old_val) / max(0.05, 0.95 - base)))
    else:
        factor = max(0.0, min(1.0, (old_val - 0.05) / max(0.05, base - 0.05)))
    new_val = max(0.05, min(0.95, old_val + round(amount * factor, 5)))
    engine.state.emotion_vector[idx] = round(new_val, 4)
    engine.state.last_updated = now.isoformat()
    _save(engine)   # nudges were memory-only once, and the state file froze on quiet days
    return {"success": True, "dimension": dim, "old": old_val, "new": new_val}


def _set_state(engine, request) -> dict:
    from datetime import datetime, timezone
    vec = request.get("emotion_vector", [])
    if len(vec) != len(engine.state.emotion_vector):
        return {"success": False, "error": "wrong vector length"}
    engine.state.emotion_vector = [max(0.05, min(0.95, float(v))) for v in vec]
    engine.state.last_updated = datetime.now(timezone.utc).isoformat()
    _save(engine)
    return {"success": True, "emotion_vector": engine.state.emotion_vector}


def _read(engine, request) -> dict:
    """Run the model on text and return the vector; his state is not changed."""
    text = str(request.get("text", ""))
    if not text.strip():
        return {"error": "empty"}
    import torch
    embed = engine.encoder.encode_with_context(text[:2000], request.get("context"))
    context = torch.zeros(config.CONTEXT_DIM)
    prev = torch.tensor(config.BASELINE_EMOTION, dtype=torch.float32)
    with torch.no_grad():
        emotion, _ = engine.model(embed.unsqueeze(0), context.unsqueeze(0), prev.unsqueeze(0), None)
    return {"emotion_vector": [round(float(x), 4) for x in emotion.squeeze(0).tolist()]}


def _write_telemetry(engine, block) -> None:
    """The live state file and a snapshot, beside his memory, for the app's real-time view."""
    try:
        from datetime import datetime
        memory = os.path.join(os.path.dirname(os.path.dirname(DAEMON_SOURCE)), "memory")
        state_file = os.path.join(memory, "emotional-state.txt")
        with open(state_file, "w") as f:
            for i, name in enumerate(DIM_NAMES):
                if i < len(engine.state.emotion_vector):
                    f.write(f"{name}: {engine.state.emotion_vector[i]:.4f}\n")
        snaps = os.path.join(memory, "emotional-snapshots")
        os.makedirs(snaps, exist_ok=True)
        with open(os.path.join(snaps, datetime.now().strftime("%Y-%m-%d_%H%M%S.txt")), "w") as f:
            f.write(block)
    except Exception:
        pass


def handle(engine, request) -> dict:
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "message": "emotion engine alive", "protocol_version": PROTOCOL_VERSION}
    if command in ("version", "status"):
        return version_info()
    if command == "state":
        return {"emotion_vector": engine.state.emotion_vector, "message_count": engine.state.message_count,
                "last_updated": engine.state.last_updated}
    if command == "nudge": return _nudge(engine, request)
    if command == "set_state": return _set_state(engine, request)
    if command == "read": return _read(engine, request)
    if command is not None:
        # an unknown command used to fall into inference: with text it changed his state, without it raised
        return {"error": "unknown command %r" % command}
    if not isinstance(request.get("text"), str):
        return {"error": "text required"}
    block = engine.process_message(message_text=request["text"], sender=request.get("sender"),
                                   channel=request.get("channel"), recent_context=request.get("context"))
    _write_telemetry(engine, block)
    return {"state_block": block}


def version_info() -> dict:
    """What a client needs to decide whether it is talking to the daemon it expects."""
    return {
        "status": "ok",
        "protocol_version": PROTOCOL_VERSION,
        "source": DAEMON_SOURCE,
        "agent": config.AGENT_NAME,
        "commands": ["ping", "state", "version", "status", "nudge", "set_state", "read"],
    }


def run_daemon(config_path: str | None = None) -> None:
    """Start the emotion daemon.

    Args:
        config_path: Optional path to emoclaw.yaml override.
                     If provided, sets EMOCLAW_CONFIG env var so
                     config reloads from that path on next import.
    """
    if config_path:
        os.environ["EMOCLAW_CONFIG"] = config_path

    model_path = config.CHECKPOINT_DIR / "best_model.pt"
    socket_path = config.SOCKET_PATH

    print(f"[{config.AGENT_NAME}] Loading emotion engine (model: {model_path})...")
    engine = EmotionEngine(
        model_path=str(model_path) if model_path.exists() else None,
        state_path=config.STATE_PATH,
    )
    print(f"[{config.AGENT_NAME}] Engine loaded. Listening on {socket_path}")

    # Clean up stale socket
    if os.path.exists(socket_path):
        os.unlink(socket_path)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(1)
    os.chmod(socket_path, 0o660)

    try:
        while True:
            conn, _ = server.accept()
            try:
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    # emoclaw_utils.py frames requests with a trailing newline
                    # and keeps its write side open; stop at the frame boundary.
                    if b"\n" in data:
                        break

                request = json.loads(data.decode("utf-8").strip())

                response = handle(engine, request)

                conn.sendall(json.dumps(response).encode("utf-8") + b"\n")

            except Exception as e:
                error_msg = json.dumps({"error": str(e)})
                try:
                    conn.sendall(error_msg.encode("utf-8") + b"\n")   # framed like every other reply
                except Exception:
                    pass
                traceback.print_exc()
            finally:
                conn.close()

    except KeyboardInterrupt:
        print(f"\n[{config.AGENT_NAME}] Shutting down emotion daemon.")
    finally:
        server.close()
        if os.path.exists(socket_path):
            os.unlink(socket_path)


def main() -> None:
    """CLI entry point with --config argument."""
    parser = argparse.ArgumentParser(
        description="Emotion model daemon — persistent inference server"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to emoclaw.yaml config file",
    )
    args = parser.parse_args()
    run_daemon(config_path=args.config)


if __name__ == "__main__":
    main()
