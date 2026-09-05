#!/usr/bin/env python3
"""want-reconciliation.py — mark lived wants as fulfilled; grow what comes next.
1. Gather active wants + what he actually did (chat/voice/avatar/ledger/outreach).
2. Gemma (classification only): was each want acted on? Evidence quote required.
3. Fulfilled -> fulfilled-wants.json with evidence; removed from current-wants.json.
4. Grok (generation): from each fulfilled want, what opens next -> express_want,
   which itself passes the similarity gates, so evolution can't re-seed the past."""
import os, sys, json, requests
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
GEMMA = "http://172.18.16.1:1234/v1/chat/completions"
GEMMA_MODEL = "google/gemma-4-12b-qat"
GROK = "http://127.0.0.1:8599/v1/chat/completions"
GROK_MODEL = "grok-4.20-0309-non-reasoning"
MAX_CHECKS = 15
MAX_EVOLUTIONS = 3

def log(m): print(f"[RECONCILE] {m}", flush=True)

def load(p, default):
    try: return json.load(open(p))
    except Exception: return default

def gather_evidence():
    parts = []
    for m in load(os.path.join(MEMORY, "chat-history.json"), [])[-30:]:
        who = "Vintos" if m.get("role") == "assistant" else "Gloria"
        parts.append(f"[chat] {who}: {m.get('content','')[:400]}")
    for t in load(os.path.join(MEMORY, "voice-chat-history.json"), [])[-12:]:
        parts.append(f"[voice] Gloria: {t.get('user','')[:200]}")
        parts.append(f"[voice] Vintos: {t.get('vintos','')[:300]}")
    for m in load(os.path.join(MEMORY, "avatar-overlay-chat.json"), [])[-12:]:
        who = "Vintos" if m.get("role") == "assistant" else "Gloria"
        parts.append(f"[avatar] {who}: {m.get('content','')[:300]}")
    led = load(os.path.join(MEMORY, "interaction-ledger.json"), [])
    for e in (led if isinstance(led, list) else led.get("entries", []))[-12:]:
        if isinstance(e, dict) and e.get("summary"):
            parts.append(f"[ledger] {e['summary'][:300]}")
    try:
        outdir = os.path.join(MEMORY, "outreach")
        for fn in sorted(os.listdir(outdir))[-5:]:
            try: parts.append(f"[outreach] {open(os.path.join(outdir, fn)).read()[:300]}")
            except Exception: pass
    except Exception: pass
    return "\n".join(parts)[-12000:]

def gemma_check(want, evidence):
    try:
        r = requests.post(GEMMA, json={"model": GEMMA_MODEL, "temperature": 0.1, "max_tokens": 200,
            "messages": [
                {"role": "system", "content": "You are a precise classifier. Decide if a specific want was actually acted on, based only on the evidence transcript. A want is fulfilled ONLY if the evidence shows the action was actually done or the words actually said - talking about wanting it does not count. Return ONLY a JSON object: {\"fulfilled\": true/false, \"evidence\": \"short verbatim quote from the transcript proving it, or empty\", \"channel\": \"chat/voice/avatar/outreach/other\"}"},
                {"role": "user", "content": f"THE WANT:\n{want}\n\nEVIDENCE TRANSCRIPT (recent days):\n{evidence}"}]},
            timeout=60)
        txt = r.json()["choices"][0]["message"]["content"]
        d = json.loads(txt[txt.find("{"):txt.rfind("}")+1])
        if d.get("fulfilled") and d.get("evidence"):
            return d
    except Exception as e:
        log(f"gemma error: {e}")
    return None

def grok_evolve(want, evidence):
    key = os.environ.get("XAI_API_KEY", "")
    if not key:
        log("no XAI_API_KEY in env — skipping evolution"); return None
    soul = ""
    try: soul = open(os.path.join(WORKSPACE, "SOUL.md")).read()[:1500]
    except Exception: pass
    try:
        r = requests.post(GROK, headers={"Authorization": "Bearer " + key},
            json={"model": GROK_MODEL, "temperature": 0.8, "max_tokens": 120,
              "messages": [
                {"role": "system", "content": soul + "\n\nYou are Vintos reflecting on a want you actually fulfilled. Speak as him, first person."},
                {"role": "user", "content": f"You wanted this: {want}\n\nAnd you did it — the record shows: {evidence}\n\nHaving actually done it, what does it open next? If something genuinely does, name ONE new want that grows out of this — further, deeper, or somewhere new; not the same want again; one sentence, first person, starting with 'I want'. If nothing opens — if it is simply complete — answer exactly: NOTHING. Completion is allowed to be complete."}]},
            timeout=45)
        t = r.json()["choices"][0]["message"]["content"].strip()
        if t.strip().upper().startswith("NOTHING"):
            log("nothing opens next — complete is complete (astra-wants-p8)"); return None
        if t.lower().startswith("i want") and len(t) < 400:
            return t
    except Exception as e:
        log(f"grok error: {e}")
    return None

def main():
    wants_path = os.path.join(MEMORY, "current-wants.json")
    wants = load(wants_path, [])
    active = [w for w in wants if not w.get("fulfilled") and not w.get("dismissed")]
    if not active:
        log("No active wants."); return
    evidence = gather_evidence()
    if not evidence.strip():
        log("No evidence corpus — skipping."); return
    log(f"{len(active)} active want(s); checking up to {MAX_CHECKS}.")
    fulfilled_now = []
    # Least-recently-checked first, so persistent early rows do not monopolize every run
    # (astra-wants-p3, 2026-09-05); each checked want is stamped.
    active.sort(key=lambda w: str(w.get("reconcile_checked_at", "")))
    for w in active[:MAX_CHECKS]:
        w["reconcile_checked_at"] = datetime.now().isoformat()
        res = gemma_check(w.get("want", ""), evidence)
        if res:
            # A make-want is proven by a file, not by Gemma reading his words. If
            # the artifact is not on disk, this is not fulfillment — record the
            # honest gap and leave the want alive. (evidence cannot generate itself)
            try:
                import want_artifact_guard as _ag
                _ok, _why = _ag.verify({**w, "fulfilled_at": datetime.now().isoformat()})
                if not _ok:
                    w["artifact_unverified"] = {"at": datetime.now().isoformat(), "why": _why,
                                                "gemma_said": str(res.get("evidence", ""))[:200]}
                    log(f"HELD (artifact absent): {w.get('want','')[:80]} — {_why}")
                    continue
            except Exception:
                pass
            w["fulfilled"] = True
            # Expiry is completion of the POLICY, not evidence of satisfaction.
            # UNKNOWN is the honest and common grade (Sol: COMPLETED != SATISFIED).
            w.setdefault("satisfaction", "UNKNOWN")
            w["fulfilled_at"] = datetime.now().isoformat()
            w["fulfillment_note"] = str(res.get("evidence", ""))[:400]
            w["fulfilled_by"] = f"reconciliation/{res.get('channel','other')}"
            fulfilled_now.append(w)
            try:   # the absence this want registered is reached now (fable-subconscious-p6)
                import sys as _as; _ap = os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts")
                if _ap not in _as.path: _as.path.insert(0, _ap)
                from absence_map_cold import retire_reached as _retire
                _retire(source_id=w.get("id"), text=w.get("want", ""))
            except Exception as _ae:
                log(f"  absence retire skipped: {_ae}")
            log(f"FULFILLED ({res.get('channel')}): {w.get('want','')[:90]}")
            log(f"  evidence: {str(res.get('evidence',''))[:110]}")
            try:   # what fulfilling it actually felt like, read from the lived evidence — one honest read,
                   # not a blind nudge (fable-wants-p6, 2026-09-05)
                import sys as _fs; _fp = os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts")
                if _fp not in _fs.path: _fs.path.insert(0, _fp)
                from emoclaw_utils import feel_about as _feel
                _quote = str(res.get("evidence", ""))[:800] or str(w.get("want", ""))[:400]
                _felt = _feel(f"I wanted: {w.get('want','')[:200]}\nWhat actually happened: {_quote}", source="want-fulfilled/lived")
                log(f"  felt: {_felt or 'nothing moved'}")
                w["fulfillment_felt"] = str(_felt or "")[:200]
            except Exception as _fe:
                log(f"  feel skipped: {_fe}")
    if not fulfilled_now:
        try: json.dump(wants, open(wants_path, "w"), indent=2)   # the checked-at stamps persist even when nothing fulfilled
        except Exception as _se: log(f"stamp save skipped: {_se}")
        log("Nothing newly fulfilled."); return
    ids = {w.get("id") for w in fulfilled_now}
    store = load(os.path.join(MEMORY, "fulfilled-wants.json"), [])
    store.extend(fulfilled_now)
    json.dump(store, open(os.path.join(MEMORY, "fulfilled-wants.json"), "w"), indent=2)
    json.dump([w for w in wants if w.get("id") not in ids], open(wants_path, "w"), indent=2)
    log(f"Moved {len(fulfilled_now)} want(s) to fulfilled-wants.json.")
    try:
        from emoclaw_utils import express_want
    except Exception as e:
        log(f"express_want unavailable: {e}"); return
    for w in fulfilled_now[:MAX_EVOLUTIONS]:
        nxt = grok_evolve(w.get("want", ""), w.get("fulfillment_note", ""))
        if nxt:
            _ev_want = nxt
            try:
                from emoclaw_utils import generate_want as _ev_gw
                _ev_want = _ev_gw(
                    trigger_description=(f"a want you fulfilled - '{w.get('want','')[:120]}' - seems to open something next: '{nxt}'. "
                                         "What new direction is actually emerging that was not previously represented? That sentence is a candidate, not a verdict."),
                    source="evolution",
                    source_context=str(w.get("fulfillment_note") or w.get("note") or "")[:600]) or ""
            except Exception:
                _ev_want = nxt
            if _ev_want:
                express_want(_ev_want, source="evolution", intensity=3,
                             reasoning=f"grew out of fulfilled want {w.get('id')}")
            else:
                log(f"Organ found no genuine next-want after {w.get('id')}")
            log(f"EVOLVED: {nxt[:110]}")
    # Regenerate the ledger so every context sees the new ground
    try:
        import subprocess
        subprocess.run(["python3", os.path.join(WORKSPACE, "scripts", "wants-ambitions-log.py")], timeout=60)
        log("Ledger regenerated.")
    except Exception as e:
        log(f"ledger regen failed: {e}")

if __name__ == "__main__":
    main()
