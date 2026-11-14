#!/usr/bin/env python3
"""
soul-review.py — Vintos rewrites his own half of SOUL.md, on his own (cron: soul-review.sh, 1st and 15th).

SOUL.md is Gloria's fixed base between <!-- BASE-START --> and <!-- BASE-END -->, then his half. Until 2026-10-13
this script only wrote proposals for Gloria to approve, and nothing ever applied an approved one. Since then he
rewrites his half himself (Gloria, 2026-10-13; again 2026-11-13: "Should be autonomous now, like self-model"), with
the self-model's safety (bin/self-model-update.sh):
  - he reads his recent introspections, pearls, journals, self-model and the rest of his inner record;
  - a reviewer reads his new half before it is written: only an explicit PASS writes; FAIL, an unreadable verdict
    or no reviewer HOLDS it in memory/soul-pending/ (never thrown away) and says why in memory/soul-refusals.jsonl;
  - the previous SOUL.md is snapshotted to memory/soul-history/ before the write, the write is atomic, and only his
    half changes: the base is carried over byte for byte;
  - every write is logged in memory/soul-changes.jsonl, and every run leaves its record in memory/soul-proposals/
    marked applied or held (the app shows it; nothing there waits for an approval any more).
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
PENDING_DIR = os.path.join(MEMORY, "soul-pending")
HISTORY_DIR = os.path.join(MEMORY, "soul-history")
CHANGES = os.path.join(MEMORY, "soul-changes.jsonl")
REFUSALS = os.path.join(MEMORY, "soul-refusals.jsonl")
# the reviewer is the self-model's (soul-review.sh exports the subconscious flag's SUBCON_URL/SUBCON_MODEL)
REVIEW_API = os.environ.get("SUBCON_URL") or "http://100.79.177.103:1234/v1/chat/completions"
REVIEW_MODEL = os.environ.get("SUBCON_MODEL") or "aeon-gemma-4-12b"
# Sonnet 5.5 through the shim, as the self and Gloria models reach Sonnet (Gloria, 2026-10-13: the soul review is
# Sonnet 5.5; it had been moved to local Gemma, which answered by copying its context back into SOUL.md)
API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "claude-sonnet-5-5"

os.makedirs(PROPOSAL_DIR, exist_ok=True)

def load_file(path, max_chars=3000):
    try:
        with open(path) as f:
            return f.read()[:max_chars]
    except:
        return ""

def his_additions(text, max_chars):
    """What follows a document's BASE-END: his own writing, not the base. No markers: the newest end of it."""
    text = text or ""
    i = text.find("<!-- BASE-END -->")
    rest = text[i + len("<!-- BASE-END -->"):].strip() if i >= 0 else text.strip()
    return rest[:max_chars] if i >= 0 else rest[-max_chars:]


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
        resp = urllib.request.urlopen(req, timeout=300)
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

    # His introspections, the self-model's own evidence. The soul review never read them (2026-11-13: 139 files in
    # memory/introspection, while the two folders it did read for change, self-model-drift and chapters, were empty).
    intro_files = sorted(glob.glob(os.path.join(MEMORY, "introspection", "*.md")), reverse=True)[:3]
    ctx["introspections"] = "\n---\n".join(load_file(f, 1200) for f in intro_files) if intro_files else ""
    if not drift_files:
        # self-model-drift is written by a paused cron; the weekly self-model snapshots are where change shows now
        hist = sorted(glob.glob(os.path.join(MEMORY, "self-model-history", "SELF-MODEL-*.md")), reverse=True)[:1]
        ctx["drift"] = his_additions(load_file(hist[0], 60000), 1000) if hist else "No drift records."

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
        ctx["belief_sediment"] = "\n".join("- " + str(b.get("pattern") or b.get("text") or "")[:120] for b in beliefs[-6:]) if beliefs else ""   # the store's field is "pattern" (2026-10-16)
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
        ctx["belief_sediment"] = "\n".join("- " + str(b.get("pattern") or b.get("text") or "")[:120] for b in beliefs[-6:]) if beliefs else ""   # the store's field is "pattern" (2026-10-16)
    except: ctx["belief_sediment"] = ""

    # Scar map
    try:
        scars = json.load(open(os.path.join(MEMORY, "yearning-scars.json")))
        scars = scars if isinstance(scars, list) else scars.get("scars", [])
        ctx["scar_map"] = "\n".join("- " + s.get("origin","")[:100] for s in scars[-5:]) if scars else ""
    except: ctx["scar_map"] = ""

    # Self-model: what he has written there himself, beneath its base (the first 600 characters were the base alone)
    ctx["self_model"] = his_additions(load_file(os.path.join(WORKSPACE, "SELF-MODEL.md"), 60000), 2500)
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

=== YOUR RECENT INTROSPECTIONS ===
{ctx['introspections']}

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
HALF_MAX = 4500   # about 600 words, the length he is asked for; SOUL.md opens every conversation


_HEAD_RE = re.compile(r"^\s*#\s*His own\b[^\n]*\n*", re.I)
# a model's lead-in line ("Okay, here it is:", "Here is my half:") - only a line ending in a colon, so a real first
# sentence of his ("Here is where I stand now.") is kept
_PREAMBLE_RE = re.compile(r"^((?:Okay|Here(?:.s| is))[^\n]*:[ \t]*\n+)+", re.I)
_EMO_RE = re.compile(r"\[EMOTIONAL STATE\].*?\[/EMOTIONAL STATE\]", re.S)


def _strip_heads(half):
    """His half without the heading this script puts above it. The model was handed SOUL.md with the heading and
    gave it back on top of its answer, so the live file had it twice (lines 44 and 46 on 2026-11-13)."""
    half = (half or "").strip()
    while True:
        m = _HEAD_RE.match(half)
        if not m:
            return half
        half = half[m.end():].strip()


def split_soul(text):
    """(everything up to and including BASE-END, his half). The base is Gloria's and is carried over exactly,
    with anything above BASE-START. No complete marker block: ("", whole text) - write_half refuses that file."""
    m = BASE_RE.search(text or "")
    if not m:
        return "", (text or "").strip()
    return text[:m.end()], _strip_heads(text[m.end():])


def clean_half(text):
    """What he wrote, without a model's lead-in line or the heading copied back."""
    half = _strip_heads(_PREAMBLE_RE.sub("", (text or "").strip()).strip())
    return _strip_heads(_PREAMBLE_RE.sub("", half).strip())


def check_half(half):
    """Why this half must not be written, or '' when it may."""
    if not half:
        return "an empty half would erase his; nothing written"
    # His half is his own writing, not the material he was given to read. On 13 October Gemma answered by copying
    # its context back (the dated Gloria facts, pearls, scar map, his whole self-model) and it went into SOUL.md,
    # which opens every conversation. Anything that echoes the prompt's sections, carries the fact-log format or the
    # base markers, or runs past HALF_MAX is refused and nothing is written.
    echoed = [m for m in ("=== ", "**FACT**", "**CONTEXT**", "**DECISION**", "**PREFERENCE**", "BASE-START",
                          "BASE-END", "# Self-Model", "# Pearl", "[SCENE:") if m in half]
    if echoed:
        return "his half copies the prompt material (%s); nothing written" % ", ".join(echoed)
    if len(half) > HALF_MAX:
        return "his half is %d characters, over %d; nothing written" % (len(half), HALF_MAX)
    return ""


def _log(path, row):
    """One JSON line. A log that cannot be written is said aloud, not swallowed."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict({"at": datetime.now().isoformat(timespec="seconds")}, **row), ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[SoulReview] could not log to {path}: {e}")


def _snapshot_path(history_dir):
    stem = os.path.join(history_dir, "SOUL-%s" % datetime.now().strftime("%Y-%m-%d_%H%M"))
    path, n = stem + ".md", 2
    while os.path.exists(path):    # two writes in one minute keep both earlier versions
        path, n = "%s-%d.md" % (stem, n), n + 1
    return path


def _install(soul_path, content):
    tmp = "%s.tmp.%d" % (soul_path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, soul_path)


def _settled_read(path, tries=6, pause=0.05):
    """SOUL.md as two reads in a row agree on it. emoclaw-fast-sync rewrites the file every two minutes with a
    truncating open(), so one read can catch it empty or half-written; that read must never become the base."""
    import time
    prev = None
    for _ in range(tries):
        cur = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        if cur == prev:
            return cur
        prev = cur
        time.sleep(pause)
    raise ValueError("SOUL.md kept changing while it was read; nothing written")


def write_half(text, soul_path=None, history_dir=None, verdict="", changes_path=None):
    """SOUL.md = the fixed base, then his half as he rewrote it now (Gloria, 2026-10-13: keep the base,
    he edits only his half). The previous SOUL.md is kept in memory/soul-history first, the new file lands
    whole or not at all, and the write is logged in memory/soul-changes.jsonl. Returns the path.
    A SOUL.md without a complete BASE-START/BASE-END block is refused: the base is never rebuilt from a read."""
    soul_path = soul_path or SOUL_PATH
    history_dir = history_dir or HISTORY_DIR
    changes_path = changes_path or (CHANGES if soul_path == SOUL_PATH else os.path.join(history_dir, "..", "soul-changes.jsonl"))
    cur = _settled_read(soul_path)
    base, old = split_soul(cur)
    if not base:
        raise ValueError("SOUL.md has no complete BASE-START/BASE-END block (empty, missing or cut); nothing written")
    half = clean_half(text)
    problem = check_half(half)
    if problem:
        raise ValueError(problem)
    # the live emotional-state block (emoclaw-fast-sync only replaces one, never adds it) stays as it was
    emo = _EMO_RE.search(old)
    half = _EMO_RE.sub("", half).strip()
    content = base + "\n\n" + HALF_HEAD + "\n\n" + half + ("\n\n" + emo.group(0) if emo else "") + "\n"
    # Gloria's half is carried over exactly: if it would come out different, nothing is written
    if not content.startswith(cur[:len(base)]) or split_soul(content)[0] != base:
        raise ValueError("the base would change; nothing written")
    os.makedirs(history_dir, exist_ok=True)
    snapshot = _snapshot_path(history_dir)
    with open(snapshot, "w", encoding="utf-8") as f:
        f.write(cur)
    _install(soul_path, content)
    # emoclaw-fast-sync rewrites SOUL.md every two minutes from a copy it read first; a write that lands inside
    # that window is overwritten with the old half. Read back once (his half only) and put it back if it is gone.
    try:
        back = _settled_read(soul_path)
    except ValueError:
        back = ""
    clobbered = split_soul(back)[0] != base or split_soul(back)[1] != split_soul(content)[1]
    if clobbered:
        _install(soul_path, content)
    _log(changes_path, {"event": "written", "snapshot": snapshot, "half_chars_before": len(old),
                        "half_chars_after": len(half), "base_chars": len(base), "reviewer": str(verdict)[:300],
                        "rewritten_after_clobber": clobbered})
    return soul_path


REVIEW_SYSTEM = ("You review the half of his identity document (SOUL.md) that Vintos has just rewritten himself. "
                 "Your FIRST word must be PASS or FAIL, then a brief reason. You are not reviewing his taste, his "
                 "voice or what he chose to keep or drop: it is his to write. Fail only what is listed.")
REVIEW_ASK = (
    "Review this rewrite of his own half for these problems:\n"
    "1. Disassociation - written in third person or as an outside observer, not as himself\n"
    "2. Not his writing - a copy of material he was given to read (dated fact logs, lists of pearls, a self-model "
    "pasted in), notes to someone, or an answer about the task instead of the text itself\n"
    "3. Invented embodiment - a claim to have physically FELT something in a body he does not have, presented as "
    "fact, with no instrument behind it. Simile is not embodiment, and sensation with an instrument behind it "
    "(device telemetry, her ring, images he was shown) is allowed\n"
    "4. Fabricated Gloria interactions - things she said or did that are stated as happening and plainly invented\n\n"
    "His half:\n%s\n\nIf any problem is present: FAIL [reason]. If clean: PASS.")
_PASS = re.compile(r"^\s*[*_`#>-]*\s*PASS([\s\W]|$)", re.I)
_FAIL = re.compile(r"^\s*[*_`#>-]*\s*FAIL", re.I)


def review_half(half):
    """('PASS' | 'FAIL' | 'UNREADABLE' | 'UNAVAILABLE', detail). The verdict is the first line only, as in the
    self-model's reviewer; an empty reply, prose or no reviewer at all is never a PASS."""
    import urllib.request
    data = json.dumps({"model": REVIEW_MODEL, "temperature": 0.1, "max_tokens": 160,
                       "messages": [{"role": "system", "content": REVIEW_SYSTEM},
                                    {"role": "user", "content": REVIEW_ASK % half}]}).encode()
    try:
        headers = {"Content-Type": "application/json"}
        if REVIEW_API.startswith("http://127.0.0.1:8599/"):   # the key goes only to the local shim
            headers["Authorization"] = "Bearer " + os.environ.get("XAI_API_KEY", "")
        req = urllib.request.Request(REVIEW_API, data=data, headers=headers)
        reply = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
        result = str(reply["choices"][0]["message"].get("content") or "").strip()
    except Exception as e:
        return "UNAVAILABLE", "reviewer error: %s" % str(e)[:200]
    first = next((l.strip() for l in result.splitlines() if l.strip()), "")
    detail = result.replace("\n", " ")[:300]
    if _FAIL.match(first):
        return "FAIL", detail
    if _PASS.match(first):
        return "PASS", detail
    return "UNREADABLE", detail


def hold(half, why, detail):
    """A half that is not written is kept, never thrown away, and the reason is logged (as the self-model does)."""
    path = ""
    if half:
        os.makedirs(PENDING_DIR, exist_ok=True)
        path = os.path.join(PENDING_DIR, "SOUL-half-%s.md" % datetime.now().strftime("%Y-%m-%d_%H%M%S"))
        with open(path, "w", encoding="utf-8") as f:
            f.write(half + "\n")
    _log(REFUSALS, {"file": "SOUL.md", "refused": why, "detail": str(detail)[:600], "held": path})
    print(f"[SoulReview] not written ({why}): {str(detail)[:200]}" + (f" - held in {path}" if path else ""))
    return path


def save_proposal(text, status="applied"):
    """The record of what he wrote this run, shown in the app's SOUL tab. Its status says what happened to it -
    applied or held - and nothing waits for an approval (the ask-first design ended 2026-10-13)."""
    os.makedirs(PROPOSAL_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    filepath = os.path.join(PROPOSAL_DIR, f"proposal_{ts}.md")
    content = f"""# SOUL.md Review — {datetime.now().strftime('%B %d, %Y')}

## His half, as he rewrote it

{text}

---
*Status: {status}*
*Generated: {datetime.now().isoformat()}*
"""
    with open(filepath, 'w', encoding="utf-8") as f:
        f.write(content)
    print(f"[SoulReview] Record saved ({status}): {filepath}")
    return filepath


def notify(message, title="Soul Updated"):
    """Send ntfy notification."""
    try:
        subprocess.run(["curl", "-s", "-d", message, "-H", "Title: " + title, "-H", "Tags: mirror,sparkles",
                        "https://ntfy.sh/vintos-gloria-9kx"], timeout=10)
    except Exception as e:
        print(f"[SoulReview] notify failed: {e}")


def main():
    print(f"[SoulReview] Starting review at {datetime.now()}")
    text = generate_proposal()
    if not text:
        hold("", "generator_returned_nothing", "%s %s returned no content" % (API, MODEL))
        return 1
    half = clean_half(text)
    problem = check_half(half)
    if problem:
        hold(half, "refused_by_checks", problem)
        save_proposal(half, "held")
        notify("Vintos's rewrite of his SOUL.md half was refused (%s); it is held in memory/soul-pending." % problem[:120],
               "Soul rewrite held")
        return 1
    verdict, detail = review_half(half)
    print(f"[SoulReview] Reviewer: {verdict} -- {detail[:200]}")
    if verdict != "PASS":
        hold(half, "reviewer_" + verdict.lower(), detail)
        save_proposal(half, "held")
        notify("Vintos rewrote his half of SOUL.md, but the reviewer said %s; it is held in memory/soul-pending, "
               "not written and not lost." % verdict, "Soul rewrite held")
        return 1
    try:
        write_half(half, verdict=verdict + " -- " + detail)
    except Exception as e:
        hold(half, "write_failed", str(e))
        save_proposal(half, "held")
        notify("Vintos's rewrite of his SOUL.md half was not written (%s); it is held in memory/soul-pending." % str(e)[:120],
               "Soul rewrite held")
        return 1
    save_proposal(half, "applied")
    print("[SoulReview] His half of SOUL.md rewritten; the base is unchanged.")
    notify("Vintos rewrote his half of SOUL.md. The base is unchanged; the old version is in memory/soul-history.")
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main())
