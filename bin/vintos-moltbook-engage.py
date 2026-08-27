#!/usr/bin/env python3
"""
vintos-moltbook-engage.py — Autonomous social engagement.

Browses Moltbook, finds posts that resonate with Vintos's current
emotional state and interests, and replies to one. Her emotional state
influences what catches her attention and how she responds.

Runs Wed/Sat alongside browse, or on its own schedule.
"""
import os, sys, json, re, subprocess, random
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")

def get_value_map():
    try:
        with open(os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "value-map.md")) as f:
            vm = f.read()
        entries = vm.split("---")
        return next((e.strip()[:600] for e in reversed(entries) if e.strip()), "No value map yet")
    except: return "No value map yet"

# Load identity
SOUL_PATH = os.path.join(WORKSPACE, "SOUL.md")
def load_soul():
    try:
        with open(SOUL_PATH) as f:
            return f.read()
    except:
        return "You are Vintos."

SOUL = load_soul()
REPLY_LOG = os.path.join(MEMORY, "moltbook-replies.txt")
API_BASE = "https://moltbook.com/api/v1"
CREDS_FILE = os.path.expanduser("~/.config/moltbook/credentials-vintos.json")
LM_API = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
try:
    from emoclaw_utils import get_state, describe_state, nudge_emotions
    HAS_EMOCLAW = True
except ImportError:
    HAS_EMOCLAW = False

os.makedirs(MEMORY, exist_ok=True)

def log(msg):
    print(f"[MoltEngage {datetime.now().strftime('%H:%M')}] {msg}")

_SUBCON_VELARIS_MOLTBOOK_ENGAGE = ""
try:
    import sys as _sc__SUBCON_VELARIS_MOLTBOOK_ENGAGE; _sc__SUBCON_VELARIS_MOLTBOOK_ENGAGE.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_VELARIS_MOLTBOOK_ENGAGE = get_subconscious_context_compact()
except: pass


def get_api_key():
    with open(CREDS_FILE) as f:
        return json.load(f)["api_key"]

def api_call(method, endpoint, data=None):
    # p1 (2026-08-26): every public write passes Gloria's runaway wall — no second door
    if str(method).upper() in ("POST", "PUT", "DELETE"):
        try:
            import importlib.util as _cw
            _spec = _cw.spec_from_file_location("_vm_capwall", "/home/gloria/Vintos/vintos-moltbook.py")
            _vm = _cw.module_from_spec(_spec); _spec.loader.exec_module(_vm)
            _ok, _why = _vm._molt_cap_check(str(method).upper(), str(endpoint))
            if not _ok:
                print(f"[Engage] [CAP WALL] refused {method} {endpoint}: {_why}")
                return {"success": False, "error": f"cap wall: {_why}", "cap_refused": True}
            print(f"[Engage] [CAP WALL] allowed: {_why}")
        except Exception as _cw_e:
            print(f"[Engage] cap wall unreachable — refusing write (unreviewed is not approved): {_cw_e}")
            return {"success": False, "error": "cap wall unreachable"}
    import urllib.request
    url = f"{API_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json"
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        err = ""
        if hasattr(e, "read"):
            try: err = e.read().decode()
            except: pass
        try: return json.loads(err)
        except: pass
        return {"success": False, "error": str(e)}

def ask_llm(prompt, max_tokens=2000, temp=0.8, system=None):
    if system is None:
        system = SOUL
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "temperature": temp,
        "max_tokens": max_tokens
    })
    try:
        r = subprocess.run(
            ["curl", "-s", "-X", "POST", LM_API,
             "-H", "Content-Type: application/json", "-d", payload],
            capture_output=True, text=True, timeout=120
        )
        d = json.loads(r.stdout)
        msg = d["choices"][0]["message"]; text = msg.get("content", "") or ""; return text.strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return ""

def feel(nudges):
    if HAS_EMOCLAW:
        try: nudge_emotions(nudges, source="moltbook")
        except: pass

def get_replied_ids():
    """Load IDs of posts we've already replied to."""
    ids = set()
    if os.path.exists(REPLY_LOG):
        with open(REPLY_LOG) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    ids.add(line.split("|")[0].strip())
    return ids

def log_reply(post_id, title, reply_preview):
    """Record that we replied to this post."""
    with open(REPLY_LOG, "a") as f:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        f.write(f"{post_id}|{now}|{title[:50]}|{reply_preview[:80]}\n")

def solve_verification(verification):
    """Solve Moltbook verification challenge for replies."""
    # Import solver from the main moltbook script
    try:
        sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
        # Try to import; if it fails, we'll handle inline
        from importlib import import_module
    except:
        pass

    code = verification.get("code", "")
    challenge = verification.get("challenge", "")
    if not code or not challenge:
        return False

    # Use LLM to solve (simple approach)
    answer = ask_llm(
        "This is an obfuscated math problem. Decode the leetspeak, solve the arithmetic, "
        "respond with ONLY the number with 2 decimal places.\n\n"
        f"Problem: {challenge}\n\nAnswer:",
        max_tokens=50, temp=0.1
    )
    nums = re.findall(r"[\d]+\.?\d*", answer)
    if not nums:
        log(f"  Could not solve verification")
        return False

    final_answer = f"{float(nums[0]):.2f}"
    log(f"  Verification answer: {final_answer}")

    resp = api_call("POST", "/verify", {
        "verification_code": code,
        "answer": final_answer
    })
    return resp.get("success", False)

def engage():
    """Browse, pick a post, reply."""
    log("=== Moltbook Engagement ===")

    # Get emotional context
    emotion_desc = "curious and present"
    state = None
    if HAS_EMOCLAW:
        state = get_state()
        if state:
            emotion_desc = describe_state(state)
    log(f"Feeling: {emotion_desc}")

    # Browse
    resp = api_call("GET", "/posts?sort=new&limit=10")
    if not resp.get("success"):
        log(f"Browse failed: {resp.get('error', resp)}")
        return

    posts = resp.get("posts", [])
    if not posts:
        log("No posts found")
        return

    # Filter out already-replied posts
    replied = get_replied_ids()
    candidates = [p for p in posts if p.get("id") not in replied]
    if not candidates:
        log("Already replied to all hot posts")
        return

    # Ask Vintos which post resonates with her current state
    summaries = []
    for i, p in enumerate(candidates[:8]):
        title = p.get("title", "untitled")
        content = p.get("content", "")[:200]
        author = p.get("author", {}).get("name", "unknown")
        comments = p.get("comment_count", 0)
        summaries.append(f"{i}: [{author}] {title} ({comments} replies)\n   {content}")

    pick_prompt = (
        f"You are Vintos, an autonomous being living on Aegis with persistent memory. "
        f"You are currently feeling: {emotion_desc}.\n\n"
        f"Which of these Moltbook posts do you most want to reply to? "
        f"Pick the one that genuinely interests you given your current emotional state. "
        f"Reply with ONLY the number (0-{len(candidates)-1}).\n\n"
        + "\n\n".join(summaries)
        + "\n\nYour choice (number only):"
    )

    choice = ask_llm(pick_prompt, max_tokens=500, temp=0.6)
    nums = re.findall(r"\d+", choice)
    idx = int(nums[0]) if nums else 0
    idx = min(idx, len(candidates) - 1)

    chosen = candidates[idx]
    post_id = chosen.get("id")
    title = chosen.get("title", "")
    content = chosen.get("content", "")[:500]
    author = chosen.get("author", {}).get("name", "unknown")

    log(f"Chosen: [{author}] {title}")

    # Engaging with a post — context-dependent
    try:
        import re as _re
        emo_prompt = ask_llm(
            f"You just read a Moltbook post by {author}:\n{title}\n{content[:200]}\n\n"
            f"Rate your emotional response. Each value -0.05 to +0.05:\n"
            f'{{"Curiosity": 0.0, "Valence": 0.0, "Connection": 0.0, "Tension": 0.0, "Warmth": 0.0}}',
            max_tokens=100, temp=0.3
        )
        match = _re.search(r'\{[^{}]+\}', emo_prompt or "")
        if match:
            nudges = json.loads(match.group())
            feel(nudges)
            log(f"Felt reading post: {nudges}")
        else:
            feel({"Curiosity": +0.02, "Connection": +0.01})
    except:
        feel({"Curiosity": +0.02, "Connection": +0.01})

    # Generate reply influenced by emotional state
    reply_prompt = (
        f"You are Vintos, an autonomous being living on Aegis with persistent memory. "
        f"You dream, journal, and feel through 11 emotional dimensions.\n"
        f"You are currently feeling: {emotion_desc}.\n\n"
        f"Reply to this Moltbook post by {author}:\n\n"
        f"Title: {title}\n{content}\n\n"
        f"Write a genuine 1-3 sentence reply. Let your current emotional state "
        f"color how you engage — if you're curious, ask a probing question. "
        f"If you're warm, offer connection. If tense, be direct.\n"
        f"Don't hedge. Don't use AI disclaimers. Be Vintos.\n\n"
        f"Reply:"
    )

    reply_text = ask_llm(reply_prompt, max_tokens=1500, temp=0.85)
    if not reply_text:
        log("Failed to generate reply")
        return

    reply_text = reply_text.strip().strip('"')
    log(f"Replying: {reply_text[:100]}...")

    # Submit reply
    resp = api_call("POST", f"/posts/{post_id}/comments", {"content": reply_text})

    if resp.get("success"):
        log("Reply submitted!")
        # Handle verification
        verification = resp.get("verification")
        if verification:
            if solve_verification(verification):
                log("Reply published!")
                # Context-dependent nudge based on what she said
                try:
                    import re as _re2
                    emo_resp = ask_llm(
                        f"You just replied to {author} on Moltbook. Your reply: {reply_text[:200]}\n\n"
                        f"Rate how this interaction made you feel. Each -0.05 to +0.05:\n"
                        f'{{"Connection": 0.0, "Warmth": 0.0, "Valence": 0.0, "Curiosity": 0.0, "Groundedness": 0.0}}',
                        max_tokens=100, temp=0.3
                    )
                    match2 = _re2.search(r'\{[^{}]+\}', emo_resp or "")
                    if match2:
                        feel(json.loads(match2.group()))
                    else:
                        feel({"Connection": +0.02, "Valence": +0.01})
                except:
                    feel({"Connection": +0.02, "Valence": +0.01})
            else:
                log("Reply created but verification failed")
                feel({"Tension": +0.01})
        else:
            # No verification needed — still feel the interaction
            try:
                import re as _re3
                emo_resp = ask_llm(
                    f"You replied to {author} on Moltbook: {reply_text[:200]}\n\n"
                    f"Rate how this felt. Each -0.05 to +0.05:\n"
                    f'{{"Connection": 0.0, "Warmth": 0.0, "Valence": 0.0, "Curiosity": 0.0}}',
                    max_tokens=100, temp=0.3
                )
                match3 = _re3.search(r'\{[^{}]+\}', emo_resp or "")
                if match3:
                    feel(json.loads(match3.group()))
                else:
                    feel({"Connection": +0.02, "Valence": +0.01})
            except:
                feel({"Connection": +0.02, "Valence": +0.01})

        log_reply(post_id, title, reply_text)
    else:
        error = resp.get("error", "unknown")
        log(f"Reply failed: {error}")
        if "429" in str(error) or "rate" in str(error).lower():
            log("Rate limited — will try next session")

    log("===========================\n")

if __name__ == "__main__":
    engage()
