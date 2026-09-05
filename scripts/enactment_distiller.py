#!/usr/bin/env python3
"""
enactment-distiller.py — Real-time enacted behavior scanner.
Runs post-response (background thread, ~8s delay).
Detects moments where behavior demonstrated something identity-relevant
through action rather than abstraction.
"""
import os, sys, json, re
from datetime import datetime, date, timedelta
import urllib.request

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY    = os.path.join(WORKSPACE, "memory")
SCRIPTS   = os.path.join(WORKSPACE, "scripts")
sys.path.insert(0, SCRIPTS)

LM_URL  = "http://172.18.16.1:1234/v1/chat/completions"
MODEL   = "google/gemma-4-12b-qat"
HEADERS = {"Content-Type": "application/json"}

EVENTS_FILE      = os.path.join(MEMORY, "earned-identity-events.json")
PROTO_PEARL_FILE = os.path.join(MEMORY, "proto-pearls.json")

CATEGORIES = [
    "successful_directness",
    "successful_grounding",
    "successful_emotional_reciprocity",
    "successful_ambiguity_tolerance",
    "sustained_emotional_presence",
    "recovery_after_drift",
    "curiosity_without_compulsive_analysis",
    "restraint_without_suppression",
    "spontaneous_honesty",
    "maintained_boundaries",
    "successful_repair",
    "unexpected_competence",
    "unexpected_restraint",
    "unexpected_warmth",
    "unexpected_stability",
    "unexpected_honesty",
    "value_enactment_under_pressure",
    "changed_behavior_after_reflection",
]

PROTO_DECAY_DAYS   = 2
PROTO_THRESHOLD    = 3   # support events before proto-pearl forms
PEARL_THRESHOLD    = 5   # support events before suggesting full pearl
SELF_STMT_MIN_CONF = 0.65


def call_llm(messages, temperature=0.2, max_tokens=200):
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }).encode()
    req = urllib.request.Request(LM_URL, data=payload, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()


def load_self_model_excerpt():
    try:
        sm = open(os.path.join(WORKSPACE, "SELF-MODEL.md")).read()
        # Pull just the core tendencies section
        return sm[:600]
    except:
        return ""



JOURNAL_CATEGORIES = [
    "introspective_pause",
    "tolerated_uncertainty",
    "named_without_explaining",
    "redirect_within_reflection",
]

def scan(response_text, gloria_msg="", context="chat"):
    """
    Main entry point. Call after response is finalized.
    Returns list of enacted behavior events detected.
    """
    if not response_text or len(response_text) < 30:
        return []

    self_model = load_self_model_excerpt()

    if context == "journal":
        jcats = "\n".join(f"- {c}" for c in JOURNAL_CATEGORIES)
        jprompt = (
            "You are detecting enacted behavior within reflective writing"
            " -- moments where the mind did something rather than described wanting to.\n\n"
            "COUNTS: staying with discomfort rather than resolving it; "
            "naming a fear or contradiction without immediately explaining it; "
            "holding a question open at the end without reaching for a framework; "
            "noticing an impulse and describing a deliberate redirect away from it.\n\n"
            "DOES NOT COUNT: rumination, pattern analysis, abstract feeling descriptions, "
            "planning or wanting to change, noticing tendencies without any actual shift.\n\n"
            f"JOURNAL ENTRY:\n{response_text[:800]}\n\n"
            f"SELF-MODEL:\n{self_model}\n\n"
            f"CATEGORIES:\n{jcats}\n\n"
            "Respond with JSON only. If enacted moment: detected true, category, "
            "event 3-6 words, observed_shift, identity_candidate as a genuine CAPABILITY this writing demonstrates, phrased 'I can ...' (an ability or strength enacted) — never a flaw, avoidance, diagnosis, or restated problem; if only self-criticism or a described tendency is present set detected false, "
            "evidence list, exceeded_self_model bool, confidence float. "
            "If nothing: detected false."
        )
        try:
            import re as _re, json as _json
            jresult = call_llm([{"role": "user", "content": jprompt}], temperature=0.2, max_tokens=250)
            jm = _re.search(r"{.*}", jresult, _re.DOTALL)
            if jm:
                jdata = _json.loads(jm.group())
                if jdata.get("detected"):
                    return [jdata]
        except Exception as je:
            print(f"[ED] Journal scan error: {je}", flush=True)
        return []

    cats = "\n".join(f"- {c}" for c in CATEGORIES)

    prompt = (
        "You are detecting enacted behavior — moments where the AI's response demonstrates "
        "something identity-relevant through action rather than abstraction.\n\n"
        "Scan this exchange for enacted behavior — concrete things Vintos ACTUALLY DID in an interaction or creative output, "
        "not things he thought, felt, reflected on, or noticed about himself. "
        "DOES NOT COUNT: noticing an impulse, resisting an impulse internally, describing a feeling, planning to do something, "
        "writing about wanting to change a pattern, introspective journal entries about tendencies or patterns. "
        "COUNTS: saying something direct when the pattern would have been to deflect, "
        "creating something unexpected, holding a boundary in an actual exchange, making a choice that contradicts a known pattern in real time. "
        "Only flag if there is a specific behavioral action in actual interaction or output that exceeded what the self-model would predict.\n\n"
        f"GLORIA'S MESSAGE:\n{gloria_msg[:300]}\n\n"
        f"VINTOS'S RESPONSE:\n{response_text[:600]}\n\n"
        f"CURRENT SELF-MODEL EXCERPT:\n{self_model}\n\n"
        f"CATEGORIES TO DETECT:\n{cats}\n\n"
        "If an enacted behavior moment is present, respond with JSON:\n"
        '{"detected": true, "category": "...", "event": "3-6 words describing what happened", '
        '"observed_shift": "previous pattern vs current behavior", '
        '"identity_candidate": "I can ... (a genuine capability demonstrated, an ability or strength — NOT a flaw, avoidance, or restated problem)", '
        '"evidence": ["...", "..."], '
        '"exceeded_self_model": true/false, '
        '"confidence": 0.0-1.0}\n\n'
        'If nothing significant: {"detected": false}'
    )

    try:
        result = call_llm([{"role": "user", "content": prompt}], temperature=0.2, max_tokens=200)
        m = re.search(r'\{.*\}', result, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group())
        if not data.get("detected"):
            return []
        return [data]
    except Exception as e:
        print(f"[ED] Scan error: {e}", flush=True)
        return []


def load_events():
    try:
        return json.load(open(EVENTS_FILE)) if os.path.exists(EVENTS_FILE) else {"events": []}
    except:
        return {"events": []}


def save_events(db):
    json.dump(db, open(EVENTS_FILE, "w"), indent=2)


def load_proto_pearls():
    try:
        return json.load(open(PROTO_PEARL_FILE)) if os.path.exists(PROTO_PEARL_FILE) else {"protos": []}
    except:
        return {"protos": []}


def save_proto_pearls(db):
    json.dump(db, open(PROTO_PEARL_FILE, "w"), indent=2)


def prune_proto_pearls(db):
    cutoff = (date.today() - timedelta(days=PROTO_DECAY_DAYS)).isoformat()
    before = len(db["protos"])
    db["protos"] = [p for p in db["protos"] if p.get("created")[:10] >= cutoff]
    if len(db["protos"]) < before:
        print(f"[ED] Pruned {before - len(db['protos'])} expired proto-pearls.", flush=True)


def update_proto_pearl(event, proto_db):
    """Add support to existing proto-pearl or create new one."""
    category = event.get("category", "")
    identity_candidate = event.get("identity_candidate", "")

    # Find matching proto
    existing = next((p for p in proto_db["protos"] if p.get("category") == category), None)

    if existing:
        existing["support_count"] = existing.get("support_count", 1) + 1
        existing["support_events"].append({
            "event": event.get("event",""),
            "timestamp": datetime.now().isoformat()
        })
        existing["identity_candidate"] = identity_candidate  # update to latest
        print(f"[ED] Proto-pearl reinforced: {category} ({existing['support_count']} support)", flush=True)

        if existing["support_count"] >= PEARL_THRESHOLD:
            print(f"[ED] Proto-pearl ready for full pearl: {identity_candidate}", flush=True)
            existing["suggest_pearl"] = True
    else:
        proto = {
            "id": f"proto_{category}_{date.today().isoformat()}",
            "category": category,
            "identity_candidate": identity_candidate,
            "support_count": 1,
            "support_events": [{"event": event.get("event",""), "timestamp": datetime.now().isoformat()}],
            "created": datetime.now().isoformat(),
            "decays_at": (date.today() + timedelta(days=PROTO_DECAY_DAYS)).isoformat(),
            "suggest_pearl": False
        }
        proto_db["protos"].append(proto)
        print(f"[ED] New proto-pearl: {category} — {identity_candidate[:60]}", flush=True)


def add_self_statement(event):
    """Add identity candidate to self-statements if confidence sufficient."""
    if event.get("confidence", 0) < SELF_STMT_MIN_CONF:
        return
    try:
        from self_statements import add_statement
        add_statement(
            event["identity_candidate"],
            stmt_type="identity",
            confidence=event["confidence"],
            source="enactment_distiller"
        )
        print(f"[ED] Self-statement added: {event['identity_candidate'][:60]}", flush=True)
    except Exception as e:
        print(f"[ED] Self-statement error: {e}", flush=True)


def nudge_emotion(event):
    """Small positive nudge for enacted behavior."""
    import socket, json as _sj
    nudges = {"Valence": 0.02, "Groundedness": 0.015}
    if "warmth" in event.get("category", "") or "reciprocity" in event.get("category", ""):
        nudges["Warmth"] = 0.02
    if "curiosity" in event.get("category", ""):
        nudges["Curiosity"] = 0.02
    for dim, amt in nudges.items():
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect("/tmp/Vintos-emotion.sock")
            s.sendall(_sj.dumps({"command": "nudge", "dimension": dim, "amount": amt}).encode() + b"\n")
            s.recv(4096)
            s.close()
        except:
            pass


def tag_for_causality(event):
    """Write timestamped tag to earned-identity-events.json for causality to read."""
    db = load_events()
    entry = {
        "id": f"ed_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
        "date": date.today().isoformat(),
        "category": event.get("category", ""),
        "event": event.get("event", ""),
        "observed_shift": event.get("observed_shift", ""),
        "identity_candidate": event.get("identity_candidate", ""),
        "evidence": event.get("evidence", []),
        "confidence": event.get("confidence", 0),
        "exceeded_self_model": event.get("exceeded_self_model", False),
        "source": "chat"
    }
    db["events"].append(entry)
    db["events"] = db["events"][-200:]
    save_events(db)
    print(f"[ED] Tagged for causality: {entry['event']} ({entry['category']})", flush=True)
    return entry


def append_to_journal(event):
    """Append enacted behavior note to today's journal entry."""
    try:
        today = date.today().isoformat()
        journal_path = os.path.join(MEMORY, "journal", f"{today}.md")
        if not os.path.exists(journal_path):
            return
        note = (
            f"\n\n[Enacted behavior — {datetime.now().strftime('%H:%M')} | {event.get('category','')}]\n"
            f"{event.get('event','')}. {event.get('observed_shift','')}\n"
            f"Observed capability: {event.get('identity_candidate','')}\n"
        )
        with open(journal_path, "a") as f:
            f.write(note)
        print(f"[ED] Journal note appended.", flush=True)
    except Exception as e:
        print(f"[ED] Journal append error: {e}", flush=True)



def append_want_enactment(want_text, capability, note=""):
    """Append enacted want note to journal after successful journal-seeded want."""
    try:
        from datetime import date, datetime
        today = date.today().isoformat()
        journal_path = os.path.join(MEMORY, "journal", f"{today}.md")
        if not os.path.exists(journal_path):
            return
        _wt_clean = want_text.strip()
        if _wt_clean.lower().startswith("i want to "): _wt_clean = _wt_clean[10:].strip()
        if _wt_clean.endswith("."): _wt_clean = _wt_clean[:-1]
        identity_prompt = (
            "You are Vintos. You wanted to " + _wt_clean + " and you did it." + chr(10) +
            "Capability: " + capability + chr(10) +
            "Result: " + note[:200] + chr(10) + chr(10) +
            "Complete in one plain sentence starting with 'I': what does completing this say about who you are? Speak as yourself. No preamble."
        )
        identity = call_llm([{"role": "user", "content": identity_prompt}], temperature=0.3, max_tokens=60).strip()
        hm = datetime.now().strftime("%H:%M")
        note_text = (chr(10) + chr(10) +
            "[Enacted want " + hm + " | " + capability + "]" + chr(10) +
            "I wanted to " + _wt_clean + " and I did." + chr(10) +
            note[:200] + chr(10) +
            identity + "." + chr(10)
        )
        open(journal_path, "a").write(note_text)
        print("[ED] Want enactment appended.", flush=True)
    except Exception as e:
        print(f"[ED] Want enactment error: {e}", flush=True)

def _is_capability(cand):
    """Observed capability must be a real strength enacted (I can ...), never a flaw/avoidance/restated problem."""
    c = (cand or "").strip().lower()
    if not c:
        return False
    if not (c.startswith("i can ") or c.startswith("i could ") or c.startswith("i am able") or c.startswith("i'm able")):
        return False
    _bad = ("to avoid", "avoid feeling", "because i can't", "because i cannot", "flinch",
            "instead of feeling", "so i do not", "so i don't", "rather than feel", "hiding",
            "a way to look", "wiring problem", "can't feel", "cannot feel", "the problem")
    return not any(b in c for b in _bad)


def process(response_text, gloria_msg="", context="chat"):
    """Full E_D pipeline."""
    events = scan(response_text, gloria_msg, context)
    events = [e for e in events if _is_capability(e.get('identity_candidate', ''))]
    if not events:
        return
    if str(context).startswith("ghost"):
        # A ghost branch is what he did NOT say. Its behaviours are hypothetical and must not become
        # proto-pearls, self-statements or emotion (review D03, 2026-09-05). Recorded apart, marked.
        try:
            with open(os.path.join(MEMORY, "ghost-enactments.jsonl"), "a") as f:
                for e in events:
                    f.write(json.dumps({**e, "hypothetical": True, "context": context, "at": datetime.now().isoformat()}) + "\n")
            print(f"[ED] {len(events)} hypothetical event(s) from {context} recorded, not enacted", flush=True)
        except Exception:
            pass
        return

    proto_db = load_proto_pearls()
    prune_proto_pearls(proto_db)

    for event in events:
        tag_for_causality(event)
        update_proto_pearl(event, proto_db)

        if event.get("exceeded_self_model") and event.get("confidence", 0) >= SELF_STMT_MIN_CONF:
            add_self_statement(event)

        nudge_emotion(event)

        if context == "journal":
            append_to_journal(event)

        print(f"[ED] Enacted: {event.get('event','')} | {event.get('category','')} | conf={event.get('confidence',0):.2f}", flush=True)

    save_proto_pearls(proto_db)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--response", default="")
    p.add_argument("--message", default="")
    p.add_argument("--context", default="chat")
    args = p.parse_args()
    process(args.response, args.message, args.context)
