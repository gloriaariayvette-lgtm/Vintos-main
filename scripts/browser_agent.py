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

ACTIONS = {"goto", "click", "type", "scroll", "key", "play", "wait", "done", "fail"}
WEB_HINT = re.compile(r"\b(youtube|browser|website|web ?site|web|search (for|the web)|video|review|url|https?://|google|recipe|reddit|wikipedia|tab|page|site|amazon|spotify web|open .{0,30}\.(com|org|net))\b", re.I)


def looks_like_web(task: str) -> bool:
    return bool(WEB_HINT.search(task or ""))


def _summary(st: Dict[str, Any], elements: List[Dict[str, Any]], text: str) -> str:
    media = st.get("media")
    if media:
        playing = media.get("present") and not media.get("paused") and not media.get("ended")
        pos = int(media.get("currentTime", 0) or 0)
        # the same rule video_done applies: playing means the clock is moving, not just that play was pressed
        word = ("PLAYING" if playing and pos >= 1 else "starting (play pressed, clock still at 0s: wait 2 seconds and look again)" if playing
                else "present but paused/ended" if media.get("present") else "none")
        m = f"VIDEO ELEMENT: {word} (position {pos}s of {media.get('duration', 0)}s)"
    else:
        m = "VIDEO ELEMENT: none on this page"
    lines = [f"URL: {st.get('url')}", f"TITLE: {st.get('title')}", m,
             f"SCROLL: {st.get('scrollY', 0)} of {st.get('height', 0)} (viewport {st.get('inner', 0)})", "",
             "CLICKABLE THINGS (number, kind, label):"]
    for i, e in enumerate(elements):
        flag = "" if e.get("ontop", True) else " (below the fold)"
        lines.append(f"[{i}] {e.get('kind', '?')}: {e.get('text', '')[:110]}{flag}")
    lines += ["", "PAGE TEXT (excerpt):", (text or "")[:2500]]
    return "\n".join(lines)


class GemmaTextPlanner:
    def __init__(self, endpoint: str = DA.GEMMA_API, model: str = DA.GEMMA_MODEL, timeout: float = 60.0):
        self.endpoint, self.model, self.timeout = endpoint, model, timeout

    def __call__(self, task: str, summary: str, step: int, last_result: str, recent: List[Dict[str, Any]]) -> Dict[str, Any]:
        prompt = f"""You drive a web browser for Vintos. Complete the task by choosing exactly ONE next action from what the page offers.

TASK: {task}
STEP: {step}
LAST RESULT: {last_result or 'none'}
RECENT ACTIONS: {json.dumps(recent[-6:], ensure_ascii=False)}

WHAT THE PAGE IS NOW:
{summary}

Rules: choose items by their NUMBER from the list; never invent numbers. To search a site, use goto with the search URL (YouTube: https://www.youtube.com/results?search_query=WORDS ; Google: https://www.google.com/search?q=WORDS). To watch a video, click the item of kind "video" whose label matches what you want; after the click, if VIDEO ELEMENT says paused, use play. If what you want is not listed, scroll (positive = down) and look again. Done means the task's finishing condition is TRUE in the page state above (for a video: VIDEO ELEMENT says PLAYING and the TITLE is the right video). Do not repeat an action that already did nothing.

Answer with one JSON object only:
{{"observed":"one sentence: what state the page is in","action":"goto","url":"https://...","reason":"..."}}
{{"observed":"...","action":"click","n":3,"reason":"..."}}
{{"observed":"...","action":"type","n":0,"text":"words","enter":true,"reason":"..."}}
{{"observed":"...","action":"scroll","px":700,"reason":"..."}}
{{"observed":"...","action":"key","key":"Escape","reason":"..."}}
{{"observed":"...","action":"play","reason":"..."}}
{{"observed":"...","action":"wait","seconds":2,"reason":"..."}}
{{"observed":"...","action":"done","summary":"what in the page state proves it"}}
{{"observed":"...","action":"fail","reason":"..."}}"""
        body = json.dumps({"model": self.model, "temperature": 0.1, "max_tokens": 260,
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
    """For a video task the finishing condition is a fact, not an opinion: a <video> that is playing on a watch page."""
    m = (st or {}).get("media") or {}
    if m.get("present") and not m.get("paused") and not m.get("ended") and int(m.get("currentTime", 0) or 0) >= 1:
        return True, f"video playing: '{st.get('title')}' at {m.get('currentTime')}s"
    if not m.get("present"): return False, "no video is playing"
    if not m.get("paused") and not m.get("ended"): return False, "the video's clock is still at 0s: wait 2 seconds, then look again"
    return False, "the video is present but not playing: use play"


def is_video_task(task: str) -> bool:
    return bool(re.search(r"\b(video|watch|play(ing)?|youtube)\b", task or "", re.I))


def run(task: str, browser, planner: Callable[..., Dict[str, Any]], max_steps: int = DA.DEFAULT_MAX_STEPS,
        should_stop: Callable[[], bool] = DA._stop_requested, job_id: Optional[str] = None,
        progress: Optional[Callable[[int, int], None]] = None, verifier: Optional[Callable[..., Tuple[bool, str]]] = None) -> DA.RunResult:
    job_id = job_id or uuid.uuid4().hex[:12]
    recent: List[Dict[str, Any]] = []; last_result = ""; last_sig = ""; repeated = 0; calls = 0; sigs: List[str] = []; errors = 0
    ens = browser.ensure()
    if not ens.get("ok"):
        return DA.RunResult("failed", "browser: " + str(ens.get("error", "could not start")), 0, 0, job_id)
    try: browser.activate()
    except Exception: pass
    for step in range(1, max_steps + 1):
        if should_stop(): return DA.RunResult("stopped", "stop requested", step - 1, calls, job_id)
        try:
            page = browser.elements(); st = page.get("state") or {}; elements = page.get("elements") or []
            text = browser.text().get("text", "") if step == 1 or "goto" in last_result or "clicked" in last_result or "scroll" in last_result or not recent else recent[-1].get("text_cache", "")
        except Exception as exc:
            return DA.RunResult("failed", "browser read failed: " + str(exc)[:200], step - 1, calls, job_id)
        # a video task finishes on a fact, without asking anyone
        if is_video_task(task):
            ok, why = video_done(st, task)
            if ok:
                DA._audit({"job_id": job_id, "step": step, "mode": "browser", "check": {"complete": True, "why": why}})
                return DA.RunResult("completed", why, step, calls, job_id)
        elif verifier is not None and step >= 3 and (step - 3) % 4 == 0:
            calls += 1
            ok, why = verifier(task, "the task as stated is complete", st, text)
            DA._audit({"job_id": job_id, "step": step, "mode": "browser", "check": {"complete": bool(ok), "why": str(why)[:200]}})
            if ok: return DA.RunResult("completed", "completion check: " + str(why)[:300], step, calls, job_id)
        summary = _summary(st, elements, text)
        try:
            action = planner(task, summary, step, last_result, recent); errors = 0
        except Exception as exc:
            errors += 1; calls += 1
            DA._audit({"job_id": job_id, "step": step, "mode": "browser", "planner_error": str(exc)[:200]})
            if errors >= 3: return DA.RunResult("failed", "the model answered unusably three times running", step, calls, job_id)
            last_result = "PLANNER ERROR: answer with exactly one JSON object (%s)" % str(exc)[:100]; continue
        calls += 1
        if progress: progress(step, calls)
        kind = action["action"]
        DA._audit({"job_id": job_id, "step": step, "mode": "browser", "page": hashlib.sha256(summary.encode()).hexdigest()[:16],
                   "action": DA._auditable_action(action)})
        if kind == "done":
            summary_txt = str(action.get("summary", "done"))
            if is_video_task(task):
                ok, why = video_done(st, task)
                if not ok:
                    last_result = "DONE REJECTED: " + why; recent.append({"step": step, "action": action, "result": last_result}); continue
            elif verifier is not None:
                calls += 1
                ok, why = verifier(task, summary_txt, st, text)
                DA._audit({"job_id": job_id, "step": step, "mode": "browser", "verify": {"claimed": summary_txt[:200], "confirmed": bool(ok), "why": str(why)[:200]}})
                if not ok:
                    last_result = "DONE REJECTED: " + str(why)[:200]; recent.append({"step": step, "action": action, "result": last_result}); continue
            return DA.RunResult("completed", summary_txt, step, calls, job_id)
        if kind == "fail":
            return DA.RunResult("failed", str(action.get("reason", "model stopped")), step, calls, job_id)
        sig = json.dumps({k: v for k, v in action.items() if k not in ("reason", "observed")}, sort_keys=True)
        repeated = repeated + 1 if sig == last_sig else 0
        if repeated >= (5 if kind == "scroll" else 2):
            return DA.RunResult("failed", "same action repeated %d times" % (repeated + 1), step, calls, job_id)
        last_sig = sig; sigs.append(sig)
        if len(sigs) >= 6 and kind != "scroll" and all(sigs[-1 - i] == sigs[-1 - i - 2] for i in range(4)):
            return DA.RunResult("failed", "cycling through the same 2 actions three times", step, calls, job_id)
        try:
            if kind == "goto":
                url = str(action.get("url", "")).strip()
                if not DA.URL_RE.match(url): raise ValueError("goto needs a full http(s) address")
                if url.rstrip("/") == str(st.get("url", "")).rstrip("/"):
                    last_result = "ALREADY on that page; going there again changes nothing. Choose from the list above: click a number (a video is kind \"video\") or scroll to see more"
                else:
                    r = browser.goto(url); last_result = f"goto -> {r.get('title')}"
            elif kind == "click":
                n = int(action.get("n")); label = elements[n]["text"][:60] if 0 <= n < len(elements) else "?"
                r = browser.click(n)
                last_result = (f"clicked [{n}] {label} -> now on: {r['state'].get('title')}" if r.get("ok") else "click failed: " + str(r.get("error")))
            elif kind == "type":
                n = int(action.get("n")); r = browser.type(n, str(action.get("text", ""))[:500], enter=bool(action.get("enter", False)))
                last_result = (f"typed into [{n}]" + (" and pressed enter" if action.get("enter") else "") + f" -> {r['state'].get('title')}") if r.get("ok") else "type failed: " + str(r.get("error"))
            elif kind == "scroll":
                px = max(-3000, min(3000, int(action.get("px", 700)))); browser.scroll(px); last_result = f"scrolled {px}"
            elif kind == "key":
                browser.key(str(action.get("key", "Escape"))[:12]); last_result = "key " + str(action.get("key"))
            elif kind == "play":
                r = browser.play(); last_result = "play -> " + str(r.get("result")) + "; " + video_done(r.get("state") or {}, task)[1]
            elif kind == "wait":
                s = max(.2, min(8.0, float(action.get("seconds", 2)))); time.sleep(s); last_result = f"waited {s:g}s"
        except Exception as exc:
            last_result = "ACTION ERROR: " + str(exc)[:200]
        try: text_cache = browser.text().get("text", "")
        except Exception: text_cache = text
        recent.append({"step": step, "action": {k: v for k, v in action.items() if k != "observed"}, "result": last_result, "text_cache": text_cache})
        for r_ in recent[:-1]: r_.pop("text_cache", None)
        if should_stop(): return DA.RunResult("stopped", "stop requested", step, calls, job_id)
    return DA.RunResult("failed", f"maximum {max_steps} steps reached", max_steps, calls, job_id)


class GemmaPageVerifier:
    """Yes/no on the page state and text, for tasks that are not about a video."""
    def __init__(self, endpoint: str = DA.GEMMA_API, model: str = DA.GEMMA_MODEL, timeout: float = 60.0):
        self.endpoint, self.model, self.timeout = endpoint, model, timeout

    def __call__(self, task: str, claim: str, st: Dict[str, Any], text: str) -> Tuple[bool, str]:
        prompt = (f"TASK: {task}\nCLAIM: {claim}\nPAGE URL: {st.get('url')}\nPAGE TITLE: {st.get('title')}\nPAGE TEXT (excerpt):\n{(text or '')[:3000]}\n\n"
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
