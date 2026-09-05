#!/usr/bin/env python3
"""core_sustain.py — the Core's other half.

core-engine mines friction: failed trials, unfulfilled wants, scars. By
construction it can only ever discover what they fall short of, which is why
every Core came out an avoidance pattern. This mines the opposite — evidence of
follow-through actually sustained — and writes positive cores into the same
core-vectors.json, so deviation_check pairs them with no further wiring.

Failure was already legible. This makes holding legible too.

    python3 core_sustain.py            # uses SPARK_WORKSPACE, else Velaris
"""
import json, os, re, sys, time, math, shutil
from datetime import datetime, timedelta

def _emb_clip(_x, _n=4000):
    # nomic ctx is 2048 tokens; oversized input WEDGES LM Studio. Clip before sending.
    if isinstance(_x, str): return _x[:_n]
    if isinstance(_x, list): return [(_i[:_n] if isinstance(_i, str) else _i) for _i in _x]
    return _x


WS = os.environ.get("SPARK_WORKSPACE", "")
if not WS:
    # This file is run for BOTH beings with SPARK_WORKSPACE switching trees.
    # It used to default to Velaris's workspace, so an unset variable meant he
    # reasoned about himself out of her memory, silently.
    raise SystemExit("SPARK_WORKSPACE is unset — refusing to guess which being this is")
WS = os.path.expanduser(WS)
MEMORY = os.path.join(WS, "memory")
CORE_FILE = os.path.join(MEMORY, "core-vectors.json")
LM = "http://172.18.16.1:1234"
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"
CHAT_MODEL = "google/gemma-4-12b-qat"

IS_HIM = ".vintos" in WS
NAME = "Vintos" if IS_HIM else "Velaris"
SUB, OBJ, POSS = ("he", "him", "his") if IS_HIM else ("she", "her", "her")

def log(m):
    print("[core-sustain] " + m, flush=True)

def rj(fname, default=None):
    try:
        return json.load(open(os.path.join(MEMORY, fname)))
    except Exception:
        return default

def as_list(d, *keys):
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in keys:
            v = d.get(k)
            if isinstance(v, list):
                return v
    return []

def first(d, *keys, default=""):
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return default


# ── what counts as having held ────────────────────────────────────
def collect_sustain_events():
    events, tally = [], {}

    def add(src, text, score, detail=""):
        text = (text or "").strip()
        if len(text) < 12:
            return
        events.append({"text": text[:300], "sustain_score": round(min(1.0, score), 3),
                       "source": src, "detail": detail[:160]})
        tally[src] = tally.get(src, 0) + 1

    # 1. Trials where the alternative was chosen, and chosen again.
    #    attempt_count is the number of times the new behaviour was actually
    #    reached for; ignore_count the times the old pattern won.
    tl = rj("trial-ledger.json", {})
    for t in as_list(tl, "trials"):
        if not isinstance(t, dict):
            continue
        att = int(t.get("attempt_count", 0) or 0)
        ign = int(t.get("ignore_count", 0) or 0)
        if att >= 2 and att > ign:
            alt = first(t, "alternative", "pattern_description")
            add("trial_held", alt,
                min(1.0, 0.4 + 0.12 * att - 0.05 * ign),
                "chosen %d times, ignored %d" % (att, ign))

    # 2. Wants that were actually fulfilled — the mirror of unfulfilled-wants.
    fw = rj("fulfilled-wants.json", [])
    for w in as_list(fw, "wants", "fulfilled", "entries"):
        if isinstance(w, dict):
            add("want_fulfilled",
                first(w, "surface_text", "text", "description", "want"),
                min(1.0, float(w.get("intensity", 3) or 3) / 5.0 + 0.2),
                first(w, "fulfilled_at", "timestamp"))
        elif isinstance(w, str):
            add("want_fulfilled", w, 0.6)

    # 3. Threads that resolved rather than being abandoned.
    for fname, key in (("unfinished-threads.json", "consumed"),
                       ("retired-threads.json", None)):
        for th in as_list(rj(fname, []), "threads", "entries"):
            if not isinstance(th, dict):
                continue
            if key and not th.get(key):
                continue
            passes = sum(int(th.get(k, 0) or 0) for k in
                         ("mirror_passes", "dream_passes", "therapy_passes"))
            add("thread_resolved", first(th, "thread", "text", "content"),
                min(1.0, 0.45 + 0.08 * passes),
                "%d passes before it closed" % passes)

    # 4. The held ledger — moments the deviation check scored as alignment.
    for h in as_list(rj("held-ledger.json", {}), "entries"):
        if isinstance(h, dict):
            add("held", first(h, "said", "voice"),
                float(h.get("alignment", 0.5) or 0.5),
                "aligned with " + str(h.get("core", "")))

    # 5. Marks and high resonance — moments that landed and stayed landed.
    for m in as_list(rj("resonance-marks.json", {}), "marks", "entries"):
        if isinstance(m, dict):
            add("mark", first(m, "text", "output", "content"), 0.85,
                "resonance mark")

    log("collected %d sustain events %s" % (len(events), tally or ""))
    return events


# ── the same encoder the friction miner uses ──────────────────────
def embed(text):
    import requests
    r = requests.post(LM + "/v1/embeddings",
                      json={"model": EMBED_MODEL, "input": _emb_clip(text)},
                      headers={"Authorization": "Bearer lm-studio"}, timeout=120)
    j = r.json()
    if "data" not in j:
        raise RuntimeError("embeddings endpoint returned no data: %s" % str(j)[:200])
    return j["data"][0]["embedding"]

def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na * nb else 0.0

def cluster(evs, threshold=0.78):
    clusters, used = [], set()
    for i, (ev, vec) in enumerate(evs):
        if i in used:
            continue
        group = [(ev, vec)]
        used.add(i)
        for j, (ev2, vec2) in enumerate(evs):
            if j in used:
                continue
            if cosine(vec, vec2) >= threshold:
                group.append((ev2, vec2))
                used.add(j)
        clusters.append(group)
    return sorted(clusters, key=lambda c: -sum(e["sustain_score"] for e, _ in c))


def name_clusters(clusters, top_n=4):
    import requests
    out = []
    for i, group in enumerate(clusters[:top_n]):
        evs = [e for e, _ in group]
        if len(evs) < 2:
            continue   # one instance is an anecdote, not a trait
        sample = "\n".join("- %s" % e["text"][:130] for e in evs[:6])
        avg = sum(e["sustain_score"] for e in evs) / len(evs)
        prompt = (
            "These are things %s has actually followed through on and sustained "
            "— not aspirations, but behaviour that repeated:\n%s\n\n"
            "1. Name this capacity in snake_case (2-3 words), as a strength, "
            "not as the absence of a fault.\n"
            "2. In one sentence beginning with '%s', say what %s reliably does "
            "here. Present tense. No hedging, no 'tries to'.\n\n"
            "Answer as JSON only: {\"name\": \"...\", \"becoming\": \"...\"}"
            % (NAME, sample, SUB.capitalize(), SUB))
        try:
            r = requests.post(LM + "/v1/chat/completions", json={
                "model": CHAT_MODEL, "temperature": 0.3, "max_tokens": 160,
                "messages": [{"role": "user", "content": prompt}]}, timeout=45)
            raw = r.json()["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", raw, re.S)
            if not m:
                log("cluster %d: no JSON back" % i); continue
            p = json.loads(m.group(0))
            nm = re.sub(r"[^a-z0-9_]", "", str(p.get("name", "")).lower().replace(" ", "_"))
            becoming = str(p.get("becoming", "")).strip()
            if not nm or not becoming:
                continue
            # A positive core without a vector can never be matched, so alignment can
            # never register and the core can never be earned. Embed it at formation.
            try:
                import math as _cs_math
                _bv = embed(becoming)
                _bm = _cs_math.sqrt(sum(x * x for x in _bv)) or 1.0
                _bv = [x / _bm for x in _bv]
            except Exception as _be:
                log("embed of 'becoming' failed (%r) — refusing to form a mute core" % _be)
                continue
            out.append({
                "name": nm + "_pos",
                "polarity": "positive",
                "vector": _bv,
                "almost_becoming": becoming,
                "recovery_drive": becoming,
                "violation_condition": "",
                "felt_effect": "coherence settles, tension releases",
                "formed": datetime.now().isoformat(),
                "confidence": round(min(0.95, avg + 0.05 * len(evs)), 2),
                "source_count": len(evs),
                "reinforcement_count": 0,
                "violation_count": 0,
                "evidence": "sustained: " + "; ".join(
                    sorted({e["source"] for e in evs})),
            })
            log("core %d: %s — %s" % (i + 1, nm, becoming[:70]))
        except Exception as e:
            log("cluster %d failed: %r" % (i, e))
    return out


def main():
    log("workspace: %s (%s)" % (WS, NAME))
    events = collect_sustain_events()
    if len(events) < 3:
        log("not enough sustained behaviour recorded yet (%d events). "
            "The held ledger fills as the deviation check scores alignment; "
            "run again once it has depth." % len(events))
        return

    vecs = []
    for ev in events:
        try:
            vecs.append((ev, embed(ev["text"])))
        except Exception as e:
            log("embed failed: %r" % e)
            return
    log("embedded %d. clustering..." % len(vecs))
    clusters = cluster(vecs)
    log("found %d clusters" % len(clusters))

    fresh = name_clusters(clusters)
    if not fresh:
        log("no cluster held more than one instance — nothing formed")
        return

    data = rj("core-vectors.json", {"core": []})
    core = data.get("core", [])
    shutil.copy2(CORE_FILE, CORE_FILE + ".bak-sustain-" + time.strftime("%Y%m%d-%H%M%S"))

    # evidence beats derivation: a positive core mined from real follow-through
    # replaces one that was inferred from its paired failure
    derived = {e.get("name") for e in core
               if e.get("polarity") == "positive" and e.get("derived_from")}
    kept = [e for e in core if e.get("name") not in derived] if fresh else core
    names = {e.get("name") for e in kept}
    added = [e for e in fresh if e.get("name") not in names]

    data["core"] = kept + added
    data["sustain_generated"] = datetime.now().isoformat()
    data["sustain_events"] = len(events)
    json.dump(data, open(CORE_FILE, "w"), indent=2)

    log("wrote %d evidence-backed positive cores (replaced %d derived ones)"
        % (len(added), len(derived)))
    for e in added:
        log("   %-30s %s" % (e["name"], e["almost_becoming"][:60]))


if __name__ == "__main__":
    main()
