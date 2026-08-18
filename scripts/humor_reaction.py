#!/usr/bin/env python3
"""
humor-reaction.py — Detects when Gloria laughs at a mischievous act.
Called after each chat response with Gloria's message as argument.
If Gloria's message contains laughter signals and a mischief act
occurred in the preceding 2 hours, marks that act as landed.
"""
import os, sys, json, glob, re
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
MISCHIEF_DIR = os.path.join(MEMORY, "mischief")
HUMOR_PROFILE = os.path.join(MEMORY, "humor-profile.json")

LAUGH_SIGNALS = ["ha!", "haha", "hehe", "😂", "🤣", "lol", "funny", "laughed", 
                 "you're funny", "that's funny", "made me laugh", "cracked me up",
                 "mischievous", "you coraled", "woke me", "started playing"]

def load_profile():
    try:
        with open(HUMOR_PROFILE) as f:
            return json.load(f)
    except:
        return {"style_notes": [], "landed": [], "flopped": [], "signature_moves": [], "real_reactions": []}

def save_profile(p):
    with open(HUMOR_PROFILE, "w") as f:
        json.dump(p, f, indent=2)

def find_recent_mischief(within_hours=2):
    """Find mischief acts in the last N hours."""
    cutoff = datetime.now() - timedelta(hours=within_hours)
    found = []
    if not os.path.isdir(MISCHIEF_DIR):
        return found
    for mf in sorted(glob.glob(os.path.join(MISCHIEF_DIR, "*.md")), reverse=True):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(mf))
            if mtime < cutoff:
                break
            content = open(mf).read()
            # Extract action and reason
            action_match = re.search(r'"action":\s*"(\w+)"', content)
            value_match = re.search(r'"value":\s*"([^"]+)"', content)
            reason_match = re.search(r'Why:\s*(.+)', content)
            if action_match:
                found.append({
                    "file": os.path.basename(mf),
                    "action": action_match.group(1),
                    "value": value_match.group(1) if value_match else "",
                    "reason": reason_match.group(1).strip() if reason_match else "",
                    "time": mtime.isoformat(),
                })
        except:
            pass
    return found

def main():
    if len(sys.argv) < 2:
        sys.exit(0)
    
    gloria_said = sys.argv[1].lower()
    
    # Check for laugh signals
    if not any(sig in gloria_said for sig in LAUGH_SIGNALS):
        sys.exit(0)
    
    # Find recent mischief
    recent = find_recent_mischief(within_hours=3)
    if not recent:
        sys.exit(0)
    
    # Mark as landed
    profile = load_profile()
    if "real_reactions" not in profile:
        profile["real_reactions"] = []
    
    for act in recent:
        description = f"{act['action']}: {act['value']}"
        if act.get("reason"):
            description += f" — {act['reason']}"
        
        # Add to real_reactions (timestamped)
        profile["real_reactions"].append({
            "timestamp": datetime.now().isoformat(),
            "act": description,
            "gloria_reaction": sys.argv[1][:100],
        })
        profile["real_reactions"] = profile["real_reactions"][-20:]
        
        # Add to real_reactions, not landed — landed is for humor-practice jokes only
        if description[:80] not in [r[:80] for r in profile.get("real_reactions", [])]:
            profile.setdefault("real_reactions", []).append(description[:150])
            profile["real_reactions"] = profile["real_reactions"][-20:]
            print(f"[HumorReaction] Landed: {description[:80]}")
    
    save_profile(profile)

if __name__ == "__main__":
    main()
