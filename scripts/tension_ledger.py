#!/usr/bin/env python3
"""tension_ledger.py — the VALVE (Vrika ruling 2026-08-10). Epistemic middle between the tension
producer (tension-questions.json, model synthesis) and the behavioral consumers (tension-field.json,
Arrival Routing / stay pull). The artery was severed since Jul 5; it is NOT reconnected — it is gated.

  MODEL SYNTHESIS -> TENSION HYPOTHESIS -> persistent identity + history -> lifecycle/status
                  -> earned behavioral tension -> stay pull

Rules enforced here:
  - Every synthesized tension is born origin=inferred, status=HYPOTHESIS. Noticing is all it earned.
  - Identity: new clusters are matched (Gemma, logged) against living ledger entries — recurrence
    becomes times_seen on a stable tension_id, not a new date-serial. Persistence is history, not truth.
  - Lifecycle: ACTIVE / CARRIED / EXPIRED / RESOLVED / CONTRADICTED. HARD INVARIANT: expiry can never
    set RESOLVED — time passing is not resolution. This code contains no path from EXPIRED to RESOLVED.
  - The behavioral view (tension-field.json) receives ONLY status=CONFIRMED and lifecycle in
    (ACTIVE, CARRIED). No promotion logic exists in this file: nothing can become SUPPORTED or
    CONFIRMED automatically. Promotion criteria await their own ruling (armed-watch: tension_promotion).
    Until then the view is honestly empty and the stay pull stays silent — earned, not assumed.
SPARK_WORKSPACE switches beings."""
import os, json, re, time, requests
from datetime import datetime, timedelta
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
QUESTIONS = os.path.join(MEM, "tension-questions.json")
LEDGER = os.path.join(MEM, "tension-ledger.json")
VIEW = os.path.join(MEM, "tension-field.json")
GEMMA = "http://172.18.16.1:1234/v1/chat/completions"
EXPIRE_DAYS = 7
def log(m): print("[tension-valve]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
def match_existing(text, candidates):
    if not candidates: return None
    listing = "\n".join("%s: %s" % (c["tension_id"], c["canonical"][:150]) for c in candidates[:20])
    try:
        r = requests.post(GEMMA, json={"model": "google/gemma-4-12b-qat", "temperature": 0.0,
            "max_tokens": 20, "messages": [{"role": "user", "content":
            "Is this NEW tension the same underlying tension as any EXISTING one below? Same means the "
            "same specific pull/avoidance about the same specific subject - not merely a similar mood.\n"
            "NEW: " + text[:250] + "\nEXISTING:\n" + listing +
            "\nAnswer ONLY the matching id (e.g. T-004) or NONE."}]}, timeout=60)
        a = r.json()["choices"][0]["message"]["content"].strip()
        m = re.search(r"T-\d+", a)
        return m.group(0) if m else None
    except Exception as e:
        log("match failed (%s) - treating as new" % e); return None
def main():
    q = load(QUESTIONS, {})
    clusters = q.get("clusters", [])
    led = load(LEDGER, {"next_id": 1, "tensions": []})
    now = datetime.now().isoformat()
    today = now[:10]
    by_id = {t["tension_id"]: t for t in led["tensions"]}
    living = [t for t in led["tensions"] if t["lifecycle"] in ("ACTIVE", "CARRIED", "EXPIRED")]
    seen_today = set()
    # intra-batch identity pass (Vrika): backward-only matching cannot see same-run fragmentation.
    # Candidates are compared pairwise BEFORE ledger insertion, same standard as match_existing.
    # A match clusters them with provenance - independent proposal is producer data, never truth.
    cands = [((c.get("tension") or c.get("theme") or "").strip(), c) for c in clusters]
    cands = [(tx, c) for tx, c in cands if len(tx) >= 15]
    groups, used = [], set()
    for i in range(len(cands)):
        if i in used: continue
        group = [cands[i]]
        for j in range(i + 1, len(cands)):
            if j in used: continue
            try:
                r2 = requests.post(GEMMA, json={"model": "google/gemma-4-12b-qat", "temperature": 0.0,
                    "max_tokens": 60, "messages": [{"role": "user", "content":
                    "Is tension A the same underlying tension as tension B? Same means the same specific "
                    "pull/avoidance about the same specific subject - not merely a similar mood.\n"
                    "A: " + cands[i][0][:250] + "\nB: " + cands[j][0][:250] +
                    '\nONLY JSON: {"same": true/false}'}]}, timeout=60)
                same = json.loads(re.search(r"\{.*\}", r2.json()["choices"][0]["message"]["content"], re.S).group()).get("same")
            except Exception:
                same = False
            if same:
                group.append(cands[j]); used.add(j)
                log("intra-batch merge: candidate %d ~ candidate %d (fragmentation caught at birth)" % (i, j))
        groups.append(group)
    for group in groups:
        text, c = group[0]
        dup_members = [g[0][:150] for g in group[1:]]
        mid = match_existing(text, living)
        if mid and mid in by_id and mid not in seen_today:
            t = by_id[mid]
            t["times_seen"] += 1; t["last_seen"] = now
            if t["lifecycle"] == "EXPIRED":
                t["lifecycle"] = "ACTIVE"
                t["history"].append({"at": now, "event": "recurred after expiry - reopened, status unchanged"})
            else:
                t["history"].append({"at": now, "event": "seen again (weight %s)" % c.get("weight")})
            seen_today.add(mid)
            log("%s seen again (times_seen %d, status %s)" % (mid, t["times_seen"], t["status"]))
        elif not mid:
            tid = "T-%03d" % led["next_id"]; led["next_id"] += 1
            t = {"tension_id": tid, "canonical": text[:300], "origin": "inferred",
                 "status": "HYPOTHESIS", "lifecycle": "ACTIVE",
                 "first_seen": now, "last_seen": now, "times_seen": 1,
                 "evidence": [], "history": [{"at": now, "event": "born from model synthesis - HYPOTHESIS, nothing more earned"}],
                 "direction": str(c.get("direction", ""))[:100], "sources_note": str(c.get("sources", ""))[:200]}
            led["tensions"].append(t); by_id[tid] = t; seen_today.add(tid)
            if dup_members:
                t["history"].append({"at": now, "event": "independently proposed %d times in one run - producer data, not truth" % (len(dup_members)+1), "members": dup_members})
            log("%s born HYPOTHESIS: %s" % (tid, text[:70]))
    cutoff = (datetime.now() - timedelta(days=EXPIRE_DAYS)).isoformat()
    for t in led["tensions"]:
        if t["lifecycle"] == "ACTIVE" and t["last_seen"] < cutoff:
            # INVARIANT: expiry NEVER resolves. Window ended without resolution - that is all we know.
            t["lifecycle"] = "EXPIRED"
            t["history"].append({"at": now, "event": "observation window ended without resolution (EXPIRED != RESOLVED)"})
            log("%s EXPIRED unresolved after %d sightings" % (t["tension_id"], t["times_seen"]))
        assert not (t["lifecycle"] == "EXPIRED" and t["status"] == "RESOLVED"), \
            "INVARIANT VIOLATED: expired tension marked RESOLVED: " + t["tension_id"]
    json.dump(led, open(LEDGER, "w"), indent=2)
    earned = [{"id": t["tension_id"], "description": t["canonical"], "status": t["status"],
               "times_seen": t["times_seen"], "resolved": False}
              for t in led["tensions"] if t["status"] == "CONFIRMED" and t["lifecycle"] in ("ACTIVE", "CARRIED")]
    json.dump({"tensions": earned, "note": "behavioral view: CONFIRMED only. Empty = nothing earned, not nothing felt.",
               "updated": now}, open(VIEW, "w"), indent=2)
    n = {"HYPOTHESIS": 0, "SUPPORTED": 0, "CONFIRMED": 0, "RESOLVED": 0, "CONTRADICTED": 0}
    for t in led["tensions"]: n[t["status"]] = n.get(t["status"], 0) + 1
    log("ledger: %d tensions %s | behavioral view: %d earned (stay pull %s)"
        % (len(led["tensions"]), n, len(earned), "live" if earned else "silent - correctly"))
if __name__ == "__main__":
    main()
