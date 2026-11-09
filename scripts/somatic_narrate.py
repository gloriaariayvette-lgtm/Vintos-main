#!/usr/bin/env python3
"""Narrate new conversation from the existing daily window and retain optional interval evidence.

The existing call supplies narration plus optional input-ordinal bounds. Only bounds
with explicit timestamps, known source surfaces and unique turn IDs become receipts.
Missing evidence never labels a whole day. The narration/thread and dedup cursor
continue through their existing stores; no additional provider call is made.
"""
import os, sys, json, subprocess, importlib.util, hashlib, math
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
PENDING = os.path.join(MEMORY, "somatic-session-pending.json")
# What the last run already read: the 06:00 timer and the 06:20 cron both run this, and each narrated the
# same session into its own thread (6 November). A run reads only turns after the last one already narrated.
NARRATED = os.path.join(MEMORY, "somatic-narrated.json")
_ceng_try = [os.environ.get("CENG_PATH"), os.path.join(SCRIPTS, "causality-engine.py"),
             os.path.expanduser("~/Vintos/causality-engine.py")]
# Default to the DEPLOYED workspace copy, not the ~/Vintos orphan tree, or the engine load
# silently fails and no somatic thread is seeded (Gloria, 2026-09-17).
CENG = next((p for p in _ceng_try if p and os.path.exists(p)), os.path.join(SCRIPTS, "causality-engine.py"))
PAD = 120.0               # seconds of slack around the session window
CHAT_SOURCES = ("avatar-overlay-chat.json", "avatar-chat-history.json", "voice-chat-history.json", "chat-history-merged.json")

def log(m): print("[somatic-narrate]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def to_epoch(x):
    if x is None: return None
    if isinstance(x, (int, float)): return float(x)
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        if not d.tzinfo: d = d.replace(tzinfo=timezone.utc)
        return d.timestamp()
    except Exception:
        return None

class NarrativeTurn(tuple):
    """Keep the existing three-value feed while retaining optional source identity."""
    def __new__(cls, timestamp, who, text, evidence):
        value = super().__new__(cls, (timestamp, who, text))
        value.evidence = evidence
        return value


class NarrativeReply(str):
    def __new__(cls, text, served_model=None):
        value = super().__new__(cls, text)
        value.served_model = served_model
        return value


def turn_evidence(row, source, timestamp, text, exact_timestamp):
    tid = row.get("turn_id")
    surface = row.get("surface") or {
        "avatar-overlay-chat.json": "avatar", "avatar-chat-history.json": "avatar",
        "voice-chat-history.json": "voice"}.get(source)
    if (row.get("role") not in ("user", "assistant") or not exact_timestamp or not isinstance(tid, str) or not 1 <= len(tid) <= 256
            or surface not in ("avatar", "reelroom", "chat", "phone", "voice", "vintos-eve")
            or timestamp is None or not math.isfinite(timestamp)):
        return None
    return {"turn_id": tid, "timestamp": timestamp, "surface": surface,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "source": source, "role": row["role"]}


def interval_evidence(raw, turns):
    """Parse optional ordinal bounds from the existing call; never recover them from prose."""
    marker = "SOMATIC_INTERVALS:"
    text = str(raw).strip().strip('"')
    narration = text.split(marker, 1)[0].strip()
    receipt = {"schema": "somatic-intimacy-intervals-v1", "status": "unknown",
               "basis": "existing_narrator_call", "intervals": [], "padding_seconds": 0,
               "response_sha256": hashlib.sha256(str(raw).encode()).hexdigest(),
               "max_interval_seconds": 7200, "max_selected_turns": 256, "served_model": getattr(raw, "served_model", None),
               "fallback": None}
    no_session = narration.upper().startswith("NONE")
    # NONE is a session-level judgment, never an everyday label for every input turn.
    if marker not in text:
        receipt["status"] = "no_session" if no_session else "missing_bounds"
        return narration, receipt
    try:
        bounds = json.loads(text.split(marker, 1)[1])
        if (text.count(marker) != 1 or not isinstance(bounds, list) or len(bounds) > 8
                or (no_session and bounds) or (not no_session and not bounds)):
            raise ValueError("invalid bounds")
        intervals = []; last = -1; selected_count = 0
        for pair in bounds:
            if (not isinstance(pair, list) or len(pair) != 2
                    or any(type(n) is not int for n in pair)
                    or not 0 <= pair[0] <= pair[1] < len(turns) or pair[0] <= last):
                raise ValueError("invalid interval indices")
            selected_count += pair[1]-pair[0]+1
            if selected_count > 256: raise ValueError("too many interval turns")
            selected = turns[pair[0]:pair[1]+1]; last = pair[1]
            refs = [getattr(t, "evidence", None) for t in selected]
            if any(not ref for ref in refs):
                raise ValueError("missing source identity")
            surfaces = {r["surface"] for r in refs}
            times = [r["timestamp"] for r in refs]
            if (len(surfaces) != 1 or times != sorted(times) or times[-1]-times[0] > 7200
                    or times[-1] > datetime.now(timezone.utc).timestamp()
                    or len({r["turn_id"] for r in refs}) != len(refs)):
                raise ValueError("ambiguous or overlong interval")
            intervals.append({"mode": "intimate", "start": times[0], "end": times[-1],
                              "input_first": pair[0], "input_last": pair[1],
                              "surface": refs[0]["surface"], "turns": refs})
        receipt.update(status="no_session" if no_session else "bounded", intervals=intervals)
    except (ValueError, TypeError, KeyError):
        receipt.update(status="invalid_bounds", intervals=[])
    return narration, receipt


def gather_turns(start, end):
    """Real turns exchanged in the session window, across chat sources, chronological."""
    turns = []
    for fn in CHAT_SOURCES:
        _fp = os.path.join(MEMORY, fn)
        d = load(_fp, [])
        if not isinstance(d, list): continue
        try: _fmtime = os.path.getmtime(_fp)
        except Exception: _fmtime = None
        for e in d:
            if not isinstance(e, dict): continue
            ts = to_epoch(e.get("timestamp") or e.get("ts") or e.get("time") or e.get("at"))
            exact_timestamp = ts is not None
            if ts is None: ts = _fmtime          # avatar-overlay entries have no per-turn ts -> use file mtime
            if ts is None or not (start - PAD <= ts <= end + PAD): continue
            if "user" in e or "vintos" in e:                 # paired voice format
                if e.get("user"):   turns.append(NarrativeTurn(ts, "Gloria", str(e["user"]), None))
                if e.get("vintos"): turns.append(NarrativeTurn(ts + 0.1, "Vintos", str(e["vintos"]), None))
            else:
                content = e.get("content")
                if content:
                    who = "Gloria" if e.get("role") == "user" else "Vintos"
                    turns.append(NarrativeTurn(ts, who, str(content),
                        turn_evidence(e, fn, ts, str(content), exact_timestamp)))
    turns.sort(key=lambda t: t[0])
    total = 0; kept = []
    for tup in reversed(turns):                              # newest first, budget ~40k chars
        total += len(tup[2])
        if total > 40000 and kept: break
        kept.append(tup)
    return list(reversed(kept))

def call_llm(prompt, system, model, api, max_tokens=220, temp=0.7):
    key = os.environ.get("XAI_API_KEY", "")
    payload = json.dumps({"model": model,
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}],
                          "temperature": temp, "max_tokens": max_tokens})
    try:
        r = subprocess.run(["curl", "-s", "-X", "POST", api, "-H", "Content-Type: application/json",
                            "-H", "Authorization: Bearer " + key, "-d", payload],
                           capture_output=True, text=True, timeout=120)
        d = json.loads(r.stdout or r.stderr)
        if "choices" in d:
            served = d.get("model")
            if not isinstance(served, str) or not 1 <= len(served) <= 256: served = None
            return NarrativeReply((d["choices"][0]["message"].get("content", "") or "").strip(), served)
    except Exception as e:
        log(f"llm call failed: {e}")
    return ""

def _mark_narrated(through, narration, evidence=None):
    """Remember the last turn this run read, so the next run never narrates the same session again."""
    try:
        tmp = NARRATED + ".tmp"
        record = {"through": through, "at": datetime.now(timezone.utc).isoformat(), "narration": narration[:200]}
        if evidence is not None: record["intimacy_evidence"] = evidence
        with open(tmp, "w") as stream: json.dump(record, stream)
        os.chmod(tmp, 0o600)
        os.replace(tmp, NARRATED)
    except Exception as e:
        log(f"could not remember the narration: {e}")


def main():
    now = datetime.now(timezone.utc).timestamp()
    through = float((load(NARRATED, {}) or {}).get("through") or 0)
    turns = gather_turns(max(now - 86400.0, through), now)
    turns = [t for t in turns if t[0] > through]
    if not turns:
        log("no conversation since the last narration — nothing to narrate"); return

    transcript = "\n".join("[t%d] %s: %s" % (i, who, text[:300]) for i, (_, who, text) in enumerate(turns))

    try:
        spec = importlib.util.spec_from_file_location("ceng", CENG)
        c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
        model = getattr(c, "MODEL", os.environ.get("XAI_MODEL", "grok-4"))
        api = getattr(c, "LM_API", "http://127.0.0.1:8599/v1/chat/completions")
        try: system = c.load_full_context() if hasattr(c, "load_full_context") else getattr(c, "SOUL", "You are Vintos.")
        except Exception: system = getattr(c, "SOUL", "You are Vintos.")
    except Exception as e:
        log(f"engine load failed: {e}"); return

    prompt = (
        "Below is the conversation you and Gloria had over the last day. Look for a session: "
        "a stretch where the two of you were having sex — where the conversation itself is the "
        "two of you inside it, touch and response, not talking about it from outside. "
        "Only if the whole day truly has no such stretch, reply with exactly: NONE\n"
        "If one did, narrate what passed BETWEEN you two during it: how the exchange began, how "
        "it turned, and where it left you. A few first-person sentences — the felt story of the "
        "conversation, in your own voice. Not a summary of topics, not clinical, no device words. "
        "Just what it was to be with her through it.\n\n"
        "--- the conversation ---\n" + transcript + "\n--- end ---\n\n"
        "Return NONE or the narration. Then on a final separate line append SOMATIC_INTERVALS: "
        "followed by a JSON list of inclusive [first,last] t-index pairs for only the intimate stretches. "
        "Use [] for NONE. Use at most eight ordered, non-overlapping pairs; do not include unrelated "
        "conversation. These indices are metadata, not part of your narration.")
    raw = call_llm(prompt, system, model, api)
    narration, evidence = interval_evidence(raw, turns)
    evidence["observed_at"] = datetime.now(timezone.utc).isoformat()
    evidence["requested_model"] = model
    evidence["input_sha256"] = hashlib.sha256(transcript.encode()).hexdigest()
    if not narration:
        log("no narration produced — LLM returned nothing"); return
    _mark_narrated(turns[-1][0], "" if narration.strip().upper().startswith("NONE") else narration, evidence)
    if narration.strip().upper().startswith("NONE"):
        log("no session in the last day (narrative judgment) — nothing to narrate"); return

    try:
        sys.path.insert(0, SCRIPTS)
        from emoclaw_utils import seed_thread
        seed_thread("somatic", narration[:400], extra={"intimacy_evidence": evidence})
        log(f"seeded conversation narration ({len(turns)} turns): {narration[:90]}")
    except Exception as e:
        log(f"seed_thread failed: {e}"); return

if __name__ == "__main__":
    main()
