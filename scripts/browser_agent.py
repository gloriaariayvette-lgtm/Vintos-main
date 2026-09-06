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
        if e.get("marker"): continue
        flag = ("" if e.get("ontop", True) else " (below the fold)") + (" [pop-up]" if e.get("popup") else "")
        flag += (" (DISABLED - greyed out; something it needs is missing)" if e.get("disabled") else "") + (" (selected)" if e.get("selected") else "")
        if e.get("kind") in ("field", "select"):
            flag += f' = "{e.get("value")}"' if e.get("value") else " = (empty)"
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
{notes or 'PLAN: (none yet)'}
LAST RESULT: {last_result or 'none'}
RECENT ACTIONS: {json.dumps(recent[-6:], ensure_ascii=False)}

WHAT THE PAGE IS NOW:
{summary}

How to think, in order:
1. Where am I in the PLAN? Which plan step is next? Read PAGE TYPE. Is this the kind of page that step needs? If you landed somewhere wrong (a channel page when you wanted a video, an ad, a login wall), the correct move is back, then a different choice. Never repeat a choice that led somewhere wrong.
2. What did my last action do? If LAST RESULT says NO CHANGE, that action does not work here: do something different (another item, scroll, back, a different kind of item). If a button is DISABLED, clicking it is useless: the page is waiting for something else first (a rating not chosen, a required field empty, a box unticked, a sign-in). Find and do that thing.
3. Read the state next to each item: a field shows what it holds now (long text is shown as its start ... end and its length; that is not truncation), "(selected)" means already chosen. Trust these over your memory: if a field you typed into reads (empty), the text is gone and must be typed again, or it was the wrong field.
4. What is the one action that makes progress now?

Rules: choose items by their NUMBER from the list; never invent numbers. Kinds: "video" opens a watch page, "short" a short clip, "channel" a creator's profile (not a video), "playlist" a list, "field" is typable, "select" a drop-down, "button"/"link" are clickable, "star" is one star of a rating (click the one for the rating you want), "option" is a choice (radio, tick box, tab). "First result" means the lowest-numbered item of the right kind. To search a site, use goto with the search URL (YouTube: https://www.youtube.com/results?search_query=WORDS ; Google: https://www.google.com/search?q=WORDS). To watch a video: click a "video" item; on the watch page, if VIDEO ELEMENT is not PLAYING, use play. If nothing suitable is listed, scroll (positive = down) and look again. To reach a section of the page, use scrollto with a word from its heading (the SECTIONS list shows what exists and what is on screen); "on screen" means that section's heading is in the viewport now. Done means the task's finishing condition is TRUE in the page state above (for a video: VIDEO ELEMENT says PLAYING, clock moving, and the TITLE is the right video); the system checks the facts and rejects a false done.
Write a short notes line each step (what you learned, what to avoid, which plan step is done); it is shown to you next step.

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
{{"observed":"...","notes":"...","action":"fail","reason":"...","evidence":"exact words from the page that prove it"}}
Fail is for a wall the PAGE shows: its visible text or a pop-up saying sign-in/log-in is required for this action, an error message, a missing feature. A "Log In" link in a header is not a wall; a form you have not yet tried is not a wall. Quote the page in "evidence"; a fail without page evidence is rejected."""
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
        progress: Optional[Callable[[int, int], None]] = None, verifier: Optional[Callable[..., Tuple[bool, str]]] = None,
        reflector: Optional[Any] = None) -> DA.RunResult:
    """Two speeds of thought. The fast one (planner) picks one action a step. The slow one (reflector) draws up a
    plan before step 1 and is called back when the loop is stuck: the same page not moving on, done rejected,
    the checker saying no twice on the same page, a button clicked while disabled. It diagnoses from the full
    history and the page and hands the fast one a corrected plan; it can also declare the task blocked.

    One step: read the page, decide, act, measure what changed. An action that changed nothing is reported as
    NO CHANGE with what to try instead; the same no-change action three times running, or the same two pages
    alternating three times, ends the job. Repeating an action that DOES change the page is allowed (next, next,
    next). The model's notes are carried from step to step so it can remember what led somewhere wrong."""
    job_id = job_id or uuid.uuid4().hex[:12]
    recent: List[Dict[str, Any]] = []; last_result = ""; calls = 0; errors = 0; notes = ""
    last_sig = ""; stalls = 0; page_hashes: List[str] = []
    plan: Dict[str, Any] = {}; stuck = 0; last_reflect_step = -10; reflections = 0; verifier_no_on: List[str] = []
    ens = browser.ensure()
    if not ens.get("ok"):
        return DA.RunResult("failed", "browser: " + str(ens.get("error", "could not start")), 0, 0, job_id)
    try: browser.activate()
    except Exception: pass
    if reflector is not None:
        calls += 1
        plan = reflector.plan(task) or {}
        DA._audit({"job_id": job_id, "step": 0, "mode": "browser", "plan": plan.get("plan", []), "done_when": plan.get("done_when", ""), "error": plan.get("error", "")})
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
            if page_hashes and page_hash == page_hashes[-1] and not last_result.startswith(("DONE REJECTED", "FAIL REJECTED", "ACTION ERROR", "PLANNER ERROR", "RE-PLANNED")) and not last_result.startswith("waited"):
                stalls = stalls + 1 if last_sig else 1
                last_result = ("NO CHANGE: " + last_result + " -- the page is exactly as before. That action does nothing here; choose something different"
                               + (" (another item, scroll, back)" if stalls == 1 else "; you have now tried it %d times" % stalls))
                if stalls >= 3: return DA.RunResult("failed", "same action repeated 3 times with no change: " + last_sig[:80], step - 1, calls, job_id)
            else:
                stalls = 0
        # stuck: no new ground for a while. New ground resets it.
        if page_hash in page_hashes and step > 1: stuck += 1
        else: stuck = max(0, stuck - 1)
        if last_result.startswith(("NO CHANGE", "DONE REJECTED")): stuck += 1
        page_hashes.append(page_hash)
        bouncing = len(page_hashes) >= 6 and all(page_hashes[-1 - i] == page_hashes[-1 - i - 2] for i in range(4)) and page_hashes[-1] != page_hashes[-2]
        if bouncing: stuck += 2
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
            verifier_no_on.append(page_hash)
            if len(verifier_no_on) >= 2 and verifier_no_on[-1] == verifier_no_on[-2]: stuck += 2
        summary = _summary(st, elements, text, outline)
        # the slow thought, when the fast one is going in circles
        if reflector is not None and stuck >= 3 and step - last_reflect_step >= 3:
            calls += 1; reflections += 1; last_reflect_step = step
            r = reflector.reflect(task, recent, summary, plan.get("plan", []), notes) or {}
            DA._audit({"job_id": job_id, "step": step, "mode": "browser", "reflection": {k: r.get(k) for k in ("diagnosis", "plan", "avoid", "blocked", "error")}})
            if r.get("blocked"):
                return DA.RunResult("failed", "blocked: " + r["blocked"], step, calls, job_id)
            if r.get("plan"):
                plan = {**plan, "plan": r["plan"], "diagnosis": r.get("diagnosis", ""), "avoid": r.get("avoid", [])}
                last_result = ("RE-PLANNED after being stuck. Diagnosis: " + str(r.get("diagnosis", ""))[:300] + " -- follow the new PLAN from its first step."
                               + (f" (your last action: {last_result[:200]})" if last_result else ""))
                stuck = 0; last_sig = ""
            if reflections >= 4:
                return DA.RunResult("failed", "stuck four times over; last diagnosis: " + str(r.get("diagnosis", ""))[:200], step, calls, job_id)
        try:
            try: action = planner(task, summary, step, last_result, recent, _notes_block(plan, notes))
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
            # a wall must be on the page, in words, the same way done must be a fact: the model gave up at a
            # header "Log In" link once (2026-09-06)
            ev = re.sub(r"\s+", " ", str(action.get("evidence", ""))).strip().lower()
            haystack = re.sub(r"\s+", " ", (text or "") + " " + " ".join(e.get("text", "") for e in elements)).lower()
            if len(ev) < 8 or ev[:60] not in haystack:
                stuck += 1
                last_result = "FAIL REJECTED: the page does not show that. Quote the exact words on the page that block you, or keep going (try the form; a Log In link is not a wall)"
                recent.append({"step": step, "action": {"action": "fail", "reason": str(action.get("reason", ""))[:100]}, "result": last_result}); continue
            return DA.RunResult("failed", str(action.get("reason", "model stopped"))[:300] + " (page says: \"" + ev[:120] + "\")", step, calls, job_id)
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
                if 0 <= n < len(elements) and elements[n].get("disabled"):
                    stuck += 1
                    raise ValueError(f"[{n}] '{label}' is DISABLED: the page will not accept it until its requirements are met (a rating chosen? required text present? a box ticked? signed in?). Do that first")
                r = browser.click(n)
                if r.get("ok"):
                    last_result = f"clicked [{n}] {ckind} '{label}' -> now on: {r['state'].get('title')} ({page_type(r['state'].get('url', ''))})"
                    if r.get("changed") is False: last_result = f"clicked [{n}] {ckind} '{label}' but nothing changed"
                else: last_result = "click failed: " + str(r.get("error"))
            elif kind == "type":
                n = int(action.get("n")); r = browser.type(n, str(action.get("text", ""))[:500], enter=bool(action.get("enter", False)))
                if r.get("ok"):
                    v = str(r.get("value") or "")
                    held = (f"; the field now holds ALL {r.get('chars')} characters of the text" if r.get("complete") else
                            f"; the field holds {r.get('chars')} of the {r.get('wanted')} characters wanted" if r.get("chars") is not None else
                            f"; the field now reads \"{v[:80]}\"" if v else "; the field reads EMPTY afterwards - this field does not take text; find another")
                    last_result = f"typed into [{n}]" + (" and pressed enter" if action.get("enter") else "") + held + f" -> {r['state'].get('title')}"
                else: last_result = "type failed: " + str(r.get("error"))
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


class GemmaReflector:
    """The slow thought. Before step 1 it turns the task into a plan of sub-goals with the preconditions each one
    usually has (a review needs a rating AND text before submit lights up; a comment needs a sign-in). When the
    loop is stuck it is given the whole history and the page and asked for a diagnosis and a revised plan. Gemma
    by default; VINTOS_BROWSER_REFLECT=sonnet hands only this call to Sonnet (larger decisions, her rule)."""
    def __init__(self, endpoint: str = DA.GEMMA_API, model: str = DA.GEMMA_MODEL, timeout: float = 90.0):
        self.endpoint, self.model, self.timeout = endpoint, model, timeout
        self.use_sonnet = os.environ.get("VINTOS_BROWSER_REFLECT", "").lower() == "sonnet"

    def _ask(self, prompt: str) -> str:
        if self.use_sonnet:
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"))
                import server as _srv  # type: ignore
                key = _srv._anthropic_key()
                body = json.dumps({"model": "claude-sonnet-5", "max_tokens": 700, "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
                req = urlrequest.Request("https://api.anthropic.com/v1/messages", data=body, headers={"Content-Type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
                with urlrequest.urlopen(req, timeout=self.timeout) as r:
                    payload = json.loads(r.read())
                return "".join(b.get("text", "") for b in payload.get("content", []))
            except Exception:
                pass   # fall through to Gemma
        body = json.dumps({"model": self.model, "temperature": 0.2, "max_tokens": 700, "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
        with urlrequest.urlopen(urlrequest.Request(self.endpoint, data=body, headers={"Content-Type": "application/json"}), timeout=self.timeout) as r:
            payload = json.loads(r.read())
        return (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()

    @staticmethod
    def _parse(raw: str) -> Dict[str, Any]:
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I | re.S)
        m = re.search(r"\{.*\}", text, flags=re.S)
        d = json.loads(m.group(0)) if m else {}
        plan = [str(x)[:160] for x in (d.get("plan") or []) if str(x).strip()][:10]
        return {"diagnosis": str(d.get("diagnosis", ""))[:400], "plan": plan, "avoid": [str(x)[:120] for x in (d.get("avoid") or [])][:6],
                "blocked": str(d.get("blocked", ""))[:200]}

    def plan(self, task: str) -> Dict[str, Any]:
        prompt = f"""You are planning how to do a task in a web browser, before touching it.

TASK: {task}

Break it into ordered sub-goals. For each, think what a website usually REQUIRES before it lets that happen (examples: a review form needs a star rating chosen AND text entered before Submit becomes clickable; a search needs Enter or the search button; a video page needs play). Put those requirements into the steps so they are not discovered by trial and error. Do not assume a sign-in is needed: only the page can say that, and only when it is tried. Say how the finished state can be recognised on the page.

Answer one JSON object only:
{{"plan": ["1. ...", "2. ...", "..."], "done_when": "what the page will show", "avoid": ["..."]}}"""
        try:
            d = self._parse(self._ask(prompt))
            return d
        except Exception as exc:
            return {"diagnosis": "", "plan": [], "avoid": [], "blocked": "", "error": str(exc)[:120]}

    def reflect(self, task: str, history: List[Dict[str, Any]], summary: str, plan: List[str], notes: str) -> Dict[str, Any]:
        hist = "\n".join(f"  step {h.get('step')}: {json.dumps(h.get('action'), ensure_ascii=False)[:120]} -> {str(h.get('result', ''))[:140]}" for h in history[-14:])
        prompt = f"""A small model is driving a browser and is STUCK. You are the slower, careful thinker. Work out WHY, then give it a corrected plan.

TASK: {task}
THE PLAN IT WAS FOLLOWING: {json.dumps(plan, ensure_ascii=False)}
ITS OWN NOTES: {notes or '(none)'}
WHAT IT DID AND WHAT HAPPENED (oldest first):
{hist}

THE PAGE RIGHT NOW:
{summary[:5000]}

Think it through:
- Which sub-goal is it failing at? What exactly did it expect that did not happen?
- What is the page telling it? Look at DISABLED buttons (the page is waiting for something), fields reading (empty) after it typed (the text was lost, likely a reload or a reset), items marked (selected) or not (a rating never registered), pop-ups, sign-in walls, error messages in the visible text.
- Is there a precondition it skipped? A different control that does the same job? A wrong page it should leave?
- If the task truly cannot be done (a sign-in wall with no account, the thing does not exist), say so in "blocked".

Answer one JSON object only:
{{"diagnosis": "two or three sentences: what went wrong and why", "plan": ["1. the concrete next actions from THIS page, in order", "2. ...", "..."], "avoid": ["what not to repeat"], "blocked": "" or "why the task cannot be completed"}}"""
        try:
            return self._parse(self._ask(prompt))
        except Exception as exc:
            return {"diagnosis": "", "plan": [], "avoid": [], "blocked": "", "error": str(exc)[:120]}


def _notes_block(plan: Dict[str, Any], notes: str) -> str:
    lines = []
    if plan.get("plan"):
        lines.append("PLAN (follow in order; say in notes which step you are on):")
        lines += ["  " + p for p in plan["plan"]]
    if plan.get("done_when"): lines.append("DONE WHEN: " + str(plan["done_when"])[:200])
    if plan.get("diagnosis"): lines.append("DIAGNOSIS OF WHY YOU WERE STUCK: " + plan["diagnosis"])
    if plan.get("avoid"): lines.append("AVOID: " + "; ".join(plan["avoid"]))
    lines.append("YOUR NOTES FROM EARLIER STEPS: " + (notes or "(none yet)"))
    return "\n".join(lines)


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
               progress=lambda step, calls: DA._state(step=step, gemma_calls=calls, mode="browser"), verifier=GemmaPageVerifier(), reflector=GemmaReflector())


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--task", required=True); ap.add_argument("--max-steps", type=int, default=DA.DEFAULT_MAX_STEPS)
    a = ap.parse_args()
    r = run_task(a.task, a.max_steps)
    print(json.dumps(r.__dict__, ensure_ascii=False)); raise SystemExit(0 if r.status == "completed" else 1)
