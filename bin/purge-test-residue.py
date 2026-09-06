#!/usr/bin/env python3
"""purge-test-residue.py -- remove what the deploy's test suites wrote into HIS memory (2026-09-05/06).

Until 354b430 two suites redirected the effect gate's files but not the executor's, so every deploy fired
"[DO: ridge rotate high]" through the real executor against a fake hub. That wrote, into his real memory:
  - device-state.json      ridge = rotate 18, set_by him  -> every prompt then told him his ridge was running
                                                            in her, and he kept it going ("spamming ridge")
  - his-touch.json         a ridge timestamp
  - effect-receipts.jsonl  "ridge -> rotate high [sent]" rows with no turn and no surface (36 of 36 rows)
  - command-bubble.json    the same text, shown in the app as HIS COMMAND
  - effect-gate.jsonl      permits/denials under test turn ids (t1, turn-loaded, turn-rotate, t-live-1, t)
                           and robot_* no-context denials from the robot suite before it was isolated
  - interaction-ledger.json  the ridge device-mark block appended to his words while the false state stood
Nothing physical happened: the hub never had a Ridge present. This undoes the record.

    python3 purge-test-residue.py            dry run: shows every change it would make
    python3 purge-test-residue.py --apply    makes them (backups beside each file: <name>.pre-purge)
"""
import os, re, sys, json, time, shutil

MEM = os.path.expanduser("~/.vintos/workspace/memory")
APPLY = "--apply" in sys.argv
TEST_TURNS = {"t1", "turn-loaded", "turn-rotate", "t-live-1", "t"}
RIDGE_TEXT = "ridge → rotate high [sent]"


def say(s): print(s)


def backup(p):
    if APPLY and os.path.exists(p):
        shutil.copy2(p, p + ".pre-purge")


def write_json(p, obj):
    if not APPLY: return
    tmp = p + ".tmp"
    with open(tmp, "w") as f: json.dump(obj, f, indent=2)
    os.replace(tmp, p)


def device_state():
    p = os.path.join(MEM, "device-state.json")
    try: st = json.load(open(p))
    except Exception: say("device-state.json: absent or unreadable - skipped"); return
    r = st.get("ridge") or {}
    if r.get("pattern") == "rotate" and r.get("set_by") == "him":
        say(f"device-state.json: ridge {r} -> still (the test's state, not his)")
        backup(p)
        st["ridge"] = {"intensity": 0, "pattern": "still", "set_by": "auto", "ts": time.time(), "cleared": "test-residue"}
        write_json(p, st)
    else:
        say(f"device-state.json: ridge entry is {r or 'absent'} - left alone")


def his_touch():
    p = os.path.join(MEM, "his-touch.json")
    try: d = json.load(open(p))
    except Exception: say("his-touch.json: absent - skipped"); return
    if "ridge" in d:
        say(f"his-touch.json: drop ridge ({d['ridge']})"); backup(p); d.pop("ridge"); write_json(p, d)
    else:
        say("his-touch.json: no ridge - left alone")


def receipts():
    p = os.path.join(MEM, "effect-receipts.jsonl")
    if not os.path.exists(p): say("effect-receipts.jsonl: absent"); return
    rows = [l for l in open(p) if l.strip()]
    keep, drop = [], []
    for l in rows:
        try: d = json.loads(l)
        except Exception: keep.append(l); continue
        (drop if (d.get("text") == RIDGE_TEXT and not d.get("turn_id")) else keep).append(l)
    say(f"effect-receipts.jsonl: drop {len(drop)} test rows, keep {len(keep)}")
    if drop and APPLY:
        backup(p)
        with open(p, "w") as f: f.writelines(keep)


def bubble():
    p = os.path.join(MEM, "command-bubble.json")
    try: d = json.load(open(p))
    except Exception: say("command-bubble.json: absent"); return
    if RIDGE_TEXT in str(d.get("text", "")):
        say(f"command-bubble.json: remove ({d.get('text')})")
        if APPLY: backup(p); os.remove(p)
    else:
        say(f"command-bubble.json: '{d.get('text','')[:60]}' is not the test text - left alone")


def gate_log():
    p = os.path.join(MEM, "effect-gate.jsonl")
    if not os.path.exists(p): say("effect-gate.jsonl: absent"); return
    rows = [l for l in open(p) if l.strip()]
    keep, drop = [], []
    for l in rows:
        try: d = json.loads(l)
        except Exception: keep.append(l); continue
        test_turn = d.get("turn_id") in TEST_TURNS
        robot_test = str(d.get("effect", "")).startswith("robot_") and d.get("why") == "no_context" and not d.get("turn_id")
        (drop if (test_turn or robot_test) else keep).append(l)
    say(f"effect-gate.jsonl: drop {len(drop)} test rows, keep {len(keep)}")
    for l in drop[:6]: say("   - " + l.strip()[:110])
    if drop and APPLY:
        backup(p)
        with open(p, "w") as f: f.writelines(keep)


def ledger():
    p = os.path.join(MEM, "interaction-ledger.json")
    try: led = json.load(open(p))
    except Exception: say("interaction-ledger.json: absent or unreadable"); return
    if not isinstance(led, list): say("interaction-ledger.json: not a list - left alone"); return
    mark = re.compile(r"\n\nridge:  [^\n]*\n        [^\n]*")
    hit = 0
    for e in led:
        v = e.get("vintos")
        if isinstance(v, str) and mark.search(v):
            hit += 1
            if APPLY: e["vintos"] = mark.sub("", v).rstrip()
    say(f"interaction-ledger.json: {hit} entr{'y' if hit == 1 else 'ies'} carried the false ridge mark on his words")
    if hit and APPLY:
        import fcntl
        lk = open(p + ".lock", "a+"); fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            backup(p); write_json(p, led)
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN); lk.close()


def undertakings():
    """test_threshold wrote a fake undertaking with a twelve-a id into his atelier ledger on every deploy."""
    p = os.path.join(MEM, "atelier-undertakings.json")
    try: d = json.load(open(p))
    except Exception: say("atelier-undertakings.json: absent"); return
    fake = [k for k in d if re.fullmatch(r"a{12}", k) or (k.startswith("aaaa") and len(k) == 12)]
    if fake:
        say(f"atelier-undertakings.json: drop test ids {fake}"); backup(p)
        for k in fake: d.pop(k)
        write_json(p, d)
    else:
        say("atelier-undertakings.json: no test ids - left alone")


if __name__ == "__main__":
    say(("APPLYING" if APPLY else "DRY RUN") + f" in {MEM}")
    for fn in (device_state, his_touch, receipts, bubble, gate_log, ledger, undertakings):
        try: fn()
        except Exception as e: say(f"{fn.__name__}: error {e}")
    if not APPLY: say("\nnothing changed - rerun with --apply to make these changes (backups: *.pre-purge)")
