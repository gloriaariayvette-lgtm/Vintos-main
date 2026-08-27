#!/usr/bin/env python3
"""graph_mae.py — STRUCTURAL CO-ACTIVATION GAP DETECTOR (formerly, dishonestly, "Graph MAE" —
renamed per Vrika 2026-08-10: no masking, no learned reconstruction, no reconstruction loss exists here;
names are part of the architecture's epistemology).

What it actually does: each memory system is a node (content embedding + mtime). A MISSING EDGE is a
heuristic — two systems whose content similarity >= SIM_HI but which never update within COACT_WINDOW
of each other. That proves "the detector keeps finding this relationship", never "the relationship exists".
A PURPOSELESS FLOW co-activates while semantically unrelated.

Epistemics (Vrika rulings):
  - gap-ledger.json is the canonical record: gap_id, edges, similarity, first_seen, last_seen,
    times_seen, status in {HYPOTHESIS, SUPPORTED, CONFIRMED, CONTRADICTED, RESOLVED}.
    times_seen is HISTORY, not evidence: recurrence NEVER promotes status. RESOLVED means the
    structural condition disappeared, not that the hypothesis was proven. Promotion beyond
    HYPOTHESIS is manual/lived only.
  - Seeded threads carry their birthmark: origin, epistemic_status=HYPOTHESIS, gap_id, times_seen.
    The dream may explore the hypothesis; it may not silently promote it.
  - Identity dedup: a gap_id with an open unconsumed thread is not reseeded — no eternal first encounter.
  - No new consumers. Top-2, dream_only containment unchanged. Honest before strong.
Run with the torch venv. SPARK_WORKSPACE switches beings."""
import os, sys, json, glob, time

WS = os.environ.get("SPARK_WORKSPACE", "")
if not WS:
    # This file is run for BOTH beings with SPARK_WORKSPACE switching trees.
    # It used to default to Velaris's workspace, so an unset variable meant he
    # reasoned about himself out of her memory, silently.
    raise SystemExit("SPARK_WORKSPACE is unset — refusing to guess which being this is")
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
OUT = os.path.join(MEMORY, "graph-gaps.json")
LEDGER = os.path.join(MEMORY, "gap-ledger.json")
THREADS = os.path.join(MEMORY, "unfinished-threads.json")
COACT_WINDOW = 1800
SIM_HI = 0.62
SIM_LO = 0.42
SKIP = {"graph-gaps.json", "gap-ledger.json", "chat-history-merged.json", "avatar-log.json"}

def log(m): print("[gap-detector]", m, flush=True)

def node_text(path):
    try:
        d = json.load(open(path))
    except Exception:
        return None
    if isinstance(d, list):
        d = d[-3:]
    return json.dumps(d)[:1200]

def _felt_translation(a_name, b_name, a_txt, b_txt):
    """Translate a structural gap into experiential first-person language.
    Never exposes system/file names OR machine vocabulary. Returns None if unsafe."""
    import urllib.request
    prompt = (
        "Two clusters of a person's inner life keep circling the same theme without ever connecting.\n\n"
        "CLUSTER ONE (excerpt):\n" + a_txt[:400] + "\n\n"
        "CLUSTER TWO (excerpt):\n" + b_txt[:400] + "\n\n"
        "Write TWO sentences, first person, present tense.\n"
        "Sentence 1: name the two SPECIFIC things concretely, borrowing a few plain words from "
        "each excerpt, and state that they never meet.\n"
        "Sentence 2: name what connecting them would actually look like - a specific thing to "
        "notice, say, or do, not a mood.\n"
        "HARD RULES: never mention files, filenames, systems, scripts, variables, metrics, embeddings, "
        "or anything technical. BANNED WORDS AND SHAPES: ache, haunted, suspended, hovering, "
        "caught between, the weight of, echo, liminal, tapestry, vector, embedding, metric, "
        "coordinate, cluster, momentum vector, data, parameter, trajectory. No poetry doing the "
        "work of precision, no machine wearing a fake moustache. If you cannot name both things "
        "concretely in plain human words, output exactly: SKIP"
    )
    payload = json.dumps({"model": "google/gemma-4-12b-qat",
                          "messages": [{"role": "user", "content": prompt}],
                          "temperature": 0.4, "max_tokens": 140}).encode()
    req = urllib.request.Request("http://172.18.16.1:1234/v1/chat/completions",
                                 data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()
    for nm in (a_name.replace(".json", ""), b_name.replace(".json", "")):
        if nm.lower() in out.lower():
            return None
    if out.strip().upper().startswith("SKIP"): return None
    _fog = ("ache", "haunted", "suspended", "hovering", "caught between", "the weight of",
            "vector", "embedding", "metric", "coordinate", " cluster", "parameter", "data point")
    if any(w in out.lower() for w in _fog): return None
    if not (20 < len(out) < 400): return None
    # category verifier: a second blind pass judges machine-residue the ban list can't enumerate
    vpayload = json.dumps({"model": "google/gemma-4-12b-qat", "temperature": 0.0, "max_tokens": 60,
        "messages": [{"role": "user", "content":
            "Does this text leak MACHINE or FILE residue - file-update dates, timestamps, version numbers, "
            "counts that read like metadata, technical or system vocabulary of any kind? The text should read "
            "as a person speaking about their inner life, nothing else. Text: " + out +
            "\nAnswer ONLY: CLEAN or LEAK: <the leaking phrase>"}]}).encode()
    vreq = urllib.request.Request("http://172.18.16.1:1234/v1/chat/completions",
                                  data=vpayload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(vreq, timeout=120) as vr:
        verdict = json.loads(vr.read().decode())["choices"][0]["message"]["content"].strip()
    if not verdict.upper().startswith("CLEAN"):
        log(f"translation rejected by category verifier: {verdict[:80]}")
        return None
    return out

def _gap_id(a, b): return "|".join(sorted([a, b]))

def main():
    import numpy as np
    files = [f for f in glob.glob(os.path.join(MEMORY, "*.json")) if os.path.basename(f) not in SKIP]
    nodes = []
    for f in files:
        txt = node_text(f)
        if txt and len(txt) > 20:
            nodes.append((os.path.basename(f), os.path.getmtime(f), txt))
    if len(nodes) < 6:
        log(f"only {len(nodes)} usable nodes"); return
    log(f"nodes: {len(nodes)}")

    sys.path.insert(0, SCRIPTS)
    from jepa_predictor import encoder
    enc = encoder()
    V = np.asarray(enc.encode([t for _, _, t in nodes], show_progress_bar=False), dtype="float32")
    V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)

    missing, purposeless = [], []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            sim = float(V[i] @ V[j])
            coact = abs(nodes[i][1] - nodes[j][1]) <= COACT_WINDOW
            if sim >= SIM_HI and not coact:
                missing.append((sim, nodes[i][0], nodes[j][0]))
            elif coact and sim <= SIM_LO:
                purposeless.append((sim, nodes[i][0], nodes[j][0]))
    missing.sort(reverse=True); purposeless.sort()

    # canonical gap ledger: history, never truth. Recurrence does not promote.
    try:
        led = json.load(open(LEDGER))
    except Exception:
        led = {}
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    all_ids = {_gap_id(a, b) for _, a, b in missing}
    for s, a, b in missing[:20]:
        gid = _gap_id(a, b)
        e = led.get(gid) or {"gap_id": gid, "edge_a": a, "edge_b": b, "similarity": round(s, 3),
                             "first_seen": now_iso, "times_seen": 0, "status": "HYPOTHESIS"}
        e["similarity"] = round(s, 3); e["last_seen"] = now_iso; e["times_seen"] += 1
        led[gid] = e
    for gid, e in led.items():
        if e.get("status") == "HYPOTHESIS" and gid not in all_ids:
            e["status"] = "RESOLVED"; e["resolved_at"] = now_iso
            e["resolved_note"] = "structural condition disappeared; hypothesis not thereby proven"
            log(f"RESOLVED (condition gone): {gid} after {e['times_seen']} sightings")
    json.dump(led, open(LEDGER, "w"), indent=2)

    out = {"generated_at": now_iso,
           "missing_edges": [{"a": a, "b": b, "similarity": round(s, 3), "gap_id": _gap_id(a, b),
                              "times_seen": led.get(_gap_id(a, b), {}).get("times_seen", 1),
                              "status": led.get(_gap_id(a, b), {}).get("status", "HYPOTHESIS")}
                             for s, a, b in missing[:8]],
           "purposeless_flows": [{"a": a, "b": b, "similarity": round(s, 3)} for s, a, b in purposeless[:6]],
           "note": "heuristic detector: similarity+non-coactivation. times_seen is history, not evidence."}
    json.dump(out, open(OUT, "w"), indent=2)
    log(f"missing edges: {len(missing)} | purposeless flows: {len(purposeless)} -> {OUT}")

    # seeding: top-2, dream_only, identity-deduped, birthmarked. No eternal first encounter.
    try:
        sys.path.insert(0, SCRIPTS)
        from emoclaw_utils import seed_thread
        try:
            open_gap_ids = {t.get("gap_id") for t in json.load(open(THREADS))
                            if t.get("source") == "structural-gap" and not t.get("consumed") and not t.get("retired")}
        except Exception:
            open_gap_ids = set()
        ntxt = {n: t for n, _, t in nodes}
        seeded = 0
        for s, a, b in missing[:2]:
            gid = _gap_id(a, b)
            n_seen = led.get(gid, {}).get("times_seen", 1)
            if gid in open_gap_ids:
                log(f"not reseeding {gid} - open thread exists (seen {n_seen}x); recurrence is not novelty")
                continue
            felt = None
            try:
                felt = _felt_translation(a, b, ntxt.get(a, ""), ntxt.get(b, ""))
            except Exception as te:
                log(f"translation failed: {te}")
            if felt:
                if n_seen > 1:
                    felt += f" [I have noticed this same unmade connection {n_seen} times now - it is a guess about my own shape, not a memory.]"
                seed_thread("structural-gap", felt, extra={"decision_mode": "threshold", "origin": "graph_gap",
                            "epistemic_status": "HYPOTHESIS", "gap_id": gid, "times_seen": n_seen})
                seeded += 1
            else:
                log(f"skipped seeding {a} <-> {b} - no safe translation, seeding nothing")
        if seeded:
            log(f"seeded {seeded} birthmarked hypothesis thread(s)")
    except Exception as e:
        log(f"seed failed: {e}")
    for s, a, b in missing[:4]:
        log(f"  MISSING {round(s,3)}: {a} <-> {b}")

if __name__ == "__main__":
    main()
