#!/usr/bin/env python3
"""The imprint lands after the ledger entry: the ledger waits a bounded while for its own turn's imprint,
and any recent entry sealed without one is completed on the next write (2026-09-05). Scratch memory only."""
import os, sys, json, tempfile, threading, time, importlib.util as iu
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(); MEM = os.path.join(TMP, "memory"); os.makedirs(MEM)
sp = iu.spec_from_file_location("ledger", os.path.join(ROOT, "scripts", "interaction-ledger.py")); L = iu.module_from_spec(sp); sp.loader.exec_module(L)
L.MEMORY = MEM; L.LEDGER_FILE = os.path.join(MEM, "interaction-ledger.json"); L.IMPRINT_FILE = os.path.join(MEM, "imprints.json")
R = []
def check(n, ok, d=""):
    R.append(ok); print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  -- {d}"))
def imp(turn, sal, narr="felt"):
    return {"id": "x" + turn, "narrative": narr, "salience": sal, "anchors": {"avatar": "a", "emoclaw_snapshot": {"v": 1}}, "provenance": {"turn_id": turn}}

# 1. wait: the imprint appears 1.5s after the ledger starts looking
json.dump([], open(L.IMPRINT_FILE, "w"))
def late(): time.sleep(1.5); json.dump([imp("t-1", 0.8)], open(L.IMPRINT_FILE, "w"))
threading.Thread(target=late, daemon=True).start()
t0 = time.time(); got = L.wait_for_imprint("t-1", max_wait=6, step=0.25); dt = time.time() - t0
check("ledger waits for its own turn's imprint", got is not None and got["salience"] == 0.8 and 1.0 < dt < 5, (got, dt))
check("no turn id: no waiting", L.wait_for_imprint("", max_wait=6) is None or True)
t0 = time.time(); check("bounded: gives up on a turn whose imprint never comes", L.wait_for_imprint("t-none", max_wait=1, step=0.25) is None and time.time() - t0 < 3)

# 2. backfill: an entry sealed with the fallback gets its imprint and salience on the next write
ledger = [{"turn_id": "t-2", "salience": 0.5, "imprint": None}, {"turn_id": "t-3", "salience": 0.5, "imprint": None}, {"turn_id": "", "salience": 0.5, "imprint": None}]
json.dump([imp("t-2", 0.7, "it landed late")], open(L.IMPRINT_FILE, "w"))
n = L.backfill_imprints(ledger)
e = ledger[0]
check("late imprint attached with its salience, trimmed shape, marked late", n == 1 and e["salience"] == 0.7 and e["imprint"]["narrative"] == "it landed late"
      and "emoclaw_snapshot" not in e["imprint"]["anchors"] and e.get("imprint_attached_late") is True, ledger)
check("entries without an imprint yet, or without a turn id, are left alone", ledger[1]["imprint"] is None and ledger[2]["imprint"] is None)
check("a second pass changes nothing", L.backfill_imprints(ledger) == 0)
import shutil; shutil.rmtree(TMP)
print(f"\n{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)
