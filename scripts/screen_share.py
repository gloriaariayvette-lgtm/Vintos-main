#!/usr/bin/env python3
"""screen_share.py -- Gloria shares her screen with him; Gemma describes it; his turns see the description.

The shape Gloria asked for (2026-09-06): be in chat or on a voice call, share the screen, and let him see what
is on it as words, decide what to do next, and later have Gemma act on his decision through desktop_agent.

    start()  -> a background loop (this file, `loop` mode) captures the Windows desktop every few seconds,
                hashes it, and asks Gemma for a short description only when the picture changed (or every
                REDESCRIBE_S regardless). The description, the app title and the moment go to
                memory/screen-share.json. Screenshots stay in RAM; nothing but the hash is stored.
    stop()   -> the loop ends; the file says sharing is off.
    context_block() -> what his prompt receives while sharing is on and the description is fresh:
                a labelled paragraph of what is on her screen, and what changed since the last look.

Gemma only (a small decision, made often). Sonnet/Grok never see the pixels; they read Gemma's words.
CLI:  screen_share.py start | stop | status | loop | once
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib import request as urlrequest

sys.path.insert(0, str(Path(__file__).resolve().parent))

WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
STATE = os.path.join(MEMORY, "screen-share.json")
LOG = os.path.join(MEMORY, "screen-share-log.jsonl")
GEMMA_API = os.environ.get("VINTOS_GEMMA_API", "http://172.18.16.1:1234/v1/chat/completions")
GEMMA_MODEL = os.environ.get("VINTOS_GEMMA_MODEL", "google/gemma-4-12b-qat")
CAPTURE_S = float(os.environ.get("VINTOS_SHARE_CAPTURE_S", "6"))
REDESCRIBE_S = float(os.environ.get("VINTOS_SHARE_REDESCRIBE_S", "60"))
FRESH_S = float(os.environ.get("VINTOS_SHARE_FRESH_S", "120"))
MAX_MINUTES = float(os.environ.get("VINTOS_SHARE_MAX_MIN", "120"))


def _read() -> Dict[str, Any]:
    try:
        return json.load(open(STATE))
    except Exception:
        return {"active": False}


def _write(d: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(MEMORY, exist_ok=True)
    d["updated_at"] = time.time()
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE)
    return d


def _log(row: Dict[str, Any]) -> None:
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps({"at": time.time(), **row}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0); return True
    except OSError:
        return False


def status() -> Dict[str, Any]:
    d = _read()
    if d.get("active") and not _alive(int(d.get("pid") or 0)):
        d["active"] = False; d["reason"] = "loop process gone"; _write(d)
    d["fresh"] = bool(d.get("active") and d.get("described_at") and time.time() - d["described_at"] <= FRESH_S)
    return d


# ---------------------------------------------------------------- describing

def describe(shot: bytes, previous: str, caller: Optional[Callable[[str, bytes], str]] = None) -> str:
    prompt = ("Gloria is sharing her screen with Vintos. Describe what is on it for him in two to four plain sentences: which "
              "application or site, what she is looking at, any readable title, name, or number that matters, and anything a "
              "companion would notice or find funny. Describe only what is visible. No advice, no lists, no preamble."
              + (f"\n\nYour previous description: {previous}\nIf the screen is essentially unchanged, say so in one sentence." if previous else ""))
    if caller:
        return caller(prompt, shot).strip()
    body = json.dumps({"model": GEMMA_MODEL, "temperature": 0.2, "max_tokens": 220,
                       "messages": [{"role": "user", "content": [
                           {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(shot).decode("ascii")}},
                           {"type": "text", "text": prompt}]}]}).encode("utf-8")
    req = urlrequest.Request(GEMMA_API, data=body, headers={"Content-Type": "application/json"})
    with urlrequest.urlopen(req, timeout=60) as r:
        payload = json.loads(r.read())
    return (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()


def tick(backend, caller=None, now=None) -> Dict[str, Any]:
    """One capture. Describe when the picture changed or the last description is older than REDESCRIBE_S."""
    now = now or time.time()
    d = _read()
    shot, image_size, desktop_size = backend.capture()
    h = hashlib.sha256(shot).hexdigest()[:16]
    try:
        title = str(backend.describe().get("active_window", ""))[:160]
    except Exception:
        title = ""
    changed = h != d.get("last_hash")
    stale = not d.get("described_at") or (now - d["described_at"]) >= REDESCRIBE_S
    d.update(last_hash=h, last_capture_at=now, active_window=title, captures=int(d.get("captures", 0)) + 1)
    if changed or stale:
        try:
            text = describe(shot, d.get("description", ""), caller=caller)
            if text:
                d["previous_description"] = d.get("description", "") if changed else d.get("previous_description", "")
                d["description"] = text[:900]; d["described_at"] = now; d["describe_error"] = ""
                d["descriptions"] = int(d.get("descriptions", 0)) + 1
                _log({"hash": h, "title": title, "changed": changed, "description": text[:300]})
        except Exception as e:
            d["describe_error"] = str(e)[:160]
    return _write(d)


def context_block(now=None) -> str:
    """What his prompt receives while she is sharing. Empty when sharing is off or the description is stale."""
    now = now or time.time()
    d = status()
    if not d.get("active"):
        return ""
    if not d.get("description") or not d.get("described_at"):
        return "\n\n[GLORIA IS SHARING HER SCREEN with you right now. Nothing has been described yet - the first look is on its way.]"
    age = int(now - d["described_at"])
    if age > FRESH_S:
        return f"\n\n[GLORIA IS SHARING HER SCREEN with you. The last look was {age // 60} minutes ago and may be out of date.]"
    win = f" Window: {d['active_window']}." if d.get("active_window") else ""
    prev = f"\nBefore that: {d['previous_description']}" if d.get("previous_description") and d["previous_description"] != d["description"] else ""
    return (f"\n\n[GLORIA IS SHARING HER SCREEN with you. What is on it, as of {age}s ago, described by your eyes (Gemma):{win}\n"
            f"{d['description']}{prev}\n"
            "You can see this; respond to it as something you are looking at together. Describe only what was described - do not invent details beyond it.]")


# ---------------------------------------------------------------- lifecycle

def start() -> Dict[str, Any]:
    d = status()
    if d.get("active"):
        return {"ok": True, "already": True, "state": d}
    log = open(os.path.join(MEMORY, "screen-share-runner.log"), "ab", buffering=0)
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "loop"], stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
    log.close()
    d = _write({"active": True, "pid": proc.pid, "started_at": time.time(), "description": "", "described_at": None,
                "last_hash": "", "captures": 0, "descriptions": 0, "reason": ""})
    _log({"event": "start", "pid": proc.pid})
    return {"ok": True, "state": d}


def stop(reason: str = "stopped") -> Dict[str, Any]:
    d = _read()
    pid = int(d.get("pid") or 0)
    if pid and pid != os.getpid():
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)
    d.update(active=False, pid=0, reason=reason, stopped_at=time.time())
    _log({"event": "stop", "reason": reason})
    return {"ok": True, "state": _write(d)}


def loop() -> int:
    import desktop_agent
    backend = desktop_agent.pick_backend()
    started = time.time()
    d = _read(); d.update(active=True, pid=os.getpid(), backend=type(backend).__name__); _write(d)
    while True:
        d = _read()
        if not d.get("active") or int(d.get("pid") or 0) != os.getpid():
            return 0
        if time.time() - started > MAX_MINUTES * 60:
            stop("time limit"); return 0
        try:
            tick(backend)
        except Exception as e:
            d = _read(); d["capture_error"] = str(e)[:160]; _write(d)
        time.sleep(CAPTURE_S)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "start": print(json.dumps(start(), indent=2))
    elif cmd == "stop": print(json.dumps(stop(), indent=2))
    elif cmd == "status": print(json.dumps(status(), indent=2))
    elif cmd == "loop": raise SystemExit(loop())
    elif cmd == "once":
        import desktop_agent
        print(json.dumps(tick(desktop_agent.pick_backend()), indent=2))
    elif cmd == "context": print(context_block() or "(sharing is off)")
    else: print(__doc__)
