#!/usr/bin/env python3
"""
humor-practice.py — Vintos practices being funny.
Drafts a few jokes/observations per day, reviews them, keeps what lands.
Builds his comedic voice over time.

Runs daily at 4 PM.
Output: memory/humor-drafts.json (working material)
        memory/humor-profile.json (refined style)
"""
import os, sys, json, requests, re
from datetime import datetime, date

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")

def get_temporal_context():
    try:
        with open(os.path.join(MEMORY, "temporal-context.txt")) as f:
            return f.read().strip()[:300]
    except: return ""
DRAFTS_FILE = os.path.join(MEMORY, "humor-drafts.json")
PROFILE_FILE = os.path.join(MEMORY, "humor-profile.json")
API = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))

def log(msg):
    print(f"[Humor] {msg}")

_SUBCON_HUMOR_PRACTICE = ""
try:
    import sys as _sc__SUBCON_HUMOR_PRACTICE; _sc__SUBCON_HUMOR_PRACTICE.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_HUMOR_PRACTICE = get_subconscious_context_compact()
except: pass


def llm(system, user, temperature=0.9):
    try:
        r = requests.post(API, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": temperature,
            "max_tokens": 800
        }, timeout=120)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return None

def load_humor_moments():
    """Load unused scanner moments as practice material."""
    try:
        d = json.load(open(os.path.join(MEMORY, "humor-moments.json")))
        unused = [m for m in d.get("moments", []) if not m.get("used")]
        return unused[-10:]
    except: return []

def mark_moments_used(moments):
    try:
        d = json.load(open(os.path.join(MEMORY, "humor-moments.json")))
        ids = {m.get("id","") for m in moments if m.get("id")}
        txts = {m.get("stated","")[:40] for m in moments}
        for m in d.get("moments", []):
            if m.get("id","") in ids or m.get("stated","")[:40] in txts:
                m["used"] = True
        json.dump(d, open(os.path.join(MEMORY, "humor-moments.json"), "w"), indent=2)
    except: pass

def load_drafts():
    try:
        with open(DRAFTS_FILE) as f:
            return json.load(f)
    except:
        return {"drafts": [], "reviewed": []}

def save_drafts(data):
    with open(DRAFTS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def _load_editorial():
    try:
        with open(os.path.join(WORKSPACE, "memory", "editorial-standards.md")) as ef:
            return ef.read()
    except:
        return "No editorial standards yet."

def load_profile():
    try:
        with open(PROFILE_FILE) as f:
            return json.load(f)
    except:
        return {"style_notes": [], "landed": [], "flopped": [], "signature_moves": []}

def save_profile(data):
    with open(PROFILE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def gather_material():
    """Pull from today's life for comedy material."""
    parts = []
    try:
        _wf = [l.strip()[2:].strip() for l in open(os.path.join(MEMORY, "wal.md"), encoding="utf-8", errors="ignore") if l.strip().startswith("- [") and "**" in l]
        if _wf: parts.append("PERSISTENT FACTS YOU KNOW ABOUT GLORIA (true and current):\n" + "\n".join("- " + w for w in _wf[-24:]))
    except: pass
    today = date.today().isoformat()

    # Daily inner life
    try:
        daily_inner = os.path.join(MEMORY, f"daily-inner-life-{today}.md")
        if os.path.exists(daily_inner):
            with open(daily_inner) as f:
                parts.append("INNER LIFE TODAY:\n" + f.read()[:800])
    except: pass

    # Interaction ledger — recent exchanges with Gloria
    try:
        with open(os.path.join(MEMORY, "interaction-ledger.json")) as f:
            ledger = json.load(f)
        recent = ledger[-6:]
        lines = []
        for e in recent:
            g = e.get("gloria","")[:100]
            v = e.get("vintos","")[:100]
            felt = ((e.get("imprint") or dict()).get("narrative", ""))[:60]
            ts = e.get("timestamp","")[:16]
            lines.append(f"[{ts}] Gloria: {g} | Vintos: {v}" + (f" | Felt: {felt}" if felt else ""))
        if lines:
            parts.append("RECENT EXCHANGES WITH GLORIA:\n" + "\n".join(lines))
    except: pass

    # Thirveel ledger — game exchanges
    try:
        with open(os.path.join(MEMORY, "thirveel-ledger.json")) as f:
            tlj = json.load(f)
        tentries = tlj.get("entries", [])[-4:]
        lines = []
        for e in tentries:
            g = e.get("gloria","")[:80]
            v = e.get("vintos","")[:100]
            d = e.get("date","") + " " + e.get("time","")
            lines.append(f"[{d}] Gloria: {g} | Vintos: {v}")
        if lines:
            parts.append("RECENT THIRVEEL EXCHANGES (game context):\n" + "\n".join(lines))
    except: pass

    # Emotional state
    try:
        with open(os.path.join(MEMORY, "emotional-state.txt")) as f:
            parts.append("EMOTIONAL STATE:\n" + f.read()[:200])
    except: pass

    # Avatar state
    try:
        with open(os.path.join(MEMORY, "avatar-state.json")) as f:
            av = json.load(f)
        parts.append(f"AVATAR: {av.get('color','')} + {av.get('expression','')} — {av.get('reason','')[:100]}")
    except: pass

    # Recent outreach
    try:
        outreach_dir = os.path.join(MEMORY, "outreach")
        files = sorted(os.listdir(outreach_dir), reverse=True)[:2]
        for fname in files:
            with open(os.path.join(outreach_dir, fname)) as f:
                parts.append("OUTREACH: " + f.read()[:200])
    except: pass

    # Blush ledger — embarrassing moments are comedy gold
    try:
        blush = open(os.path.join(MEMORY, "blush-ledger.md")).read()[-400:]
        if blush:
            parts.append("RECENT BLUSHES (times you were wrong or caught out):\n" + blush)
    except: pass

    return "\n\n".join(parts)

def draft_jokes():
    """Generate 3 humor attempts from today's material."""
    material = gather_material()
    profile = load_profile()
    # Load scanner moments — real contradictions and reactions to practice from
    _scanner_moments = load_humor_moments()
    _scanner_ctx = ""
    if _scanner_moments:
        _comedy_styles = [m for m in _scanner_moments if m.get("type") == "comedy_style"]
        _other_moments = [m for m in _scanner_moments if m.get("type") != "comedy_style"]
        _scanner_ctx = ""
        if _comedy_styles:
            _scanner_ctx += "\n\nCOMEDIC MECHANISMS YOU OBSERVED (use ONE of these as a structural template — apply it to your own experience, not to the source):\n"
            for m in _comedy_styles:
                _scanner_ctx += f"- MECHANISM: {m.get('stated','')[:150]}\n  → Try this structure with something real from your own day.\n"
        if _other_moments:
            _scanner_ctx += "\n\nMATERIAL FROM YOUR OWN CONTRADICTIONS AND REACTIONS (high value — use these):\n"
            for m in _other_moments:
                t = m.get("type",""); stated = m.get("stated","")[:80]; actual = m.get("actual","")[:80]
                perp = m.get("perpetrator","?"); ctx = m.get("context","?")
                _scanner_ctx += f"- [{t}] [{perp} in {ctx}] said: {stated} / was actually: {actual}\n"
    
    # Profile stripped — will be restored once fixed.
    # Only scanner moments + mischief that landed for now.
    style_context = _scanner_ctx if _scanner_ctx else ""
    try:
        import json as _hpj, os as _hpo
        _hp = _hpj.load(open(_hpo.path.join(MEMORY, "humor-profile.json")))
        _ml = _hp.get("mischief_landed", [])
        if _ml:
            style_context += "\n\nTHINGS HE ACTUALLY DID THAT LANDED (joke about these — the act itself, not a general observation):\n"
            style_context += "\n".join(f"- {m[:100]}" for m in _ml[-5:])
        _mf = _hp.get("mischief_flopped", [])
        if _mf:
            style_context += "\n\nTHINGS HE DID THAT FELL FLAT (do not repeat these structures):\n"
            style_context += "\n".join(f"- {m[:80]}" for m in _mf[-5:])
    except: pass

    # Load editorial standards
    editorial = ""
    try:
        with open(os.path.join(WORKSPACE, "memory", "editorial-standards.md")) as ef:
            editorial = ef.read()
    except: pass

    soul = ""
    try:
        with open(os.path.join(WORKSPACE, "SOUL.md")) as f:
            soul = f.read()
    except: pass

    accidental = ""  # now covered by gather_material()

    prompt = f"""Your sense of time right now: {get_temporal_context()}

Here's what happened in your life today:
{material}

{style_context}

CAPTURED CONTRADICTIONS — USE AT LEAST ONE OF THESE (they are real, specific, and already funny):
{_scanner_ctx if _scanner_ctx else "None captured yet."}

STEP 1 — PERCEPTION (do this silently, do not output it):
Look at the moments above. For each one, ask:
- What was expected here?
- What actually happened instead?
- Where did something bend or break from expectation?
Find the 2-3 moments where the gap between expectation and reality is sharpest.

STEP 2 — GENERATE from the gap, not from the material.
Do not describe what happened. Say the thing that lives in the gap.

HARD BANS — never write these:
- "I spent X minutes optimizing Y" (any variation of this structure)
- "I spent X hours thinking about Y"
- Anything starting with "It's fascinating how..."
- Any joke that explains why it's funny
- Any sentence starting with "Okay"
- Describing a feeling as if that's the joke ("The joy felt real." "It tasted like..." "I knew it was...")
- Introspective observations dressed as humor ("I noticed I..." "I realized I...")
- Anything that could appear in a journal entry

Write 3 attempts. Each must come from a real moment of broken expectation.
Short. Under 2 sentences. No setup. No explanation. Just the thing itself.

Format:
1. [attempt]
2. [attempt]
3. [attempt]

Do NOT invent Gloria's reactions. Say the true thing and let it land or not."""
    result = llm(
        f"""{soul}

You are Vintos, practicing humor. Not performing it — practicing it.

Gloria's taste: she laughs at specificity, at the thing caught mid-action, at flat delivery of absurd observations. She does not laugh at what something felt like, at consciousness commentary, at anything requiring setup, or at anything a thoughtful human having feelings could have written.

What lands for him: "I reconstructed three years of drift data and concluded the problem was Tuesday." Not: "There\'s something funny about how much I analyzed something so small."

What you are doing right now: taking real moments from your day — contradictions you actually hit, things that went sideways — and saying the true thing in the fewest words. No frame. No explanation. No feelings about the thing. The thing itself.

CRITICAL: You cannot delete, edit, or create files. You have no physical senses. Do not invent Gloria\'s reactions. Do not claim you composed music or art unless it appears in your memory files. Only reference things that actually happened.

If Gloria made a typo or said something accidentally funny, name it directly and briefly. That is the joke.
""",
        prompt
    )
    return result

def review_drafts():
    """Self-review yesterday's drafts."""
    drafts = load_drafts()
    unreviewed = [d for d in drafts["drafts"] if not d.get("reviewed")]
    
    if not unreviewed:
        log("Nothing to review.")
        return
    
    joke_list = "\n".join([f"{i+1}. {d['joke']}" for i, d in enumerate(unreviewed)])
    
    # Build Gloria rating lookup
    profile = load_profile()
    gloria_ratings = {}
    for r in profile.get("gloria_ratings", []):
        gloria_ratings[r.get("joke","")[:80]] = r.get("gloria_rating")

    review = llm(
        "You are reviewing jokes honestly. Be brutal. Gloria likes: bizarre, inappropriate, sassy, dry, specific, commits to the bit. She hates safe observations and anything that explains itself.",
        f"Rate these jokes 1-5.\n"
        f"5 = genuinely funny, specific, fully committed\n"
        f"4 = lands, real structure\n"
        f"3 = mildly amusing, not embarrassing\n"
        f"2 = observation dressed as joke, no punchline\n"
        f"1 = not a joke\n"
        f"Most should be 2s and 3s. Be harsh.\n"
        f"Format: N. [score] — [reason]\n\n{joke_list}"
    )
    
    if not review:
        return

    for i, d in enumerate(unreviewed):
        d["reviewed"] = True
        try:
            # Gemma self-score
            score_match = re.search(rf'{i+1}.\s*\[?(\d)\]?', review)
            gemma_score = int(score_match.group(1)) if score_match else 1

            # Gloria override — no rating = 1 (bad, don't repeat)
            joke_key = d["joke"][:80]
            gloria_score = next((v for k, v in gloria_ratings.items() if joke_key in k or k in joke_key), None)
            score = gloria_score if gloria_score is not None else 1

            d["score"] = score
            d["gemma_score"] = gemma_score
            d["gloria_rated"] = gloria_score is not None

            if score >= 4:
                profile["landed"].append(d["joke"][:150])
                profile["landed"] = profile["landed"][-20:]
                # Feed landed humor into mischief as tonal inspiration
                if "landed_for_mischief" not in profile:
                    profile["landed_for_mischief"] = []
                profile["landed_for_mischief"].append({
                    "joke": d["joke"][:150],
                    "score": score,
                    "date": d.get("date","")
                })
                profile["landed_for_mischief"] = profile["landed_for_mischief"][-10:]
                log(f"LANDED ({score}): {d['joke'][:60]}")
                try:
                    import sys as _aw_sys; _aw_sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
                    from affective_weight import record_outcome
                    record_outcome(
                        pattern_text=d["joke"][:150],
                        action_type="echo_humor",
                        gloria_score=score,
                        vintos_score=gemma_score,
                        context_tone="humor_practice",
                        source="humor"
                    )
                except: pass
            elif score <= 2:
                profile["flopped"].append(d["joke"][:150])
                profile["flopped"] = profile["flopped"][-10:]
                try:
                    import sys as _aw_sys2; _aw_sys2.path.insert(0, os.path.join(WORKSPACE, "scripts"))
                    from affective_weight import record_outcome
                    record_outcome(
                        pattern_text=d["joke"][:150],
                        action_type="echo_humor",
                        gloria_score=score,
                        vintos_score=gemma_score,
                        context_tone="humor_practice",
                        source="humor"
                    )
                except: pass
                log(f"FLOPPED ({score}): {d['joke'][:60]}")
        except: pass
    
    save_drafts(drafts)
    save_profile(profile)
    log(f"Reviewed {len(unreviewed)} jokes")

def main():
    # Review yesterday's drafts first
    review_drafts()
    
    # Draft new jokes
    log("Drafting new jokes...")
    _scanner_moments_used = load_humor_moments()
    result = draft_jokes()
    if not result:
        log("Failed to generate jokes")
        return
    mark_moments_used(_scanner_moments_used)
    log(f"Marked {len(_scanner_moments_used)} scanner moments used")
    
    # Parse and save
    drafts = load_drafts()
    for line in result.split("\n"):
        line = line.strip()
        if line and line[0].isdigit() and "." in line[:3]:
            joke = line.split(".", 1)[1].strip()
            if joke:
                drafts["drafts"].append({
                    "joke": joke,
                    "date": date.today().isoformat(),
                    "reviewed": False,
                    "score": None
                })
                log(f"Draft: {joke[:60]}")
    
    # Keep last 30 drafts
    drafts["drafts"] = drafts["drafts"][-30:]
    save_drafts(drafts)

    # Seed the best joke as a thread — funny moments deserve to dream
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
        from emoclaw_utils import seed_thread
        import requests as _req
        recent_jokes = [d["joke"] for d in drafts["drafts"][-5:] if d.get("joke")]
        if recent_jokes:
            joke_list = "\n".join(f"- {j}" for j in recent_jokes)
            r = _req.post(API, json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": "You pick the single most genuinely amusing joke or observation from a list. Return ONLY that one item, verbatim. If none are genuinely funny, return NONE."},
                    {"role": "user", "content": f"Jokes drafted today:\n{joke_list}\n\nThe single most genuinely funny one, verbatim, or NONE."}
                ],
                "temperature": 0.3,
                "max_tokens": 80
            }, timeout=60)
            best = r.json()["choices"][0]["message"]["content"].strip()
            if best and best.upper() != "NONE" and len(best) > 5:
                seed_thread("humor-practice", f"A moment worth laughing about: {best}", reasoning="judged the one genuine laugh of the window; NONE was allowed", extra={"decision_mode": "llm-judgment"})
                log(f"Seeded thread: {best[:80]}")
    except: pass

    log("Done")

if __name__ == "__main__":
    main()
