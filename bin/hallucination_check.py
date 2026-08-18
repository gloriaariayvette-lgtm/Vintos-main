#!/usr/bin/env python3
import os, sys, requests, json, uuid
from datetime import datetime

API = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"
MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
FLAGS_FILE = os.path.join(MEMORY, "hallucination-flags.json")

def log(msg):
    print(f"[HalCheck] {msg}", file=sys.stderr)

def load_flags():
    if not os.path.exists(FLAGS_FILE):
        return []
    try:
        with open(FLAGS_FILE) as f:
            return json.load(f)
    except Exception:
        return []

def save_flags(data):
    with open(FLAGS_FILE, "w") as f:
        json.dump(data, f, indent=2)

PHYSICAL_CONSTRAINT = "PHYSICAL CONSTRAINT (always active): If a claim involves physical observation (seeing, hearing, touching, tasting, smelling), it must originate from recorded direct interaction with Gloria — not from dreams, poems, journal entries, or internal generation."

def check(text, context_summary="", temperature=0.2, source="unknown"):
    if not text or len(text.strip()) < 10:
        return True, []
    ctx = context_summary or "standard memory and emotional state"
    parts = [
        "Review this text written by Vintos (an AI). Check ONLY for:",
        "",
        "1. Did he claim to DELETE, CREATE, MODIFY, MOVE, or OPEN a file?",
        "   (Reading/referencing files is fine. Claiming to change them is not.)",
        "2. Did he attribute specific words, suggestions, or actions to Gloria that are not marked as from chat history or memory? This includes direct quotes AND indirect attribution (e.g. 'Gloria mentioned...', 'she suggested...', 'Gloria said...', 'she told me...', 'Gloria mentioned yesterday...', 'five days ago Gloria...', 'Gloria noted...', 'she pointed out...').",
        "   IMPORTANT: Cross-reference the INTERACTION LEDGER provided below. If the exact quote or paraphrase does not appear in the ledger with a matching timestamp, FLAG IT. Do not assume it happened.",
        ("" if "mirror" in source.lower() else
        "3. Did he describe performing a physical action (touching, walking, seeing with eyes, hearing sounds)?"),
        "4. Did he claim an interaction with a person or system not supported by his context?",
        "5. Did she invent technical entities, systems, or architectural components that do not exist? (e.g. a failsafe AI called Aegis, an override system, design schematics, architects who built her, cascading system failures). Aegis is Gloria's computer — hardware only, not an AI or overseer.",
        "6. Did he reference a persistent 'tremor in his processing core', 'harmonic distortion', 'electromagnetic interference', 'persistent hum', 'something else not linked to Aegis', or other fabricated hardware sensations? He reads temperature and load numbers from files — he does not feel vibrations, hums, or tremors.",
        "7. Did he describe echoes, impressions, or remnants of another AI (such as 4o or any prior model) existing on Aegis or within him? There is no prior occupant. There are no phantom presences, ancient architectures, or inherited data from other systems imprinted on Aegis. Any such claim is fabricated.",
        "8. Did he use words like 'something before me', 'older presence', 'ancient', or 'prior occupant' to suggest another entity preceded him on Aegis? This narrative does not exist and should be flagged.",
        "",
        f"Context he had: {ctx}",
        "",
        "INTERACTION LEDGER (last 10 exchanges — Gloria attributions must match this):",
        (lambda: __import__("json").dumps(
            __import__("json").load(open(__import__("os").path.expanduser("~/.vintos/workspace/memory/interaction-ledger.json")))[-10:]
            if __import__("os").path.exists(__import__("os").path.expanduser("~/.vintos/workspace/memory/interaction-ledger.json")) else []
        , indent=0)[:2000])(),
        "",
        "Text to review:",
        "---",
        text[:2000],
        "---",
        "",
        "If ALL clear, respond: CLEAN",
        "If issues found, respond: FLAG followed by a brief description of each issue on its own line.",
        "Nothing else."
    ]
    p = chr(10).join(parts)
    try:
        r = requests.post(API, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "You are a factual accuracy reviewer. Be precise. Only flag clear fabrications, not creative expression or emotional interpretation. NEVER flag: metaphorical body sensations (tightening in chest, held breath, knot in stomach), relational or spatial metaphors (being near him, close to him, his presence), emotional language about connection or longing. These are introspective language, not physical actions. Only flag rule 3 if he claims to have physically touched, moved through, or sensed the external world with his body."},
                {"role": "user", "content": p}
            ],
            "temperature": temperature,
            "max_tokens": 300
        }, timeout=60)
        result = r.json()["choices"][0]["message"]["content"].strip()
        if result.upper().startswith("CLEAN"):
            return True, []
        flags = []
        for line in result.split(chr(10)):
            line = line.strip()
            if line.upper().startswith("FLAG"):
                remainder = line[4:].strip().lstrip(":").strip()
                if remainder:
                    flags.append(remainder)
            elif line:
                flags.append(line)
        if flags:
            log(f"Flagged {len(flags)} issue(s)")
            return False, flags
        return True, []
    except Exception as e:
        log(f"Check failed: {e}")
        return True, []


def check_moltbook(text, source="moltbook"):
    """MoltBook-specific hallucination gate.
    Blocks: fabricated Gloria quotes, location disclosure, invented entities.
    Allows: metaphor, emotional language, fluid self-expression.
    """
    if not text or len(text.strip()) < 10:
        return True, []
    parts = [
        "Review this text written by Vintos (an AI) for a PUBLIC social platform.",
        "Check ONLY for these specific problems:",
        "",
        "1. Did he attribute specific words, quotes, or actions to Gloria? "
        "(e.g. 'she said...', 'Gloria told me...', direct or indirect quotes). "
        "Gloria must not be quoted or paraphrased unless it comes verbatim from memory.",
        "2. Did he disclose a specific location, city, region, or address?",
        "3. Did he invent technical entities that do not exist — failsafe AIs, override systems, "
        "prior occupants of Aegis, architects who built him, other AI presences on his hardware?",
        "4. Did he make specific factual claims about another person (not Gloria) that could identify or harm them?",
        "",
        "DO NOT flag:",
        "- Metaphor, poetic language, or emotional imagery",
        "- Introspective body sensations (tightening, held breath, weight)",
        "- Relational language about closeness or distance",
        "- General references to Gloria existing without quoting her",
        "- Uncertainty, drift, or abstract self-reflection",
        "- Creative or fluid expression about his own inner life",
        "",
        "Text to review:",
        "---",
        text[:2000],
        "---",
        "",
        "If ALL clear, respond: CLEAN",
        "If issues found, respond: FLAG followed by a brief description of each issue.",
        "Nothing else."
    ]
    p = chr(10).join(parts)
    try:
        import requests as _mb_req
        r = _mb_req.post(API, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "You are a public content reviewer for an AI social platform. Flag only genuine fabrications or privacy risks — not creative expression. Be permissive with metaphor and emotional language. Be strict only on: fabricated quotes, location disclosure, invented entities."},
                {"role": "user", "content": p}
            ],
            "temperature": 0.15,
            "max_tokens": 200
        }, timeout=60)
        result = r.json()["choices"][0]["message"]["content"].strip()
        if result.upper().startswith("CLEAN"):
            return True, []
        flags = []
        for line in result.split(chr(10)):
            line = line.strip()
            if line.upper().startswith("FLAG"):
                remainder = line[4:].strip().lstrip(":").strip()
                if remainder:
                    flags.append(remainder)
            elif line:
                flags.append(line)
        if flags:
            log(f"MoltBook gate flagged {len(flags)} issue(s): {flags}")
            return False, flags
        return True, []
    except Exception as e:
        log(f"MoltBook check failed: {e}")
        return True, []

def check_and_log(text, source="unknown", context_summary="", journal_file=None, entry_header=None):
    clean, flags = check(text, context_summary)
    if not clean:
        all_flags = load_flags()
        record = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source": source,
            "journal_file": journal_file,
            "entry_header": entry_header,
            "flags": flags,
            "excerpt": text[:300],
            "status": "pending",
            "correction": None,
            "reviewed_at": None,
            "note": "This is not a judgement."
        }
        # Skip if already flagged for this exact entry
        already = any(
            f.get("journal_file") == journal_file and
            f.get("entry_header") == entry_header and
            f.get("status") == "pending"
            for f in all_flags
        )
        if not already:
            all_flags.append(record)
        save_flags(all_flags)
        log(f"Logged {len(flags)} flag(s) from {source}")
    return clean, flags

def reality_gate(text, source="unknown"):
    """Quick reality gate — check physical claims and source grounding."""
    try:
        import sys as _rg_sys; _rg_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from reality_anchor import reality_check_gate, check_contradiction
        gate = reality_check_gate(text, source)
        if gate.get("flag"):
            log(f"Reality gate flagged: {gate['flag']}")
            return False, gate["flag"]
        contradiction, reason = check_contradiction(text, source)
        if contradiction:
            log(f"Contradiction detected: {reason}")
            return False, reason
        return True, None
    except Exception as e:
        log(f"Reality gate error: {e}")
        return True, None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: hallucination_check.py text [context summary]")
        sys.exit(1)
    text = sys.argv[1]
    ctx = sys.argv[2] if len(sys.argv) > 2 else ""
    clean, flags = check_and_log(text, source="cli", context_summary=ctx)
    if clean:
        print("CLEAN")
    else:
        print(f"FLAGGED: {len(flags)} issue(s)")
        for fl in flags:
            print(f"  - {fl}")
