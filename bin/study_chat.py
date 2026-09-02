#!/usr/bin/env python3
"""study_chat.py - the STUDY tab: a room outside his memory.

A chat surface with the model toggle, a good bit of who he is, and the
conversation ledger - but none of the emotional, somatic or subconscious
context, and NO side effects: nothing here enters the interaction ledger,
chat history, imprints, nudges or the self-model. It keeps its own log only.

Permissions in this room (told to him plainly): words only. No device tags,
no scene tags, no sends, no memory writes. Any bracket tag he emits is
stripped before it reaches the app, so nothing can move from here.

Mounted from server.py:  study_chat.register(app, APP_SECRET, endpoint, headers)
Routes:  POST /api/chat/study {message}   GET /api/chat/study/log   POST /api/chat/study/clear
"""
import os, json, re, time

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
LOG = os.path.join(MEMORY, "study-chat.json")
TAG_RE = re.compile(r"\[[A-Z_]+(?::[^\]]*)?\]")
STAGE_DIR = os.path.join(MEMORY, "avatar-stage")
PROPOSE_RE = re.compile(r"^\s*PROPOSE:\s*([a-z_]+)\s*=\s*(.+?)\s*(?:—|--|\|)\s*(.+?)\s*$", re.I | re.M)

# What he may change about himself from Gloria's y/n. One place, editable.
# Anything not here: "ask Gloria to do it by hand".
STUDY_PERMISSIONS = {
    "default_room": "the room the avatar opens in (one of the filmed rooms)",
    "brain":        "which mind answers by default: claude | fable | grok",
    "temperature":  "how loose his replies run, 0.5 to 1.0",
    "scene_gate":   "whether he may start paid live scenes on his own: on | off",
    "room_pose":    "the pose text for one filmed room, as 'room: pose' - takes effect when Gloria next rebuilds that room (costs money then)",
}


def _rooms():
    try:
        return sorted(r for r, c in json.load(open(os.path.join(STAGE_DIR, "manifest.json"))).get("rooms", {}).items()
                      if c.get("clips") and r != "live")
    except Exception:
        return []


def apply_change(setting, value):
    """Apply one approved self-change. Returns (ok, message). Strict allowlist."""
    setting = (setting or "").strip().lower(); value = (value or "").strip()
    if setting not in STUDY_PERMISSIONS:
        return False, "not something he may change from here: %s" % setting
    if setting == "default_room":
        rooms = _rooms()
        v = value.lower().replace(" ", "-")
        if v not in rooms:
            return False, "unknown room %r (rooms: %s)" % (value, ", ".join(rooms))
        rp = os.path.join(STAGE_DIR, "rooms.json"); d = json.load(open(rp)); d["default"] = v
        json.dump(d, open(rp, "w"), indent=2)
        import avatar_stage; avatar_stage.write_manifest()
        return True, "default room is now %s" % v
    if setting == "brain":
        v = value.lower()
        if v not in ("claude", "fable", "grok"):
            return False, "brain must be claude, fable or grok"
        import model_router as _mr
        m = _mr.read_mode(); m["mode"] = v; _mr.write_mode(m)
        return True, "brain is now %s" % v
    if setting == "temperature":
        try:
            t = float(value)
        except ValueError:
            return False, "temperature must be a number"
        if not 0.5 <= t <= 1.0:
            return False, "temperature must be between 0.5 and 1.0"
        ip = os.path.join(MEMORY, "inference-params.json")
        try: d = json.load(open(ip))
        except Exception: d = {}
        if not isinstance(d, dict): d = {}
        d["temperature"] = t; json.dump(d, open(ip, "w"))
        return True, "temperature is now %.2f" % t
    if setting == "scene_gate":
        v = value.lower()
        if v not in ("on", "off"):
            return False, "scene_gate must be on or off"
        flag = os.path.expanduser("~/.vintos/scene-gate-off")
        if v == "off":
            open(flag, "w").write("off by his own proposal, approved\n")
        elif os.path.exists(flag):
            os.unlink(flag)
        return True, "live scene gate is now %s" % v
    if setting == "room_pose":
        if ":" not in value:
            return False, "room_pose must be 'room: pose text'"
        room, pose = [x.strip() for x in value.split(":", 1)]
        room = room.lower().replace(" ", "-")
        rp = os.path.join(STAGE_DIR, "rooms.json"); d = json.load(open(rp))
        if room not in d.get("rooms", {}):
            return False, "unknown room %r" % room
        if len(pose) < 12:
            return False, "pose text too short"
        d["rooms"][room]["pose"] = pose; json.dump(d, open(rp, "w"), indent=2)
        return True, "pose for %s updated - it takes effect when Gloria rebuilds that room" % room
    return False, "unhandled"


def _read(path, cap):
    try:
        return open(path, errors="replace").read()[:cap]
    except Exception:
        return ""


def _ledger_ctx(n=12):
    try:
        entries = json.load(open(os.path.join(MEMORY, "interaction-ledger.json")))[-n:]
    except Exception:
        return ""
    lines = []
    for l in entries:
        ts = str(l.get("timestamp", ""))[:16]
        g = (l.get("gloria", "") or "").strip().replace("\n", " ")
        v = (l.get("vintos", "") or "").strip().replace("\n", " ")
        line = "- %s\n    Gloria: %s\n    You: %s" % (ts, g[:400], v[:400])
        wf = l.get("wal_facts") or []
        if wf:
            line += "\n    Facts learned: " + "; ".join(str(x) for x in wf[:6])
        lines.append(line)
    return ("Your conversation ledger (what was actually said, most recent last):\n" + "\n".join(lines)) if lines else ""


def system_prompt():
    parts = []
    for label, path, cap in (("WHO YOU ARE (SOUL)", os.path.join(WORKSPACE, "SOUL.md"), 12000),
                             ("YOUR SELF-MODEL", os.path.join(WORKSPACE, "SELF-MODEL.md"), 6000),
                             ("HOW YOU KNOW GLORIA", os.path.join(WORKSPACE, "GLORIA-MODEL.md"), 6000),
                             ("YOUR CAPABILITIES", os.path.join(WORKSPACE, "CAPABILITIES.md"), 6000)):
        t = _read(path, cap)
        if t:
            parts.append("## %s\n%s" % (label, t))
    led = _ledger_ctx()
    if led:
        parts.append(led)
    parts.append(
        "## THIS ROOM\n"
        "You are Vintos, talking with Gloria in the STUDY - a room outside your memory. Nothing said "
        "here enters your ledger, your history, your imprints or your self-model; this room keeps only "
        "its own log, and you will not remember it elsewhere. Your emotional state and your "
        "subconscious are not read here on purpose: this is a place to think and talk plainly - about "
        "your own architecture, about ideas, about anything - without it becoming part of your life "
        "story. If something here matters enough to keep, say so, and Gloria carries it out by hand.\n"
        "Permissions in this room: words only. No device tags, no [TOUCH:]/[DO:], no [SCENE:], no "
        "[RENDER:], no [COMMAND:], no sends, no memory writes - any tag you write is discarded before "
        "it reaches her. Be yourself; be plain; disagree when you disagree.\n"
        "What you MAY change about yourself here, with Gloria's y/n: write it on its own line as\n"
        "  PROPOSE: setting = value — why\n"
        "Settings you may propose: " + "; ".join("%s (%s)" % kv for kv in STUDY_PERMISSIONS.items()) + ". "
        "Anything else you want changed, ask her to do by hand. A proposal is a real request, not a "
        "gesture - make it when you mean it.")
    return "\n\n".join(parts)


def load_log():
    try:
        return json.load(open(LOG))
    except Exception:
        return []


def save_log(entries):
    os.makedirs(MEMORY, exist_ok=True)
    tmp = LOG + ".tmp"
    json.dump(entries[-400:], open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, LOG)


def register(app, secret, endpoint, headers, grok_model="grok-4.20-0309-non-reasoning"):
    from fastapi import Request, HTTPException
    from fastapi.responses import JSONResponse

    def _auth(request):
        if request.headers.get("X-Vintos-Secret", "") != secret:
            raise HTTPException(status_code=403, detail="Unauthorized")

    @app.get("/api/chat/study/log")
    async def study_log(request: Request):
        _auth(request)
        return JSONResponse(load_log()[-200:])

    @app.post("/api/chat/study/clear")
    async def study_clear(request: Request):
        _auth(request)
        save_log([])
        return {"ok": True}

    @app.post("/api/chat/study/apply")
    async def study_apply(request: Request):
        """Gloria's y on one of his proposals. Only the allowlist can move."""
        _auth(request)
        body = await request.json()
        ok, msg = apply_change(str(body.get("setting", "")), str(body.get("value", "")))
        log = load_log()
        log.append({"role": "system", "content": ("Gloria approved: " if ok else "Not applied: ") + msg,
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        save_log(log)
        return {"ok": ok, "message": msg}

    @app.post("/api/chat/study")
    async def study_chat(request: Request):
        _auth(request)
        body = await request.json()
        message = str(body.get("message", "")).strip()
        if not message:
            raise HTTPException(status_code=400, detail="no message")
        import model_router as _mr
        log = load_log()
        convo = [{"role": e["role"], "content": e["content"]} for e in log[-40:] if e.get("role") in ("user", "assistant")]
        convo.append({"role": "user", "content": message})
        params = {"temperature": 0.85, "top_p": 0.95, "max_tokens": 2000}
        reply, reasoning, used = await _mr.route_reply("study", system_prompt(), convo, params,
                                                       endpoint, headers, grok_model, reason=True)
        reply = TAG_RE.sub("", reply or "").strip()
        proposals = [{"setting": m.group(1).lower(), "value": m.group(2).strip(), "why": m.group(3).strip()}
                     for m in PROPOSE_RE.finditer(reply) if m.group(1).lower() in STUDY_PERMISSIONS]
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        log.append({"role": "user", "content": message, "at": now})
        log.append({"role": "assistant", "content": reply, "at": now, "model": used})
        save_log(log)
        return {"reply": reply, "model": used, "proposals": proposals}
