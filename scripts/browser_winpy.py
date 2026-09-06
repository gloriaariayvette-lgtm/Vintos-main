#!/usr/bin/env python3
"""browser_winpy.py -- his browser, driven by structure instead of pixels.

Pixel clicking with a 12B vision model on a 3440-wide screen shrunk to 1600 was fragile: the cat video played
and the loop never knew; then it found the results and forgot to click one (2026-09-06). A browser has a
better door: the DevTools protocol. Through it we read the page's text and its clickable things with their
labels, click by label, type into fields by label, read the <video> element's playing state, and take an
exact screenshot of the tab. Gemma chooses among TEXT candidates; nothing is guessed from a picture.

Edge runs on Windows with its own profile for him (his tabs, his history, no interference with Gloria's):
    msedge --remote-debugging-port=9222 --user-data-dir=%LOCALAPPDATA%\\VintosEdge
DevTools binds to localhost on Windows, so the client runs there too: a Windows Python helper (stdlib urllib
for /json, websocket-client for the socket), started from WSL exactly the way desktop_winpy does it.
Needs, once on the Windows side:  python.exe -m pip install --user websocket-client

CLI:  browser_winpy.py ensure | tabs | goto URL | elements | text | media | click N | type N TEXT | scroll PX | shot out.jpg
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import desktop_winpy  # find_python()

PORT = int(os.environ.get("VINTOS_EDGE_PORT", "9222"))
MAX_ELEMENTS = 80
MAX_TEXT = 6000

# runs under Windows Python; talks to Edge on localhost
_HELPER = r'''
import sys, json, os, time, subprocess, urllib.request, base64
req = json.loads(sys.stdin.read()); op = req["op"]; port = int(req.get("port", 9222))
BASE = "http://127.0.0.1:%d" % port

def jget(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r: return json.loads(r.read())

def alive():
    try: jget("/json/version"); return True
    except Exception: return False

def ensure():
    if alive(): return {"ok": True, "launched": False}
    prof = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "VintosEdge")
    cands = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
             os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\Edge\Application\msedge.exe")]
    exe = next((c for c in cands if os.path.exists(c)), "msedge")
    # sync off and first-run off: Edge's sync-confirmation pop-up came back as the first "page", goto navigated it,
    # and Edge dropped the port (2026-09-06)
    subprocess.Popen([exe, "--remote-debugging-port=%d" % port, "--user-data-dir=" + prof, "--no-first-run", "--no-default-browser-check",
                      "--disable-sync", "--disable-features=msSyncConfirmation,msEdgeSignInOnFirstRun,msImplicitSignin",
                      "--remote-allow-origins=*", "--new-window", "about:blank"], close_fds=True)
    for _ in range(40):
        time.sleep(0.25)
        if alive(): return {"ok": True, "launched": True, "profile": prof}
    return {"ok": False, "error": "Edge did not open its debugging port"}

def is_web(t):
    u = (t.get("url") or "").lower()
    return t.get("type") == "page" and not u.startswith(("edge://", "chrome://", "devtools://", "chrome-extension://", "extension://"))

def tabs():
    return [t for t in jget("/json") if is_web(t)]

def new_tab():
    return json.loads(urllib.request.urlopen(urllib.request.Request(BASE + "/json/new?about:blank", method="PUT"), timeout=5).read())

def pick_tab(tid=None):
    # only real web tabs: Edge's own dialogs and settings pages are "page" type too, and navigating one kills the session
    ts = tabs()
    if tid:
        for t in ts:
            if t["id"] == tid: return t
    return ts[0] if ts else new_tab()

class CDP:
    def __init__(self, ws_url):
        import websocket
        self.ws = websocket.create_connection(ws_url, timeout=20, suppress_origin=True); self.n = 0
    def call(self, method, **params):
        self.n += 1; self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.n:
                if "error" in m: raise RuntimeError(m["error"].get("message", "cdp error"))
                return m.get("result", {})
    def eval(self, js):
        r = self.call("Runtime.evaluate", expression=js, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r: raise RuntimeError(str(r["exceptionDetails"].get("text", "js error")))
        return r.get("result", {}).get("value")
    def close(self):
        try: self.ws.close()
        except Exception: pass

ELEMENTS_JS = r"""
(() => {
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none' && r.bottom > 0 && r.top < innerHeight * 3; };
  const isWatch = h => /\/watch\?v=|\/shorts\/|\/video\/|vimeo\.com\/\d|dailymotion\.com\/video/.test(h || '');
  const out = []; const seen = new Set();
  // YouTube keeps changing its result markup (ytd-video-renderer, then yt-lockup-view-model); a video is any link to
  // a watch page with a label, whatever it is wrapped in
  const nodes = document.querySelectorAll('a[href], button, input, textarea, select, [role="button"], [role="link"], [role="textbox"], [contenteditable="true"]');
  for (const e of nodes) {
    if (!vis(e)) continue;
    let tag = e.tagName.toLowerCase(); let kind = tag;
    let text = (e.innerText || e.value || e.getAttribute('aria-label') || e.getAttribute('placeholder') || e.title || e.alt || '').replace(/\s+/g, ' ').trim();
    if (tag === 'a' && isWatch(e.href)) {
      kind = 'video';
      const h = e.querySelector('h3, #video-title, [class*="title"]');
      if (h && (h.innerText || '').trim()) text = h.innerText.replace(/\s+/g, ' ').trim();
      if (!text) continue;
      const vkey = 'video|' + e.href.replace(/&.*$/, '');
      if (seen.has(vkey)) continue; seen.add(vkey);
    } else {
      if (!text && !['input','textarea'].includes(tag)) continue;
      const key = kind + '|' + text.slice(0, 80) + '|' + (e.href || '');
      if (seen.has(key)) continue; seen.add(key);
      if (tag === 'input' || tag === 'textarea' || e.getAttribute('role') === 'textbox' || e.getAttribute('contenteditable') === 'true') kind = 'field';
      else if (tag === 'button' || e.getAttribute('role') === 'button') kind = 'button';
      else if (tag === 'a' || e.getAttribute('role') === 'link') kind = 'link';
    }
    const r = e.getBoundingClientRect();
    out.push({kind, text: text.slice(0, 140), href: (e.href || '').slice(0, 200), x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), ontop: r.top >= 0 && r.bottom <= innerHeight});
    e.setAttribute('data-vintos-n', String(out.length - 1));
    if (out.length >= %d) break;
  }
  return out;
})()
""" % int(req.get("max_elements", 80))

def with_tab(fn):
    t = pick_tab(req.get("tab")); c = CDP(t["webSocketDebuggerUrl"])
    try:
        c.call("Page.enable"); c.call("Runtime.enable")
        # a background tab neither loads nor plays media: front and focused before anything is read or done
        try: c.call("Page.bringToFront"); c.call("Emulation.setFocusEmulationEnabled", enabled=True)
        except Exception: pass
        return fn(c, t)
    finally:
        c.close()

def state(c, t):
    info = c.eval("({url: location.href, title: document.title, scrollY: Math.round(scrollY), height: Math.round(document.documentElement.scrollHeight), inner: innerHeight})") or {}
    # the one that is actually playing, not the first in the DOM: YouTube Shorts keeps several preloaded players and
    # the first reports 0s of 0s forever (2026-09-06)
    media = c.eval("""(()=>{const vs=[...document.querySelectorAll('video')]; if(!vs.length) return null;
      const score=v=>{const r=v.getBoundingClientRect(); const onscreen=r.width>50&&r.height>50&&r.bottom>0&&r.top<innerHeight;
        return (v.currentTime>0?1000:0)+(!v.paused&&!v.ended?100:0)+(v.readyState>=2?10:0)+(onscreen?1:0)+Math.min(v.currentTime,9)/10;};
      const v=vs.slice().sort((a,b)=>score(b)-score(a))[0];
      return {present:true, count:vs.length, paused:v.paused, ended:v.ended, currentTime:Math.round(v.currentTime), duration:Math.round(v.duration||0), readyState:v.readyState, src:(v.currentSrc||'').slice(0,80)};})()""")
    return {"tab": t["id"], "url": info.get("url"), "title": info.get("title"), "scrollY": info.get("scrollY"), "height": info.get("height"), "inner": info.get("inner"), "media": media}

if op == "ensure": print(json.dumps(ensure()))
elif op == "tabs": print(json.dumps([{"id": t["id"], "title": t.get("title"), "url": t.get("url")} for t in tabs()]))
elif op == "goto":
    def f(c, t):
        c.call("Page.navigate", url=req["url"])
        for _ in range(60):
            time.sleep(0.25)
            if c.eval("document.readyState") == "complete": break
        time.sleep(0.8)
        return state(c, t)
    print(json.dumps(with_tab(f)))
elif op == "state": print(json.dumps(with_tab(state)))
elif op == "elements":
    def f(c, t):
        els = c.eval(ELEMENTS_JS) or []
        return {"state": state(c, t), "elements": els}
    print(json.dumps(with_tab(f)))
elif op == "text":
    def f(c, t):
        txt = c.eval("(document.body && document.body.innerText || '').replace(/\\n{3,}/g,'\\n\\n').slice(0, %d)" % int(req.get("max_text", 6000)))
        return {"state": state(c, t), "text": txt}
    print(json.dumps(with_tab(f)))
elif op == "click":
    def f(c, t):
        n = int(req["n"])
        ok = c.eval("(()=>{const e=document.querySelector('[data-vintos-n=\"%d\"]'); if(!e) return 'missing'; e.scrollIntoView({block:'center'}); e.click(); return 'clicked';})()" % n)
        if ok == "missing": return {"ok": False, "error": "element %d is gone; list elements again" % n}
        for _ in range(24):
            time.sleep(0.25)
            if c.eval("document.readyState") == "complete": break
        time.sleep(1.0)
        return {"ok": True, "state": state(c, t)}
    print(json.dumps(with_tab(f)))
elif op == "type":
    def f(c, t):
        n = int(req["n"]); text = req["text"]
        ok = c.eval("(()=>{const e=document.querySelector('[data-vintos-n=\"%d\"]'); if(!e) return 'missing'; e.scrollIntoView({block:'center'}); e.focus(); if(e.isContentEditable){e.textContent='';} else {e.value='';} return 'ok';})()" % n)
        if ok == "missing": return {"ok": False, "error": "field %d is gone; list elements again" % n}
        c.call("Input.insertText", text=text)
        if req.get("enter"):
            for typ in ("keyDown", "keyUp"):
                c.call("Input.dispatchKeyEvent", type=typ, key="Enter", code="Enter", windowsVirtualKeyCode=13, nativeVirtualKeyCode=13)
            time.sleep(1.5)
        return {"ok": True, "state": state(c, t)}
    print(json.dumps(with_tab(f)))
elif op == "scroll":
    def f(c, t):
        c.eval("window.scrollBy(0, %d)" % int(req.get("px", 600))); time.sleep(0.6); return {"ok": True, "state": state(c, t)}
    print(json.dumps(with_tab(f)))
elif op == "key":
    def f(c, t):
        k = req["key"]; codes = {"Enter": 13, "Escape": 27, "Tab": 9, "Space": 32, "k": 75, "f": 70}
        for typ in ("keyDown", "keyUp"):
            c.call("Input.dispatchKeyEvent", type=typ, key=k, code=k, windowsVirtualKeyCode=codes.get(k, 0), nativeVirtualKeyCode=codes.get(k, 0))
        time.sleep(0.6); return {"ok": True, "state": state(c, t)}
    print(json.dumps(with_tab(f)))
elif op == "play":
    def f(c, t):
        r = c.eval("(()=>{const vs=[...document.querySelectorAll('video')]; if(!vs.length) return 'no video'; const on=v=>{const r=v.getBoundingClientRect(); return r.width>50&&r.height>50&&r.bottom>0&&r.top<innerHeight;}; const v=vs.find(on)||vs[0]; v.muted=false; v.play(); return 'played';})()")
        time.sleep(1.5); return {"ok": True, "result": r, "state": state(c, t)}
    print(json.dumps(with_tab(f)))
elif op == "shot":
    def f(c, t):
        r = c.call("Page.captureScreenshot", format="jpeg", quality=80)
        return {"jpeg": r.get("data", ""), "state": state(c, t)}
    print(json.dumps(with_tab(f)))
elif op == "activate":
    t = pick_tab(req.get("tab")); urllib.request.urlopen(BASE + "/json/activate/" + t["id"], timeout=5).read(); print(json.dumps({"ok": True}))
else:
    raise ValueError("unknown op " + op)
'''


def available() -> bool:
    py = desktop_winpy.find_python()
    if not py:
        return False
    try:
        r = subprocess.run([py, "-c", "import websocket; print('ok')"], capture_output=True, timeout=25)
        return r.returncode == 0 and b"ok" in r.stdout
    except Exception:
        return False


def call(op: str, timeout: float = 60.0, _retry: bool = False, **kw) -> Dict[str, Any]:
    py = desktop_winpy.find_python()
    if not py:
        raise RuntimeError("no python.exe reachable from WSL")
    req = {"op": op, "port": PORT, "max_elements": MAX_ELEMENTS, "max_text": MAX_TEXT, **kw}
    proc = subprocess.run([py, "-c", _HELPER], input=json.dumps(req).encode("utf-8"), capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        last = (err[-1] if err else "failed")
        # Edge closed (or was never open): open it and try the same call once more
        if op != "ensure" and not _retry and ("10061" in last or "refused" in last.lower() or "not connect" in last.lower()):
            e = call("ensure", timeout=30)
            if e.get("ok"):
                return call(op, timeout=timeout, _retry=True, **kw)
        raise RuntimeError("browser helper: " + last[:300])
    lines = [l for l in proc.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
    return json.loads(lines[-1])


class EdgeBrowser:
    """The interface browser_agent drives. Every method returns plain data; nothing is guessed from pixels.

    One tab for the whole job: Edge lists tabs in a shifting order, and a driver that takes "the first tab" on every
    call read one tab and clicked another once three were open (2026-09-06)."""
    def __init__(self, tab: Optional[str] = None): self.tab = tab

    def _tab(self) -> Optional[str]:
        ts = call("tabs", timeout=15)
        ids = [t["id"] for t in ts]
        if self.tab not in ids:
            self.tab = ids[0] if ids else None
        return self.tab

    def _call(self, op: str, timeout: float = 60.0, **kw) -> Dict[str, Any]:
        d = call(op, timeout=timeout, tab=self._tab(), **kw)
        st = d.get("state") if isinstance(d, dict) else None
        if isinstance(st, dict) and st.get("tab"): self.tab = st["tab"]
        elif isinstance(d, dict) and d.get("tab"): self.tab = d["tab"]
        return d

    def ensure(self) -> Dict[str, Any]: return call("ensure", timeout=30)
    def goto(self, url: str) -> Dict[str, Any]: return self._call("goto", url=url)
    def state(self) -> Dict[str, Any]: return self._call("state", timeout=20)
    def elements(self) -> Dict[str, Any]: return self._call("elements")
    def text(self) -> Dict[str, Any]: return self._call("text")
    def click(self, n: int) -> Dict[str, Any]: return self._call("click", n=int(n))
    def type(self, n: int, text: str, enter: bool = False) -> Dict[str, Any]: return self._call("type", n=int(n), text=text, enter=bool(enter))
    def scroll(self, px: int) -> Dict[str, Any]: return self._call("scroll", px=int(px), timeout=20)
    def key(self, key: str) -> Dict[str, Any]: return self._call("key", key=key, timeout=20)
    def play(self) -> Dict[str, Any]: return self._call("play", timeout=20)
    def shot(self) -> bytes: return base64.b64decode(self._call("shot").get("jpeg", ""))
    def activate(self) -> Dict[str, Any]: return self._call("activate", timeout=10)


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else "state"
    b = EdgeBrowser()
    if cmd == "ensure": print(json.dumps(b.ensure(), indent=2))
    elif cmd == "tabs": print(json.dumps(call("tabs", timeout=15), indent=2))
    elif cmd == "goto": print(json.dumps(b.goto(a[1]), indent=2))
    elif cmd == "elements":
        d = b.elements(); print(json.dumps(d["state"], indent=2))
        for i, e in enumerate(d["elements"]): print(f"[{i}] {e['kind']:6s} {e['text'][:100]}")
    elif cmd == "text": print(b.text()["text"][:3000])
    elif cmd == "media": print(json.dumps(b.state().get("media"), indent=2))
    elif cmd == "click": print(json.dumps(b.click(int(a[1])), indent=2))
    elif cmd == "type": print(json.dumps(b.type(int(a[1]), " ".join(a[2:]), enter=True), indent=2))
    elif cmd == "scroll": print(json.dumps(b.scroll(int(a[1]) if len(a) > 1 else 600), indent=2))
    elif cmd == "play": print(json.dumps(b.play(), indent=2))
    elif cmd == "shot": open(a[1], "wb").write(b.shot()); print("wrote", a[1])
    else: print(__doc__)
