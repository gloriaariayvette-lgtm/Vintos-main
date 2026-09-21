#!/usr/bin/env python3
"""The prospective receipt is isolated, idempotent, exact-input, and causally inert."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-residual-shadow-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS

spec = importlib.util.spec_from_file_location("residual_shadow_test", os.path.join(REPO, "scripts", "residual_shadow.py"))
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)

results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:300]) if detail and not ok else ""))

check("all writes are in the scratch workspace",
      S.ROOT.startswith(WS) and S.EVENTS.startswith(WS) and "/home/gloria" not in S.EVENTS, S.EVENTS)
source = open(os.path.join(REPO, "scripts", "residual_shadow.py")).read()
check("the recorder has no sender or provider client",
      all(token not in source for token in ("requests", "urllib", "ntfy", "deliver(", "socket.")))
check("the recorder claims no causal authority", "causal_effect" in source and "none_from_this_recorder" in source)

exact = "She said: keep every line.\nHe replied: even this one."
one = S.record(input_text=exact, source="exchange", surface="avatar", turn_id="TURN-1",
               generated_deltas={"Warmth": .04, "Safety": float("nan"), "Bogus": 1},
               applied_deltas={"Warmth": .03}, pre_state={"Warmth": .5}, post_state={"Warmth": .53},
               model="local-ablit", response_digest="abc")
rows = S.pending()
check("a completed receipt is written", one.get("recorded") is True and len(rows) == 1, rows)
row = rows[0]
check("the precise same input survives", row["input_text"] == exact and len(row["input_sha256"]) == 64, row)
check("only finite named dimensions survive", row["generated_deltas"] == {"Warmth": .04}, row["generated_deltas"])
check("pre and post state remain distinct", row["pre_state"]["Warmth"] == .5 and row["post_state"]["Warmth"] == .53)
check("the receipt stays pending offline measurement",
      row["residual_status"] == "pending_offline_measurement" and row["causal_effect"] == "none_from_this_recorder")

again = S.record(input_text=exact, source="exchange", surface="avatar", turn_id="TURN-1",
                 generated_deltas={"Warmth": .09})
check("a retry is idempotent", again.get("reason") == "already_recorded" and len(S.pending()) == 1, again)

failed = S.record(input_text="provider failed on this exact input", source="gloria", surface="main",
                  turn_id="TURN-2", status="failed", error="timeout token=not-copied")
check("failure is evidence rather than silence", failed.get("recorded") and S.pending()[-1]["status"] == "failed")
before = open(S.EVENTS).read()
held = S.record(input_text="test text", source="gloria", surface="avatar", turn_id="TEST", test_mode=True)
check("test mode writes nothing", held == {"recorded": False, "reason": "test_mode"} and open(S.EVENTS).read() == before)

server = open(os.path.join(REPO, "bin", "server.py")).read()
check("avatar and ReelRoom bind receipts to their coordinated turn",
      server.count("turn_id=(_turn.turn_id if _turn is not None else \"\")") >= 2)
check("post-turn passes surface turn and test mode",
      'source="gloria", surface=surface, turn_id=turn_id, test_mode=test_mode' in server)
check("live reader exits before any provider or state effect in test mode",
      'if not t or test_mode:\n        return' in server)

print("\n%d/%d checks passed" % (sum(results), len(results)))
raise SystemExit(0 if all(results) else 1)
