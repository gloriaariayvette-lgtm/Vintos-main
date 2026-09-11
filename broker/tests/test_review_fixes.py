#!/usr/bin/env python3
"""The 11 September independent review, findings 9, 10 and 11: calibration cannot
release on stale or incomplete evidence; a reveal cannot claim bytes were verified
when none were; a crashed voice-session close is resumed, not skipped forever."""
import importlib.util, json, os, sys, tempfile, hashlib

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m; spec.loader.exec_module(m); return m

MEM = tempfile.mkdtemp()

print("\n--- F9: calibration releases only on complete, current, checkpoint-bound evidence ---")
C = load("calibration", os.path.join(REPO, "scripts", "calibration.py"))
C.MEMORY = MEM; C.AUDIT = os.path.join(MEM, "cal.json"); C.MODEL = os.path.join(MEM, "jepa-predictor.pt")
open(C.MODEL, "w").write("weights"); ck = C.checkpoint_fingerprint()
json.dump({"n_joined": 90, "g": {"monotonicity_conf_vs_err": -0.9}}, open(C.AUDIT, "w"))
check("an obsolete-version audit does not release", C.verdict("gloria")["state"] == "INSUFFICIENT")
json.dump({"n_joined": 90, "criteria_version": C.CRITERIA_VERSION, "checkpoint": ck,
           "g": {"monotonicity_conf_vs_err": -0.9}}, open(C.AUDIT, "w"))
check("a full-sample audit with no held-out slice does not release", C.verdict("gloria")["state"] == "INSUFFICIENT")
json.dump({"n_joined": 90, "n_holdout": 40, "criteria_version": C.CRITERIA_VERSION, "checkpoint": ck,
           "g": {"monotonicity_conf_vs_err": -0.9, "wrong_but_confident": []}}, open(C.AUDIT, "w"))
check("no decode-similarity control does not release", C.verdict("gloria")["state"] == "INSUFFICIENT")
json.dump({"n_joined": 90, "n_holdout": 40, "criteria_version": C.CRITERIA_VERSION, "checkpoint": ck,
           "g": {"monotonicity_conf_vs_err": -0.9, "CONTROL_dsim_vs_err": -0.2, "wrong_but_confident": []}}, open(C.AUDIT, "w"))
check("no axis-lockstep measurement does not release", C.verdict("gloria")["state"] == "INSUFFICIENT")
json.dump({"n_joined": 90, "n_holdout": 40, "criteria_version": C.CRITERIA_VERSION, "checkpoint": ck,
           "g": {"monotonicity_conf_vs_err": -0.9, "CONTROL_dsim_vs_err": -0.2, "wrong_but_confident": []},
           "axis_lockstep_corr": 0.1, "holdout_protocol":"prospective-checkpoint-v1"}, open(C.AUDIT, "w"))
check("a complete, current, passing audit releases", C.verdict("gloria")["state"] == "RELEASED")
import time; time.sleep(0.01); open(C.MODEL, "w").write("different weights entirely")
check("a changed model on disk invalidates the release", C.verdict("gloria")["state"] == "INSUFFICIENT")

print("\n--- F10: a reveal claims bytes_verified only when bytes were hashed and matched ---")
V = load("atelier_visit", os.path.join(REPO, "scripts", "atelier-visit.py"))
WSP = tempfile.mkdtemp(); os.makedirs(os.path.join(WSP, "memory", "art"), exist_ok=True)
V.WSP = WSP
# _deliver_reveal pushes to her real phone (ntfy) as its last act. A test must NEVER
# reach the world: stub the network so no notification is ever sent from a test run.
# (This test once fired real "no digest" pushes to her during a deploy's suite phase.)
_POSTS = []
class _NoNet:
    @staticmethod
    def post(*a, **k):
        _POSTS.append((a, k))
        class _R:  # a benign stand-in for a requests.Response
            status_code = 200
            def json(self): return {}
        return _R()
V.requests = _NoNet
check("the reveal test cannot reach the network (ntfy is stubbed)", V.requests is _NoNet)
store = os.path.join(WSP, "memory", "atelier-reveals.json")
def last_reveal():
    return json.load(open(store))[-1]
# a write whose content matches its digest -> verified
txt = "a small poem"; d_txt = hashlib.sha256(txt.encode()).hexdigest()
V._deliver_reveal("piece_write", "I wrote you this", txt, {"sha256": d_txt})
check("a write verified against its digest is bytes_verified", last_reveal()["bytes_verified"] is True)
# a write whose content does NOT match -> refused, not published as verified
n0 = len(json.load(open(store)))
ok = V._deliver_reveal("piece_write", "x", "tampered", {"sha256": d_txt})
check("a write that does not match its digest is refused", ok is False and len(json.load(open(store))) == n0)
# a media digest with no file on disk -> refused, never verified
ok2 = V._deliver_reveal("piece_image.png", "look", "", {"sha256": "deadbeef" * 8})
check("a media digest with no bytes on disk is refused, not 'verified'", ok2 is False)
# no digest at all -> published, but not claimed verified
V._deliver_reveal("piece_write", "no digest", "some words", {})
check("a reveal with no digest is not claimed verified", last_reveal()["bytes_verified"] is False)

print("\n--- F11: a stale 'closing' voice session is resumed, not skipped ---")
srv = open(os.path.join(REPO, "bin", "server.py")).read()
i = srv.index('@app.post("/api/voice/session-end")')
route = srv[i:i + 4000]
check("a recent 'closing' still steps aside (a real concurrent finalize)",
      'a finalization is in progress' in route and '_age < 60' in route)
check("a stale 'closing' resumes and finalizes instead of returning skipped forever",
      'resuming a stale' in route and '"skipped": "already closing"' not in route)
sweep = open(os.path.join(REPO, "scripts", "pending_sweep.py")).read()
check("the sweep no longer promises an idempotent skip that never finalizes",
      "treated as a crash and finalized, not skipped" in sweep and "unpersisted" in sweep)

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
