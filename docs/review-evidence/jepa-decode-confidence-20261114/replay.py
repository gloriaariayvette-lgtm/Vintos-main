"""RD-replay (prereg.json, this directory). Offline, on byte copies; counts only, never prints text.

Run with SPARK_WORKSPACE pointing at a scratch workspace whose memory/ holds copies of the chat sources,
jepa-readouts/gloria.npz, jepa-self-head.npz and the self embedding cache. argv[1] = the worktree's scripts/.
"""
import os, sys, json, hashlib
from datetime import datetime

sys.path.insert(0, sys.argv[1])
assert os.environ.get("SPARK_WORKSPACE") and ".vintos" not in os.environ["SPARK_WORKSPACE"], "copies only"
import numpy as np
import jepa_predictor as JP
import jepa_self_head as SH
import jepa_readout as RO
from jepa_calibration_audit import spear

CUTOFF = datetime(2026, 10, 31, 0, 0).timestamp()
MEM = os.path.join(os.environ["SPARK_WORKSPACE"], "memory")
GLORIA_FROM = RO.BOUNDARIES[-1]                      # the readout's test block onward: never fit
SELF_TRAINED = datetime.fromisoformat("2026-10-16T12:13:15.785506").timestamp()


class Enc:
    def __init__(self, enc):
        self.enc, self.cache = enc, {}

    def encode(self, texts, show_progress_bar=False, **kw):
        miss = list(dict.fromkeys(t for t in texts if t not in self.cache))
        if miss:
            vs = self.enc.encode(miss, show_progress_bar=False, batch_size=32)
            self.cache.update(zip(miss, [np.asarray(v, dtype="float32") for v in vs]))
        return np.asarray([self.cache[t] for t in texts], dtype="float32")


def cos(a, b):
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return float(a @ b / (na * nb)) if na and nb else 0.0


def dsim(pred, past, enc):
    if not past:
        return None
    E = enc.encode([t[:300] for t in past])
    return round(max(cos(pred, e) for e in E), 3)


def mrr(P, Y):
    return round(RO.metrics(RO.units(P), RO.units(Y))[0]["mrr"], 4)


def score(rows, control_key):
    n = len(rows); half = n // 2
    d = np.asarray([r["dsim"] for r in rows]); e = np.asarray([r["err"] for r in rows])
    A = np.column_stack([np.ones(half), d[:half]])
    intercept, slope = np.linalg.lstsq(A, e[:half], rcond=None)[0]
    conf = np.clip(1 - (intercept + slope * d) / 2, 0, 1).round(3)
    ctrl = [r[control_key] for r in rows]
    mono, cmono = spear(list(conf), list(e)), spear(ctrl, list(e))
    exp2 = intercept + slope * d[half:]
    out = {"n": n, "first": rows[0]["day"], "last": rows[-1]["day"],
           "map": {"intercept": round(float(intercept), 4), "slope": round(float(slope), 4), "fit_n": half},
           "monotonicity_decode_conf_vs_err": mono, "CONTROL_vs_err": cmono, "control": control_key,
           "raw_decode_similarity_vs_err": spear(list(d), list(e)),
           "decode_similarity_range": [round(float(d.min()), 3), round(float(np.median(d)), 3), round(float(d.max()), 3)],
           "second_half": {"n": n - half, "decode_mono": spear(list(conf[half:]), list(e[half:])),
                           "control_mono": spear(ctrl[half:], list(e[half:])),
                           "map_error_mse": round(float(np.mean((exp2 - e[half:]) ** 2)), 5),
                           "constant_error_mse": round(float(np.mean((e[:half].mean() - e[half:]) ** 2)), 5)},
           "bins_low_mid_high_decode_conf_err": [round(float(e[ix].mean()), 4) for ix in np.array_split(np.argsort(conf, kind="stable"), 3)],
           "mean_cosine_error": round(float(e.mean()), 4)}
    out["pass"] = bool(n >= 30 and mono is not None and cmono is not None and mono <= -0.20
                       and mono <= cmono - 0.10 and slope < 0)
    return out


def main():
    exs = [x for x in SH.exchanges() if x["at"] < CUTOFF]       # nothing at or after the cutoff is encoded
    enc = Enc(JP.encoder())
    model_dir = os.path.join(MEM, "jepa-readouts")
    g_rows, seen = [], set()
    for j, x in enumerate(exs):
        if not x["her"] or x["ts"][:10] < GLORIA_FROM or j == 0 or not exs[j - 1]["his"]:
            continue
        d = hashlib.sha256(x["her"][:400].encode()).hexdigest()
        if d in seen:
            continue
        fc = RO.forecast(enc, "gloria", exs=exs[:j], model_dir=model_dir)
        if fc is None:
            continue
        seen.add(d)
        pred = np.asarray(fc["emb"], dtype="float32")
        past = [e["her"] for e in exs[:j] if e["her"]][-12:]
        y = enc.encode([x["her"][:400]])[0]
        g_rows.append({"day": x["ts"][:10], "dsim": dsim(pred, past, enc), "err": round(1 - cos(pred, y), 4),
                       "readout_confidence": fc["confidence"], "pred": pred, "y": y})
    s_rows, seen = [], set()
    for j, x in enumerate(exs):
        if not x["his"] or x["at"] <= SELF_TRAINED or j == 0:
            continue
        d = hashlib.sha256(x["his"][:400].encode()).hexdigest()
        if d in seen:
            continue
        fc = SH.forecast(enc, exs=exs[:j], mode="ahead", today=x["ts"][:10], persist=False)
        if fc is None:
            continue
        seen.add(d)
        pred = np.asarray(fc["emb"], dtype="float32")
        past = [e["his"] for e in exs[:j] if e["his"]][-12:]
        y = enc.encode([x["his"][:400]])[0]
        s_rows.append({"day": x["ts"][:10], "dsim": dsim(pred, past, enc), "err": round(1 - cos(pred, y), 4),
                       "coherence": fc["coherence"], "self_confidence_placeholder": fc["confidence"] is None,
                       "pred": pred, "y": y})
    res = {"prereg": "prereg.json (this directory)", "cutoff": "2026-10-31T00:00 local (exclusive)"}
    for name, rows, ctrl in (("gloria", g_rows, "readout_confidence"), ("self", s_rows, "coherence")):
        rows = [r for r in rows if r["dsim"] is not None]
        if len(rows) < 4:
            res[name] = {"n": len(rows), "pass": False, "why": "too few rows"}
            continue
        r = score(rows, ctrl)
        P = np.asarray([q["pred"] for q in rows]); Y = np.asarray([q["y"] for q in rows])
        r["mrr_served_forecast"] = mrr(P, Y)
        r["forecast_embedding_sha"] = hashlib.sha256(P.astype("float32").tobytes()).hexdigest()[:16]
        if name == "self":
            r["served_confidence_placeholder_rows"] = sum(q["self_confidence_placeholder"] for q in rows)
            # forecast-time numbers only (no error, no text): the reference a served percentile is read against
            r["decode_similarity_sorted"] = sorted(q["dsim"] for q in rows)
        res[name] = r
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
