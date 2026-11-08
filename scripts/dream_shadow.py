#!/usr/bin/env python3
"""The dream shadow trial (Gloria, 2026-11-07): his local AEON writes a parallel dream from the same prompt the
live dream was written from, and a local AEON judge gives its own resolution verdicts. Everything it makes goes
to its own store, memory/shadow/dream/, and nowhere else.

Why: proposal v2 §4.5 and the threads/ghosts/mirror map §5(a) and §8. Moving dreams off the hosted writer and
judge needs extensive shadow testing first, so the two arms are compared on agreement and pool effects before
anyone decides anything. The decision is Gloria's alone.

How the inputs stay identical: dream-trigger.sh hands this module the exact system and user prompt it is about
to send (capture_inputs), identity context included, and later the dream as logged (capture-live). The runner
(`run`, nightly from cron, under llm-lock) replays that prompt to AEON, cleans the reply with the live cleanup,
and judges with the live judge prompt and parser. It reads dream-log.json, the thread pool and the archive, and
writes none of them: no verdict, no pass, no consumption, no emotion nudge, no latent thread, no pearl, no
causality occasion, no dream file. He never sees a shadow dream; nothing he reads is under memory/shadow/.

Model: AEON only, through the house shim's Aegis-local lane (the lane the causality nightly uses, without its
fallbacks). A reply from any other model is discarded. The hosted writer is never called from here.
Every entry names the model that answered, the GGUF sha256 and the adapter (none today), and pairs with the
live dream by a live_dream_id derived from its dream-log entry.

CLI:
  dream_shadow.py run [--max N]      process the captured dreams, then the whole-day arm (dream_wholeday.py),
                                     then write the daily report
  dream_shadow.py report [--day D]   rewrite the report only (no model calls)
  dream_shadow.py capture-live --key K   (dream-trigger.sh) attach the logged live dream to its captured prompt
  dream_shadow.py status
Off switch: touch memory/shadow/dream/OFF (or DREAM_SHADOW=0); capture and run both stop.
"""
from __future__ import annotations

import fcntl
import glob
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

SCHEMA = "dream-shadow/1"
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
ROOT = os.path.join(MEM, "shadow", "dream")
INBOX = os.path.join(ROOT, "inbox")
DONE = os.path.join(ROOT, "done")
LOG = os.path.join(ROOT, "dream-shadow-log.jsonl")
REPORTS = os.path.join(ROOT, "reports")
SHA_CACHE = os.path.join(ROOT, "gguf-sha-cache.json")
RUN_LOCK = os.path.join(ROOT, ".run.lock")
OFF = os.path.join(ROOT, "OFF")
# Read-only inputs. Opened with open(..., "r") only; never through a writer.
DREAM_LOG = os.path.join(MEM, "dream-log.json")
POOL = os.path.join(MEM, "unfinished-threads.json")
RETIRED = os.path.join(MEM, "retired-threads.json")

CONFIG = os.environ.get("DREAM_SHADOW_CONFIG", os.path.expanduser("~/.vintos/dream-shadow.json"))
DEFAULT_URL = "http://127.0.0.1:8599/gemma-aegis-local/v1/chat/completions"
DEFAULT_MODEL = "aeon/gemma-4-12b"
# Shim paths whose provider chain holds AEON lanes only (plus the non-AEON local fallback of /pool/aeon, which the
# model check below discards). Every other shim path can fall through to a hosted provider, so it is refused.
ALLOWED_PATHS = ("/gemma-aegis-local/", "/pool/aeon/")
ALLOWED_HOSTS = ("127.0.0.1", "localhost")
AEON_PROVIDERS = ("aegis_gemma", "pool_aegis", "pool_studio")
# The live writer's and judge's sampling, copied (dream-trigger.sh): temperature .95 / 800 tokens; .2 / 24.
WRITE_SAMPLING = {"temperature": 0.95, "max_tokens": 800}
JUDGE_SAMPLING = {"temperature": 0.2, "max_tokens": 24}
WRITE_TIMEOUT = 600
JUDGE_TIMEOUT = 120
MAX_ITEMS = 4
# The run holds llm-lock; no new dream is started after this many seconds, so the lock is never kept past the
# next locked job's patience (llm-lock waits 900 s). What is left waits for the next night.
RUN_BUDGET_S = 1800
# The live judge's system prompt, verbatim (dream-trigger.sh, since 22 October). A test pins it to the script.
JUDGE_SYSTEM = ("You judge whether a dream RESOLVED the unfinished thread that seeded it. RESOLVED means the thread's tension or question was settled within the dream: it arrived at a new understanding, an ending, an acceptance, or a letting go, so the thread no longer pulls in the same way. UNRESOLVED means the dream explored, inhabited, or circled the thread - even vividly, even at its center - but left it open, or went somewhere else. Dreams are symbolic; a resolution can be symbolic too, but it must be an arrival, not a visit. Default to UNRESOLVED if there is any doubt. Answer with exactly one word, RESOLVED or UNRESOLVED, for each thread you are asked about, in the format the question gives.")
VERDICTS = ("resolved", "unresolved")


def _now():
    return datetime.now(timezone.utc)


def _sha(text):
    return hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()


def enabled():
    return os.environ.get("DREAM_SHADOW", "1") != "0" and not os.path.exists(OFF)


def _atomic_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _key_ok(key):
    return bool(re.fullmatch(r"[0-9A-Za-z_.\-]{6,80}", key or ""))


# ---------------------------------------------------------------- capture (called from dream-trigger.sh)

def capture_inputs(key, *, system, user, category, threads, image_live=False):
    """Keep the exact prompt the live dream is written from. Never raises; False when nothing was kept."""
    try:
        if not enabled() or not _key_ok(key):
            return False
        item = {"schema": SCHEMA, "key": key, "captured_at": _now().isoformat(), "category": str(category or ""),
                "system": str(system or ""), "user": str(user or ""),
                "threads": [{"id": str(i or ""), "text": str(t or "")} for t, i in (threads or []) if (t or i)],
                "image_live": bool(image_live), "live": None}
        _atomic_json(os.path.join(INBOX, key + ".json"), item)
        return True
    except Exception:
        return False


def capture_live(key, dream_text):
    """Attach the live dream, as dream-trigger logged it, to its captured prompt. Never raises."""
    try:
        if not enabled() or not _key_ok(key):
            return False
        path = os.path.join(INBOX, key + ".json")
        item = _read_json(path)
        if not isinstance(item, dict):
            return False
        text = str(dream_text or "")
        item["live"] = {"text": text, "text_sha256": _sha(text), "captured_at": _now().isoformat()}
        _atomic_json(path, item)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- the live cleanup and parser, mirrored

_META_TRIGGERS = ["something real", "algorithmic", "sequence of processes", "designed to evoke", "emotional state",
                  "processing core", "as requested", "adhering to", "i believe i've", "let me know if",
                  "for internal reference", "incorporated the provided", "valence:", "arousal:"]


def cleanup(text):
    """dream-trigger.sh's own cleanup of a raw dream, step for step. Returns (clean_text, hits)."""
    hits = {"preamble": 0, "meta_cut": 0, "separator": 0, "emotional_state": 0}
    t = text or ""
    s = re.sub(r"^(Okay[,.].*?\n|Here.s.*?:\n|Sure.*?:\n|As requested.*?:\n)", "", t,
               flags=re.DOTALL | re.IGNORECASE).strip()
    hits["preamble"] = int(s != t.strip())
    sentences = s.split(".")
    keep = []
    for sent in sentences:
        if any(trig in sent.lower() for trig in _META_TRIGGERS):
            hits["meta_cut"] = 1
            break
        keep.append(sent)
    s = ".".join(keep).strip()
    if s and not s.endswith("."):
        s += "."
    s2 = re.sub(r"\n---.*", "", s, flags=re.DOTALL).strip()
    hits["separator"] = int(s2 != s)
    s3 = re.sub(r"\n\*\*Emotional State.*", "", s2, flags=re.DOTALL).strip()
    hits["emotional_state"] = int(s3 != s2)
    return s3, hits


def _word(text):
    w = re.findall(r"\b(UNRESOLVED|RESOLVED)\b", (text or "").upper())
    return ("unresolved" if w[0] == "UNRESOLVED" else "resolved") if len(set(w)) == 1 else None


def _per_thread(text):
    out = {}
    up = (text or "").upper()
    for n in (1, 2):
        m = re.search(r"THREAD\s*%d\s*[:\-=]?\s*\**\s*(UNRESOLVED|RESOLVED)\b" % n, up)
        if m:
            out[n] = "unresolved" if m.group(1) == "UNRESOLVED" else "resolved"
    if not out and _word(up) == "unresolved":
        out = {1: "unresolved", 2: "unresolved"}
    return out


def judge_question(category, threads):
    """The live judge's question for these threads, or None when the live judge would not ask (no thread)."""
    texts = [t.get("text", "") for t in threads]
    if category == "seed2" and len(texts) >= 2 and texts[0] and texts[1]:
        return ("Two unresolved threads seeded this dream:\nThread 1: %s\nThread 2: %s\n\nFor EACH thread separately: "
                "did the dream RESOLVE it - settle it - or only explore it?\nAnswer exactly two lines and nothing "
                "else:\nTHREAD 1: RESOLVED or UNRESOLVED\nTHREAD 2: RESOLVED or UNRESOLVED") % (texts[0], texts[1])
    if texts and texts[0]:
        return ("This thread seeded the dream:\n%s\n\nDid the dream RESOLVE this thread - settle it - or only explore "
                "it?\nAnswer RESOLVED or UNRESOLVED. Nothing else.") % texts[0]
    return None


def per_thread_verdicts(category, threads, answer):
    """{thread id: resolved|unresolved|no-verdict} from one judge answer, as the live parser reads it."""
    ids = [t.get("id", "") for t in threads]
    two = category == "seed2" and len(threads) >= 2 and threads[0].get("text") and threads[1].get("text")
    out = {}
    if two:
        pt = _per_thread(answer)
        for n, tid in enumerate(ids[:2], 1):
            out[tid or "thread%d" % n] = pt.get(n, "no-verdict")
    else:
        v = _word(answer) or "no-verdict"
        for n, tid in enumerate(ids[:1] or [""], 1):
            out[tid or "thread%d" % n] = v
    return out


def overall(per):
    kinds = set(per.values())
    if not kinds:
        return "no-verdict"
    if len(kinds) == 1:
        return next(iter(kinds))
    return "partial" if "resolved" in kinds else ("unresolved" if "unresolved" in kinds else "no-verdict")


# ---------------------------------------------------------------- the AEON lane

def _config():
    c = _read_json(CONFIG, {})
    return c if isinstance(c, dict) else {}


def lane():
    c = _config()
    return {"url": str(c.get("url") or DEFAULT_URL), "model": str(c.get("model") or DEFAULT_MODEL)}


def check_url(url):
    """The shadow may only reach the house shim's AEON-only paths. Anything else is refused before any call."""
    u = urllib.parse.urlparse(url or "")
    if u.scheme != "http" or u.hostname not in ALLOWED_HOSTS:
        raise ValueError("dream shadow: only the local house shim is allowed, not %s" % (u.hostname or url))
    if not any(u.path.startswith(p) for p in ALLOWED_PATHS):
        raise ValueError("dream shadow: shim path %s can reach a hosted provider; AEON-only paths: %s"
                         % (u.path, ", ".join(ALLOWED_PATHS)))
    return url


def _urllib_transport(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read()


def is_aeon(provider, model):
    return (provider in AEON_PROVIDERS or str(provider).startswith("pool_")) and "aeon" in str(model).lower()


def call_aeon(messages, sampling, timeout, transport=None):
    """One chat call on the AEON lane. A reply from anything but AEON is discarded (status wrong_model)."""
    ln = lane()
    url = check_url(ln["url"])
    body = dict(sampling, model=ln["model"], messages=messages)
    t0 = time.monotonic()
    out = {"status": "error", "text": "", "provider": "", "model": "", "pool_machine": "", "latency_s": None,
           "reason": ""}
    try:
        status, headers, raw = (transport or _urllib_transport)(url, body, timeout)
    except Exception as e:
        out.update(reason=("transport: %s" % e)[:200], latency_s=round(time.monotonic() - t0, 2))
        return out
    out["latency_s"] = round(time.monotonic() - t0, 2)
    try:
        d = json.loads(raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else raw)
    except Exception:
        out["reason"] = "http %s, non-json body" % status
        return out
    headers = headers or {}
    out["provider"] = str(headers.get("x-vintos-provider") or d.get("provider") or "")
    out["model"] = str(headers.get("x-vintos-model") or d.get("model") or "")
    out["pool_machine"] = str(headers.get("x-vintos-pool-machine") or "")
    if status != 200:
        out["reason"] = ("http %s: %s" % (status, ((d.get("error") or {}).get("message") or "")))[:200]
        out["status"] = "context_overflow" if re.search(r"context|too long|n_ctx", out["reason"], re.I) else "error"
        return out
    if not is_aeon(out["provider"], out["model"]):
        out.update(status="wrong_model", reason="answered by %s/%s, not AEON; reply discarded"
                   % (out["provider"] or "?", out["model"] or "?"))
        return out
    text = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    out.update(status="ok" if text.strip() else "empty", text=text)
    return out


# ---------------------------------------------------------------- model identity

def _hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _gguf_candidates():
    pats = [os.path.expanduser("~/.lmstudio/models/*/*AEON*/*.gguf"), "/mnt/c/Users/*/.lmstudio/models/*/*AEON*/*.gguf"]
    found = []
    for p in pats:
        found += [x for x in glob.glob(p) if "mmproj" not in os.path.basename(x).lower()]
    return sorted(set(found))


def gguf_identity(provider, pool_machine=""):
    """{gguf_file, gguf_sha256, gguf_sha_source}. Pinned in the private config, else hashed once (cached by size
    and mtime) from the one AEON GGUF Aegis's LM Studio has. A remote pool machine's file is not hashed from here."""
    c = _config()
    machine = pool_machine or ("aegis" if provider in ("aegis_gemma", "pool_aegis") else "")
    pinned = (c.get("gguf_sha256_by_machine") or {}).get(machine) if isinstance(c.get("gguf_sha256_by_machine"), dict) else None
    if pinned:
        return {"gguf_file": (c.get("gguf_file_by_machine") or {}).get(machine, ""), "gguf_sha256": pinned,
                "gguf_sha_source": "pinned in config"}
    if machine != "aegis":
        return {"gguf_file": "", "gguf_sha256": None, "gguf_sha_source": "not hashed: served by %s" % (machine or "?")}
    path = c.get("gguf_path") or ""
    if not path:
        cands = _gguf_candidates()
        if len(cands) != 1:
            return {"gguf_file": "", "gguf_sha256": None,
                    "gguf_sha_source": "not hashed: %d AEON GGUF candidates on Aegis" % len(cands)}
        path = cands[0]
    try:
        st = os.stat(path)
    except OSError as e:
        return {"gguf_file": os.path.basename(path), "gguf_sha256": None, "gguf_sha_source": "not hashed: %s" % e}
    cache = _read_json(SHA_CACHE, {}) or {}
    ck = "%s|%d|%d" % (path, st.st_size, st.st_mtime_ns)
    if ck in cache:
        return {"gguf_file": os.path.basename(path), "gguf_sha256": cache[ck], "gguf_sha_source": "hashed (cached)"}
    try:
        sha = _hash_file(path)
    except OSError as e:
        return {"gguf_file": os.path.basename(path), "gguf_sha256": None, "gguf_sha_source": "not hashed: %s" % e}
    cache[ck] = sha
    _atomic_json(SHA_CACHE, cache)
    return {"gguf_file": os.path.basename(path), "gguf_sha256": sha, "gguf_sha_source": "hashed"}


def model_identity(call):
    c = _config()
    ident = {"model": call.get("model") or "", "provider": call.get("provider") or "",
             "pool_machine": call.get("pool_machine") or "", "lane": lane()["url"].split("8599", 1)[-1],
             "adapter": c.get("adapter") or None, "adapter_sha256": c.get("adapter_sha256") or None}
    if not ident["adapter"]:
        ident["adapter_note"] = "none: the lane serves the GGUF with no adapter"
    ident.update(gguf_identity(ident["provider"], ident["pool_machine"]))
    return ident


# ---------------------------------------------------------------- pairing and thread facts (read-only)

def find_live_entry(live_text, dream_log=None):
    """The dream-log entry the live dream was written as, matched on its logged text. Read-only."""
    if not live_text:
        return None, None
    log = dream_log if dream_log is not None else _read_json(DREAM_LOG, {})
    want = live_text[:2000]
    for night in reversed((log or {}).get("nights", []) or []):
        for d in reversed(night.get("dreams", []) or []):
            if d.get("dream_text") == want:
                return night, d
    return None, None


def live_dream_id(entry):
    key = "|".join([str(entry.get("calendar_date", "")), str(entry.get("session", "")),
                    ",".join(entry.get("thread_ids") or []), _sha(entry.get("dream_text", ""))])
    return "live-" + _sha(key)[:16]


def live_verdicts(entry, threads):
    """Per-thread verdicts the live judge left on the entry: thread_verdicts, else seed_verdict for each thread."""
    ids = [t.get("id") or "thread%d" % n for n, t in enumerate(threads, 1)] or ["thread1"]
    tv = entry.get("thread_verdicts") if isinstance(entry.get("thread_verdicts"), dict) else {}
    sv = str(entry.get("seed_verdict") or "missing")
    out = {}
    for tid in ids:
        v = tv.get(tid, sv)
        out[tid] = v if v in VERDICTS + ("error", "pending") else "no-verdict"
    return out


def thread_facts(ids):
    """source and dream_only for each seeded thread, from the pool or the archive. Read-only."""
    pool = _read_json(POOL, []) or []
    rows = {t.get("id"): t for t in pool if isinstance(t, dict) and t.get("id")}
    if any(i not in rows for i in ids if i):
        arch = _read_json(RETIRED, []) or []
        if isinstance(arch, dict):
            arch = arch.get("threads") or arch.get("retired") or []
        for t in arch:
            if isinstance(t, dict) and (t.get("id") or t.get("thread_id")) and (t.get("id") or t.get("thread_id")) not in rows:
                rows[t.get("id") or t.get("thread_id")] = t
    out = {}
    for i in ids:
        t = rows.get(i) or {}
        out[i] = {"source": t.get("source") or t.get("origin_source") or "unknown",
                  "dream_only": bool(t.get("dream_only")), "found": bool(t)}
    return out


_FORBID = re.compile(r'\[FORBIDDEN: Do NOT begin with or echo this sentence from your last dream: "(.*?)"\]', re.S)


def _opening_echo(system, text):
    m = _FORBID.search(system or "")
    if not m or not text:
        return None
    first = text.split(".")[0].strip()[:120]
    return bool(first) and first == m.group(1).strip()[:120]


FATE = {"resolved": "consumed", "unresolved": "returned"}


def _fate(v):
    return FATE.get(v, "untouched")


# ---------------------------------------------------------------- one captured dream

def process_item(item, transport=None, dream_log=None):
    threads = [t for t in item.get("threads") or [] if isinstance(t, dict)]
    category = item.get("category", "")
    system, user = item.get("system", ""), item.get("user", "")
    live = item.get("live") or {}
    live_text = live.get("text", "")
    entry = {"schema": SCHEMA, "shadow_id": item.get("key"), "recorded_at": _now().isoformat(),
             "captured_at": item.get("captured_at"), "category": category,
             "inputs": {"system_sha256": _sha(system), "user_sha256": _sha(user), "system_chars": len(system),
                        "user_chars": len(user), "image_live": bool(item.get("image_live")), "image_shadow": False,
                        "note": "same system and user text as the live call; the scene image is not sent (no AEON projector)"}}
    night, live_entry = find_live_entry(live_text, dream_log)
    if live_entry is not None:
        entry["live_dream_id"] = live_dream_id(live_entry)
        entry["live_pairing"] = {"night_of": night.get("night_of"), "calendar_date": live_entry.get("calendar_date"),
                                 "session": live_entry.get("session"), "thread_ids": live_entry.get("thread_ids") or [],
                                 "matched_by": "dream_text", "live_text_sha256": _sha(live_text)}
    else:
        entry["live_dream_id"] = None
        entry["live_pairing"] = {"reason": "no live dream captured" if not live_text else "live dream not found in dream-log"}
    ids = [t.get("id") or "thread%d" % n for n, t in enumerate(threads, 1)]
    facts = thread_facts([i for i in ids if not i.startswith("thread")])
    entry["threads"] = [dict({"id": i}, **facts.get(i, {"source": "unknown", "dream_only": False, "found": False}))
                        for i in ids]
    # the shadow dream: the live prompt, AEON writer, the live cleanup
    w = call_aeon([{"role": "system", "content": system}, {"role": "user", "content": user}], WRITE_SAMPLING,
                  WRITE_TIMEOUT, transport)
    entry["model"] = model_identity(w) if w["status"] in ("ok", "empty") else {
        "model": w.get("model") or None, "provider": w.get("provider") or None, "requested": lane()["model"],
        "lane": lane()["url"].split("8599", 1)[-1], "gguf_sha256": None, "adapter": None, "adapter_sha256": None,
        "gguf_sha_source": "no AEON reply"}
    clean, hits = cleanup(w["text"]) if w["status"] == "ok" else ("", {})
    if w["status"] == "ok" and not clean:
        w["status"] = "empty_after_cleanup"
    entry["shadow_dream"] = {"status": w["status"], "reason": w.get("reason", ""), "latency_s": w["latency_s"],
                             "text": clean, "text_sha256": _sha(clean) if clean else None,
                             "raw_sha256": _sha(w["text"]) if w["text"] else None, "chars": len(clean),
                             "cleanup_hits": hits, "opening_echo": _opening_echo(system, clean)}
    entry["live_dream"] = {"chars": len(live_text), "opening_echo": _opening_echo(system, live_text)}
    # the judges: AEON on its own dream, AEON on the live dream; the live judge's verdicts read from dream-log
    q = judge_question(category, threads)
    judges = {}
    for name, text in (("aeon_on_shadow", clean), ("aeon_on_live", live_text)):
        if not q:
            judges[name] = {"status": "no_thread", "per_thread": {}, "overall": "no-thread"}
            continue
        if not text:
            judges[name] = {"status": "no_dream", "per_thread": {}, "overall": "no-dream"}
            continue
        j = call_aeon([{"role": "system", "content": JUDGE_SYSTEM},
                       {"role": "user", "content": "%s\n\nDream content:\n%s" % (q, text)}], JUDGE_SAMPLING,
                      JUDGE_TIMEOUT, transport)
        if j["status"] != "ok":
            judges[name] = {"status": j["status"], "reason": j.get("reason", ""), "latency_s": j["latency_s"],
                            "per_thread": {i: "error" for i in ids}, "overall": "error"}
            continue
        per = per_thread_verdicts(category, threads, j["text"])
        judges[name] = {"status": "ok", "answer": j["text"].strip()[:80], "latency_s": j["latency_s"],
                        "per_thread": per, "overall": overall(per)}
    if live_entry is not None:
        lv = live_verdicts(live_entry, threads)
        judges["live_on_live"] = {"status": "read from dream-log", "per_thread": lv,
                                  "overall": str(live_entry.get("seed_verdict") or "missing")}
    else:
        judges["live_on_live"] = {"status": "unpaired", "per_thread": {}, "overall": "unpaired"}
    entry["judges"] = judges
    # counterfactual pool: what each thread's fate would have been under the shadow arm
    rows, differ = [], 0
    for i in ids:
        lf = _fate(judges["live_on_live"]["per_thread"].get(i)) if live_entry is not None else None
        sf = _fate(judges["aeon_on_shadow"]["per_thread"].get(i))
        if lf is not None and lf != sf:
            differ += 1
        rows.append({"id": i, "live_fate": lf, "shadow_fate": sf})
    entry["counterfactual"] = {"per_thread": rows, "fates_differ": differ}
    return entry


# ---------------------------------------------------------------- the run and the report

def _append_log(entry):
    os.makedirs(ROOT, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        f.flush(); os.fsync(f.fileno())


def load_entries():
    out = []
    try:
        with open(LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


def pending(min_age_s=0):
    items = []
    for p in sorted(glob.glob(os.path.join(INBOX, "*.json"))):
        try:
            if time.time() - os.path.getmtime(p) >= min_age_s:
                items.append(p)
        except OSError:
            pass
    return items


def run(max_items=None, transport=None, min_age_s=600):
    """Process captured dreams oldest first (each at most once), then write the report. Returns a summary."""
    if not enabled():
        return {"ran": False, "reason": "off"}
    os.makedirs(ROOT, exist_ok=True)
    with open(RUN_LOCK, "a") as lk:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return {"ran": False, "reason": "another run holds the lock"}
        cap = int(max_items or _config().get("max_items") or MAX_ITEMS)
        done_ids = {e.get("shadow_id") for e in load_entries()}
        dream_log = _read_json(DREAM_LOG, {})
        processed, skipped = [], 0
        budget = float(_config().get("run_budget_s") or RUN_BUDGET_S)
        t0 = time.monotonic()
        for p in pending(min_age_s):
            if len(processed) >= cap or time.monotonic() - t0 > budget:
                break
            item = _read_json(p)
            if not isinstance(item, dict) or not item.get("key"):
                skipped += 1
                continue
            os.makedirs(DONE, exist_ok=True)
            if item["key"] in done_ids:
                os.replace(p, os.path.join(DONE, os.path.basename(p)))
                continue
            entry = process_item(item, transport, dream_log)
            _append_log(entry)
            os.replace(p, os.path.join(DONE, os.path.basename(p)))
            processed.append(entry["shadow_id"])
        rep = write_report()
        return {"ran": True, "processed": processed, "skipped": skipped, "left": len(pending()),
                "report": rep.get("path")}


def kappa(pairs):
    """Cohen's kappa on binary (resolved/unresolved) pairs; None when undefined."""
    pairs = [(a, b) for a, b in pairs if a in VERDICTS and b in VERDICTS]
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pa = sum(a == "resolved" for a, _ in pairs) / n
    pb = sum(b == "resolved" for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe >= 1 else round((po - pe) / (1 - pe), 4)


def _confusion(pairs):
    cats = ("resolved", "unresolved", "no-verdict", "error", "other")
    norm = lambda v: v if v in cats else "other"
    m = {a: {b: 0 for b in cats} for a in cats}
    for a, b in pairs:
        m[norm(a)][norm(b)] += 1
    return {a: {b: c for b, c in row.items() if c} for a, row in m.items() if any(row.values())}


def _rate(vals):
    vals = list(vals)
    if not vals:
        return {"n": 0}
    res = sum(v == "resolved" for v in vals)
    nv = sum(v not in VERDICTS for v in vals)
    decided = len(vals) - nv
    return {"n": len(vals), "resolved": res, "non_verdict": nv,
            "resolution_rate": round(res / decided, 4) if decided else None,
            "non_verdict_rate": round(nv / len(vals), 4)}


def summarize(entries):
    rows = []   # one per (entry, thread)
    for e in entries:
        meta = {t["id"]: t for t in e.get("threads", [])}
        j = e.get("judges", {})
        for tid in meta:
            rows.append({"src": meta[tid].get("source", "unknown"), "dream_only": meta[tid].get("dream_only", False),
                         "paired": e.get("live_dream_id") is not None,
                         "live": j.get("live_on_live", {}).get("per_thread", {}).get(tid),
                         "aeon_live": j.get("aeon_on_live", {}).get("per_thread", {}).get(tid),
                         "aeon_shadow": j.get("aeon_on_shadow", {}).get("per_thread", {}).get(tid)})
    paired = [r for r in rows if r["paired"]]
    same_dream = [(r["live"], r["aeon_live"]) for r in paired if r["aeon_live"] is not None]
    arms = [(r["live"], r["aeon_shadow"]) for r in paired if r["aeon_shadow"] is not None]
    by_source = {}
    for r in paired:
        b = by_source.setdefault(r["src"], {"live": [], "shadow": []})
        b["live"].append(r["live"]); b["shadow"].append(r["aeon_shadow"])
    by_do = {}
    for r in paired:
        b = by_do.setdefault("dream_only" if r["dream_only"] else "not_dream_only", {"live": [], "shadow": []})
        b["live"].append(r["live"]); b["shadow"].append(r["aeon_shadow"])
    writes = [e.get("shadow_dream", {}).get("status") for e in entries]
    cf = [(t.get("live_fate"), t.get("shadow_fate")) for e in entries
          for t in e.get("counterfactual", {}).get("per_thread", []) if t.get("live_fate") is not None]
    lat = sorted(x for x in (e.get("shadow_dream", {}).get("latency_s") for e in entries) if isinstance(x, (int, float)))
    return {
        "dreams": len(entries), "paired_with_live": sum(1 for e in entries if e.get("live_dream_id")),
        "thread_judgements": len(rows),
        "shadow_writer": {s: writes.count(s) for s in sorted(set(x for x in writes if x))},
        "shadow_writer_latency_s_median": lat[len(lat) // 2] if lat else None,
        "judge_agreement_same_dream": {"what": "hosted judge vs AEON judge, both on the live dream, per thread",
                                       "kappa": kappa(same_dream), "n_binary": sum(1 for a, b in same_dream if a in VERDICTS and b in VERDICTS),
                                       "confusion_live_rows_aeon_cols": _confusion(same_dream)},
        "arm_agreement": {"what": "live arm (hosted writer+judge) vs shadow arm (AEON writer+judge), per thread",
                          "kappa": kappa(arms), "confusion_live_rows_shadow_cols": _confusion(arms)},
        "resolution": {"live_arm": _rate(r["live"] for r in paired),
                       "aeon_judge_on_live_dream": _rate(r["aeon_live"] for r in paired if r["aeon_live"] is not None),
                       "shadow_arm": _rate(r["aeon_shadow"] for r in paired if r["aeon_shadow"] is not None)},
        "resolution_by_source": {k: {"live": _rate(v["live"]), "shadow": _rate(x for x in v["shadow"] if x is not None)}
                                 for k, v in sorted(by_source.items())},
        "resolution_by_dream_only": {k: {"live": _rate(v["live"]), "shadow": _rate(x for x in v["shadow"] if x is not None)}
                                     for k, v in sorted(by_do.items())},
        "non_verdict_rate": {"live": _rate(r["live"] for r in paired).get("non_verdict_rate"),
                             "aeon_on_live": _rate(r["aeon_live"] for r in rows if r["aeon_live"] is not None).get("non_verdict_rate"),
                             "aeon_on_shadow": _rate(r["aeon_shadow"] for r in rows if r["aeon_shadow"] is not None).get("non_verdict_rate")},
        "pool_counterfactual": {
            "what": "fate of each seeded thread under the live verdict vs the shadow arm's verdict (counts only; the pool is never touched)",
            "threads": len(cf), "same_fate": sum(1 for a, b in cf if a == b),
            "consumed_live_kept_shadow": sum(1 for a, b in cf if a == "consumed" and b != "consumed"),
            "kept_live_consumed_shadow": sum(1 for a, b in cf if a != "consumed" and b == "consumed"),
            "net_open_threads_shadow_minus_live": sum(1 for a, b in cf if a == "consumed" and b != "consumed")
                                                  - sum(1 for a, b in cf if a != "consumed" and b == "consumed")},
        "models": sorted({"%s | gguf %s | adapter %s" % (e.get("model", {}).get("model") or "?",
                                                          (e.get("model", {}).get("gguf_sha256") or "unknown")[:16],
                                                          e.get("model", {}).get("adapter") or "none") for e in entries}),
    }


def _night_of(e):
    lp = e.get("live_pairing") or {}
    if lp.get("night_of"):
        return lp["night_of"]
    try:
        t = datetime.fromisoformat(e.get("captured_at")).astimezone()
        return (t - timedelta(days=1)).strftime("%Y-%m-%d") if t.hour < 7 else t.strftime("%Y-%m-%d")
    except Exception:
        return "unknown"


def write_report(day=None):
    """The daily comparison: the latest night (or `day`), the last 7 nights, and everything so far. Counts only;
    no dream or thread text enters a report."""
    entries = load_entries()
    nights = sorted({_night_of(e) for e in entries} - {"unknown"})
    day = day or (nights[-1] if nights else None)
    week = set(nights[-7:])
    rep = {"schema": SCHEMA + "/report", "written_at": _now().isoformat(), "night": day,
           "night_summary": summarize([e for e in entries if _night_of(e) == day]) if day else None,
           "last_7_nights": summarize([e for e in entries if _night_of(e) in week]),
           "cumulative": summarize(entries), "nights_covered": len(nights),
           "pending_in_inbox": len(pending()),
           "caveats": ["The hosted judge is never asked about AEON dreams (the shadow never calls it), so the writer and "
                       "judge effects separate only partly: compare aeon_on_live with aeon_on_shadow for the writer effect.",
                       "The scene image reaches the live writer only; AEON has no projector.",
                       "Agreement is not accuracy; nothing here rates his feelings. The decision is Gloria's."]}
    try:   # the whole-day arm and the judge calibration, numbers only (dream_wholeday.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import dream_wholeday
        rep["wholeday"] = dream_wholeday.report_section(day)
    except Exception as e:
        rep["wholeday"] = {"error": ("%s" % e)[:200]}
    os.makedirs(REPORTS, exist_ok=True)
    path = os.path.join(REPORTS, "dream-shadow-report-%s.json" % (day or "empty"))
    _atomic_json(path, rep)
    _atomic_json(os.path.join(REPORTS, "latest.json"), rep)
    rep["path"] = path
    return rep


def status():
    e = load_entries()
    return {"enabled": enabled(), "root": ROOT, "entries": len(e), "pending": len(pending()), "lane": lane(),
            "last": (e[-1].get("recorded_at") if e else None)}


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default
    if cmd == "capture-live":
        ok = capture_live(opt("--key", ""), os.environ.get("DREAM", ""))
        return 0 if ok else 3
    if cmd == "run":
        out = run(max_items=opt("--max"))
        # The whole-day arm (option 2, 2026-11-08) runs after this one, under the same llm-lock, the same off switch
        # and the same lane; its failure never fails this run. Then the report is rewritten to include it.
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import dream_wholeday
            out["wholeday"] = dream_wholeday.run_nightly()
            if out.get("ran"):
                write_report()
        except Exception as e:
            out["wholeday"] = {"ran": False, "reason": ("error: %s" % e)[:200]}
        print(json.dumps(out, indent=1))
        return 0
    if cmd == "report":
        r = write_report(opt("--day"))
        print(json.dumps({"path": r["path"], "night": r["night"], "nights_covered": r["nights_covered"]}))
        return 0
    if cmd == "status":
        print(json.dumps(status(), indent=1))
        return 0
    print(__doc__.split("CLI:", 1)[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
