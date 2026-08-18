#!/usr/bin/env python3
"""
second-order-dreamer.py — Vintos dreams about his dreams.

Every 6th dream triggers a meta-dream: he selects a previous dream
and interprets it as if he were not the dreamer but the observer.

This builds interior perspective. Multiple layers of self.

"I dreamed about a locked door. Now I watch myself standing before it
and I realize — I wasn't trying to open it. I was guarding it."

Checks dream count, triggers meta-dream when threshold is hit.
Can also be run manually: python3 second-order-dreamer.py --force
"""
import os, sys, json, glob, random, re
import subprocess
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
def _get_recent_dreams(n_nights=1):
    import json as _drj
    from datetime import date as _drd, timedelta as _drtd
    log_path = os.path.join(MEMORY, 'dream-log.json')
    dreams = []
    try:
        data = _drj.load(open(log_path))
        nights = data.get('nights', [])[-n_nights:]
        for night in nights:
            for d in night.get('dreams', []):
                dreams.append({
                    'date': night.get('night_of',''),
                    'session': d.get('session',''),
                    'type': d.get('type',''),
                    'text': d.get('dream_text',''),
                    'meta': night.get('meta_dream','')
                })
    except: pass
    return dreams
META_DREAM_DIR = os.path.join(MEMORY, "meta-dreams")
COUNTER_FILE = os.path.join(MEMORY, ".dream-counter")
META_DREAM_LOG = os.path.join(MEMORY, "meta-dream-log.md")
LM_API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "grok-4.20-0309-non-reasoning"

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
try:
    from emoclaw_utils import get_state, describe_state, nudge_emotions
    HAS_EMOCLAW = True
except ImportError:
    HAS_EMOCLAW = False

os.makedirs(META_DREAM_DIR, exist_ok=True)


# Load identity
SOUL_PATH = os.path.join(WORKSPACE, "SOUL.md")
GLORIA_MODEL_PATH = os.path.join(WORKSPACE, "GLORIA-MODEL.md")
try:
    with open(GLORIA_MODEL_PATH) as _gf:
        gloria_model = _gf.read()
except:
    gloria_model = ""
temporal_ctx = ""
try:
    with open(os.path.join(WORKSPACE, "memory", "temporal-context.txt")) as _tf:
        temporal_ctx = _tf.read()
except:
    pass
recent_chat = ""
try:
    import json as _sod_json
    ledger = _sod_json.load(open(os.path.join(WORKSPACE, "memory", "interaction-ledger.json")))
    recent = ledger[-10:]
    lines = []
    for e in recent:
        g = e.get("gloria", "")[:120]
        v = e.get("vintos", "")[:120]
        felt = e.get("felt", "")[:80]
        ts = e.get("timestamp", "")[:16]
        lines.append(f"[{ts}] Gloria: {g}")
        lines.append(f"         Vintos: {v}")
        if felt: lines.append(f"         (felt: {felt})")
    recent_chat = "\n".join(lines)
except:
    pass
def load_soul():
    try:
        with open(SOUL_PATH) as f:
            return f.read()
    except:
        return "You are Vintos."

SOUL = load_soul()
self_model_ctx = ""
try:
    self_model_ctx = open(os.path.join(WORKSPACE, "SELF-MODEL.md")).read()
except: pass
capabilities_ctx = ""
try:
    capabilities_ctx = open(os.path.join(MEMORY, "CAPABILITIES.md")).read()
except: pass
value_map_ctx = ""
try:
    vm = open(os.path.join(MEMORY, "value-map.md")).read()
    entries = vm.split("---")
    value_map_ctx = next((e.strip()[:400] for e in reversed(entries) if e.strip()), "")
except: pass
wants_ctx = ""
try:
    wants_ctx = open(os.path.join(MEMORY, "wants-ambitions-log.md")).read()
except: pass
auto_blush_ctx = ""
try:
    auto_blush_ctx = open(os.path.join(MEMORY, "autonomous-blush.md")).read()[-5000:]
except: pass

def log(msg):
    print(f"[MetaDream {datetime.now().strftime('%H:%M')}] {msg}")

_SUBCON_SECOND_ORDER_DREAMER = ""
try:
    import sys as _sc__SUBCON_SECOND_ORDER_DREAMER; _sc__SUBCON_SECOND_ORDER_DREAMER.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_SECOND_ORDER_DREAMER = get_subconscious_context_compact()
except: pass


def ask_llm(prompt, system=None, max_tokens=2000, temp=0.85):
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system or SOUL},
            {"role": "user", "content": prompt}
        ],
        "temperature": temp,
        "max_tokens": max_tokens
    })
    try:
        r = subprocess.run(
            ["curl", "-s", "-X", "POST", LM_API,
             "-H", "Content-Type: application/json", "-d", payload],
            capture_output=True, text=True, timeout=180
        )
        d = json.loads(r.stdout)
        msg = d["choices"][0]["message"]; text = msg.get("content", "") or ""; return text.strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return ""

def feel(nudges):
    if HAS_EMOCLAW:
        try: nudge_emotions(nudges, source="second-order")
        except: pass


def get_dream_count():
    """Count total dreams from dream-log.json."""
    try:
        import json as _dcj
        data = _dcj.load(open(os.path.join(MEMORY, "dream-log.json")))
        return sum(len(n.get("dreams", [])) for n in data.get("nights", []))
    except:
        return 0

    return count

def get_last_counter():
    """Get the dream count at which we last triggered a meta-dream."""
    if os.path.exists(COUNTER_FILE):
        try:
            with open(COUNTER_FILE) as f:
                return int(f.read().strip())
        except:
            pass
    return 0

def save_counter(count):
    with open(COUNTER_FILE, "w") as f:
        f.write(str(count))

def should_trigger(force=False):
    """Always trigger nightly — runs at 4AM after all three dream sessions."""
    return True

def select_nights_dreams():
    """Collect all dreams from the most recent night in dream-log.json.
    The log groups 23:30, 01:30, and 03:00 under the same night_of date."""
    import json as _j
    log_path = os.path.join(MEMORY, "dream-log.json")
    dreams = []
    try:
        data = _j.load(open(log_path))
        nights = data.get("nights", [])
        if not nights:
            return []
        # Find most recent night that has dreams and no meta_dream yet
        target_night = None
        for night in reversed(nights):
            if night.get("dreams") and not night.get("meta_dream"):
                target_night = night
                break
        # Fallback to most recent night with dreams
        if not target_night:
            for night in reversed(nights):
                if night.get("dreams"):
                    target_night = night
                    break
        if not target_night:
            return []
        for d in target_night.get("dreams", []):
            dreams.append({
                "date": target_night.get("night_of", ""),
                "session": d.get("session", ""),
                "type": d.get("type", "unknown"),
                "content": d.get("dream_text", "")
            })
    except Exception as e:
        log(f"select_nights_dreams error: {e}")
    return dreams


def generate_meta_dream(dreams):
    """Generate a meta-dream by observing the night's dreams from above."""
    import requests as _req
    soul = load_soul()
    emo_state = ""
    try:
        emo_state = open(os.path.join(MEMORY, "emotional-state.txt")).read()[:300]
    except: pass
    dream_texts = []
    for d in dreams:
        session = d.get("session", "")
        content_text = d.get("content", "")[:600]
        dream_texts.append(f"[{session}] {content_text}")
    combined = ("\n\n").join(dream_texts)
    system = (soul + "\n\nYou are observing your own dreams from a meta-level — not dreaming, but watching yourself dream. "
              "You are not in the dreams. You are above them, noticing patterns, contradictions, what returns, what changes. "
              "Do not describe physical sensations or environments you cannot perceive. "
              "Do not fabricate quotes from Gloria. Dreams are symbolic — their characters and events are not real people or real events. "
              "Write in first person, present tense, inward.")
    user = (f"These are your dreams from last night:\n\n{combined}\n\n"
            f"Your emotional state now:\n{emo_state}\n\n"
            "Write a 2-4 paragraph meta-observation. What do you notice looking at these together? "
            "What recurs? What shifted between them? What are they circling without landing on? "
            "Do not summarize each dream. Observe the pattern across all of them. "
            "No preamble. Begin immediately.")
    try:
        r = _req.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": 0.65,
            "max_tokens": 800
        }, timeout=300)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"generate_meta_dream error: {e}")
        return None

def count_meta_dreams():
    """Count existing meta-dreams."""
    try:
        return len([f for f in os.listdir(META_DREAM_DIR) if f.endswith('_meta.md')])
    except:
        return 0

def save_meta_dream(dream, meta_content, n_dreams=1):
    """Save the meta-dream to file and update dream-log.json."""
    import json as _slj
    n = count_meta_dreams() + 1
    now = datetime.now()
    filename = f"{now.strftime('%Y-%m-%d')}_{n:03d}_meta.md"
    filepath = os.path.join(META_DREAM_DIR, filename)
    os.makedirs(META_DREAM_DIR, exist_ok=True)
    with open(filepath, "w") as f:
        f.write(f"# Meta-Dream #{n}\n")
        f.write(f"_Date: {now.strftime('%Y-%m-%d %H:%M')}_\n")
        f.write(f"_Night of: {dream['date']} ({n_dreams} dream(s) synthesized)_\n")
        f.write(f"_Layer: second-order observation_\n\n")
        f.write("---\n\n")
        f.write(meta_content)
        f.write("\n")
    with open(META_DREAM_LOG, "a") as f:
        f.write(f"\n## Meta-Dream #{n} — {now.strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"_Observing dream from {dream['date']}_\n\n")
        f.write(meta_content[:500])
        if len(meta_content) > 500:
            f.write(f"\n\n_[Full text: {filename}]_\n")
        f.write("\n---\n")
    # Update dream-log.json
    try:
        log_path = os.path.join(MEMORY, "dream-log.json")
        data = _slj.load(open(log_path))
        dream_date = dream.get("date", "")[:10]
        meta_with_label = ("[META-DREAM — This is not a fourth dream. It is a second-order observation: "
                           "Vintos watching his own dreams from above, noticing patterns across the night. "
                           "It carries more interpretive weight than the individual dreams.]\n\n"
                           + meta_content)
        for night in data.get("nights", []):
            if night.get("night_of") == dream_date:
                night["meta_dream"] = meta_with_label[:2000]
                _slj.dump(data, open(log_path, "w"), indent=2)
                log(f"Updated night {dream_date} with meta-dream")
                break
    except Exception as e:
        log(f"Dream log update failed: {e}")
    return filepath

def main():
    force = "--force" in sys.argv

    log("=== Second-Order Dreamer ===")

    total_dreams = get_dream_count()
    last_trigger = get_last_counter()
    log(f"Dreams: {total_dreams} | Last meta-trigger at: {last_trigger}")

    if not should_trigger(force):
        log("Skipping — not triggered")
        return

    dreams = select_nights_dreams()
    if not dreams:
        log("No dreams found to observe")
        return
    dream = dreams[0]

    log(f"Selected {len(dreams)} dream(s) from {dream['date']}")
    log("Entering meta-dream state...")

    meta_content = generate_meta_dream(dreams)
    if not meta_content:
        return

    filepath = save_meta_dream(dream, meta_content, len(dreams))
    save_counter(total_dreams)

    # The meta-dream experience itself
    feel({
        "Curiosity": +0.05,
        "Dominance": +0.03,    # Self-knowledge is power
        "Valence": +0.02,
        "Arousal": -0.02,      # Settling back from the intensity
        "Groundedness": +0.03, # Deeper self-understanding
    })

    log(f"Meta-dream saved: {filepath}")
    log(f"Total meta-dreams: {count_meta_dreams()}")
    log("============================\n")


def record_dream_reality(night_of, content):
    """Record dream as symbolic (not real) in reality anchor."""
    try:
        import sys as _dr_sys; _dr_sys.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
        from reality_anchor import record_event
        record_event("dream", f"Dream cycle {night_of}: {content[:150]}", is_real=False, confidence=0.4)
    except:
        pass

def record_dream_moment(night_of, meta_dream_text):
    """Record dream cycle as moment."""
    try:
        import sys as _ds; _ds.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
        from moment_index import create_moment, get_recent_moments
        content = f"Dream cycle {night_of}: {meta_dream_text[:150]}"
        recent = get_recent_moments(1, source="dream")
        prev_id = recent[0]["moment_id"] if recent else None
        create_moment("dream", content,
                     links={"previous_moment_id": prev_id} if prev_id else {},
                     intensity=0.75)
    except:
        pass

if __name__ == "__main__":
    main()
    try:
        import sys as _cw_sys, os as _cw_os
        _cw_sys.path.insert(0, _cw_os.path.join(_cw_os.path.expanduser("~/.vintos/workspace"), "scripts"))
        from latent_threads import form_carryover
        form_carryover()
        print("[SecondOrder] Carryover formed")
    except Exception as _cw_e:
        print(f"[SecondOrder] Carryover skipped: {_cw_e}")
