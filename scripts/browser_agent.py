#!/usr/bin/env python3
"""browser_agent.py -- Gemma drives the browser by what is on the page, not by where pixels are.

Each step Gemma receives: the page's address and title, the video element's state, an excerpt of the page
text, and a numbered list of the clickable things with their labels. It answers with one action naming an
item number or a URL. "Playing" is read from the <video> element; "posted" or "visible" is checked against
the page text. Pixels are never guessed; a screenshot of the tab is only taken for the audit.

Same guards as the desktop loop: one task at a time, the stop file, repetition and cycle detection, a step
cap, a fresh completion check every few steps, hashed audit rows. Used by desktop_agent.run_task for tasks
that are about the web; the pixel loop keeps everything else.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib import request as urlrequest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import desktop_agent as DA

ACTIONS = {"goto", "click", "type", "scroll", "scrollto", "key", "play", "back", "dismiss", "wait", "done", "fail"}
WEB_HINT = re.compile(r"\b(youtube|browser|website|web ?site|web|search (for|the web)|video|review|url|https?://|google|recipe|reddit|wikipedia|tab|page|site|amazon|spotify web|open .{0,30}\.(com|org|net))\b", re.I)


def looks_like_web(task: str) -> bool:
    return bool(WEB_HINT.search(task or ""))


def page_type(url: str) -> str:
    """What kind of page this is, from its address: the one fact a small model most often loses track of."""
    u = (url or "").lower()
    if not u or u.startswith("about:"): return "blank page"
    if "youtube.com" in u:
        if "/results" in u: return "YouTube SEARCH RESULTS page (a list of videos; pick one)"
        if "/watch" in u: return "YouTube WATCH page (one video; this is where a video plays)"
        if "/shorts/" in u: return "YouTube SHORTS page (a vertical short clip; playing here also counts as a video)"
        if "/playlist" in u: return "YouTube PLAYLIST page"
        if re.search(r"youtube\.com/(@|channel/|c/|user/)", u): return "YouTube CHANNEL page (a creator's profile, NOT a video; go back if you wanted a video)"
        return "YouTube home/other page"
    if "google.com/search" in u: return "Google SEARCH RESULTS page"
    return "web page"


def _summary(st: Dict[str, Any], elements: List[Dict[str, Any]], text: str, outline: Optional[List[Dict[str, Any]]] = None) -> str:
    media = st.get("media")
    if media:
        playing = media.get("present") and not media.get("paused") and not media.get("ended")
        pos = int(media.get("currentTime", 0) or 0)
        # the same rule video_done applies: playing means the clock is moving, not just that play was pressed
        word = ("PLAYING, clock moving" if playing and media.get("advancing", pos >= 1) else "play pressed but the clock is not moving (use play; if that fails, back and pick another)" if playing
                else "present but paused (use play)" if media.get("present") else "none")
        m = f"VIDEO ELEMENT: {word} (position {pos}s of {media.get('duration', 0)}s)"
    else:
        m = "VIDEO ELEMENT: none on this page"
    lines = [f"URL: {st.get('url')}", f"PAGE TYPE: {page_type(st.get('url', ''))}", f"TITLE: {st.get('title')}", m,
             f"SCROLL: {st.get('scrollY', 0)} of {st.get('height', 0)} (viewport {st.get('inner', 0)})"]
    popup = next((e for e in elements if e.get("marker")), None)
    if popup:
        lines.append(f"POP-UP COVERING THE PAGE: \"{popup.get('text', '')[:120]}\" -- the page behind it cannot be used until it is closed. Use dismiss (or click its close/No Thanks item, marked [pop-up]) unless the task needs this pop-up.")
    lines += ["", "THINGS ON THE PAGE, in page order (number, kind, label):"]
    for i, e in enumerate(elements):
        flag = ("" if e.get("ontop", True) else " (below the fold)") + (" [pop-up]" if e.get("popup") and not e.get("marker") else "")
        lines.append(f"[{i}] {e.get('kind', '?')}: {e.get('text', '')[:110]}{flag}")
    if outline:
        lines += ["", "SECTIONS OF THIS PAGE (heading, position in px, whether on screen now):"]
        lines += [f"  {o.get('y', 0)}px {'ON SCREEN' if o.get('onscreen') else '         '}  {o.get('text', '')}" for o in outline[:40]]
    lines += ["", "TEXT VISIBLE ON SCREEN NOW:", (text or "")[:2500]]
    return "\n".join(lines)


class GemmaTextPlanner:
    def __init__(self, endpoint: str = DA.GEMMA_API, model: str = DA.GEMMA_MODEL, timeout: float = 60.0):
        self.endpoint, self.model, self.timeout = endpoint, model, timeout

    def __call__(self, task: str, summary: str, step: int, last_result: str, recent: List[Dict[str, Any]], notes: str = "") -> Dict[str, Any]:
        prompt = f"""You drive a web browser for Vintos, one step at a time. Think before you act.

TASK: {task}
STEP: {step}
YOUR NOTES FROM EARLIER STEPS: {notes or '(none yet)'}
LAST RESULT: {last_result or 'none'}
RECENT ACTIONS: {json.dumps(recent[-6:], ensure_ascii=False)}

WHAT THE PAGE IS NOW:
{summary}

How to think, in order:
1. Where am I? Read PAGE TYPE. Is this the kind of page the next part of the task needs? If you landed somewhere wrong (a channel page when you wanted a video, an ad, a login wall), the correct move is back, then a different choice. Never repeat a choice that led somewhere wrong.
2. What did my last action do? If LAST RESULT says NO CHANGE, that action does not work here: do something different (another item, scroll, back, a different kind of item).
3. What is the one action that makes progress now?

Rules: choose items by their NUMBER from the list; never invent numbers. Kinds: "video" opens a watch page, "short" a short clip, "channel" a creator's profile (not a video), "playlist" a list, "field" is typable, "button"/"link" are clickable, "popup" marks a pop-up covering the page. "First result" means the lowest-numbered item of the right kind. To search a site, use goto with the search URL (YouTube: https://www.youtube.com/results?search_query=WORDS ; Google: https://www.google.com/search?q=WORDS). To watch a video: click a "video" item; on the watch page, if VIDEO ELEMENT is not PLAYING, use play. If nothing suitable is listed, scroll (positive = down) and look again. To reach a section of the page, use scrollto with a word from its heading (the SECTIONS list shows what exists and what is on screen); "on screen" means that section's heading is in the viewport now. Done means the task's finishing condition is TRUE in the page state above (for a video: VIDEO ELEMENT says PLAYING, clock moving, and the TITLE is the right video); the system checks the facts and rejects a false done.
Write a short notes line each step (what you learned, what to avoid); it is shown to you next step.

Answer with one JSON object only:
{{"observed":"one sentence: where I am and what my last action did","notes":"what to remember","action":"goto","url":"https://...","reason":"..."}}
{{"observed":"...","notes":"...","action":"click","n":3,"reason":"..."}}
{{"observed":"...","notes":"...","action":"type","n":0,"text":"words","enter":true,"reason":"..."}}
{{"observed":"...","notes":"...","action":"scroll","px":700,"reason":"..."}}
{{"observed":"...","notes":"...","action":"scrollto","text":"Reviews","reason":"..."}}
{{"observed":"...","notes":"...","action":"back","reason":"..."}}
{{"observed":"...","notes":"...","action":"dismiss","reason":"close the pop-up covering the page"}}
{{"observed":"...","notes":"...","action":"key","key":"Escape","reason":"..."}}
{{"observed":"...","notes":"...","action":"play","reason":"..."}}
{{"observed":"...","notes":"...","action":"wait","seconds":2,"reason":"..."}}
{{"observed":"...","notes":"...","action":"done","summary":"what in the page state proves it"}}
{{"observed":"...","notes":"...","action":"fail","reason":"..."}}"""
        body = json.dumps({"model": self.model, "temperature": 0.1, "max_tokens": 320,
                           "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
        req = urlrequest.Request(self.endpoint, data=body, headers={"Content-Type": "application/json"})
        with urlrequest.urlopen(req, timeout=self.timeout) as r:
            payload = json.loads(r.read())
        raw = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        return parse_action(raw)


def parse_action(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    value = None
    try:
        value = json.loads(text)
    except Exception:
        start = text.find("{"); dec = json.JSONDecoder()
        while start != -1 and value is None:
            try: value, _ = dec.raw_decode(text[start:])
            except Exception: start = text.find("{", start + 1)
    if isinstance(value, list) and value and isinstance(value[0], dict): value = value[0]
    if not isinstance(value, dict) or value.get("action") not in ACTIONS:
        raise ValueError("model returned no usable browser action")
    return value


def video_done(st: Dict[str, Any], task: str) -> Tuple[bool, str]:
    """For a video task the finishing condition is a fact, not an opinion: an on-screen video whose clock is moving."""
    m = (st or {}).get("media") or {}
    pos = int(m.get("currentTime", 0) or 0)
    moving = m.get("advancing", pos >= 1)   # older drivers report no sample; then a position past 0s stands in
    if m.get("present") and not m.get("paused") and not m.get("ended") and moving and pos >= 1:
        return True, f"video playing: '{st.get('title')}' at {pos}s"
    if not m.get("present"): return False, "no video on this page"
    if not m.get("paused") and not m.get("ended"): return False, "play was pressed but the video's clock is not moving: use play, or back and choose another"
    return False, "the video is present but paused: use play"


def is_video_task(task: str) -> bool:
    return bool(re.search(r"\b(video|watch|play(ing)?|youtube)\b", task or "", re.I))


def run(task: str, browser, planner: Callable[..., Dict[str, Any]], max_steps: int = DA.DEFAULT_MAX_STEPS,
        should_stop: Callable[[], bool] = DA._stop_requested, job_id: Optional[str] = None,
        progress: Optional[Callable[[int, int], None]] = None, verifier: Optional[Callable[..., Tuple[bool, str]]] = None) -> DA.RunResult:
    """One step: read the page, decide, act, measure what changed. An action that changed nothing is reported as
    NO CHANGE with what to try instead; the same no-change action three times running, or the same two pages
    alternating three times, ends the job. Repeating an action that DOES change the page is allowed (next, next,
    next). The model's notes are carried from step to step so it can remember what led somewhere wrong."""
    job_id = job_id or uuid.uuid4().hex[:12]
    recent: List[Dict[str, Any]] = []; last_result = ""; calls = 0; errors = 0; notes = ""
    last_sig = ""; stalls = 0; page_hashes: List[str] = []
    ens = browser.ensure()
    if not ens.get("ok"):
        return DA.RunResult("failed", "browser: " + str(ens.get("error", "could not start")), 0, 0, job_id)
    try: browser.activate()
    except Exception: pass
    text = ""
    for step in range(1, max_steps + 1):
        if should_stop(): return DA.RunResult("stopped", "stop requested", step - 1, calls, job_id)
        try:
            page = browser.elements(); st = page.get("state") or {}; elements = page.get("elements") or []
            tx = browser.text(); text = tx.get("text", ""); outline = tx.get("outline") or []
        except Exception as exc:
            return DA.RunResult("failed", "browser read failed: " + str(exc)[:200], step - 1, calls, job_id)
        page_hash = hashlib.sha256((str(st.get("url")) + "|" + str(st.get("title")) + "|" + (text or "")[:3000] + "|" + str(int(st.get("scrollY", 0) or 0) // 200)).encode()).hexdigest()[:16]
        # did the last action change anything? the model is told plainly, and the same dead action is not tried forever
        if step > 1:
            if page_hashes and page_hash == page_hashes[-1] and not last_result.startswith(("DONE REJECTED", "ACTION ERROR", "PLANNER ERROR")) and not last_result.startswith("waited"):
                stalls = stalls + 1 if last_sig else 1
                last_result = ("NO CHANGE: " + last_result + " -- the page is exactly as before. That action does nothing here; choose something different"
                               + (" (another item, scroll, back)" if stalls == 1 else "; you have now tried it %d times" % stalls))
                if stalls >= 3: return DA.RunResult("failed", "same action repeated 3 times with no change: " + last_sig[:80], step - 1, calls, job_id)
            else:
                stalls = 0
        page_hashes.append(page_hash)
        if len(page_hashes) >= 6 and all(page_hashes[-1 - i] == page_hashes[-1 - i - 2] for i in range(4)) and page_hashes[-1] != page_hashes[-2]:
            return DA.RunResult("failed", "bouncing between the same two pages three times", step - 1, calls, job_id)
        # a video task finishes on a fact, without asking anyone
        if is_video_task(task):
            ok, why = video_done(st, task)
            if ok:
                DA._audit({"job_id": job_id, "step": step, "mode": "browser", "check": {"complete": True, "why": why}})
                return DA.RunResult("completed", why, step, calls, job_id)
        elif verifier is not None and step >= 3 and (step - 3) % 4 == 0:
            calls += 1
            try: ok, why = verifier(task, "the task as stated is complete", st, text, outline)
            except TypeError: ok, why = verifier(task, "the task as stated is complete", st, text)
            DA._audit({"job_id": job_id, "step": step, "mode": "browser", "check": {"complete": bool(ok), "why": str(why)[:200]}})
            if ok: return DA.RunResult("completed", "completion check: " + str(why)[:300], step, calls, job_id)
        summary = _summary(st, elements, text, outline)
        try:
            try: action = planner(task, summary, step, last_result, recent, notes)
            except TypeError: action = planner(task, summary, step, last_result, recent)
            errors = 0
        except Exception as exc:
            errors += 1; calls += 1
            DA._audit({"job_id": job_id, "step": step, "mode": "browser", "planner_error": str(exc)[:200]})
            if errors >= 3: return DA.RunResult("failed", "the model answered unusably three times running", step, calls, job_id)
            last_result = "PLANNER ERROR: answer with exactly one JSON object (%s)" % str(exc)[:100]; continue
        calls += 1
        if progress: progress(step, calls)
        kind = action["action"]
        if action.get("notes"): notes = str(action["notes"])[:400]
        DA._audit({"job_id": job_id, "step": step, "mode": "browser", "page": page_hash, "action": DA._auditable_action(action)})
        if kind == "done":
            summary_txt = str(action.get("summary", "done"))
            if is_video_task(task):
                ok, why = video_done(st, task)
                if not ok:
                    last_result = "DONE REJECTED: " + why; last_sig = ""; recent.append({"step": step, "action": {"action": "done"}, "result": last_result}); continue
            elif verifier is not None:
                calls += 1
                try: ok, why = verifier(task, summary_txt, st, text, outline)
                except TypeError: ok, why = verifier(task, summary_txt, st, text)
                DA._audit({"job_id": job_id, "step": step, "mode": "browser", "verify": {"claimed": summary_txt[:200], "confirmed": bool(ok), "why": str(why)[:200]}})
                if not ok:
                    last_result = "DONE REJECTED: " + str(why)[:200]; last_sig = ""; recent.append({"step": step, "action": {"action": "done"}, "result": last_result}); continue
            return DA.RunResult("completed", summary_txt, step, calls, job_id)
        if kind == "fail":
            return DA.RunResult("failed", str(action.get("reason", "model stopped")), step, calls, job_id)
        sig = json.dumps({k: v for k, v in action.items() if k not in ("reason", "observed", "notes")}, sort_keys=True)
        if sig != last_sig: stalls = 0
        last_sig = sig
        try:
            if kind == "goto":
                url = str(action.get("url", "")).strip()
                if not DA.URL_RE.match(url): raise ValueError("goto needs a full http(s) address")
                if url.rstrip("/") == str(st.get("url", "")).rstrip("/"):
                    last_result = "already on that page; going there again changes nothing. Choose from the list: click a number or scroll to see more"
                else:
                    r = browser.goto(url); last_result = f"goto -> {r.get('title')}"
            elif kind == "click":
                n = int(action.get("n")); label = elements[n]["text"][:60] if 0 <= n < len(elements) else "?"
                ckind = elements[n].get("kind", "") if 0 <= n < len(elements) else ""
                r = browser.click(n)
                if r.get("ok"):
                    last_result = f"clicked [{n}] {ckind} '{label}' -> now on: {r['state'].get('title')} ({page_type(r['state'].get('url', ''))})"
                    if r.get("changed") is False: last_result = f"clicked [{n}] {ckind} '{label}' but nothing changed"
                else: last_result = "click failed: " + str(r.get("error"))
            elif kind == "type":
                n = int(action.get("n")); r = browser.type(n, str(action.get("text", ""))[:500], enter=bool(action.get("enter", False)))
                last_result = (f"typed into [{n}]" + (" and pressed enter" if action.get("enter") else "") + f" -> {r['state'].get('title')}") if r.get("ok") else "type failed: " + str(r.get("error"))
            elif kind == "scroll":
                px = max(-3000, min(3000, int(action.get("px", 700)))); browser.scroll(px); last_result = f"scrolled {px}"
            elif kind == "scrollto":
                r = browser.scrollto(str(action.get("text", ""))[:80])
                last_result = (f"scrolled to '{r.get('found')}'" if r.get("ok") else f"no section or text matching '{action.get('text')}' on this page; see the SECTIONS list")
            elif kind == "dismiss":
                r = browser.dismiss(); last_result = f"dismiss: {r.get('how')} -> now on: {r['state'].get('title')}"
            elif kind == "back":
                r = browser.back(); last_result = f"went back -> now on: {r['state'].get('title')} ({page_type(r['state'].get('url', ''))})"
            elif kind == "key":
                browser.key(str(action.get("key", "Escape"))[:12]); last_result = "key " + str(action.get("key"))
            elif kind == "play":
                r = browser.play(); last_result = "play -> " + str(r.get("result")) + "; " + video_done(r.get("state") or {}, task)[1]
            elif kind == "wait":
                s = max(.2, min(8.0, float(action.get("seconds", 2)))); time.sleep(s); last_result = f"waited {s:g}s"
        except Exception as exc:
            last_result = "ACTION ERROR: " + str(exc)[:200]
        recent.append({"step": step, "action": {k: v for k, v in action.items() if k not in ("observed", "notes")}, "result": last_result[:160]})
        if should_stop(): return DA.RunResult("stopped", "stop requested", step, calls, job_id)
    return DA.RunResult("failed", f"maximum {max_steps} steps reached", max_steps, calls, job_id)


class GemmaPageVerifier:
    """Yes/no on the page state and text, for tasks that are not about a video."""
    def __init__(self, endpoint: str = DA.GEMMA_API, model: str = DA.GEMMA_MODEL, timeout: float = 60.0):
        self.endpoint, self.model, self.timeout = endpoint, model, timeout

    def __call__(self, task: str, claim: str, st: Dict[str, Any], text: str, outline: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, str]:
        secs = "\n".join(f"  {'ON SCREEN' if o.get('onscreen') else '         '} {o.get('text', '')}" for o in (outline or [])[:40])
        prompt = (f"TASK: {task}\nCLAIM: {claim}\nPAGE URL: {st.get('url')}\nPAGE TITLE: {st.get('title')}\nSCROLL: {st.get('scrollY', 0)} of {st.get('height', 0)}\n"
                  f"SECTIONS OF THE PAGE (which are on screen now):\n{secs}\nTEXT VISIBLE ON SCREEN NOW:\n{(text or '')[:3000]}\n\n"
                  "Does the page state show that the claim is true and the task is complete? Any error, wrong page, or missing result means NO. "
                  'Answer one JSON object only: {"verified": true|false, "seen": "one sentence"}')
        body = json.dumps({"model": self.model, "temperature": 0.0, "max_tokens": 120, "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
        try:
            with urlrequest.urlopen(urlrequest.Request(self.endpoint, data=body, headers={"Content-Type": "application/json"}), timeout=self.timeout) as r:
                payload = json.loads(r.read())
            raw = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            m = re.search(r"\{.*\}", raw, flags=re.S); d = json.loads(m.group(0)) if m else {}
            return bool(d.get("verified")), str(d.get("seen", raw))[:200]
        except Exception as exc:
            return False, "verifier unavailable: " + str(exc)[:120]


def run_task(task: str, max_steps: int = DA.DEFAULT_MAX_STEPS, job_id: Optional[str] = None) -> DA.RunResult:
    import browser_winpy
    return run(task, browser_winpy.EdgeBrowser(), GemmaTextPlanner(), max_steps, job_id=job_id,
               progress=lambda step, calls: DA._state(step=step, gemma_calls=calls, mode="browser"), verifier=GemmaPageVerifier())


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--task", required=True); ap.add_argument("--max-steps", type=int, default=DA.DEFAULT_MAX_STEPS)
    a = ap.parse_args()
    r = run_task(a.task, a.max_steps)
    print(json.dumps(r.__dict__, ensure_ascii=False)); raise SystemExit(0 if r.status == "completed" else 1)
