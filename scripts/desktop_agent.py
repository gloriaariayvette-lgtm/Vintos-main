#!/usr/bin/env python3
"""Gemma 4 desktop agent for Vintos.

The old Velaris skill had reliable PyAutoGUI primitives but its "AI agent"
never sent a screenshot to a model.  This module supplies the missing loop:

    fresh screenshot -> one Gemma decision -> one bounded action -> repeat

It can run as a CLI and can register authenticated FastAPI start/stop/status
routes in Vintos's house server.  Screenshots stay in RAM and go only to the
configured local OpenAI-compatible endpoint.  The audit log stores hashes and
actions, never screenshots or model prose.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import dataclasses
import hashlib
import io
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol, Tuple
from urllib import request as urlrequest

sys.path.insert(0, str(Path(__file__).resolve().parent))


HOME = Path.home()
STATE_DIR = Path(os.environ.get("VINTOS_DESKTOP_STATE_DIR", HOME / ".vintos" / "desktop"))
STATE_FILE = STATE_DIR / "state.json"
STOP_FILE = STATE_DIR / "STOP"
LOCK_FILE = STATE_DIR / "agent.lock"
LOG_FILE = STATE_DIR / "events.jsonl"
GEMMA_API = os.environ.get("VINTOS_GEMMA_API", "http://172.18.16.1:1234/v1/chat/completions")
GEMMA_MODEL = os.environ.get("VINTOS_GEMMA_MODEL", "google/gemma-4-12b-qat")

ALLOWED_ACTIONS = {
    "move", "click", "double_click", "right_click", "drag", "scroll",
    "type", "press", "hotkey", "wait", "launch", "focus", "open_url", "done", "fail",
}
URL_RE = re.compile(r"^https?://[^\s\"'<>]{4,2000}$", re.I)
DEFAULT_MAX_STEPS = 60      # a video hunt is: open search, scroll, pick, wait for playback, verify - not 3 steps
HARD_MAX_STEPS = 150
# the window title each launched app shows, so launch can wait for it and give it the keyboard
WINDOW_TITLES = {"notepad": "Notepad", "calc": "Calculator", "mspaint": "Paint", "explorer": "File Explorer",
                 "msedge": "Edge", "chrome": "Chrome", "spotify": "Spotify", "ms-settings:": "Settings", "wt": "Terminal"}
# apps he may open by name, one step, instead of hunting taskbar icons a few pixels wide (2026-09-06)
LAUNCHABLE = {"notepad": "notepad", "calculator": "calc", "calc": "calc", "paint": "mspaint", "mspaint": "mspaint",
              "explorer": "explorer", "files": "explorer", "edge": "msedge", "browser": "msedge", "chrome": "chrome",
              "spotify": "spotify", "settings": "ms-settings:", "terminal": "wt", "wsl": "wt"}
KEY_RE = re.compile(r"^[a-z0-9_+\-]{1,24}$", re.I)


class DesktopBackend(Protocol):
    def capture(self) -> Tuple[bytes, Tuple[int, int], Tuple[int, int]]: ...
    def execute(self, action: Dict[str, Any], image_size: Tuple[int, int]) -> str: ...
    def describe(self) -> Dict[str, Any]: ...


def _atomic_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp." + str(os.getpid()))
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _state(**changes: Any) -> Dict[str, Any]:
    try:
        current = json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:
        current = {}
    current.update(changes)
    current["updated_at"] = time.time()
    _atomic_json(STATE_FILE, current)
    return current


def read_state() -> Dict[str, Any]:
    try:
        value = json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:
        return {"status": "idle"}
    pid = int(value.get("pid", 0) or 0)
    if value.get("status") in ("starting", "running") and pid:
        try:
            os.kill(pid, 0)
        except OSError:
            value["status"] = "stopped"
            value["reason"] = "process disappeared"
    return value


def _audit(event: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    event = {"at": time.time(), **event}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def _auditable_action(action: Dict[str, Any]) -> Dict[str, Any]:
    """Keep control evidence without copying typed content into the audit log."""
    safe = dict(action)
    if safe.get("action") == "type" and "text" in safe:
        raw = str(safe.pop("text"))
        safe["typed"] = {"chars": len(raw), "sha256": hashlib.sha256(raw.encode()).hexdigest()[:16]}
    return safe


def _stop_requested() -> bool:
    return STOP_FILE.exists()


def request_stop() -> Dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STOP_FILE.touch()
    current = read_state()
    if current.get("status") not in ("starting", "running", "stopping"):
        with contextlib.suppress(FileNotFoundError): STOP_FILE.unlink()
        return _state(status="idle", pid=0, reason="no desktop task was active")
    pid = int(current.get("pid", 0) or 0)
    _state(status="stopping", reason="stop requested")
    # SIGINT makes a blocking local-model request return promptly on the usual
    # Python stack.  The STOP file remains the durable authority if it does not.
    if pid and pid != os.getpid():
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGINT)
    return read_state()


class PyAutoGUIBackend:
    def __init__(self, max_image_width: int = 1600):
        if os.environ.get("VINTOS_DESKTOP_DISPLAY") and not os.environ.get("DISPLAY"):
            os.environ["DISPLAY"] = os.environ["VINTOS_DESKTOP_DISPLAY"]
        if not os.environ.get("DISPLAY"):
            sockets = sorted(Path("/tmp/.X11-unix").glob("X*"))
            if sockets: os.environ["DISPLAY"] = ":" + sockets[0].name[1:]
        if not os.environ.get("XAUTHORITY") and (HOME / ".Xauthority").exists():
            os.environ["XAUTHORITY"] = str(HOME / ".Xauthority")
        import pyautogui  # intentionally lazy: status/stop work headlessly
        self.pg = pyautogui
        self.pg.FAILSAFE = True
        self.pg.PAUSE = 0.08
        self.max_image_width = max(640, int(max_image_width))

    def describe(self) -> Dict[str, Any]:
        size = self.pg.size()
        pos = self.pg.position()
        title = ""
        with contextlib.suppress(Exception):
            title = self.pg.getActiveWindowTitle() or ""
        return {"desktop_size": [size.width, size.height], "mouse": [pos.x, pos.y],
                "active_window": title[:200], "display": os.environ.get("DISPLAY", "")}

    def capture(self) -> Tuple[bytes, Tuple[int, int], Tuple[int, int]]:
        image = self.pg.screenshot()
        desktop_size = tuple(map(int, self.pg.size()))
        if image.width > self.max_image_width:
            height = max(1, round(image.height * self.max_image_width / image.width))
            image = image.resize((self.max_image_width, height))
        out = io.BytesIO()
        image.convert("RGB").save(out, format="JPEG", quality=82, optimize=True)
        return out.getvalue(), (image.width, image.height), desktop_size

    @staticmethod
    def _scaled(action: Dict[str, Any], image_size: Tuple[int, int],
                desktop_size: Tuple[int, int], xkey: str, ykey: str) -> Tuple[int, int]:
        iw, ih = image_size
        dw, dh = desktop_size
        x = float(action[xkey]); y = float(action[ykey])
        if not (0 <= x < iw and 0 <= y < ih):
            raise ValueError("coordinates outside screenshot")
        return round(x * dw / iw), round(y * dh / ih)

    def execute(self, action: Dict[str, Any], image_size: Tuple[int, int]) -> str:
        kind = action["action"]
        desktop_size = tuple(map(int, self.pg.size()))
        if kind in ("move", "click", "double_click", "right_click"):
            x, y = self._scaled(action, image_size, desktop_size, "x", "y")
            if kind == "move": self.pg.moveTo(x, y, duration=min(float(action.get("duration", .25)), 2.0))
            elif kind == "click": self.pg.click(x, y)
            elif kind == "double_click": self.pg.doubleClick(x, y, interval=.12)
            else: self.pg.rightClick(x, y)
            return f"{kind} at desktop ({x},{y})"
        if kind == "drag":
            x1, y1 = self._scaled(action, image_size, desktop_size, "x", "y")
            x2, y2 = self._scaled(action, image_size, desktop_size, "to_x", "to_y")
            self.pg.moveTo(x1, y1, duration=.15)
            self.pg.dragTo(x2, y2, duration=min(float(action.get("duration", .6)), 3.0), button="left")
            return f"drag ({x1},{y1}) to ({x2},{y2})"
        if kind == "scroll":
            amount = max(-12, min(12, int(action.get("amount", 0))))
            if "x" in action and "y" in action:
                x, y = self._scaled(action, image_size, desktop_size, "x", "y"); self.pg.moveTo(x, y, duration=.1)
            self.pg.scroll(amount * 3)
            return f"scroll {amount}"
        if kind == "open_url":
            url = str(action.get("url", "")).strip()
            if not URL_RE.match(url): raise ValueError("open_url needs a full http(s) address")
            subprocess.Popen(["xdg-open", url], start_new_session=True); time.sleep(2.0)
            return f"opened {url[:80]}"
        if kind == "type":
            text = str(action.get("text", ""))[:4000]
            if not text: raise ValueError("empty text")
            try:
                import pyperclip
                previous = pyperclip.paste()
                pyperclip.copy(text)
                self.pg.hotkey("ctrl", "v")
                time.sleep(.1)
                pyperclip.copy(previous)
            except Exception:
                if not text.isascii():
                    raise RuntimeError("non-ASCII typing needs pyperclip")
                self.pg.write(text, interval=min(float(action.get("interval", .01)), .1))
            return f"typed {len(text)} characters"
        if kind == "press":
            key = str(action.get("key", "")).lower()
            if not KEY_RE.fullmatch(key): raise ValueError("invalid key")
            self.pg.press(key)
            return f"pressed {key}"
        if kind == "hotkey":
            keys = [str(k).lower() for k in action.get("keys", [])][:4]
            if not keys or not all(KEY_RE.fullmatch(k) for k in keys):
                raise ValueError("invalid hotkey")
            self.pg.hotkey(*keys)
            return "hotkey " + "+".join(keys)
        if kind == "wait":
            seconds = max(.1, min(8.0, float(action.get("seconds", 1))))
            time.sleep(seconds)
            return f"waited {seconds:g}s"
        if kind == "launch":
            app = LAUNCHABLE.get(str(action.get("app", "")).lower().strip())
            if not app: raise ValueError("app not in the launch list")
            subprocess.Popen([app], start_new_session=True)
            time.sleep(1.5)
            return f"launched {app}"
        if kind == "focus":
            title = str(action.get("title", ""))[:80]
            try:
                import pygetwindow as gw
                wins = [w for w in gw.getAllWindows() if w.title and title.lower() in w.title.lower()]
                if wins: wins[0].activate(); return f"focus {title}"
            except Exception:
                pass
            raise RuntimeError("no window titled like " + repr(title))
        raise ValueError("action is not executable: " + kind)


class GemmaPlanner:
    def __init__(self, endpoint: str = GEMMA_API, model: str = GEMMA_MODEL,
                 timeout: float = 60.0):
        self.endpoint, self.model, self.timeout = endpoint, model, timeout

    def __call__(self, task: str, screenshot: bytes, image_size: Tuple[int, int],
                 desktop: Dict[str, Any], step: int, last_result: str,
                 recent: list[Dict[str, Any]]) -> Dict[str, Any]:
        encoded = base64.b64encode(screenshot).decode("ascii")
        prompt = f"""You control this desktop for Vintos. Complete the task by looking at the fresh screenshot and choosing exactly ONE next action.

TASK: {task}
STEP: {step}
SCREENSHOT PIXELS: {image_size[0]} x {image_size[1]}
ACTIVE WINDOW TITLE: {desktop.get('active_window') or 'unknown'}   (a YouTube watch page is titled "<video title> - YouTube"; a results page is titled "<search> - YouTube")
DESKTOP: {json.dumps(desktop, ensure_ascii=False)}
LAST RESULT: {last_result or 'none'}
RECENT ACTIONS: {json.dumps(recent[-5:], ensure_ascii=False)}

First look at THIS screenshot and the window title and decide what state you are actually in - not what you expected after the last action. If the task's finishing condition is visible right now, return done immediately. Return one JSON object only (never two), with an "observed" field: one sentence of what the screen shows now. Coordinates are pixels in the screenshot you see, not percentages.
Allowed shapes:
{{"observed":"...","action":"click|double_click|right_click|move","x":123,"y":456,"reason":"..."}}
{{"action":"drag","x":1,"y":2,"to_x":3,"to_y":4,"duration":0.6,"reason":"..."}}
{{"action":"scroll","amount":-5,"x":800,"y":400,"reason":"..."}}   (negative = down; x,y optional: where to scroll)
{{"action":"open_url","url":"https://www.youtube.com/results?search_query=...","reason":"..."}}   (opens in the browser; the fastest way to reach a site or a search)
{{"action":"type","text":"exact text","reason":"..."}}
{{"action":"press","key":"enter","reason":"..."}}
{{"action":"hotkey","keys":["ctrl","l"],"reason":"..."}}
{{"action":"launch","app":"notepad","reason":"..."}}   (apps: {", ".join(sorted(set(LAUNCHABLE)))})
{{"action":"focus","title":"Calculator","reason":"..."}}   (bring a window to the front by its title before typing into it)
{{"action":"wait","seconds":3,"reason":"..."}}   (up to 8: after open_url, launch, or a click that loads a page, wait before deciding)
{{"action":"done","summary":"what visibly proves completion"}}
{{"action":"fail","reason":"why the task cannot be completed"}}

To open an application use launch, or press "win", type its name, press enter. To reach a website or a search, use open_url with the full address (a YouTube search is https://www.youtube.com/results?search_query=WORDS). Do not hunt for tiny taskbar icons. Keys go to the ACTIVE window only: check DESKTOP "active_window" before type/press/hotkey, and use focus (or click the window) when it is not the one you mean.
Long tasks: work in stages and keep going until the task itself is done - opening the site is not done, finding the thing is not done, the thing playing or posted or visible IS done. Scroll to see more when what you want is not on screen; read titles before clicking; click the thumbnail or title of the exact result you chose; after a page loads, wait, then look again. For a video, done means the player is visibly playing that video. If the same action did nothing twice, do something different.
Do not claim success unless it is verified: for anything visible, the current screenshot must show it. The mouse cursor is NOT drawn in screenshots - for cursor position use the DESKTOP "mouse" field (true desktop pixels) together with LAST RESULT. If the task is already done, return done now; do not repeat an action that already succeeded. Prefer visible UI and shortcuts over guessing coordinates. After every action you will receive a new screenshot. Never emit shell commands or multiple actions."""
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + encoded}},
                {"type": "text", "text": prompt},
            ]}],
            "temperature": 0.1,
            "max_tokens": 300,
        }).encode("utf-8")
        req = urlrequest.Request(self.endpoint, data=body, headers={"Content-Type": "application/json"})
        with urlrequest.urlopen(req, timeout=self.timeout) as response:
            payload = json.loads(response.read())
        raw = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        return parse_action(raw)


class GemmaVerifier:
    """A second, narrower question to the same model: does THIS screenshot show what was claimed? Yes or no."""
    def __init__(self, endpoint: str = GEMMA_API, model: str = GEMMA_MODEL, timeout: float = 60.0):
        self.endpoint, self.model, self.timeout = endpoint, model, timeout

    def __call__(self, task: str, claim: str, screenshot: bytes, image_size: Tuple[int, int]) -> Tuple[bool, str]:
        encoded = base64.b64encode(screenshot).decode("ascii")
        prompt = (f"TASK: {task}\nCLAIM: {claim}\n\nLook only at this screenshot. Does it visibly show that the claim is true "
                  "and the task is complete? Any error message, wrong value, or missing result means NO. "
                  'Answer with one JSON object only: {"verified": true|false, "seen": "what the screenshot actually shows, one sentence"}')
        body = json.dumps({"model": self.model, "temperature": 0.0, "max_tokens": 120,
                           "messages": [{"role": "user", "content": [
                               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + encoded}},
                               {"type": "text", "text": prompt}]}]}).encode("utf-8")
        req = urlrequest.Request(self.endpoint, data=body, headers={"Content-Type": "application/json"})
        try:
            with urlrequest.urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read())
            raw = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            m = re.search(r"\{.*\}", raw, flags=re.S)
            d = json.loads(m.group(0)) if m else {}
            return bool(d.get("verified")), str(d.get("seen", raw))[:200]
        except Exception as exc:
            return False, "verifier unavailable: " + str(exc)[:120]


def parse_action(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    value = None
    try:
        value = json.loads(text)
    except Exception:
        # take the FIRST complete object; Gemma sometimes appends a second one (2026-09-06: "Extra data")
        start = text.find("{")
        dec = json.JSONDecoder()
        while start != -1 and value is None:
            try:
                value, _end = dec.raw_decode(text[start:])
            except Exception:
                start = text.find("{", start + 1)
        if value is None: raise ValueError("Gemma returned no JSON object")
    if isinstance(value, list) and value and isinstance(value[0], dict): value = value[0]
    if not isinstance(value, dict) or value.get("action") not in ALLOWED_ACTIONS:
        raise ValueError("Gemma returned an unsupported action")
    return value


@dataclasses.dataclass
class RunResult:
    status: str
    reason: str
    steps: int
    gemma_calls: int
    job_id: str


def run_loop(task: str, backend: DesktopBackend, planner: Callable[..., Dict[str, Any]],
             max_steps: int = DEFAULT_MAX_STEPS, interval: float = .25, dry_run: bool = False,
             should_stop: Callable[[], bool] = _stop_requested,
             job_id: Optional[str] = None,
             progress: Optional[Callable[[int, int], None]] = None,
             verifier: Optional[Callable[..., Tuple[bool, str]]] = None) -> RunResult:
    job_id = job_id or uuid.uuid4().hex[:12]
    recent: list[Dict[str, Any]] = []
    last_result = ""
    last_action_sig = ""
    repeated = 0
    calls = 0
    sigs: list[str] = []            # every action signature, for A-B-A-B cycle detection
    screens: list[str] = []         # every screenshot hash, to tell Gemma when it is back where it was
    planner_errors = 0
    for step in range(1, max_steps + 1):
        if should_stop(): return RunResult("stopped", "stop requested", step - 1, calls, job_id)
        shot, image_size, _desktop_size = backend.capture()
        digest = hashlib.sha256(shot).hexdigest()[:16]
        if digest in screens[:-1]:
            last_result = (last_result + " | NOTE: this screen is one you were on before (step %d); your last action brought you back rather than forward."
                           % (screens.index(digest) + 1))
        screens.append(digest)
        if should_stop(): return RunResult("stopped", "stop requested", step - 1, calls, job_id)
        # every fourth step from the third on, ask the narrower question outright: is the task already done?
        # (the cat video played and the loop never knew - Gemma kept "seeing" the results page, 2026-09-06)
        if verifier is not None and not dry_run and step >= 3 and (step - 3) % 4 == 0:
            calls += 1
            try:
                ok, why = verifier(task, "the task as stated is complete", shot, image_size)
            except Exception as exc:
                ok, why = False, str(exc)[:120]
            _audit({"job_id": job_id, "step": step, "screen": digest, "check": {"complete": bool(ok), "why": str(why)[:200]}})
            if ok:
                return RunResult("completed", "completion check: " + str(why)[:300], step, calls, job_id)
        try:
            action = planner(task, shot, image_size, backend.describe(), step, last_result, recent)
            planner_errors = 0
        except Exception as exc:
            planner_errors += 1
            calls += 1
            _audit({"job_id": job_id, "step": step, "screen": digest, "planner_error": str(exc)[:200]})
            if planner_errors >= 3:
                return RunResult("failed", "the model answered unusably three times running: " + str(exc)[:200], step, calls, job_id)
            last_result = "PLANNER ERROR: your last answer was not one valid JSON action (%s). Answer with exactly one JSON object." % str(exc)[:120]
            continue
        calls += 1
        if progress: progress(step, calls)
        if should_stop(): return RunResult("stopped", "stop requested", step - 1, calls, job_id)
        kind = action["action"]
        _audit({"job_id": job_id, "step": step, "screen": digest,
                "action": _auditable_action(action)})
        if kind == "done":
            summary = str(action.get("summary", "done"))
            if verifier is not None and not dry_run:
                # Gemma claimed 19 was showing while Calculator said Invalid input (2026-09-06): a claim of done is
                # checked against a fresh screenshot by a separate yes/no question before it is believed
                shot2, size2, _ = backend.capture()
                calls += 1
                ok, why = verifier(task, summary, shot2, size2)
                _audit({"job_id": job_id, "step": step, "screen": hashlib.sha256(shot2).hexdigest()[:16],
                        "verify": {"claimed": summary[:200], "confirmed": bool(ok), "why": str(why)[:200]}})
                if not ok:
                    last_result = "DONE REJECTED: a fresh look at the screen does not show it - " + str(why)[:200]
                    recent.append({"step": step, "action": action, "result": last_result})
                    last_action_sig = ""
                    continue
            return RunResult("completed", summary, step, calls, job_id)
        if kind == "fail": return RunResult("failed", str(action.get("reason", "Gemma stopped")), step, calls, job_id)
        if dry_run: return RunResult("dry_run", json.dumps(action, ensure_ascii=False), step, calls, job_id)
        sig = json.dumps({k: v for k, v in action.items() if k not in ("reason", "observed")},
                         sort_keys=True, ensure_ascii=False)
        repeated = repeated + 1 if sig == last_action_sig else 0
        if repeated >= (7 if kind == "scroll" else 3):   # eight identical scrolls is a page you should not be on; four identical anything else is a stall
            return RunResult("failed", "same action repeated %d times" % (repeated + 1), step, calls, job_id)
        last_action_sig = sig
        sigs.append(sig)
        # an A-B-A-B (or A-B-C-A-B-C) cycle is the same stall wearing two hats: clicks that flip between two windows
        for period in (2, 3):
            n = period * 3
            if len(sigs) >= n and kind != "scroll" and all(sigs[-1 - i] == sigs[-1 - i - period] for i in range(n - period)):
                return RunResult("failed", "cycling through the same %d actions three times" % period, step, calls, job_id)
        try:
            last_result = backend.execute(action, image_size)
        except Exception as exc:
            last_result = "ACTION ERROR: " + str(exc)[:240]
        recent.append({"step": step, "action": action, "result": last_result})
        if should_stop(): return RunResult("stopped", "stop requested", step, calls, job_id)
        time.sleep(max(0.0, min(interval, 2.0)))
        if kind in ("open_url", "launch", "click", "double_click", "press") and not dry_run:
            _settle(backend, should_stop)
    return RunResult("failed", f"maximum {max_steps} steps reached", max_steps, calls, job_id)


def _settle(backend: DesktopBackend, should_stop: Callable[[], bool], max_wait: float = 6.0, quiet: float = 0.9) -> None:
    """After an action that may load something, wait until two captures in a row match (the page stopped
    changing) or max_wait passes. Costs no Gemma calls; saves the decision that would have been made on a
    half-drawn page."""
    t0 = time.time(); last = None
    while time.time() - t0 < max_wait:
        if should_stop(): return
        try:
            shot, _i, _d = backend.capture()
        except Exception:
            return
        h = hashlib.sha256(shot).hexdigest()
        if h == last: return
        last = h
        time.sleep(quiet)


@contextlib.contextmanager
def _exclusive_run():
    import fcntl
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("a desktop task is already running")
        yield


def pick_backend() -> DesktopBackend:
    """Aegis is WSL: the desktop Gloria sees is Windows, which no Linux display can reach. When powershell.exe
    is reachable the Windows backend drives it; otherwise the PyAutoGUI backend (a real Linux session)."""
    if os.environ.get("VINTOS_DESKTOP_BACKEND", "").lower() == "pyautogui":
        return PyAutoGUIBackend()
    forced = os.environ.get("VINTOS_DESKTOP_BACKEND", "").lower()
    try:   # first choice: Windows Python + PyAutoGUI (Defender treats it as an ordinary program)
        import desktop_winpy
        if forced in ("", "winpy") and desktop_winpy.available():
            return desktop_winpy.WindowsPythonBackend()
    except Exception:
        pass
    try:   # second: PowerShell (Defender blocked its user32 declarations on Aegis, 2026-09-06; kept for hosts where it passes)
        import desktop_windows
        if forced in ("", "powershell") and desktop_windows.available():
            return desktop_windows.WindowsBackend()
    except Exception:
        pass
    return PyAutoGUIBackend()


def run_task(task: str, max_steps: int = DEFAULT_MAX_STEPS, interval: float = .25,
             dry_run: bool = False, job_id: Optional[str] = None) -> RunResult:
    job_id = job_id or uuid.uuid4().hex[:12]
    with _exclusive_run():
        # A directly-invoked run clears an old stop. A server-spawned child
        # must preserve a stop that arrived during its startup window.
        if os.environ.get("VINTOS_DESKTOP_CHILD") != "1":
            with contextlib.suppress(FileNotFoundError): STOP_FILE.unlink()
        _state(status="running", pid=os.getpid(), job_id=job_id, task=task,
               step=0, started_at=time.time(), reason="")
        try:
            use_browser = False
            if not dry_run and os.environ.get("VINTOS_DESKTOP_MODE", "").lower() != "pixels":
                try:
                    import browser_agent, browser_winpy
                    use_browser = browser_agent.looks_like_web(task) and browser_winpy.available()
                except Exception:
                    use_browser = False
            if use_browser:
                # a task about the web is driven by the page's structure, not by pixels (2026-09-06)
                _state(mode="browser")
                result = browser_agent.run_task(task, max_steps, job_id=job_id)
            else:
                _state(mode="pixels")
                result = run_loop(task, pick_backend(), GemmaPlanner(), max_steps,
                                  interval, dry_run, job_id=job_id,
                                  progress=lambda step, calls: _state(step=step, gemma_calls=calls),
                                  verifier=GemmaVerifier())
        except KeyboardInterrupt:
            result = RunResult("stopped", "interrupted", 0, 0, job_id)
        except Exception as exc:
            result = RunResult("failed", str(exc)[:500], 0, 0, job_id)
        _state(status=result.status, reason=result.reason, steps=result.steps,
               gemma_calls=result.gemma_calls, finished_at=time.time(), pid=0)
        _audit({"job_id": job_id, "status": result.status, "reason": result.reason,
                "steps": result.steps, "gemma_calls": result.gemma_calls})
        return result


def start_task(task: str, max_steps: int = DEFAULT_MAX_STEPS) -> Dict[str, Any]:
    current = read_state()
    if current.get("status") in ("starting", "running", "stopping"):
        return {"accepted": False, "reason": "a desktop task is already active", "state": current}
    task = task.strip()[:2000]
    if not task: return {"accepted": False, "reason": "task is empty", "state": current}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileNotFoundError): STOP_FILE.unlink()
    job_id = uuid.uuid4().hex[:12]
    _state(status="starting", pid=0, job_id=job_id, task=task, started_at=time.time())
    log = open(STATE_DIR / "runner.log", "ab", buffering=0)
    child_env = os.environ.copy(); child_env["VINTOS_DESKTOP_CHILD"] = "1"
    try:
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "run", "--task", task,
                                 "--max-steps", str(max_steps), "--job-id", job_id],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, close_fds=True, env=child_env)
    except Exception as exc:
        log.close()
        failed = _state(status="failed", pid=0, reason="runner launch failed: " + str(exc)[:300])
        return {"accepted": False, "job_id": job_id, "reason": failed["reason"], "state": failed}
    log.close()
    # Do not overwrite "running" if the child won the startup race.
    current = read_state()
    if current.get("job_id") != job_id or current.get("status") == "starting":
        _state(status="starting", pid=proc.pid)
    deadline = time.time() + 1.0
    while time.time() < deadline:
        current = read_state()
        if current.get("job_id") == job_id and current.get("status") != "starting": break
        time.sleep(.05)
    accepted = current.get("status") in ("starting", "running", "completed", "dry_run")
    return {"accepted": accepted, "job_id": job_id, "pid": proc.pid,
            "reason": "" if accepted else current.get("reason", "desktop runner failed to start"),
            "state": current}


TAG_RE = re.compile(r"\[DESKTOP:\s*([^\]]+)\]", re.I)


def extract_and_start(reply: str, channel: str) -> str:
    """Start the last desktop task in a model reply and remove all tags."""
    tasks = [m.group(1).strip() for m in TAG_RE.finditer(reply or "") if m.group(1).strip()]
    if tasks:
        outcome = ({"accepted": True, "state": request_stop()}
                   if tasks[-1].strip().lower() in ("stop", "cancel", "abort")
                   else start_task(tasks[-1]))
        _audit({"source": channel, "tag": True, "accepted": outcome.get("accepted"),
                "job_id": outcome.get("job_id", ""), "reason": outcome.get("reason", "")})
        clean = TAG_RE.sub("", reply or "").strip()
        if not outcome.get("accepted"):
            clean += "\n\n[Desktop control did not start: %s]" % outcome.get("reason", "unknown error")
        return clean
    return reply or ""


def register(app: Any, secret: str) -> None:
    from fastapi import HTTPException, Request

    def auth(request: Any) -> None:
        if request.headers.get("X-Vintos-Secret", "") != secret:
            raise HTTPException(status_code=403, detail="Unauthorized")

    @app.get("/api/desktop/status")
    async def desktop_status(request: Request):
        auth(request); return read_state()

    @app.post("/api/desktop/start")
    async def desktop_start(request: Request):
        auth(request); body = await request.json()
        return start_task(str(body.get("task", "")), max(1, min(HARD_MAX_STEPS, int(body.get("max_steps", DEFAULT_MAX_STEPS)))))

    @app.post("/api/desktop/stop")
    async def desktop_stop(request: Request):
        auth(request); return request_stop()


def doctor() -> Dict[str, Any]:
    out: Dict[str, Any] = {"gemma_api": GEMMA_API, "model": GEMMA_MODEL,
                           "display": os.environ.get("DISPLAY", "")}
    try:
        backend = pick_backend()
        out["backend"] = type(backend).__name__
        shot, image, desktop = backend.capture()
        out.update({"ok": True, "image_size": image, "desktop_size": desktop,
                    "screenshot_bytes": len(shot), **backend.describe()})
        action = GemmaPlanner()("Inspection only: look at the current screen, take no action, and return fail.",
                                shot, image, backend.describe(), 1, "doctor: do not act", [])
        out.update({"gemma_ok": True, "gemma_action": action.get("action")})
        try:
            import browser_winpy
            out["browser"] = "ready (websocket-client present)" if browser_winpy.available() else "missing: python.exe -m pip install --user websocket-client"
        except Exception as _bx:
            out["browser"] = "unavailable: " + str(_bx)[:80]
    except Exception as exc:
        out.update({"ok": False, "gemma_ok": False, "error": str(exc)})
        try:
            import desktop_winpy
            py = desktop_winpy.find_python()
            out["windows_python"] = py or "not found on PATH from WSL"
            if py and not desktop_winpy.available():
                out["hint"] = "install on the Windows side once: %s -m pip install --user pyautogui pillow pyperclip pygetwindow" % os.path.basename(py)
        except Exception:
            pass
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Vintos Gemma 4 desktop agent")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--task", required=True)
    run.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    run.add_argument("--interval", type=float, default=.25)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--job-id")
    sub.add_parser("status"); sub.add_parser("stop"); sub.add_parser("doctor")
    args = parser.parse_args()
    if args.command == "run":
        result = run_task(args.task, max(1, min(args.max_steps, HARD_MAX_STEPS)), args.interval,
                          args.dry_run, args.job_id)
        print(json.dumps(dataclasses.asdict(result), ensure_ascii=False))
        return 0 if result.status in ("completed", "dry_run", "stopped") else 1
    if args.command == "status": print(json.dumps(read_state(), indent=2)); return 0
    if args.command == "stop": print(json.dumps(request_stop(), indent=2)); return 0
    if args.command == "doctor":
        result = doctor(); print(json.dumps(result, indent=2)); return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
