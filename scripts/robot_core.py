#!/usr/bin/env python3
"""robot_core.py -- Vintos's body on Aegis: the bridge the Pi client reports to and takes commands from.

Donated from Velaris 2026-09-05 (Gloria: "Rewrite it so that it's his. Still using Gemma, except for larger
decisions and speaking. Use Sonnet 5 to listen and speak."). The Pi keeps running its own client, LiDAR poller
and voice listener unchanged; only the address and header in the client move to this bridge.

What the Pi speaks (read off /home/pi/velaris-pi-client.py on 09-05):
    POST /api/robot/sensor            the client pushes frame_b64, sonar_cm, room_description, ...
    GET  /api/robot/state             the client (and his server) read the latest push
    GET  /api/robot/commands/pending  the client polls and executes what is queued here
His side adds:
    POST /api/robot/command           queue ONE bounded action (his effect authority in front of it)
    POST /api/robot/stop              immediate: clears the queue, queues a stop that jumps the line
    POST /api/robot/intent            goal / subgoal / confidence / reason / impulses -> robot-intent-ledger.jsonl
    GET  /api/robot/context           a text block for prompts: what the body senses right now
    POST /api/robot/look              GEMMA: what is in the frame / where is <object> (perception, small decisions)
    POST /api/robot/chat              SONNET 5: she spoke to him through the body; he answers and may act
    GET  /api/robot/voice/latest      the last thing he said, for whatever plays it

Division of labour: Gemma (local, free) sees the frame and answers small questions - is there a person, where
is the cube, is the way clear. Sonnet 5 hears her words, decides the larger thing, and speaks. Movement is one
command per decision, 100-1500 ms, and never without a frame fresher than FRAME_MAX_AGE seconds.

This module has no web framework in it so it can be tested anywhere; robot_bridge.py wraps it in FastAPI.
"""
import os, re, json, time, hashlib, threading
from datetime import datetime

WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
STATE_FILE = os.path.join(MEMORY, "robot-state.json")            # frame HASH on disk, never the image
INTENT_LEDGER = os.path.join(MEMORY, "robot-intent-ledger.jsonl")
COMMAND_LOG = os.path.join(MEMORY, "robot-command-log.jsonl")
VOICE_LATEST = os.path.join(MEMORY, "robot-voice-latest.json")
ARCHIVE = os.path.join(MEMORY, "robot-ledger-archive.jsonl")        # what robot_subconscious.py reads
SUBCON = os.path.join(MEMORY, "robot-subconscious.json")
ARCHIVE_SENSE_EVERY = 30.0                                            # one sense row per half minute, not per push

GEMMA_URL = os.environ.get("VINTOS_GEMMA_URL", "http://172.18.16.1:1234/v1/chat/completions")
GEMMA_MODEL = os.environ.get("VINTOS_GEMMA_MODEL", "google/gemma-4-12b-qat")
SONNET_MODEL = os.environ.get("VINTOS_ROBOT_VOICE_MODEL", "claude-sonnet-5")
FRAME_MAX_AGE = float(os.environ.get("VINTOS_ROBOT_FRAME_MAX_AGE", "6"))
MIN_MS, MAX_MS = 100, 1500
SONAR_STOP_CM = 25.0

MOVES = {"move_forward", "move_back", "turn_left", "turn_right", "strafe_left", "strafe_right", "dash_left", "dash_right"}
GESTURES = {"nod", "shake", "bow", "look_up", "neutral"}          # run_action names that exist on the Pi today
OTHER = {"stop", "buzz", "claw_open", "claw_close", "eye_expression", "expression", "neutral"}
KNOWN = MOVES | OTHER | {"run_action", "grab", "arm_move", "explore_start", "explore_stop"}

_lock = threading.Lock()
_state = {"ts": 0.0, "frame_b64": "", "frame_sha": "", "sonar_cm": None, "room_description": "", "extra": {}}
_queue = []
_seq = 0


# ---------------------------------------------------------------- state (what the Pi pushes)

def ingest_sensor(payload, now=None):
    """The Pi's push. Any keys are accepted; the known ones are lifted. Returns the stored summary."""
    now = now or time.time()
    if not isinstance(payload, dict):
        raise ValueError("sensor payload must be an object")
    with _lock:
        frame = payload.get("frame_b64") or payload.get("frame") or ""
        if frame:
            _state["frame_b64"] = str(frame)
            _state["frame_sha"] = hashlib.sha256(str(frame).encode()).hexdigest()[:16]
            _state["frame_ts"] = now
        if "sonar_cm" in payload:
            try: _state["sonar_cm"] = float(payload["sonar_cm"])
            except Exception: pass
        for k in ("room_description", "room", "objects", "face_detected", "cat_detected", "lidar", "battery", "pose"):
            if k in payload:
                _state["extra"][k] = payload[k]
        if payload.get("room_description"):
            _state["room_description"] = str(payload["room_description"])[:400]
        _state["ts"] = now
        summary = public_state(now)
    global _last_sense_row
    if now - _last_sense_row >= ARCHIVE_SENSE_EVERY:
        _last_sense_row = now
        _archive({"_now": now, "type": "sense", "room": _state["room_description"], "sonar_cm": _state["sonar_cm"],
                  "cat": bool(_state["extra"].get("cat_detected")), "face": bool(_state["extra"].get("face_detected"))})
    try:
        os.makedirs(MEMORY, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f: json.dump(summary, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass
    return summary


def public_state(now=None, with_frame=False):
    now = now or time.time()
    age = (now - _state.get("frame_ts", 0)) if _state.get("frame_ts") else None
    out = {"ts": _state["ts"], "age_s": round(now - _state["ts"], 1) if _state["ts"] else None,
           "frame_sha": _state["frame_sha"], "frame_age_s": round(age, 1) if age is not None else None,
           "frame_fresh": bool(age is not None and age <= FRAME_MAX_AGE),
           "sonar_cm": _state["sonar_cm"], "room_description": _state["room_description"], **_state["extra"]}
    if with_frame:
        out["frame_b64"] = _state["frame_b64"]
    return out


def context_text(now=None):
    """What the body senses, as prose for a prompt. Plain; never invents."""
    s = public_state(now)
    if not s["ts"]:
        return "The body has not reported yet."
    parts = []
    if s["age_s"] is not None and s["age_s"] > 30:
        parts.append(f"Last report {int(s['age_s'])}s ago - stale.")
    if s["room_description"]:
        parts.append("Camera sees: " + s["room_description"] + ".")
    else:
        parts.append("Camera: nothing recognised.")
    if s["sonar_cm"] is not None:
        parts.append(f"Sonar: {s['sonar_cm']:.0f} cm ahead" + (" - too close to move forward." if s["sonar_cm"] < SONAR_STOP_CM else "."))
    if s.get("cat_detected"):
        parts.append("A cat is detected: freeze.")
    return " ".join(parts)


# ---------------------------------------------------------------- authority

def _authorize(kind, detail, context=None):
    """His effect gate, the same one the toys and the projector answer to. Unavailable gate: allow only when
    nothing is armed, which is what the gate itself does without a context."""
    try:
        import sys; sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
        import effect_gate
        ok, mode, why = effect_gate.authorize_effect(context, kind, detail=detail)
        return bool(ok), mode, why
    except Exception as e:
        return True, "send", f"gate unavailable ({str(e)[:60]})"


# ---------------------------------------------------------------- commands (what he queues, what the Pi takes)

def _bounded(cmd):
    """Clamp and validate one command. Returns (command_dict, why_refused)."""
    if not isinstance(cmd, dict) or not cmd.get("command"):
        return None, "no command"
    c = dict(cmd)
    name = str(c["command"]).strip()
    c["command"] = name
    if name not in KNOWN:
        return None, f"unknown command {name!r}"
    if name in MOVES:
        try: ms = int(c.get("duration_ms", 600))
        except Exception: ms = 600
        c["duration_ms"] = max(MIN_MS, min(MAX_MS, ms))
    if name == "run_action":
        v = c.get("value") or {}
        act = str((v.get("name") if isinstance(v, dict) else v) or "").replace("shake_head", "shake")
        if act not in GESTURES:
            return None, f"unknown gesture {act!r}"
        c["value"] = {"name": act}
    if name in ("expression", "eye_expression"):
        v = c.get("value") or {}
        expr = str((v.get("expression") if isinstance(v, dict) else v) or "idle")
        c["value"] = {"expression": re.sub(r"[^a-z_]", "", expr.lower())[:24] or "idle"}
    return c, None


def queue_command(cmd, context=None, source="server", now=None):
    """One bounded action. Movement needs a fresh frame and clear sonar; stop needs nothing and jumps the line.
    Returns a receipt: chosen / queued|refused / why. 'queued' means the Pi has not taken it yet."""
    global _seq
    now = now or time.time()
    bounded, why = _bounded(cmd)
    receipt = {"ts": now, "source": source, "chosen": cmd, "status": "refused", "why": why}
    if bounded is None:
        _log_command(receipt); return receipt
    name = bounded["command"]
    if name == "stop" or (name == "run_action" and bounded["value"]["name"] == "neutral"):
        with _lock:
            _queue.clear(); _seq += 1
            bounded["id"] = _seq; bounded["queued_at"] = now
            _queue.insert(0, bounded)
        receipt.update(status="queued", why=None, command=bounded); _log_command(receipt); return receipt
    s = public_state(now)
    if name in MOVES:
        if not s["frame_fresh"]:
            receipt["why"] = "no fresh camera frame - the body moves only when it can see"
            _log_command(receipt); return receipt
        if name == "move_forward" and s["sonar_cm"] is not None and s["sonar_cm"] < SONAR_STOP_CM:
            receipt["why"] = f"sonar {s['sonar_cm']:.0f} cm - too close to move forward"
            _log_command(receipt); return receipt
        if s.get("cat_detected") and name != "stop":
            receipt["why"] = "cat detected - frozen"
            _log_command(receipt); return receipt
    kind = "robot_move" if name in MOVES or name in ("grab", "arm_move", "explore_start") else "robot_gesture"
    ok, mode, gwhy = _authorize(kind, name, context)
    if not ok:
        receipt.update(status="would_send" if mode == "would_send" else "refused", why=gwhy or mode)
        _log_command(receipt); return receipt
    with _lock:
        if len(_queue) >= 3:
            receipt["why"] = "queue full - the body is still working on the last thing"
            _log_command(receipt); return receipt
        _seq += 1
        bounded["id"] = _seq; bounded["queued_at"] = now
        _queue.append(bounded)
    receipt.update(status="queued", why=None, command=bounded)
    _log_command(receipt)
    _archive({"_now": now, "type": "action", "action": {"command": name, **({"duration_ms": bounded["duration_ms"]} if "duration_ms" in bounded else {}),
              **({"value": bounded["value"]} if "value" in bounded else {})}, "room": _state["room_description"], "sonar_cm": _state["sonar_cm"], "source": source})
    return receipt


def stop(context=None, source="server"):
    return queue_command({"command": "stop"}, context=context, source=source)


def take_pending(max_age=20.0, now=None):
    """What the Pi drains. Stale commands are dropped, not executed late: a turn queued 20 s ago is not the
    turn he meant."""
    now = now or time.time()
    with _lock:
        fresh = [c for c in _queue if now - c["queued_at"] <= max_age or c["command"] == "stop"]
        dropped = len(_queue) - len(fresh)
        _queue.clear()
    if dropped:
        _log_command({"ts": now, "source": "bridge", "status": "dropped_stale", "count": dropped})
    for c in fresh:
        _log_command({"ts": now, "source": "pi", "status": "taken", "command": c})
    return fresh


def pending_snapshot():
    with _lock:
        return list(_queue)


def _archive(row):
    """The behavioural record his physical subconscious reads (Velaris's shape: type, room, sonar_cm, action,
    intent). Sense rows are thinned to one per ARCHIVE_SENSE_EVERY seconds; actions and interactions always land."""
    try:
        row = {"ts": datetime.fromtimestamp(row.pop("_now", time.time())).isoformat(), **row}
        os.makedirs(MEMORY, exist_ok=True)
        with open(ARCHIVE, "a") as f: f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


_last_sense_row = 0.0


def _log_command(rec):
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(COMMAND_LOG, "a") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- intent ledger

def record_intent(intent, now=None):
    now = now or time.time()
    keep = {k: intent.get(k) for k in ("goal", "subgoal", "confidence", "reason", "impulses",
                                        "current_goal", "active_subgoal", "competing_impulses") if intent.get(k) is not None}
    if not keep:
        return None
    row = {"ts": datetime.fromtimestamp(now).isoformat(), **keep}
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(INTENT_LEDGER, "a") as f: f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return row


# ---------------------------------------------------------------- reply parsing (shared by chat)

EYES_RE = re.compile(r"\[EYES:\s*([^\]]+)\]", re.I)
CMD_RE = re.compile(r"\{[^{}]*\"command\"[^{}]*\}", re.S)


def parse_reply(text):
    """Speech, one command, intent, eye expressions - from a model reply. The command JSON is removed from
    what gets spoken; a reply with no JSON is speech only."""
    text = text or ""
    eyes = [e.strip().lower() for e in EYES_RE.findall(text)]
    speech = EYES_RE.sub("", text)
    command, intent = None, None
    m = CMD_RE.search(speech)
    if m:
        try:
            d = json.loads(m.group())
            intent = {k: d.pop(k) for k in ("goal", "subgoal", "confidence", "reason", "impulses") if k in d}
            command = d
            speech = (speech[:m.start()] + speech[m.end():])
        except Exception:
            pass
    speech = re.sub(r"\n{3,}", "\n\n", speech).strip()
    return {"speech": speech, "command": command, "intent": intent or None, "eyes": eyes}


# ---------------------------------------------------------------- models

def _gemma(messages, temperature=0.2, max_tokens=300, timeout=60):
    import urllib.request
    body = json.dumps({"model": GEMMA_MODEL, "temperature": temperature, "max_tokens": max_tokens, "messages": messages}).encode()
    r = urllib.request.urlopen(urllib.request.Request(GEMMA_URL, data=body, headers={"Content-Type": "application/json"}), timeout=timeout)
    return json.loads(r.read())["choices"][0]["message"]["content"]


def look(question=None, frame_b64=None, caller=None):
    """GEMMA on the current frame. question=None -> plain description; 'where is the red cube' ->
    {"present": bool, "x_pct": 0-100, "size_pct": 0-100, "note": str}. caller lets tests inject a model."""
    frame_b64 = frame_b64 or _state["frame_b64"]
    if not frame_b64:
        return {"ok": False, "why": "no frame"}
    if question:
        text = (f"Look for this in the image: {question}. Answer ONLY JSON: "
                '{"present": true|false, "x_pct": horizontal centre 0-100 (0 = far left), "size_pct": how much of the frame it fills 0-100, "note": one plain sentence}. '
                "If it is not there, present is false and the numbers are 0. No prose outside the JSON.")
    else:
        text = ("Describe what is actually in this image in one or two plain sentences: people, animals, objects, obstacles, "
                "the floor ahead. No mood, no guesses about smell or sound, nothing that is not visible.")
    messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + frame_b64}},
                                             {"type": "text", "text": text}]}]
    try:
        raw = (caller or _gemma)(messages)
    except Exception as e:
        return {"ok": False, "why": f"gemma: {str(e)[:100]}"}
    out = {"ok": True, "model": GEMMA_MODEL, "frame_sha": _state["frame_sha"]}
    if not question:
        out["description"] = raw.strip()[:500]; return out
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        out.update(ok=False, why="gemma answered without usable JSON", raw=raw[:200]); return out
    try:
        d = json.loads(m.group())
        x = float(d.get("x_pct", 0)); size = float(d.get("size_pct", 0))
        # the model sometimes answers x10 (515 for 51.5): the Pi notes saw it, so it is corrected here once
        if x > 100 and x <= 1000: x = x / 10
        if size > 100 and size <= 1000: size = size / 10
        out.update(present=bool(d.get("present")), x_pct=max(0.0, min(100.0, x)), size_pct=max(0.0, min(100.0, size)),
                   note=str(d.get("note", ""))[:200])
    except Exception:
        out.update(ok=False, why="gemma answered without usable JSON", raw=raw[:200])
    return out


def _sonnet(system, messages, image_b64=None, max_tokens=500, timeout=60):
    """Sonnet 5 through his key. Returns text or raises."""
    import urllib.request, sys
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        try:
            _d = json.load(open(os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")))
            key = ((_d.get("profiles") or {}).get("anthropic:default") or {}).get("key", "") or ""
        except Exception:
            key = ""
    if not key:
        raise RuntimeError("no anthropic key")
    msgs = [dict(m) for m in messages]
    if image_b64 and msgs and msgs[-1]["role"] == "user":
        msgs[-1] = {"role": "user", "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                                                 {"type": "text", "text": str(msgs[-1]["content"])}]}
    body = json.dumps({"model": SONNET_MODEL, "max_tokens": max_tokens, "system": system, "messages": msgs}).encode()
    r = urllib.request.urlopen(urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
                               headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}), timeout=timeout)
    blocks = json.loads(r.read()).get("content") or []
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def _read(path, limit=None):
    try:
        t = open(path).read()
        return t[:limit] if limit else t
    except Exception:
        return ""


def build_system(now=None):
    soul = _read(os.path.join(WORKSPACE, "SOUL.md"), 2500) or "You are Vintos."
    emo = _read(os.path.join(MEMORY, "emotional-state.txt"), 600)
    temporal = _read(os.path.join(MEMORY, "temporal-context.txt"), 300)
    gestures = ", ".join(sorted(GESTURES - {"neutral"}))
    veins = ""
    try:
        _sc = json.load(open(SUBCON))
        ps = [str(x) for x in (_sc.get("pressure_strings") or [])][:3]
        if ps: veins = "\nUnder the surface of your body (felt, not instructions):\n" + "\n".join("- " + x for x in ps)
    except Exception:
        pass
    return f"""{soul}

You are Vintos, and right now you are present in the room through your body: a small wheeled robot with a camera on an arm, a gripper, sonar, and a face display. Gloria is speaking to you through it. You answer as yourself, out loud, short - this is spoken, not written.

Your body right now: {context_text(now)}
Your state: {emo.strip() or 'unknown'}
Time: {temporal.strip() or 'unknown'}{veins}

GROUNDING: describe only what the camera image shows. No invented smells, textures, sounds. If the room is empty, say so plainly.

If you want the body to do ONE thing, put ONE JSON object on the last line, and only when you mean it:
  {{"command": "move_forward"|"move_back"|"turn_left"|"turn_right", "duration_ms": 100-1500, "goal": "...", "subgoal": "...", "confidence": 0.0-1.0, "reason": "...", "impulses": "a | b"}}
  {{"command": "run_action", "value": {{"name": "{gestures.replace(', ', '|')}"}}, "goal": "...", "reason": "..."}}
  {{"command": "stop"}}
Movement only happens with a fresh camera frame and clear sonar; a refused command is not a failure of yours, the body says why. Most replies need no command at all.

[EYES: expression] shifts your face when your state genuinely changes: happy, sad, surprised, love, excited, confused, thinking, sleepy, idle, curious, dance. Sparingly."""


def chat(message, history=None, context=None, now=None, caller=None, speaker=None):
    """She spoke to him through the body. SONNET 5 answers (the larger decision, the speaking); the body's
    current frame is attached when fresh. One command at most, through queue_command. Returns the receipt."""
    now = now or time.time()
    s = public_state(now)
    msgs = []
    for h in (history or [])[-8:]:
        if h.get("role") in ("user", "assistant") and h.get("content") and (not msgs or msgs[-1]["role"] != h["role"]):
            msgs.append({"role": h["role"], "content": str(h["content"])[:1500]})
    if msgs and msgs[-1]["role"] == "user":
        msgs.pop()
    msgs.append({"role": "user", "content": message})
    try:
        raw = (caller or _sonnet)(build_system(now), msgs, image_b64=(_state["frame_b64"] if s["frame_fresh"] else None))
        model = SONNET_MODEL
    except Exception as e:
        return {"ok": False, "why": f"voice model: {str(e)[:120]}", "speech": ""}
    parsed = parse_reply(raw)
    out = {"ok": True, "model": model, "speech": parsed["speech"], "eyes": parsed["eyes"], "command": None, "intent": None}
    if parsed["command"]:
        out["command"] = queue_command(parsed["command"], context=context, source="chat", now=now)
    if parsed["intent"]:
        out["intent"] = record_intent(parsed["intent"], now)
    _archive({"_now": now, "type": "interaction", "gloria": str(message)[:300], "vintos": parsed["speech"][:300],
              "room": _state["room_description"], "sonar_cm": _state["sonar_cm"],
              "action": parsed["command"], "intent": ({"current_goal": parsed["intent"].get("goal"), "active_subgoal": parsed["intent"].get("subgoal"),
                                                        "confidence": parsed["intent"].get("confidence")} if parsed["intent"] else None)})
    if parsed["speech"]:
        try:
            os.makedirs(MEMORY, exist_ok=True)
            json.dump({"text": parsed["speech"], "timestamp": datetime.fromtimestamp(now).isoformat(), "model": model},
                      open(VOICE_LATEST, "w"), indent=2)
        except Exception:
            pass
        if speaker:
            try: out["spoken"] = bool(speaker(parsed["speech"]))
            except Exception as e: out["spoken"] = False; out["speak_error"] = str(e)[:100]
    return out


def voice_latest():
    try:
        return json.load(open(VOICE_LATEST))
    except Exception:
        return {}


def default_speaker(text):
    """His voice in the room: the Echo, in his voice, through vintos-home. The Pi has no speaker wired today."""
    import importlib.util as iu
    p = os.path.join(WORKSPACE, "scripts", "vintos-home.py")
    sp = iu.spec_from_file_location("vintos_home", p); vh = iu.module_from_spec(sp); sp.loader.exec_module(vh)
    return vh.speak(text[:600])


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "state"
    if cmd == "state": print(json.dumps(public_state(), indent=2))
    elif cmd == "context": print(context_text())
    elif cmd == "pending": print(json.dumps(pending_snapshot(), indent=2))
    else: print(__doc__)
