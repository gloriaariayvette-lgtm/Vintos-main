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

CLI:  browser_winpy.py ensure | tabs | goto URL | elements | text | media | click N | type N TEXT | scroll PX | scrollto TEXT | back | dismiss | play | shot out.jpg
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
  // where a link goes decides what it is: a watch page is a video, /shorts/ a short, a channel a channel, a
  // playlist a playlist. YouTube's wrappers change every few months; destinations do not.
  const dest = h => { h = h || ''; if (/\/watch\?v=|vimeo\.com\/\d|dailymotion\.com\/video/.test(h)) return 'video';
    if (/\/shorts\//.test(h)) return 'short'; if (/youtube\.com\/(@|channel\/|c\/|user\/)/.test(h)) return 'channel';
    if (/youtube\.com\/playlist\?list=/.test(h)) return 'playlist'; return ''; };
  // a pop-up covering the page (newsletter, "send this recipe to yourself", cookie wall): the things inside it are
  // what can be clicked; the page behind is not reachable until it is closed
  let overlay = null;
  for (const d of document.querySelectorAll('[role="dialog"], [aria-modal="true"], dialog[open], [class*="modal" i], [id*="modal" i], [class*="popup" i], [class*="overlay" i], [class*="lightbox" i]')) {
    if (!vis(d)) continue; const r = d.getBoundingClientRect(); const s = getComputedStyle(d);
    if ((s.position === 'fixed' || s.position === 'absolute' || d.getAttribute('role') === 'dialog' || d.getAttribute('aria-modal') === 'true') && r.width * r.height > innerWidth * innerHeight * 0.08) {
      if (!overlay || parseInt(s.zIndex || 0) >= parseInt(getComputedStyle(overlay).zIndex || 0)) overlay = d;
    }
  }
  const out = []; const seen = new Set();
  const nodes = document.querySelectorAll('a[href], button, input, textarea, select, [role="button"], [role="link"], [role="textbox"], [contenteditable="true"]');
  const ordered = overlay ? [...overlay.querySelectorAll('a[href], button, input, textarea, select, [role="button"], [role="link"], [role="textbox"], [contenteditable="true"]'), ...nodes] : [...nodes];
  for (const e of ordered) {
    if (!vis(e)) continue;
    let tag = e.tagName.toLowerCase(); let kind = tag;
    let text = (e.innerText || e.value || e.getAttribute('aria-label') || e.getAttribute('placeholder') || e.title || e.alt || '').replace(/\s+/g, ' ').trim();
    const d = tag === 'a' ? dest(e.href) : '';
    if (d) {
      kind = d;
      const h = e.querySelector('h3, #video-title, [class*="title"]');
      if (h && (h.innerText || '').trim()) text = h.innerText.replace(/\s+/g, ' ').trim();
      if (!text) continue;
      const vkey = kind + '|' + e.href.replace(/[&#].*$/, '');
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
    out.push({kind, text: text.slice(0, 140), href: (e.href || '').slice(0, 200), x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), ontop: r.top >= 0 && r.bottom <= innerHeight, popup: !!(overlay && overlay.contains(e))});
    e.setAttribute('data-vintos-n', String(out.length - 1));
    if (out.length >= %d) break;
  }
  if (overlay) {
    const t = (overlay.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 160);
    out.push({kind: 'popup', text: t, href: '', x: 0, y: 0, ontop: true, popup: true, marker: true});   // appended: item numbers stay aligned with data-vintos-n
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

MEDIA_JS = """(()=>{const vs=[...document.querySelectorAll('video')]; if(!vs.length) return null;
  const score=v=>{const r=v.getBoundingClientRect(); const onscreen=r.width>50&&r.height>50&&r.bottom>0&&r.top<innerHeight;
    return (v.currentTime>0?1000:0)+(!v.paused&&!v.ended?100:0)+(v.readyState>=2?10:0)+(onscreen?1:0)+Math.min(v.currentTime,9)/10;};
  const v=vs.slice().sort((a,b)=>score(b)-score(a))[0];
  return {present:true, count:vs.length, paused:v.paused, ended:v.ended, currentTime:Math.round(v.currentTime*10)/10, duration:Math.round(v.duration||0), readyState:v.readyState, src:(v.currentSrc||'').slice(0,80)};})()"""

def media_state(c, sample=True):
    # the player actually on screen, not the first in the DOM (Shorts keeps several preloaded), and "playing" is a
    # clock that moves between two reads, not a flag that play was pressed (2026-09-06)
    m = c.eval(MEDIA_JS)
    if not m: return None
    if sample and not m.get("paused") and not m.get("ended"):
        t1 = m.get("currentTime", 0); time.sleep(1.2); m2 = c.eval(MEDIA_JS) or m
        m2["advancing"] = float(m2.get("currentTime", 0)) > float(t1); m2["currentTime"] = round(m2.get("currentTime", 0)); return m2
    m["advancing"] = False; m["currentTime"] = round(m.get("currentTime", 0)); return m

def signature(c):
    return c.eval("(()=>{const t=(document.body&&document.body.innerText||'').slice(0,4000); let h=0; for(const ch of t){h=(h*31+ch.charCodeAt(0))>>>0;} return location.href+'|'+document.title+'|'+h+'|'+Math.round(scrollY/200);})()")

def wait_change(c, before, secs):
    for _ in range(int(secs * 4)):
        time.sleep(0.25)
        try:
            if signature(c) != before: return True
        except Exception: pass
    return False

def wait_load(c, secs=15):
    for _ in range(int(secs * 4)):
        time.sleep(0.25)
        try:
            if c.eval("document.readyState") == "complete": break
        except Exception: pass
    time.sleep(0.8)

def mouse_click(c, x, y):
    c.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
    c.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
    c.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)

def settle_media(c, secs=6.0):
    # a watch page takes a few seconds to start; reading it at once says "not playing" and the model leaves a
    # good video (two of them, 2026-09-06). Wait for the clock to move, up to a bound.
    try:
        if not c.eval("/\\/watch\\?v=|\\/shorts\\//.test(location.href)"): return
    except Exception: return
    end = time.time() + secs
    while time.time() < end:
        m = c.eval(MEDIA_JS)
        if m and not m.get("paused") and float(m.get("currentTime", 0)) >= 1: return
        time.sleep(0.5)

def state(c, t, sample=True):
    info = c.eval("({url: location.href, title: document.title, scrollY: Math.round(scrollY), height: Math.round(document.documentElement.scrollHeight), inner: innerHeight})") or {}
    return {"tab": t["id"], "url": info.get("url"), "title": info.get("title"), "scrollY": info.get("scrollY"), "height": info.get("height"), "inner": info.get("inner"), "media": media_state(c, sample)}

if op == "ensure": print(json.dumps(ensure()))
elif op == "tabs": print(json.dumps([{"id": t["id"], "title": t.get("title"), "url": t.get("url")} for t in tabs()]))
elif op == "goto":
    def f(c, t):
        c.call("Page.navigate", url=req["url"]); wait_load(c); settle_media(c)
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
        # what is on screen now, and a map of the page's sections: the first N characters of the whole page said
        # "ingredients" while the reviews were on screen, and nobody could see it (2026-09-06)
        d = c.eval(r"""(()=>{
          const lim=%d; const vis=[]; let n=0;
          const w=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          while (w.nextNode() && n < lim) { const tn=w.currentNode; const s=(tn.nodeValue||'').replace(/\s+/g,' ').trim(); if(!s) continue;
            const p=tn.parentElement; if(!p) continue; const tag=p.tagName; if(tag==='SCRIPT'||tag==='STYLE'||tag==='NOSCRIPT') continue;
            const r=p.getBoundingClientRect(); if(r.bottom<0||r.top>innerHeight||r.width===0) continue;
            const cs=getComputedStyle(p); if(cs.visibility==='hidden'||cs.display==='none') continue;
            vis.push(s); n+=s.length+1; }
          const outline=[]; for (const h of document.querySelectorAll('h1,h2,h3,h4,[role="heading"]')) { const s=(h.innerText||'').replace(/\s+/g,' ').trim(); if(!s) continue;
            const r=h.getBoundingClientRect(); if(r.width===0&&r.height===0) continue;
            outline.push({text:s.slice(0,70), y:Math.round(r.top+scrollY), onscreen:r.bottom>0&&r.top<innerHeight}); if(outline.length>=40) break; }
          return {visible: vis.join('\n').slice(0, lim), outline};})()""" % int(req.get("max_text", 6000)))
        return {"state": state(c, t, sample=False), "text": d.get("visible", ""), "outline": d.get("outline", [])}
    print(json.dumps(with_tab(f)))
elif op == "scrollto":
    def f(c, t):
        q = req.get("text", "")
        hit = c.eval(r"""(q=>{q=q.toLowerCase(); const els=[...document.querySelectorAll('h1,h2,h3,h4,[role="heading"],section,[id],[aria-label]')];
          const label=e=>((e.innerText||'').slice(0,120)+' '+(e.id||'')+' '+(e.getAttribute('aria-label')||'')).toLowerCase();
          let e=els.find(x=>/^h[1-4]$/i.test(x.tagName)&&label(x).includes(q))||els.find(x=>label(x).includes(q));
          if(!e) return null; e.scrollIntoView({block:'start'}); window.scrollBy(0,-80); return (e.innerText||e.id||q).slice(0,80);})(%s)""" % json.dumps(q))
        if hit is None and q:
            hit = c.eval("window.find(%s) ? 'text match' : null" % json.dumps(q))
        time.sleep(0.6)
        return {"ok": hit is not None, "found": hit, "state": state(c, t, sample=False)}
    print(json.dumps(with_tab(f)))
elif op == "click":
    def f(c, t):
        n = int(req["n"])
        info = c.eval("(()=>{const e=document.querySelector('[data-vintos-n=\"%d\"]'); if(!e) return null; e.scrollIntoView({block:'center'}); const r=e.getBoundingClientRect(); return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2), href:(e.tagName==='A'&&/^https?:/.test(e.href))?e.href:''};})()" % n)
        if not info: return {"ok": False, "error": "element %d is gone; list elements again" % n}
        before = signature(c); how = "mouse"
        # what a person does: a real pointer click at the element; synthetic .click() is swallowed by half of
        # YouTube's components and lands on the wrong wrapper for the other half (a channel page, 2026-09-06)
        mouse_click(c, info["x"], info["y"])
        changed = wait_change(c, before, 4.0)
        if not changed and info.get("href"):
            c.call("Page.navigate", url=info["href"]); wait_load(c); how = "navigate"; changed = signature(c) != before
        elif not changed:
            c.eval("(()=>{const e=document.querySelector('[data-vintos-n=\"%d\"]'); if(e) e.click();})()" % n); how = "js"; changed = wait_change(c, before, 3.0)
        if changed: wait_load(c, 6); settle_media(c)
        return {"ok": True, "changed": changed, "how": how, "state": state(c, t)}
    print(json.dumps(with_tab(f)))
elif op == "dismiss":
    def f(c, t):
        before = signature(c)
        hit = c.eval(r"""(()=>{const rx=/^(close|dismiss|no thanks|no, thanks|not now|maybe later|reject|reject all|decline|skip|continue without|x|×|✕)$/i;
          const cands=[...document.querySelectorAll('button, [role="button"], a[href], [aria-label]')].filter(e=>{const r=e.getBoundingClientRect(); return r.width>4&&r.height>4&&r.bottom>0&&r.top<innerHeight;});
          const label=e=>((e.getAttribute('aria-label')||e.title||e.innerText||'').replace(/\s+/g,' ').trim());
          let b=cands.find(e=>rx.test(label(e)))||cands.find(e=>/close|dismiss/i.test(label(e))||/close|dismiss/i.test(e.className||''));
          if(!b) return null; const r=b.getBoundingClientRect(); return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2), label:label(b).slice(0,60)};})()""")
        how = "nothing found"
        if hit:
            mouse_click(c, hit["x"], hit["y"]); how = "clicked '%s'" % hit["label"]
            if not wait_change(c, before, 2.0): hit = None
        if not hit:
            for typ in ("keyDown", "keyUp"):
                c.call("Input.dispatchKeyEvent", type=typ, key="Escape", code="Escape", windowsVirtualKeyCode=27, nativeVirtualKeyCode=27)
            how += "; pressed Escape"; wait_change(c, before, 1.5)
        return {"ok": True, "how": how, "state": state(c, t)}
    print(json.dumps(with_tab(f)))
elif op == "back":
    def f(c, t):
        before = signature(c); c.eval("history.back()"); wait_change(c, before, 5.0); wait_load(c, 6); return {"ok": True, "state": state(c, t)}
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
        r = c.eval("(()=>{const vs=[...document.querySelectorAll('video')]; if(!vs.length) return 'no video'; const on=v=>{const r=v.getBoundingClientRect(); return r.width>50&&r.height>50&&r.bottom>0&&r.top<innerHeight;}; const v=vs.find(on)||vs[0]; v.muted=false; v.play().catch(()=>{}); return 'played';})()")
        m = media_state(c) if r != "no video" else None
        if m and not m.get("advancing"):
            # the site's own button, a real click, as a person would
            btn = c.eval("(()=>{const b=document.querySelector('.ytp-large-play-button, button.ytp-play-button, [aria-label=\"Play\"], [title=\"Play\"]'); if(!b) return null; const r=b.getBoundingClientRect(); return r.width>0?{x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2)}:null;})()")
            if btn: mouse_click(c, btn["x"], btn["y"]); r = "played via the page's play button"
        settle_media(c, 5.0); return {"ok": True, "result": r, "state": state(c, t)}
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
    def scrollto(self, text: str) -> Dict[str, Any]: return self._call("scrollto", text=str(text)[:80], timeout=20)
    def key(self, key: str) -> Dict[str, Any]: return self._call("key", key=key, timeout=20)
    def play(self) -> Dict[str, Any]: return self._call("play", timeout=25)
    def back(self) -> Dict[str, Any]: return self._call("back", timeout=30)
    def dismiss(self) -> Dict[str, Any]: return self._call("dismiss", timeout=20)
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
    elif cmd == "text":
        d = b.text(); print("SECTIONS:"); [print(f"  {o['y']:6d} {'ON SCREEN ' if o['onscreen'] else '          '}{o['text']}") for o in d.get("outline", [])]; print("VISIBLE:\n" + d["text"][:3000])
    elif cmd == "scrollto": print(json.dumps(b.scrollto(" ".join(a[1:])), indent=2))
    elif cmd == "media": print(json.dumps(b.state().get("media"), indent=2))
    elif cmd == "click": print(json.dumps(b.click(int(a[1])), indent=2))
    elif cmd == "type": print(json.dumps(b.type(int(a[1]), " ".join(a[2:]), enter=True), indent=2))
    elif cmd == "scroll": print(json.dumps(b.scroll(int(a[1]) if len(a) > 1 else 600), indent=2))
    elif cmd == "play": print(json.dumps(b.play(), indent=2))
    elif cmd == "back": print(json.dumps(b.back(), indent=2))
    elif cmd == "dismiss": print(json.dumps(b.dismiss(), indent=2))
    elif cmd == "shot": open(a[1], "wb").write(b.shot()); print("wrote", a[1])
    else: print(__doc__)
