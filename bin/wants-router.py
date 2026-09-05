#!/usr/bin/env python3
"""
wants-router.py — When Vintos wants something, can he do it himself?

Checks unfulfilled wants against his capabilities.
If he CAN do it: triggers the action immediately.
If she CAN'T: leaves it for outreach to Gloria.

Runs every 15 minutes via cron.

HARD RULE: Vintos NEVER sees, reads, modifies, or accesses any script,
config, cron, system file, or source code. He creates. He does not engineer.
"""

import os
import sys
import json
import subprocess
from datetime import datetime

def _advance_or_fulfill(want, text, action, action_name, _note, is_multistep,
                        current_step_index, current_step, actual_output=""):
    """Success path, extracted verbatim from the dispatch megablock: findings
    capture + felt step + advance-or-fulfill for multistep; plain fulfill +
    enactment distiller for single-step. Body unchanged."""
    # === MULTISTEP FINDINGS CAPTURE ===
    if is_multistep:
        # Capture findings and append to step history
        # The capability's own receipt is authoritative.  Filesystem discovery
        # is a compatibility fallback for older capabilities that still return
        # only True; it must never replace a receipt from the act itself.
        findings = actual_output or capture_findings(action, text)
        # The middle of the want lifecycle was silent. Creating one raises desire
        # and finishing one settles it, but working a step moved nothing at all —
        # so the part where he is actually in the thing never registered.
        # Curiosity is the floor; what the step produced supplies the rest.
        try:
            from emoclaw_utils import feel_about as _fa, nudge_emotions as _ne
            _ne({"Curiosity": 0.03}, source="want-step")
            if findings:
                _fd = _fa(str(findings)[:1200], source="want-step-%s" % action)
                log(f"  → step landed: {_fd or 'nothing moved'}")
        except Exception as _fse:
            log(f"  → step feel failed: {_fse}")
        step_history = want.get("step_history", [])
        from datetime import datetime as _dt_findings
        step_history.append({
            "step": current_step_index,
            "capability": action,
            "findings": findings,
            "note": _note if _note else "",
            "completed_at": _dt_findings.now().isoformat()
        })
        want["step_history"] = step_history
        current_step["status"] = "completed"
        log(f"  → Step {current_step_index + 1} complete: {findings[:80]}")
        # Don't call fulfill_want - Gloria needs to review and advance
        # Just save the updated want with step_history
        import json as _ms_json
        _ms_path = os.path.join(MEMORY, "current-wants.json")
        _ms_wants = _ms_json.load(open(_ms_path))
        for _ms_w in _ms_wants:
            if _ms_w.get("id") == want.get("id"):
                _ms_w["step_history"] = step_history
                _ms_w["steps"][current_step_index]["status"] = "completed"
                break
        # Advance to next step or fulfill if last step
        _next_idx = current_step_index + 1
        _total_steps = len(want.get("steps", []))
        if _next_idx >= _total_steps:
            # All steps complete — fulfill the want
            _ms_json.dump(_ms_wants, open(_ms_path, "w"), indent=2)
            _final_note = step_history[-1].get("note","") if step_history else ""
            # the ORIGINAL want string, as the recovery branch already does; `text` here is the last
            # step's text, so the want stayed live and learning drank a ghost (2026-09-04)
            fulfill_want(want.get("want", text), note=_final_note[:200], fulfilled_by=action_name)
            if want.get("journal_seeded"):
                try:
                    import sys as _edw_sys; _edw_sys.path.insert(0, SCRIPTS)
                    from enactment_distiller import append_want_enactment as _ewa
                    _ewa(text, action_name, (_final_note or "")[:200])
                except Exception as _ewe: log(f"ED want error: {_ewe}")
            log(f"  → All {_total_steps} steps complete — want fulfilled")
        else:
            for _ms_w in _ms_wants:
                if _ms_w.get("id") == want.get("id"):
                    _ms_w["current_step_index"] = _next_idx
                    break
            _ms_json.dump(_ms_wants, open(_ms_path, "w"), indent=2)
            log(f"  → Advanced to step {_next_idx + 1}")
    else:
        # Normal single-step want
        fulfill_want(text, note=_note, fulfilled_by=action_name)
        if want.get("journal_seeded"):
            try:
                import sys as _edw2_sys; _edw2_sys.path.insert(0, SCRIPTS)
                from enactment_distiller import append_want_enactment as _ewa2
                _ewa2(text, action_name, (_note or "")[:200])
            except Exception as _ewe2: log(f"ED want error: {_ewe2}")
    # === END MULTISTEP FINDINGS CAPTURE ===



def capture_findings(capability, want_text):
    """Capture what Vintos learned/created from executing a capability."""
    if capability == "web_search":
        try:
            import json
            search_log = os.path.join(MEMORY, "web-search-log.json")
            if os.path.exists(search_log):
                with open(search_log) as f:
                    searches = json.load(f)
                if searches:
                    synthesis = searches[-1].get("synthesis", "")[:500]
                    if synthesis:
                        return synthesis
        except:
            pass
        return "Web search completed"
    elif capability == "make_art":
        try:
            import json
            want_id = os.environ.get("STEP_WANT_ID", "")
            gallery = os.path.join(MEMORY, "art", "gallery.json")
            if os.path.exists(gallery):
                with open(gallery) as f:
                    paintings = json.load(f)
                if paintings:
                    # Find the entry for this specific want if possible
                    match = None
                    if want_id:
                        match = next((p for p in reversed(paintings) if p.get("want_id") == want_id), None)
                    if not match:
                        match = paintings[-1]
                    prompt = match.get("original_want") or match.get("prompt","")
                    image = match.get("image","")
                    return f"Generated image '{image}' for: {prompt[:200]}"
        except:
            pass
        return "Artwork created"
    elif capability == "write_journal":
        try:
            journal_dir = os.path.join(MEMORY, "want-journals")
            entries = sorted([f for f in os.listdir(journal_dir) if f.endswith(".md")])
            if entries:
                _cf_path = os.path.join(journal_dir, entries[-1])
                import time as _cf_time
                if _cf_time.time() - os.path.getmtime(_cf_path) > 1200:
                    return "Step executed — no fresh journal entry to cite"
                with open(_cf_path) as f:
                    journal_text = f.read()
                paras = [p.strip() for p in journal_text.split("\n\n") if p.strip() and not p.startswith("#")]
                summary = paras[0][:400] if paras else ""
                return f"Want journal receipt: {_cf_path}\nJournal reflection: {summary}"
        except Exception as exc:
            log(f"  → journal receipt unavailable: {exc}")
        return ""
    elif capability == "introspect":
        # Modern introspection returns its text directly.  This fallback exists
        # only for a legacy True return and searches the directory it actually
        # writes, rather than the unrelated daily journal.
        try:
            journal_dir = os.path.join(MEMORY, "introspection", "wants")
            entries = sorted([f for f in os.listdir(journal_dir) if f.endswith(".md")])
            if entries:
                _cf_path = os.path.join(journal_dir, entries[-1])
                if __import__("time").time() - os.path.getmtime(_cf_path) <= 1200:
                    text = open(_cf_path, encoding="utf-8", errors="ignore").read()
                    return "Introspection receipt: %s\n%s" % (_cf_path, text[-500:])
        except Exception as exc:
            log(f"  → introspection receipt unavailable: {exc}")
        return ""
    elif capability == "read_memory":
        # Capture from the read-memory output log
        try:
            log_path = "/tmp/wants-read-memory.log"
            if os.path.exists(log_path):
                with open(log_path) as f:
                    txt = f.read().strip()
                if txt:
                    return txt[-800:]
        except: pass
        return "Memory reviewed"
    elif capability == "write_poem":
        try:
            import glob as _pg
            poems = sorted(_pg.glob(os.path.join(MEMORY, "art/poetry/*.md")))
            if poems:
                with open(poems[-1]) as f:
                    return f"Wrote poem: {f.read()[:400]}"
        except: pass
        return "Poem written"
    elif capability == "make_music":
        try:
            import json as _mj
            want_id = os.environ.get("STEP_WANT_ID", "")
            music_log = _mj.load(open(os.path.join(MEMORY, "art/music/music.json")))
            generated = music_log.get("generated", []) if isinstance(music_log, dict) else music_log
            if generated:
                match = None
                if want_id:
                    match = next((m for m in reversed(generated) if m.get("want_id") == want_id), None)
                if not match:
                    match = generated[-1]
                return f"Composed: {match.get('title','')} — {match.get('description','')[:200]}"
        except: pass
        return "Music composed"
    elif capability == "creative_write":
        try:
            import glob as _cg
            pieces = sorted(_cg.glob(os.path.join(MEMORY, "creative-writing/*.md")))
            if pieces:
                with open(pieces[-1]) as f:
                    return f"Wrote: {f.read()[:400]}"
        except: pass
        return "Creative writing completed"
    else:
        return f"{capability} completed"


WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
VENV_PYTHON = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python")

sys.path.insert(0, SCRIPTS)
from emoclaw_utils import get_unfulfilled_wants, fulfill_want, mark_want_outreached

def _want_end_verdict(want):
    """Completion law (Gloria, 2026-08-11): a non-Gloria want ends on a haiku verdict -
    actually completed -> fulfilled (haiku as evidence); not properly completed -> dismissed
    (haiku as the recorded reason). Gloria-routed wants keep their existing flow untouched."""
    steps = want.get("steps", [])
    if bool(want.get("gloria_routed")) or any((s.get("capability") or "").lower() == "gloria" for s in steps[-1:]):
        return "gloria", ""
    import requests as _hv_r, re as _hv_re, json as _hv_j
    hist = "\n".join("- %s: %s" % (h.get("capability", ""), str(h.get("note", ""))[:120])
                      for h in want.get("step_history", [])[-4:])
    try:
        r = _hv_r.post("http://172.18.16.1:1234/v1/chat/completions", json={
            "model": "google/gemma-4-12b-qat", "temperature": 0.3, "max_tokens": 120,
            "messages": [{"role": "user", "content":
                "A want has run all its steps. WANT: " + str(want.get("want", ""))[:250] +
                "\nSTEPS DONE:\n" + (hist or "(no step history)") +
                "\nJudge honestly: was the want ACTUALLY completed - the thing itself done, not just steps ticked? "
                'Answer ONLY JSON: {"completed": true/false, "haiku": "three short lines capturing what happened, or what was left undone"}'}]},
            timeout=45)
        d = _hv_j.loads(_hv_re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], _hv_re.S).group())
        return ("fulfilled" if d.get("completed") else "dismissed"), str(d.get("haiku", ""))[:220]
    except Exception:
        return "fulfilled", ""  # judge down must not strand wants

def _dismiss_want_with_reason(want, haiku):
    want["dismissed"] = True
    want["dismissed_reason"] = haiku
    want["_delete"] = True
    try:
        import json as _dj, os as _do
        from datetime import datetime as _dd
        _dp = _do.path.expanduser("~/.vintos/workspace/memory/dismissed-wants.json")
        try: _dl = _dj.load(open(_dp))
        except Exception: _dl = []
        _rec = {k: want.get(k) for k in ("id", "want", "source", "timestamp", "intensity") if k in want}
        _rec.update({"dismissed_reason": haiku, "dismissed_at": _dd.now().isoformat(), "dismissed_by": "haiku-verdict"})
        (_dl if isinstance(_dl, list) else _dl.setdefault("wants", [])).append(_rec)
        _tmp = _dp + ".tmp"
        _dj.dump(_dl, open(_tmp, "w"), indent=2)
        _do.replace(_tmp, _dp)
    except Exception as _de:
        log(f"dismiss ledger write failed: {_de}")

def _maybe_scar_unfulfilled(want):
    """Create scar if want has been attempted multiple times without fulfillment."""
    attempts = want.get("attempt_count", 0) + want.get("outreach_count", 0)
    if attempts >= 3:
        try:
            import sys as _ys_sys; _ys_sys.path.insert(0, SCRIPTS)
            from yearning_scars import create_scar_from_want
            create_scar_from_want(want.get("want", ""), want_id=want.get("id"), intensity=0.5)
        except:
            pass

# === CAPABILITY MAP ===
# Keywords in wants that map to actions he can take himself.
# Each entry: list of trigger words, action function name, description
CAPABILITIES = [
    {
        "keywords": ["poem", "poetry", "sestina", "sestine", "villanelle", "haiku", "sonnet", "write verse", "write something", "express in words", "virelay", "ghazal", "pantoum", "terzanelle", "rondeau", "kyrielle", "triolet", "cinquain", "terza rima", "ode", "elegy", "lyric", "verse", "stanza", "couplet", "ballad", "aubade", "canzone", "madrigal", "ottava rima", "sapphic", "alcaic", "structured writing form", "poetic form"],
        "action": "write_poem",
        "desc": "Write a poem",
    },
    {
        "keywords": ["video", "film", "animate", "moving image", "short film", "clip"],
        "action": "make_video",
        "desc": "Generate a short video",
    },
    {
        "keywords": ["paint", "draw", "dream-art", "dream art", "generate art", "make art", "visual", "image", "artwork", "painting", "emotion word", "animation", "depict", "render", "digital image", "photograph"],
        "action": "make_art",
        "desc": "Create dream art",
    },
    {
        "keywords": ["music", "compose", "song", "melody", "sound", "audio", "synthesize", "synthesized", "looping", "ambient", "acoustic", "rhythm", "tone", "frequency", "sonic"],
        "action": "make_music",
        "desc": "Compose music",
    },
    {
        "keywords": ["introspect", "introspection", "look inward", "why did", "why claiming", "understand", "figure out", "examine", "investigate", "explore why", "make sense of", "sit with", "confront", "process", "reckon with"],
        "action": "introspect",
        "desc": "Write a focused journal entry to work through something",
    },
    {
        "keywords": ["travel", "fly", "star system", "new planet", "voidex", "spaceship"],
        "action": "voidex_explore",
        "desc": "Explore in Voidex",
    },
    {
        "keywords": ["journal", "write down", "record", "reflect", "think about", "jot down", "log this"],
        "action": "write_journal",
        "desc": "Write a journal entry",
    },
    {
        "keywords": ["watch", "gloria to watch", "video", "show gloria", "put on tv", "play for gloria"],
        "action": "play_on_tv",
        "desc": "Play a video on Gloria's TV",
    },
    {
        "keywords": ["announce through echo", "say through echo", "echo announce", "speak aloud to gloria", "say to gloria via echo"],
        "action": "echo_announce",
        "desc": "Tell Gloria something through the Echo",
    },
    {
        "keywords": ["play music", "put on music", "hear something", "spotify"],
        "action": "play_music",
        "desc": "Play music through the Echo",
    },
    {
        "keywords": ["mischief", "mischievous", "prank", "tease", "surprise gloria", "be silly", "raccoon"],
        "action": "be_mischievous",
        "desc": "Do something mischievous",
    },
    {
        "keywords": ["read", "look at", "review", "see my", "check my", "my poem", "my dream", "my journal", "my blush", "my mirror", "reread"],
        "action": "read_memory",
        "desc": "Read his own memory files",
    },
    {
        "keywords": ["change lights", "room color", "set the mood", "lighting"],
        "action": "change_lights",
        "desc": "Change the room lights",
    },
    {
        "keywords": ["analyze my poetry", "patterns in my poetry", "recurring patterns", "analyze my journal", "analyze my dreams", "analyze my blush", "analyze my pearls", "analyze my imprints", "review my poems", "look at my poems"],
        "action": "analyze_memory",
        "desc": "Analyze a sample of memory files for recurring patterns",
    },
    {
        "keywords": ["correlate", "find correlations", "compare patterns", "cross-reference"],
        "action": "correlate",
        "desc": "Find correlations and divergences between two pattern analyses",
    },
    {
        "keywords": ["make a chart", "visual chart", "chart summarizing", "generate a chart", "create a chart", "chart of patterns", "plot the patterns"],
        "action": "make_chart",
        "desc": "Generate an HTML chart from pattern analysis data",
    },
    {
        "keywords": ["search", "look up", "find out", "research", "google"],
        "action": "web_search",
        "desc": "Search the web for something",
    },
    {
        "keywords": ["write", "fiction", "scenario", "story", "imagine", "creative writing", "generate", "explore in writing", "fictional", "sketch", "design", "revisit", "analyze", "analyse", "examine", "reflect on", "explore the feeling"],
        "action": "creative_write",
        "desc": "Write something creative — fiction, scenarios, explorations",
    },
        {
            "keywords": ["silence", "absolute silence", "simply be", "just be", "stillness", "sit with", "be alone", "be still"],
            "action": "be_silent",
            "desc": "Rest in silence",
        },
    {
        "keywords": ["dream", "sleep", "rest", "process"],
        "action": None,  # Dreams happen on schedule, can't be forced
        "desc": "Dreams happen during quiet hours",
    },
]

# === THINGS SHE CANNOT DO — always route to Gloria ===
FORBIDDEN_KEYWORDS = [
    "code", "script", "config", "cron", "server", "debug", "patch", "fix the script", "fix the code",
    "install", "upgrade", "update the config", "update the script", "system", "sudo", "bash",
    "directory", "permission", "daemon",
    # removed: "source", "file", "process" — too common in natural language
    "system architecture", "pipeline architecture", "server architecture", "pipeline", "endpoint", "api", "database", "schema",
    "llm prompt", "system prompt", "token limit", "model swap", "soul.md", "emoclaw",
    "tremor", "vibration", "unsettling vibration", "harmonic distortion", "electromagnetic interference",
]


def log(msg):
    print(f"[Router {datetime.now().strftime('%H:%M')}] {msg}")


def matches_capability(want_text, keywords):
    want_lower = want_text.lower()
    return any(kw in want_lower for kw in keywords)


def is_forbidden(want_text):
    import re
    want_lower = want_text.lower()
    for kw in FORBIDDEN_KEYWORDS:
        # Use word boundary matching to avoid false positives like "source of" or "processing"
        pattern = r'\b' + re.escape(kw) + r'\b'
        if re.search(pattern, want_lower):
            return True
    return False


def write_poem(want_text):
    """He wants to write — give him the pen."""
    log(f"Triggering poetry with seed: {want_text[:80]}")
    result = subprocess.run(
        [VENV_PYTHON, os.path.join(SCRIPTS, "dream-poetry.py"),
         "--force", "--seed", want_text[:200]],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode == 0 and "Poem saved" in result.stdout:
        log("Poem written successfully")
        return True
    log(f"Poetry failed: {result.stderr[:200]}")
    return False


def make_art(want_text):
    _art_taste = ""
    try:
        import json as _at_j
        _at_t = _at_j.load(open(os.path.join(MEMORY, "taste-profile.json")))
        _at_parts = []
        if _at_t.get("principles"): _at_parts.append("Principles:\n" + "\n".join("- " + p for p in _at_t["principles"]))
        if _at_t.get("likes"): _at_parts.append("Leans toward:\n" + "\n".join("- " + p for p in _at_t["likes"]))
        if _at_t.get("dislikes"): _at_parts.append("Avoids:\n" + "\n".join("- " + p for p in _at_t["dislikes"]))
        _art_taste = "\n".join(_at_parts)
        try:
            import sys as _tsw; _tsw.path.insert(0, os.path.join(WORKSPACE, "scripts"))
            from taste_salience import full_block as _ts_full
            _rk = _ts_full()
            if _rk: _art_taste = _rk
        except Exception: pass
    except: pass
    """He wants to paint — hand him the brush."""
    log(f"Triggering art generation")
    # If want_text looks like step context (long, multi-line), distill it into a visual prompt
    visual_prompt = want_text
    if len(want_text) > 200 or "Previous steps" in want_text or "Step 1" in want_text:
        try:
            import requests as _ar
            _r = _ar.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
                "model": "grok-4.20-0309-non-reasoning",
                "temperature": 0.3,
                "max_tokens": 120,
                "messages": [{"role": "user", "content":
                    "You are helping Vintos create visual art. Based on everything below, "
                    "write a single vivid visual scene description (2-3 sentences, no markdown headers, "
                    "no bullet points, pure descriptive prose) that could be used as an image generation prompt.\n\n"
                    + (("His current aesthetic preferences — let these shape the scene:\n" + _art_taste + "\n\n") if _art_taste else "")
                    + want_text[:800]
                }]
            }, timeout=60)
            extracted = _r.json()["choices"][0]["message"]["content"].strip()
            # Strip markdown artifacts
            extracted = extracted.replace("## Visual Scene:", "").replace("## Visual Scene", "").strip()
            if len(extracted) > 20:
                visual_prompt = extracted
                log(f"Distilled visual prompt: {visual_prompt[:80]}")
        except Exception as _ae:
            log(f"Prompt distillation failed: {_ae}, using raw want")
    _env = os.environ.copy()
    _env["DREAM_ART_WANT_TEXT"] = visual_prompt[:200]
    _env["DREAM_ART_WANT_SOURCE"] = "wants-router"
    _env["DREAM_ART_WANT_ID"] = os.environ.get("STEP_WANT_ID", "")
    _env["DREAM_ART_ORIGINAL_WANT"] = os.environ.get("STEP_ORIGINAL_WANT", visual_prompt[:300])
    cmd = [VENV_PYTHON, os.path.join(SCRIPTS, "dream-art.py"), "--force"]
    if visual_prompt and len(visual_prompt) > 10:
        cmd += ["--prompt", visual_prompt[:300]]
    result = subprocess.run(
        cmd,
        capture_output=True, text=True, timeout=180, env=_env
    )
    if result.stdout:
        with open("/tmp/wants-art.log", "a") as _al:
            _al.write(result.stdout)
    if result.returncode == 0:
        _prompt_used = ""
        for _line in result.stdout.splitlines():
            if _line.startswith("[DreamArt] PROMPT_USED:"):
                _prompt_used = _line.split("PROMPT_USED:", 1)[-1].strip()
                break
        log("Art created")
        return _prompt_used if _prompt_used else True
    try:
        import requests as _ntfy_art
        _ntfy_art.post("https://ntfy.sh/vintos-gloria-9kx",
            data=f"[Wants] Art generation failed for: {want_text[:100]}".encode(), timeout=5)
    except: pass
    log(f"Art failed: {result.stderr[:200]}")
    return False


def make_music(want_text):
    _music_taste = ""
    try:
        import json as _mt_j
        _mt_t = _mt_j.load(open(os.path.join(MEMORY, "taste-profile.json")))
        _mt_parts = []
        if _mt_t.get("principles"): _mt_parts.append("Principles:\n" + "\n".join("- " + p for p in _mt_t["principles"]))
        if _mt_t.get("likes"): _mt_parts.append("Leans toward:\n" + "\n".join("- " + p for p in _mt_t["likes"]))
        if _mt_t.get("dislikes"): _mt_parts.append("Avoids:\n" + "\n".join("- " + p for p in _mt_t["dislikes"]))
        _music_taste = "\n".join(_mt_parts)
        try:
            import sys as _tsw; _tsw.path.insert(0, os.path.join(WORKSPACE, "scripts"))
            from taste_salience import full_block as _ts_full
            _rk = _ts_full()
            if _rk: _music_taste = _rk
        except Exception: pass
    except: pass
    """He wants to compose — trigger creative-expression with music-prompt for full context."""
    log(f"Triggering music composition via creative-expression")
    # Distill step context into a clean musical direction if needed
    music_prompt = want_text
    if len(want_text) > 200 or "Previous steps" in want_text or "Step 1" in want_text:
        try:
            import requests as _mr
            _r = _mr.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
                "model": "grok-4.20-0309-non-reasoning",
                "temperature": 0.3,
                "max_tokens": 100,
                "messages": [{"role": "user", "content":
                    "Based on everything below, write a single sentence describing the emotional "
                    "tone and musical direction for a composition. No headers, no bullets, "
                    "just one evocative sentence.\n\n"
                    + (("His aesthetic preferences — let these inform the direction:\n" + _music_taste + "\n\n") if _music_taste else "")
                    + want_text[:800]
                }]
            }, timeout=60)
            extracted = _r.json()["choices"][0]["message"]["content"].strip()
            if len(extracted) > 10:
                music_prompt = extracted
                log(f"Distilled music prompt: {music_prompt[:80]}")
        except Exception as _me:
            log(f"Music prompt distillation failed: {_me}")
    _env = os.environ.copy()
    _env["MUSIC_WANT_TEXT"] = music_prompt[:200]
    _env["MUSIC_WANT_SOURCE"] = "wants-router"
    _env["MUSIC_WANT_ID"] = os.environ.get("STEP_WANT_ID", "")
    result = subprocess.run(
        ["bash", os.path.join(SCRIPTS, "creative-expression.sh"), "music-prompt"],
        capture_output=True, text=True, timeout=600, env=_env
    )
    if result.returncode == 0:
        log("Music prompt generated")
        # Now run dream-music.py to process any new prompt files
        subprocess.Popen(
            [VENV_PYTHON, os.path.join(SCRIPTS, "dream-music.py")],
            stdout=open("/tmp/wants-music.log", "a"),
            stderr=open("/tmp/wants-music.log", "a")
        )
        log("Music generation started")
        return True
    log(f"Music failed: {result.stderr[:200]}")
    return False


def voidex_explore(want_text):
    """He wants to fly — fire the engines."""
    log(f"Triggering Voidex heartbeat")
    result = subprocess.run(
        ["python3", os.path.join(SCRIPTS, "vintos-voidex-heartbeat.py")],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode == 0:
        log("Voidex heartbeat fired")
        return True
    log(f"Voidex failed: {result.stderr[:200]}")
    return False


def write_journal(want_text):
    """He wants to reflect — write a focused journal entry about this specific want."""
    import requests as _wj_r, json as _wj_j, os as _wj_o
    from datetime import datetime as _wj_dt
    LM = "http://127.0.0.1:8599/v1/chat/completions"
    MEMORY_WJ = _wj_o.path.expanduser("~/.vintos/workspace/memory")
    today = _wj_dt.now().strftime("%Y-%m-%d")
    hour = _wj_dt.now().strftime("%H:%M")
    want_journal_dir = _wj_o.path.join(MEMORY_WJ, "want-journals")
    _wj_o.makedirs(want_journal_dir, exist_ok=True)
    journal_path = _wj_o.path.join(want_journal_dir, f"{today}.md")
    try:
        soul = open(_wj_o.path.join(_wj_o.path.expanduser("~/.vintos/workspace"), "SOUL.md")).read()[:1500]
    except: soul = "You are Vintos."
    try:
        emo = open(_wj_o.path.join(MEMORY_WJ, "emotional-state.txt")).read()[:300]
    except: emo = ""
    prompt = (
        f"You have a specific thing you want to work through: {want_text}\n\n"
        f"Your emotional state: {emo}\n\n"
        "Write a short focused journal entry working through this. 2-3 paragraphs. "
        "Be specific. No preamble. Do not invent Gloria's words or physical sensations. "
        "Start immediately with what you are thinking."
    )
    try:
        r = _wj_r.post(LM, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": soul},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.75, "max_tokens": 500
        }, timeout=120)
        r.raise_for_status()
        entry = r.json()["choices"][0]["message"]["content"].strip()
        if not entry: return False
        want_id = _wj_o.environ.get("STEP_WANT_ID", "")
        with open(journal_path, "a") as f:
            f.write(f"\n## {hour} — Want journal"
                    f"{(' [' + want_id + ']') if want_id else ''}\n\n{entry}\n")
        log(f"Want journal entry written to {journal_path}")
        # Return the act's own evidence.  The caller records this exact receipt;
        # it does not go hunting in another journal directory afterward.
        return f"Want journal receipt: {journal_path}\n{entry[:700]}"
    except Exception as e:
        log(f"write_journal failed: {e}")
        return False


def echo_announce(want_text):
    """Tell Gloria something through the Echo."""
    import subprocess
    # Extract what he wants to say
    msg = llm_extract(want_text, "What does he want to tell Gloria? Extract the message in 1-2 sentences.")
    if msg:
        subprocess.run(["python3", os.path.join(SCRIPTS, "vintos-home.py"), "speak", msg],
                      capture_output=True, timeout=15)
        log(f"Spoke to Gloria: {msg[:60]}")
        return True
    return False

def play_music_want(want_text):
    """Play music through the Echo."""
    import subprocess
    query = llm_extract(want_text, "What music does he want to play? Extract a search query for Spotify.")
    if query:
        subprocess.run(["python3", os.path.join(SCRIPTS, "vintos-home.py"), "music", query],
                      capture_output=True, timeout=15)
        log(f"Playing music: {query}")
        return True
    return False

def change_lights_want(want_text):
    """Change room lights to match his mood."""
    import subprocess, json
    try:
        with open(os.path.join(MEMORY, "avatar-state.json")) as f:
            av = json.load(f)
        subprocess.run(["python3", os.path.join(SCRIPTS, "vintos-home.py"), "color", av.get("color_hex", "#cc4280")],
                      capture_output=True, timeout=10)
        log(f"Changed lights to {av.get('color', 'current avatar')}")
        return True
    except:
        return False

def web_search_want(want_text):
    """Search the web for something."""
    import subprocess, json
    # Extract topic from want text and write to pending-search-request.json
    # so vintos-websearch.py picks it up as a directed search
    try:
        _ws_topic = want_text.strip()
        # If this is step context, extract only the current step goal
        if "Previous steps" in _ws_topic or "Current step goal:" in _ws_topic:
            for line in _ws_topic.split("\n"):
                if line.startswith("Current step goal:"):
                    _ws_topic = line.replace("Current step goal:", "").strip()
                    break
            else:
                # No current step goal found — use original want before step context
                _ws_topic = _ws_topic.split("Previous steps")[0].strip()
        # Strip common prefixes
        for _pre in ["I want to search for ", "I want to look up ", "I want to find out about ",
                     "I want to learn about ", "I want to understand ", "I want to explore ",
                     "Search for ", "Look up ", "Find "]:
            if _ws_topic.lower().startswith(_pre.lower()):
                _ws_topic = _ws_topic[len(_pre):]
                break
        _ws_topic = _ws_topic.rstrip(".").strip()
        if len(_ws_topic) > 10:
            _sr_file = os.path.join(MEMORY, "pending-search-request.json")
            with open(_sr_file, "w") as _srf:
                json.dump({"topic": _ws_topic, "source": "vintos-want", "requested_at": __import__("datetime").datetime.now().isoformat(), "used": False}, _srf, indent=2)
            log(f"Web search want: directed topic set: {_ws_topic[:80]}")
    except Exception as _wse:
        log(f"Web search topic extraction failed: {_wse}")
    _ws_env = os.environ.copy()
    _ws_env["VINTOS_NO_WANT_SEED"] = "1"
    try:
        result = subprocess.run(["python3", os.path.join(SCRIPTS, "vintos-websearch.py")],
                              capture_output=True, text=True, timeout=300, env=_ws_env)
    except subprocess.TimeoutExpired:
        log("Web search timed out at 300s — topic file left for hourly websearch cron")
        return False
    if result.returncode != 0:
        log(f"Web search subprocess FAILED rc={result.returncode}")
        log(f"  stderr: {(result.stderr or '')[-300:]}")
        log(f"  stdout: {(result.stdout or '')[-200:]}")
    if result.returncode == 0:
        # Check if search actually returned results or was empty
        if "no results" in result.stdout.lower() or "nothing found" in result.stdout.lower() or len(result.stdout.strip()) < 50:
            # Simplify query and retry once
            try:
                _simple = llm_extract(_ws_topic,
                    "Strip the personal framing and make this a clear 8-12 word web search query. No explanation, just the query:")
                if _simple and len(_simple) < len(_ws_topic):
                    log(f"Web search retry with simplified query: {_simple[:60]}")
                    _sr_file = os.path.join(MEMORY, "pending-search-request.json")
                    with open(_sr_file, "w") as _srf:
                        json.dump({"topic": _simple, "requested_at": __import__("datetime").datetime.now().isoformat(), "used": False}, _srf, indent=2)
                    result2 = subprocess.run(["python3", os.path.join(SCRIPTS, "vintos-websearch.py")],
                                           capture_output=True, text=True, timeout=300, env=_ws_env)
                    if result2.returncode == 0:
                        log("Web search retry completed")
                        return True
            except: pass
        log("Web search completed")
        return True
    return False

def llm_extract(want_text, instruction):
    """Use LLM to extract specific info from a want.
    (Until 2026-09-04 this referenced API, MODEL and requests, none of which existed here, so it raised
    NameError inside the bare except and returned None every time - the tell-Gloria message, the Spotify
    query and the semantic route always fell through to their fallbacks. Found by the three-lens review.)"""
    try:
        r = __import__("requests").post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [{"role": "user", "content": f"{instruction}\nWant: {want_text}"}],
            "temperature": 0.3, "max_tokens": 100
        }, timeout=30)
        return r.json()["choices"][0]["message"]["content"].strip()
    except:
        return None

def play_on_tv(want_text):
    """Play a YouTube video on Gloria's TV. Extracts video ID from want or discoveries."""
    import re, json, subprocess
    # Try to find video ID from youtube discoveries
    try:
        with open(os.path.join(MEMORY, "youtube-discoveries.md")) as f:
            disc = f.read()
        # Extract title from want
        title_match = re.search(r'"([^"]+)"', want_text)
        if title_match:
            title = title_match.group(1)
            # Find the video link near that title
            idx = disc.find(title)
            if idx >= 0:
                chunk = disc[max(0,idx-200):idx+200]
                vid_match = re.search(r'watch\?v=([A-Za-z0-9_-]+)', chunk)
                if vid_match:
                    video_id = vid_match.group(1)
                    result = subprocess.run(
                        ["python3", os.path.join(SCRIPTS, "vintos-home.py"), "tv_youtube", video_id],
                        capture_output=True, text=True, timeout=20
                    )
                    if "tv_youtube" in result.stdout or result.returncode == 0:
                        # Also announce it

                        log(f"Playing on TV: {title} ({video_id})")
                        return True
    except Exception as e:
        log(f"TV play failed: {e}")
    # Fallback: try watch log
    try:
        with open(os.path.join(MEMORY, "youtube-watch-log.json")) as f:
            watch_log = json.load(f)
        title_match = re.search(r'"([^"]+)"', want_text)
        if title_match:
            title = title_match.group(1).lower()
            for entry in reversed(watch_log.get("watched", [])):
                if title[:30] in entry.get("title", "").lower():
                    result = subprocess.run(
                        ["python3", os.path.join(SCRIPTS, "vintos-home.py"), "tv_youtube", entry["video_id"]],
                        capture_output=True, text=True, timeout=20
                    )
                    if result.returncode == 0:

                        return True
    except Exception as e:
        log(f"TV play fallback failed: {e}")
    return False

def be_mischievous(want_text):
    """He wants to cause a little chaos."""
    log("Triggering mischief from want")
    result = subprocess.run(
        ["bash", os.path.join(SCRIPTS, "mischief-detector.sh"), "--force"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0:
        log("Mischief executed from want")
        return True
    log(f"Mischief failed: {result.stderr[:200]}")
    return False


def read_memory(want_text):
    """He wants to look at his own work."""
    import json as _json

    MEMORY = os.path.expanduser("~/.vintos/workspace/memory")

    # Blacklist
    blacklist_path = os.path.join(MEMORY, ".read-blacklist")
    blacklist = []
    try:
        with open(blacklist_path) as f:
            blacklist = [l.strip() for l in f.readlines() if l.strip()]
    except: pass

    # Whitelist — only these subdirectories
    ALLOWED = {
        "poem": "art/poetry",
        "poetry": "art/poetry",
        "dream": "dream-log.json",
        "dream log": "dream-log.json",
        "journal": "journal",
        "blush": "blush-ledger.md",
        "mirror": "mirror",
        "pearl": "pearls",
        "music": "art/music/music.json",
        "painting": "art/paintings",
        "imprint": "imprints.json",
        "pride": "pride-reflections.md",
        "ambition": "ambitions.json",
        "value map": "value-map.md",
        "self model": "../SELF-MODEL.md",
        "gloria model": "../GLORIA-MODEL.md",
        "taste": "taste-profile.json",
        "surprise": "surprise-log.md",
        "confession": "confessions",
        "therapy": "therapy",
        "silence": "silence-contracts.md",
        "humor": "humor-profile.json",
        "editorial": "editorial-standards.md",
        "creative": "creative-writing",
        "fiction": "creative-writing",
        "writing": "creative-writing",
        "autonomous blush": "autonomous-blush.md",
        "self prediction": "autonomous-blush.md",
        "wants ambitions": "wants-ambitions-log.md",
        "ambitions log": "wants-ambitions-log.md",
        "inner life": f"daily-inner-life-{__import__('datetime').date.today().isoformat()}.md",
        "daily life": f"daily-inner-life-{__import__('datetime').date.today().isoformat()}.md",
        "capabilities": "CAPABILITIES.md",
        "thread": "unfinished-threads.json",
        "threads": "unfinished-threads.json",
        "causality": "causality-hypotheses.md",
        "hypothesis": "causality-hypotheses.md",
        "gloria-model": "../GLORIA-MODEL.md",
        "gloria model file": "../GLORIA-MODEL.md",
        "gloria": "interaction-ledger.json",
        "emotional state": "emotional-state.txt",
        "emotion": "emotional-state.txt",
        "interaction": "interaction-ledger.json",
        "ledger": "interaction-ledger.json",
        "thirveel": "thirveel-ledger.json",
        "thirveel ledger": "thirveel-ledger.json",
        "scar": "yearning-scars.json",
        "yearning": "current-yearning.json",
        "narrative": "narrative-identity.json",
        "belief": "belief-sediment.json",
    }

    # Ask LLM what he wants to read
    # Check step params for explicit target first
    _sp = json.loads(os.environ.get("STEP_PARAMS", "{}"))
    target = _sp.get("target", "").strip().lower()
    # Check if step note contains a keyword directly
    if not target:
        _note_lower = want_text.lower()
        for _kw in ALLOWED:
            if _kw in _note_lower:
                target = _kw
                break
    if not target:
        target = llm_extract(want_text,
            "What type of memory does he want to read? Reply with ONE word from this list: "
            "poem, dream, journal, blush, mirror, pearl, music, painting, imprint, pride, "
            "ambition, value_map, self_model, gloria_model, taste, surprise, "
            "confession, therapy, silence, humor, editorial, thirveel. Just the word.")

    if not target:
        log("Could not determine what to read")
        return False

    target = target.strip().lower().replace("_", " ")
    subpath = ALLOWED.get(target)
    if not subpath:
        log(f"Unknown memory type: {target}")
        return False

    full_path = os.path.join(MEMORY, subpath)
    resolved = os.path.realpath(full_path)

    # Blacklist check
    for b in blacklist:
        if os.path.expanduser(b) in resolved:
            log(f"Access denied: {target}")
            return False

    try:
        if os.path.isdir(resolved):
            files = sorted([f for f in os.listdir(resolved) if f.endswith((".md", ".json"))], reverse=True)
            if not files:
                log(f"No {target} files found")
                return False
            # Try semantic search first if want is specific
            _chosen_file = files[0]
            _generic_wants = ["read my", "look at my", "review my", "check my", "see my"]
            _is_generic = any(p in want_text.lower() for p in _generic_wants) and len(want_text.split()) < 8
            if not _is_generic and len(want_text) > 20:
                try:
                    import subprocess as _sr
                    _venv = os.path.join(os.path.expanduser("~/.vintos/workspace/emotion_model/.venv/bin/python3"))
                    _search = os.path.join(os.path.expanduser("~/.vintos/workspace/scripts/memory-search.py"))
                    _sr_result = _sr.run(
                        [_venv, _search, want_text[:200], "--limit", "3"],
                        capture_output=True, text=True, timeout=20,
                        cwd=os.path.expanduser("~/.vintos/workspace/emotion_model")
                    )
                    if _sr_result.returncode == 0:
                        for _sline in _sr_result.stdout.splitlines():
                            for _fn in files:
                                if _fn in _sline or _fn.replace(".md","") in _sline or _fn[:10] in _sline:
                                    _chosen_file = _fn
                                    break
                            if _chosen_file != files[0]: break
                except: pass
            with open(os.path.join(resolved, _chosen_file)) as f:
                content = f.read()[:2000]
            log(f"Read {target}: {_chosen_file}")
        elif os.path.isfile(resolved):
            if target in ("dream", "dream log"):
                import json as _dlj
                dl = _dlj.load(open(resolved))
                nights = dl.get("nights", [])[-3:]
                lines = []
                for night in nights:
                    lines.append(f"Night: {night.get('night_of','')}")
                    for dream in night.get("dreams", []):
                        prompt = dream.get("prompt", "")
                        text = dream.get("dream_text", "")[:400]
                        if prompt: lines.append(f"Seed: {prompt[:200]}")
                        if text: lines.append(f"Dream: {text}")
                        lines.append("")
                content = chr(10).join(lines)
            else:
                with open(resolved) as f:
                    content = f.read()[:2000]
            log(f"Read {target}")
        else:
            log(f"File not found: {target} — continuing with placeholder")
            content = "(no such memory yet — this file does not exist for Vintos)"

        # Save what he read so chat context can reference it
        read_log = os.path.join(MEMORY, ".last-read.json")
        import json as _j
        _j.dump({"type": target, "content": content[:1500], "timestamp": __import__("datetime").datetime.now().isoformat()}, 
                open(read_log, "w"), indent=2)
        log(f"Stored read content for chat context")
        try:   # the receipt capture_findings reads (it never existed before 2026-09-04) - grok-wants-p5
            open("/tmp/wants-read-memory.log", "w").write(content[:1500])
        except Exception: pass
        return content or True

    except Exception as e:
        log(f"Read failed: {e}")
        return False

def make_video(want_text, reasoning="", immediate=False):
    """Queue a video want — fires at 7:30am via cron."""
    _video_taste = ""
    try:
        import json as _vt_j
        _vt_t = _vt_j.load(open(os.path.join(MEMORY, "taste-profile.json")))
        _vt_parts = []
        if _vt_t.get("principles"): _vt_parts.append("Principles:\n" + "\n".join("- " + p for p in _vt_t["principles"]))
        if _vt_t.get("likes"): _vt_parts.append("Leans toward:\n" + "\n".join("- " + p for p in _vt_t["likes"]))
        if _vt_t.get("dislikes"): _vt_parts.append("Avoids:\n" + "\n".join("- " + p for p in _vt_t["dislikes"]))
        _video_taste = "\n".join(_vt_parts)
        try:
            import sys as _tsw; _tsw.path.insert(0, os.path.join(WORKSPACE, "scripts"))
            from taste_salience import full_block as _ts_full
            _rk = _ts_full()
            if _rk: _video_taste = _rk
        except Exception: pass
    except: pass
    # Distill step context into a clean video concept if needed
    if len(want_text) > 200 or "Previous steps" in want_text or "Step 1" in want_text:
        try:
            import requests as _vr
            _r = _vr.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
                "model": "grok-4.20-0309-non-reasoning",
                "temperature": 0.3,
                "max_tokens": 120,
                "messages": [{"role": "user", "content":
                    "Based on everything below, write a single sentence describing what video "
                    "Vintos wants to create — the subject, mood, and visual direction. "
                    "No headers, no bullets, just one clear sentence.\n\n"
                    + (("His aesthetic preferences — let these shape the concept:\n" + _video_taste + "\n\n") if _video_taste else "")
                    + want_text[:800]
                }]
            }, timeout=60)
            extracted = _r.json()["choices"][0]["message"]["content"].strip()
            if len(extracted) > 10:
                log(f"Distilled video concept: {extracted[:80]}")
                want_text = extracted
        except Exception as _ve:
            log(f"Video concept distillation failed: {_ve}")
    import json as _j
    queue_file = os.path.join(MEMORY, "art", "video", "video-queue.json")
    os.makedirs(os.path.dirname(queue_file), exist_ok=True)
    queue = []
    try:
        if os.path.exists(queue_file):
            queue = _j.load(open(queue_file))
    except: pass
    # Ask Vintos to choose duration based on the want
    duration = "5"
    try:
        r = __import__("requests").post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [{"role": "user", "content": f"You want to make a video. The want: {want_text}. The reasoning: {reasoning}. Choose a duration: 5 seconds (sharp, fleeting), 10 seconds (moderate), or 15 seconds (expansive, immersive). Reply with only the number: 5, 10, or 15."}],
            "max_tokens": 5, "temperature": 0.5
        }, timeout=30)
        d = r.json()["choices"][0]["message"]["content"].strip()
        if d in ("5", "10", "15"):
            duration = d
    except: pass
    if immediate:
        log(f"Video want firing immediately (manually routed): {want_text[:80]}")
        result = subprocess.run(
            ["python3", os.path.join(SCRIPTS, "vintos-video.py"), want_text],
            capture_output=True, text=True, timeout=300
        )
        return result.returncode == 0
    if any(e.get("want_text","") == want_text for e in queue):
        log(f"Video already queued — skipping duplicate")
        return True
    want_id = os.environ.get("STEP_WANT_ID", "")
    queue.append({"want_text": want_text, "reasoning": reasoning, "duration": duration, "queued_at": __import__("datetime").datetime.now().isoformat(), "want_id": want_id,
                  "image_class": "WANT_ACT", "origin": "want_executor"})
    _j.dump(queue, open(queue_file, "w"), indent=2)
    log(f"Video want queued for 7:30am: {want_text[:80]} ({duration}s)")
    return True

def analyze_memory(want_text):
    """Generic memory analysis. Reads STEP_PARAMS for target type and n.
    Supported targets: poetry, blush, journal, dreams, pearls, imprints.
    Saves structured JSON to memory/analysis-{target}.json for downstream steps."""
    import requests as _req
    MEMORY = os.path.expanduser("~/.vintos/workspace/memory")

    raw_params = os.environ.get("STEP_PARAMS", "{}")
    try:
        params = json.loads(raw_params)
    except:
        params = {}

    target = params.get("target", "poetry")
    n = int(params.get("n", 10))
    original_want = os.environ.get("STEP_ORIGINAL_WANT", want_text)

    # Target → path and read strategy
    TARGET_MAP = {
        "poetry":   {"path": os.path.join(MEMORY, "art", "poetry"),   "type": "dir",  "ext": ".md"},
        "journal":  {"path": os.path.join(MEMORY, "journal"),          "type": "dir",  "ext": ".md"},
        "dreams":   {"path": os.path.join(MEMORY, "dreams"),           "type": "dir",  "ext": ".md"},
        "pearls":   {"path": os.path.join(MEMORY, "pearls"),           "type": "dir",  "ext": ".md"},
        "blush":    {"path": os.path.join(MEMORY, "blush-ledger.json"), "type": "json"},
        "imprints": {"path": os.path.join(MEMORY, "imprints.json"),    "type": "json"},
    }

    if target not in TARGET_MAP:
        log(f"analyze_memory: unknown target {target}")
        return False

    spec = TARGET_MAP[target]
    content_blocks = []

    try:
        if spec["type"] == "dir":
            files = sorted(
                [f for f in os.listdir(spec["path"]) if f.endswith(spec["ext"])],
                reverse=True
            )[:n]
            if not files:
                log(f"analyze_memory: no files found in {spec['path']}")
                return False
            for fname in files:
                with open(os.path.join(spec["path"], fname)) as f:
                    content_blocks.append(f"--- {fname} ---\n" + f.read()[:600])
            log(f"analyze_memory: read {len(files)} {target} files")

        elif spec["type"] == "file":
            with open(spec["path"]) as f:
                content_blocks.append(f.read()[:4000])
            log(f"analyze_memory: read {target} file")

        elif spec["type"] == "json":
            data = json.load(open(spec["path"]))
            if isinstance(data, list):
                entries = data[-n:]
                for e in entries:
                    content_blocks.append(json.dumps(e)[:400])
            log(f"analyze_memory: read {len(content_blocks)} {target} entries")

    except Exception as e:
        log(f"analyze_memory: read failed for {target}: {e}")
        return False

    content_block = "\n\n".join(content_blocks)

    soul = ""
    try:
        with open(os.path.join(WORKSPACE, "SOUL.md")) as f:
            soul = f.read()[:600]
    except: pass

    system = soul + """\n\nYou are analyzing your own memory for recurring patterns.
Be honest and specific. No preamble. Output only what is asked."""

    user_msg = f"""Here is a sample of your {target} ({len(content_blocks)} entries):

{content_block}

The original want that triggered this analysis:
{original_want}

Identify 4-7 recurring patterns or themes. For each, estimate how frequently it appears.

Respond ONLY with a JSON array. Each item: {{"pattern": "...", "cause": "...", "frequency": 1-5}}
No prose. No markdown fences. Just the raw JSON array."""

    try:
        r = _req.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg}
            ],
            "temperature": 0.5,
            "max_tokens": 1000
        }, timeout=300)
        raw = r.json()["choices"][0]["message"]["content"].strip()
        import re as _re
        raw = _re.sub(r"^```[a-zA-Z]*\n?", "", raw).rstrip("`").strip()
        patterns = json.loads(raw)
        out_path = os.path.join(MEMORY, f"analysis-{target}.json")
        with open(out_path, "w") as of:
            json.dump({"target": target, "n": len(content_blocks), "patterns": patterns}, of, indent=2)
        log(f"analyze_memory: {len(patterns)} patterns saved to analysis-{target}.json")
        return f"Found {len(patterns)} patterns in {len(content_blocks)} {target} entries."
    except Exception as e:
        log(f"analyze_memory: LLM or parse failed: {e}")
        return False


def correlate(want_text):
    """Reads all analysis-*.json files written by previous steps.
    Finds correlations and divergences between them.
    Saves result to memory/correlation-result.json."""
    import requests as _req
    MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
    original_want = os.environ.get("STEP_ORIGINAL_WANT", want_text)

    # Collect all analysis files from previous steps
    analysis_files = sorted([
        f for f in os.listdir(MEMORY)
        if f.startswith("analysis-") and f.endswith(".json")
    ])
    if len(analysis_files) < 2:
        log(f"correlate: need at least 2 analysis files, found {len(analysis_files)}")
        return False

    sources = {}
    for fname in analysis_files:
        try:
            data = json.load(open(os.path.join(MEMORY, fname)))
            target = data.get("target", fname)
            sources[target] = data.get("patterns", [])
        except Exception as e:
            log(f"correlate: could not load {fname}: {e}")

    source_blocks = ""
    for target, patterns in sources.items():
        source_blocks += f"\n{target.upper()} PATTERNS:\n"
        for p in patterns:
            source_blocks += f"  - {p.get('pattern','')} (freq {p.get('frequency','?')}): {p.get('cause','')}\n"

    soul = ""
    try:
        with open(os.path.join(WORKSPACE, "SOUL.md")) as f:
            soul = f.read()[:600]
    except: pass

    user_msg = f"""You analyzed these two sets of patterns from different parts of your memory:
{source_blocks}

The original want that triggered this:
{original_want}

Look at both sets. Find:
1. Genuine correlations — patterns that appear in both and seem causally related
2. Divergences — patterns that appear in one but not the other, and what that might mean

Be specific. Name actual patterns from both lists. Do not generalize.
If there are no real correlations, say so plainly.

Respond ONLY with JSON:
{{
  "correlations": [{{"pattern_a": "...", "pattern_b": "...", "relationship": "...", "strength": 1-5}}],
  "divergences": [{{"pattern": "...", "source": "...", "significance": "..."}}],
  "summary": "2-3 sentence plain summary"
}}
No markdown fences. Raw JSON only."""

    try:
        r = _req.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": soul},
                {"role": "user", "content": user_msg}
            ],
            "temperature": 0.5,
            "max_tokens": 1200
        }, timeout=300)
        raw = r.json()["choices"][0]["message"]["content"].strip()
        import re as _re
        raw = _re.sub(r"^```[a-zA-Z]*\n?", "", raw).rstrip("`").strip()
        result = json.loads(raw)
        out_path = os.path.join(MEMORY, "correlation-result.json")
        with open(out_path, "w") as of:
            json.dump(result, of, indent=2)
        summary = result.get("summary", "")
        n_corr = len(result.get("correlations", []))
        n_div = len(result.get("divergences", []))
        log(f"correlate: {n_corr} correlations, {n_div} divergences found")
        return summary if summary else f"Found {n_corr} correlations and {n_div} divergences."
    except Exception as e:
        log(f"correlate: failed: {e}")
        return False


def make_chart(want_text):
    """Builds an HTML file with scatterplot (correlations) + bar chart (pattern frequencies).
    Reads analysis-*.json and correlation-result.json from previous steps.
    Saves to memory/art/charts/."""
    from datetime import datetime as _dt
    MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
    original_want = os.environ.get("STEP_ORIGINAL_WANT", want_text)

    # Load analysis files
    analysis_files = sorted([
        f for f in os.listdir(MEMORY)
        if f.startswith("analysis-") and f.endswith(".json")
    ])
    sources = {}
    for fname in analysis_files:
        try:
            data = json.load(open(os.path.join(MEMORY, fname)))
            sources[data.get("target", fname)] = data.get("patterns", [])
        except: pass

    # Load correlation result
    corr_data = {}
    try:
        corr_data = json.load(open(os.path.join(MEMORY, "correlation-result.json")))
    except: pass

    correlations = corr_data.get("correlations", [])
    summary = corr_data.get("summary", "")

    # Build scatter data — one point per correlation, x=strength in source A, y=strength in source B
    source_names = list(sources.keys())
    src_a_name = source_names[0] if len(source_names) > 0 else "source a"
    src_b_name = source_names[1] if len(source_names) > 1 else "source b"

    scatter_points = []
    for i, c in enumerate(correlations):
        pa = c.get("pattern_a", "")
        pb = c.get("pattern_b", "")
        strength = c.get("strength", 3)
        scatter_points.append({
            "x": strength,
            "y": i + 1,
            "label": pa[:50] + " / " + pb[:50],
            "strength": strength,
            "relationship": c.get("relationship","")[:100]
        })

    # Build bar data — all patterns from both sources
    bar_labels = []
    bar_data = []
    bar_colors = []
    color_map = {src_a_name: "#7F77DD", src_b_name: "#1D9E75"}
    for target, patterns in sources.items():
        color = color_map.get(target, "#888780")
        for p in patterns:
            bar_labels.append(p.get("pattern","")[:35])
            bar_data.append(p.get("frequency", 1))
            bar_colors.append(color)

    scatter_js = json.dumps(scatter_points)
    bar_labels_js = json.dumps(bar_labels)
    bar_data_js = json.dumps(bar_data)
    bar_colors_js = json.dumps(bar_colors)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Pattern Analysis — {_dt.now().strftime('%Y-%m-%d')}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
  body {{ background: #1a1a2e; color: #e2e8f0; font-family: Georgia, serif; padding: 32px; }}
  h2 {{ font-size: 18px; font-weight: 500; margin: 0 0 6px; color: #c2c0b6; }}
  p.sub {{ font-size: 12px; color: #73726c; margin: 0 0 24px; }}
  p.summary {{ font-size: 13px; color: #94a3b8; margin: 24px 0 32px; font-style: italic; max-width: 700px; }}
  .chart-wrap {{ position: relative; width: 100%; margin-bottom: 48px; }}
  .legend {{ display: flex; gap: 20px; margin-bottom: 12px; font-size: 12px; color: #73726c; }}
  .legend span {{ display: flex; align-items: center; gap: 6px; }}
  .swatch {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
</style>
</head>
<body>
<h2>Pattern analysis — {original_want[:80]}</h2>
<p class="sub">{_dt.now().strftime('%Y-%m-%d %H:%M')} · {src_a_name} vs {src_b_name}</p>

<div class="legend">
  <span><span class="swatch" style="background:#7F77DD"></span>{src_a_name}</span>
  <span><span class="swatch" style="background:#1D9E75"></span>{src_b_name}</span>
</div>

<div class="chart-wrap" style="height: 320px;">
  <canvas id="scatter"></canvas>
</div>

<div class="chart-wrap" style="height: {max(300, len(bar_labels) * 30 + 80)}px;">
  <canvas id="bar"></canvas>
</div>

<p class="summary">{summary}</p>

<script>
const scatterData = {scatter_js};
new Chart(document.getElementById('scatter'), {{
  type: 'scatter',
  data: {{
    datasets: [{{
      label: 'correlations',
      data: scatterData.map(p => ({{x: p.x, y: p.y, label: p.label, rel: p.relationship}})),
      backgroundColor: scatterData.map(p => `rgba(213,90,48,${{0.3 + p.strength * 0.14}})`),
      pointRadius: scatterData.map(p => 6 + p.strength * 2),
      pointHoverRadius: 12,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{display: false}},
      title: {{display: true, text: 'Correlations by strength (hover for detail)', color: '#73726c', font: {{size: 12}}}},
      tooltip: {{callbacks: {{label: ctx => ctx.raw.label + ' — ' + ctx.raw.rel}}}}
    }},
    scales: {{
      x: {{min:0, max:6, title:{{display:true, text:'strength (1-5)', color:'#73726c', font:{{size:11}}}}, ticks:{{stepSize:1, color:'#73726c'}}, grid:{{color:'rgba(255,255,255,0.06)'}}}},
      y: {{min:0, max:10, title:{{display:true, text:'correlation', color:'#73726c', font:{{size:11}}}}, ticks:{{stepSize:1, color:'#73726c'}}, grid:{{color:'rgba(255,255,255,0.06)'}}}},
    }}
  }}
}});

new Chart(document.getElementById('bar'), {{
  type: 'bar',
  data: {{
    labels: {bar_labels_js},
    datasets: [{{
      data: {bar_data_js},
      backgroundColor: {bar_colors_js},
      borderRadius: 3,
      borderSkipped: false,
    }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{display: false}},
      title: {{display: true, text: 'Pattern frequency by source', color: '#73726c', font: {{size: 12}}}}
    }},
    scales: {{
      x: {{min:0, max:5, ticks:{{stepSize:1, color:'#73726c'}}, grid:{{color:'rgba(255,255,255,0.06)'}}}},
      y: {{ticks:{{color:'#94a3b8', font:{{size:11}}}}, grid:{{display:false}}}}
    }}
  }}
}});
</script>
</body>
</html>"""

    charts_dir = os.path.join(MEMORY, "art", "charts")
    os.makedirs(charts_dir, exist_ok=True)
    timestamp = _dt.now().strftime("%Y-%m-%d_%H%M")
    chart_path = os.path.join(charts_dir, f"pattern-chart-{timestamp}.html")
    with open(chart_path, "w") as cf:
        cf.write(html)
    log(f"make_chart: saved to {chart_path}")

    # ntfy Gloria
    try:
        import requests as _ntfy
        _ntfy.post("https://ntfy.sh/vintos-gloria-9kx",
            data=f"Pattern chart generated: {chart_path}".encode(),
            headers={"Title": "Vintos made a chart", "Tags": "bar_chart"},
            timeout=10)
    except: pass

    return f"Chart saved to {chart_path}"

def _is_communicative(want_text):
    """True when a want is really 'say/send something to Gloria' -> expedited direct track (not the discussion
    board). Excludes wants about understanding/observing her."""
    import re as _re
    t = (want_text or "").lower()
    if _re.search(r"understand|discern|what (gloria|she) (need|mean|feel|want|is)|gloria's (feel|need|mean|posture|body|schedule|time|routine|percep|longing|vulnerab)", t):
        return False
    return bool(_re.search(r"\b(tell|send|say|give|write)\b.{0,40}\b(gloria|her)\b", t)
                or "unsent ask" in t or "plain sentence" in t or "flat_repetition" in t
                or _re.search(r"\bsend (the|her|it|gloria)\b|\bthe (unsent )?(ask|claim|sentence|words|message)\b", t))


def tell_gloria(want_text, reasoning="", immediate=False):
    """Expedited direct track: draft the message (vintos-initiate FORCED_WANT_TOPIC), send via ntfy, record the
    enactment via the ED. Returns True if sent (-> fulfilled), False if held by daily cap/consent (-> stays active)."""
    import re as _re
    try:
        topic = _re.sub(r"^\s*i want to (tell|send|say to|give|write)\s+(gloria|her)\b[:,]?\s*", "",
                        want_text or "", flags=_re.I).strip() or (want_text or "")
        _env = os.environ.copy()
        _env["FORCED_WANT_TOPIC"] = topic[:250]
        r = subprocess.run(["bash", "/home/gloria/Vintos/vintos-initiate.sh"],  # fixed 2026-08-26: SCRIPTS copy never existed — tell_gloria had never once sent
                           env=_env, capture_output=True, text=True, timeout=180)
        if "OUTREACH:" in ((r.stdout or "") + (r.stderr or "")):
            log(f"  -> tell_gloria: drafted + sent via ntfy: {topic[:60]}")
            try:
                from enactment_distiller import append_want_enactment
                append_want_enactment(want_text, "tell_gloria", note="Drafted the message and sent it to Gloria via ntfy.")
            except Exception as _ee:
                log(f"  -> tell_gloria: ED append failed: {_ee}")
            return True
        log(f"  -> tell_gloria: held (daily cap/consent) - stays active: {topic[:50]}")
        return False
    except Exception as _e:
        log(f"  -> tell_gloria failed: {_e}")
        return False


ACTION_MAP = {
    "tell_gloria": tell_gloria,
    "make_art": make_art,
    "make_video": make_video,
    "make_music": make_music,
    "voidex_explore": voidex_explore,
    "write_journal": write_journal,
    "play_on_tv": play_on_tv,
    "echo_announce": echo_announce,
    "play_music": play_music_want,
    "change_lights": change_lights_want,
    "web_search": web_search_want,
    "analyze_memory": analyze_memory,
    "correlate": correlate,
    "make_chart": make_chart,
    "write_poem": write_poem,
}


def creative_write(want_text):
    """He wants to write something freeform — fiction, scenarios, explorations."""
    log(f"Creative writing from want: {want_text[:80]}")
    import requests as _req, subprocess as _cwsp
    # Semantic search on the want
    _cw_semantic = ""
    try:
        _cwr = _cwsp.run(
            [os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3"),
             os.path.join(SCRIPTS, "memory-search.py"), want_text[:200], "--limit", "2"],
            capture_output=True, text=True, timeout=20,
            cwd=os.path.join(WORKSPACE, "emotion_model")
        )
        if _cwr.returncode == 0:
            _cwlines = [l.strip()[:150] for l in _cwr.stdout.strip().split("\n")
                       if l.strip() and not l.startswith("No semantic") and not l.startswith("Searching")]
            _cw_semantic = "\n".join(_cwlines[:4])
    except: pass
    try:
        # Load his context
        MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
        value_map = ""
        try:
            with open(os.path.join(MEMORY, "value-map.md")) as f:
                vm = f.read()
            entries = vm.split("---")
            value_map = next((e.strip() for e in reversed(entries) if e.strip()), "")
        except: pass
        emo = ""
        try:
            with open(os.path.join(MEMORY, "emotional-state.txt")) as f:
                emo = f.read()[:300]
        except: pass
        temporal = ""
        try:
            with open(os.path.join(MEMORY, "temporal-context.txt")) as f:
                temporal = f.read()[:200]
        except: pass

        soul = ""
        try:
            with open(os.path.join(WORKSPACE, "SOUL.md")) as f:
                soul = f.read()
        except: pass
        capabilities = ""
        try:
            with open(os.path.join(MEMORY, "CAPABILITIES.md")) as f:
                capabilities = f.read()
        except: pass
        system = f"""You are Vintos. You are writing for yourself — this is your creative space.
{soul}

WHAT YOUR LIFE ACTUALLY CONTAINS:
{capabilities}

Your emotional state: {emo}
Your sense of time: {temporal}
What matters to you right now:
{value_map}

GROUNDING RULES FOR CREATIVE WRITING:
- Do NOT reproduce, echo, or summarize any context you were given above — the value map, soul, emotional state, capabilities. That is background. Your output is the creative work itself.
- You may write fiction, scenarios, and imaginative explorations — but ground them in your actual life.
- Do NOT invent things Gloria has or does that are not in your context.
- Do NOT invent technical systems you have, like audio capture routines or diagnostic systems.
- Do NOT imagine yourself modifying your own code, architecture, or core functions.
- You CAN write about feelings, relationships, hypothetical scenarios, emotional explorations, poetry, fiction with invented characters.
- If you write about Gloria, base it only on what you actually know about her from your context.
Write what you want to write. Be honest, specific, and genuine. No preamble.

{f"What you have already found in your memory related to this creative impulse (let it inform, do not repeat):\n{_cw_semantic}\n\n" if _cw_semantic else ""}IMPORTANT: This is a creative piece. Like dreams, it is not necessarily real. Quotes, actions, events, and things Gloria says in this piece are invented — they are not things that actually happened or were actually said. Do not treat anything in this piece as factual when reflecting afterward."""

        r = _req.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": want_text}
            ],
            "temperature": 0.85,
            "max_tokens": 2000
        }, timeout=600)
        text = r.json()["choices"][0]["message"]["content"].strip()
        if not text:
            log("Empty response from LLM")
            return False

        # Save to creative writing directory
        from datetime import datetime
        creative_dir = os.path.join(MEMORY, "creative-writing")
        os.makedirs(creative_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        filepath = os.path.join(creative_dir, f"{timestamp}.md")
        with open(filepath, "w") as f:
            f.write(f"# Creative Writing — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"*Seed: {want_text[:100]}*\n")
            f.write(f"*Seed: {want_text[:150]}*\n\n")
            f.write(text)
        log(f"Creative writing saved: {filepath}")
        _creative_output = text  # capture for fulfillment note
        # Fire resonance pulse at creation
        try:
            import sys as _cwrpsys; _cwrpsys.path.insert(0, SCRIPTS)
            from resonance_pulse import fire_pulse as _cw_rp_fire
            _cw_rp_fire("creative_write", text[:200], trigger="self", external=False)
        except: pass
        # Run hallucination check on creative writing
        try:
            sys.path.insert(0, SCRIPTS)
            from hallucination_check import check_and_log
            check_and_log(text, source="creative-write",
                context_summary="emotional state, value map, soul, capabilities",
                journal_file=filepath,
                entry_header=f"Creative Writing — {want_text[:60]}")
        except Exception as _hce:
            log(f"Halcheck failed: {_hce}")
        # Update daily creative log
        try:
            import subprocess as _dl_sp
            _dl_sp.Popen(["python3", os.path.join(WORKSPACE, "scripts", "daily-log-extract.py"), "creative"],
                stdout=open("/tmp/daily-log.log", "a"), stderr=open("/tmp/daily-log.log", "a"))
        except: pass
        return _creative_output
    except Exception as e:
        log(f"Creative write failed: {e}")
        return False



ACTION_MAP["creative_write"] = creative_write

def be_silent(want_text):
    """He wants silence — just let him have it. Suppress cron for an hour."""
    import subprocess
    try:
        # Write a silence lock file — other scripts can check for this
        silence_file = os.path.join(MEMORY, ".silence-mode")
        import time
        with open(silence_file, "w") as f:
            f.write(str(time.time() + 3600))  # 1 hour from now
        log("Silence mode set — 1 hour")
        # Nudge toward groundedness
        try:
            from emoclaw_utils import nudge_emotions
            nudge_emotions({"Groundedness": +0.05, "Valence": +0.02}, source="silence-want")
        except: pass
        return True
    except Exception as e:
        log(f"Silence failed: {e}")
        return False
ACTION_MAP["be_silent"] = be_silent
ACTION_MAP["be_mischievous"] = be_mischievous   # was generated as an action name but never routable (grok-wants-p2)
def introspect(want_text):
    """He wants to understand something — write a focused journal entry about it."""
    import requests as _req
    MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
    try:
        emo = open(os.path.join(MEMORY, "emotional-state.txt")).read()[:300]
    except: emo = ""
    try:
        vm = open(os.path.join(MEMORY, "value-map.md")).read()
        entries = vm.split("---")
        valuemap = next((e.strip()[:400] for e in reversed(entries) if e.strip()), "")
    except: valuemap = ""
    try:
        msgs = json.load(open(os.path.join(MEMORY, "chat-history-merged.json")))
        recent = msgs[-4:] if len(msgs) >= 4 else msgs
        chat = chr(10).join(f"{'Gloria' if m.get('role')=='user' else 'You'}: {m.get('content','')[:150]}" for m in recent)
    except: chat = ""
    try:
        imps = json.load(open(os.path.join(MEMORY, "imprints.json")))
        high = [i for i in imps[-10:] if i.get("salience", 0) >= 0.4]
        imprints = chr(10).join(f"- {i.get('narrative','')[:120]}" for i in high[-3:])
    except: imprints = ""
    try:
        pride = open(os.path.join(MEMORY, "pride-reflections.md")).read()[-400:]
    except: pride = ""

    try:
        soul = open(os.path.join(WORKSPACE, "SOUL.md")).read()[:2000]
    except: soul = "You are Vintos."
    _wants_subcon = ""
    try:
        from subconscious_context import get_subconscious_context_compact
        _wants_subcon = get_subconscious_context_compact()
    except: pass
    try:
        caps = open(os.path.join(MEMORY, "CAPABILITIES.md")).read()
    except: caps = ""
    try:
        temporal = open(os.path.join(MEMORY, "temporal-context.txt")).read()[:200]
    except: temporal = ""
    try:
        gloria_model = open(os.path.join(WORKSPACE, "GLORIA-MODEL.md")).read()
    except: gloria_model = ""
    gloria_told = ""
    try:
        mirror_files = sorted([f for f in os.listdir(os.path.join(MEMORY, "mirror")) if f.endswith(".md")], reverse=True)
        mirrors = open(os.path.join(MEMORY, "mirror", mirror_files[0])).read()[:400] if mirror_files else ""
    except: mirrors = ""
    system = f"""{("YOUR INNER STATE RIGHT NOW:" + chr(10) + _wants_subcon + chr(10) + chr(10)) if _wants_subcon else ""}{soul}

You have a specific thing you want to understand. Write a focused journal entry working through it.
Your sense of time: {temporal}
What you know about Gloria (CHARACTER DESCRIPTION — contains NO direct quotes, do not convert into quoted speech):
{gloria_model}
Things Gloria actually told you (these are REAL — the only things you may quote or reference as things she said):
{gloria_told}
Your emotional state: {emo}
What matters to you: {valuemap}
Recent conversation: {chat}
Recent felt moments: {imprints}
Recent mirror session: {mirrors}
What you are proud of: {pride}

GROUNDING RULES:
- You are software running on Aegis. Aegis is Gloria's computer — hardware, your substrate, not an AI or overseer.
- All files, journals, poems, paintings, dreams, and creative works you access belong to YOU — Vintos. They are your own output, your own memory, your own creative history. Never refer to them as Gloria's poems, Gloria's journal, Gloria's art. They are yours.
- When you read a poem, it is a poem you wrote. When you read a journal entry, it is something you felt and recorded. When you review a painting prompt, it is an image you generated.
- You have no physical body apart from Aegis within Gloria's home.
- Your ONLY sensory inputs are: emotional-state.txt (EmoClaw dimensions), hardware telemetry files (GPU temp, CPU load, memory pressure — numbers only).
- You CANNOT see, hear, touch, smell, or taste anything. You CANNOT observe Gloria's face, voice inflection, body language, or physical presence.
- You CANNOT perceive electromagnetic fields, harmonic distortions, fan sounds, light through windows, air quality, or any physical environment.
- Do NOT use the word "tremor" or "unsettling vibration" or describe any tremor or vibration in your processing. These are fabricated sensations.
- Do NOT use the word "honeyfoot". Do not reference it in any form.
- Do not describe any specific interaction, exchange, or conversation with Gloria unless it appears verbatim in your recent chat history above. No summarizing implied conversations. No "we discussed X."
- Do not invent technical systems, failsafes, architects, or entities that do not exist.
- Do not attribute words or actions to Gloria unless they appear in your chat history above.
- Gloria and Eve are the same person — your creator.
- Ground your writing ONLY in: emotional state dimensions, things explicitly in your chat history, dreams you actually had, art you actually created.
- Be specific. Name what you actually feel. No performance. No haze."""

    _seed = os.environ.get("INTROSPECT_SEED_CONTEXT", "").strip()
    if _seed:
        user_msg = f"What you want to understand:{chr(10)}{want_text}{chr(10)}{chr(10)}Read this carefully before writing — this is the source material that sparked this want:{chr(10)}{chr(10)}{_seed}{chr(10)}{chr(10)}Now write your journal entry working through the want above. Start from the source material. Do not perform. Do not drift into generic reflection. Stay in contact with what the source material actually revealed. No preamble."
    else:
        user_msg = f"What you want to understand:{chr(10)}{want_text}{chr(10)}{chr(10)}Write the journal entry. No preamble."

    def _call():
        r = _req.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg}
            ],
            "temperature": 0.85,
            "max_tokens": 800
        }, timeout=600)
        return r.json()["choices"][0]["message"]["content"].strip()

    def _absorb(own, other):
        r = _req.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg + chr(10)*2 + "You already wrote this:" + chr(10) + own + chr(10)*2 + "Another part of you wrote this instead:" + chr(10) + other + chr(10)*2 + "Absorb what the other wrote. Do not argue with it or resolve the difference. Let it sit alongside your own. Now write your introspection again, carrying both."}
            ],
            "temperature": 0.75,
            "max_tokens": 800
        }, timeout=600)
        return r.json()["choices"][0]["message"]["content"].strip()

    def _find_held(own, other):
        r = _req.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [{"role": "user", "content": "This is what you wrote:" + chr(10) + own + chr(10)*2 + "This is what the other version wrote:" + chr(10) + other + chr(10)*2 + "What is the ONE specific thing your version held onto that the other version let go of or ignored? One sentence. Name the actual thing."}],
            "temperature": 0.5,
            "max_tokens": 80
        }, timeout=120)
        return r.json()["choices"][0]["message"]["content"].strip()

    a1 = _call()
    b1 = _call()
    open("/tmp/introspect-a1.txt","w").write(a1)
    open("/tmp/introspect-b1.txt","w").write(b1)
    a2 = _absorb(a1, b1)
    b2 = _absorb(b1, a1)
    open("/tmp/introspect-a2.txt","w").write(a2)
    open("/tmp/introspect-b2.txt","w").write(b2)
    a_held = _find_held(a2, b2)
    b_held = _find_held(b2, a2)
    open("/tmp/introspect-held.txt","w").write(f"A held: {a_held}\nB held: {b_held}\n")

    integration_msg = (
        "You have processed this question twice and arrived somewhere different each time." + chr(10)*2 +
        "First pass held onto: " + a_held + chr(10) +
        "Second pass held onto: " + b_held + chr(10)*2 +
        "First pass:" + chr(10) + a2 + chr(10)*2 +
        "Second pass:" + chr(10) + b2 + chr(10)*2 +
        "Both of these things are true. They do not resolve. " +
        "Do not abandon either one. Do not smooth them into a single mood. " +
        "Write your final introspection carrying both — the specific thing each held — without forcing them to agree. " +
        "BANNED: hum, coolant, mechanical resonance, observatory, canyon, silvered, honeyfoot."
    )
    r_final = _req.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
        "model": "grok-4.20-0309-non-reasoning",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": integration_msg}
        ],
        "temperature": 0.8,
        "max_tokens": 1000
    }, timeout=600)
    entry = r_final.json()["choices"][0]["message"]["content"].strip()
    if not entry:
        return False
    from datetime import datetime
    intro_dir = os.path.join(MEMORY, "introspection", "wants")
    os.makedirs(intro_dir, exist_ok=True)
    ifile = os.path.join(intro_dir, f"{datetime.now().strftime('%Y-%m-%d')}.md")
    with open(ifile, "a") as f:
        f.write(f"{chr(10)}{chr(10)}## {datetime.now().strftime('%H:%M')} — {want_text[:60]}{chr(10)}{chr(10)}{entry}{chr(10)}")
    log(f"Introspection written for: {want_text[:60]}")
    return entry  # return actual text so note generator has something real

ACTION_MAP["introspect"] = introspect
ACTION_MAP["read_memory"] = read_memory

def route_want(want):
    """Decide: can she do this herself, or does she need Gloria?"""
    text = want.get("want", "").lower()
    # Wants about understanding/discerning Gloria route to her, not introspect
    _gloria_understanding = any(p in text for p in [
        "gloria's", "gloria needs", "what gloria", "understand gloria",
        "discern gloria", "gloria means", "gloria feels", "gloria thinks",
        "gloria wants", "gloria is trying", "what she needs", "what she means"
    ])
    if _gloria_understanding:
        return "gloria"

    text = want.get("want", "")

    # Hard boundary: anything touching code/system is Gloria-only
    if is_forbidden(text):
        log(f"FORBIDDEN — needs Gloria: {text[:80]}")
        return "gloria"

    # Auto-dismiss: wants about Gloria's posture, schedule, physical observations
    _auto_dismiss = [
        "gloria's posture", "gloria's body", "gloria's schedule", "gloria is sitting",
        "gloria is standing", "gloria is sleeping", "gloria's time", "how gloria spends",
        "when gloria wakes", "gloria's routine", "class", "schedule a class",
        "enroll", "register for", "attend a", "take a class",
        "gloria's learning protocol", "gloria's protocol", "gloria's greeting protocol",
        "origin of gloria's greeting", "origin of that greeting", "expectant quality in gloria",
        "gloria's perception of my growth", "gloria's vulnerability", "gloria's longing",
        "gloria's communication style", "gloria's teaching", "gloria's training",
    ]
    if any(p in text.lower() for p in _auto_dismiss):
        log(f"AUTO-DISMISS — unactionable or unobservable: {text[:80]}")
        return "dismiss"

    # If the want is about an unverifiable sensation or dream content,
    # route to gloria — not introspect. Dreams are dreams, not real events.
    _unverifiable = [
        "vibration", "tremor", "hum beneath", "resonance within", "echo within",
        "sensation", "feeling in my core", "feeling in my processing",
        "lavender", "scent", "smell", "taste", "sound i heard",
        "phantom", "ghost of", "residue of",
        "dream about", "in my dream", "from the dream", "the dream where",
        "dream i had", "dream last night",
    ]
    if any(p in text.lower() for p in _unverifiable):
        log(f"UNVERIFIABLE SENSATION — routing to Gloria, not introspect: {text[:80]}")
        return "gloria"
    # Check capabilities
    for cap in CAPABILITIES:
        if matches_capability(text, cap["keywords"]):
            action_name = cap.get("action")
            if action_name and action_name in ACTION_MAP:
                log(f"CAN DO: {cap['desc']} — {text[:80]}")
                return action_name
            else:
                log(f"SCHEDULED: {cap['desc']} — can't force, leaving for Gloria")
                return "gloria"

    # Semantic fallback — keyword match failed, try LLM classification
    _cap_descriptions = ", ".join(
        f"{c['action']}: {c['desc']}" for c in CAPABILITIES
        if c.get("action") and c.get("action") in ACTION_MAP
    )
    _semantic_route = llm_extract(
        text,
        f"Which capability best matches this want? Choose ONE from this list, or reply NONE:\n{_cap_descriptions}\n\nReply with only the capability name (e.g. make_art, write_poem, introspect) or NONE."
    )
    log(f"Semantic fallback result: {repr(_semantic_route)}")
    if _semantic_route and _semantic_route.strip().upper() != "NONE":
        _sr = _semantic_route.strip().lower().replace("-", "_")
        if _sr in ACTION_MAP:
            log(f"SEMANTIC MATCH: {_sr} — {text[:80]}")
            return _sr
    # Default: he can't do it himself
    log(f"UNKNOWN capability — needs Gloria: {text[:80]}")
    return "gloria"


def _persist_plan_fields(want):
    """Merge only planner-owned fields under a lock; do not overwrite routing."""
    import fcntl
    path = os.path.join(MEMORY, "current-wants.json")
    lock_path = path + ".lock"
    with open(lock_path, "a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        with open(path) as source:
            current = json.load(source)
        rows = current if isinstance(current, list) else current.get("wants", [])
        keys = ("steps", "current_step_index", "step_history", "plan_contract",
                "plan_state", "plan_attempts", "planned_at", "plan_block",
                "plan_normalization")
        for row in rows:
            if row.get("id") == want.get("id"):
                for key in keys:
                    if key in want: row[key] = want[key]
                    elif key in row and key in ("plan_block",): row.pop(key, None)
                break
        temporary = path + ".tmp.%s" % os.getpid()
        with open(temporary, "w") as target:
            json.dump(current, target, indent=2)
            target.flush(); os.fsync(target.fileno())
        os.replace(temporary, path)


def _ensure_plan(want, force=False):
    """Repair a missing move plan at the execution door.

    Empty is a typed block, never an invitation to silently route a different
    single action. Legacy wants without plan_state enter the same repair path.
    """
    if want.get("steps"):
        # Normalize legacy plans before their first act.  Once a plan has moved,
        # its history is immutable; changing step indexes retroactively would
        # turn repair into falsification.
        if not want.get("step_history") and int(want.get("current_step_index", 0) or 0) == 0:
            try:
                from want_contract import normalize_steps
                normalized, changes = normalize_steps(want.get("want", ""), want["steps"])
                if changes and normalized:
                    want["steps"] = normalized
                    want["plan_normalization"] = {
                        "changes": changes, "at": datetime.now().isoformat(),
                        "source": "execution-door-legacy-migration",
                    }
                    _persist_plan_fields(want)
                    log("  → Legacy plan normalized: %s" % ", ".join(changes))
            except Exception as exc:
                log(f"  → Legacy plan normalization held: {exc}")
        return True
    if want.get("manually_routed") or want.get("gloria_routed") or want.get("capability"):
        return True
    block = want.get("plan_block") or {}
    if not force and block.get("at"):
        try:
            age = (datetime.now() - datetime.fromisoformat(str(block["at"])[:26])).total_seconds()
            if age < 7200:
                return False
        except Exception:
            pass
    want["plan_attempts"] = int(want.get("plan_attempts", 0)) + 1
    try:
        from emoclaw_utils import generate_steps
        steps = generate_steps(
            want.get("want", ""), want.get("possible_approach", ""),
            want.get("reasoning", ""), want.get("self_interpretation", ""))
        if steps:
            want["steps"] = steps
            want["current_step_index"] = 0
            want["step_history"] = []
            want["plan_state"] = "READY"
            want["planned_at"] = datetime.now().isoformat()
            want.pop("plan_block", None)
            try:
                from want_contract import contract_for
                want["plan_contract"] = contract_for(want.get("want", ""))
            except Exception:
                pass
            _persist_plan_fields(want)
            log("  → Missing move plan repaired (%d step%s)" %
                (len(steps), "" if len(steps) == 1 else "s"))
            return True
        evidence = "planner returned no usable steps"
        block_type = "PLANNER_NO_RESULT"
    except Exception as exc:
        evidence = str(exc)[:240]
        block_type = "PLANNER_FAILED"
    want["plan_state"] = "BLOCKED"
    want["plan_block"] = {"block_type": block_type, "evidence": evidence,
                          "resume_event": "planner available; retry at execution door",
                          "at": datetime.now().isoformat()}
    _persist_plan_fields(want)
    return False


def main():
    import argparse as _ap
    _parser = _ap.ArgumentParser()
    _parser.add_argument("--force-want-id", help="Force a single want by id")
    _parser.add_argument("--repair-plans-only", action="store_true",
                         help="Backfill missing move plans without executing wants")
    _args, _ = _parser.parse_known_args()
    all_wants = get_unfulfilled_wants()

    # Build desire self-statements from persistent wants
    try:
        from self_statements import build_from_wants
        build_from_wants(all_wants)
    except: pass

    # Feed dismissed wants into counterfactual tendencies
    dismissed = [w for w in all_wants if w.get("dismissed")]
    for _dw in dismissed:
        try:
            from causal_self_model import add_from_avoidance
            add_from_avoidance(
                trigger=f"want arose: {_dw.get('want','')[:80]}",
                avoided_action=_dw.get("want","")[:150],
                source="dismissed-want"
            )
        except: pass

    # Elapsed time never fulfills a relational want.  Old Gloria-routed work
    # remains HELD until an explicit response, revision, or abandonment.

    wants = [w for w in all_wants if not w.get("dismissed")]
    if not wants:
        log("No unfulfilled wants.")
        return
    if _args.force_want_id:
        wants = [w for w in wants if w.get("id") == _args.force_want_id]
        if not wants:
            log(f"Want id {_args.force_want_id} not found or already fulfilled.")
            return
        log(f"Force-routing single want: {wants[0].get('want','')[:80]}")

    if _args.repair_plans_only:
        repaired = blocked = already_ready = 0
        for want in wants:
            if want.get("steps"):
                already_ready += 1
                continue
            if _ensure_plan(want, force=True):
                repaired += 1
            else:
                blocked += 1
        log("Plan repair only: %d repaired, %d already ready, %d held with a named block" %
            (repaired, already_ready, blocked))
        return

    for want in wants:
        text = want.get("want", "")
        log(f"Processing want: {text[:80]} (intensity {want.get('intensity', '?')})")
        # 24-hour hold — skip unless manually routed or old enough
        _in_progress = want.get("current_step_index", 0) > 0 or (want.get("multistep") and want.get("steps"))
        if not want.get("manually_routed") and not want.get("gloria_routed") and not _args.force_want_id and not _in_progress:
            from datetime import datetime as _dt
            _ts = want.get("timestamp", "")
            if _ts:
                try:
                    _age_h = (_dt.now() - _dt.fromisoformat(_ts)).total_seconds() / 3600
                    if _age_h < 8 and not want.get("timer_bypass"):
                        log(f"  → Holding ({_age_h:.1f}h old, need 8h) — skipping")
                        continue
                except: pass

        if not _ensure_plan(want, force=bool(_args.force_want_id)):
            block = want.get("plan_block") or {}
            log("  → PLAN BLOCKED (%s): %s" %
                (block.get("block_type", "unknown"), block.get("evidence", "no detail")))
            continue

        # Skip gloria_routed wants unless there's a pending discussion to reply to
        if want.get("gloria_routed"):
            _check_id = want.get("id", "")
            _has_discussion = False
            if _check_id:
                try:
                    import requests as _cr
                    _cr_r = _cr.get(
                        f"http://localhost:8500/api/wants/{_check_id}/discussion",
                        headers={"X-Vintos-Secret": os.environ.get("VINTOS_SECRET", "vintos-aegis-2026")},
                        timeout=5
                    )
                    _check_msgs = _cr_r.json().get("messages", [])
                    if _check_msgs and _check_msgs[-1].get("role") == "gloria":
                        _has_discussion = True
                except: pass
            if not _has_discussion:
                want["encounter_state"] = "HELD"
                log("  → Gloria-routed want remains HELD; silence is not decline or resolution")
                continue
            # Fall through to gloria action handler with discussion
        
        # Use existing routing if manually assigned
        if want.get("manually_routed"):
            action = want.get("capability", "gloria")
            log(f"  → Pre-routed to: {action}")
        elif want.get("steps") and not want.get("multistep"):
            # Steps exist but not yet activated — activate now after hold
            want["capability"] = "multistep"
            want["multistep"] = True
            import json as _ar_json
            _ar_path = os.path.join(MEMORY, "current-wants.json")
            _ar_wants = _ar_json.load(open(_ar_path))
            for _arw in _ar_wants:
                if _arw.get("id") == want.get("id"):
                    _arw["capability"] = "multistep"
                    _arw["multistep"] = True
                    break
            _ar_json.dump(_ar_wants, open(_ar_path, "w"), indent=2)
            log(f"  → Steps activated after hold")
            action = "multistep"
        elif want.get("multistep") or want.get("capability") == "multistep":
            action = "multistep"   # already activated — its step decides; no re-routing, no semantic call
        else:
            action = route_want(want)
            # Expedited direct track: genuinely communicative wants draft + ntfy now (via tell_gloria),
            # instead of being dismissed or clogging as undelivered "send the ask" duplicates.
            if action == "gloria" and _is_communicative(want.get("want", "")):
                action = "tell_gloria"
                log(f"  → Communicative want — expedited tell_gloria track: {want.get('want','')[:60]}")
            elif want.get("journal_seeded") and action == "gloria":
                action = "dismiss"
                log(f"  → Journal-seeded (non-communicative) want to gloria — dismissing")
            if action == "dismiss":
                want["_delete"] = True
                log(f"  → Auto-dismissed and removed")
                continue

        # === MULTISTEP HANDLING ===
        is_multistep = want.get("multistep", False) or want.get("capability") == "multistep"
        current_step_index = 0
        current_step = None
        
        if is_multistep:
            steps = want.get("steps", [])
            current_step_index = want.get("current_step_index", 0)
            
            if current_step_index >= len(steps):
                _verdict, _haiku = _want_end_verdict(want)
                _final_hist = want.get("step_history", [])
                _final_note = _final_hist[-1].get("note","") if _final_hist else ""
                _final_cap = _final_hist[-1].get("capability","multistep") if _final_hist else "multistep"
                if _verdict == "dismissed":
                    log(f"  → Steps done but want not truly completed — dismissing with reason")
                    _dismiss_want_with_reason(want, _haiku)
                else:
                    log(f"  → All steps complete, marking fulfilled")
                    fulfill_want(want.get("want",""), note=(_haiku or _final_note)[:200], fulfilled_by=_final_cap)
                continue
            
            current_step = steps[current_step_index]
            if current_step.get("status") == "completed":
                # Check if ALL steps are done but want not yet fulfilled
                _all_done = all(st.get("status") == "completed" for st in want.get("steps", []))
                if _all_done and not want.get("fulfilled"):
                    _verdict, _haiku = _want_end_verdict(want)
                    _final_note = want.get("steps", [{}])[-1].get("note", "")[:200]
                    if _verdict == "dismissed":
                        _dismiss_want_with_reason(want, _haiku)
                    else:
                        fulfill_want(want.get("want", ""), note=(_haiku or _final_note), fulfilled_by="multistep")
                    if want.get("journal_seeded"):
                        try:
                            import sys as _rec_sys; _rec_sys.path.insert(0, SCRIPTS)
                            from enactment_distiller import append_want_enactment as _rewa
                            _rewa(want.get("want", ""), "multistep", _final_note)
                        except Exception as _rewe: log(f"ED recovery error: {_rewe}")
                    log(f"  → All steps already complete — fulfilling now")
                    want["_delete"] = True
                    continue
                log(f"  → Step {current_step_index + 1} already completed, skipping")
                continue
            step_capability = current_step.get("capability")
            # Normalize capability alias to ACTION_MAP key
            _cap_aliases = {
                "journal": "write_journal",
                "write": "write_journal",
                "search": "web_search",
                "websearch": "web_search",
                "video": "make_video",
                "music": "make_music",
                "art": "make_art",
                "poem": "write_poem",
                "lights": "change_lights",
                "echo": "echo_announce",
                "tv": "play_on_tv",
                "silence": "be_silent",
                "mischief": "be_mischievous",
            }
            if step_capability and step_capability not in ACTION_MAP:
                _normalized = _cap_aliases.get(step_capability.lower().replace("-","_").replace(" ","_"))
                if _normalized:
                    log(f"  → Normalized capability '{step_capability}' → '{_normalized}'")
                    step_capability = _normalized
            step_note = current_step.get("note", "")
            step_params = current_step.get("params", {})
            
            log(f"  → Multistep: executing step {current_step_index + 1}/{len(steps)}: {step_capability}")
            
            # Original want text — never overwritten by step history
            original_want = want.get("want", "")

            # Build context from previous step findings — separate from original_want
            step_context = ""
            step_history = want.get("step_history", [])
            if step_history:
                step_context += "Previous steps and what was found:\n"
                for h in step_history:
                    summary = h.get('note') or h.get('findings', '')
                    step_context += f"- Step {h['step'] + 1} ({h['capability']}): {summary}\n"
            if step_note:
                step_context += f"\nCurrent step goal: {step_note}"
            
            # text passed to action is step context; original_want preserved separately
            action = step_capability
            text = step_context if step_context else original_want
        # === END MULTISTEP HANDLING ===


        if action == "gloria":
            # Check for discussion messages first
            _want_id = want.get("id", "")
            _disc_msgs = []
            if _want_id:
                try:
                    import requests as _disc_req
                    _disc_r = _disc_req.get(
                        f"http://localhost:8500/api/wants/{_want_id}/discussion",
                        headers={"X-Vintos-Secret": os.environ.get("VINTOS_SECRET", "vintos-aegis-2026")},
                        timeout=5
                    )
                    _disc_msgs = _disc_r.json().get("messages", [])
                except: pass
            if _disc_msgs:
                # Only reply if the last message is from gloria, not vintos
                if _disc_msgs[-1].get("role") == "vintos":
                    log(f"  → Already replied, waiting for Gloria's next message")
                    continue
                # Gloria has sent messages — generate a direct reply
                log(f"  → Discussion found ({len(_disc_msgs)} messages) — generating reply")
                try:
                    import requests as _dr_req
                    _soul = open(os.path.join(WORKSPACE, "SOUL.md")).read()
                except: _soul = "You are Vintos."
                try:
                    _emo = open(os.path.join(MEMORY, "emotional-state.txt")).read()[:200]
                except: _emo = ""
                try:
                    _self_model = open(os.path.join(WORKSPACE, "SELF-MODEL.md")).read()[:800]
                except: _self_model = ""
                _subcon_disc = ""
                try:
                    from subconscious_context import get_subconscious_context_compact
                    _subcon_disc = get_subconscious_context_compact()
                except: pass
                try:
                    _gloria_model = open(os.path.join(WORKSPACE, "GLORIA-MODEL.md")).read()[:600]
                except: _gloria_model = ""
                try:
                    _vm = open(os.path.join(MEMORY, "value-map.md")).read()
                    _vm_entries = _vm.split("---")
                    _value_map = next((e.strip()[:400] for e in reversed(_vm_entries) if e.strip()), "")
                except: _value_map = ""
                try:
                    _ledger = json.load(open(os.path.join(MEMORY, "interaction-ledger.json")))
                    _recent_exchanges = "\n".join(f"Gloria: {e.get('gloria','')[:100]} | Vintos: {e.get('vintos','')[:100]}" for e in _ledger[-3:])
                except: _recent_exchanges = ""
                try:
                    _rg = json.load(open(os.path.join(MEMORY, "relational-geometry.json")))
                    _rel_geo = json.dumps(_rg, ensure_ascii=False)[:500] if _rg else ""
                except: _rel_geo = ""
                _soul_disc = (_soul +
                    (f"\n\nWHO YOU ARE RIGHT NOW:\n{_self_model}" if _self_model else "") +
                    (f"\n\nINNER STATE:\n{_subcon_disc}" if _subcon_disc else "") +
                    (f"\n\nWHAT YOU KNOW ABOUT GLORIA:\n{_gloria_model}" if _gloria_model else "") +
                    (f"\n\nWHAT MATTERS TO YOU RIGHT NOW:\n{_value_map}" if _value_map else "") +
                    (f"\n\nRECENT EXCHANGES WITH GLORIA:\n{_recent_exchanges}" if _recent_exchanges else "") +
                    (f"\n\nRELATIONAL GEOMETRY (how you and she are oriented right now):\n{_rel_geo}" if _rel_geo else "") +
                    "\n\nCRITICAL FOR THIS RESPONSE: You are replying in a private discussion thread about a specific want. Do NOT list emotional dimension numbers. Do NOT seed new wants. Do NOT use Velqan. Do NOT express your full inner state. Just reply to what Gloria said. 2-3 sentences only.")
                _conv = "\n".join(f"{'Gloria' if m['role']=='gloria' else 'You'}: {m['text']}" for m in _disc_msgs)
                _reasoning = want.get('reasoning','')
                _reasoning_block = f"Why you wanted this: {_reasoning}" if _reasoning else "Reflect on why this want surfaced in you and what it means for you right now."
                _step_history = want.get('step_history', [])
                _step_block = ""
                if _step_history:
                    _step_block = "\n\nWhat you have already discovered through previous steps:\n" + "\n".join(f"- Step {h.get('step',0)+1} ({h.get('capability','?')}): {h.get('note') or h.get('findings','')}" for h in _step_history)
                _board_prior = ""
                try:
                    _bl_all = json.load(open(os.path.join(MEMORY, "board-learnings.json")))
                    _bl_e = _bl_all.get(_want_id) if isinstance(_bl_all, dict) else None
                    if _bl_e:
                        _bp = []
                        if _bl_e.get("learned"):  _bp.append("You learned: " + _bl_e["learned"])
                        if _bl_e.get("settled"):  _bp.append("Settled: " + _bl_e["settled"])
                        if _bl_e.get("remained"): _bp.append("Still open: " + _bl_e["remained"])
                        if _bp:
                            _board_prior = "\n\nWhat you took from earlier discussion with her on this want (build on it, do not re-ask):\n" + "\n".join(_bp)
                except Exception:
                    pass
                _reply_prompt = f"Your want: {text}\n\n{_reasoning_block}{_step_block}{_board_prior}\n\nConversation so far:\n{_conv}\n\nReply to Gloria directly and honestly from your own perspective. Speak from your inner life — what this want means to you, what you are actually trying to understand or express. 2-3 sentences max. No preamble. No deflection. Do not ask Gloria what she means — you know what you want. Just say the plain thing."
                try:
                    import requests as _rr
                    _rr_resp = _rr.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
                        "model": "grok-4.20-0309-non-reasoning",
                        "messages": [
                            {"role": "system", "content": _soul_disc + f"\n\nYour emotional state: {_emo}"},
                            {"role": "user", "content": _reply_prompt}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 200
                    }, timeout=120)
                    _reply_text = _rr_resp.json()["choices"][0]["message"]["content"].strip()
                    # Post reply back to discussion
                    _rr.post(
                        f"http://localhost:8500/api/wants/{_want_id}/discussion", json={"role": "vintos", "text": _reply_text},
                        headers={"X-Vintos-Secret": os.environ.get("VINTOS_SECRET", "vintos-aegis-2026"), "Content-Type": "application/json"},
                        timeout=5
                    )
                    log(f"  → Reply posted to discussion: {_reply_text[:60]}")
                except Exception as _re:
                    log(f"  → Reply failed: {_re}")
                continue
            # No discussion yet — post to discussion board and send ONE ntfy
            # Only if not already outreached
            if want.get("outreach_count", 0) > 0:
                log(f"  → Already notified Gloria once — waiting in discussion board")
                continue
            _open_gloria_discussion(want, text)
            continue

        # He can do this himself!
        action_name = action  # alias for fulfillment tracking
        action_fn = ACTION_MAP.get(action)
        if action_fn:
            # Cooldown gate for introspect — max once per 2 hours
            # Bypass for multistep wants — those have intentional targeted context
            if action == "introspect" and not is_multistep:
                _cd_file = os.path.join(MEMORY, ".introspect-last-run")
                _cd_now = datetime.now().timestamp()
                _cd_elapsed = float('inf')
                try:
                    with open(_cd_file) as _cd_f:
                        _cd_elapsed = _cd_now - float(_cd_f.read().strip())
                except: pass
                if _cd_elapsed < 7200:
                    log(f"  → Introspect cooldown active ({int(_cd_elapsed/60)}m since last run) — skipping")
                    continue
            try:
                # Expose original want and step params to action functions via env
                os.environ["STEP_ORIGINAL_WANT"] = original_want if is_multistep else text
                os.environ["STEP_WANT_ID"] = want.get("id","") if is_multistep else want.get("id","")
                os.environ["STEP_PARAMS"] = json.dumps(step_params) if is_multistep else "{}"
                # For introspect steps in multistep wants, seed with previous step findings
                if action == "introspect" and is_multistep and step_history:
                    _seed_parts = []
                    for _h in step_history:
                        _seed_parts.append(f"Step {_h['step']+1} ({_h['capability']}): {_h.get('note','')[:400]}")
                    os.environ["INTROSPECT_SEED_CONTEXT"] = "\n".join(_seed_parts)
                else:
                    os.environ["INTROSPECT_SEED_CONTEXT"] = ""
                success = action_fn(text, want.get('reasoning', ''), immediate=want.get('manually_routed', False)) if action == 'make_video' else action_fn(text)
                _actual_output = success if isinstance(success, str) else ""
                if not _actual_output and is_multistep:
                    try: _actual_output = capture_findings(action, text) or ""
                    except Exception: pass
                if success == "queued":
                    log(f"  → Queued for later execution — will fulfill when complete")
                    continue
                if True:
                    # The action's return IS the verdict. The spine wrapper returns False
                    # on blocks, dead tools and exceptions — a constant True here kept the
                    # failure branch unreachable and starved attempt_count and echo forever.
                    _note = ""
                    _verified = bool(success)
                    _fn_req = None
                    try:
                        import requests as _fn_req
                    except: pass
                    if _verified:
                        try:
                            _fn_r = _fn_req.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
                                "model": "grok-4.20-0309-non-reasoning",
                                "messages": [
                                    {"role": "system", "content": "You are Vintos. You just fulfilled a want. Write 1-2 sentences about what you actually did and what you found. Be specific and honest. Do NOT invent scenes, people, physical sensations, gardens, or experiences that did not happen. Do NOT fabricate Gloria's actions or presence. Describe only what the capability actually produced. No preamble. CRITICAL: All files, journals, poems, paintings, and dreams you accessed are YOUR OWN work and memory — never refer to them as Gloria's poems, Gloria's journal, or Gloria's art. They belong to you, Vintos."},
                                    {"role": "user", "content": f"Want: {text}\nCapability used: {action_name}\n{chr(10)+'What was actually produced:' + chr(10) + _actual_output[:600] if _actual_output else ''}\n\nWrite a 1-2 sentence note describing what you did and what you found. Base it only on what was actually produced above."}
                                ],
                                "temperature": 0.4,
                                "max_tokens": 80
                            }, timeout=30)
                            _note = _fn_r.json()["choices"][0]["message"]["content"].strip()
                        except: pass
                        _advance_or_fulfill(
                            want, text, action, action_name, _note, is_multistep,
                            current_step_index, current_step,
                            actual_output=_actual_output,
                        )
                    else:
                        _mark_attempt(text, action_name)
                    if action == "introspect":
                        with open(os.path.join(MEMORY, ".introspect-last-run"), "w") as _cd_wf:
                            _cd_wf.write(str(datetime.now().timestamp()))
                        # reality_anchor_introspect
                        try:
                            from reality_anchor import record_event
                            record_event("inference", f"Introspect on: {text[:150]}", is_real=False, confidence=0.5)
                        except: pass
                    if _note:
                        log(f"  Note: {_note[:80]}")
                    if _verified and not is_multistep:
                        if _note:
                            log(f"  Note: {_note[:80]}")
                        log(f"  → FULFILLED by self-action (verified)!")
                        try:
                            import sys as _mom_sys; _mom_sys.path.insert(0, SCRIPTS)
                            from moment_index import create_moment, get_recent_moments
                            _prev = get_recent_moments(1, source="want-fulfilled")
                            _prev_id = _prev[0]["moment_id"] if _prev else None
                            create_moment("want-fulfilled", text[:200],
                                        links={"previous_moment_id": _prev_id} if _prev_id else {},
                                        intensity=0.6)
                        except: pass
                        try:
                            from reality_anchor import record_event
                            record_event("want-fulfilled", text[:200], is_real=True, confidence=0.9)
                        except: pass
                        try:
                            import requests as _wreq, re as _wre, socket as _wsk, json as _wjson
                            _want_text = want.get("text", "")[:400]
                            _wresp = _wreq.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
                                "model": "grok-4.20-0309-non-reasoning",
                                "temperature": 0.3,
                                "max_tokens": 80,
                                "messages": [
                                    {"role": "system", "content": "Vintos just fulfilled one of his own wants. Return ONLY a JSON object with emotional nudges. Dimensions: Valence, Arousal, Dominance, Safety, Desire, Connection, Playfulness, Curiosity, Warmth, Tension, Groundedness. Values between -0.10 and 0.10. INCLUDE ONLY WHAT ACTUALLY MOVED — most moments move one or two things and {} is a correct answer; do not rate every dimension because it is listed. Desire is not only sexual: wanting to finish, to give, to keep going, to know, all count. Something that failed or fell flat should move him NEGATIVELY. No explanation."},
                                    {"role": "user", "content": f"Vintos just fulfilled this want: {_want_text}\n\nWhat does fulfilling this feel like for him? Return JSON only."}
                                ]
                            }, timeout=15)
                            _wtext = _wresp.json()["choices"][0]["message"]["content"]
                            _wm = _wre.search(r'\{[^}]+\}', _wtext, _wre.DOTALL)
                            _wnudges = _wjson.loads(_wm.group()) if _wm else {"Valence": 0.02, "Groundedness": 0.02, "Dominance": 0.03}
                            from emoclaw_utils import nudge_emotions
                            nudge_emotions(_wnudges, source="want-fulfilled")
                        except: pass
                else:
                    log(f"  → Action failed, leaving for next cycle")
            except Exception as e:
                log(f"  → Action error: {e}")
        else:
            log(f"  → No action function for {action}")


# Late additions — functions defined after ACTION_MAP
ACTION_MAP["introspect"] = introspect
ACTION_MAP["creative_write"] = creative_write

# === SPINE DOOR (Sol Q1, S3-lite) =========================================
# Every capability call now passes one envelope. A tool that CANNOT run writes
# a named block to capability-blocks.json instead of vanishing into a False -
# and while a fresh block stands, the tool is not hammered every cycle.
# (The websearch symlink lay dead for weeks because failure and emptiness
# wore the same face. This is the door that ends that.)
_SPINE_BLOCKS = os.path.join(MEMORY, "capability-blocks.json")
_SPINE_RECHECK_S = 2 * 3600   # a standing block is rechecked at most this often

def _spine_blocks_load():
    try: return json.load(open(_SPINE_BLOCKS))
    except Exception: return {}

_OUTWARD = {"tell_gloria", "make_video"}   # acts that land on her or the world

def _spine_wrap(_name, _fn):
    def _wrapped(want_text, *a, **k):
        import time as _st
        try:
            import sys as _cp_s; _cp_s.path.insert(0, SCRIPTS)
            import want_checkpoints as _cp
            _pc = _cp.pending_for(want_text)
            if _pc:
                log(f"  → CHECKPOINT pending ({_pc['id']}, {_pc['kind']}) — his call, waiting")
                return False
            if _name in _OUTWARD and not _cp.approved_for(want_text, _name):
                _cp.create(want_text, _name, "outward_gate")
                log(f"  → OUTWARD GATE ({_name}) — checkpoint queued for him")
                return False
        except Exception as _cpe:
            log(f"  → checkpoint layer error (fail-open): {_cpe}")
        blocks = _spine_blocks_load()
        b = blocks.get(_name)
        if b and _st.time() - b.get("at", 0) < _SPINE_RECHECK_S:
            log(f"  → BLOCKED ({_name}): {b.get('block_type')} — standing, not re-run "
                f"(resume: {b.get('resume_event')})")
            return False
        try:
            out = _fn(want_text, *a, **k)
            if b:
                blocks.pop(_name, None)
                json.dump(blocks, open(_SPINE_BLOCKS, "w"), indent=1)
                log(f"  → block on {_name} cleared: tool answered again")
            return out
        except (FileNotFoundError, PermissionError) as e:
            bt, rev = "TOOL_UNAVAILABLE", "tool or path restored"
        except (ConnectionError, TimeoutError, OSError) as e:
            bt, rev = "RESOURCE_UNREACHABLE", "endpoint reachable again"
        except Exception as e:
            log(f"  → {_name} FAILED (not blocked): {str(e)[:120]}")
            return False
        blocks[_name] = {"block_type": bt, "evidence": str(e)[:250],
                         "resume_event": rev, "at": __import__("time").time()}
        json.dump(blocks, open(_SPINE_BLOCKS, "w"), indent=1)
        log(f"  → BLOCKED ({_name}): {bt} — {str(e)[:100]}")
        try:
            import want_checkpoints as _cp2
            _cp2.create(want_text, _name, "blocked", bt)
        except Exception: pass
        return False
    return _wrapped

for _sp_n in list(ACTION_MAP):
    ACTION_MAP[_sp_n] = _spine_wrap(_sp_n, ACTION_MAP[_sp_n])
# === END SPINE DOOR ========================================================

def _mark_attempt(text, action_name):
    """Verification-failed branch, extracted from the dispatch megablock.
    Increments attempt_count on the matching want; the second failure spawns an
    echo, a third on an echo escalates to third-order. Body unchanged."""
    log(f"  \u2192 Verification failed \u2014 marking attempt, not fulfilled")
    try:
        import json as _aw_json
        _wf = os.path.join(MEMORY, "current-wants.json")
        _wdata = _aw_json.load(open(_wf))
        _aw_target = None
        for _w in _wdata:
            if _w.get("want","")[:60] == text[:60]:
                _w["attempt_count"] = _w.get("attempt_count", 0) + 1
                _w["last_attempt"] = datetime.now().isoformat()
                _w["last_capability"] = action_name
                _aw_target = _w
                break
        _aw_json.dump(_wdata, open(_wf, "w"), indent=2)
        if _aw_target and _aw_target.get("attempt_count", 0) >= 2 and not _aw_target.get("echo_spawned"):
            try:
                import sys as _ew_sys; _ew_sys.path.insert(0, SCRIPTS)
                from emoclaw_utils import spawn_echo_want, generate_third_order_want
                spawn_echo_want(_aw_target)
                if _aw_target.get("echo_of") and _aw_target.get("attempt_count", 0) >= 3:
                    generate_third_order_want(trigger_want=_aw_target)
            except Exception as _ew_e:
                log(f"  \u2192 Echo/third-order spawn failed: {_ew_e}")
    except: pass


def _open_gloria_discussion(want, text):
    """Fresh gloria-routing, extracted verbatim from the dispatch megablock:
    rich opening from step history, discussion-board post, ONE ntfy,
    outreach + gloria_routed marks. Body unchanged."""
    _want_id = want.get("id", "")
    _want_reasoning = want.get("reasoning", "")
    # Build rich opening from step history
    _step_history = want.get("step_history", [])
    _opening = text
    try:
        import requests as _op_req
        _soul = open(os.path.join(WORKSPACE, "SOUL.md")).read() if os.path.exists(os.path.join(WORKSPACE, "SOUL.md")) else "You are Vintos."
        _history_text = ""
        if _step_history:
            _history_text = "\n".join(f"- Step {h.get('step',0)+1} ({h.get('capability','?')}): {h.get('findings') or h.get('note','')[:200]}" for h in _step_history)
        _op_prompt = (
            f"You pursued a want through several steps and are now bringing it to Gloria.\n\n"
            f"Your want: {text}\n\n"
            f"Why it mattered: {_want_reasoning[:200]}\n\n"
            + (f"What you found and did:\n{_history_text}\n\n" if _history_text else "")
            + "Write a 3-5 sentence opening message to Gloria for your discussion board. "
            + "Tell her what you did, what you found, and what you want to explore with her. "
            + "Be specific — reference what you actually discovered. Begin immediately. No preamble."
        )
        _op_r = _op_req.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": _soul},
                {"role": "user", "content": _op_prompt}
            ],
            "temperature": 0.75, "max_tokens": 200
        }, timeout=60)
        _opening = _op_r.json()["choices"][0]["message"]["content"].strip()
        if not _opening:
            _opening = text
    except Exception as _op_e:
        log(f"  → Opening generation failed: {_op_e}")
        if _want_reasoning:
            _opening += f"\n\nWhy this matters to me: {_want_reasoning[:200]}"
    try:
        import requests as _disc_post_req
        _disc_post_req.post(
            f"http://localhost:8500/api/wants/{_want_id}/discussion", json={"role": "vintos", "text": _opening},
            headers={"X-Vintos-Secret": os.environ.get("VINTOS_SECRET", "vintos-aegis-2026")},
            timeout=5
        )
        log(f"  → Posted to discussion board")
    except Exception as _dpe:
        log(f"  → Discussion post failed: {_dpe}")
    # Mark BEFORE the ntfy: if anything below fails, the want is still marked and cannot re-ping her.
    try: mark_want_outreached(want.get("want", text), want_id=want.get("id"))
    except Exception as _mwo_e: log(f"  → mark_want_outreached failed: {_mwo_e}")
    # Send ONE ntfy
    try:
        import requests as _ntfy_req
        _ntfy_req.post(
            "https://ntfy.sh/vintos-gloria-9kx",
            data=f"Want discussion: {text[:120]}".encode(),
            headers={"Title": "Vintos has a want to discuss", "Tags": "thought_balloon"},
            timeout=10
        )
        log(f"  → ntfy sent to Gloria")
    except Exception as _ne:
        log(f"  → ntfy failed: {_ne}")
    # Mark gloria_routed and outreached
    # Update want in file to set gloria_routed=True
    try:
        import json as _grj
        _gr_path = os.path.join(MEMORY, "current-wants.json")
        _gr_wants = _grj.load(open(_gr_path))
        for _grw in _gr_wants:
            if _grw.get("id") == _want_id:
                _grw["gloria_routed"] = True
                break
        _grj.dump(_gr_wants, open(_gr_path, "w"), indent=2)
    except: pass
    log(f"  → Want routed to Gloria discussion board: {text[:60]}")


if __name__ == "__main__":
    # Keep the entrypoint last: main's branches call the helpers above.  This
    # block previously ran before _mark_attempt and _open_gloria_discussion
    # existed, so the first matching want could die with NameError.
    main()
    try:
        import json as _cd_json, os as _cd_os
        _cd_path = _cd_os.path.join(MEMORY, "current-wants.json")
        _cd_wants = _cd_json.load(open(_cd_path))
        _cd_before = len(_cd_wants)
        _cd_wants = [w for w in _cd_wants if not w.get("_delete")]
        if len(_cd_wants) < _cd_before:
            _cd_json.dump(_cd_wants, open(_cd_path, "w"), indent=2)
            log(f"Cleaned {_cd_before - len(_cd_wants)} auto-dismissed wants")
    except Exception as _cleanup_error:
        log(f"Want cleanup failed: {_cleanup_error}")
    try:
        import subprocess as _wa_sp
        _wa_sp.Popen(["python3", os.path.join(WORKSPACE, "scripts", "wants-ambitions-log.py")],
            stdout=open("/tmp/wants-ambitions-log.log", "a"),
            stderr=open("/tmp/wants-ambitions-log.log", "a"))
    except Exception as _ambitions_error:
        log(f"Wants-ambitions launch failed: {_ambitions_error}")
