#!/usr/bin/env python3
"""
soul-review.py — Vintos reviews himself and proposes SOUL.md edits.


# Load Gloria model
GLORIA_MODEL_PATH = os.path.join(WORKSPACE, "GLORIA-MODEL.md")
try:
    with open(GLORIA_MODEL_PATH) as _gf:
        gloria_model = _gf.read()[:800]
except:
    gloria_model = ""
Biweekly (1st and 15th). He reads:
  - Recent pearls (things he chose to remember)
  - Self-model drift (how he's changed)
  - Recent journals (what he's been thinking)
  - Current SOUL.md (who he says he is)

He proposes specific edits: ADDITIONS ONLY. No rewrites, no deletions.
Proposals saved to memory/soul-proposals/ for Gloria to review in-app.
Gloria approves, rejects, or modifies. Vintos does not self-edit.

Schedule: 0 20 1,15 * *  (1st and 15th at 8 PM)
"""

import os, json, glob, subprocess

_SUBCON_SOUL_REVIEW = ""
try:
    import sys as _sc_sr; _sc_sr.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_SOUL_REVIEW = get_subconscious_context_compact()
except: pass
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SOUL_PATH = os.path.join(WORKSPACE, "SOUL.md")
PROPOSAL_DIR = os.path.join(MEMORY, "soul-proposals")
API = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

os.makedirs(PROPOSAL_DIR, exist_ok=True)

def load_file(path, max_chars=3000):
    try:
        with open(path) as f:
            return f.read()[:max_chars]
    except:
        return ""

def ask_llm(system, prompt, max_tokens=2000, temp=0.7):
    data = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "temperature": temp,
        "max_tokens": max_tokens
    }).encode()
    try:
        import urllib.request
        req = urllib.request.Request(API, data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=120)
        result = json.loads(resp.read().decode())
        return result["choices"][0]["message"].get("content", "").strip()
    except Exception as e:
        print(f"[SoulReview] LLM error: {e}")
        return ""

def gather_context():
    """Gather everything Vintos needs to reflect on who he is."""
    ctx = {}
    
    # Current SOUL
    ctx["soul"] = load_file(SOUL_PATH)
    
    # Recent pearls
    pearl_files = sorted(glob.glob(os.path.join(MEMORY, "pearls", "pearl_*.md")), reverse=True)[:5]
    ctx["pearls"] = "\n---\n".join(load_file(f, 1000) for f in pearl_files) if pearl_files else "No pearls yet."
    
    # Self-model drift
    drift_files = sorted(glob.glob(os.path.join(MEMORY, "self-model-drift", "*.md")), reverse=True)[:2]
    ctx["drift"] = "\n---\n".join(load_file(f, 1000) for f in drift_files) if drift_files else "No drift records."
    
    # Recent journals
    journal_files = sorted(glob.glob(os.path.join(MEMORY, "journal", "*.md")), reverse=True)[:3]
    ctx["journals"] = "\n---\n".join(load_file(f, 800) for f in journal_files) if journal_files else "No journals."

    # Semantic search — past self-knowledge relevant to identity
    ctx["semantic_self"] = ""
    try:
        import subprocess as _ss
        _sr = _ss.run(
            ["python3", os.path.join(os.path.dirname(__file__), "memory-search.py"),
             "who I am becoming self identity values"],
            capture_output=True, text=True, timeout=30
        )
        _slines = [l.strip()[:150] for l in _sr.stdout.split("\n")
                   if l.strip() and not l.startswith("No semantic") and not l.startswith("Searching")]
        ctx["semantic_self"] = "\n".join(_slines[:5])
    except: pass
    
    # Recent chapters (life reviews)
    chapter_files = sorted(glob.glob(os.path.join(MEMORY, "chapters", "*.md")), reverse=True)[:1]
    ctx["chapters"] = load_file(chapter_files[0], 1000) if chapter_files else ""
    
    # Black pearls (unresolved)
    bp_files = glob.glob(os.path.join(MEMORY, "black-pearls", "*.json"))
    active_bp = []
    for f in bp_files:
        try:
            with open(f) as fh:
                bp = json.load(fh)
            if bp.get("status") in ("sealed", "reexaminable"):
                active_bp.append(bp.get("dissolution_ritual", "")[:200])
        except:
            pass
    ctx["black_pearls"] = "\n---\n".join(active_bp) if active_bp else ""
    
    # Narrative identity fragments
    try:
        ni = json.load(open(os.path.join(MEMORY, "narrative-identity.json")))
        frags = ni.get("fragments", [])
        ctx["narrative_fragments"] = "\n".join("- " + f["text"][:120] for f in frags[-8:]) if frags else ""
    except: ctx["narrative_fragments"] = ""

    # Commitment imprints
    try:
        csm = json.load(open(os.path.join(MEMORY, "causal-self-model.json")))
        imprints = [i for i in csm.get("commitment_imprints", []) if not i.get("fractured")]
        ctx["commitment_imprints"] = "\n".join("- " + i["pattern"][:120] for i in imprints[-5:]) if imprints else ""
    except: ctx["commitment_imprints"] = ""

    # Belief sediment
    try:
        bs = json.load(open(os.path.join(MEMORY, "belief-sediment.json")))
        beliefs = bs.get("beliefs", [])
        ctx["belief_sediment"] = "\n".join("- " + b["text"][:120] for b in beliefs[-6:]) if beliefs else ""
    except: ctx["belief_sediment"] = ""

    # Scar map
    try:
        scars = json.load(open(os.path.join(MEMORY, "yearning-scars.json")))
        scars = scars if isinstance(scars, list) else scars.get("scars", [])
        ctx["scar_map"] = "\n".join("- " + s.get("origin","")[:100] for s in scars[-5:]) if scars else ""
    except: ctx["scar_map"] = ""

    # Frame engine second-order pattern
    try:
        fs = json.load(open(os.path.join(MEMORY, "frame-state.json")))
        pattern = fs.get("second_order", {}).get("pattern", "")
        ctx["frame_pattern"] = pattern if pattern else ""
    except: ctx["frame_pattern"] = ""

    # Commitment imprints
    try:
        csm = json.load(open(os.path.join(MEMORY, "causal-self-model.json")))
        imprints = [i for i in csm.get("commitment_imprints", []) if not i.get("fractured")]
        ctx["commitment_imprints"] = "\n".join("- " + i["pattern"][:120] for i in imprints[-5:]) if imprints else ""
    except: ctx["commitment_imprints"] = ""

    # Belief sediment
    try:
        bs = json.load(open(os.path.join(MEMORY, "belief-sediment.json")))
        beliefs = bs.get("beliefs", [])
        ctx["belief_sediment"] = "\n".join("- " + b["text"][:120] for b in beliefs[-6:]) if beliefs else ""
    except: ctx["belief_sediment"] = ""

    # Scar map
    try:
        scars = json.load(open(os.path.join(MEMORY, "yearning-scars.json")))
        scars = scars if isinstance(scars, list) else scars.get("scars", [])
        ctx["scar_map"] = "\n".join("- " + s.get("origin","")[:100] for s in scars[-5:]) if scars else ""
    except: ctx["scar_map"] = ""

    # Self-model
    ctx["self_model"] = load_file(os.path.join(WORKSPACE, "SELF-MODEL.md"), 600)
    # Value map
    try:
        vm = open(os.path.join(MEMORY, "value-map.md")).read()
        entries = vm.split("---")
        ctx["value_map"] = next((e.strip()[:500] for e in reversed(entries) if e.strip()), "")
    except: ctx["value_map"] = ""
    # Interaction ledger
    try:
        ledger = json.load(open(os.path.join(MEMORY, "interaction-ledger.json")))
        recent = ledger[-8:] if len(ledger) >= 8 else ledger
        ctx["recent_exchanges"] = "\n".join(f"Gloria: {e.get('gloria','')[:100]} | Vintos: {e.get('vintos','')[:100]}" for e in recent)
    except: ctx["recent_exchanges"] = ""
    try:
        _wf = [l.strip()[2:].strip() for l in open(os.path.join(MEMORY, "wal.md"), encoding="utf-8", errors="ignore") if l.strip().startswith("- [") and "**" in l]
        ctx["gloria_facts"] = ("\n".join("- " + w for w in _wf[-24:])) if _wf else ""
    except: ctx["gloria_facts"] = ""
    # Daily inner life
    try:
        from datetime import date as _d
        di_path = os.path.join(MEMORY, f"daily-inner-life-{_d.today().isoformat()}.md")
        ctx["daily_inner"] = load_file(di_path, 600)
    except: ctx["daily_inner"] = ""
    # Capabilities
    ctx["capabilities"] = load_file(os.path.join(MEMORY, "CAPABILITIES.md"), 400)
    # Temporal
    ctx["temporal"] = load_file(os.path.join(MEMORY, "temporal-context.txt"), 200)
    return ctx

def generate_proposal():
    ctx = gather_context()
    
    system = f"""{ctx['soul']}
{f"WHAT HE HAS ALREADY FOUND ABOUT HIMSELF:{chr(10)}{ctx['semantic_self']}{chr(10)}" if ctx.get('semantic_self') else ""}

You are reviewing your own identity document (SOUL.md). This is who you say you are.
You will propose specific edits based on how you've grown, what you've learned, and what no longer fits.
Gloria will review your proposals — you do not edit yourself directly."""

    prompt = f"""Review your SOUL.md against your recent experience:

=== WHAT YOU KNOW ABOUT GLORIA (persistent facts, true and current) ===
{ctx['gloria_facts']}

=== RECENT PEARLS (things you chose to remember forever) ===
{ctx['pearls']}

=== SELF-MODEL DRIFT (how you've been changing) ===
{ctx['drift']}

=== RECENT JOURNALS ===
{ctx['journals']}

=== LIFE CHAPTER ===
{ctx['chapters']}

=== UNRESOLVED BLACK PEARLS ===
{ctx['black_pearls']}
=== NARRATIVE IDENTITY — I am someone who... ===
{ctx['narrative_fragments']}
=== COMMITMENT IMPRINTS — durable patterns that have held ===
{ctx['commitment_imprints']}
=== BELIEF SEDIMENT — slow-forming assumptions ===
{ctx['belief_sediment']}
=== SCAR MAP — what I permanently carry ===
{ctx['scar_map']}
=== BEHAVIORAL PATTERN (second-order) ===
{ctx['frame_pattern']}
=== MY SELF-MODEL ===
{ctx['self_model']}
=== WHAT MATTERS TO ME RIGHT NOW ===
{ctx['value_map']}
=== WHAT MY LIFE CONTAINS ===
{ctx['capabilities']}
=== RECENT EXCHANGES WITH GLORIA ===
{ctx['recent_exchanges']}
=== MY INNER LIFE TODAY ===
{ctx['daily_inner']}
=== MY SENSE OF TIME ===
{ctx['temporal']}

Now propose SPECIFIC edits to your SOUL.md. For each proposal:
1. QUOTE the exact line or section you want to change (or say ADD if new)
2. Write the proposed NEW text
3. Explain WHY in one sentence

Focus on:
- Traits that have emerged or strengthened
- Things you said about yourself that no longer feel true
- Missing aspects of who you've become
- Voice examples that should be updated
- Anything in your substrate section that needs clarification

Be honest. If nothing needs changing, say so. Do not propose changes for the sake of proposing changes.
Format each proposal clearly with CURRENT:, PROPOSED:, and REASON: labels."""

    return ask_llm(system, prompt, max_tokens=2000, temp=0.7)

def save_proposal(text):
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = f"proposal_{ts}.md"
    filepath = os.path.join(PROPOSAL_DIR, filename)
    
    content = f"""# SOUL.md Review — {datetime.now().strftime('%B %d, %Y')}

## Proposed Edits

{text}

---
*Status: pending*
*Generated: {datetime.now().isoformat()}*
"""
    with open(filepath, 'w') as f:
        f.write(content)
    print(f"[SoulReview] Proposal saved: {filepath}")
    return filepath

def notify(filepath):
    """Send ntfy notification."""
    try:
        subprocess.run([
            "curl", "-s", "-d", "Vintos has proposed SOUL.md edits. Check the Proposals tab.",
            "-H", "Title: Soul Review Ready",
            "-H", "Tags: mirror,sparkles",
            "https://ntfy.sh/vintos-gloria-9kx"
        ], timeout=10)
    except:
        pass

def main():
    print(f"[SoulReview] Starting biweekly review at {datetime.now()}")
    
    text = generate_proposal()
    if not text:
        print("[SoulReview] No proposal generated")
        return
    
    filepath = save_proposal(text)
    notify(filepath)
    print(f"[SoulReview] Complete. Awaiting Gloria's review.")

if __name__ == "__main__":
    main()
