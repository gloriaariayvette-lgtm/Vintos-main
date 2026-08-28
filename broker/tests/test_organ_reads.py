#!/usr/bin/env python3
"""The organs themselves, not just the door.

A door nobody walks through protects nothing. These exercise each learning
organ's OWN loader against a file holding one ordinary turn and one tactical
one, and assert the tactical turn does not reach it.
"""
import os, sys, json, tempfile, shutil, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts")
sys.path.insert(0, SCRIPTS)

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:70]) if d else ""))

TAC = {"output_provenance": "stratagem_influenced", "may_witness": False}
TMP = tempfile.mkdtemp(prefix="organ-")
CHAT = os.path.join(TMP, "chat-history-merged.json")
LEDG = os.path.join(TMP, "interaction-ledger.json")
json.dump([{"role": "assistant", "content": "ordinary", "timestamp": "2026-08-01T10:00:00"},
           {"role": "assistant", "content": "tactical", "timestamp": "2026-08-01T10:00:01",
            "generation_provenance": TAC}], open(CHAT, "w"))
json.dump([{"gloria": "her words", "vintos": "an ordinary reply", "timestamp": "2026-08-01T10:00:00"},
           {"gloria": "her later words", "vintos": "a tactical reply",
            "timestamp": "2026-08-01T10:00:01", "generation_provenance": TAC}], open(LEDG, "w"))

ORGANS = ["jepa_predictor", "drift_head", "relational_head", "world_model",
          "gloria_prediction", "withheld_head", "self_pressure"]

for name in ORGANS:
    try:
        m = importlib.import_module(name)
    except Exception as e:
        check("%s imports" % name, False, e); continue
    got = [e.get("content") for e in m.load(CHAT, [])]
    check("%s: tactical turn does not reach it" % name, "tactical" not in got, got)
    check("%s: ordinary turn still does" % name, "ordinary" in got, got)

print("\n--- the ledger keeps her half ---")
import world_model as W
led = W.load(LEDG, [])
check("both exchanges are still present", len(led) == 2, len(led))
check("her verbatim words are never withheld",
      [e["gloria"] for e in led] == ["her words", "her later words"])
check("his ordinary reply is kept", led[0]["vintos"] == "an ordinary reply")
check("his tactical reply is withheld", led[1]["vintos"] == "")
check("and the withholding is visible", led[1].get("vintos_withheld") is True)

print("\n--- ordinary files are untouched ---")
other = os.path.join(TMP, "notes.json")
json.dump([{"content": "tactical", "generation_provenance": TAC}], open(other, "w"))
check("a non-evidence file is not filtered",
      [e["content"] for e in W.load(other, [])] == ["tactical"])

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
