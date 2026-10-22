#!/usr/bin/env python3
"""Read-only: the state of his JEPA heads and their neighbours, for Chat's review (22 October). Writes nothing.

  1. each checkpoint: present, when trained, how big; and whether retraining is held (and why)
  2. the forecast ledgers: how many forecasts, over what dates, for which checkpoint
  3. the audits as last written: ranking against the last turn, the speaker's recent centroid and the context copy;
     calibration; the self head's own held-out eval; presence calibration; each with its date
  4. a FRESH ranking audit of the current checkpoint on today's history, computed in memory, never saved
     (only with the torch venv; with plain python3 this part is skipped)
  5. the other latent organs: drift, relational, LAM, latent preparation - their outputs and freshness
  6. the crontab lines that run them

    ~/.vintos/workspace/emotion_model/.venv/bin/python3 jepa_heads_probe.py
"""
import glob, json, os, re, subprocess, sys, time

WS = os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
sys.path.insert(0, os.path.join(WS, "scripts"))


def age(p):
    if not os.path.exists(p): return "MISSING"
    d = (time.time() - os.path.getmtime(p)) / 86400
    return "%s (%s)" % (time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p))),
                        ("%.0f min ago" % (d * 1440)) if d < 1 else ("%.1f days ago" % d))


def load(p, d=None):
    try: return json.load(open(p))
    except Exception: return d


def jsonl(p, limit=200000):
    rows = []
    try:
        with open(p, errors="ignore") as f:
            for line in f.readlines()[-limit:]:
                try: rows.append(json.loads(line))
                except ValueError: pass
    except OSError:
        pass
    return rows


def short(obj, n=900):
    s = json.dumps(obj, sort_keys=True, default=str)
    return s if len(s) <= n else s[:n] + " ...(%d more chars)" % (len(s) - n)


print("== 1. checkpoints ==")
for ck in ("jepa-predictor.pt", "jepa-predictor-structured-shadow.pt", "jepa-self-head.npz", "lam.pt", "reality-ebm.pt"):
    p = os.path.join(MEM, ck)
    print("  %-38s %s%s" % (ck, age(p), ("  %.1f MB" % (os.path.getsize(p) / 1e6)) if os.path.exists(p) else ""))
try:
    import jepa_predictor as J
    for shadow in (False, True):
        ok, why = J.retrain_readiness(J.SHADOW_MODEL if shadow else J.MODEL, shadow=shadow)
        print("  retrain %-8s %s  %s" % ("(shadow)" if shadow else "", "READY" if ok else "HELD", short(why, 400)))
except Exception as e:
    print("  retrain readiness: could not ask (%s)" % str(e)[:120])

print("\n== 2. forecast ledgers ==")
for name in ("jepa-prediction-history.jsonl", "jepa-prediction-structured-shadow-history.jsonl", "jepa-self-forecasts.jsonl"):
    rows = jsonl(os.path.join(MEM, name))
    if not rows:
        print("  %-48s MISSING or empty" % name); continue
    isos = sorted(str(r.get("iso") or r.get("at") or r.get("ts") or "") for r in rows)
    cks = {}
    for r in rows: cks[str(r.get("checkpoint_id"))[:12]] = cks.get(str(r.get("checkpoint_id"))[:12], 0) + 1
    print("  %-48s %d rows, %s .. %s; by checkpoint %s" % (name, len(rows), isos[0][:16], isos[-1][:16], cks))
pend = glob.glob(os.path.join(MEM, "jepa-self-pending", "*"))
print("  %-48s %d pending on-message forecasts" % ("jepa-self-pending/", len(pend)))
led = load(os.path.join(MEM, "interaction-ledger.json"), []) or []
print("  %-48s %d rows (the realized turns the audits join against)" % ("interaction-ledger.json", len(led)))

print("\n== 3. audits as last written ==")
for name in ("jepa-ranking-audit.json", "jepa-ranking-structured-shadow.json", "jepa-calibration.json",
             "jepa-presence-calibration.json", "jepa-self-eval.json", "presence-audit.json"):
    p = os.path.join(MEM, name); d = load(p)
    print("  -- %s, written %s" % (name, age(p)))
    if isinstance(d, dict):
        d = {k: v for k, v in d.items() if k not in ("rows", "joined", "history", "items")}
        print("     " + short(d, 1400))
rel = jsonl(os.path.join(MEM, "calibration-releases.jsonl"))
print("  -- calibration-releases.jsonl: %d releases%s" % (len(rel), ("; last " + short(rel[-1], 300)) if rel else ""))

print("\n== 4. a fresh ranking audit of the current checkpoint (in memory, not saved) ==")
try:
    import hashlib
    import jepa_ranking_audit as A
    ck = os.path.join(MEM, "jepa-predictor.pt")
    checkpoint = hashlib.sha256(open(ck, "rb").read()).hexdigest()
    rows = A.evaluate(jsonl(os.path.join(MEM, "jepa-prediction-history.jsonl")), led, J.encoder(),
                      checkpoint=checkpoint, trained_before=os.path.getmtime(ck))
    for head in ("gloria", "self"):
        print("  %-7s %s" % (head, short(A._summary(rows, head), 1200)))
    all_rows = A.evaluate(jsonl(os.path.join(MEM, "jepa-prediction-history.jsonl")), led, J.encoder())
    print("  every checkpoint, every forecast (not only the current one):")
    for head in ("gloria", "self"):
        print("  %-7s %s" % (head, short(A._summary(all_rows, head), 1200)))
except Exception as e:
    print("  skipped (%s: %s) - run with the torch venv for this part" % (type(e).__name__, str(e)[:160]))

print("\n== 5. the other latent organs ==")
for name in ("jepa-prediction.json", "presence-forecast.json", "drift.json", "relational.json", "lam-forecast.json",
             "latent-preparation.json", "living-trajectory.json", "reality-ebm.json", "withheld.json", "gloria-prediction.json"):
    p = os.path.join(MEM, name); d = load(p)
    keys = (", ".join(sorted(d.keys())[:12]) if isinstance(d, dict) else type(d).__name__) if d is not None else ""
    print("  %-28s %s  %s" % (name, age(p), keys[:150]))
jp = load(os.path.join(MEM, "jepa-prediction.json"), {}) or {}
if jp:
    print("  jepa-prediction.json says: steering_allowed=%s; calibration %s; qualification %s" % (
        jp.get("steering_allowed"), short({k: (v or {}).get("state") for k, v in (jp.get("calibration") or {}).items()}, 200),
        short(jp.get("qualification"), 300)))

print("\n== 6. schedules ==")
try:
    cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10).stdout
except Exception:
    cron = ""
for organ in ("jepa_predictor", "jepa_self_head", "jepa_ranking_audit", "calibration", "presence_audit", "lam.py",
              "drift_head", "relational_head", "latent_preparation", "reality_ebm", "gloria_prediction", "withheld_head"):
    lines = [re.sub(r"\s+", " ", l.strip()) for l in cron.splitlines() if organ in l and not l.strip().startswith("#")]
    print("  %-20s %s" % (organ, ("; ".join(l[:150] for l in lines[:3])) if lines else "no crontab line"))
