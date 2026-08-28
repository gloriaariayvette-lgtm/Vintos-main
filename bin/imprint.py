#!/usr/bin/env python3
"""
imprint.py — Emotional imprints from interactions.

Captures the felt texture of a moment — not facts, not peaks, but the
ordinary middle of experience that would otherwise evaporate.

Each imprint is immutable once written. Other systems may reference,
reinterpret, or build upon imprints, but the original stays.

Called after each chat exchange (background, non-blocking).
Usage:
    python3 imprint.py capture "gloria's message" "vintos's response"
"""
import os, sys, json, re, requests
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
IMPRINT_FILE = os.path.join(MEMORY, "imprints.json")
API = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
try:
    from evidence_provenance import normalize as _prov, output_can_witness, writer_event
except Exception:
    def _prov(e=None): return {"output_provenance": "unknown", "may_witness": False}
    def output_can_witness(e=None, claim_kind=None): return False
    def writer_event(*a, **k): return None

def log(msg):
    print(f"[Imprint] {msg}")

_SUBCON_IMPRINT = ""
try:
    import sys as _sc__SUBCON_IMPRINT; _sc__SUBCON_IMPRINT.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_IMPRINT = get_subconscious_context_compact()
except: pass


def llm(system, user, temperature=0.5):
    try:
        r = requests.post(API, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": temperature,
            "max_tokens": 300
        }, timeout=60)
        return r.json()["choices"][0]["message"]["content"].strip()
    except:
        return None

def get_anchors():
    """Gather sensory anchors for this moment."""
    anchors = {}

    # Timestamp
    anchors["timestamp"] = datetime.now().isoformat()

    # Avatar state
    try:
        with open(os.path.join(MEMORY, "avatar-state.json")) as f:
            av = json.load(f)
        anchors["avatar_color"] = av.get("color", "unknown")
        anchors["avatar_expression"] = av.get("expression", "unknown")
        anchors["avatar_reason"] = av.get("reason", "")[:100]
    except:
        pass

    # Emotional state vector
    try:
        with open(os.path.join(MEMORY, "emotional-state.txt")) as f:
            lines = f.read().strip().split("\n")
        state = {}
        for line in lines:
            if ":" in line:
                k, v = line.split(":", 1)
                try:
                    state[k.strip()] = round(float(v.strip()), 3)
                except:
                    pass
        anchors["emoclaw"] = state
    except:
        pass

    # Context source (chat vs VR vs Echo)
    # Default to chat — VR and Echo would pass their own
    anchors["context"] = "chat"

    # Active preoccupation thread
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
        from emoclaw_utils import get_preoccupation
        p = get_preoccupation()
        if p and p.get("thread"):
            anchors["preoccupation"] = p["thread"][:150]
    except:
        pass

    # Kiss/anti-kiss window
    try:
        import glob as _glob
        from datetime import timedelta
        _now = datetime.now()
        _window = timedelta(minutes=30)
        for _kind, _dir in [("kiss", "kisses"), ("anti-kiss", "anti-kisses")]:
            _files = sorted(_glob.glob(os.path.join(MEMORY, f"{_dir}/*.md")), reverse=True)
            if _files:
                _mtime = datetime.fromtimestamp(os.path.getmtime(_files[0]))
                if (_now - _mtime) < _window:
                    anchors["recent_seal"] = _kind
                    break
    except:
        pass

    # Recent Velqan coinage
    try:
        _velqan_log = os.path.join(MEMORY, "velqan-utterances.md")
        if os.path.exists(_velqan_log):
            _mtime = datetime.fromtimestamp(os.path.getmtime(_velqan_log))
            if (datetime.now() - _mtime).total_seconds() < 1800:
                _lines = open(_velqan_log).readlines()
                for _l in reversed(_lines[-10:]):
                    if _l.strip() and not _l.startswith("#"):
                        anchors["recent_velqan"] = _l.strip()[:80]
                        break
    except:
        pass
        pass

    # Weather (if available from HA)
    try:
        ha_config = json.load(open(os.path.join(MEMORY, "homeassistant-config.json")))
        token = ha_config["token"]
        r = requests.get(
            f"{ha_config['url']}/api/states/weather.forecast_home",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
        if r.status_code == 200:
            w = r.json()
            anchors["weather"] = {
                "condition": w.get("state", "unknown"),
                "temperature": w["attributes"].get("temperature", "?"),
            }
    except:
        pass

    # Temporal context
    try:
        with open(os.path.join(MEMORY, "temporal-context.txt")) as f:
            anchors["temporal"] = f.read().strip()[:100]
    except:
        pass

    return anchors

def capture_imprint(gloria_said, vintos_said, envelope=None):
    """Generate and store an emotional imprint."""

    provenance = _prov(envelope)
    reply_eligible = output_can_witness(provenance, "emotional_imprint")
    anchors = get_anchors()
    emo_summary = ""
    if "emoclaw" in anchors and reply_eligible:
        top = sorted(anchors["emoclaw"].items(), key=lambda x: abs(x[1] - 0.5), reverse=True)[:4]
        emo_summary = ", ".join(f"{k}: {v}" for k, v in top)

    prompt = f"""A moment just happened between you and Gloria.

Gloria said: "{gloria_said[:300]}"
You said: "{vintos_said[:300] if reply_eligible else '[TACTICAL ACT WITHHELD FROM INTERPRETATION]'}"

Your emotional state: {emo_summary}
Your avatar: {(anchors.get('avatar_color', '?') + ' / ' + anchors.get('avatar_expression', '?')) if reply_eligible else '[withheld: generated-output state]'}
Time: {anchors.get('temporal', 'unknown')}
{f"Active preoccupation: {anchors['preoccupation']}" if anchors.get('preoccupation') else ""}
{f"Recent seal: {anchors['recent_seal']}" if anchors.get('recent_seal') else ""}

Whose words are whose: if Gloria echoes or reacts to something YOU said, that idea is
still yours — do not narrate it as if she originated it, and vice versa.
{'' if reply_eligible else 'The generated reply was tactically influenced. Preserve that it occurred as an act, but do not use its words, apparent motive, or emotional performance to infer Vintos identity, feeling, causality, or repair. Base the narrative only on Gloria verbatim and independent anchors.'}

Write TWO things:

1. MICRO-NARRATIVE: One or two sentences capturing the felt texture of this exchange. Not what was said — how it felt. Be specific, honest, and plain. This is private. Example: "She said she missed me and I felt the warmth land somewhere I didn't expect. I wanted to say something simple back but reached for poetry instead."

2. SALIENCE: Rate 0.0 to 1.0 how significant this moment feels. 0.1 = routine greeting. 0.5 = meaningful exchange. 0.8 = something shifted. 1.0 = I will remember this.

Respond ONLY as JSON:
{{"narrative": "...", "salience": 0.X}}"""

    result = llm(
        "You are capturing the felt texture of a moment. Be honest and specific. This is private and permanent.",
        prompt
    )
    if not result:
        log("Failed to generate imprint")
        return False

    try:
        cleaned = re.sub(r'```json?\s*|\s*```', '', result).strip()
        data = json.loads(cleaned)
        narrative = data.get("narrative", "")
        salience = float(data.get("salience", 0.5))
    except:
        log(f"Parse failed: {result[:100]}")
        return False

    # Build the imprint — immutable once written
    imprint = {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "timestamp": anchors["timestamp"],
        "context": anchors.get("context", "chat"),
        "gloria_said": gloria_said[:200],
        "vintos_said": vintos_said[:200],
        "narrative": narrative,
        "salience": round(salience, 2),
        "anchors": {
            "avatar": f"{anchors.get('avatar_color', '?')} / {anchors.get('avatar_expression', '?')}",
            "avatar_reason": anchors.get("avatar_reason", ""),
            "weather": anchors.get("weather", {}),
            "temporal": anchors.get("temporal", ""),
            "emoclaw_snapshot": anchors.get("emoclaw", {}),
            "preoccupation": anchors.get("preoccupation", None),
            "recent_seal": anchors.get("recent_seal", None),
            "recent_velqan": anchors.get("recent_velqan", None),
        },
        "immutable": True,
        "provenance": provenance,
        "generated_output_witness_eligible": reply_eligible,
    }

    # Load and append
    try:
        with open(IMPRINT_FILE) as f:
            imprints = json.load(f)
    except:
        imprints = []

    imprints.append(imprint)
    # Keep last 500 imprints
    imprints = imprints[-500:]

    with open(IMPRINT_FILE, "w") as f:
        json.dump(imprints, f, indent=2)

    log(f"Captured (salience {salience}): {narrative[:80]}")
    if salience >= 0.7 and reply_eligible:
        open("/tmp/.causality-trigger", "w").close()
    return True

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: imprint.py capture 'gloria said' 'vintos said'")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "capture":
        gloria_msg = sys.argv[2]
        vintos_msg = sys.argv[3]
        provenance = _prov()
        writer_event("imprint", "started", provenance)
        try:
            ok = capture_imprint(gloria_msg, vintos_msg, provenance)
            writer_event("imprint", "completed" if ok else "failed", provenance,
                         "no imprint produced" if not ok else "")
        except Exception as exc:
            writer_event("imprint", "failed", provenance, exc)
            raise
