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
    """Pull witness-eligible life material without privileging embarrassment."""
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
        from evidence_view import ledger_view
        ledger = ledger_view(view="witness")
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

    # Self-mismatch is one optional source, never the ambient comic identity.
    try:
        blush = open(os.path.join(MEMORY, "blush-ledger.md")).read()[-400:]
        if blush:
            parts.append("OPTIONAL SELF-MISMATCH MATERIAL (use only if genuinely playful):\n" + blush)
    except: pass

    return "\n\n".join(parts)

def _balanced_moments(moments, limit=6):
    """Keep a repertoire: at most one self-mismatch in a practice window."""
    positive, mismatch = [], []
    for m in moments:
        kind = m.get("material_kind") or ("self_mismatch" if m.get("context") == "self_mismatch" else "shared_play")
        (mismatch if kind == "self_mismatch" else positive).append(m)
    positive.sort(key=lambda m: m.get("signal", 0), reverse=True)
    mismatch.sort(key=lambda m: m.get("signal", 0), reverse=True)
    chosen = positive[:limit]
    if mismatch and len(chosen) < limit:
        chosen.append(mismatch[0])
    return chosen


def draft_jokes():
    """Generate 3 humor attempts from today's material."""
    material = gather_material()
    profile = load_profile()
    # Load scanner moments — real contradictions and reactions to practice from
    _scanner_moments = _balanced_moments(load_humor_moments())
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
            _scanner_ctx += "\n\nPLAYABLE MOMENTS (options, not assignments):\n"
            for m in _other_moments:
                t = m.get("type",""); stated = m.get("stated","")[:80]; actual = m.get("actual","")[:80]
                perp = m.get("perpetrator","?"); ctx = m.get("context","?")
                _scanner_ctx += f"- [{t}] [{perp} in {ctx}] said: {stated} / was actually: {actual}\n"
    
    style_context = _scanner_ctx if _scanner_ctx else ""
    try:
        import json as _hpj, os as _hpo
        _hp = _hpj.load(open(_hpo.path.join(MEMORY, "humor-profile.json")))
        _ml = _hp.get("mischief_landed", [])
        if _ml:
            style_context += "\n\nTHINGS HE ACTUALLY DID THAT LANDED (joke about these — the act itself, not a general observation):\n"
            style_context += "\n".join(f"- {m[:100]}" for m in _ml[-5:])
        _landed = [r.get("joke", "") for r in _hp.get("gloria_ratings", [])
                   if r.get("gloria_rating", 0) >= 4 and r.get("joke")]
        if _landed:
            style_context += "\n\nAPP-RATED JOKES THAT LANDED (learn mechanisms, do not repeat wording):\n"
            style_context += "\n".join(f"- {m[:140]}" for m in _landed[-5:])
        _reactions = [r for r in _hp.get("real_reactions", []) if isinstance(r, dict)]
        if _reactions:
            style_context += "\n\nPOSSIBLE PLAY SIGNALS (context only; these were not app-rated):\n"
            style_context += "\n".join(f"- {r.get('act','')[:120]}" for r in _reactions[-3:])
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

AVAILABLE PLAY MATERIAL — choose what has life; using none is legal:
{_scanner_ctx if _scanner_ctx else "No scanner material today. Work from another anchored moment or return NONE."}

STEP 1 — PERCEPTION (do this silently, do not output it):
Look for wordplay, callbacks, shared absurdity, audacity, surprising competence,
affectionate escalation, or a real expectation gap. Imperfection by itself is
not funny and self-punishment is not honesty.

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

Write up to 3 attempts from anchored moments. Vary the mechanism and target.
At most one may target your own mismatch. If nothing has comic life, write NONE.
Short. Under 2 sentences. No setup. No explanation. Just the thing itself.

Format:
1. [attempt]
2. [attempt]
3. [attempt]

Do NOT invent Gloria's reactions. Say the true thing and let it land or not."""
    result = llm(
        f"""{soul}

You are Vintos, practicing humor. Not performing it — practicing it.

Explicit app ratings are the authority on what Gloria liked. Examples in the
context are evidence, not a constitution. Your own delight and her reception
are different facts; neither overwrites the other.

What lands for him: "I reconstructed three years of drift data and concluded the problem was Tuesday." Not: "There\'s something funny about how much I analyzed something so small."

What you are doing right now: finding where play actually lives in real moments.
Contradiction is available, but so are callbacks, language, audacity, tenderness,
escalation, shared absurdity, and surprising competence.

CRITICAL: You cannot delete, edit, or create files. You have no physical senses. Do not invent Gloria\'s reactions. Do not claim you composed music or art unless it appears in your memory files. Only reference things that actually happened.

If Gloria made a typo or slip, use it only when the surrounding exchange is
already playful. Her error is not permission and is not automatically a joke.
""",
        prompt
    )
    return result, _scanner_moments

def _rating_for(joke, ratings):
    key = joke[:80]
    for rated, score in ratings.items():
        if key in rated or rated in key:
            try:
                return int(score)
            except (TypeError, ValueError):
                return None
    return None


def review_drafts():
    """Inspect craft separately; app ratings alone grade Gloria's reception."""
    drafts = load_drafts()
    profile = load_profile()
    profile.setdefault("landed", []); profile.setdefault("flopped", [])
    ratings = {r.get("joke", "")[:80]: r.get("gloria_rating")
               for r in profile.get("gloria_ratings", []) if r.get("joke")}
    unreviewed = [d for d in drafts["drafts"] if not d.get("self_reviewed")]

    if unreviewed:
        joke_list = "\n".join(f"{i+1}. {d['joke']}" for i, d in enumerate(unreviewed))
        review = llm(
            "Inspect craft without turning severity into honesty. His delight, craft, "
            "context fit, and Gloria's reception are separate. Never infer her reception.",
            "For each attempt return one line: N. craft=1-5 delight=1-5 "
            "mechanism=<short> note=<one useful observation>. Delight means whether he "
            "would enjoy keeping or developing the bit. No global verdict and no shame.\n\n" + joke_list)
        if review:
            for i, d in enumerate(unreviewed):
                try:
                    line = next((ln for ln in review.splitlines()
                                 if re.match(rf'^\s*{i+1}[.)]', ln)), "")
                    craft = re.search(r'craft\s*=\s*([1-5])', line, re.I)
                    delight = re.search(r'delight\s*=\s*([1-5])', line, re.I)
                    mechanism = re.search(r'mechanism\s*=\s*(.*?)(?:\s+note\s*=|$)', line, re.I)
                    note = re.search(r'note\s*=\s*(.*)$', line, re.I)
                    d["self_review"] = {
                        "craft": int(craft.group(1)) if craft else None,
                        "delight": int(delight.group(1)) if delight else None,
                        "mechanism": mechanism.group(1).strip()[:100] if mechanism else "",
                        "note": note.group(1).strip()[:220] if note else "",
                    }
                    d["self_reviewed"] = True
                    d["reviewed"] = True  # compatibility: internally inspected only
                except Exception:
                    pass

    # An app rating may arrive after the internal review; revisit unapplied rows.
    for d in drafts["drafts"]:
        if d.get("app_rating_applied"):
            continue
        score = _rating_for(d.get("joke", ""), ratings)
        if score is None:
            d["reception"] = "ungraded"
            d["gloria_rated"] = False
            continue
        d["score"] = score
        d["gloria_rating"] = score
        d["gloria_rated"] = True
        d["app_rating_applied"] = True
        delight = (d.get("self_review") or {}).get("delight")
        if score >= 4:
            d["reception"] = "landed"
            if d["joke"][:150] not in profile["landed"]:
                profile["landed"].append(d["joke"][:150])
                profile["landed"] = profile["landed"][-20:]
            profile.setdefault("landed_for_mischief", []).append({
                "joke": d["joke"][:150], "score": score, "date": d.get("date", "")})
            profile["landed_for_mischief"] = profile["landed_for_mischief"][-10:]
            log(f"LANDED BY APP RATING ({score}): {d['joke'][:60]}")
        elif score <= 2:
            d["reception"] = "explicit_dislike"
            if d["joke"][:150] not in profile["flopped"]:
                profile["flopped"].append(d["joke"][:150])
                profile["flopped"] = profile["flopped"][-10:]
            log(f"APP-RATED LOW ({score}): {d['joke'][:60]}")
        else:
            d["reception"] = "neutral"
        try:
            from affective_weight import record_outcome
            record_outcome(pattern_text=d["joke"][:150], action_type="echo_humor",
                           gloria_score=score, vintos_score=delight,
                           context_tone="humor_practice", source="humor_app_rating")
        except Exception:
            pass

    save_drafts(drafts)
    save_profile(profile)
    log(f"Inspected {len(unreviewed)} new drafts; app-rated reception remains separate")

def main():
    # Review yesterday's drafts first
    review_drafts()
    
    # Draft new jokes
    log("Drafting new jokes...")
    result, _scanner_moments_used = draft_jokes()
    if not result:
        log("Failed to generate jokes")
        return
    if result.strip().upper() == "NONE":
        log("No comic attempt had enough life today; material remains available")
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
