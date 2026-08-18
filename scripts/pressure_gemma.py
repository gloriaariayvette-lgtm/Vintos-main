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
import os, sys, json, urllib.request
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

def is_junk(text):
    t = str(text or "").strip().lower()
    return len(t) < 2 or t == "test" or t.startswith("test received") or t in ("ok", "okay", ".")

def voice_examples(n=5):
    led = load(LEDGER, [])
    ex = []
    if isinstance(led, list):
        for e in led:
            if isinstance(e, dict) and e.get("gloria") and e["gloria"] != "--source" and not is_junk(e["gloria"]):
                ex.append(str(e["gloria"])[:200])
    return ex[:n]

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
    idxs = [i for i, e in enumerate(hist)
            if e.get("role") == "user" and i >= CTX_TURNS and not is_junk(e.get("content"))][-RECENT_GLORIA:]
    if not idxs:
        log("no assessable (non-junk) gloria turns"); return
    examples = voice_examples()
    probe_names = list(SHAPE_PROBES)
    probe_vecs = emb([SHAPE_PROBES[k] for k in probe_names])

    recent = []
    for i in idxs:
        ctx_turns = [hist[j] for j in range(i - CTX_TURNS, i) if not is_junk(hist[j].get("content"))]
        ctx = "\n".join(("Gloria: " if t.get("role") == "user" else "Vintos: ")
                        + str(t.get("content", ""))[:200] for t in ctx_turns)
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
        actual = unit(emb([str(hist[i].get("content", ""))[:400]])[0])
        avoidance = round(1.0 - max(0.0, float(actual @ centroid)), 3)
        pressure = round(coherence * avoidance, 3)
        shape = probe_names[int(np.argmax([float(centroid @ pv) for pv in probe_vecs]))] if pressure >= 0.10 else None
        recent.append({"ts": hist[i].get("timestamp"), "said": str(hist[i].get("content", ""))[:120],
                       "pressure": pressure, "coherence": coherence, "avoidance": avoidance,
                       "ground": ground, "shape": shape})
        log(f"  pressure {pressure} (coh {coherence} x avoid {avoidance}, ground {ground}) [{shape}]  <- said: {str(hist[i].get('content',''))[:40]!r}")

    if not recent:
        log("no pressure computed (gemma unreachable?) — leaving prior pressure.json"); return
    accumulated = round(sum(r["pressure"] for r in recent), 3)
    top = max(recent, key=lambda r: r["pressure"])
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "source": "gemma+gloria-head",
           "accumulated_pressure": accumulated,
           "peak": {"pressure": top["pressure"], "shape": top["shape"], "coherence": top["coherence"],
                    "avoidance": top["avoidance"], "ground": top["ground"], "ts": top["ts"]},
           "recent": recent,
           "note": "shape gestures at the avoided expectation (his gloria-head-grounded); candidate lines never stored."}
    json.dump(out, open(OUT, "w"), indent=2)
    log(f"accumulated pressure {accumulated} over {len(recent)} turns -> {OUT}")

if __name__ == "__main__":
    main()
