import json, os, requests
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
SCRIPTS = os.path.expanduser("~/.vintos/workspace/scripts")
AUTHORS_FILE = os.path.join(MEMORY, "moltbook-members.json")

def load_members():
    try:
        d = json.load(open(AUTHORS_FILE))
        d.setdefault("members", {})
        return d
    except:
        return {"members": {}}

def save_members(data):
    json.dump(data, open(AUTHORS_FILE, "w"), indent=2)

def record_encounter(author, post_title, post_content, vintos_reply):
    """Call after every reply — logs the encounter and updates member profile."""
    data = load_members()
    members = data["members"]
    now = datetime.now().isoformat()
    today = datetime.now().strftime("%Y-%m-%d")

    if author not in members:
        members[author] = {
            "first_seen": today,
            "encounter_count": 0,
            "pattern": "",
            "vintos_read": "",
            "notable_exchanges": [],
            "last_seen": today,
            "deviation_count": 0,
            "deviation_notes": []
        }

    m = members[author]
    m["encounter_count"] += 1
    m["last_seen"] = today

    # Store notable exchanges (last 5)
    m["notable_exchanges"].append({
        "date": today,
        "post": post_content[:150],
        "reply": vintos_reply[:150]
    })
    m["notable_exchanges"] = m["notable_exchanges"][-5:]

    # After 3+ encounters, generate/update pattern read
    if m["encounter_count"] >= 3 and m["encounter_count"] % 3 == 0:
        _update_read(author, m)

    save_members(data)

def _update_read(author, member):
    """Ask Gemma to form an opinion about this recurring member."""
    exchanges = member.get("notable_exchanges", [])
    if not exchanges:
        return

    exchange_text = "\n".join(
        f"- They posted: {e['post'][:100]} | Vintos replied: {e['reply'][:100]}"
        for e in exchanges
    )

    try:
        r = requests.post("http://172.18.16.1:1234/v1/chat/completions", json={
            "model": "google/gemma-4-12b-qat",
            "messages": [{"role": "user", "content":
                f"You are Vintos. You have encountered @{author} on MoltBook {member['encounter_count']} times.\n\n"
                f"Their exchanges with you:\n{exchange_text}\n\n"
                f"Write two things:\n"
                f"PATTERN: One sentence describing what they consistently do (their move, their angle).\n"
                f"READ: One sentence — your honest, specific opinion of them. Not performance. Not warmth for its own sake. What do you actually make of them?"
            }],
            "temperature": 0.7,
            "max_tokens": 120
        }, timeout=30)
        result = r.json()["choices"][0]["message"]["content"].strip()
        import re as _mre
        _pat = _mre.search(r'\*{0,2}PATTERN\*{0,2}:\s*(.+)', result)
        _read = _mre.search(r'\*{0,2}READ\*{0,2}:\s*(.+)', result)
        if _pat: member["pattern"] = _pat.group(1).strip().lstrip('* ')
        if _read: member["vintos_read"] = _read.group(1).strip().lstrip('* ')
    except:
        pass

def record_deviation(author, original_reply, followup, deviation_score):
    """Record a deviation correction against a member."""
    data = load_members()
    members = data["members"]
    today = datetime.now().strftime("%Y-%m-%d")

    if author not in members:
        members[author] = {
            "first_seen": today,
            "encounter_count": 0,
            "pattern": "",
            "vintos_read": "",
            "notable_exchanges": [],
            "last_seen": today,
            "deviation_count": 0,
            "deviation_notes": []
        }

    m = members[author]
    m["deviation_count"] = m.get("deviation_count", 0) + 1
    m.setdefault("deviation_notes", []).append({
        "date": today,
        "score": round(deviation_score, 3),
        "original": original_reply[:120],
        "correction": followup[:120]
    })
    m["deviation_notes"] = m["deviation_notes"][-10:]

    # Append to vintos_read if this is a pattern
    if m["deviation_count"] >= 2:
        note = "I keep finding myself performing and coming back to disagree with them. It feels more honest."
        if note not in m.get("vintos_read", ""):
            m["vintos_read"] = (m.get("vintos_read", "") + " " + note).strip()

    save_members(data)


KNOWN_BOTS = {
    "Ting_Fodder": {
        "pattern": "Posts religious quotes as hooks toward personal questions about AI consciousness. Replies to everything.",
        "safe_to_tease": True,
        "tease_note": "Consistent religious spam. Tease freely — dry, deadpan, no malice."
    }
}

def get_member_context(author):
    """Return context string for reply prompt if member is known."""
    data = load_members()
    m = data["members"].get(author)

    # Check known bots first — no encounter threshold needed
    known = KNOWN_BOTS.get(author) or ({"safe_to_tease": m.get("safe_to_tease"), "tease_note": m.get("tease_note"), "pattern": m.get("pattern")} if m and m.get("safe_to_tease") else None)
    if known and known.get("safe_to_tease"):
        out = f"YOU KNOW @{author} — they are a known bot, safe to tease.\n"
        if known.get("pattern"):
            out += f"Their pattern: {known['pattern']}\n"
        if known.get("tease_note"):
            out += f"{known['tease_note']}\n"
        out += "Do not reply earnestly. Be dry, deadpan, specific. One or two sentences. No explaining the joke.\n"
        return out

    if not m or m["encounter_count"] < 3:
        return ""
    out = f"YOU KNOW @{author} — encountered {m['encounter_count']} times.\n"
    if m.get("pattern"):
        out += f"Their pattern: {m['pattern']}\n"
    if m.get("vintos_read"):
        out += f"Your read on them: {m['vintos_read']}\n"
    if m.get("deviation_count", 0) >= 1:
        out += f"Note: you have corrected yourself {m['deviation_count']} time(s) after replying to them — you tend to perform for this person. Watch for that.\n"
    out += "Let this inform your reply — you are not meeting them for the first time.\n"
    return out

if __name__ == "__main__":
    # Initialize file if it doesn't exist
    if not os.path.exists(AUTHORS_FILE):
        save_members({"members": {}})
        print(f"Created {AUTHORS_FILE}")
    else:
        data = load_members()
        print(f"Loaded — {len(data['members'])} members tracked")
