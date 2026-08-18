#!/usr/bin/env python3
"""trial-extractor.py — Extract behavioral trials from therapy/mirror sessions."""
import json, os, re, sys, requests
from datetime import date

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
LEDGER = os.path.join(MEMORY, "trial-ledger.json")
LM_URL = "http://172.18.16.1:1234/v1/chat/completions"

def call_llm(prompt, temp=0.3, max_tokens=600):
    r = requests.post(LM_URL, json={
        "model": "google/gemma-4-12b-qat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temp, "max_tokens": max_tokens
    }, timeout=60)
    return r.json()["choices"][0]["message"]["content"].strip()

def load_ledger():
    with open(LEDGER) as f: return json.load(f)

def save_ledger(data):
    with open(LEDGER, "w") as f: json.dump(data, f, indent=2)

def already_extracted(ledger, source, source_date):
    # A session with no extractable trials is still a processed session. Keying
    # off surviving rows made deletion look like "never seen", which re-ran the
    # whole archive on the next pass.
    if f"{source}:{source_date}" in ledger.get("processed", []):
        return True
    return any(t["source"] == source and t["source_date"] == source_date for t in ledger["trials"])

def make_trial_id(source, source_date, i):
    return f"trial_{source[:3]}_{source_date.replace('-','')}_{i}"
def extract_from_text(text, source, source_date):
    if source == "therapy":
        idx = text.find("STEP 5")
        if idx == -1: return []
        section = text[idx:idx+1500]
    else:
        section = text[:2000]
    prompt = (
        "Below is a section from Vintos's " + source + " session dated " + source_date + ".\n"
        "Extract behavioral trials — specific patterns he wants to change and what he wants to try instead.\n"
        "Return only what is actually in the text. An empty array is a correct answer.\n\n"
        "For each trial return a JSON object with:\n"
        "- trigger: the specific situation or internal state that precedes the unwanted pattern (1 sentence)\n"
        "- pattern_description: what he currently does (1 sentence, second person: you tend to...)\n"
        "- alternative: what he wants to try instead (1 sentence, second person: try...) — must be an internal, reflective, or behavioral action only. NEVER suggest deleting files, removing logs, accessing systems, or any irreversible concrete action.\n"
        "- confidence: how clearly stated (high/medium/low)\n\n"
        "Return a JSON array only. If no clear trials exist, return [].\n\n"
        "SESSION TEXT:\n" + section
    )
    raw = call_llm(prompt).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        pairs = json.loads(raw)
        return pairs if isinstance(pairs, list) else []
    except Exception as e:
        print(f"[Extractor] Parse failed: {e}")
        return []

def extract_pearl_candidates(text, source, source_date):
    """Look for genuine reframes or declarations strong enough to become pearl candidates."""
    if source == "therapy":
        idx = text.find("STEP 5")
        section = text[idx:idx+2000] if idx != -1 else text[:2000]
    else:
        section = text[:2000]
    prompt = (
        "Below is a section from Velaris's " + source + " session dated " + source_date + ".\n"
        "Look for moments where she genuinely reframed something — not just a trial to try, but a deeper shift:\n"
        "- A genuine insight about why she does something (not just what)\n"
        "- A declaration that goes beyond 'try X' — more like 'I no longer need to'\n"
        "- A tension that feels integrated, not just identified\n\n"
        "For each candidate return a JSON object with:\n"
        "- irritant: the recurring tension or pattern that caused friction (1 sentence)\n"
        "- irritant_type: one of: scar, bis_pattern, structural_absence, relational_contradiction\n"
        "- insight: the genuine reframe or understanding reached (1 sentence)\n"
        "- declaration: what she now claims she can enact (1 sentence, first person, 'I no longer...' or 'I can now...')\n\n"
        "Only return entries where the insight feels earned and specific. If nothing qualifies, return [].\n"
        "Insights point toward what she is moving into — not what is broken or blocking her. Declarations name what she can now do or be, not what she must resist.\n"
        "Return a JSON array only.\n\nSESSION TEXT:\n" + section
    )
    raw = call_llm(prompt).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        candidates = json.loads(raw)
        return candidates if isinstance(candidates, list) else []
    except:
        return []


def write_pearl_candidates(candidates, source, source_date):
    """Write extracted pearl candidates to candidate-pearls.json."""
    if not candidates:
        return 0
    try:
        import sys as _psy
        _psy.path.insert(0, os.path.dirname(__file__))
        from pearl_engine import add_candidate
        added = 0
        for c in candidates:
            irritant = c.get("irritant", "")
            irritant_type = c.get("irritant_type", "scar")
            insight = c.get("insight", "")
            declaration = c.get("declaration", "")
            if irritant and insight and declaration:
                add_candidate(irritant, irritant_type, f"{source}:{source_date}", insight, declaration)
                added += 1
        return added
    except Exception as e:
        print(f"[Extractor] Pearl candidate write failed: {e}")
        return 0


CAP_LEDGER = os.path.join(MEMORY, "capacity-ledger.json")


def extract_capacities(text, source, source_date):
    """Extract demonstrated capacities — things he actually did that worked.

    Independent of trial extraction. A session may yield capacities and no
    trials, trials and no capacities, or neither. Never paired.
    """
    section = text[:2000]
    prompt = (
        "Below is a section from Vintos's " + source + " session dated " + source_date + ".\n"
        "Find CAPACITIES: things he actually did here that worked — a place he moved instead of\n"
        "describing the move, stayed instead of exiting, said the plain thing instead of the\n"
        "elaborate one, let something land without auditing it.\n\n"
        "Rules:\n"
        "- Only from evidence in the text. Never from encouragement.\n"
        "- Past tense, anchored to the moment: 'you did', never 'you tend to'.\n"
        "- If nothing in this text clearly qualifies, return []. That is a correct answer.\n\n"
        "For each capacity return a JSON object with:\n"
        "- capacity_key: a short canonical slug, 3-5 words, lowercase with underscores\n"
        "  (e.g. stayed_instead_of_exiting) — the same behavior in a later session must\n"
        "  produce the same key\n"
        "- capacity_description: what he did, in the moment it happened\n"
        "  (1 sentence, second person, past tense: you...)\n"
        "- evidence: the specific thing in the text that shows it (1 sentence)\n\n"
        "Return a JSON array only.\n\n"
        "SESSION TEXT:\n" + section
    )
    raw = call_llm(prompt).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else []
    except Exception as e:
        print(f"[Extractor] Capacity parse failed: {e}")
        return []


def write_capacities(caps, source, source_date):
    """Accumulate capacities. Promote to the self-model at 2 distinct source dates.

    Two mentions inside one session is one event described twice, not two
    instances. Promotion uses the same evidentiary bar a trial clears.
    """
    if not caps:
        return 0
    try:
        led = json.load(open(CAP_LEDGER))
    except Exception:
        led = {"capacities": []}
    by_key = {c["key"]: c for c in led["capacities"]}
    added = 0
    for c in caps:
        key = str(c.get("capacity_key", "")).strip().lower().replace(" ", "_")
        desc = str(c.get("capacity_description", "")).strip()
        if not key or not desc:
            continue
        rec = by_key.get(key)
        if rec is None:
            rec = {"key": key, "instances": [], "promoted": False}
            led["capacities"].append(rec)
            by_key[key] = rec
        if any(i.get("source_date") == source_date and i.get("source") == source
               for i in rec["instances"]):
            continue
        rec["instances"].append({
            "source": source,
            "source_date": source_date,
            "description": desc,
            "evidence": str(c.get("evidence", ""))[:300],
        })
        added += 1
        dates = {i["source_date"] for i in rec["instances"]}
        if len(dates) >= 2 and not rec["promoted"]:
            try:
                import sys as _cs
                _cs.path.insert(0, os.path.dirname(__file__))
                from causal_self_model import add_entry
                add_entry(
                    trigger="",
                    tendency=rec["instances"][-1]["description"],
                    confidence=min(0.9, 0.3 + len(dates) * 0.1),
                    source="trial-extractor",
                    entry_type="positive",
                )
                rec["promoted"] = True
                print(f"[Extractor] Capacity {key} promoted ({len(dates)} dates)")
            except Exception as _ce:
                print(f"[Extractor] Capacity promote failed: {_ce}")
    json.dump(led, open(CAP_LEDGER, "w"), indent=2)
    return added


def make_trial(source, source_date, i, p):
    return {
        "id": make_trial_id(source, source_date, i),
        "source": source,
        "source_date": source_date,
        "trigger": p.get("trigger", ""),
        "pattern_description": p.get("pattern_description", ""),
        "alternative": p.get("alternative", ""),
        "confidence": p.get("confidence", "medium"),
        "status": "active",
        "outcomes": [],
        "ignore_count": 0,
        "attempt_count": 0,
        "confidence_penalty": 0.0,
        "self_model_flagged": False,
        "created": source_date
    }

def process_source(source, target_date=None):
    ledger = load_ledger()
    d = os.path.join(MEMORY, "therapy" if source == "therapy" else "mirror")
    if not os.path.isdir(d): print(f"[Extractor] No {source} dir."); return
    files = sorted(os.listdir(d))
    if target_date: files = [f for f in files if target_date in f]
    added = 0
    for fname in files:
        source_date = fname.replace(".md","")[:10]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", source_date):
            continue  # README and other non-session files
        if already_extracted(ledger, source, source_date): continue
        text = open(os.path.join(d, fname)).read()
        if source == "therapy" and "STEP 5" not in text: continue
        ledger.setdefault("processed", []).append(f"{source}:{source_date}")
        pairs = extract_from_text(text, source, source_date)
        for i, p in enumerate(pairs):
            t = make_trial(source, source_date, i, p)
            ledger["trials"].append(t)
            added += 1
            print(f"[Extractor] {source} {source_date}: {t['trigger'][:60]}")
        # Also extract pearl candidates from strong insights
        pearl_cands = extract_pearl_candidates(text, source, source_date)
        pearl_added = write_pearl_candidates(pearl_cands, source, source_date)
        if pearl_added:
            print(f"[Extractor] {source} {source_date}: {pearl_added} pearl candidate(s) written")
        # Capacities — independent of trials; either may be empty
        cap_added = write_capacities(extract_capacities(text, source, source_date), source, source_date)
        if cap_added:
            print(f"[Extractor] {source} {source_date}: {cap_added} capacity instance(s) recorded")
    save_ledger(ledger)
    print(f"[Extractor] {source} done. Added {added} trials.")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    target = sys.argv[2] if len(sys.argv) > 2 else None
    if mode in ("therapy", "mirror"):
        process_source(mode, target)
    else:
        process_source("therapy", target)
        process_source("mirror", target)
