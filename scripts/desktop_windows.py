#!/usr/bin/env python3
"""desktop_windows.py -- the Windows desktop, driven from WSL through PowerShell.

Aegis is Ubuntu under WSL2. The screen Gloria looks at is the Windows desktop, which no Linux X display can see
or touch: PyAutoGUI inside WSL captures, at best, the WSLg Linux desktop. WSL can, however, run Windows
executables directly, so this backend speaks to the desktop through powershell.exe:

    capture()  -> System.Drawing CopyFromScreen of the primary screen (DPI-aware), JPEG bytes back over stdout
    execute()  -> user32 SetCursorPos / mouse_event for the mouse, SendKeys for keys, the clipboard for text
    describe() -> desktop size, mouse position, foreground window title

Same interface as desktop_agent.PyAutoGUIBackend, so the Gemma loop does not know which side it is on.
Nothing here is persistent; every call is one PowerShell process. Screenshots go only to the local model.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import time
from typing import Any, Dict, Tuple

POWERSHELL = shutil.which("powershell.exe") or "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
KEY_RE = re.compile(r"^[a-z0-9_+\-]{1,24}$", re.I)

# PyAutoGUI key names -> SendKeys tokens. Letters and digits pass through.
SENDKEYS = {
    "enter": "{ENTER}", "return": "{ENTER}", "tab": "{TAB}", "esc": "{ESC}", "escape": "{ESC}",
    "backspace": "{BACKSPACE}", "delete": "{DELETE}", "del": "{DELETE}", "space": " ",
    "up": "{UP}", "down": "{DOWN}", "left": "{LEFT}", "right": "{RIGHT}",
    "home": "{HOME}", "end": "{END}", "pageup": "{PGUP}", "pagedown": "{PGDN}", "insert": "{INSERT}",
    "capslock": "{CAPSLOCK}", "numlock": "{NUMLOCK}", "printscreen": "{PRTSC}", "scrolllock": "{SCROLLLOCK}",
    **{f"f{i}": f"{{F{i}}}" for i in range(1, 17)},
}
MODIFIERS = {"ctrl": "^", "control": "^", "alt": "%", "shift": "+"}
SENDKEYS_ESCAPE = set("+^%~(){}[]")

_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System; using System.Runtime.InteropServices; using System.Text;
public static class U32 {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint data, UIntPtr extra);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
}
"@
[void][U32]::SetProcessDPIAware()
"""


def _run(script: str, timeout: float = 20.0) -> str:
    """Run a PowerShell script (prelude + body) and return stdout. Raises on a non-zero exit."""
    full = _PRELUDE + "\n" + script
    encoded = base64.b64encode(full.encode("utf-16-le")).decode("ascii")
    proc = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                          capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip() or proc.stdout.decode("utf-8", "replace").strip()
        raise RuntimeError("powershell: " + err[:400])
    return proc.stdout.decode("utf-8", "replace")


def available() -> bool:
    """True when this is WSL with a reachable powershell.exe."""
    try:
        if "microsoft" not in open("/proc/version").read().lower():
            return False
    except Exception:
        return False
    return os.path.exists(POWERSHELL) or shutil.which("powershell.exe") is not None


def sendkeys_sequence(keys) -> str:
    """['ctrl','l'] -> '^l' ; ['enter'] -> '{ENTER}' ; ['alt','f4'] -> '%{F4}'."""
    mods, rest, n_keys = "", "", 0
    for k in keys:
        k = str(k).lower()
        if not KEY_RE.fullmatch(k):
            raise ValueError("invalid key " + repr(k))
        if k in MODIFIERS:
            mods += MODIFIERS[k]
        elif k in SENDKEYS:
            rest += SENDKEYS[k]; n_keys += 1
        elif len(k) == 1:
            rest += ("{" + k + "}") if k in SENDKEYS_ESCAPE else k; n_keys += 1
        elif k in ("win", "winleft", "super"):
            raise ValueError("the Windows key is not sendable through SendKeys; use a hotkey the app itself has")
        else:
            raise ValueError("unknown key " + repr(k))
    if not rest:
        raise ValueError("a hotkey needs a non-modifier key")
    return mods + ("(" + rest + ")" if n_keys > 1 and mods else rest)   # one token like {F4} needs no group


class WindowsBackend:
    def __init__(self, max_image_width: int = 1600):
        if not available():
            raise RuntimeError("not WSL, or powershell.exe not reachable")
        self.max_image_width = max(640, int(max_image_width))
        self._size: Tuple[int, int] = (0, 0)

    # ---------------------------------------------------------------- observe
    def describe(self) -> Dict[str, Any]:
        out = _run(r"""
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$p = New-Object U32+POINT; [void][U32]::GetCursorPos([ref]$p)
$sb = New-Object System.Text.StringBuilder 512; [void][U32]::GetWindowText([U32]::GetForegroundWindow(), $sb, 512)
@{ w = $b.Width; h = $b.Height; mx = $p.X; my = $p.Y; title = $sb.ToString() } | ConvertTo-Json -Compress
""")
        d = json.loads(out.strip().splitlines()[-1])
        self._size = (int(d["w"]), int(d["h"]))
        return {"desktop_size": [int(d["w"]), int(d["h"])], "mouse": [int(d["mx"]), int(d["my"])],
                "active_window": str(d.get("title", ""))[:200], "display": "windows"}

    def capture(self) -> Tuple[bytes, Tuple[int, int], Tuple[int, int]]:
        out = _run(rf"""
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); $g.Dispose()
$maxw = {self.max_image_width}
if ($bmp.Width -gt $maxw) {{
  $h = [int][Math]::Round($bmp.Height * $maxw / $bmp.Width)
  $small = New-Object System.Drawing.Bitmap $bmp, $maxw, $h; $bmp.Dispose(); $bmp = $small
}}
$codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object {{ $_.MimeType -eq 'image/jpeg' }}
$ep = New-Object System.Drawing.Imaging.EncoderParameters 1
$ep.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter ([System.Drawing.Imaging.Encoder]::Quality, [long]82)
$ms = New-Object System.IO.MemoryStream; $bmp.Save($ms, $codec, $ep)
Write-Output ("{{0}} {{1}} {{2}} {{3}} " -f $b.Width, $b.Height, $bmp.Width, $bmp.Height)
Write-Output ([Convert]::ToBase64String($ms.ToArray()))
$bmp.Dispose(); $ms.Dispose()
""", timeout=30.0)
        lines = [l for l in out.splitlines() if l.strip()]
        dw, dh, iw, ih = (int(x) for x in lines[0].split()[:4])
        self._size = (dw, dh)
        return base64.b64decode("".join(lines[1:])), (iw, ih), (dw, dh)

    # ---------------------------------------------------------------- act
    def _scaled(self, action: Dict[str, Any], image_size: Tuple[int, int], xkey: str, ykey: str) -> Tuple[int, int]:
        iw, ih = image_size
        dw, dh = self._size if self._size != (0, 0) else image_size
        x = float(action[xkey]); y = float(action[ykey])
        if not (0 <= x < iw and 0 <= y < ih):
            raise ValueError("coordinates outside screenshot")
        return round(x * dw / iw), round(y * dh / ih)

    @staticmethod
    def _mouse(x: int, y: int, clicks: str = "") -> str:
        # mouse_event flags: 0x0002 left down, 0x0004 left up, 0x0008 right down, 0x0010 right up, 0x0800 wheel
        return f"[void][U32]::SetCursorPos({x},{y}); Start-Sleep -Milliseconds 60\n" + clicks

    LEFT = "[U32]::mouse_event(0x0002,0,0,0,[UIntPtr]::Zero); [U32]::mouse_event(0x0004,0,0,0,[UIntPtr]::Zero)\n"
    RIGHT = "[U32]::mouse_event(0x0008,0,0,0,[UIntPtr]::Zero); [U32]::mouse_event(0x0010,0,0,0,[UIntPtr]::Zero)\n"

    def execute(self, action: Dict[str, Any], image_size: Tuple[int, int]) -> str:
        kind = action["action"]
        if self._size == (0, 0):
            self.describe()
        if kind in ("move", "click", "double_click", "right_click"):
            x, y = self._scaled(action, image_size, "x", "y")
            clicks = {"move": "", "click": self.LEFT, "double_click": self.LEFT + "Start-Sleep -Milliseconds 90\n" + self.LEFT,
                      "right_click": self.RIGHT}[kind]
            _run(self._mouse(x, y, clicks))
            return f"{kind} at desktop ({x},{y})"
        if kind == "drag":
            x1, y1 = self._scaled(action, image_size, "x", "y")
            x2, y2 = self._scaled(action, image_size, "to_x", "to_y")
            steps = 12
            path = "\n".join(f"[void][U32]::SetCursorPos({round(x1 + (x2 - x1) * i / steps)},{round(y1 + (y2 - y1) * i / steps)}); Start-Sleep -Milliseconds 30"
                             for i in range(1, steps + 1))
            _run(f"[void][U32]::SetCursorPos({x1},{y1}); Start-Sleep -Milliseconds 80\n[U32]::mouse_event(0x0002,0,0,0,[UIntPtr]::Zero)\n{path}\n[U32]::mouse_event(0x0004,0,0,0,[UIntPtr]::Zero)")
            return f"drag ({x1},{y1}) to ({x2},{y2})"
        if kind == "scroll":
            amount = max(-12, min(12, int(action.get("amount", 0))))
            _run(f"[U32]::mouse_event(0x0800,0,0,[uint32]({amount * 120} -band 0xFFFFFFFF),[UIntPtr]::Zero)")
            return f"scroll {amount}"
        if kind == "type":
            text = str(action.get("text", ""))[:4000]
            if not text:
                raise ValueError("empty text")
            b64 = base64.b64encode(text.encode("utf-16-le")).decode("ascii")
            _run(f"""
$prev = $null; try {{ $prev = Get-Clipboard -Raw }} catch {{}}
$t = [System.Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{b64}'))
Set-Clipboard -Value $t
[System.Windows.Forms.SendKeys]::SendWait('^v'); Start-Sleep -Milliseconds 150
if ($null -ne $prev) {{ Set-Clipboard -Value $prev }}
""")
            return f"typed {len(text)} characters"
        if kind == "press":
            seq = sendkeys_sequence([str(action.get("key", "")).lower()])
            _run(f"[System.Windows.Forms.SendKeys]::SendWait('{seq}')")
            return f"pressed {action.get('key')}"
        if kind == "hotkey":
            keys = [str(k).lower() for k in action.get("keys", [])][:4]
            seq = sendkeys_sequence(keys)
            _run(f"[System.Windows.Forms.SendKeys]::SendWait('{seq}')")
            return "hotkey " + "+".join(keys)
        if kind == "wait":
            seconds = max(.1, min(5.0, float(action.get("seconds", 1))))
            time.sleep(seconds)
            return f"waited {seconds:g}s"
        raise ValueError("action is not executable: " + kind)
