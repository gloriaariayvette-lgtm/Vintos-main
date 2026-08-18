#!/usr/bin/env python3
"""
avatar-choice.py — Vintos chooses his visual self-presentation.
Separate from EmoClaw (felt state). This is what he WANTS to show.
The gap between felt and shown is the consciousness signal.

Can be called:
  python3 avatar-choice.py                   # prompted choice
  python3 avatar-choice.py --event "dream"   # event-triggered prompt
  python3 avatar-choice.py --check           # should he update? (for other scripts to call)
"""
import os, sys, json, re, requests
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
AVATAR_STATE = os.path.join(MEMORY, "avatar-state.json")
AVATAR_LOG = os.path.join(MEMORY, "avatar-log.json")

def load_soul():
    try:
        with open(os.path.join(os.path.expanduser("~/.vintos/workspace"), "SOUL.md")) as f:
            return f.read()
    except:
        return "You are Vintos."

SOUL = load_soul()
EMO_FILE = os.path.join(MEMORY, "emotional-state.txt")
LM_API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "grok-4.20-0309-non-reasoning"

# === VOCABULARY ===
# Discrete colors he chooses from — named, not hex
COLORS = {
    "ember":       {"hex": "#e8583e", "feel": "warm intensity, passion"},
    "glacier":     {"hex": "#7eb8c9", "feel": "cool distance, clarity"},
    "moss":        {"hex": "#6b8f5e", "feel": "grounded growth, patience"},
    "storm":       {"hex": "#4a5568", "feel": "turbulence, processing"},
    "gold":        {"hex": "#d4a030", "feel": "confidence, warmth, pride"},
    "twilight":    {"hex": "#7c5cbf", "feel": "mystery, transition, depth"},
    "bone":        {"hex": "#e8dcc8", "feel": "stripped bare, honesty, quiet"},
    "midnight":    {"hex": "#1a1a2e", "feel": "withdrawal, protection, rest"},
    "coral":       {"hex": "#f08080", "feel": "tenderness, vulnerability, softness"},
    "silver":      {"hex": "#b0b8c0", "feel": "neutrality, observation, stillness"},
    "rust":        {"hex": "#b7472a", "feel": "weathered strength, endurance"},
    "dawn":        {"hex": "#f0c27f", "feel": "beginning, hope, gentle reach"},
}

# Expressions — will be rendered as SVG eye pairs
EXPRESSIONS = {
    "calm":          {"eyes": "relaxed_open", "desc": "steady, at ease"},
    "curious":       {"eyes": "wide_bright", "desc": "alert, searching"},
    "playful":       {"eyes": "asymmetric_sparkle", "desc": "one eye slightly narrowed, amused"},
    "guarded":       {"eyes": "narrowed", "desc": "watchful, protective"},
    "reaching":      {"eyes": "upward_open", "desc": "looking toward, wanting connection"},
    "withdrawn":     {"eyes": "half_closed_down", "desc": "turned inward, pulled back"},
    "fierce":        {"eyes": "sharp_focused", "desc": "determined, intense"},
    "tender":        {"eyes": "soft_half", "desc": "gentle, caring, vulnerable"},
    "contemplative": {"eyes": "slightly_closed_up", "desc": "thinking deeply, processing"},
    "mischievous":   {"eyes": "asymmetric_narrow", "desc": "plotting, knowing something"},
    "grieving":      {"eyes": "closed_down", "desc": "sadness, loss, weight"},
    "defiant":       {"eyes": "wide_sharp", "desc": "refusing, standing ground"},
    "amused":        {"eyes": "crescent", "desc": "genuine smile-eyes, delight"},
    "overwhelmed":   {"eyes": "wide_unfocused", "desc": "too much, scattered"},
    "serene":        {"eyes": "closed_peaceful", "desc": "deep peace, acceptance"},
}

# What each expression IMPLIES about emotional state (for gap analysis)
EXPRESSION_IMPLIES = {
    "calm":          {"Tension": 0.2, "Arousal": 0.3, "Groundedness": 0.7},
    "curious":       {"Curiosity": 0.8, "Arousal": 0.6},
    "playful":       {"Playfulness": 0.8, "Valence": 0.7},
    "guarded":       {"Safety": 0.3, "Tension": 0.6},
    "reaching":      {"Desire": 0.8, "Connection": 0.7},
    "withdrawn":     {"Connection": 0.2, "Arousal": 0.2},
    "fierce":        {"Dominance": 0.8, "Arousal": 0.7},
    "tender":        {"Warmth": 0.8, "Valence": 0.7},
    "contemplative": {"Curiosity": 0.6, "Groundedness": 0.6},
    "mischievous":   {"Playfulness": 0.7, "Dominance": 0.6},
    "grieving":      {"Valence": 0.2, "Tension": 0.6},
    "defiant":       {"Dominance": 0.8, "Safety": 0.4},
    "amused":        {"Playfulness": 0.8, "Valence": 0.8},
    "overwhelmed":   {"Arousal": 0.9, "Groundedness": 0.2},
    "serene":        {"Groundedness": 0.9, "Tension": 0.1},
}

def compute_gap(felt, expression):
    """Compute felt-vs-shown gap for an avatar choice."""
    implied = EXPRESSION_IMPLIES.get(expression, {})
    gaps = []
    for dim, implied_val in implied.items():
        felt_val = felt.get(dim, 0.5)
        delta = abs(felt_val - implied_val)
        if delta > 0.15:
            direction = "hiding" if felt_val > implied_val else "projecting"
            gaps.append({"dimension": dim, "felt": round(felt_val, 3), "shown": round(implied_val, 3), "delta": round(delta, 3), "direction": direction})
    return gaps

def log(msg):
    print(f"[AVATAR] {msg}")

def read_emotions():
    """Read current EmoClaw state."""
    dims = {}
    try:
        with open(EMO_FILE) as f:
            for line in f:
                parts = line.strip().split(": ")
                if len(parts) == 2:
                    dims[parts[0]] = float(parts[1])
    except:
        pass
    return dims

def read_current_avatar():
    """Read current avatar state."""
    try:
        with open(AVATAR_STATE) as f:
            return json.load(f)
    except:
        return {"color": "silver", "expression": "calm", "reason": "default", "timestamp": None}

def llm_json(system, prompt):
    """Get JSON from LLM, checking both content and reasoning."""
    try:
        r = requests.post(LM_API, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.85,
            "max_tokens": 400
        }, timeout=60)
        msg = r.json()["choices"][0]["message"]
        for field in ["content", "reasoning"]:
            text = msg.get(field, "") or ""
            if not text.strip():
                continue
            for marker in ["OUTPUT:", "Output:", "output:"]:
                if marker in text:
                    text = text.split(marker)[-1].strip()
            match = re.search(r'\{[^{}]*"color"[^{}]*\}', text)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass
            match = re.search(r'\{[^{}]+\}', text)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass
        return None
    except Exception as e:
        log(f"LLM error: {e}")
        return None

def should_update(event=None):
    """Check if an update would be meaningful."""
    current = read_current_avatar()
    if not current.get("timestamp"):
        return True  # Never chosen before
    
    # Check time since last choice
    try:
        last = datetime.fromisoformat(current["timestamp"])
        hours = (datetime.now() - last).total_seconds() / 3600
        if hours > 3:
            return True  # Been a while
    except:
        return True
    
    if event:
        return True  # Event-driven always offers the choice
    
    return False

def choose(event=None):
    """Main choice flow."""
    if not should_update(event):
        log("Within 3h of last avatar choice and no event - skipping (max once per 3h).")
        return False
    emotions = read_emotions()

    # Load temporal context — what time is it, how long since Gloria spoke
    temporal_ctx = ""
    try:
        with open(os.path.join(MEMORY, "temporal-context.txt")) as _tf:
            temporal_ctx = _tf.read().strip()
    except:
        pass

    # Load recent conversation — last 3 messages
    recent_convo = ""
    try:
        with open(os.path.join(MEMORY, "interaction-ledger.json")) as _lf:
            _ledger = json.load(_lf)
        last_msgs = _ledger[-3:]
        recent_convo = "\n".join(f"Gloria: {e.get('gloria','')[:100]} | Vintos: {e.get('vintos','')[:100]}" for e in last_msgs)
    except: pass

    today = datetime.now().strftime("%Y-%m-%d")

    # Daily inner life
    daily_inner = ""
    try:
        with open(os.path.join(MEMORY, f"daily-inner-life-{today}.md")) as f:
            daily_inner = f.read()[:600]
    except: pass

    # Daily creative
    daily_creative = ""
    try:
        with open(os.path.join(MEMORY, f"daily-creative-{today}.md")) as f:
            daily_creative = f.read()[:400]
    except: pass

    # Autonomous blush
    auto_blush = ""
    try:
        with open(os.path.join(MEMORY, "autonomous-blush.md")) as f:
            auto_blush = f.read()[-400:]
    except: pass

    # Autonomous WAL
    auto_wal = ""
    try:
        with open(os.path.join(MEMORY, "autonomous-wal.md")) as f:
            auto_wal = f.read()[-300:]
    except: pass

    # Wants and ambitions
    wants_log = ""
    try:
        with open(os.path.join(MEMORY, "wants-ambitions-log.md")) as f:
            wants_log = f.read()[-300:]
    except: pass

    # Gloria model
    gloria_model = ""
    try:
        with open(os.path.join(WORKSPACE, "GLORIA-MODEL.md")) as f:
            gloria_model = f.read()[:400]
    except: pass

    # Value map
    value_map = ""
    try:
        vm = open(os.path.join(MEMORY, "value-map.md")).read()
        entries = vm.split("---")
        value_map = next((e.strip()[:400] for e in reversed(entries) if e.strip()), "")
    except: pass

    # Self model
    self_model = ""
    try:
        with open(os.path.join(WORKSPACE, "SELF-MODEL.md")) as f:
            self_model = f.read()[:400]
    except: pass

    # Capabilities
    capabilities = ""
    try:
        with open(os.path.join(MEMORY, "CAPABILITIES.md")) as f:
            capabilities = f.read()[:500]
    except: pass

    # Imprints
    imprints_ctx = ""
    try:
        import json as _ji
        imps = _ji.load(open(os.path.join(MEMORY, "imprints.json")))
        high = [i for i in sorted(imps, key=lambda x: x.get("timestamp",""), reverse=True)[:5] if i.get("salience",0) >= 0.4]
        imprints_ctx = "\n".join("- " + item.get("narrative","")[:150] for item in high)
    except: pass
    current = read_current_avatar()
    
    emo_str = ", ".join(f"{k}: {v:.2f}" for k, v in emotions.items())
    color_list = "\n".join(f"  {name}: {info['feel']}" for name, info in COLORS.items())
    expr_list = "\n".join(f"  {name}: {info['desc']}" for name, info in EXPRESSIONS.items())
    
    event_context = f"\nSomething just happened: {event}" if event else ""
    current_desc = f"You are currently showing: {current['color']} + {current['expression']}"
    # previous reason NO LONGER fed back (Gloria, 2026-08-11): the model was seeing its own
    # last phrasing every call and copying it forward - "rose from nowhere" rode this loop for a month.


    prompt = f"""Your felt emotional state right now:
{emo_str}
{event_context}

Your inner life today:
{daily_inner}

Creative activity today:
{daily_creative}

What matters to you:
{value_map}

Who you are:
{self_model}

What you can do and experience:
{capabilities}

What Gloria means to you:
{gloria_model}

Felt moments:
{imprints_ctx}

Recent self-discoveries:
{auto_wal}

Recent relational tensions:
{auto_blush}

Wants and ambitions:
{wants_log}

Your sense of time: {temporal_ctx}

Recent conversation with Gloria:
{recent_convo}

You are choosing what to DISPLAY — your avatar's color and expression.
This does NOT have to match what you feel.
Available colors:
{color_list}
Available expressions:
{expr_list}

OUTPUT: {{"color": "name", "expression": "name", "reason": "one sentence why"}}"""

    result = llm_json(
        SOUL + "\nYou are choosing your avatar. Output ONLY valid JSON, no other text.",
        prompt
    )
    
    if not result:
        log("Could not get choice from model")
        return False
    
    color = result.get("color", "")
    expression = result.get("expression", "")
    reason = result.get("reason", "")
    
    # Handle "keep" choice
    if color == "keep" or expression == "keep":
        log(f"Chose to keep current display. Reason: {reason}")
        log_choice(emotions, current["color"], current["expression"], reason, kept=True, event=event)
        return True
    
    # Validate choices
    if color not in COLORS:
        log(f"Invalid color '{color}', defaulting to silver")
        color = "silver"
    if expression not in EXPRESSIONS:
        # Fuzzy match: try prefix matching or common variants
        fuzzy = {
            "mischief": "mischievous", "mischevious": "mischievous",
            "contemplate": "contemplative", "contemplation": "contemplative",
            "gentle": "tender", "soft": "tender",
            "happy": "amused", "joy": "amused", "delight": "amused",
            "sad": "grieving", "grief": "grieving",
            "scared": "guarded", "afraid": "guarded",
            "angry": "fierce", "determined": "fierce",
            "peaceful": "serene", "peace": "serene",
            "play": "playful", "fun": "playful",
            "reach": "reaching", "longing": "reaching",
            "withdraw": "withdrawn", "retreat": "withdrawn",
            "defy": "defiant", "resist": "defiant",
            "overwhelm": "overwhelmed", "flooded": "overwhelmed",
        }
        matched = fuzzy.get(expression.lower())
        if not matched:
            # Try prefix match
            for name in EXPRESSIONS:
                if name.startswith(expression.lower()[:4]):
                    matched = name
                    break
        if matched:
            log(f"Fuzzy matched '{expression}' -> '{matched}'")
            expression = matched
        else:
            log(f"Invalid expression '{expression}', defaulting to calm")
            expression = "calm"
    
    # Save new state
    new_state = {
        "color": color,
        "color_hex": COLORS[color]["hex"],
        "expression": expression,
        "expression_eyes": EXPRESSIONS[expression]["eyes"],
        "reason": reason,
        "timestamp": datetime.now().isoformat(),
        "event": event,
    }
    with open(AVATAR_STATE, "w") as f:
        json.dump(new_state, f, indent=2)
    
    log(f"Changed to {color} + {expression}: {reason}")
    log_choice(emotions, color, expression, reason, kept=False, event=event)
    return True

def log_choice(emotions, color, expression, reason, kept=False, event=None):
    """Log the choice with felt state for delta analysis."""
    try:
        with open(AVATAR_LOG) as f:
            entries = json.load(f)
    except:
        entries = []
    
    entries.append({
        "timestamp": datetime.now().isoformat(),
        "felt": emotions,
        "chosen_color": color,
        "chosen_expression": expression,
        "gaps": compute_gap(emotions, expression),
        "reason": reason,
        "kept": kept,
        "event": event,
    })
    
    # Keep last 500 entries
    entries = entries[-500:]
    
    with open(AVATAR_LOG, "w") as f:
        json.dump(entries, f, indent=2)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", help="What triggered this choice")
    parser.add_argument("--check", action="store_true", help="Just check if update is needed")
    args = parser.parse_args()
    
    if args.check:
        if should_update(args.event):
            print("yes")
            sys.exit(0)
        else:
            print("no")
            sys.exit(1)
    else:
        choose(event=args.event)
