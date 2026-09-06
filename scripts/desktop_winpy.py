#!/usr/bin/env python3
"""desktop_winpy.py -- the Windows desktop, driven from WSL through Windows Python + PyAutoGUI.

Defender blocked the PowerShell route (an encoded script declaring user32 mouse and keyboard entry points is
what commodity automation malware looks like, 2026-09-06). Windows Python running PyAutoGUI is an ordinary
program to Defender, and WSL can start python.exe directly. Each call is one short python.exe process:

    capture()  -> pyautogui.screenshot() on the Windows side, resized, JPEG base64 over stdout
    execute()  -> the same PyAutoGUI primitives the Linux backend uses, on the real desktop
    describe() -> size, mouse, active window title

Needs, on the Windows side once:  python.exe -m pip install --user pyautogui pillow pyperclip pygetwindow
Same interface as desktop_agent.PyAutoGUIBackend. Screenshots go only to the local model.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from typing import Any, Dict, Tuple

_CANDIDATES = ("python.exe", "python3.exe", "py.exe")

_HELPER = r'''
import sys, json, base64, io
req = json.loads(sys.stdin.read())
import pyautogui
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.08
op = req["op"]
def size():
    s = pyautogui.size(); return [int(s.width), int(s.height)]
if op == "describe":
    p = pyautogui.position(); title = ""
    try:
        import pygetwindow as gw
        w = gw.getActiveWindow(); title = (w.title if w else "") or ""
    except Exception:
        pass
    print(json.dumps({"desktop_size": size(), "mouse": [int(p.x), int(p.y)], "active_window": title[:200], "display": "windows-python"}))
elif op == "capture":
    img = pyautogui.screenshot(); ds = size(); maxw = int(req.get("max_width", 1600))
    if img.width > maxw:
        img = img.resize((maxw, max(1, round(img.height * maxw / img.width))))
    out = io.BytesIO(); img.convert("RGB").save(out, format="JPEG", quality=82, optimize=True)
    print(json.dumps({"desktop_size": ds, "image_size": [img.width, img.height], "jpeg": base64.b64encode(out.getvalue()).decode("ascii")}))
elif op == "execute":
    a = req["action"]; kind = a["action"]; res = ""
    if kind == "move": pyautogui.moveTo(a["x"], a["y"], duration=min(float(a.get("duration", .25)), 2.0)); res = "move"
    elif kind == "click": pyautogui.click(a["x"], a["y"]); res = "click"
    elif kind == "double_click": pyautogui.doubleClick(a["x"], a["y"], interval=.12); res = "double_click"
    elif kind == "right_click": pyautogui.rightClick(a["x"], a["y"]); res = "right_click"
    elif kind == "drag":
        pyautogui.moveTo(a["x"], a["y"], duration=.15); pyautogui.dragTo(a["to_x"], a["to_y"], duration=min(float(a.get("duration", .6)), 3.0), button="left"); res = "drag"
    elif kind == "scroll": pyautogui.scroll(int(a["amount"])); res = "scroll"
    elif kind == "type":
        text = a["text"]
        # keystrokes for short plain text (a paste of "12+7" is Invalid input to Calculator; keys are what a
        # person does); the clipboard only for long or non-ASCII text
        if text.isascii() and len(text) <= 120:
            pyautogui.write(text, interval=.02)
        else:
            try:
                import pyperclip, time
                prev = pyperclip.paste(); pyperclip.copy(text); pyautogui.hotkey("ctrl", "v"); time.sleep(.1); pyperclip.copy(prev)
            except Exception:
                if not text.isascii(): raise
                pyautogui.write(text, interval=.01)
        res = "typed %d" % len(text)
    elif kind == "press": pyautogui.press(a["key"]); res = "pressed " + a["key"]
    elif kind == "hotkey": pyautogui.hotkey(*a["keys"]); res = "hotkey " + "+".join(a["keys"])
    elif kind in ("launch", "focus"):
        import subprocess, time
        title = a.get("title", "")
        if kind == "launch":
            subprocess.Popen("start \"\" " + a["app"], shell=True)
        # a window opened from a background process does not get the keyboard: wait for it and bring it to
        # the front, or every keystroke lands in whatever had focus (Gloria's terminal, 2026-09-06)
        focused = ""
        try:
            import pygetwindow as gw
            deadline = time.time() + (6.0 if kind == "launch" else 2.0)
            while time.time() < deadline and not focused:
                wins = [w for w in gw.getAllWindows() if w.title and title.lower() in w.title.lower()]
                if wins:
                    w = wins[0]
                    try:
                        if w.isMinimized: w.restore()
                        w.activate()
                    except Exception:
                        pass
                    time.sleep(0.4)
                    aw = gw.getActiveWindow()
                    if aw and title.lower() in (aw.title or "").lower(): focused = aw.title
                else:
                    time.sleep(0.3)
        except Exception:
            pass
        res = ("launched %s" % a["app"] if kind == "launch" else "focus %s" % title) + (", focused: " + focused if focused else ", NOT focused - click the window first")
    else: raise ValueError("unknown action " + kind)
    print(json.dumps({"ok": True, "result": res}))
else:
    raise ValueError("unknown op")
'''


def find_python() -> str:
    for c in _CANDIDATES:
        p = shutil.which(c)
        if p:
            return p
    import glob
    # not on PATH yet (a fresh install, a terminal opened before it): the usual homes, newest version first
    homes = glob.glob("/mnt/c/Users/*/AppData/Local/Programs/Python/Python3*/python.exe") + glob.glob("/mnt/c/Python3*/python.exe") \
        + glob.glob("/mnt/c/Users/*/AppData/Local/Microsoft/WindowsApps/python3*.exe") + ["/mnt/c/Windows/py.exe"]
    for p in sorted((h for h in homes if os.path.exists(h)), reverse=True):
        return p
    return ""


def available() -> bool:
    """WSL, a Windows python, and pyautogui importable there. Cached per process."""
    global _AVAILABLE
    try:
        return _AVAILABLE
    except NameError:
        pass
    _AVAILABLE = False
    try:
        if "microsoft" not in open("/proc/version").read().lower():
            return False
        py = find_python()
        if not py:
            return False
        r = subprocess.run([py, "-c", "import pyautogui, PIL; print('ok')"], capture_output=True, timeout=25)
        _AVAILABLE = r.returncode == 0 and b"ok" in r.stdout
    except Exception:
        _AVAILABLE = False
    return _AVAILABLE


def _call(req: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
    py = find_python()
    if not py:
        raise RuntimeError("no python.exe reachable from WSL")
    proc = subprocess.run([py, "-c", _HELPER], input=json.dumps(req).encode("utf-8"), capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError("windows python: " + (err[-1] if err else "failed")[:300])
    lines = [l for l in proc.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
    return json.loads(lines[-1])


class WindowsPythonBackend:
    def __init__(self, max_image_width: int = 1600):
        if not available():
            raise RuntimeError("Windows python with pyautogui not reachable")
        self.max_image_width = max(640, int(max_image_width))
        self._size: Tuple[int, int] = (0, 0)

    def describe(self) -> Dict[str, Any]:
        d = _call({"op": "describe"})
        self._size = tuple(d["desktop_size"])
        return d

    def capture(self) -> Tuple[bytes, Tuple[int, int], Tuple[int, int]]:
        d = _call({"op": "capture", "max_width": self.max_image_width}, timeout=40.0)
        self._size = tuple(d["desktop_size"])
        return base64.b64decode(d["jpeg"]), tuple(d["image_size"]), tuple(d["desktop_size"])

    def _scaled(self, action: Dict[str, Any], image_size: Tuple[int, int], xkey: str, ykey: str) -> Tuple[int, int]:
        iw, ih = image_size
        dw, dh = self._size if self._size != (0, 0) else image_size
        x = float(action[xkey]); y = float(action[ykey])
        if not (0 <= x < iw and 0 <= y < ih):
            raise ValueError("coordinates outside screenshot")
        return round(x * dw / iw), round(y * dh / ih)

    def execute(self, action: Dict[str, Any], image_size: Tuple[int, int]) -> str:
        import re, time
        kind = action["action"]
        if self._size == (0, 0):
            self.describe()
        a: Dict[str, Any] = {"action": kind}
        if kind in ("move", "click", "double_click", "right_click"):
            a["x"], a["y"] = self._scaled(action, image_size, "x", "y"); a["duration"] = action.get("duration", .25)
        elif kind == "drag":
            a["x"], a["y"] = self._scaled(action, image_size, "x", "y")
            a["to_x"], a["to_y"] = self._scaled(action, image_size, "to_x", "to_y"); a["duration"] = action.get("duration", .6)
        elif kind == "scroll":
            a["amount"] = max(-12, min(12, int(action.get("amount", 0))))
        elif kind == "type":
            a["text"] = str(action.get("text", ""))[:4000]
            if not a["text"]: raise ValueError("empty text")
        elif kind == "press":
            a["key"] = str(action.get("key", "")).lower()
            if not re.fullmatch(r"[a-z0-9_+\-]{1,24}", a["key"]): raise ValueError("invalid key")
        elif kind == "hotkey":
            a["keys"] = [str(k).lower() for k in action.get("keys", [])][:4]
            if not a["keys"] or not all(re.fullmatch(r"[a-z0-9_+\-]{1,24}", k) for k in a["keys"]): raise ValueError("invalid hotkey")
        elif kind == "wait":
            s = max(.1, min(5.0, float(action.get("seconds", 1)))); time.sleep(s); return f"waited {s:g}s"
        elif kind == "launch":
            import desktop_agent
            name = str(action.get("app", "")).lower().strip()
            app = desktop_agent.LAUNCHABLE.get(name)
            if not app: raise ValueError("app not in the launch list")
            a["app"] = app; a["title"] = desktop_agent.WINDOW_TITLES.get(app, name)
        elif kind == "focus":
            a["title"] = str(action.get("title", ""))[:80]
            if not a["title"].strip(): raise ValueError("focus needs a window title")
        else:
            raise ValueError("action is not executable: " + kind)
        d = _call({"op": "execute", "action": a}, timeout=30.0)
        where = f" at desktop ({a['x']},{a['y']})" if "x" in a else ""
        return str(d.get("result", kind)) + where
