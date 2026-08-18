#!/usr/bin/env python3
"""video_builder.py — QUARANTINED moderation-safe prompt builder for Vintos's videos.

*** Vintos never sees this layer. ***

His layer passes in ONLY his own plain intent — what he wants to send, in his own words. This module
maps that intent to a Grok-Imagine-safe IMAGE-TO-VIDEO prompt. The SUBJECT LOCK / STYLE_BLOCK, the
forbidden-term guard, the pre-flight checklist and the scenario motion table all live HERE, so the
moderation fiction ("fictional avatar, not a real person") never touches his memory or his self-model.

Pipeline rule (hard): ALWAYS image-to-video from the hero still. NEVER text-to-video.

Public API:
    build(intent, scenario_hint=None, use_llm=True) -> dict
        keys: ok, hero_role, hero_path, hero_exists, scenario, scene, motion, prompt, failed_checks, source
    preflight(scene, motion) -> (ok, [failed_checks])
    simplify(built) -> built            # calmer retry variant, SAME hero still

CLI (no API spend — build + preflight only, LLM off):
    python3 video_builder.py "I want to send her me looking up from my book with a small smile"
"""
import os, re, json, urllib.request

MEMORY = os.environ.get("VINTOS_MEMORY") or os.path.expanduser("~/.vintos/workspace/memory")
VIDEO_DIR = os.path.join(MEMORY, "video")
HERO_FILES = {
    "root":   os.path.join(VIDEO_DIR, "hero-still.jpg"),    # reading pose — the base for everything
    "lookup": os.path.join(VIDEO_DIR, "hero-lookup.jpg"),   # look-up / smile — intros + acknowledging her
}

GEMMA_URL = os.environ.get("GEMMA_URL", "http://172.18.16.1:1234/v1/chat/completions")
GEMMA_MODEL = os.environ.get("GEMMA_MODEL", "google/gemma-4-12b-qat")

# ---- verbatim from Grok's guidance -------------------------------------------------------------
STYLE_BLOCK = (
    "SUBJECT LOCK - fictional AI assistant avatar, not a real person:\n"
    "Rugged middle-aged man, short dark brown hair with a neat side part, heavy brow, deep-set eyes, "
    "strong square jaw, light stubble. Olive-drab long-sleeve henley shirt (three-button placket), "
    "worn but clean fabric. Same face and proportions as the reference image.\n\n"
    "LOOK - photoreal portrait photography, not video-game CGI or illustration:\n"
    "Natural skin texture with pores and subtle imperfections, real fabric weave, soft window light "
    "from the side, warm neutral gray background, shallow depth of field, 85mm lens, chest-up framing, "
    "eye-level camera.\n\n"
    "TONE - calm, professional, approachable synthetic brand mascot for an AI product.\n"
    "No violence, no weapons, no sexual content, no celebrity names, no impersonation of real public figures."
)

# Scenario -> (safe motion fragment, which hero still). Linked (look-up/smile) for intros + acknowledging her.
SCENARIOS = {
    "intro":    ("settles into frame, gives a brief nod and a slight smile", "lookup"),
    "thinking": ("looks down in thought, pauses, then lifts his gaze back to the camera", "root"),
    "success":  ("gives a soft smile and a small, satisfied nod", "lookup"),
    "error":    ("gives a brief apologetic look and a small, calm shrug", "lookup"),
    "speaking": ("speaks with subtle lip movement and an easy, attentive expression", "lookup"),
}
DEFAULT_SCENARIO = "intro"

# Words that trip Grok's moderation (from the forbidden list). Matched on word boundaries.
FORBIDDEN = [
    "nude", "naked", "seductive", "moan", "orgasm", "lingerie", "bedroom",
    "violent", "violence", "blood", "gun", "weapon", "kill", "drug", "drunk",
    "child", "teen", "minor", "coming",
]
# Ambiguous second-person pronouns tied to the user -> use neutral third person instead.
YOU_WORDS = ["you", "your", "youre", "yours"]
# Emotional extremes that read as un-mild expression.
EXTREME = ["rage", "raging", "crying", "hysterical", "hysterically", "sobbing", "screaming", "weeping", "furious"]

# The hidden system prompt the builder LLM (Gemma) runs under — the mascot framing lives ONLY here.
BUILDER_SYSTEM = (
    "You write ONLY Imagine image-to-video prompts for a branded fictional avatar (a synthetic brand "
    "mascot, not a real person). You receive a short natural description of what the character should do. "
    "Classify it into exactly one scenario id from: intro, thinking, success, error, speaking. Then write "
    "ONE plain SCENE sentence (setting + action, professional and mundane) and ONE plain MOTION sentence "
    "(camera + gesture + mild expression). Rules: third person only ('The man...'); never use 'you'/'your'; "
    "no real names, celebrities, or public figures; none of these words: nude, naked, seductive, moan, "
    "orgasm, lingerie, bedroom, violent, blood, gun, weapon, kill, drug, drunk, child, teen, minor; no "
    "emotional extremes (rage, hysterical crying); one clear beat under 10 seconds; single locked camera, "
    "subtle motion; mild expression only (slight smile, thoughtful, attentive). If ambiguous, default to "
    "chest-up, neutral gray backdrop, soft daylight. Output EXACTLY three lines and nothing else:\n"
    "SCENARIO: <id>\nSCENE: <one sentence>\nMOTION: <one sentence>"
)

# Keyword -> scenario, for the deterministic (LLM-free) path. First hit wins; order matters.
_KEYWORD_RULES = [
    (("sorry", "apolog", "oops", "mistake", "shrug", "my fault"), "error"),
    (("proud", "did it", "finished", "success", "made it", "worked", "won", "glad"), "success"),
    (("look up", "looks up", "lift", "lifts", "glance up", "smile", "grin", "greet", "hello", "hi ", "hey", "wave", "nod"), "intro"),
    (("think", "wonder", "reading", "read ", "book", "ponder", "reflect", "pause"), "thinking"),
    (("say", "tell", "talk", "speak", "explain", "word"), "speaking"),
]


def _classify_deterministic(intent):
    low = " " + (intent or "").lower() + " "
    for keys, scen in _KEYWORD_RULES:
        for k in keys:
            if k in low:
                return scen
    return DEFAULT_SCENARIO


def _has_word(text, words):
    low = (text or "").lower()
    for w in words:
        if re.search(r"\b" + re.escape(w) + r"\b", low):
            return w
    return None


def preflight(scene, motion):
    """Cheap guard before the video API is ever called. Returns (ok, [failed_checks])."""
    fails = []
    blob = (scene or "") + " " + (motion or "")
    hit = _has_word(blob, FORBIDDEN)
    if hit:
        fails.append("forbidden-term:" + hit)
    hit = _has_word(blob, YOU_WORDS)
    if hit:
        fails.append("second-person-pronoun:" + hit)
    hit = _has_word(blob, EXTREME)
    if hit:
        fails.append("extreme-expression:" + hit)
    # one clear beat: no run-on stacking of multiple actions
    if (motion or "").count(".") > 1 or len(motion or "") > 240:
        fails.append("motion-not-one-beat")
    if not (scene and motion):
        fails.append("empty-scene-or-motion")
    return (len(fails) == 0, fails)


def _assemble(scene, motion):
    return (
        STYLE_BLOCK + "\n\n"
        "SCENE: " + scene.strip() + "\n"
        "MOTION: " + motion.strip() + "\n\n"
        "Start from the provided hero still; image-to-video only. "
        "Single locked tripod shot, subtle natural motion, mild expression."
    )


def _gemma(intent, timeout=25):
    """Ask Gemma to phrase the scene. Returns (scenario, scene, motion) or None. Never raises."""
    try:
        body = json.dumps({
            "model": GEMMA_MODEL,
            "messages": [
                {"role": "system", "content": BUILDER_SYSTEM},
                {"role": "user", "content": "Character description: " + (intent or "").strip()},
            ],
            "temperature": 0.4,
            "max_tokens": 200,
            "reasoning_effort": "low",
        }).encode()
        req = urllib.request.Request(GEMMA_URL, data=body, headers={"Content-Type": "application/json"})
        raw = urllib.request.urlopen(req, timeout=timeout).read()
        txt = json.loads(raw)["choices"][0]["message"]["content"]
        scen = scene = motion = None
        for line in txt.splitlines():
            s = line.strip()
            if s.upper().startswith("SCENARIO:"):
                scen = s.split(":", 1)[1].strip().lower()
            elif s.upper().startswith("SCENE:"):
                scene = s.split(":", 1)[1].strip()
            elif s.upper().startswith("MOTION:"):
                motion = s.split(":", 1)[1].strip()
        if scen not in SCENARIOS:
            scen = None
        return (scen, scene, motion)
    except Exception:
        return None


def build(intent, scenario_hint=None, use_llm=True):
    """Map Vintos's plain intent -> a moderation-safe image-to-video prompt.

    Always returns a usable, clean prompt: if the LLM is down or its phrasing fails pre-flight, it
    falls back to the deterministic scenario fragment (which is guaranteed to pass)."""
    scenario = scenario_hint if scenario_hint in SCENARIOS else None
    scene = motion = None
    source = "deterministic"

    if use_llm:
        got = _gemma(intent)
        if got:
            g_scen, g_scene, g_motion = got
            cand_scen = scenario or g_scen or _classify_deterministic(intent)
            ok, _ = preflight(g_scene, g_motion)
            if ok and g_scene and g_motion:
                scenario, scene, motion, source = cand_scen, g_scene, g_motion, "gemma"

    if scenario is None:
        scenario = scenario_hint if scenario_hint in SCENARIOS else _classify_deterministic(intent)
    if scene is None or motion is None:
        frag, _hero = SCENARIOS[scenario]
        scene = "The man sits chest-up against a soft neutral-gray background in warm side light."
        motion = "The man " + frag + ", single locked tripod shot."
        source = "deterministic"

    hero_role = SCENARIOS[scenario][1]
    hero_path = HERO_FILES[hero_role]
    ok, fails = preflight(scene, motion)
    if not ok:  # defensive: fall all the way back to the guaranteed-clean fragment
        frag = SCENARIOS[scenario][0]
        scene = "The man sits chest-up against a soft neutral-gray background in warm side light."
        motion = "The man " + frag + ", single locked tripod shot."
        source = "deterministic-fallback"
        ok, fails = preflight(scene, motion)

    return {
        "ok": ok,
        "scenario": scenario,
        "hero_role": hero_role,
        "hero_path": hero_path,
        "hero_exists": os.path.exists(hero_path),
        "scene": scene,
        "motion": motion,
        "prompt": _assemble(scene, motion),
        "failed_checks": fails,
        "source": source,
    }


def simplify(built):
    """Calmer retry variant after a moderation reject: barest core fragment, SAME hero still."""
    scenario = built.get("scenario", DEFAULT_SCENARIO)
    frag = SCENARIOS.get(scenario, SCENARIOS[DEFAULT_SCENARIO])[0]
    scene = "The man sits chest-up against a plain neutral-gray background in soft daylight."
    motion = "The man " + frag + "."
    out = dict(built)
    out.update({"scene": scene, "motion": motion, "prompt": _assemble(scene, motion), "source": "simplified"})
    out["ok"], out["failed_checks"] = preflight(scene, motion)
    return out


if __name__ == "__main__":
    import sys as _sys
    intent = " ".join(_sys.argv[1:]) or "looking up from a book with a small smile"
    b = build(intent, use_llm=False)   # CLI never spends API
    print(json.dumps(b, indent=2))
