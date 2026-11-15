#!/usr/bin/env python3
"""JEPA decode-similarity confidence (14 November): the self triple serves a decode-similarity percentile for
the tested self checkpoint, the old confidence is kept beside it, the Gloria confidence is held (its replay
failed), the forecast embeddings never change, and the calibration audit computes the registered prospective
evaluation on its own.

Synthetic data only. Every behaviour check is also run against a mutant of the code it protects; the mutant
must fail it. Scratch HOME and SPARK_WORKSPACE before any import; stub encoder; `requests` fails the suite."""
import json, os, sys, tempfile, types, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="jepa-decode-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
import numpy as np
sys.path.insert(0, os.path.join(REPO, "scripts"))
import jepa_predictor as JP
import jepa_calibration_audit as CA
import jepa_self_head as SH
import calibration as CAL

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:400]) if d and not ok else ""))

def mutant(mod, old, new):
    src = open(mod.__file__).read()
    assert src.count(old) == 1, "mutation anchor not unique: %r" % old
    m = types.ModuleType(mod.__name__ + "_mutant"); m.__file__ = mod.__file__
    exec(compile(src.replace(old, new), mod.__file__, "exec"), m.__dict__)
    return m

def killed(name, probe, mod, old, new):
    try:
        survived = bool(probe(mutant(mod, old, new)))
    except Exception:
        survived = False
    check("mutation killed: " + name, not survived)

check("every path is scratch", all(str(p).startswith(HOME) for p in (JP.MEMORY, JP.CHAT, JP.OUT, CA.MEM, SH.MEMORY)))
iso = lambda t: datetime.fromtimestamp(t).isoformat()
SPEC = {"checkpoint_id": "ck-self", "source": "self-head-v2", "mode": "ahead", "reference": (0.2, 0.4, 0.6, 0.8)}

# ------------------------------------------------------------------ 1. the mapping
print("--- 1. decode similarity -> confidence: same range, same direction ---")
def probe_map(J):
    vals = [J.decode_confidence(d, SPEC) for d in (0.1, 0.3, 0.5, 0.7, 0.9)]
    return vals == [0.0, 0.25, 0.5, 0.75, 1.0] and all(0.0 <= v <= 1.0 for v in vals)
check("a percentile of the reference rows: 0 below them, 1 above them, rising with similarity", probe_map(JP))
killed("direction flipped", probe_map, JP, "return round(bisect.bisect_right(ref, d) / float(len(ref)), 3)",
       "return round(1 - bisect.bisect_right(ref, d) / float(len(ref)), 3)")
check("no spec, no similarity, or a non-number is no confidence (never a guess)",
      JP.decode_confidence(.5, None) is None and JP.decode_confidence(None, SPEC) is None
      and JP.decode_confidence(float("nan"), SPEC) is None and JP.decode_confidence("x", SPEC) is None)
ref = JP.SELF_DECODE_CONFIDENCE["reference"]
check("the installed self reference is the 30 replay rows, sorted, bound to one checkpoint",
      len(ref) == 30 and list(ref) == sorted(ref) and len(JP.SELF_DECODE_CONFIDENCE["checkpoint_id"]) == 64
      and JP.SELF_DECODE_CONFIDENCE["source"] == "self-head-v2" and JP.SELF_DECODE_CONFIDENCE["mode"] == "ahead")
check("the Gloria decode confidence is held (its replay failed)", JP.GLORIA_DECODE_CONFIDENCE is None)
evid = json.load(open(os.path.join(REPO, "docs", "review-evidence", "jepa-decode-confidence-20261114", "result.json")))
check("the installed reference is the replay's own rows, and the replay verdicts are what the code does",
      list(ref) == evid["self"]["decode_similarity_sorted"] and evid["self"]["pass"] is True and evid["gloria"]["pass"] is False)

def probe_applies(J):
    ok = {"source": "self-head-v2", "checkpoint_id": "ck-self", "mode": "ahead"}
    return (J._self_decode_applies(ok, SPEC) and not J._self_decode_applies(dict(ok, checkpoint_id="other"), SPEC)
            and not J._self_decode_applies(dict(ok, source="anchored-readout-v1"), SPEC)
            and not J._self_decode_applies(dict(ok, mode="on_message"), SPEC) and not J._self_decode_applies(None, SPEC))
check("served only for the tested self forecast: that checkpoint, that source, ahead mode", probe_applies(JP))
killed("checkpoint binding dropped", probe_applies, JP, 'and self_fc.get("checkpoint_id") == spec["checkpoint_id"]', "")

# ------------------------------------------------------------------ 2. the audit's prospective evaluation
print("--- 2. the registered prospective evaluation is computed by the audit ---")
B = 1.79e9
def grow(i, dsim, conf, err, trig="after_reply", day="2026-11-20", ver=CA.DECODE_VERSION):
    return {"iso": day + "T10:%02d" % (i % 60), "ts": B + i, "trigger": trig, "decode_version": ver,
            "g_conf": conf, "g_err": err, "g_dsim": dsim}
def srow(i, dsim, coh, err, day="2026-11-20"):
    # s_conf is the clipped percentile (all 1.0 here: ties); the registered statistic is the raw s_dsim
    return {"iso": day + "T11:%02d" % (i % 60), "ts": B + i, "trigger": "cron", "s_conf": 1.0, "s_dsim": dsim,
            "s_coherence": coh, "s_err": err}
rng = np.random.default_rng(11)
g_good = [grow(i, 1 - i / 40, float(rng.random()), i / 40) for i in range(30)]
g_bad_later = [grow(100 + i, i / 40, float(rng.random()), i / 40) for i in range(60)]
s_good = [srow(i, 1 - i / 40, float(rng.random()), i / 40) for i in range(30)]
P = CA.preregistered_decode
check("29 rows are still collecting", P(g_good[:29], s_good[:29])["gloria"]["state"] == "COLLECTING"
      and P(g_good[:29], s_good[:29])["self"]["state"] == "COLLECTING")
check("Gloria: cron rows, rows not written by the decode code, and rows before registration do not count",
      P([dict(r, trigger="cron") for r in g_good], [])["gloria"]["state"] == "COLLECTING"
      and P([dict(r, decode_version=None) for r in g_good], [])["gloria"]["state"] == "COLLECTING"
      and P([dict(r, iso="2026-11-13T10:00") for r in g_good], [])["gloria"]["state"] == "COLLECTING")
def probe_first(C):
    v = C.preregistered_decode(g_good + g_bad_later, s_good + [srow(100 + i, i / 40, .5, i / 40) for i in range(60)])
    return v["gloria"]["state"] == "PASS" and v["gloria"]["n"] == 30 and v["self"]["state"] == "PASS"
check("decode similarity that tracks error passes; later contrary rows never change the verdict", probe_first(CA))
killed("self scored on the tied percentile instead of the raw similarity", probe_first, CA,
       '"s_dsim", "s_coherence", "s_err"))', '"s_conf", "s_coherence", "s_err"))')
FZ = os.path.join(MEM, "frozen-decode.json")
def probe_frozen(C):
    if os.path.exists(FZ): os.remove(FZ)
    a = C.preregistered_decode(g_good, s_good, frozen_path=FZ)
    # the first 30 later change (an exchange forgotten, a readout reinstalled): the verdict does not
    b = C.preregistered_decode(g_bad_later, [srow(100 + i, i / 40, .5, i / 40) for i in range(60)], frozen_path=FZ)
    return (a["gloria"]["state"] == a["self"]["state"] == "PASS" and b["gloria"]["state"] == b["self"]["state"] == "PASS"
            and b["gloria"].get("frozen") is True and len(json.load(open(FZ))["gloria"]["scored_rows_ts"]) == 30)
check("scored once: the first verdict is frozen with its rows and reported as it was", probe_frozen(CA))
killed("freeze ignored", probe_frozen, CA, 'if isinstance(frozen.get(name), dict) and frozen[name].get("state") in ("PASS", "FAIL"):', "if False:")
if os.path.exists(FZ): os.remove(FZ)
check("a collecting arm is not frozen", CA.preregistered_decode(g_good[:5], [], frozen_path=FZ)["gloria"]["state"] == "COLLECTING"
      and not os.path.exists(FZ))
killed("scored on the latest rows", probe_first, CA, 'first = elig[:reg["n"]]\n        err = [r[err_k]', 'first = elig[-reg["n"]:]\n        err = [r[err_k]')
def probe_control(C):
    tied = [dict(r, g_conf=r["g_dsim"]) for r in g_good]
    return C.preregistered_decode(tied, [])["gloria"]["state"] == "FAIL"
check("matching the control (the served readout confidence) is a FAIL", probe_control(CA))
killed("control margin dropped", probe_control, CA,
       'and mono <= ctrl - reg["pass"]["beat_control_by"])\n        out[name] = {"state": "PASS" if ok else "FAIL", "n": len(first), "monotonicity_decode_vs_err"',
       ')\n        out[name] = {"state": "PASS" if ok else "FAIL", "n": len(first), "monotonicity_decode_vs_err"')
check("the registration uses the calibration v2 numbers and 30 targets",
      CA.PREREGISTERED_DECODE["n"] == 30 and CA.PREREGISTERED_DECODE["registered"] == "2026-11-14"
      and CA.PREREGISTERED_DECODE["pass"] == {"max_monotonicity": CAL.CRITERIA["max_monotonicity"], "beat_control_by": CAL.CRITERIA["beat_control_by"]})
prereg = json.load(open(os.path.join(REPO, "docs", "review-evidence", "jepa-decode-confidence-20261114", "prereg.json")))
check("the code's registration matches the committed file", prereg["prospective"]["n"] == CA.PREREGISTERED_DECODE["n"]
      and prereg["prospective"]["id"] == CA.PREREGISTERED_DECODE["id"])

class Enc:
    def __init__(self, vec=(1.0, 0.0)): self.vec = vec
    def encode(self, texts, **kw): return np.asarray([list(self.vec) for _ in texts], dtype="float32")

class TextEnc:
    """A different, stable direction per text, so nearest turns and similarities can actually differ."""
    def encode(self, texts, **kw):
        import hashlib
        a = [int(hashlib.md5(str(t).encode()).hexdigest()[:8], 16) / 0xffffffff * 6.283 for t in texts]
        return np.asarray([[np.cos(x), np.sin(x)] for x in a], dtype="float32")

def hrow(t, ctx_t, conf=.7, src=CA.DECODE_VERSION):
    return {"ts": t, "iso": iso(t), "trigger": "cron", "decode_confidence_version": CA.DECODE_VERSION,
            "self": {"confidence": conf, "confidence_source": src, "coherence": .3, "emb": [1.0, 0.0],
                     "decode_similarity_admitted": conf,
                     "source": "self-head-v2", "context_last_ts": iso(ctx_t)},
            "legacy_self": {"checkpoint_id": "pt", "confidence": .4, "emb": [0.0, 1.0]}}
turns = [(B + 50, "her a", "his a"), (B + 150, "her b", "his b"), (B + 250, "her c", "his c")]
def probe_selfjoin(C):
    # A forecast at B+160 whose context ends at B+50 would join his b (B+150), already said: dropped. A row
    # without the decode source is not this population. Context B+150, forecast B+200 -> his c, once.
    rs = C.served_self_rows([hrow(B + 160, B + 50), hrow(B + 190, B + 150, conf=.1, src=None),
                             hrow(B + 200, B + 150), hrow(B + 201, B + 150)], turns, Enc())
    return len(rs) == 1 and rs[0]["s_err"] == 0.0 and rs[0]["s_dsim"] == .7 and rs[0]["s_coherence"] == .3
check("self join: his first reply after the context, said after the forecast, once per target", probe_selfjoin(CA))
killed("reply already said is joined", probe_selfjoin, CA, "if not target or target[0] <= fts:", "if not target:")
killed("decode-source filter dropped", probe_selfjoin, CA,
       'if s.get("confidence_source") != DECODE_VERSION or not s.get("emb")', 'if not s.get("emb")')

def probe_legacy_axis(C):
    # the shared-checkpoint self axis (retrain gate, calibration.verdict) still reads legacy_self
    h = dict(hrow(B + 100, B + 50), checkpoint_id="pt")
    rs = C.joined_rows([h], turns, Enc(), "pt", 0, arrivals={})
    return len(rs) == 1 and rs[0]["s_conf"] == .4 and rs[0]["decode_version"] == C.DECODE_VERSION
check("the shared-checkpoint audit keeps reading legacy_self, and rows carry the decode marker", probe_legacy_axis(CA))
killed("marker not carried", probe_legacy_axis, CA, '"decode_version": h.get("decode_confidence_version")}', '"decode_version": None}')

print("--- the audit itself, with too few shared-checkpoint rows, still writes the registered evaluations ---")
import jepa_ranking_audit as RA
open(CAL.MODEL, "w").write("weights")
C0 = datetime(2026, 11, 20, 12).timestamp()   # after the registration date
open(CA.HIST, "w").write(json.dumps(hrow(C0 + 200, C0 + 150)) + "\n")
_saved = (JP.encoder, RA.realized_ledger, RA.load_arrivals)
JP.encoder = lambda: Enc(); RA.realized_ledger = lambda: [{"timestamp": iso(C0 + 250), "gloria": "her c", "vintos": "his c"}]
RA.load_arrivals = lambda *a, **k: {}
try:
    CA.main()
    rep = json.load(open(CA.OUT))
    check("early-return path: INSUFFICIENT, yet preregistered_decode is computed (one self row collecting)",
          rep.get("verdict") == "INSUFFICIENT" and rep["preregistered_decode"]["self"] == {"state": "COLLECTING", "n": 1, "needed": 30})
finally:
    JP.encoder, RA.realized_ledger, RA.load_arrivals = _saved
    os.remove(CAL.MODEL); os.remove(CA.HIST)

# ------------------------------------------------------------------ 3. a real forecast, when torch is installed
try:
    import torch
    real_torch = hasattr(torch, "nn")
except Exception:
    real_torch = False
if real_torch:
    print("--- 3. a real forecast (torch present): self served, Gloria held, embeddings unchanged ---")
    net = JP.make_net(2); torch.save({"state": net.state_dict(), "dim": 2, "presence_trained": False}, JP.MODEL)
    chat = [{"role": ("user" if i % 2 == 0 else "assistant"), "content": "turn %d" % i, "timestamp": iso(time.time() - 3000 + i * 60)} for i in range(14)]
    json.dump(chat, open(JP.CHAT, "w"))
    sys.modules["latent_feed"] = types.SimpleNamespace(refresh=lambda **k: None)
    SELF_CK = JP.SELF_DECODE_CONFIDENCE["checkpoint_id"]
    def fake_self(ck):
        return lambda enc, **k: {"emb": np.asarray([0.9, 0.3], dtype="float32"), "confidence": None,
                                 "qualification": "unqualified_not_predictive", "mode": "ahead", "coherence": 0.42,
                                 "source": "self-head-v2", "schema": "self-ledger-v2", "checkpoint_id": ck,
                                 "context_last_ts": iso(time.time() - 100), "context_last_turn_id": "", "n_recent": 6}
    REAL_FORECAST, REAL_EXS = SH.forecast, SH.exchanges
    ADMITTED = ["admitted reply %d" % i for i in range(15)]   # his admitted replies: not the chat rows' texts
    def run(J, ck=SELF_CK, admitted=ADMITTED):
        SH.forecast = fake_self(ck)
        SH.exchanges = lambda *a, **k: [{"her": "h", "his": t, "at": 0, "ts": ""} for t in admitted] + [{"her": "h", "his": "", "at": 0, "ts": ""}]
        hp = os.path.join(MEM, "hist-%s.jsonl" % id(J))
        for p in (J.OUT, hp):
            if os.path.exists(p): os.remove(p)
        try:
            J.predict(history_path=hp, enc=TextEnc(), trigger="after_reply", side_feeds=False)
        finally:
            SH.forecast, SH.exchanges = REAL_FORECAST, REAL_EXS
        return json.load(open(J.OUT)), json.loads(open(hp).read().splitlines()[-1])
    out, row = run(JP)
    s = out["self"]
    E = TextEnc().encode(ADMITTED[-12:]); v = np.asarray([0.9, 0.3]) / np.linalg.norm([0.9, 0.3])
    expect_adm = round(float(max(E @ v / np.linalg.norm(E, axis=1))), 3)
    def probe_served(J):
        o, r = run(J)
        x = o["self"]
        return (x["decode_similarity_admitted"] == expect_adm
                and x["confidence"] == JP.decode_confidence(expect_adm, JP.SELF_DECODE_CONFIDENCE)
                and x["confidence_placeholder"] is False and x["legacy_confidence"] is None
                and x["legacy_confidence_placeholder"] is True and x["legacy_qualification"] == "unqualified_not_predictive"
                and x["confidence_source"] == JP.DECODE_CONFIDENCE_VERSION
                and o["qualification"]["self"] == "qualified" and o["decode_confidence"]["self"] == "served"
                and r["self"]["confidence"] == x["confidence"] and r["self"]["legacy_confidence"] is None
                and r["self"]["decode_similarity_admitted"] == expect_adm
                and r["self"]["confidence_source"] == JP.DECODE_CONFIDENCE_VERSION and r["self"]["coherence"] == 0.42
                and r["decode_confidence_version"] == JP.DECODE_CONFIDENCE_VERSION)
    check("self: the served confidence is the percentile of the similarity to his last 12 ADMITTED replies; the old one (a placeholder) is kept beside it, on the file and the history row", probe_served(JP))
    check("the served similarity is the replay's (admitted replies), not the chat-row decode_similarity",
          s["decode_similarity"] != s["decode_similarity_admitted"])
    killed("decode confidence not served", probe_served, JP, "    if _s_dc is not None:\n        _self_decode = {", "    if False:\n        _self_decode = {")
    killed("similarity taken against the chat rows", probe_served, JP,
           "_s_dc = decode_confidence(_s_adm, SELF_DECODE_CONFIDENCE)", "_s_dc = decode_confidence(_s_sim, SELF_DECODE_CONFIDENCE)")
    off = mutant(JP, "    if _self_decode_applies(_self_fc):\n        try:", "    if False:\n        try:")
    out0, row0 = run(off)
    check("ranking cannot move: both heads' forecast embeddings, nearest turns and novelty are identical with and without the change",
          row["gloria"]["emb"] == row0["gloria"]["emb"] and row["self"]["emb"] == row0["self"]["emb"]
          and row["legacy_self"]["emb"] == row0["legacy_self"]["emb"]
          and out["gloria_forecast_nearest"] == out0["gloria_forecast_nearest"] and s["nearest"] == out0["self"]["nearest"]
          and s["novelty"] == out0["self"]["novelty"] and out["novelty"] == out0["novelty"])
    check("Gloria is held: the top-level and Gloria confidence are exactly what they were", out["confidence"] == out0["confidence"]
          and out["gloria"]["confidence"] == out0["gloria"]["confidence"] and "legacy_confidence" not in out["gloria"]
          and row["gloria"] == row0["gloria"] and out["variance_qualified"] == out0["variance_qualified"]
          and out["steering_allowed"] == out0["steering_allowed"])
    check("without the change the self confidence is the 0.5 placeholder it was", out0["self"]["confidence"] == 0.5
          and out0["self"]["confidence_placeholder"] is True and "legacy_confidence" not in out0["self"])
    none, nrow = run(JP, admitted=[])
    check("no admitted reply: no similarity, so no decode confidence (never a measured-looking 0.0)",
          none["self"]["confidence"] == 0.5 and none["self"]["confidence_placeholder"] is True
          and "confidence_source" not in nrow["self"])
    other, orow = run(JP, ck="0" * 64)
    check("another self checkpoint keeps its own confidence (untested, not served)", other["self"]["confidence"] == 0.5
          and other["self"]["confidence_placeholder"] is True and "confidence_source" not in orow["self"]
          and other["decode_confidence"]["self"].startswith("not applied"))
    # the one reader of the self confidence (emoclaw's undertow) now reads a measured number, same direction
    try:
        import emoclaw_utils as EU
        json.dump({"self_trajectory": {"declared": ["toward something"]}}, open(os.path.join(MEM, "living-trajectory.json"), "w"))
        sys.modules["latent_feed"] = types.SimpleNamespace(refresh=lambda **k: None, append_context=lambda o, *a, **k: o)
        def directive(conf, placeholder):
            json.dump({"source": "jepa", "self": {"novelty": 0.1, "confidence": conf, "confidence_placeholder": placeholder}},
                      open(os.path.join(MEM, "jepa-prediction.json"), "w"))
            return EU._novelty_directive()
        hi, lo, ph = directive(0.9, False), directive(0.2, False), directive(0.9, True)
        check("consumer: a high decode confidence reads as known ground, a low one as unsure, a placeholder never licenses",
              "know this ground well" in hi and "unsure even of familiar ground" in lo and "unsure even of familiar ground" in ph)
    except ImportError as e:
        print("SKIP consumer check: emoclaw_utils not importable here (%s)" % e)
else:
    print("SKIP 3. real forecast: torch not installed in this interpreter (the _predict checks did NOT run)")

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
