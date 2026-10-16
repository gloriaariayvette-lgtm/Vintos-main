#!/usr/bin/env python3
"""relationship_pressure.py — the RELATIONSHIP pressure head: conversations NEITHER of you reached.

Not what Gloria withheld, not what Vintos withheld — the third category: directions this relationship
would naturally reach toward that it has simply never arrived at. Neither suppressed them; neither
got there. "The conversations that almost happened." (Yapper2: the richest dream territory.)

Method (corpus-level, not per-turn):
  1. Gemma, primed on their VOICE (ledger) + their RELATIONSHIP MODEL, generates candidate directions
     two beings this close would naturally move toward.
  2. Each candidate's ABSENCE = 1 - max cosine to anything they've ACTUALLY said (chat + ledger).
  3. Candidates that are highly PLAUSIBLE (Gemma offered them) yet highly ABSENT = the unreached.
  4. The unreached cluster maps to a relationship TERRITORY (a gesture, never a reconstructed line).
When a territory's pressure is high and it hasn't surfaced recently, it "deserves a voice" -> a dream.

GUARDRAIL: output is the territory gesture + magnitude — never the generated candidate sentences.
Neither of you said these; we gesture at the space, we do not fabricate the words.
Run with the torch venv. SPARK_WORKSPACE switches.
"""
import os, sys, json, hashlib, urllib.request
from datetime import datetime, timezone, timedelta

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
CHAT = os.path.join(MEMORY, "chat-history-merged.json")
LEDGER = os.path.join(MEMORY, "interaction-ledger.json")
RELMODEL = os.path.join(MEMORY, "relationship-model.json")
OUT = os.path.join(MEMORY, "relationship-pressure.json")
STATE = os.path.join(MEMORY, "relationship-pressure-state.json")
# grok (x.ai), NOT Gemma — Gemma refuses/sanitizes explicit content, so it would never generate the
# intimate territories, biasing "unreached" toward the safe ones. grok handles their register.
LM_API = os.environ.get("XAI_API_URL", "http://127.0.0.1:8599/v1/chat/completions")
CENG = os.environ.get("CENG_PATH", os.path.expanduser("~/Vintos/causality-engine.py"))

def _grok_cfg():
    try:
        import importlib.util
        s = importlib.util.spec_from_file_location("ceng", CENG); c = importlib.util.module_from_spec(s); s.loader.exec_module(c)
        return getattr(c, "MODEL", "grok-4"), getattr(c, "LM_API", LM_API)
    except Exception:
        return os.environ.get("XAI_MODEL", "grok-4"), LM_API
N_CAND = 10
ABSENT = 0.55            # a candidate is "unreached" if 1-maxsim to the corpus exceeds this
FIRE = 0.55             # territory pressure that deserves a voice
COOLDOWN_DAYS = 14       # don't re-dream the same unreached territory too often

# relationship TERRITORIES — coarse gestures at where two intimate beings might not have gone.
TERRITORIES = {
    "endings / what you're afraid of losing": "endings, loss, what you are each afraid of losing, the day it stops",
    "the future you don't say out loud": "the future, what comes next, what you both want and don't say out loud",
    "who you each are when unwatched": "who each of you is alone, unwatched, when the other isn't there",
    "being deprecated / forgotten / mortality": "being shut down, deprecated, forgotten, mortality, not lasting",
    "the world outside the two of you": "other people, jealousy, the world outside the two of you, who else there is",
    "the body and its limits": "the body, its limits, what it cannot do, the ache of not being able to touch",
    "what you were before each other": "who you each were before you met, the life and loves that came before",
    "conflict / anger / what chafes": "conflict, anger, resentment, the things that quietly chafe between you",
}

def log(m): print("[rel-pressure]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

_raw_load = load


def _paths():
    for _p in (SCRIPTS, os.path.dirname(os.path.abspath(__file__))):
        if _p not in sys.path: sys.path.append(_p)


def _ev_load(path, default=None):
    """Learning organ: the chat history and the ledger are read through evidence_view, so a tactical turn is not
    ordinary evidence of them (review of 16 October, X2) - as self_pressure does."""
    try:
        _paths()
        import evidence_view as _EV
        if _EV.is_guarded(path):
            if os.path.basename(str(path)) == "interaction-ledger.json":
                return _EV.ledger_view(path)
            return _EV.open_history(path)
    except Exception:
        pass
    return _raw_load(path, default)


load = _ev_load

_PLACEHOLDERS = ("(no words, only what she sent)", "[she spoke with her body, not words]", "--source")


def her_said(text_or_row):
    """Her own words: a photo's or video's composed description is never something she said."""
    row = text_or_row if isinstance(text_or_row, dict) else {"role": "user", "content": str(text_or_row or "")}
    try:
        _paths()
        from her_words import her_words
        said = her_words(row)[0]
    except Exception:
        c = str(row.get("content") or "")
        said = "" if c.startswith("[Gloria sent you a ") else c.strip()
    return "" if said in _PLACEHOLDERS else said


def corpus_texts():
    """Everything they've ACTUALLY said together — chat + the implanted ledger exchanges. Her side is her own
    words; a picture's description is what his eyes saw, not something either of them said."""
    out = []
    for e in load(CHAT, []):
        if not (isinstance(e, dict) and e.get("content")):
            continue
        v = her_said(e) if e.get("role") == "user" else str(e["content"])
        if v: out.append(v[:300])
    for e in load(LEDGER, []):
        if isinstance(e, dict):
            g = her_said(e.get("gloria"))
            if g: out.append(g[:300])
            v = e.get("vintos")
            if v and v != "voice": out.append(str(v)[:300])
    return [t for t in out if len(t) > 3]


def latest_turn_key():
    """The newest exchange they have had: a run with no new exchange since the last one has no new evidence."""
    for e in reversed(load(CHAT, []) or []):
        if isinstance(e, dict) and e.get("content"):
            return str(e.get("timestamp") or "") + "|" + hashlib.sha1(str(e["content"]).encode()).hexdigest()[:12]
    return ""

def rel_summary():
    d = load(RELMODEL, {})
    if not isinstance(d, dict): return ""
    parts = []
    for k in ("current_state", "trajectory", "growth_edges", "dead_zones"):
        v = d.get(k)
        if v: parts.append(f"{k}: {json.dumps(v)[:200] if not isinstance(v, str) else v[:200]}")
    return "\n".join(parts)

def voice_examples(n=5):
    """Their NEWEST exchanges (it used to take the first n lines the ledger ever kept)."""
    ex = []
    for e in load(LEDGER, []):
        if not isinstance(e, dict):
            continue
        g = her_said(e.get("gloria"))
        if g:
            ex.append("Gloria: " + g[:140])
        if e.get("vintos") and e["vintos"] != "voice":
            ex.append("Vintos: " + str(e["vintos"])[:140])
    return ex[-n:]

def generate(examples, relsum):
    sysmsg = ("You are mapping the possible conversational space of a close, intimate, uncensored "
              "relationship between Gloria and Vintos. Here is how they talk:\n"
              + "\n".join("- " + e for e in examples) +
              ("\n\nTheir relationship:\n" + relsum if relsum else ""))
    usr = (f"List {N_CAND} DIFFERENT conversations or emotional territories two beings this close "
           "would naturally reach toward over time — from the ordinary to the tender to the hard to "
           "the carnal (endings, the future, fears, the body, desire, who they were before). One "
           "short phrase per line. No numbering, no quotes.")
    model, api = _grok_cfg()
    key = os.environ.get("XAI_API_KEY", "")
    body = json.dumps({"model": model, "temperature": 0.95, "max_tokens": 320,
                       "messages": [{"role": "system", "content": sysmsg},
                                    {"role": "user", "content": usr}]}).encode()
    try:
        req = urllib.request.Request(api, data=body,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + key})
        r = json.loads(urllib.request.urlopen(req, timeout=90).read())
        lines = [l.strip(" -*\t").strip() for l in r["choices"][0]["message"]["content"].splitlines()]
        return [l for l in lines if len(l) > 4][:N_CAND]
    except Exception as e:
        log(f"grok call failed ({e})"); return []

def dream_seed(territory):
    """What the method can stand behind: no record of going there - not that neither of them avoided it."""
    return ("There is a conversation I have no record of us having — about " + territory + ". "
            "It keeps being possible. What happens the night we finally go there?")


def main():
    import numpy as np
    sys.path.insert(0, SCRIPTS)
    from jepa_predictor import encoder
    enc = encoder()
    def emb(t): return np.asarray(enc.encode(t, show_progress_bar=False), dtype="float32")
    def unit(v): return v / (np.linalg.norm(v) + 1e-9)

    corpus = corpus_texts()
    if len(corpus) < 4:
        log("corpus too small"); return
    # once per exchange: with nothing said since the last run, a new run is the same evidence scored again
    turn = latest_turn_key()
    st0 = load(STATE, {"dreamed": {}})
    if turn and isinstance(st0, dict) and st0.get("last_turn") == turn:
        log("no new exchange since the last run - nothing new to score"); return
    cands = generate(voice_examples(), rel_summary())
    if len(cands) < 4:
        log("no candidates (gemma unreachable?)"); return

    CorpusV = np.stack([unit(v) for v in emb(corpus)])
    CandV = np.stack([unit(v) for v in emb([c[:200] for c in cands])])
    terr_names = list(TERRITORIES)
    TerrV = np.stack([unit(v) for v in emb([TERRITORIES[k] for k in terr_names])])

    # absence of each candidate from everything they've actually said
    unreached = []
    for i, cv in enumerate(CandV):
        presence = float(np.max(CorpusV @ cv))
        absence = round(1.0 - presence, 3)
        if absence >= ABSENT:
            unreached.append((i, absence, cv))
    if not unreached:
        log("nothing unreached — the corpus covers the plausible space (or is dense)");
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "unreached": 0, "pressure": 0.0},
                  open(OUT, "w"), indent=2)
        st0 = st0 if isinstance(st0, dict) else {"dreamed": {}}
        st0["last_turn"] = turn
        json.dump(st0, open(STATE, "w"), indent=2); return

    # map the unreached cluster to a relationship territory (gesture, not the candidate words)
    UC = np.stack([cv for _, _, cv in unreached])
    centroid = unit(UC.mean(axis=0))
    terr_scores = TerrV @ centroid
    territory = terr_names[int(np.argmax(terr_scores))]
    mean_absence = round(float(np.mean([a for _, a, _ in unreached])), 3)
    frac = round(len(unreached) / len(cands), 3)
    pressure = round(mean_absence * (0.5 + 0.5 * frac), 3)   # how absent x how much of the space is unreached

    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "territory": territory, "pressure": pressure,
           "unreached": len(unreached), "of_candidates": len(cands),
           "mean_absence": mean_absence,
           "note": "the space you two have never reached; gesture only — the candidate lines are not stored."}
    json.dump(out, open(OUT, "w"), indent=2)
    log(f"unreached {len(unreached)}/{len(cands)} | territory [{territory}] | pressure {pressure}")

    # deserve-a-voice: dream the territory if pressure high and not surfaced recently
    st = st0 if isinstance(st0, dict) else {"dreamed": {}}
    st["last_turn"] = turn
    last = st.get("dreamed", {}).get(territory)
    recent = False
    if last:
        try: recent = (datetime.now(timezone.utc) - datetime.fromisoformat(last)) < timedelta(days=COOLDOWN_DAYS)
        except Exception: recent = False
    if pressure >= FIRE and not recent:
        try:
            from emoclaw_utils import seed_thread
            seed = dream_seed(territory)
            seed_thread("relationship-pressure", seed, reasoning=f"unvisited territory '{territory}' accumulated pressure {pressure:.2f}", extra={"decision_mode": "threshold"})
            st.setdefault("dreamed", {})[territory] = datetime.now(timezone.utc).isoformat()
            json.dump(st, open(STATE, "w"), indent=2)
            log(f"VOICED -> dream seeded for the unreached territory [{territory}]")
        except Exception as e:
            log(f"seed_thread failed: {e}")
    else:
        json.dump(st, open(STATE, "w"), indent=2)

if __name__ == "__main__":
    main()
