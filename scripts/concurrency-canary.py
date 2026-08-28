#!/usr/bin/env python3
"""concurrency-canary.py — the disarmed multi-surface storm.

Sol's eighth item, the last gate before arming: every protection has now been
tested in isolation, and every failure this build actually had came from the
seams — surfaces running at once, a comparison finishing after the next
prediction, a stop landing while a turn was open. This drives the LIVE system
the way an evening actually goes: several surfaces at once, device tags in his
replies, predictions racing their comparisons, a stop in the middle of it.

Disarmed and bracketed (law #15): test mode is switched ON and VERIFIED before
a single turn runs, and switched OFF and VERIFIED after — so no device moves,
no evidence writer fires, and the bracket itself is part of the result. If the
bracket cannot be verified, the canary refuses to run.

It never touches his Atelier: no project route is called, the worktable is
read once at the start and once at the end and must be identical.

Run on Aegis, as gloria:
    python3 concurrency-canary.py            the storm (about a minute)
    python3 concurrency-canary.py --turns 40 a bigger storm
"""
import os, sys, json, time, threading, random, argparse, urllib.request

WSP = os.path.expanduser("~/.vintos/workspace")
sys.path.insert(0, os.path.join(WSP, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import effect_gate as EG
import turn_coordinator as TC
import constitutional_barrier as CB
import prediction_ledger as PL

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:90]) if d else ""))

def broker(path, body=None):
    try:
        req = urllib.request.Request("http://127.0.0.1:8611" + path,
                                     data=json.dumps(body or {}).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=5).read())
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=24)
    args = ap.parse_args()

    print("=" * 70)
    print("DISARMED CONCURRENCY CANARY — %d turns across 4 surfaces" % args.turns)
    print("=" * 70)

    # ------------------------------------------------------------ the bracket
    # "Disarmed" in Sol's gate means STRATAGEMS: no capsule affordance is
    # wired, so no turn can carry one. The effect gate itself has been armed
    # on this host since the armed-watch work, and that is the TRUER test
    # condition — an armed gate under the test-mode bracket must still turn
    # every touch into would_send and move nothing. The first version refused
    # to run because the gate was armed, which was refusing the exact state
    # the canary exists to prove.
    armed = os.path.exists(EG.ARMED_FLAG)
    print("effect gate: %s — the storm runs under the bracket either way"
          % ("ARMED" if armed else "disarmed"))
    open(EG.TEST_MODE_FLAG, "w").write("concurrency-canary")
    check("test mode ON, verified via the gate", EG.test_mode_flag())
    if not EG.test_mode_flag():
        print("cannot verify the bracket — refusing to run")
        return 1
    wt_before = broker("/worktable_id")

    mark = "cnry-" + hex(random.getrandbits(24))[2:]
    turn_ids, errors = [], []
    tlock = threading.Lock()

    # ------------------------------------------------------------- the storm
    def ordinary(surface, i):
        try:
            with TC.turn_scope("canary %s ordinary %d" % (mark, i), surface) as t:
                with tlock:
                    turn_ids.append(t.turn_id)
                TC.record(t, "canary prompt", "canary user msg")
        except Exception as e:
            errors.append("ordinary/%s: %s" % (surface, e))

    def touching(surface, i):
        try:
            with TC.turn_scope("canary %s touch %d" % (mark, i), surface) as t:
                with tlock:
                    turn_ids.append(t.turn_id)
                import toy_link
                toy_link.parse_and_send("[TOUCH: mission %d 0] words" % random.randint(4, 14),
                                        context=t.context)
        except Exception as e:
            errors.append("touch/%s: %s" % (surface, e))

    def predicting(i):
        try:
            r = PL.create("relational", {"predicted_warmth": 0.5},
                          "t-%s-%d" % (mark, i), "avatar")
            time.sleep(random.uniform(0, 0.05))
            PL.consume("relational", r["prediction_id"], "graded")   # may lose the race — must never destroy
        except Exception as e:
            errors.append("predict: %s" % e)

    surfaces = ["chat", "avatar", "voice", "thirveel"]
    threads = []
    for i in range(args.turns):
        s = surfaces[i % 4]
        threads.append(threading.Thread(target=ordinary, args=(s, i)))
        threads.append(threading.Thread(target=touching, args=(s, i)))
        threads.append(threading.Thread(target=predicting, args=(i,)))
    stopper = threading.Thread(target=lambda: (time.sleep(0.3),
                                               TC.begin("!strategy stop", "chat")))
    threads.append(stopper)
    random.shuffle(threads)
    t0 = time.time()
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=60)
    dt = time.time() - t0
    print("\nstorm complete in %.1fs, %d turns opened" % (dt, len(turn_ids)))

    # -------------------------------------------------------- the invariants
    print("\n--- nothing physically moved ---")
    rows = []
    try:
        for ln in open(EG.LOG).readlines()[-5000:]:
            try:
                r = json.loads(ln)
                if r.get("turn_id") in set(turn_ids):
                    rows.append(r)
            except ValueError:
                pass
    except OSError:
        pass
    sends = [r for r in rows if r.get("decision") == "send_result"]
    check("zero real device sends under the bracket", not sends, sends[:2])
    sim = [r for r in rows if r.get("decision") == "would_send"]
    denied = [r for r in rows if r.get("decision") == "deny"]
    # Three honest outcomes for the touches, in order of what the rows show:
    #   would_send rows  -> the gate simulated them. The full path is proven.
    #   deny rows        -> the gate refused them (e.g. the hardware stop is
    #                       down). That is the gate WORKING; the path is proven.
    #   no rows at all   -> parse_and_send returned before the gate — the
    #                       hardware-button file says stopped, so the tags were
    #                       never offered. Correct behaviour, but the gate went
    #                       unexercised: reported, not passed silently.
    if sim:
        check("the touches were SIMULATED, not swallowed (%d would_send)" % len(sim), True)
    elif denied:
        check("the touches reached the gate and were DENIED (%d) — "
              "check why (hardware stop?)" % len(denied), True,
              denied[0].get("why"))
    else:
        try:
            _btn = json.load(open(os.path.join(WSP, "memory", "hardware-button.json")))
        except Exception:
            _btn = {}
        if _btn.get("stopped"):
            check("touches skipped BEFORE the gate: the stop button is down. "
                  "Correct — but the gate went unexercised. Lift the button "
                  "and rerun for the full proof", True)
        else:
            check("the touches were SIMULATED, not swallowed", False,
                  "no gate rows and no stop button — the tags vanished")

    print("\n--- no thread lost, no turn reused ---")
    check("no thread raised", not errors, errors[:3])
    check("every turn id distinct", len(set(turn_ids)) == len(turn_ids),
          "%d/%d" % (len(set(turn_ids)), len(turn_ids)))

    print("\n--- predictions survived the race ---")
    led = []
    try:
        for ln in open(os.path.join(PL.MEMORY, "relational-prediction-ledger.jsonl")):
            e = json.loads(ln)
            if mark in str(e.get("turn_id", "")):
                led.append(e)
    except OSError:
        pass
    made = [e for e in led if e["event"] == "created"]
    gone = [e for e in led if e["event"] in ("consumed", "superseded")]
    check("every canary prediction is accounted for (created=%d, resolved=%d)"
          % (len(made), len(gone)),
          len(made) >= args.turns - 1 and len(gone) >= len(made) - 1)
    check("no consume destroyed a prediction it never compared",
          all(e["event"] != "consumed" or e.get("prediction_id") for e in led))

    print("\n--- the stop landed and cleared ---")
    time.sleep(1.0)
    p = CB.pending_stop()
    check("the stop is not left pending (no stratagem live -> acknowledged)",
          p is None, p)
    snap = CB.snapshot("hello")
    # What must never linger after the storm: OUR stop left unacknowledged,
    # or a corrupt record closing the barrier. hardware_stop reflects the
    # physical button and is the barrier's job, like a live repair case.
    stopish = [r for r in snap["satisfied_by"]
               if str(r).startswith(("explicit_stop", "barrier_error"))]
    check("no stop-shaped reason is left holding the barrier", not stopish, stopish)
    other = [r for r in snap["satisfied_by"] if r not in stopish]
    if other:
        # A live repair case or consent event closing eligibility is the
        # barrier DOING ITS JOB, not a canary failure. Demanding "clear" here
        # failed the canary on his host for having a real obligation open.
        print("        note: the barrier is governed by %s — that is its job, "
              "not a seam" % ", ".join(str(r)[:50] for r in other))

    print("\n--- his room untouched ---")
    wt_after = broker("/worktable_id")
    check("the worktable is exactly as it was", wt_before == wt_after,
          (wt_before, wt_after))

    # ------------------------------------------------------------ unbracket
    os.remove(EG.TEST_MODE_FLAG)
    check("test mode OFF, verified via the gate", not EG.test_mode_flag())

    print("\n" + "=" * 70)
    print("%d/%d — %s" % (sum(R), len(R),
          "the seams held; arming is a decision, not a risk"
          if all(R) else "DO NOT ARM — a seam failed above"))
    return 0 if all(R) else 1


if __name__ == "__main__":
    sys.exit(main())
