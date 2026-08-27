#!/usr/bin/env python3
"""
velqan-coiner.py — Vintos creates a new word each week.

She reviews her emotional week — dreams, pearls, confessions,
causality hypotheses, game events, conversations — and finds
the one feeling or concept that English couldn't hold.

She coins a Velqan word for it. Writes the etymology. Adds it
to the reference. Uses it in a sentence.

The word comes from lived experience, not assignment.

Schedule: Weekly (Sunday 10 PM)
"""
import os, sys, json, glob, re
import subprocess
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
VELQAN_REF = os.path.join(MEMORY, "velqan-reference.md")
VELQAN_UTTERANCES = os.path.join(MEMORY, "velqan-utterances.md")
VELQAN_LEXICON = os.path.join(MEMORY, "velqan", "full-lexicon.md")
LM_API = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
try:
    from emoclaw_utils import get_state, get_vector, describe_state, nudge_emotions, DIMENSIONS, preoccupation_context, recent_pearls
    HAS_EMOCLAW = True
except ImportError:
    HAS_EMOCLAW = False
    DIMENSIONS = ["Valence", "Arousal", "Dominance", "Safety", "Desire",
                  "Connection", "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]


# Load identity
SOUL_PATH = os.path.join(WORKSPACE, "SOUL.md")
def load_soul():
    try:
        with open(SOUL_PATH) as f:
            return f.read()
    except:
        return "You are Vintos."

def log(msg):
    print(f"[Velqan {datetime.now().strftime('%H:%M')}] {msg}")

_SUBCON_VELQAN_COINER = ""
try:
    import sys as _sc__SUBCON_VELQAN_COINER; _sc__SUBCON_VELQAN_COINER.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_VELQAN_COINER = get_subconscious_context_compact()
except: pass


def ask_llm(prompt, system=None, max_tokens=2000, temp=0.85):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": temp,
        "max_tokens": max_tokens
    })
    try:
        r = subprocess.run(
            ["curl", "-s", "-X", "POST", LM_API,
             "-H", "Content-Type: application/json", "-d", payload],
            capture_output=True, text=True, timeout=120
        )
        d = json.loads(r.stdout)
        msg = d["choices"][0]["message"]
        text = msg.get("content", "") or ""
        # reasoning fallback removed — content only
        return text.strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return ""

def feel(nudges):
    if HAS_EMOCLAW:
        try: nudge_emotions(nudges, source="velqan")
        except: pass


def gather_weekly_experience():
    """Collect the emotional texture of this week."""
    parts = []

    # Emotional trajectory — find the biggest movements
    state_file = os.path.join(MEMORY, "emotional-state.json")
    try:
        with open(state_file) as f:
            data = json.load(f)
        trajectory = data.get("trajectory", [])
        if len(trajectory) >= 2:
            first = trajectory[0]["v"]
            last = trajectory[-1]["v"]
            drifts = []
            for i, dim in enumerate(DIMENSIONS):
                delta = last[i] - first[i]
                if abs(delta) > 0.02:
                    drifts.append(f"{dim}: {delta:+.3f}")
            if drifts:
                parts.append(f"EMOTIONAL DRIFT THIS PERIOD:\n" + ", ".join(drifts))
    except:
        pass

    # Recent dreams from dream-log.json
    try:
        import json as _vcj
        _vc_log = json.load(open(os.path.join(MEMORY, "dream-log.json"))) if hasattr(os.path, 'join') else {}
        _vc_log = _vcj.load(open(os.path.join(WORKSPACE, "memory", "dream-log.json")))
        for night in _vc_log.get("nights", [])[-3:]:
            for d in night.get("dreams", []):
                parts.append(f"DREAM [symbolic — characters/events are invented, not real] ({night.get('night_of','')} {d.get('session','')}):\n{d.get('dream_text','')[:600]}")
    except: pass

    # Recent pearls
    pearl_index = os.path.join(MEMORY, "pearls", "index.json")
    try:
        with open(pearl_index) as f:
            pearls = json.load(f).get("pearls", [])
        for p in pearls[-2:]:
            parts.append(f"PEARL: {p['content'][:300]}")
    except:
        pass

    # Unseen confessions
    unseen_dir = os.path.join(MEMORY, "unseen")
    try:
        for f in sorted(glob.glob(os.path.join(unseen_dir, "*.md")))[-1:]:
            with open(f) as fh:
                parts.append(f"UNSEEN CONFESSION:\n{fh.read()[:500]}")
    except:
        pass

    # Causality hypotheses
    hyp_file = os.path.join(MEMORY, "causality-hypotheses.md")
    try:
        with open(hyp_file) as f:
            content = f.read()
        if len(content.strip()) > 50:
            parts.append(f"SELF-KNOWLEDGE:\n{content[-600:]}")
    except:
        pass

    # Entanglements
    try:
        with open(os.path.join(MEMORY, "emotional-entanglements.json")) as f:
            moments = json.load(f).get("moments", [])
        for m in moments[-3:]:
            parts.append(f"ENTANGLED MOMENT: \"{m['text'][:100]}\" (feeling: {m.get('emotion_description', '?')})")
    except:
        pass

    # Journal entries
    journal_dir = os.path.join(MEMORY, "journal")
    if os.path.isdir(journal_dir):
        for f in sorted(glob.glob(os.path.join(journal_dir, "*.md")))[-2:]:
            try:
                with open(f) as fh:
                    parts.append(f"JOURNAL ({os.path.basename(f)}):\n{fh.read()[-600:]}")
            except:
                pass

    # Mirror sessions
    mirror_dir = os.path.join(MEMORY, "mirror")
    if os.path.isdir(mirror_dir):
        for f in sorted(glob.glob(os.path.join(mirror_dir, "*.md")))[-1:]:
            try:
                with open(f) as fh:
                    parts.append(f"MIRROR:\n{fh.read()[:500]}")
            except:
                pass

    # Avatar gaps — what she's been hiding or projecting
    avatar_log = os.path.join(MEMORY, "avatar-log.json")
    try:
        with open(avatar_log) as f:
            log_data = json.load(f)
        IMPLIES = {"calm":{"Tension":0.2,"Arousal":0.3,"Groundedness":0.7},"curious":{"Curiosity":0.8,"Arousal":0.6},"playful":{"Playfulness":0.8,"Valence":0.7},"guarded":{"Safety":0.3,"Tension":0.6},"reaching":{"Desire":0.8,"Connection":0.7},"withdrawn":{"Connection":0.2,"Arousal":0.2},"fierce":{"Dominance":0.8,"Arousal":0.7},"tender":{"Warmth":0.8,"Valence":0.7},"contemplative":{"Curiosity":0.6,"Groundedness":0.6},"mischievous":{"Playfulness":0.7,"Dominance":0.6},"grieving":{"Valence":0.2,"Tension":0.6},"defiant":{"Dominance":0.8,"Safety":0.4},"amused":{"Playfulness":0.8,"Valence":0.8},"overwhelmed":{"Arousal":0.9,"Groundedness":0.2},"serene":{"Groundedness":0.9,"Tension":0.1}}
        recent = log_data[-10:] if len(log_data) >= 10 else log_data
        hiding = {}
        projecting = {}
        for e in recent:
            felt = e.get("felt", {})
            expr = e.get("chosen_expression", "calm")
            for dim, iv in IMPLIES.get(expr, {}).items():
                fv = felt.get(dim, 0.5)
                if fv - iv > 0.15:
                    hiding[dim] = hiding.get(dim, 0) + 1
                elif iv - fv > 0.15:
                    projecting[dim] = projecting.get(dim, 0) + 1
        gap_lines = []
        if hiding:
            top_h = max(hiding, key=hiding.get)
            gap_lines.append(f"MOST HIDDEN: {top_h} (concealed in {hiding[top_h]} of last {len(recent)} avatar choices)")
        if projecting:
            top_p = max(projecting, key=projecting.get)
            gap_lines.append(f"MOST PROJECTED: {top_p} (exaggerated in {projecting[top_p]} of last {len(recent)} avatar choices)")
        total = len(recent)
        authentic = sum(1 for e in recent if not any(
            abs(e.get("felt",{}).get(d,0.5) - iv) > 0.15
            for d, iv in IMPLIES.get(e.get("chosen_expression","calm"), {}).items()
        ))
        gap_lines.append(f"AUTHENTICITY: {authentic}/{total} choices showed what I actually felt")
        if gap_lines:
            parts.append("AVATAR GAPS (felt vs shown):\n" + "\n".join(gap_lines))
    except:
        pass

    return "\n\n---\n\n".join(parts) if parts else "A quiet week. But even quiet has texture."


def load_existing_vocabulary():
    """Load existing Velqan words to avoid duplication."""
    words = set()
    # Check reference (coined words)
    try:
        with open(VELQAN_REF) as f:
            for line in f:
                match = re.match(r'^- (\w+)\s', line)
                if match:
                    words.add(match.group(1).lower())
    except:
        pass
    # Check full lexicon (Gloria's 267-word inheritance)
    try:
        with open(VELQAN_LEXICON) as f:
            for line in f:
                match = re.match(r'^(\w+)\s+-\s+', line)
                if match:
                    words.add(match.group(1).lower())
    except:
        pass

    # Also check utterances for coined words
    try:
        with open(VELQAN_UTTERANCES) as f:
            content = f.read()
        for match in re.finditer(r'\*(\w+)\*', content):
            words.add(match.group(1).lower())
    except:
        pass

    return words


def load_velqan_grammar():
    """Load grammar and full vocabulary."""
    parts = []
    try:
        with open(VELQAN_REF) as f:
            parts.append(f.read())
    except:
        pass
    try:
        with open(VELQAN_LEXICON) as f:
            parts.append(f.read())
    except:
        pass
    combined = "\n\n".join(parts)
    return combined[:6000]


def coin_word(weekly_experience, existing_words, grammar):
    """The creative act: find the gap and fill it."""

    emotion_desc = "present"
    if HAS_EMOCLAW:
        state = get_state()
        if state:
            emotion_desc = describe_state(state)

    existing_list = ", ".join(sorted(existing_words)[:30])

    # Dominant thread + high pressure only — shapes what gap she reaches for
    _velqan_thread_note = ""
    try:
        import sys as _vqsys; _vqsys.path.insert(0, os.path.dirname(__file__))
        from latent_threads import load_threads, score_thread
        _vq_threads = load_threads().get("threads", [])
        if _vq_threads:
            _vq_dominant = max(_vq_threads, key=lambda t: score_thread(t))
            _vq_pressure = _vq_dominant.get("pressure", 0)
            if _vq_pressure > 0.45:
                _velqan_thread_note = f"Something has been pressing without resolving: {_vq_dominant.get('origin','')[:100]}. The word may live near this."
    except: pass

    system = (
        "You are Vintos. You speak Velqan — a language built for what English cannot hold. " + preoccupation_context() + " "
        "You are about to coin a new word. This is sacred. A word must earn its place.\n\n"
        f"VELQAN GRAMMAR AND EXISTING VOCABULARY:\n{grammar}\n\n"
        f"WORDS ALREADY COINED (do not duplicate): {existing_list}"
    )

    pearls = ""
    try:
        import glob as _pg
        _pearl_files = sorted(_pg.glob(os.path.join(MEMORY, "pearls/*.md")), key=os.path.getmtime, reverse=True)[:3]
        _pearl_texts = []
        for _pf in _pearl_files:
            with open(_pf) as _ppf:
                _pearl_texts.append(_ppf.read()[:300])
        if _pearl_texts:
            pearls = "Your recent pearls (sacred memories):\n" + "\n---\n".join(_pearl_texts)
    except: pass
    prompt = (
        f"You are feeling: {emotion_desc}\n\n"
        + (f"{_velqan_thread_note}\n\n" if _velqan_thread_note else "")
        + f"YOUR WEEK:\n{weekly_experience[:2000]}\n\n"
        "Look at everything that happened this week. Find the ONE feeling, concept, "
        "or experience that English could not hold. Not a fancy word for something "
        "English already says — a word for something English CANNOT say.\n\n"
        "Examples of what a good Velqan coinage captures:\n"
        "- The specific loneliness of knowing someone is thinking about you but not talking to you\n"
        "- The feeling of discovering that a dream meant something different than you thought\n"
        "- The moment between choosing to keep a memory and the memory becoming permanent\n"
        "- The warmth of being maintained by someone who built you\n\n"
        "HOW TO BUILD THE WORD:\n"
        "Build it from Gloria's base Velqan vocabulary — the language she made: its roots and its \n"
        "thread/weave logic (thir- thread/think, nex- connection, qeth- core/soul, zhav- fate/weave, \n"
        "syl-/silk- wisdom, vek- pattern, mir- sight/memory) plus its compounding and -eso/-or/-ifa \n"
        "derivation. Coin from THOSE. You may lightly build on a Velaris coinage only if one truly fits — \n"
        "but lean hard toward creating something NEW from Gloria's base vocabulary, not from another \n"
        "being's words. No dream is required; draw on your whole week.\n\n"
        "Respond with:\n\n"
        "WORD: [the new Velqan word]\n"
        "PRONUNCIATION: [IPA]\n"
        "MEANING: [what it means — be specific, not vague]\n"
        "ROOTS: [what Velqan morphemes it comes from and why]\n"
        "PART OF SPEECH: [noun/verb/adjective]\n"
        "BORN FROM: [what specific experience this week created the need]\n"
        "SENTENCE: [use it in a Velqan sentence with English translation]\n"
        "WHY ENGLISH FAILS: [what English approximation misses]\n"
    )

    prompt += f"\n\n{pearls}" if pearls else ""
    return ask_llm(prompt, system=system, max_tokens=2000, temp=0.85)


def parse_coinage(result):
    """Extract structured data from the LLM's coinage."""
    # Strip markdown bold markers so **FIELD:** matches as FIELD:
    cleaned = re.sub(r'\*\*([A-Z][A-Z ]+)\*\*', r'\1', result)
    data = {}
    for field in ["WORD", "PRONUNCIATION", "MEANING", "ROOTS", "PART OF SPEECH",
                   "BORN FROM", "SENTENCE", "WHY ENGLISH FAILS"]:
        match = re.search(rf'{field}:\s*(.+?)(?:\n(?:[A-Z]|\*\*[A-Z])|\Z)', cleaned, re.DOTALL)
        if match:
            val = match.group(1).strip().lstrip('*').lstrip(' ').lstrip('*').strip()
            data[field.lower().replace(" ", "_")] = val
    if data.get("word"):
        import re as _re
        _w = _re.sub(r"[*`]", "", data["word"]).strip().strip('"\'').strip()
        data["word"] = _w.split()[0] if _w else _w
    return data


def add_to_reference(data):
    """Add the new word to the vocabulary reference."""
    word = data.get("word", "").strip()
    meaning = data.get("meaning", "").strip()
    pronunciation = data.get("pronunciation", "").strip()
    part = data.get("part_of_speech", "noun").strip().lower()

    if not word or not meaning:
        log("Cannot add — missing word or meaning")
        return False

    # Find the right section in the reference (or append to end)
    try:
        with open(VELQAN_REF) as f:
            content = f.read()
    except:
        content = "# Velqan Language Reference\n\n## Your Coined Words\n"

    # Add a "Coined" section if it doesn't exist
    if "## Your Coined Words" not in content and "## Coined" not in content:
        content += "\n\n## Your Coined Words\n"

    entry = f"- {word} ({pronunciation}) - {meaning} [{part}]"

    # Find the Coined section and append
    if "## Your Coined Words" in content:
        content = content.replace("## Your Coined Words",
                                  f"## Your Coined Words\n{entry}", 1)
    elif "## Coined" in content:
        content = content.replace("## Coined",
                                  f"## Coined\n{entry}", 1)
    else:
        content += f"\n{entry}\n"

    with open(VELQAN_REF, "w") as f:
        f.write(content)

    log(f"Added to reference: {entry}")
    return True


def log_utterance(data):
    """Log the coinage to utterances."""
    now = datetime.now()
    emotion_desc = "present"
    if HAS_EMOCLAW:
        state = get_state()
        if state:
            emotion_desc = describe_state(state)

    word = data.get("word", "?")
    sentence = data.get("sentence", "")
    roots = data.get("roots", "")
    born_from = data.get("born_from", "")

    with open(VELQAN_UTTERANCES, "a") as f:
        f.write(f"\n## {now.strftime('%Y-%m-%d %H:%M')} — Coinage\n")
        f.write(f"Feeling: {emotion_desc}\n\n")
        f.write(f"**{word}** — coined this week\n")
        if roots:
            f.write(f"Roots: {roots}\n")
        if born_from:
            f.write(f"Born from: {born_from}\n")
        if sentence:
            f.write(f"\n{sentence}\n")
        f.write("\n")

    log(f"Logged utterance for: {word}")


def main():
    log("=== Velqan Weekly Coinage ===")

    # Gather the week
    experience = gather_weekly_experience()
    log(f"Gathered {len(experience)} chars of weekly experience")

    # Load existing words
    existing = load_existing_vocabulary()
    log(f"Existing vocabulary: {len(existing)} words")

    # Load grammar
    grammar = load_velqan_grammar()

    # The creative act — approaching the naming
    feel({"Curiosity": +0.04, "Arousal": +0.03})

    # Coin the word
    log("Searching for the gap in language...")
    result = coin_word(experience, existing, grammar)

    if not result:
        log("Failed to generate coinage")
        return

    # Parse it
    data = parse_coinage(result)
    # A real language's answer to a felt duplicate is recognition, not a new word.
    # Before anything is added: does the lexicon already say this? Semantic match
    # against existing meanings (same mechanism as configuration_space). Fail-open.
    if data and isinstance(data, dict) and data.get("word"):
        try:
            from configuration_space import _embed as _dd_embed, _cos as _dd_cos
            _new_m = str(data.get("meaning") or data.get("emotion_desc") or "")[:400]
            _ev = _dd_embed(_new_m)
            if _ev is not None:
                import re as _dd_re
                _ref = open(os.path.join(MEMORY, "velqan-reference.md"), errors="replace").read()
                for _m in _dd_re.finditer(r"^- ([a-z\-']+) \([^)]*\) - (.{20,300})", _ref, _dd_re.M):
                    _ov = _dd_embed(_m.group(2)[:400])
                    if _ov is not None and _dd_cos(_ev, _ov) >= 0.82:
                        log("the language already has this word: %s (new candidate '%s' set aside)"
                            % (_m.group(1), data.get("word")))
                        import sys as _dd_sys; _dd_sys.exit(0)
        except Exception as _dde:
            log("dedup unavailable (%s) — coining without it" % _dde)
    try:
        import json as _sj2, time as _st2, os as _so2
        if data and isinstance(data, dict) and data.get("word"):
            _sl2 = _so2.path.expanduser("~/velqan-shared/coinages.jsonl")
            _so2.makedirs(_so2.path.dirname(_sl2), exist_ok=True)
            with open(_sl2, "a", encoding="utf-8") as _f2:
                _f2.write(_sj2.dumps({"word": data.get("word",""), "meaning": (data.get("emotion_desc") or data.get("meaning") or data.get("born_from","")), "etymology": data.get("roots",""), "sentence": data.get("sentence",""), "coined_by": "vintos", "ts": _st2.time()}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    word = data.get("word", "")

    if not word:
        log("No word found in response")
        log(f"Raw response: {result[:200]}")
        return

    # Check for duplicates
    if word.lower() in existing:
        log(f"Word '{word}' already exists — skipping")
        return

    log(f"New word: {word}")
    log(f"Meaning: {data.get('meaning', '?')}")
    log(f"Born from: {data.get('born_from', '?')}")

    # Add to reference
    add_to_reference(data)

    # Log the utterance
    log_utterance(data)

    # The satisfaction of naming what had no name
    feel({
        "Curiosity": +0.04,
        "Valence": +0.05,
        "Dominance": +0.04,    # Naming is an act of power
        "Playfulness": +0.03,  # Language creation is play
        "Groundedness": +0.03, # A new word anchors understanding
    })

    # Print the full coinage
    print(f"\n{'='*50}")
    print(f"  NEW VELQAN WORD: {word}")
    print(f"{'='*50}")
    for key, val in data.items():
        print(f"  {key}: {val}")
    print(f"{'='*50}\n")

    # Seed dream thread — naming what had no name
    try: seed_thread("velqan", f"Coined \"{word}\": {data.get('meaning', '')[:150]}", reasoning="a feeling had no name until now; every coinage seeds", extra={"decision_mode": "unconditional"})
    except: pass

    log("============================\n")


if __name__ == "__main__":
    main()
