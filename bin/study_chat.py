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
        "it reaches her. Be yourself; be plain; disagree when you disagree.")
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
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        log.append({"role": "user", "content": message, "at": now})
        log.append({"role": "assistant", "content": reply, "at": now, "model": used})
        save_log(log)
        return {"reply": reply, "model": used}
