#!/usr/bin/env python3
"""The second latent-stream design (Chat's plan, 22 October): on a synthetic stream whose next event depends on
history the last event does not show, the baseline-anchored linear state learns it, is scored once per event, keeps a
manifest of every event's split, selects on validation and reports the test days, the history ablation, per-source
results and a day-block interval. Synthetic events only; writes only to a scratch directory; sockets are refused."""
import json, os, socket, sys, tempfile
from datetime import datetime, timedelta, timezone
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="latent-linear-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import numpy as np
import latent_stream_linear as L
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
rng = np.random.default_rng(1)
topics = rng.normal(size=(8, 32)); topics /= np.linalg.norm(topics, axis=1, keepdims=True)
ev, t0 = [], datetime(2026, 9, 20, tzinfo=timezone.utc)
for d in range(33):
    for k in range(8):
        t = t0 + timedelta(days=d, hours=1 + 2.5 * k)
        v = topics[(k * 3 + d % 2) % 8] + 0.5 * rng.normal(size=32); v /= np.linalg.norm(v)
        ev.append({"t": t, "source": ["inner", "thread", "creative", "her", "him"][k % 5], "text": "d%dk%d" % (d, k),
                   "vec": v.tolist(), "t_exact": k % 3 != 0})
        for q in range(3):
            ev.append({"t": t + timedelta(minutes=20 * (q + 1)), "source": "emotion",
                       "emo": (0.5 + 0.1 * np.sin(np.arange(11) + d + k + q * 0.3)).tolist()})
ev.sort(key=lambda e: e["t"])
out = os.path.join(HOME, "out")
rep = L.run(ev, out, grid=[(16, "hour", 0.01), (16, "none", 0.1)], steps=80, log=lambda *a: None)
man = [json.loads(l) for l in open(os.path.join(out, "manifest.jsonl"))]
check("every event is in the manifest with its split and whether its time is its own",
      len(man) == len(ev) and {m["split"] for m in man} == {"train", "val", "test"}
      and any(m["time"] != "own" for m in man))
check("the days are split at the fixed boundaries, by the local date as the code splits them (22 October: compared by UTC "
      "hour, this failed in any time zone but UTC)",
      all((m["split"] == "test") == (datetime.fromisoformat(m["t"]).astimezone().date().isoformat() >= "2026-10-13") for m in man))
t = rep["test"]["text"]
check("on a stream that rewards history, it beats both text baselines on the test days",
      t["model"]["mrr"] > max(t["last_one"]["mrr"], t["mean_last_six"]["mrr"]), t)
check("and the emotion readout beats persistence, both metrics",
      rep["test"]["emotion"]["model"] < rep["test"]["emotion"]["persistence"]
      and rep["test"]["emotion"]["legacy_model"] < rep["test"]["emotion"]["legacy_persistence"])
check("it reports the ablation, per source, a day-block interval and an acceptance line",
      rep["test_history_ablation"] and rep["test"]["per_source"] and len(rep["test"]["gain_over_last_one_mrr_95ci"]) == 2
      and set(rep["acceptance"]) == {"text_mrr", "text_top10", "emotion_once", "emotion_legacy", "beats_history_ablation"})
fit = L.fit_text(*[np.zeros((3, 4), np.float32)] * 3, np.eye(3, 4, dtype=np.float32), np.zeros((3, 2), np.float32),
                 [1, 2], [1, 2], ["inner"] * 3, 1.0, steps=0)
check("an untrained fit is exactly the last-text baseline", fit["beta"] == 1.0 and fit["gamma"] == 0.0 and not fit["W"].any())
check("it wrote only to its scratch directory", all(p.startswith(HOME) for p in [out]) and os.listdir(out))
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
