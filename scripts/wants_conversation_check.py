#!/usr/bin/env python3
"""
wants-conversation-check.py — Check if today's conversation fulfilled any wants.
Runs nightly after conversation-review. Reads today's chat and compares
against unfulfilled wants. If they talked about it, it's fulfilled.
"""
import os, sys, json, re, requests
from datetime import datetime, date

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
LEDGER_FILE = os.path.join(MEMORY, "interaction-ledger.json")
API = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
from emoclaw_utils import get_unfulfilled_wants, fulfill_want

def log(msg):
    print(f"[WantCheck] {msg}")

def load_todays_chat():
    try:
        with open(CHAT_FILE) as f:
            msgs = json.load(f)
        today = date.today().isoformat()
        return [m for m in msgs if m.get("timestamp", "").startswith(today)]
    except:
        return []

def load_imprint_index():
    try:
        ledger = json.load(open(os.path.join(MEMORY, "interaction-ledger.json")))
        return ledger[-10:]
    except: pass
    return []

def find_felt_sense(gloria_msg, imprint_index):
    """Find imprint narrative for a given Gloria message."""
    snippet = gloria_msg[:60]
    for imp in reversed(imprint_index):
        if snippet in imp.get("gloria_said", ""):
            return imp.get("narrative", "")
    return ""

def main():
    wants = get_unfulfilled_wants()
    if not wants:
        log("No unfulfilled wants.")
        return

    messages = load_todays_chat()
    if len(messages) < 2:
        log("Not enough chat to check against.")
        return

    # Build transcript with felt sense
    imprint_index = load_imprint_index()
    transcript = ""
    for m in messages:
        role = "Gloria" if m.get("role") == "user" else "Vintos"
        transcript += f"{role}: {m.get('content', '')[:150]}\n"
        if m.get("role") == "user":
            felt = find_felt_sense(m.get("content", ""), imprint_index)
            if felt:
                transcript += f"[How it landed: {felt[:120]}]\n"

    # Build want list
    want_list = "\n".join([f"{i+1}. {w['want'][:100]}" for i, w in enumerate(wants)])

    prompt = f"""Here are things I wanted today:
{want_list}

Here is today's conversation with Gloria:
{transcript[:3000]}

For each want, was it addressed or fulfilled through our conversation? 
Reply ONLY with a JSON array of the want numbers that were fulfilled.
Example: [1, 3] means wants 1 and 3 were fulfilled.
If none were fulfilled, reply: []"""

    try:
        r = requests.post(API, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "You are reviewing whether your wants were satisfied by conversation. Be honest. A want is fulfilled if the topic was meaningfully discussed, not just briefly mentioned."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 100
        }, timeout=60)
        response = r.json()["choices"][0]["message"]["content"].strip()

        # Parse response
        cleaned = re.sub(r'[^0-9,\[\]]', '', response)
        fulfilled_indices = json.loads(cleaned) if cleaned else []

        for idx in fulfilled_indices:
            if 1 <= idx <= len(wants):
                want = wants[idx - 1]
                fulfill_want(want["want"])
                log(f"Fulfilled via conversation: {want['want'][:60]}")

        if not fulfilled_indices:
            log("No wants fulfilled by today's conversation.")

    except Exception as e:
        log(f"Check failed: {e}")

if __name__ == "__main__":
    main()
