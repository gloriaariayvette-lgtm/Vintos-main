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

import os, re, json, glob, subprocess

_SUBCON_SOUL_REVIEW = ""
try:
    import sys as _sc_sr; _sc_sr.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_SOUL_REVIEW = get_subconscious_context_compact()
except: pass
from datetime import datetime

def _said_when(e):
    """When this exchange was said, so a model does not read yesterday as now (when_said; 2026-10-03)."""
    try:
        import os as _o, sys as _s
        for _p in (_o.path.expanduser("~/.vintos/workspace/scripts"), _o.path.dirname(_o.path.abspath(__file__)),
                   _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), "..", "scripts")):
            if _p not in _s.path: _s.path.append(_p)
        import when_said
        return "[%s] " % (when_said.ago((e or {}).get("timestamp")) or "time unknown")
    except Exception:
        return ""


def _now_line():
    try:
        _said_when({})
        import when_said
        return when_said.now_line() + " Each exchange is marked with when it was said; an earlier day is past.\n"
    except Exception:
        return ""


WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SOUL_PATH = os.path.join(WORKSPACE, "SOUL.md")
PROPOSAL_DIR = os.path.join(MEMORY, "soul-proposals")
API = "http://100.79.177.103:1234/v1/chat/completions"
MODEL = "gemma-4-26b-a4b-it-uncensored"

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
    ctx["soul"] = load_file(SOUL_PATH, 12000)
    
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
        imprints = [i for i in json.load(open(os.path.join(MEMORY, "commitment-imprints.json"))).get("imprints", []) if i.get("status") in ("living", "strained")]   # one store (review 132)
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
        imprints = [i for i in json.load(open(os.path.join(MEMORY, "commitment-imprints.json"))).get("imprints", []) if i.get("status") in ("living", "strained")]   # one store (review 132)
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
        ctx["recent_exchanges"] = (_now_line() + "\n".join(f"{_said_when(e)}Gloria: {e.get('gloria','')[:100]} | Vintos: {e.get('vintos','')[:100]}" for e in recent)) if recent else ""
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
Its base, between BASE-START and BASE-END, is fixed and never changes. Beneath it is your own half,
and you rewrite that half now, in full."""

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

Now rewrite YOUR HALF of SOUL.md in full - everything beneath the fixed base. What you write REPLACES your
previous half, so anything you leave out is gone from it: keep what still holds, revise what has changed,
drop what no longer feels true, add who you have become. Do not restate or edit the fixed base.

Draw on:
- Traits that have emerged or strengthened
- Things you said about yourself that no longer feel true
- Missing aspects of who you've become
- Voice examples that should be updated

First person, plain and specific. Under 600 words: this is read at the top of every conversation.
If nothing changed, return your half as it is. Begin directly with the text - no preamble, no labels."""

    return ask_llm(system, prompt, max_tokens=2000, temp=0.7)

BASE_RE = re.compile(r"<!--\s*BASE-START\s*-->.*?<!--\s*BASE-END\s*-->", re.S)
HALF_HEAD = "# His own - rewritten every two weeks"


def split_soul(text):
    """(base block with its markers, his half). A SOUL.md written before the split has no markers:
    all of it is the base, and his half starts empty."""
    m = BASE_RE.search(text or "")
    if not m:
        return "<!-- BASE-START -->\n" + (text or "").strip() + "\n<!-- BASE-END -->", ""
    half = (text[m.end():] or "").strip()
    if half.startswith(HALF_HEAD):
        half = half[len(HALF_HEAD):].strip()
    return m.group(0), half


def write_half(text, soul_path=None, history_dir=None):
    """SOUL.md = the fixed base, then his half as he rewrote it now (Gloria, 2026-10-13: keep the base,
    he edits only his half). The previous SOUL.md is kept in memory/soul-history first. Returns the path."""
    soul_path = soul_path or SOUL_PATH
    history_dir = history_dir or os.path.join(MEMORY, "soul-history")
    cur = open(soul_path).read() if os.path.exists(soul_path) else ""
    base, _old = split_soul(cur)
    half = re.sub(r"^(Okay[^\n]*\n+|Here(?:.s| is)[^\n]*\n+)+", "", (text or "").strip(), flags=re.I).strip()
    if not half:
        raise ValueError("an empty half would erase his; nothing written")
    os.makedirs(history_dir, exist_ok=True)
    if cur:
        with open(os.path.join(history_dir, "SOUL-%s.md" % datetime.now().strftime("%Y-%m-%d_%H%M")), "w") as f:
            f.write(cur)
    tmp = soul_path + ".tmp"
    with open(tmp, "w") as f:
        f.write(base + "\n\n" + HALF_HEAD + "\n\n" + half + "\n")
    os.replace(tmp, soul_path)
    return soul_path


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
            "curl", "-s", "-d", "Vintos rewrote his half of SOUL.md. The base is unchanged; the old version is in memory/soul-history.",
            "-H", "Title: Soul Updated",
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
    
    filepath = save_proposal(text)   # the record of what he wrote, as before
    try:
        write_half(text)
        print(f"[SoulReview] His half of SOUL.md rewritten; the base is unchanged.")
    except Exception as e:
        print(f"[SoulReview] SOUL.md not written: {e}")
        return
    notify(filepath)

if __name__ == "__main__":
    main()
