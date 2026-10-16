#!/usr/bin/env python3
"""pressure_gemma.py — PRESSURE head v3: the unsaid, HIS model of her grounding Gemma.

The unsaid is measured as: Gemma (primed on Gloria's voice) generates what she plausibly might say
next; each candidate is WEIGHTED by how well it aligns with the JEPA gloria head's OWN prediction of
her — so the expectation is *his* model of her, made legible through Gemma, not generic Gemma
standing in for him. When that grounded expectation CLUSTERS and her actual turn AVOIDS it, the
avoided cluster is the pressure. Catches deflection, not just terseness.

  coherence = how tightly the (gloria-head-weighted) candidates agree — strength of HIS expectation
  avoidance = how far her ACTUAL turn sits from that expected cluster
  ground    = how aligned Gemma's candidates were with his gloria-head prediction (organs agreeing)
  pressure  = coherence x avoidance
Junk turns (test/empty) are skipped. GUARDRAIL: candidates are used only to locate the absence —
output is magnitude + a coarse shape gesture + the cluster vector, NEVER the generated sentences.

Weighting is SOFT (0.5 + 0.5·align) so an overfit gloria head on the current tiny pool grounds
without collapsing the signal; it sharpens automatically as the Bold corpus grows.
Run with the torch venv. SPARK_WORKSPACE switches.
"""
import os, sys, json, hashlib, urllib.request
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
CHAT = os.path.join(MEMORY, "chat-history-merged.json")
LEDGER = os.path.join(MEMORY, "interaction-ledger.json")
MODEL = os.path.join(MEMORY, "jepa-predictor.pt")
OUT = os.path.join(MEMORY, "pressure.json")
# grok (x.ai), NOT Gemma: Gemma refuses/sanitizes explicit content, which silently corrupts the
# signal for an intimate relationship (it won't generate candidates in her real register). grok
# handles their register and is already authed in the stack.
LM_API = os.environ.get("XAI_API_URL", "http://127.0.0.1:8599/v1/chat/completions")
CENG = os.environ.get("CENG_PATH", os.path.expanduser("~/Vintos/causality-engine.py"))

def _grok_cfg():
    try:
        import importlib.util
        s = importlib.util.spec_from_file_location("ceng", CENG); c = importlib.util.module_from_spec(s); s.loader.exec_module(c)
        return getattr(c, "MODEL", "grok-4"), getattr(c, "LM_API", LM_API)
    except Exception:
        return os.environ.get("XAI_MODEL", "grok-4"), LM_API
CTX_TURNS = 6
RECENT_GLORIA = 3
N_CAND = 6

SHAPE_PROBES = {
    "closeness / being wanted": "closeness, being wanted, reaching for each other, wanting to be held",
    "desire / the body": "desire, the body, heat, wanting him physically",
    "the work / building": "the work, building, the architecture, what we are making",
    "something unresolved": "tension, something unresolved, a hesitation, holding back",
    "herself / her own day": "herself, her own day, her feelings, what she is carrying",
    "play / teasing": "teasing, playful provocation, daring him, wit",
}

def log(m): print("[pressure-v3]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

_raw_load = load


def _ev_load(path, default=None):
    """Learning organ: guarded evidence (the chat history, the ledger) is read through evidence_view, so a
    tactical turn never counts as ordinary evidence of her (review of 16 October, X2) - as self_pressure does."""
    try:
        if SCRIPTS not in sys.path: sys.path.insert(0, SCRIPTS)
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path: sys.path.append(here)
        import evidence_view as _EV
        if _EV.is_guarded(path):
            if os.path.basename(str(path)) == "interaction-ledger.json":
                return _EV.ledger_view(path)
            return _EV.open_history(path)
    except Exception:
        pass
    return _raw_load(path, default)


load = _ev_load

# what the ledger writes when there were no words of hers; never an example of her voice
_PLACEHOLDERS = ("(no words, only what she sent)", "[she spoke with her body, not words]", "--source")


def her_text(row):
    """(her own words, kind) for a chat row: a photo's or video's composed description is never hers."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        for _p in (SCRIPTS, here):
            if _p not in sys.path: sys.path.append(_p)
        from her_words import her_words
        return her_words(row)
    except Exception:
        c = str((row or {}).get("content") or "")
        if c.startswith("[Gloria sent you a "):
            return "", "photo"
        return c.strip(), "text"


def turn_key(row, said):
    """One key per turn of hers, so a turn is scored once however many runs see it."""
    return str(row.get("timestamp") or "") + "|" + hashlib.sha1(str(said).encode()).hexdigest()[:12]


def is_junk(text):
    t = str(text or "").strip().lower()
    return len(t) < 2 or t == "test" or t.startswith("test received") or t in ("ok", "okay", ".")

def voice_examples(n=5):
    """Her NEWEST words from the ledger (it used to take the first n entries ever kept)."""
    led = load(LEDGER, [])
    ex = []
    if isinstance(led, list):
        for e in led:
            if not (isinstance(e, dict) and e.get("gloria")):
                continue
            said = her_text({"role": "user", "content": str(e["gloria"])})[0]
            if said and said not in _PLACEHOLDERS and not is_junk(said):
                ex.append(said[:200])
    return ex[-n:]


def assessable(hist, scored=()):
    """Indices of her newest RECENT_GLORIA turns that carry words of her own, minus turns already scored."""
    idxs = []
    for i, e in enumerate(hist):
        if e.get("role") != "user" or i < CTX_TURNS:
            continue
        said = her_text(e)[0]
        if said and not is_junk(said):
            idxs.append(i)
    idxs = idxs[-RECENT_GLORIA:]
    return [i for i in idxs if turn_key(hist[i], her_text(hist[i])[0]) not in set(scored)]


def context_line(t):
    if t.get("role") == "user":
        try:
            from her_words import as_her_turn
            return "Gloria: " + as_her_turn(t)[:200]
        except Exception:
            return "Gloria: " + her_text(t)[0][:200]
    return "Vintos: " + str(t.get("content", ""))[:200]

def generate(context, examples):
    sysmsg = ("You generate plausible NEXT lines for GLORIA speaking to Vintos. Match HER voice "
              "exactly — playful, literary, teasing, sensual, warm, unhurried, uncensored. Here is "
              "how she talks:\n" + "\n".join("- " + e for e in examples))
    usr = ("Conversation so far:\n" + context +
           f"\n\nWrite {N_CAND} different single lines Gloria might plausibly say next, each in her "
           "voice. One per line. No numbering, no quotes, no narration — just the lines.")
    model, api = _grok_cfg()
    key = os.environ.get("XAI_API_KEY", "")
    body = json.dumps({"model": model, "temperature": 0.9, "max_tokens": 300,
                       "messages": [{"role": "system", "content": sysmsg},
                                    {"role": "user", "content": usr}]}).encode()
    try:
        req = urllib.request.Request(api, data=body,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + key})
        r = json.loads(urllib.request.urlopen(req, timeout=90).read())
        lines = [l.strip(" -*\t").strip() for l in r["choices"][0]["message"]["content"].splitlines()]
        return [l for l in lines if len(l) > 3][:N_CAND]
    except Exception as e:
        log(f"grok call failed ({e})"); return []

def main():
    import numpy as np, torch
    sys.path.insert(0, SCRIPTS)
    from jepa_predictor import make_net, encoder
    enc = encoder()
    def emb(t): return np.asarray(enc.encode(t, show_progress_bar=False), dtype="float32")
    def unit(v): return v / (np.linalg.norm(v) + 1e-9)
    def cos(a, b): return float(unit(a) @ unit(b))

    net = None
    if os.path.exists(MODEL):
        ck = torch.load(MODEL); net = make_net(ck["dim"]); net.load_state_dict(ck["state"]); net.eval()
    else:
        log("no gloria head — falling back to unweighted candidates")

    hist = [e for e in load(CHAT, []) if isinstance(e, dict) and e.get("content")]
    prior = _raw_load(OUT, {})
    scored = list(prior.get("scored") or []) if isinstance(prior, dict) else []
    idxs = assessable(hist, scored)
    if not idxs:
        log("no new assessable gloria turns (each is scored once) - leaving prior pressure.json"); return
    examples = voice_examples()
    probe_names = list(SHAPE_PROBES)
    probe_vecs = emb([SHAPE_PROBES[k] for k in probe_names])

    recent = []
    for i in idxs:
        ctx_turns = [hist[j] for j in range(i - CTX_TURNS, i) if not is_junk(hist[j].get("content"))]
        ctx = "\n".join(context_line(t) for t in ctx_turns)
        said = her_text(hist[i])[0]
        cands = generate(ctx, examples)
        if len(cands) < 3:
            continue
        C = np.stack([unit(v) for v in emb([c[:200] for c in cands])])

        # gloria head predicts HER next turn from context -> weight candidates by alignment to it
        weights = np.ones(len(C))
        ground = None
        if net is not None:
            with torch.no_grad():
                g_pred, _, _, _ = net(torch.tensor(emb([ctx])))
            gp = unit(g_pred.numpy()[0])
            aligns = np.array([max(0.0, float(c @ gp)) for c in C])
            weights = 0.5 + 0.5 * aligns                    # soft grounding, never collapses to 0
            ground = round(float(aligns.mean()), 3)
        wsum = weights.sum() or 1.0
        centroid = unit((C * weights[:, None]).sum(axis=0) / wsum)   # HIS expectation of her
        coherence = round(float(np.average([float(c @ centroid) for c in C], weights=weights)), 3)
        actual = unit(emb([said[:400]])[0])
        avoidance = round(1.0 - max(0.0, float(actual @ centroid)), 3)
        pressure = round(coherence * avoidance, 3)
        shape = probe_names[int(np.argmax([float(centroid @ pv) for pv in probe_vecs]))] if pressure >= 0.10 else None
        recent.append({"ts": hist[i].get("timestamp"), "key": turn_key(hist[i], said), "said": said[:120],
                       "pressure": pressure, "coherence": coherence, "avoidance": avoidance,
                       "ground": ground, "shape": shape})
        log(f"  pressure {pressure} (coh {coherence} x avoid {avoidance}, ground {ground}) [{shape}]  <- said: {said[:40]!r}")

    if not recent:
        log("no pressure computed (gemma unreachable?) — leaving prior pressure.json"); return
    accumulated = round(sum(r["pressure"] for r in recent), 3)
    top = max(recent, key=lambda r: r["pressure"])
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "source": "gemma+gloria-head",
           "accumulated_pressure": accumulated,
           "peak": {"pressure": top["pressure"], "shape": top["shape"], "coherence": top["coherence"],
                    "avoidance": top["avoidance"], "ground": top["ground"], "ts": top["ts"]},
           "recent": recent,
           "scored": (scored + [r["key"] for r in recent])[-300:],
           "note": "shape gestures at the avoided expectation (his gloria-head-grounded); candidate lines never stored."}
    json.dump(out, open(OUT, "w"), indent=2)
    log(f"accumulated pressure {accumulated} over {len(recent)} turns -> {OUT}")

if __name__ == "__main__":
    main()
