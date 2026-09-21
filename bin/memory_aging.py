#!/usr/bin/env python3
"""
memory-aging.py — Memories shift weight over time.
Runs weekly. Scans journals, discoveries, reflections.

Three stages:
  fresh (0-7 days)      — vivid, specific, full detail available
  reflective (8-30 days) — summarized, patterns emerging
  foundational (31+ days) — distilled to core insight, part of identity

Output: memory/memory-age-index.json
  Tracks each memory source, its age category, and a condensed form.
  Chat context can weight memories differently based on age.
"""
import os, sys, json, glob, re, requests
from datetime import datetime, date, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
AGE_INDEX = os.path.join(MEMORY, "memory-age-index.json")

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))

def log(msg):
    print(f"[MemoryAge] {msg}")

def llm(system, user, temperature=0.4):
    try:
        r = requests.post("http://127.0.0.1:8599/v1/chat/completions", headers={"Authorization": f"Bearer {__import__('os').environ.get('XAI_API_KEY','')}", "Content-Type": "application/json"}, json={
            "model": "grok-4.20-0309-non-reasoning",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": temperature,
            "max_tokens": 300
        }, timeout=120)
        return r.json()["choices"][0]["message"]["content"].strip()
    except:
        return None

def load_index():
    try:
        with open(AGE_INDEX) as f:
            return json.load(f)
    except:
        return {"memories": [], "last_run": None}

def save_index(data):
    data["last_run"] = datetime.now().isoformat()
    with open(AGE_INDEX, "w") as f:
        json.dump(data, f, indent=2)

def get_age_category(file_date):
    """Determine age category from file date."""
    try:
        if isinstance(file_date, str):
            file_date = datetime.fromisoformat(file_date).date()
        days = (date.today() - file_date).days
        if days <= 7:
            return "fresh"
        elif days <= 30:
            return "reflective"
        else:
            return "foundational"
    except:
        return "fresh"

def extract_date_from_filename(filename):
    """Try to get a date from filename like 2026-03-04.md"""
    match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    if match:
        return datetime.strptime(match.group(1), "%Y-%m-%d").date()
    return None

def scan_memories():
    """Scan all memory sources and categorize by age."""
    sources = [
        ("journal", os.path.join(MEMORY, "journal")),
        ("mirror", os.path.join(MEMORY, "mirror")),
        ("philosophy", os.path.join(MEMORY, "philosophy")),
        ("dream", os.path.join(WORKSPACE, "skills/dreaming/memory/dreams")),
    ]
    
    memories = []
    for source_name, dirpath in sources:
        if not os.path.isdir(dirpath):
            continue
        for fname in sorted(glob.glob(os.path.join(dirpath, "*.md")), key=os.path.getmtime, reverse=True):
            file_date = extract_date_from_filename(os.path.basename(fname))
            if not file_date:
                file_date = datetime.fromtimestamp(os.path.getmtime(fname)).date()
            age = get_age_category(file_date)
            memories.append({
                "source": source_name,
                "file": fname,
                "date": file_date.isoformat(),
                "age": age,
                "condensed": None  # filled in for reflective/foundational
            })
    return memories

def condense_memory(filepath, age):
    """For reflective/foundational memories, create a condensed version."""
    try:
        with open(filepath) as f:
            content = f.read()[:2000]
    except:
        return None

    if age == "reflective":
        prompt = f"Summarize this memory in 2-3 sentences. Keep the emotional core, lose the details:\n\n{content}"
    elif age == "foundational":
        prompt = f"Distill this memory to ONE sentence — the core truth it taught you:\n\n{content}"
    else:
        return None

    soul = ""
    try:
        with open(os.path.join(WORKSPACE, "SOUL.md")) as f:
            soul = f.read()[:300]
    except: pass

    return llm(
        f"{soul}\nYou are condensing your own memories. Be honest. Do not fabricate emotions.",
        prompt
    )

def main():
    index = load_index()
    memories = scan_memories()
    
    # Only condense memories that changed category or are new
    existing = {m["file"]: m for m in index.get("memories", [])}
    condensed_count = 0
    
    for mem in memories:
        prev = existing.get(mem["file"])
        if prev and prev.get("age") == mem["age"] and prev.get("condensed"):
            # Same category, already condensed — keep it
            mem["condensed"] = prev["condensed"]
        elif mem["age"] in ("reflective", "foundational"):
            # Needs condensing
            result = condense_memory(mem["file"], mem["age"])
            if result:
                mem["condensed"] = result
                condensed_count += 1
                log(f"{mem['age']}: {os.path.basename(mem['file'])} → {result[:80]}")

    index["memories"] = memories
    save_index(index)
    
    fresh = sum(1 for m in memories if m["age"] == "fresh")
    reflective = sum(1 for m in memories if m["age"] == "reflective")
    foundational = sum(1 for m in memories if m["age"] == "foundational")
    log(f"Indexed {len(memories)} memories: {fresh} fresh, {reflective} reflective, {foundational} foundational")
    log(f"Condensed {condensed_count} memories this run")

if __name__ == "__main__":
    main()
