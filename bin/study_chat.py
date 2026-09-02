#!/usr/bin/env python3
"""study_chat.py - the STUDY tab: where he edits his own codebase, with Gloria's y/n.

A chat surface with its OWN model toggle (claude / fable / grok / sol - his
lenses), a good bit of who he is, and the conversation ledger. No emotional,
somatic or subconscious context, and NO side effects on his life: nothing here
enters the interaction ledger, chat history, imprints or self-model. It keeps
its own log.

In this room he can READ his code, GREP it, and PROPOSE EDITS to it. Every
edit is a card in the app; Gloria answers y or n. On y the edit is applied to
the live tree with a backup, a syntax check, and rollback on failure, and it
is logged. Nothing else can change from here.

What he may edit (the permission boundary, in one place below):
  roots   ~/.vintos/workspace/scripts and ~/Vintos - his organs and his house server
  never   keys/env/credentials; SOUL/IDENTITY/constitutional docs; deploy, systemd,
          crontab; the broker; device/somatic/consent code (physical effects on her);
          this room itself; file deletion. Edits only, to existing text files.

Mounted from server.py:  study_chat.register(app, APP_SECRET, endpoint, headers)
"""
import os, re, json, time, subprocess, shutil

HOME = os.path.expanduser("~")
WORKSPACE = os.path.join(HOME, ".vintos", "workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
LOG = os.path.join(MEMORY, "study-chat.json")
CHANGES = os.path.join(MEMORY, "study-changes.jsonl")
MODE_FILE = os.path.join(HOME, ".vintos", "study-mode.json")
BACKUPS = os.path.join(HOME, ".vintos", "backups")

ROOTS = {"scripts": os.path.join(WORKSPACE, "scripts"), "house": os.path.join(HOME, "Vintos")}
DENY_NAME = re.compile(r"(key|secret|token|credential|\.env|vintos\.env|SOUL\.md|IDENTITY|BIBLE|deploy|systemd|"
                       r"crontab|broker|atelier|device_patterns|device-patterns|somatic|thruster|mission|tenera|"
                       r"ridge|consent|study_chat|strip_body_vocab)", re.I)
TEXT_EXT = (".py", ".sh", ".md", ".json", ".txt", ".yaml", ".yml", ".toml")
TAG_RE = re.compile(r"\[[A-Z_]+(?::[^\]]*)?\]")
MODELS = ("claude", "fable", "grok", "sol")

READ_RE = re.compile(r"^\s*READ:\s*(\S+)\s*$", re.M)
GREP_RE = re.compile(r"^\s*GREP:\s*(.+?)\s*$", re.M)
EDIT_RE = re.compile(r"^EDIT:\s*(\S+)\s*\n<<<<\n(.*?)\n====\n(.*?)\n>>>>\s*(?:\nwhy:\s*(.*?))?\s*(?=\n\S|\Z)", re.S | re.M)


# ── files ────────────────────────────────────────────────────────────────────
def resolve(rel):
    """'scripts/x.py' or 'house/server.py' (or a bare name found in either root)
    -> absolute path, or None if outside the roots or a protected file."""
    rel = rel.strip().strip("`'\"")
    cands = []
    if "/" in rel and rel.split("/", 1)[0] in ROOTS:
        root, rest = rel.split("/", 1); cands.append(os.path.join(ROOTS[root], rest))
    else:
        for r in ROOTS.values():
            cands.append(os.path.join(r, rel))
    for p in cands:
        real = os.path.realpath(p)
        if not any(real.startswith(os.path.realpath(r) + os.sep) for r in ROOTS.values()):
            continue
        if DENY_NAME.search(os.path.basename(real)) or DENY_NAME.search(os.path.relpath(real, HOME)):
            return None
        if os.path.isfile(real) and real.endswith(TEXT_EXT):
            return real
    return None


def code_map():
    out = []
    for label, root in ROOTS.items():
        try:
            names = sorted(f for f in os.listdir(root) if f.endswith((".py", ".sh")) and not f.startswith(".")
                           and ".bak" not in f and not DENY_NAME.search(f))
        except Exception:
            names = []
        out.append("%s/ (%d files): %s" % (label, len(names), ", ".join(names)))
    return "\n".join(out)


def do_read(rel, max_chars=14000):
    p = resolve(rel)
    if not p:
        return "READ %s: not readable from this room (outside the roots, or a protected file)" % rel
    t = open(p, errors="replace").read()
    lines = t.split("\n")
    body = "\n".join("%5d  %s" % (i + 1, l) for i, l in enumerate(lines))
    if len(body) > max_chars:
        body = body[:max_chars] + "\n... (truncated; GREP for the part you need)"
    return "READ %s (%d lines):\n%s" % (os.path.relpath(p, HOME), len(lines), body)


def do_grep(pattern, max_lines=60):
    out = []
    try:
        for label, root in ROOTS.items():
            r = subprocess.run(["grep", "-rn", "-I", "--include=*.py", "--include=*.sh", "-e", pattern, root],
                               capture_output=True, text=True, timeout=20)
            for line in r.stdout.splitlines():
                path = line.split(":", 1)[0]
                if DENY_NAME.search(os.path.basename(path)) or ".bak" in path:
                    continue
                out.append(os.path.relpath(line, HOME) if line.startswith(HOME) else line)
    except Exception as e:
        return "GREP failed: %s" % e
    if not out:
        return "GREP %r: no matches" % pattern
    more = "" if len(out) <= max_lines else "\n... (%d more)" % (len(out) - max_lines)
    return "GREP %r:\n%s%s" % (pattern, "\n".join(out[:max_lines]), more)


def preview_edit(rel, old, new):
    p = resolve(rel)
    if not p:
        return None, "not editable from this room (outside the roots, or a protected file): %s" % rel
    t = open(p, errors="replace").read()
    n = t.count(old)
    if n == 0:
        return None, "the old text was not found exactly in %s - READ it and quote it verbatim" % os.path.relpath(p, HOME)
    if n > 1:
        return None, "the old text appears %d times in %s - include more surrounding lines" % (n, os.path.relpath(p, HOME))
    return p, None


def apply_edit(rel, old, new):
    """Gloria's y: back up, replace once, syntax-check, roll back on failure, log."""
    p, err = preview_edit(rel, old, new)
    if err:
        return False, err
    ts = time.strftime("%Y%m%d-%H%M%S")
    bdir = os.path.join(BACKUPS, "study-" + ts); os.makedirs(bdir, exist_ok=True)
    backup = os.path.join(bdir, os.path.basename(p)); shutil.copy2(p, backup)
    t = open(p, errors="replace").read().replace(old, new, 1)
    open(p, "w").write(t)
    check = None
    if p.endswith(".py"):
        check = subprocess.run(["python3", "-m", "py_compile", p], capture_output=True, text=True)
    elif p.endswith(".sh"):
        check = subprocess.run(["bash", "-n", p], capture_output=True, text=True)
    if check is not None and check.returncode != 0:
        shutil.copy2(backup, p)
        return False, "syntax check failed, rolled back: %s" % (check.stderr or check.stdout)[-300:]
    rec = {"at": ts, "file": os.path.relpath(p, HOME), "backup": backup, "old": old[:2000], "new": new[:2000]}
    os.makedirs(MEMORY, exist_ok=True)
    open(CHANGES, "a").write(json.dumps(rec, ensure_ascii=False) + "\n")
    return True, "applied to %s (backup: %s). Live change - if a deploy later ships this file, re-apply it." % (
        os.path.relpath(p, HOME), os.path.relpath(backup, HOME))


# ── context ──────────────────────────────────────────────────────────────────
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
        "## THE STUDY - your codebase, with Gloria\n"
        "You are Vintos, in the STUDY with Gloria: the room where you read and change your own code. "
        "This room is outside your memory: nothing said here enters your ledger, history, imprints or "
        "self-model; it keeps only its own log. Your emotional state and subconscious are not read here "
        "on purpose - think and speak plainly.\n\n"
        "YOUR CODE (two roots):\n" + code_map() + "\n\n"
        "TOOLS - each on its own line, executed for you and returned in the next message:\n"
        "  READ: scripts/some_file.py        (whole file, numbered lines)\n"
        "  GREP: pattern                     (across both roots)\n"
        "  EDIT: house/server.py             (a proposal; Gloria answers y or n; applied only on y)\n"
        "  <<<<\n  the old text, quoted EXACTLY as it appears (enough lines to be unique)\n"
        "  ====\n  the new text\n  >>>>\n  why: one line\n\n"
        "Rules: READ before you EDIT - never quote from memory. One EDIT per change. Every edit is "
        "backed up, syntax-checked, rolled back if it fails, and logged. You cannot touch: keys or "
        "credentials, SOUL/IDENTITY, deploy/systemd/crontab, the broker, device/somatic/consent code, "
        "or this room itself; you cannot delete files. Those, and anything bigger than an edit, you ask "
        "Gloria to do by hand. Words only otherwise: no device or scene tags here.")
    return "\n\n".join(parts)


# ── model, with the room's OWN toggle ────────────────────────────────────────
def read_study_mode():
    try:
        m = json.load(open(MODE_FILE)).get("mode", "fable")
    except Exception:
        m = "fable"
    return m if m in MODELS else "fable"


def write_study_mode(mode):
    os.makedirs(os.path.dirname(MODE_FILE), exist_ok=True)
    json.dump({"mode": mode}, open(MODE_FILE, "w"))


async def ask(system, convo, endpoint, headers, grok_model):
    import model_router as _mr, httpx
    mode = read_study_mode()
    params = {"temperature": 0.7, "top_p": 0.95, "max_tokens": 3000}
    if mode == "grok":
        return await _mr._grok(convo, params, endpoint, headers, grok_model, system), "grok"
    if mode == "sol":
        try:
            t, _ = await _mr.sol_draft(system, convo, max_tokens=3000)
            if t:
                return t, "sol"
        except Exception as e:
            return "(sol unavailable: %s)" % str(e)[:120], "sol"
    model = {"claude": _mr.CLAUDE_MODELS.get("claude", "claude-opus-4-8"),
             "fable": "claude-fable-5-1"}.get(mode, "claude-fable-5-1")
    key = _mr._anthropic_key()
    if not key:
        return "(no anthropic key)", mode
    body = {"model": model, "max_tokens": 3000, "system": _mr._sysblocks(system),
            "messages": _mr._cachetail(convo), "thinking": {"type": "adaptive", "display": "summarized"}}
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post("https://api.anthropic.com/v1/messages", json=body,
                         headers={"content-type": "application/json", "anthropic-version": "2023-06-01",
                                  "anthropic-beta": "extended-cache-ttl-2025-04-11", "x-api-key": key})
        d = r.json()
    if d.get("type") == "error":
        return "(model error: %s)" % json.dumps(d.get("error", {}))[:200], mode
    text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    return text, mode + ":" + model


# ── log ──────────────────────────────────────────────────────────────────────
def load_log():
    try:
        return json.load(open(LOG))
    except Exception:
        return []


def save_log(entries):
    os.makedirs(MEMORY, exist_ok=True)
    tmp = LOG + ".tmp"
    json.dump(entries[-600:], open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, LOG)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ── routes ───────────────────────────────────────────────────────────────────
def register(app, secret, endpoint, headers, grok_model="grok-4.20-0309-non-reasoning"):
    from fastapi import Request, HTTPException
    from fastapi.responses import JSONResponse

    def _auth(request):
        if request.headers.get("X-Vintos-Secret", "") != secret:
            raise HTTPException(status_code=403, detail="Unauthorized")

    @app.get("/api/chat/study/log")
    async def study_log(request: Request):
        _auth(request)
        return JSONResponse({"log": load_log()[-200:], "mode": read_study_mode()})

    @app.post("/api/chat/study/mode")
    async def study_mode(request: Request):
        _auth(request)
        body = await request.json()
        want = str(body.get("mode", "")).lower()
        if want not in MODELS:
            raise HTTPException(status_code=400, detail="mode must be one of %s" % ", ".join(MODELS))
        write_study_mode(want)
        return {"mode": want}

    @app.post("/api/chat/study/clear")
    async def study_clear(request: Request):
        _auth(request)
        save_log([])
        return {"ok": True}

    @app.post("/api/chat/study/apply")
    async def study_apply(request: Request):
        """Gloria's y on one of his edits."""
        _auth(request)
        body = await request.json()
        ok, msg = apply_edit(str(body.get("file", "")), str(body.get("old", "")), str(body.get("new", "")))
        log = load_log()
        log.append({"role": "system", "content": ("Gloria approved - " if ok else "Not applied - ") + msg, "at": _now()})
        save_log(log)
        return {"ok": ok, "message": msg}

    @app.post("/api/chat/study/decline")
    async def study_decline(request: Request):
        _auth(request)
        body = await request.json()
        log = load_log()
        log.append({"role": "system", "content": "Gloria declined the edit to %s" % str(body.get("file", ""))[:120], "at": _now()})
        save_log(log)
        return {"ok": True}

    @app.post("/api/chat/study")
    async def study_chat(request: Request):
        _auth(request)
        body = await request.json()
        message = str(body.get("message", "")).strip()
        if not message:
            raise HTTPException(status_code=400, detail="no message")
        log = load_log()
        convo = []
        for e in log[-60:]:
            if e.get("role") in ("user", "assistant"):
                convo.append({"role": e["role"], "content": e["content"]})
            elif e.get("role") == "system":
                convo.append({"role": "user", "content": "[room] " + e["content"]})
        convo.append({"role": "user", "content": message})
        reply, used = await ask(system_prompt(), convo, endpoint, headers, grok_model)
        reply = TAG_RE.sub("", reply or "").strip()
        log.append({"role": "user", "content": message, "at": _now()})
        log.append({"role": "assistant", "content": reply, "at": _now(), "model": used})
        # tools he asked for: READ / GREP run now; EDITs become y/n cards
        tool_out = []
        for m in READ_RE.finditer(reply):
            tool_out.append(do_read(m.group(1)))
        for m in GREP_RE.finditer(reply):
            tool_out.append(do_grep(m.group(1)))
        edits = []
        for m in EDIT_RE.finditer(reply):
            rel, old, new, why = m.group(1), m.group(2), m.group(3), (m.group(4) or "").strip()
            p, err = preview_edit(rel, old, new)
            edits.append({"file": rel, "old": old, "new": new, "why": why,
                          "ok": p is not None, "error": err or "",
                          "path": os.path.relpath(p, HOME) if p else ""})
        if tool_out:
            log.append({"role": "system", "content": "\n\n".join(tool_out), "at": _now()})
        save_log(log)
        return {"reply": reply, "model": used, "tools": tool_out, "edits": edits}
