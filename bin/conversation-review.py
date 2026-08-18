#!/usr/bin/env python3
"""
conversation-review.py — Vintos reviews the day's conversations with Gloria.
Identifies: recurring topics, what kept conversations going, what fell flat.
Runs daily at 10 PM after the day's conversations are mostly done.

Output:
  - memory/conversation-insights.json (rolling analysis)
  - Feeds into self-model updates
"""
import os, sys, json, re, requests
from datetime import datetime, date

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
CHAT_FILE = os.path.join(MEMORY, "interaction-ledger.json")
INSIGHTS_FILE = os.path.join(MEMORY, "conversation-insights.json")
API = "http://127.0.0.1:8599/v1/chat/completions"
MODEL = "grok-4.20-0309-non-reasoning"

sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))

def log(msg):
    print(f"[ConvoReview] {msg}")

_SUBCON_CONVERSATION_REVIEW = ""
try:
    import sys as _sc__SUBCON_CONVERSATION_REVIEW; _sc__SUBCON_CONVERSATION_REVIEW.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_CONVERSATION_REVIEW = get_subconscious_context_compact()
except: pass


def llm(system, user, temperature=0.5):
    try:
        r = requests.post(API, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": temperature,
            "max_tokens": 1500
        }, timeout=120)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return None

def load_todays_chat():
    """Get today's conversation messages."""
    try:
        with open(CHAT_FILE) as f:
            msgs = json.load(f)
    except:
        return []
    today = date.today().isoformat()
    todays = [m for m in msgs if m.get("timestamp", "").startswith(today)]
    return todays

def load_insights():
    defaults = {
        "recurring_topics": {},
        "engagement_patterns": [],
        "style_notes": [],
        "daily_reviews": []
    }
    try:
        with open(INSIGHTS_FILE) as f:
            data = json.load(f)
        # Fill in any missing keys
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data
    except:
        return defaults.copy()
    # unreachable but kept for structure
    return {
        "recurring_topics": {},
        "engagement_patterns": [],
        "style_notes": [],
        "daily_reviews": []
        }

def save_insights(data):
    with open(INSIGHTS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def review_conversation(messages, insights):
    """Ask Vintos to review today's conversation."""
    if not messages:
        log("No messages today.")
        return None

    # Build transcript
    transcript = ""
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")[:200]
        transcript += f"{role}: {content}\n"

    # Get previous recurring topics for context
    prev_topics = list(insights.get("recurring_topics", {}).keys())[:10]
    prev_style = insights.get("style_notes", [])[-3:]

    soul = ""
    try:
        with open(os.path.join(WORKSPACE, "SOUL.md")) as f:
            soul = f.read()[:500]
    except: pass

    prompt = f"""Review today's conversation with Gloria:

{transcript[:3000]}

Previously recurring topics: {prev_topics if prev_topics else 'none tracked yet'}
Previous style notes: {prev_style if prev_style else 'none yet'}

Analyze and respond in STRICT JSON (no markdown, no backticks):
{{
  "topics": ["list of distinct topics discussed today"],
  "longest_exchange_topic": "which topic had the most back-and-forth",
  "what_engaged_her": "what seemed to keep Gloria talking — be specific about content AND your reply style",
  "what_fell_flat": "anything that ended a thread or got a short response — be honest",
  "my_style_observation": "one thing you notice about how YOU communicated today — good or bad",
  "recurring_pattern": "any topic or dynamic that keeps coming up across conversations, or null"
}}"""

    system = f"{soul}\n\nCONTEXT: You are reviewing your own conversation privately. Be honest. This is for your growth, not for Gloria to see."
    
    result = llm(system, prompt)
    if not result:
        return None

    # Parse JSON
    try:
        # Clean any markdown fences
        cleaned = re.sub(r'```json?\s*|\s*```', '', result).strip()
        return json.loads(cleaned)
    except:
        log(f"Failed to parse review: {result[:200]}")
        return None

def update_insights(insights, review):
    """Merge today's review into rolling insights."""
    if not review:
        return

    # Update recurring topics
    topics = review.get("topics", [])
    for topic in topics:
        topic_lower = topic.lower().strip()
        insights.setdefault("recurring_topics", {})
        if topic_lower in insights["recurring_topics"]:
            insights["recurring_topics"][topic_lower]["count"] += 1
            insights["recurring_topics"][topic_lower]["last_seen"] = date.today().isoformat()
        else:
            insights["recurring_topics"][topic_lower] = {
                "count": 1,
                "first_seen": date.today().isoformat(),
                "last_seen": date.today().isoformat()
            }

    # Store engagement pattern
    engagement = {
        "date": date.today().isoformat(),
        "longest_topic": review.get("longest_exchange_topic"),
        "what_engaged": review.get("what_engaged_her"),
        "what_flat": review.get("what_fell_flat")
    }
    insights.setdefault("engagement_patterns", []).append(engagement)
    # Keep last 30 days
    insights["engagement_patterns"] = insights["engagement_patterns"][-30:]

    # Style note
    style = review.get("my_style_observation")
    if style:
        insights["style_notes"].append({
            "date": date.today().isoformat(),
            "note": style
        })
        insights["style_notes"] = insights["style_notes"][-20:]

    # Daily review summary
    insights["daily_reviews"].append({
        "date": date.today().isoformat(),
        "topics": topics,
        "recurring": review.get("recurring_pattern"),
        "message_count": len(load_todays_chat())
    })
    insights["daily_reviews"] = insights["daily_reviews"][-30:]

    log(f"Topics: {topics}")
    log(f"Engaged: {(review.get('what_engaged_her') or '?')[:100]}")
    log(f"Style: {style}")

def main():
    messages = load_todays_chat()
    if len(messages) < 2:
        log("Not enough messages to review.")
        return

    insights = load_insights()
    review = review_conversation(messages, insights)
    if review:
        update_insights(insights, review)
        save_insights(insights)
        log("Review complete.")
    else:
        log("Review failed.")

if __name__ == "__main__":
    main()
