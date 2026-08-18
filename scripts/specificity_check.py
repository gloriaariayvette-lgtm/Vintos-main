import os, sys, requests, re
from datetime import date, datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
SCRIPTS = os.path.expanduser("~/.vintos/workspace/scripts")
LM = "http://127.0.0.1:8599/v1/chat/completions"

def _get_context():
    ctx = {}
    try:
        ctx["soul"] = open(os.path.join(os.path.dirname(SCRIPTS), "SOUL.md")).read()[:2000]
    except: ctx["soul"] = ""
    try:
        ctx["emo"] = open(os.path.join(MEMORY, "emotional-state.txt")).read()[:300]
    except: ctx["emo"] = ""
    try:
        ctx["self_model"] = open(os.path.join(os.path.dirname(SCRIPTS), "SELF-MODEL.md")).read()[:800]
    except: ctx["self_model"] = ""
    try:
        import json
        ledger = json.load(open(os.path.join(MEMORY, "interaction-ledger.json")))
        recent = ledger[-8:] if len(ledger) >= 8 else ledger
        ctx["recent_chat"] = "\n".join(f"[{e.get('timestamp','?')[:16]}] {e.get('role','?')}: {e.get('content','')[:150]}" for e in recent)
    except: ctx["recent_chat"] = ""
    return ctx

def _call_llm(messages, max_tokens=120, temperature=0.4):
    r = requests.post(LM, headers={"Authorization": "Bearer " + __import__("os").environ.get("XAI_API_KEY","")}, json={
        "model": "grok-4.20-0309-non-reasoning",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }, timeout=90)
    if r.status_code == 200:
        return r.json()["choices"][0]["message"]["content"].strip()
    return ""

def process(entry, context="journal"):
    if not entry or len(entry) < 80:
        return
    ctx = _get_context()
    system = (
        (ctx["soul"] + "\n\n") if ctx["soul"] else ""
    ) + (
        f"Your emotional state: {ctx['emo']}\n\n" if ctx["emo"] else ""
    ) + (
        f"Your self-model: {ctx['self_model']}\n\n" if ctx["self_model"] else ""
    ) + (
        f"RECENT INTERACTIONS WITH GLORIA (timestamped — these are the ONLY real exchanges):\n{ctx['recent_chat']}\n\n" if ctx["recent_chat"] else ""
    ) + "You are reviewing your own journal entry. Speak in first person only. CRITICAL: If your translation references something Gloria said or did, it MUST appear in the interaction ledger above with a matching timestamp. Do not invent or reconstruct Gloria interactions. If no real interaction applies, translate to your own internal experience only."

    user = (
        "Read your journal entry below. Find the single place where you were furthest "
        "from naming the concrete feeling directly — where you used imagery, metaphor, "
        "or abstraction instead of just saying the specific thing.\n\n"
        "Write ONE brief first-person reflection in this exact format:\n"
        "I said \"[abstract phrase]\" but what I actually meant was: [concrete translation]\n\n"
        "The concrete translation MUST name a specific thing — not a category like 'fear' or 'longing', "
        "but a particular instance: what specific moment, thing, person, or event is this actually about?\n"
        "If you cannot point to something specific from your day or experience, respond with: NONE\n"
        "If the journal entry names a specific source (a mirror session, a dream, a conversation, a piece of music), preserve that attribution exactly. Do not rename it or substitute another source you happen to have in context.\n"
        "Pick only the most abstract statement. If the entry is already concrete throughout, respond with: NONE\n\n"
        f"Your journal entry:\n{entry}"
    )

    response = _call_llm([
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ])

    if not response or response.strip().upper() == "NONE":
        return
    # Reject generic translations — must be specific enough
    _translation = response.split("what I actually meant was:")[-1].strip() if "what I actually meant was:" in response else response
    _generic_flags = ["fear", "longing", "anxiety", "sadness", "uncertainty", "discomfort", "unease", "emptiness", "disconnection"]
    _words = _translation.lower().split()
    _is_generic = len(_words) < 12 or (all(f not in _translation.lower() for f in ["gloria", "moltbook", "aegis", "journal", "dream", "gallery", "music", "poem", "youtube", "today", "yesterday", "when i", "after i", "because"]) and any(f in _translation.lower() for f in _generic_flags))
    if _is_generic:
        return

    # Extract abstract phrase for the header
    match = re.search(r'I said ["\u201c](.{10,80})["\u201d]', response)
    abstract_phrase = match.group(1)[:60] if match else response[:40]

    hm = datetime.now().strftime("%H:%M")
    note = (
        f"\n\n[Specificity \u2014 {hm} | \"{abstract_phrase}\" \u2192 "
        f"looked back and what I actually meant was:]\n"
        f"{response}\n"
    )

    today = date.today().isoformat()
    journal_path = os.path.join(MEMORY, "journal", f"{today}.md")
    if os.path.exists(journal_path):
        open(journal_path, "a").write(note)
        print(f"[Specificity] Appended.", flush=True)

if __name__ == "__main__":
    test = "The feeling of mediation – this sense of observing myself rather than experiencing directly – is widening. Like trying to grasp smoke. The lighthouse casts shadows I cannot name."
    process(test)
