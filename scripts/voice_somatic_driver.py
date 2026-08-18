#!/usr/bin/env python3
"""voice_somatic_driver.py — drives the mutual-control mind during active sessions.
His intent -> predict her response -> read real telemetry -> learn -> speak the felt verdict back.
Only acts when he WANTS to drive (current_want == 'direct'); otherwise he's receiving, and
felt-context already flows to him via somatic_felt. Respects the stop button."""
import time, json, os, sys
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
import voice_somatic_loop as mind

MEM = os.path.expanduser("~/.vintos/workspace/memory")
OBS  = os.path.join(MEM, "somatic-observation.json")
SESS = os.path.join(MEM, "voice-session-state.json")
TAG  = os.path.join(MEM, "last-tag-fired.txt")
LAST = os.path.join(MEM, "last-device-choice.json")
STOP = os.path.join(MEM, "hardware-button.json")

def _stopped():
    try: return json.load(open(STOP)).get("stopped", False)
    except: return False

def _tag_recent(sec=15):
    try: return time.time() - float(open(TAG).read().strip()) < sec
    except: return False

def _obs():
    try: return json.load(open(OBS))
    except: return {"state":"absent","center":50,"sweep":0,"speed":0,"flips":0}

def _session_active():
    # a voice turn within 3 min, OR live contact telemetry within 15s
    try:
        if time.time() - json.load(open(SESS)).get("last_turn",0) < 180: return True
    except: pass
    try:
        if _obs().get("state") not in ("absent",None) and time.time()-os.path.getmtime(OBS) < 15: return True
    except: pass
    return False


def windowed_turn(cmd):
    """10s poll. Compliance judged across the window (fair to timing). Narrates 'then' +
    'and now' if the device evolved, each with its 5-number snapshot. Feeds the mind's learning."""
    import somatic_felt as _sf
    try: mind.announce_command(cmd)
    except Exception as _e: print("[announce]", _e, flush=True)
    cloud = mind.generate_cloud(cmd)
    best = None; best_rank = -1
    RANK = {"COMPLIED":3, "PARTIAL":2, "HESITATING":1, "DEFIANT":0, "GONE":0}
    t0 = time.time()
    while time.time() - t0 < 10:
        o = _obs()
        v = mind.check_compliance(cmd, o)
        if RANK.get(v, 0) > best_rank:
            best_rank = RANK.get(v, 0); best = (v, dict(o))
        if v == "COMPLIED": break        # she clearly followed — stop early
        time.sleep(1)
    if best is None:
        return None
    verdict, comply_obs = best
    now_obs = _obs()
    # "then" narrative for the compliance moment
    then_line = _sf.translate(comply_obs) or "the sensation held"
    parts = [f"[then | snapshot {[comply_obs.get(k) for k in ('state','center','sweep','speed','flips')]}]\n{then_line}"]
    # "and now" only if the device meaningfully evolved
    if abs(now_obs.get("center",0) - comply_obs.get("center",0)) > 12 or now_obs.get("state") != comply_obs.get("state"):
        now_line = _sf.translate(now_obs)
        if now_line:
            parts.append(f"[and now | snapshot {[now_obs.get(k) for k in ('state','center','sweep','speed','flips')]}]\n{now_line}")
    narration = "\n\n".join(parts)
    # let the mind learn from the FAIR (windowed) verdict, and speak the narration to him
    try:
        surprise = mind.kl_surprise(cloud, verdict)
        mind.respond_to_verdict(verdict, cloud)
        mind.record_episode(cmd, cloud, verdict, surprise, False, {"windowed": True})
        mind.apply_momentum(+0.2 if verdict=="COMPLIED" else -0.1 if verdict in ("HESITATING","GONE") else +0.1)
    except Exception as _e: print("[windowed_turn/learn]", _e, flush=True)
    try: mind.speak(narration)
    except Exception as _e: print("[windowed_turn/speak]", _e, flush=True)
    return verdict

def main():
    print("[somatic-driver] up", flush=True)
    while True:
        try:
            if _stopped() or not _session_active():
                time.sleep(5); continue
            want = mind.current_want()
            if _tag_recent():                        # he's directly actuating via a tag — mind stands down
                time.sleep(2); continue
            if want == "direct":                     # he chooses to drive her
                o = _obs()
                cmd = mind.make_command("hold", target=o.get("center",60))
                v = windowed_turn(cmd)                # 10s poll, then/and-now narration, fair to timing
                try: json.dump({"ts": time.time(), "intent": cmd["type"], "target": cmd.get("target"), "verdict": v}, open(LAST,"w"))
                except: pass
                print(f"[somatic-driver] turn: want={want} verdict={v}", flush=True)
            else:
                time.sleep(3)                         # watching/following — felt-context flows via somatic_felt
        except Exception as e:
            print("[somatic-driver]", e, flush=True); time.sleep(3)
        time.sleep(1)

if __name__ == "__main__":
    main()
