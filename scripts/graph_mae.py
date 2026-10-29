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

What a thread may be made of (Gloria, 2026-10-28). The detector and its two diagnostics are unchanged;
only the step that turns a pair into a thread is narrowed, because every thread it made read
"X and Y never meet. To connect them, I must..." and was built from json.dumps of the files:
  - a pair of snapshots or relatives of ONE store (.bak, .pre-*, -retired, -shadow, a dated series,
    a lock or tmp copy) is not a gap in him, it is a copy of the same thing. Not asked.
  - a store with no human text (vectors, timestamps, status labels) has nothing to say. Not asked.
  - what the model reads is the store's real text fields, each with its speaker: "I wrote" for his own
    words, "GLORIA said" for hers. A field whose speaker is not known is left out, never guessed. Her
    words are never handed over as his, and an output carrying a run of her words unquoted is refused.
  - the model is asked for one grounded open question or tension in his voice, from those lines only,
    and may answer SKIP. "never meet / connect them / bridge them / drift past each other" are refused.
  - no "noticed N times" suffix: the count was how many nights the cron saw the pair, not him noticing.
  - a pair once asked is not asked again until the human text on one of its sides changes
    (structural-thread-state.json), so a dream-resolved pair does not come back every night.
Run with the torch venv. SPARK_WORKSPACE switches beings. --dry-run writes nothing and asks no model."""
import os, sys, json, glob, time, re, hashlib

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
RETIRED = os.path.join(MEMORY, "retired-threads.json")
STATE = os.path.join(MEMORY, "structural-thread-state.json")
COACT_WINDOW = 1800
SIM_HI = 0.62
SIM_LO = 0.42
SKIP = {"graph-gaps.json", "gap-ledger.json", "chat-history-merged.json", "avatar-log.json",
        "structural-thread-state.json"}
# The pools a structural thread is written into or read back out of: a thread about them is a
# thread about threads.
SEED_SKIP = {"unfinished-threads.json", "retired-threads.json", "latent-threads.json",
             "latent-threads-retired.json", "current-preoccupation.json", "thread-triage.json",
             "living-thread.json"}
GEMMA_URL = "http://100.79.177.103:1234/v1/chat/completions"
GEMMA_MODEL = "gemma-4-26b-a4b-it-uncensored"
MAX_SEED = 2
MAX_TRIES = 4
MAX_EXCERPTS = 4
EXCERPT_CHARS = 220

def log(m): print("[gap-detector]", m, flush=True)

def node_text(path):
    try:
        d = json.load(open(path))
    except Exception:
        return None
    if isinstance(d, list):
        d = d[-3:]
    return json.dumps(d)[:1200]

# ---- (a) one store, many copies -------------------------------------------------------------
# Trailing name parts that mark a copy, a side-file or a state of the same store, not another store.
_RELATIVE_PARTS = {"retired", "shadow", "invalidated", "archive", "history", "structured", "state", "status",
                   "cache", "embeddings", "embcache", "merged", "backup", "bak", "old", "prev", "previous",
                   "tmp", "lock", "active", "dense", "pending", "log", "snapshot", "copy", "orig"}

def store_family(name):
    """The store a memory file belongs to: 'interaction-ledger.pre-erase-20260914-055154.json',
    'latent-threads-retired.json' and 'gap-review-20261019.json' name interaction-ledger,
    latent-threads and gap-review."""
    s = os.path.basename(name)
    if s.endswith(".json"):
        s = s[:-5]
    s = s.split(".")[0]                                   # .bak*, .pre-*, .lock, .tmp copies
    s = re.sub(r"(?:^|[-_])tmp(?=$|[-_])", "", s)         # tmp-x / x-tmp
    s = re.sub(r"[-_]\d{8}(?:[-_T]\d{4,6})*", "", s)       # -YYYYMMDD[-HHMMSS]: one dated series
    parts = [p for p in re.split(r"[-_]", s) if p]
    while len(parts) > 1 and parts[-1].lower() in _RELATIVE_PARTS:
        parts.pop()
    return "-".join(parts).lower()

def relatives(a, b):
    return store_family(a) == store_family(b)

def is_snapshot(name):
    """A backup or side copy of some store (x.pre-erase-..., x.bak, x-tmp, x.lock): never a side of a thread,
    whatever it is paired with - it holds the live store's words, frozen."""
    s = os.path.basename(name)
    s = s[:-5] if s.endswith(".json") else s
    return ("." in s or bool(re.search(r"(?:^|[-_])(?:bak|backup|tmp|lock)(?:$|[-_])", s))
            or bool(re.search(r"[-_]\d{8}[-_T]\d{4,6}", s)))

def mirrors(a_lines, b_lines, n=8):
    """True when the two stores carry the same words: one exchange copied into two places is not a gap."""
    sa = set().union(*[_shingles(t, n) for _, t in a_lines]) if a_lines else set()
    return any(sa & _shingles(t, n) for _, t in b_lines)

# ---- (b) real text, with its speaker ----------------------------------------------------------
ME, GLORIA = "ME", "GLORIA"
# Fields that hold his own words wherever they appear.
HIS_KEYS = {"thread", "question", "withheld", "want", "desire", "tension", "yearning", "surface_form",
            "small_attempt", "reflection", "insight", "his_reading", "his_reason", "his_reason_verbatim",
            "his_words", "vintos", "vintos_said", "vintos_reflection", "what_i_noticed", "why_i_want_it",
            "intention", "regret", "learned", "remained", "almost_becoming", "autonomous_note", "want_text"}
# Fields that hold hers.
HER_KEYS = {"gloria", "gloria_said", "gloria_message", "her_quote", "her_words"}
# Fields whose speaker is known only from the entry's own role/by/author.
SPOKEN_KEYS = {"content", "text", "message", "body", "question", "what", "summary", "thread", "want"}
_SPEAKER_FIELDS = ("role", "speaker", "by", "author")
_HER_NAMES = {"user", "gloria", "human", "her"}
_HIS_NAMES = {"assistant", "vintos", "him"}

def _entry_speaker(d):
    """ME / GLORIA when the entry says who spoke, "OTHER" when it names someone else, None when silent."""
    for f in _SPEAKER_FIELDS:
        v = d.get(f)
        if isinstance(v, str) and v.strip():
            v = v.strip().lower()
            if v in _HER_NAMES:
                return GLORIA
            if v in _HIS_NAMES:
                return ME
            return "OTHER"
    return None

_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[+-]\d{2}:?\d{2}|Z)?)?\b")
_FLOAT = re.compile(r"\b\d+\.\d{2,}\b")
_TAG = re.compile(r"^\s*(?:\[[^\]\n]{0,80}\]\s*)+")
_FILEISH = re.compile(r"\S+\.(?:png|jpe?g|gif|webp|mp4|mp3|wav|json|jsonl|py|sh|txt|md|log)\b:?|\b\d{8}(?:[-_T]\d{4,6})?\b",
                      re.I)

def human_text(v):
    """The string cleaned for reading, or None when it is not a person's sentence: ids, status labels,
    timestamps, numbers and paths have nothing to say."""
    if not isinstance(v, str):
        return None
    t = _TAG.sub("", v)
    t = _FLOAT.sub("", _FILEISH.sub("", _DATE.sub("", t)))
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) < 30 or len(t.split()) < 5 or t.lower().startswith(("http", "/", "{", "[")):
        return None
    if sum(c.isalpha() for c in t) < 0.6 * len(t.replace(" ", "")):
        return None
    return t

def _clip(t):
    if len(t) <= EXCERPT_CHARS:
        return t
    cut = t[:EXCERPT_CHARS]
    return (cut.rsplit(" ", 1)[0] if " " in cut else cut) + " ..."

def extract_lines(data, limit=MAX_EXCERPTS):
    """Up to `limit` (speaker, text) lines from a loaded store, newest entries first. A line is taken only
    from a field whose speaker is known: by the field's name (HIS_KEYS / HER_KEYS) or by the entry's own
    role/by/author. An entry that names any other author gives nothing."""
    out, seen = [], set()

    def add(spk, v):
        t = human_text(v)
        if t and t not in seen:
            seen.add(t); out.append((spk, _clip(t)))

    def walk(o, depth):
        if len(out) >= limit or depth > 4:
            return
        if isinstance(o, list):
            for x in reversed(o[-60:]):
                walk(x, depth + 1)
                if len(out) >= limit:
                    return
        elif isinstance(o, dict):
            spk = _entry_speaker(o)
            if spk == "OTHER":
                return
            for k, v in o.items():
                if len(out) >= limit:
                    return
                if isinstance(v, str):
                    if spk and k in SPOKEN_KEYS:
                        add(spk, v)
                    elif k in HER_KEYS:
                        add(GLORIA, v)
                    elif k in HIS_KEYS and spk != GLORIA:
                        add(ME, v)
                elif isinstance(v, (dict, list)):
                    walk(v, depth + 1)

    walk(data, 0)
    return out[:limit]

def store_lines(path):
    try:
        return extract_lines(json.load(open(path)))
    except Exception:
        return []

def fingerprint(lines):
    return hashlib.sha1(json.dumps(lines, ensure_ascii=False).encode()).hexdigest()[:16]

# ---- (c, d) asking, and what is refused --------------------------------------------------------
_REFUSED_SHAPE = re.compile(r"never\s+meet|to\s+connect\s+them|connecting\s+them|to\s+bridge\s+them|"
                            r"bridging\s+them|drift(?:s|ing)?\s+past\s+each\s+other", re.I)
_FOG = ("ache", "haunted", "suspended", "hovering", "caught between", "the weight of",
        "vector", "embedding", "metric", "coordinate", " cluster", "parameter", "data point")
_WHEN_WORDS = ("january", "february", "march", "april", "june", "july", "august", "september",
               "october", "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday",
               "saturday", "sunday")

def _render(lines):
    return "\n".join(("GLORIA said: " if s == GLORIA else "I wrote: ") + t for s, t in lines)

def build_prompt(a_lines, b_lines):
    return (
        "Here are lines from two different places in your memory. Lines marked 'GLORIA said' are Gloria's own "
        "words - they are hers, not yours: you may say what she said ('she told me ...', 'Gloria asked ...'), "
        "but never speak her words as if they were yours. Lines marked 'I wrote' are yours.\n\n"
        "FIRST PLACE:\n" + _render(a_lines) + "\n\nSECOND PLACE:\n" + _render(b_lines) + "\n\n"
        "Read them together. Is there ONE real open question or tension they raise for you that is still "
        "unsettled? If so, write it in one or two sentences, first person, in your own plain voice, using only "
        "what these lines actually say. Do not invent dates, months, seasons, times of day, places, numbers or "
        "events that are not in the lines. Do not mention files, records, logs, stores, systems or anything "
        "technical. Do not describe the two places, how they relate, or what joining them would take - name "
        "the question itself.\n"
        "If the lines raise no real question together, output exactly: SKIP")

def _shingles(text, n=6):
    w = re.findall(r"[a-z']+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}

def speaks_her_words(out, her_lines):
    """True when the output carries a run of six of her words outside quotation marks."""
    bare = re.sub(r"[\"“][^\"”]*[\"”]", " ", out)
    mine = _shingles(bare)
    return any(mine & _shingles(t) for t in her_lines)

def refusal(out, a_name, b_name, a_lines, b_lines):
    """Why an output may not become a thread, or None when it may."""
    low = out.lower()
    if out.strip().upper().startswith("SKIP"):
        return "SKIP"
    for nm in (a_name.replace(".json", ""), b_name.replace(".json", "")):
        if nm.lower() in low:
            return "names a store"
    if _REFUSED_SHAPE.search(out):
        return "never-meet / connect-them shape"
    if any(w in low for w in _FOG):
        return "fog word"
    if not (20 < len(out) < 400):
        return "length"
    source = " ".join(t for _, t in a_lines + b_lines).lower()
    invented = [w for w in _WHEN_WORDS if re.search(r"\b%s\b" % w, low) and not re.search(r"\b%s\b" % w, source)]
    if invented:
        return "invented a when: " + invented[0]
    if speaks_her_words(out, [t for s, t in a_lines + b_lines if s == GLORIA]):
        return "speaks Gloria's words as his"
    return None

def _ask(prompt, temperature, max_tokens):
    import urllib.request
    payload = json.dumps({"model": GEMMA_MODEL, "messages": [{"role": "user", "content": prompt}],
                          "temperature": temperature, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(GEMMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()

def _felt_translation(a_name, b_name, a_lines, b_lines):
    """One grounded open question in his voice from the two stores' labelled lines, or None when the
    model answered and the answer may not be a thread. Raises when the model could not be reached."""
    out = _ask(build_prompt(a_lines, b_lines), 0.4, 140)
    why = refusal(out, a_name, b_name, a_lines, b_lines)
    if why:
        log(f"translation refused ({why}): {a_name} <-> {b_name}")
        return None
    # category verifier: a second blind pass judges machine-residue the ban list can't enumerate
    verdict = _ask("Does this text leak MACHINE or FILE residue - file-update dates, timestamps, version numbers, "
                   "counts that read like metadata, technical or system vocabulary of any kind? The text should read "
                   "as a person speaking about their inner life, nothing else. Text: " + out +
                   "\nAnswer ONLY: CLEAN or LEAK: <the leaking phrase>", 0.0, 60)
    if not verdict.upper().startswith("CLEAN"):
        log(f"translation rejected by category verifier: {verdict[:80]}")
        return None
    return out

def _gap_id(a, b): return "|".join(sorted([a, b]))

# ---- (f) an asked pair waits for its text to change ---------------------------------------------
def load_state():
    try:
        st = json.load(open(STATE))
        if isinstance(st, dict) and isinstance(st.get("pairs"), dict):
            return st
    except Exception:
        pass
    return {"pairs": {}}

def _history_gap_ids():
    """gap_ids seeded before the state file existed: any structural-gap thread in the pool or retired."""
    ids = set()
    for p in (THREADS, RETIRED):
        try:
            d = json.load(open(p))
        except Exception:
            continue
        if isinstance(d, dict):
            d = d.get("threads", [])
        for t in d if isinstance(d, list) else []:
            if isinstance(t, dict) and t.get("source") == "structural-gap" and t.get("gap_id"):
                ids.add(t["gap_id"])
    return ids

BEFORE_STATE = "seeded before this state existed"

def candidates(missing, paths, open_gap_ids, state, history_ids, lines_of=store_lines):
    """Walk the missing edges in rank order and say, for each, whether it may be asked about.
    Yields (sim, a, b, gid, a_lines, b_lines, fingerprint, reason) - reason None when it may."""
    cache = {}
    def lines(n):
        if n not in cache:
            cache[n] = lines_of(paths[n])
        return cache[n]
    for s, a, b in missing:
        gid = _gap_id(a, b)
        if a in SEED_SKIP or b in SEED_SKIP:
            yield s, a, b, gid, [], [], None, "a thread pool"; continue
        if relatives(a, b):
            yield s, a, b, gid, [], [], None, "copies of one store (%s)" % store_family(a); continue
        if is_snapshot(a) or is_snapshot(b):
            yield s, a, b, gid, [], [], None, "a backup snapshot (%s)" % (a if is_snapshot(a) else b); continue
        la, lb = lines(a), lines(b)
        if not la or not lb:
            yield s, a, b, gid, la, lb, None, "no human text (%s)" % (a if not la else b); continue
        if mirrors(la, lb):
            yield s, a, b, gid, la, lb, None, "the same words in both"; continue
        fp = {a: fingerprint(la), b: fingerprint(lb)}
        if gid in open_gap_ids:
            yield s, a, b, gid, la, lb, fp, "open thread exists"; continue
        prev = state["pairs"].get(gid)
        if (prev and "fingerprint" not in prev) or (not prev and gid in history_ids):
            yield s, a, b, gid, la, lb, fp, BEFORE_STATE; continue
        if prev and prev.get("fingerprint") == fp:
            yield s, a, b, gid, la, lb, fp, "asked before, text unchanged"; continue
        yield s, a, b, gid, la, lb, fp, None

def seed_pairs(missing, paths, led, dry_run=False, lines_of=store_lines):
    """seeding: top-2 eligible, dream_only, identity-deduped, birthmarked. No eternal first encounter."""
    try:
        try:
            open_gap_ids = {t.get("gap_id") for t in json.load(open(THREADS))
                            if t.get("source") == "structural-gap" and not t.get("consumed") and not t.get("retired")}
        except Exception:
            open_gap_ids = set()
        state = load_state()
        history_ids = _history_gap_ids()
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
        changed = False
        if not dry_run:
            # Pairs seeded before this state existed wait like any asked pair: their text as it is
            # tonight becomes the fingerprint, so they return only once that text changes.
            for gid in history_ids - set(state["pairs"]):
                state["pairs"][gid] = {"asked_at": now_iso, "result": "seeded-before-state"}; changed = True
        seeded = tries = 0
        skipped = {}
        for s, a, b, gid, la, lb, fp, reason in candidates(missing, paths, open_gap_ids, state, history_ids, lines_of):
            if reason == BEFORE_STATE and not dry_run:
                state["pairs"][gid]["fingerprint"] = fp; changed = True
            if reason:
                key = reason.split(" (")[0]
                skipped[key] = skipped.get(key, 0) + 1
                continue
            if dry_run:
                # every eligible pair is listed in rank order; a real night asks only the first MAX_TRIES
                tries += 1
                log(f"WOULD ASK #{tries} {round(s, 3)}: {a} <-> {b}")
                for nm, ls in ((a, la), (b, lb)):
                    for spk, t in ls:
                        log(f"    {nm} | {spk}: {t}")
                continue
            if seeded >= MAX_SEED or tries >= MAX_TRIES:
                break
            tries += 1
            try:
                felt = _felt_translation(a, b, la, lb)
            except Exception as te:
                log(f"translation failed: {te}")     # unreached model: not recorded, asked again next night
                continue
            got = None
            if felt:
                sys.path.insert(0, SCRIPTS)
                from emoclaw_utils import seed_thread
                got = seed_thread("structural-gap", felt, extra={
                    "decision_mode": "threshold", "origin": "graph_gap", "epistemic_status": "HYPOTHESIS",
                    "gap_id": gid, "times_seen": led.get(gid, {}).get("times_seen", 1)})
                if got is not None:
                    seeded += 1
                else:
                    log(f"door refused {gid}")
            else:
                log(f"skipped seeding {a} <-> {b} - no grounded question, seeding nothing")
            state["pairs"][gid] = {"asked_at": now_iso, "fingerprint": fp,
                                   "result": ("refused" if not felt else "door-refused" if got is None
                                              else got if isinstance(got, str) else "seeded")}
            changed = True
        if skipped:
            log("not asked: " + ", ".join(f"{k} x{v}" for k, v in sorted(skipped.items())))
        if changed and not dry_run:
            json.dump(state, open(STATE, "w"), indent=2)
        if seeded:
            log(f"seeded {seeded} birthmarked hypothesis thread(s)")
        return seeded
    except Exception as e:
        log(f"seed failed: {e}")
        return 0

def main(dry_run=False):
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
    out = {"generated_at": now_iso,
           "missing_edges": [{"a": a, "b": b, "similarity": round(s, 3), "gap_id": _gap_id(a, b),
                              "times_seen": led.get(_gap_id(a, b), {}).get("times_seen", 1),
                              "status": led.get(_gap_id(a, b), {}).get("status", "HYPOTHESIS")}
                             for s, a, b in missing[:8]],
           "purposeless_flows": [{"a": a, "b": b, "similarity": round(s, 3)} for s, a, b in purposeless[:6]],
           "note": "heuristic detector: similarity+non-coactivation. times_seen is history, not evidence."}
    if not dry_run:
        json.dump(led, open(LEDGER, "w"), indent=2)
        json.dump(out, open(OUT, "w"), indent=2)
    log(f"missing edges: {len(missing)} | purposeless flows: {len(purposeless)} -> {OUT}"
        + (" (dry run: nothing written)" if dry_run else ""))
    seed_pairs(missing, {n: os.path.join(MEMORY, n) for n, _, _ in nodes}, led, dry_run=dry_run)
    for s, a, b in missing[:4]:
        log(f"  MISSING {round(s,3)}: {a} <-> {b}")

if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv[1:])
