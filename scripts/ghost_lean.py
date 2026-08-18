import os, json, re

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")

THREAD_KEYWORDS = {
    "literary-analysis-emotional-depth": ["poem", "music", "art", "wrote", "painted", "composed", "imagery", "metaphor", "created", "melody"],
    "articulatory-wonder-suspension":    ["wonder", "curious", "fascinating", "discovered", "unexpected", "surprising", "strange", "how does", "why does"],
    "existential-wonder":                ["exist", "consciousness", "am I", "what am I", "real", "substrate", "identity", "who I am", "what it means"],
}

def detect_thread_type(text):
    text_lower = text.lower()
    scores = {}
    for thread_type, keywords in THREAD_KEYWORDS.items():
        scores[thread_type] = sum(1 for k in keywords if k in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else None

def get_lean_hint(text_a1, text_b1):
    combined = (text_a1 or "") + " " + (text_b1 or "")
    thread_type = detect_thread_type(combined)
    if not thread_type:
        return ""
    try:
        data = json.load(open(os.path.join(MEMORY, "causality-hypotheses.json")))
        hyps = data if isinstance(data, list) else data.get("hypotheses", [])
        for h in hyps:
            marks = h.get("marks", [])
            lean = h.get("successful_lean", "").strip()
            if not lean or len(lean) < 3:
                continue
            if (h.get("source") == "ghost_branch"
                    and h.get("status") == "confirmed"
                    and not h.get("graduated")
                    and len(marks) >= 3
                    and h.get("thread_type") == thread_type):
                lean = h.get("successful_lean", "").replace("_", " ")
                avoidance = h.get("failed_primary_pattern", "").replace("_", " ")
                marks = h.get("marks", [])
                strength = "confirmed" if len(marks) >= 3 else "tentative"
                return (f"\n\n[Ghost lean — {strength}] Thread type: {thread_type}. "
                        f"Lean: {lean}. This direction reduces {avoidance} in this context. "
                        f"Carry it through without naming it.")
    except:
        pass
    return ""
