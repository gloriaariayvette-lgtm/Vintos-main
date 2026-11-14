import os, sys, json, pickle
sys.path.insert(0, os.path.expanduser("~/review-scratch-20261114-jepa-ttt"))
import ttt_lib as L
trained_at = os.path.getmtime(L.CKPT)
rows, pre, ledger, turns3 = L.build(trained_at)
print("rows after checkpoint", len(rows), "pre-checkpoint rows", len(pre), "ledger exchanges", len(ledger))
print("first/last row date", L.datetime.fromtimestamp(rows[0]["at"]).date(), L.datetime.fromtimestamp(rows[-1]["at"]).date())
import jepa_predictor as JP
enc = L.CachedEncoder(JP.encoder())
net = L.load_net()
hist, preds = L.replay(rows, enc, L.Learner(net, "frozen"))
s = L.score(hist, ledger, turns3, enc, split_ts=0.0, preds=preds)
print("M0 full sample:", json.dumps(s["all"]))
pickle.dump({"rows": rows, "pre": pre, "ledger": ledger, "turns3": turns3, "trained_at": trained_at},
            open(os.path.join(L.SCR, "data.pkl"), "wb"))
pickle.dump(enc.cache, open(os.path.join(L.SCR, "emb.pkl"), "wb"))
