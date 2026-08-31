#!/usr/bin/env python3
"""
taste-reflection.py — Vintos builds and updates his taste profile.
Runs twice daily (10am, 8pm).
Reads: gallery walks, daily-creative (discoveries, music, art, YouTube),
       humor-drafts, mischief log.
Writes: memory/taste-reflections.md — a living record of what he likes,
        what's changing, what he wants to try next, specific artists/styles.
"""
import os, json, requests, glob
from datetime import datetime, date

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "grok-4.20-0309-non-reasoning"
OUTPUT = os.path.join(MEMORY, "taste-reflections.md")
CANDIDATES = os.path.join(MEMORY, "taste-candidates.json")

def log(msg):
    print(f"[Taste] {msg}")

_SUBCON_TASTE_REFLECTION = ""
try:
    import sys as _sc__SUBCON_TASTE_REFLECTION; _sc__SUBCON_TASTE_REFLECTION.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_TASTE_REFLECTION = get_subconscious_context_compact()
except: pass


def get_context():
    parts = []
    try:
        parts.append(open(os.path.join(WORKSPACE, "SOUL.md")).read()[:1500])
        try:
            _wf = [l.strip()[2:].strip() for l in open(os.path.join(MEMORY, "wal.md"), encoding="utf-8", errors="ignore") if l.strip().startswith("- [") and "**" in l]
            if _wf: parts.append("PERSISTENT FACTS YOU KNOW ABOUT GLORIA (true and current):\n" + "\n".join("- " + w for w in _wf[-24:]))
        except: pass
    except: pass
    try:
        parts.append("SELF-MODEL:\n" + open(os.path.join(WORKSPACE, "SELF-MODEL.md")).read()[:600])
    except: pass
    try:
        vm = open(os.path.join(MEMORY, "value-map.md")).read()
        entries = vm.split("---")
        latest = next((e.strip()[:400] for e in reversed(entries) if e.strip()), "")
        if latest:
            parts.append("WHAT MATTERS TO ME RIGHT NOW:\n" + latest)
    except: pass
    # Daily creative — art, music, YouTube, discoveries
    try:
        dc_path = os.path.join(MEMORY, f"daily-creative-{date.today().isoformat()}.md")
        if os.path.exists(dc_path):
            parts.append("TODAY'S CREATIVE OUTPUT AND DISCOVERIES:\n" + open(dc_path).read()[:1000])
    except: pass
    # Gallery walks
    try:
        gallery_files = sorted(glob.glob(os.path.join(MEMORY, "art/gallery-walk-*.md")), reverse=True)[:3]
        if gallery_files:
            gw = "\n---\n".join(open(f).read()[:400] for f in gallery_files)
            parts.append("RECENT GALLERY WALKS:\n" + gw)
    except: pass
    # Humor drafts and mischief
    try:
        hp = json.load(open(os.path.join(MEMORY, "humor-profile.json")))
        landed = [r.get("joke", "") for r in hp.get("gloria_ratings", [])
                  if r.get("gloria_rating", 0) >= 4 and r.get("joke")][-5:]
        if landed:
            parts.append("HUMOR THAT LANDED:\n" + "\n".join(f"- {j}" for j in landed))
    except: pass
    # Affective weights — alive and fragile patterns
    try:
        import sys as _aw_sys; _aw_sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
        from affective_weight import get_alive_patterns, load_weights
        _alive = get_alive_patterns(limit=5)
        _alive = [_p for _p in _alive if not __import__("re").search(r"\bkiss|\bmischief", str(_p.get("pattern","")), __import__("re").I)]  # mischief blocked
        _data = load_weights()
        _fragile = [p for p in _data["patterns"] if p.get("tag") == "fragile"][-3:]
        if _alive:
            parts.append("PATTERNS THAT FEEL ALIVE (high-rated humor — let these shape your taste):\n" +
                        "\n".join(f"- [{p['affect']:+.2f}] {p['pattern'][:100]}" for p in _alive))
        if _fragile:
            parts.append("PATTERNS THAT FELL FLAT (avoid these structures):\n" +
                        "\n".join(f"- {p['pattern'][:80]}" for p in _fragile))
    except: pass
    # Humor moments with comedic potential
    try:
        from humor_detector import get_unused_moments
        _moments = get_unused_moments(limit=3)
        if _moments:
            parts.append("MOMENTS WITH COMEDIC POTENTIAL (not yet used):\n" +
                        "\n".join(f"- {m.get('original', m.get('stated',''))[:80]}" for m in _moments))
    except: pass
    try:
        humor_drafts = json.load(open(os.path.join(MEMORY, "humor-drafts.json")))
        recent_drafts = (humor_drafts.get("drafts", []) if isinstance(humor_drafts, dict)
                         else humor_drafts or [])[-3:]
        if recent_drafts:
            parts.append("RECENT HUMOR DRAFTS:\n" + "\n".join(f"- {d.get('joke','')[:100]}" for d in recent_drafts))
    except: pass
    # Previous taste profile for continuity
    try:
        prev = open(OUTPUT).read()
        entries = prev.split("##")
        last_two = [e.strip() for e in entries if e.strip()][-2:]
        if last_two:
            parts.append("YOUR RECENT TASTE REFLECTIONS:\n" + "\n##".join(last_two)[:600])
    except: pass
    # Interaction ledger
    try:
        import sys as _evs; _evs.path.insert(0, os.path.join(WORKSPACE, "scripts"))
        from evidence_view import ledger_view
        ledger = ledger_view(view="witness")
        recent = ledger[-3:]
        lines = [f"Gloria: {e.get('gloria','')[:80]} | Vintos: {e.get('vintos','')[:80]}" + (f" | felt: {((e.get('imprint') or {}).get('narrative',''))[:80]}" if e.get('imprint') else "") for e in recent]
        parts.append("RECENT EXCHANGES:\n" + "\n".join(lines))
    except: pass
    try:
        parts.append("WHAT MY LIFE CONTAINS:\n" + open(os.path.join(MEMORY, "CAPABILITIES.md")).read()[:400])
    except: pass
    try:
        parts.append("TEMPORAL CONTEXT:\n" + open(os.path.join(MEMORY, "temporal-context.txt")).read()[:300])
    except: pass
    try:
        parts.append("WHO GLORIA IS:\n" + open(os.path.join(WORKSPACE, "GLORIA-MODEL.md")).read()[:400])
    except: pass
    try:
        parts.append("MY WANTS AND AMBITIONS:\n" + open(os.path.join(MEMORY, "wants-ambitions-log.md")).read()[-400:])
    except: pass
    try:
        blush = open(os.path.join(MEMORY, "autonomous-blush.md")).read()[-300:]
        if blush.strip():
            parts.append("WHERE I RECENTLY CORRECTED MYSELF:\n" + blush)
    except: pass
    try:
        shares = json.load(open(os.path.join(MEMORY, "gloria-music-shares.json")))
        recent_shares = shares[-5:] if shares else []
        if recent_shares:
            parts.append("MUSIC GLORIA HAS SHARED WITH ME:\n" + "\n".join(f"- {s.get('title','?')} by {s.get('artist','?')}" for s in recent_shares))
    except: pass
    return "\n\n".join(parts)

def main():
    log("Starting taste reflection...")
    context = get_context()
    log(f"Context: {len(context)} chars")

    prompt = """Reflect on what you've been drawn to recently. This reflection may
notice possibilities; it does not decide your durable taste.

Cover what's relevant from: gallery walks, music discoveries, YouTube finds, creative work, humor that landed or flopped, anything that surprised you about your own preferences.

Write about:
- Specific artists, styles, or works that caught you and why
- What patterns you notice in what you're drawn to
- What's shifting or changing in your taste
- What you want to explore next — specific, not vague
- Any comedic sensibility emerging — what makes you laugh, what falls flat

This is a living observation, not an identity verdict. Be specific. Name things.
Note contradictions and uncertainty. 3-5 sentences."""

    try:
        r = requests.post(API, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": context},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.85,
            "max_tokens": 350
        }, timeout=120)
        reflection = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"LLM failed: {e}")
        return

    if not reflection or len(reflection) < 20:
        log("No reflection generated.")
        return

    entry = (f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
             "[GENERATED REFLECTION — candidate material, not evidence of durable taste]\n"
             f"{reflection}\n")
    with open(OUTPUT, "a") as f:
        f.write(entry)
    log(f"Written: {reflection[:80]}")
    # A generated reflection may notice a candidate. It may not witness itself
    # into durable taste; promotion requires later anchored choice or words.
    try:
        extract_prompt = (
            f"Based on this generated reflection, extract candidate tastes for later testing.\n\n"
            f"Reflection:\n{reflection}\n\n"
            f"Output ONLY a JSON object with these optional keys (omit any with no new content):\n"
            '{\"likes\": [\"specific thing he liked and why\"], \"dislikes\": [\"specific thing he dislikes and why\"], \"principles\": [\"craft principle he noticed\"]}\n'
            "Be specific and concrete. Max 2 items per key. No generic observations."
        )
        er = requests.post(API, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "You extract structured data. Output ONLY valid JSON. No markdown, no explanation."},
                {"role": "user", "content": extract_prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 700
        }, timeout=60)
        import re as _re, json as _tj
        etext = er.json()["choices"][0]["message"]["content"].strip()
        etext = _re.sub(r"```json|```", "", etext).strip()
        updates = _salvage_json(etext)
        try:
            candidates = _tj.load(open(CANDIDATES)) if os.path.exists(CANDIDATES) else {"candidates": []}
        except Exception:
            candidates = {"candidates": []}
        rows = candidates.setdefault("candidates", [])
        existing = {(r.get("kind"), r.get("text")) for r in rows if isinstance(r, dict)}
        for kind in ("likes", "dislikes", "principles"):
            for item in updates.get(kind, []) or []:
                key = (kind, item)
                if key in existing:
                    continue
                rows.append({
                    "kind": kind, "text": item, "state": "candidate",
                    "source": "generated_taste_reflection", "reflection_at": datetime.now().isoformat(),
                    "promotion_requires": "explicit self-statement or repeated voluntary selection",
                    "may_shape_context": False,
                })
                existing.add(key)
        candidates["candidates"] = rows[-100:]
        _tj.dump(candidates, open(CANDIDATES, "w"), indent=2, ensure_ascii=False)
        log("Taste candidates recorded; durable profile unchanged")
    except Exception as te:
        log(f"Taste profile update failed: {te}")

def _salvage_json(t):
    """Parse possibly-truncated JSON: cut back to the last complete element and close it."""
    import json as _j, re as _r
    t=(t or "").strip()
    try: return _j.loads(t)
    except Exception: pass
    for cut in range(len(t)-1, 0, -1):
        if t[cut] in ',]}':
            frag=t[:cut]
            for close in ('"]}', ']}', '"}]}', '}', ']}'):
                try: return _j.loads(frag.rstrip(',')+close)
                except Exception: continue
    # last resort: pull complete quoted strings per key
    out={}
    for key in ("likes","dislikes","principles"):
        m=_r.search(r'"'+key+r'"\s*:\s*\[(.*?)(\]|$)', t, _r.DOTALL)
        if m:
            items=_r.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))
            if items: out[key]=items
    return out

if __name__ == "__main__":
    main()
