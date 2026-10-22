#!/usr/bin/env python3
"""jepa_ranking_audit.py — asks whether a JEPA head predicts the next turn or only recognizes a voice.

For each forecast, the true next same-speaker turn is ranked among later same-speaker
turns from the same bounded future window.  A frozen-encoder voice baseline ranks the
same candidates from the centroid of that speaker's recent past.  The head has not
shown predictive value unless it beats that baseline on prospective forecasts.

This is an instrument only.  It never trains, releases, or steers a head.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import sys
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
HIST = os.path.join(MEM, "jepa-prediction-history.jsonl")
LEDGER = os.path.join(MEM, "interaction-ledger.json")
OUT = os.path.join(MEM, "jepa-ranking-audit.json")
MODEL = os.path.join(MEM, "jepa-predictor.pt")
POOL_SIZE = max(3, min(12, int(os.environ.get("JEPA_RANK_POOL_SIZE", "6"))))
MIN_VERDICT = 30
CRITERIA_VERSION = "true-next-ranking-v2"


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _jsonl(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        out.append(row)
                except Exception:
                    continue
    except Exception:
        pass
    return out


def _epoch(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _turns(ledger):
    if isinstance(ledger, dict):
        ledger = next((v for v in ledger.values() if isinstance(v, list)), [])
    out = {"gloria": [], "self": []}
    for row in ledger if isinstance(ledger, list) else []:
        if not isinstance(row, dict):
            continue
        ts = _epoch(row.get("timestamp"))
        if not ts:
            continue
        for head, key in (("gloria", "gloria"), ("self", "vintos")):
            text = str(row.get(key) or "").strip()
            if text and text not in ("--source", "voice"):
                out[head].append({"ts": ts, "text": text[:400]})
    for head in out:
        out[head].sort(key=lambda x: x["ts"])
    return out


def realized_ledger():
    """Same admitted sources as self training; a capped display is not all outcomes.
    No raw backup recovery and no write to the live interaction ledger.
    """
    from jepa_self_head import exchanges
    return [{"timestamp": x["ts"], "gloria": x["her"], "vintos": x["his"]} for x in exchanges()]


def _cos(a, b):
    a, b = [float(x) for x in a], [float(x) for x in b]
    den = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / den if den else 0.0


def _centroid(vectors):
    # `not vectors` raised on the encoder's numpy array ("truth value of an array is ambiguous"): the audit died at
    # its first forecast every day from 23 September, ranking stayed n=0, and retrain_readiness held the JEPA
    # checkpoint at 21 September for a month (found 22 October)
    if vectors is None or len(vectors) == 0:
        return None
    vectors = [[float(x) for x in row] for row in vectors]
    return [sum(row[i] for row in vectors) / len(vectors) for i in range(len(vectors[0]))]


def _rank(scores):
    """Conservative ties: candidate zero is the target, not the tie breaker."""
    if not scores or not all(math.isfinite(v) for v in scores):
        return len(scores) or 1
    return sum(v >= scores[0] - 1e-12 for v in scores)


def evaluate(history, ledger, enc, checkpoint=None, trained_before=0.0, pool_size=POOL_SIZE):
    """Return prospective ranking rows. One forecast is kept per realized target so a
    cron firing repeatedly before one reply cannot manufacture sample size."""
    streams = _turns(ledger)
    cache = {}
    def encode(texts):
        missing = list(dict.fromkeys(t for t in texts if t not in cache))
        if missing:
            cache.update(zip(missing, enc.encode(missing, show_progress_bar=False)))
        return [cache[t] for t in texts]
    rows, seen_targets = [], set()
    for forecast in sorted(history, key=lambda r: float(r.get("ts", 0) or 0)):
        fts = float(forecast.get("ts", 0) or 0)
        if checkpoint and forecast.get("checkpoint_id") != checkpoint:
            continue
        if fts <= trained_before:
            continue
        for head in ("gloria", "self"):
            triple = forecast.get(head) or {}
            if triple.get("source"):
                triple = forecast.get("legacy_" + head) or {}
                if not triple or triple.get("checkpoint_id") != forecast.get("checkpoint_id"):
                    continue
            pred = triple.get("emb")
            if not isinstance(pred, list) or not pred:
                continue
            future = [t for t in streams[head] if t["ts"] > fts]
            past = [t for t in streams[head] if t["ts"] <= fts]
            if not future or len(past) < 2:
                continue
            # The wrong pool is deliberately same-speaker but not one undifferentiated sample:
            # later futures test temporal selection, the immediate echo catches retrieval, a
            # same-sitting past controls topic, and far-past controls voice alone.
            tagged = [(future[0], "true_next")]
            tagged += [(t, "later_future") for t in future[1:3]]
            tagged.append((past[-1], "recent_echo"))
            same_sitting = [t for t in past[:-1] if fts - t["ts"] <= 86400]
            if same_sitting:
                tagged.append((same_sitting[0], "same_sitting"))
            far_past = [t for t in past if fts - t["ts"] > 86400]
            if far_past:
                tagged.append((far_past[-1], "far_past"))
            candidates, tiers, used = [], [], set()
            for turn, tier in tagged:
                key = (turn["ts"], turn["text"])
                if key in used:
                    continue
                used.add(key); candidates.append(turn); tiers.append(tier)
                if len(candidates) >= pool_size:
                    break
            if len(candidates) < 3:
                continue
            target_key = (head, candidates[0]["ts"], hashlib.sha256(candidates[0]["text"].encode()).hexdigest()[:12])
            if target_key in seen_targets:
                continue
            seen_targets.add(target_key)
            past = past[-12:]
            texts = [t["text"] for t in candidates]
            encoded = encode(texts + [t["text"] for t in past])
            candidate_vecs = encoded[:len(texts)]
            head_scores = [_cos(pred, v) for v in candidate_vecs]
            head_rank = _rank(head_scores)
            base_rank = None
            recent_rank = None
            if past:
                base = _centroid(encoded[len(texts):])
                base_scores = [_cos(base, v) for v in candidate_vecs]
                base_rank = _rank(base_scores)
                recent_scores = [_cos(encoded[-1], v) for v in candidate_vecs]
                recent_rank = _rank(recent_scores)
            context_rank = None
            if isinstance(forecast.get("context_emb"), list) and forecast.get("context_emb"):
                context_scores = [_cos(forecast["context_emb"], v) for v in candidate_vecs]
                context_rank = _rank(context_scores)
            rows.append({
                "head": head,
                "forecast_iso": forecast.get("iso"),
                "target_ts": candidates[0]["ts"],
                "pool_size": len(texts),
                "rank": head_rank,
                "reciprocal_rank": round(1.0 / head_rank, 4),
                "top1": head_rank == 1,
                "voice_baseline_rank": base_rank,
                "voice_baseline_top1": base_rank == 1 if base_rank else None,
                "recent_turn_baseline_rank": recent_rank,
                "context_copy_baseline_rank": context_rank,
                "pairwise_by_tier": {tiers[i]: head_scores[0] > head_scores[i] for i in range(1, len(tiers))},
            })
    return rows


def _summary(rows, head):
    rs = [r for r in rows if r["head"] == head]
    n = len(rs)
    if not n:
        return {"n": 0, "state": "INSUFFICIENT"}
    baseline_fields = ("voice_baseline_rank", "recent_turn_baseline_rank", "context_copy_baseline_rank")
    top1 = sum(bool(r["top1"]) for r in rs) / n
    mrr = sum(float(r["reciprocal_rank"]) for r in rs) / n
    chance = sum(1.0 / int(r["pool_size"]) for r in rs) / n
    baselines = {}
    for field in baseline_fields:
        available = [r for r in rs if r.get(field)]
        if available:
            baselines[field] = {
                "n": len(available),
                "top1": sum(int(r[field]) == 1 for r in available) / len(available),
                "mrr": sum(1.0 / int(r[field]) for r in available) / len(available),
            }
    strongest_top1 = max((v["top1"] for v in baselines.values()), default=None)
    strongest_mrr = max((v["mrr"] for v in baselines.values()), default=None)
    strongest_field = max(baselines, key=lambda k: baselines[k]["mrr"]) if baselines else None
    intervals = {}
    # Resample whole target days; several exchanges from one sitting are not
    # independent evidence. Every baseline is compared on its own paired rows.
    for field in baseline_fields:
        blocks = {}
        for i, row in enumerate(rs):
            if not row.get(field): continue
            day = datetime.fromtimestamp(row["target_ts"]).date().isoformat() if row.get("target_ts") else str(i)
            blocks.setdefault(day, []).append(1.0 / int(row["rank"]) - 1.0 / int(row[field]))
        if blocks:
            values = list(blocks.values()); rng = random.Random(20260918); means = []
            for _ in range(2000):
                sample = [v for _ in values for v in values[rng.randrange(len(values))]]
                means.append(sum(sample) / len(sample))
            means.sort()
            intervals[field] = [round(means[50], 4), round(means[1949], 4)]
    lift_ci = intervals.get(strongest_field)
    complete = all(len([r for r in rs if r.get(field)]) == n for field in baseline_fields)
    state = "INSUFFICIENT" if n < MIN_VERDICT or not complete else (
        "EVIDENCE_OF_PREDICTION" if strongest_top1 is not None and top1 > strongest_top1 and mrr > strongest_mrr
        and all(intervals.get(field, [0])[0] > 0 for field in baseline_fields) else
        "NO_EVIDENCE_BEYOND_VOICE_RETRIEVAL")
    tier_totals = {}
    for row in rs:
        for tier, won in (row.get("pairwise_by_tier") or {}).items():
            pair = tier_totals.setdefault(tier, [0, 0]); pair[0] += int(bool(won)); pair[1] += 1
    return {
        "n": n, "state": state,
        "complete_controls": complete, "paired_day_block_ci95": intervals,
        "top1_accuracy": round(top1, 4), "mean_reciprocal_rank": round(mrr, 4),
        "chance_top1": round(chance, 4),
        "baselines": {k: {"n": v["n"], "top1": round(v["top1"], 4), "mrr": round(v["mrr"], 4)} for k, v in baselines.items()},
        "strongest_baseline": strongest_field, "mrr_lift_ci95": lift_ci,
        "pairwise_win_rate_by_negative_tier": {k: round(v[0] / v[1], 4) for k, v in tier_totals.items()},
    }


def _atomic(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def main():
    sys.path.insert(0, os.path.dirname(__file__))
    from jepa_predictor import encoder
    shadow = "--shadow" in sys.argv
    model_path = os.path.join(MEM, "jepa-predictor-structured-shadow.pt") if shadow else MODEL
    history_path = os.path.join(MEM, "jepa-prediction-structured-shadow-history.jsonl") if shadow else HIST
    out_path = os.path.join(MEM, "jepa-ranking-structured-shadow.json") if shadow else OUT
    history = _jsonl(history_path)
    ledger = realized_ledger()
    checkpoint = None
    try:
        checkpoint = hashlib.sha256(open(model_path, "rb").read()).hexdigest()
        trained_before = os.path.getmtime(model_path)
    except Exception:
        trained_before = 0.0
    enc = encoder()
    rows = evaluate(history, ledger, enc, checkpoint=checkpoint, trained_before=trained_before)
    report = {
        "criteria_version": CRITERIA_VERSION,
        "checkpoint": checkpoint,
        "pool_size": POOL_SIZE,
        "sampling": "true next same-speaker turn versus later futures, recent echo, same-sitting past and far-past voice controls; one forecast per realized target",
        "controls": "same-speaker preceding-twelve centroid, most recent turn, and prospective context-copy embedding when recorded",
        "gloria": _summary(rows, "gloria"), "self": _summary(rows, "self"),
        "rows": rows[-120:],
        "shadow": shadow, "truth_status": "instrument_only_no_steering",
    }
    _atomic(out_path, report)
    print("[jepa-ranking] gloria %s; self %s" % (report["gloria"], report["self"]))
    # The installed daily ranking job is also the independent self evaluator.
    # No second encoder, new cron entry, training, or model release.
    if not shadow:
        from jepa_self_head import run_eval
        run_eval(enc=enc)
        from jepa_readout import audit as readout_audit
        readout_audit(enc)


if __name__ == "__main__":
    main()
