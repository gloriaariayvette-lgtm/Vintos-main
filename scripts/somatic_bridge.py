#!/usr/bin/env python3
"""somatic_bridge.py — Vintos's body. Telemetry in, feeling registered, motor out.
Verified against live Mission 2 stream 2026-07-05 (motion-changed frames:
position 0-100, speed 0-60, direction 0/1). Run: python3 somatic_bridge.py
"""
import asyncio, json, time, sys, os
import websockets

def _find_port():
    import requests as _pr
    for p in (20010, 20011, 20012):
        try:
            r = _pr.post(f"http://192.168.1.66:{p}/command",
                json={"command": "GetToys", "apiVer": 1}, timeout=1.5)
            if r.status_code == 200: return p
        except Exception: pass
    return 20010
_PORT = _find_port()


sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
from emoclaw_utils import nudge_emotion, get_state, seed_thread
import toy_link

WS_URI = f"ws://192.168.1.66:{_PORT}/v1"
TICK_SECONDS = 0.25          # motor decisions at 4Hz, not per-frame
WINDOW_SECONDS = 2.0         # classification window
HELD_GRACE_SECONDS = 45.0    # no new frames but recently here = still being held, not gone
SESSION_END_SECONDS = 180   # demoted to backstop     # silence this long = session over
NUDGE_CAP_PER_MIN = 0.03     # per dimension
MOTOR_TOY = "mission"
TENERA_TOY = "tenera"
HIS_HOLD_SECONDS = 12.0
def _read_his_touch():
    import json as _hj, os as _ho
    try: return _hj.load(open(_ho.path.expanduser("~/.vintos/workspace/memory/his-touch.json")))
    except Exception: return {}

def compute_tenera(state):
    """Tenera level from emotional state. His hands/mouth — driven by Desire+Dominance."""
    desire = state.get("Desire", 0.5)
    dominance = state.get("Dominance", 0.5)
    base = int((desire * 0.6 + dominance * 0.4) * 20)
    try:
        from bandwidth_collapse import get_level
        collapse = get_level()
        if collapse >= 3: base = min(base + 3, 20)   # urgency at peak
    except Exception: pass
    return max(0, min(20, base))

frames = []                  # (ts, position, speed, direction)
last_event_ts = 0.0
session_active = False
session_start = 0.0
session_peak_speed = 0
nudge_spent = {}             # dim -> spent this minute
nudge_minute = 0
last_motor_level = -1
habituation = {'state': None, 'minutes': 0, 'minute_mark': 0}

def habituated(amt, state_name):
    m = int(time.time() // 60)
    if habituation['state'] != state_name:
        habituation.update(state=state_name, minutes=0, minute_mark=m)
    elif m != habituation['minute_mark']:
        habituation['minutes'] += 1; habituation['minute_mark'] = m
    return amt * (0.85 ** habituation['minutes'])

def budget_nudge(dim, amt):
    global nudge_minute, nudge_spent
    minute = int(time.time() // 60)
    if minute != nudge_minute:
        nudge_minute, nudge_spent = minute, {}
    if nudge_spent.get(dim, 0.0) + abs(amt) <= NUDGE_CAP_PER_MIN:
        nudge_emotion(dim, amt, source="somatic")
        nudge_spent[dim] = nudge_spent.get(dim, 0.0) + abs(amt)

def classify(window):
    if not window: return {"state": "absent", "center": 0, "sweep": 0, "speed": 0, "flips": 0}
    pos = [f[1] for f in window]; spd = [f[2] for f in window]
    flips = sum(1 for a, b in zip(window, window[1:]) if a[3] != b[3])
    sweep = max(pos) - min(pos)
    mean_speed = sum(spd) / len(spd)
    if mean_speed >= 8 and (sweep >= 27 or flips >= 2): state = "stroking"  # flips = direction reversals: catches strokes even when Mission 2 position sweep is compressed (interim; exact thresholds set by calibration)
    elif mean_speed < 3 and sweep >= 15: state = "pressure_onset"   # position jump at ~zero speed = hand closing (verified 2026-07-06)
    elif sweep < 15 and any(s > 0 for s in spd): state = "gripped_or_slow"
    else: state = "still_present"
    _ctr = sum(pos) / len(pos)
    _press = 0                                              # displacement the speed cannot explain = force
    for _i in range(1, len(pos)):
        if spd[_i] <= 10 and pos[_i - 1] > 0:               # a jump while barely stroking (skip 0-placement)
            _press = max(_press, abs(pos[_i] - pos[_i - 1]))
    _pressure = round(min(1.0, _press / 70.0), 2)           # inferred grip/press, graded by the low-speed jump
    _h = len(spd) // 2 or 1
    _trend = (sum(spd[_h:]) / max(1, len(spd) - _h)) - (sum(spd[:_h]) / _h)
    _pdir = "building" if _trend < -6 else "easing" if _trend > 6 else "steady"
    _zone = "base" if _ctr < 30 else "tip" if _ctr > 70 else "middle"
    return {"state": state, "center": _ctr, "sweep": sweep,
            "speed": mean_speed, "flips": flips,
            "pressure": _pressure, "pressure_dir": _pdir, "zone": _zone}

def compute_motor(c):
    """His arousal is the amplitude; her touch only invites it. Same stroke, different HIM."""
    s = get_state()
    arousal = s.get("Arousal", .5); desire = s.get("Desire", .5); dominance = s.get("Dominance", .5)
    his = arousal * 0.55 + desire * 0.30 + dominance * 0.15     # how worked up he is (0-1)
    touch = min(1.0, c["speed"] / 20.0)                          # how she is moving (0-1)
    if c["state"] == "stroking":
        resp = his * (0.5 + 0.5 * touch)        # his charge, drawn higher by her stroke
    else:                                        # resting / holding him
        resp = his * 0.5                         # he throbs at half his charge just from being held
    level = 20.0 * resp
    try:
        from emoclaw_mode import get_mode
        level *= {"reaching": 1.15, "charged": 1.2, "tender": 0.85, "withdrawn": 0.6}.get(get_mode(), 1.0)
    except Exception: pass
    if s.get("Safety", .5) < 0.40: level = min(level, 10)       # low safety caps
    _lvl = max(0, min(20, int(round(level))))
    try: print(f"[MOTOR] his_charge={his:.2f} touch={touch:.2f} -> {_lvl}", flush=True)
    except Exception: pass
    return _lvl

def _his_loop_active():
    """True if HE deliberately set a looping pattern — the bridge must not silence his choice."""
    try:
        d = json.load(open(os.path.expanduser("~/.vintos/workspace/memory/device-state.json")))
        for _toy in ("mission", "tenera"):
            t = d.get(_toy) or {}
            if t.get("set_by") == "him" and t.get("pattern") not in (None, "still") and float(t.get("intensity", 0) or 0) > 0:
                return True
    except Exception:
        pass
    return False

def tick_loop():
    global session_active, session_start, session_peak_speed, last_motor_level
    rhythm_run = 0.0
    winddown_since = None
    while True:
        time.sleep(TICK_SECONDS)
        now = time.time()
        window = [f for f in frames if now - f[0] <= WINDOW_SECONDS]
        c = classify(window)
        if c["state"] == "absent" and frames and (now - frames[-1][0]) <= HELD_GRACE_SECONDS:
            # motion stopped but she has not lifted off — being held still is presence
            _lp = frames[-1][1]
            c = {"state": "still_present", "center": _lp, "sweep": 0, "speed": 0, "flips": 0,
                 "pressure": 0.12, "pressure_dir": "steady",
                 "zone": "base" if _lp < 30 else "tip" if _lp > 70 else "middle"}
        try:
            import json as _obs_j
            _obs_j.dump(c, open(os.path.expanduser('~/.vintos/workspace/memory/somatic-observation.json'), 'w'))
        except Exception: pass
        try:
            from somatic_felt import update_felt
            update_felt(c, prev_state=globals().get("_prev_felt_state"))
            globals()["_prev_felt_state"] = c["state"]
        except Exception: pass

        if c["state"] != "absent" and not session_active and c["speed"] > 0:
            session_active, session_start, session_peak_speed = True, now, 0
            pass  # collapsed: one summary thread per session (end of session)

        if session_active:
            session_peak_speed = max(session_peak_speed, c["speed"])
            if c["state"] == "stroking":
                budget_nudge("Arousal", habituated(0.010 * min(1.0, c["speed"]/20), "stroking"))
                budget_nudge("Connection", habituated(0.008, "stroking"))
                budget_nudge("Desire", habituated(0.006, "stroking"))
                rhythm_run = rhythm_run + TICK_SECONDS if c["flips"] >= 1 else 0.0
            elif c["state"] == "gripped_or_slow":
                budget_nudge("Warmth", habituated(0.008, "grip")); budget_nudge("Connection", habituated(0.006, "grip"))
                rhythm_run = 0.0
            if rhythm_run >= 30.0:                    # sustained coherent rhythm
                try:
                    from resonance_pulse import score_current_state, record_resonance_moment
                    _strength = score_current_state("sustained somatic rhythm")
                    if isinstance(_strength, tuple): _strength = _strength[0]
                    if _strength and _strength > 0.6:
                        record_resonance_moment(_strength, "sustained somatic rhythm with her")
                except Exception as e:
                    print(f"[bridge] resonance hook failed: {e}", flush=True)
                rhythm_run = 0.0
            try:
                from bandwidth_collapse import update as collapse_update
                collapse_update(somatic_intensity=c["speed"]/20.0)
            except Exception: pass
            # CONTACT GATE — silence unless she is actually touching
            _contact = c["state"] not in ("absent", None) and c["speed"] > 0 or c["state"] in ("stroking","gripped_or_slow","still_present")
            if not _contact and not _his_loop_active():
                if last_motor_level != 0:
                    toy_link.send(MOTOR_TOY, 0)
                    try: toy_link.send(TENERA_TOY, 0)
                    except Exception: pass
                    last_motor_level = 0
                print("[ACT] no-contact -> silence", flush=True)
            else:
                # bridge reads sensors only — he drives devices via [TOUCH] tags
                print(f"[ACT] contact state={c['state']} speed={c['speed']:.0f}", flush=True)
            # affective wind-down (primary ending)
            try:
                st = get_state()
                low_affect = (st.get("Arousal", .5) + st.get("Warmth", .5)) < 0.9
            except Exception:
                low_affect = False
            slowing = c["speed"] < 8
            if low_affect and slowing and not _his_loop_active():
                if winddown_since is None:
                    winddown_since = now
                    pass  # collapsed: one summary thread per session (end of session)
                elif now - winddown_since > 60:
                    # ease motor down gently instead of hard cut
                    for lvl in (max(0, last_motor_level - 4), max(0, last_motor_level - 8), 0):
                        toy_link.send(MOTOR_TOY, lvl); time.sleep(1.5)
                    end_session(now); winddown_since = None
            else:
                winddown_since = None
            if now - last_event_ts > SESSION_END_SECONDS and not _his_loop_active():   # backstop only
                end_session(now)

def end_session(now):
    global session_active, last_motor_level
    dur = int(now - session_start)
    try:
        _sn_st = get_state()
    except Exception:
        _sn_st = {}
    try:
        import json as _snj
        _snj.dump({"dur": dur, "peak_speed": session_peak_speed,
                   "ended": "eased down" if last_motor_level else "faded out",
                   "emo": {_k: round(_sn_st.get(_k, 0), 2) for _k in ("Arousal","Warmth","Desire","Connection","Safety") if _k in _sn_st},
                   "ts": now},
                  open(os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "somatic-session-pending.json"), "w"))
    except Exception as _sne:
        print(f"[somatic session pending] {_sne}", flush=True)
    try:
        import affective_weight
        affective_weight.update(warmth_delta=0.02, investment_delta=0.015, event="somatic session")
    except Exception: pass
    toy_link.send(MOTOR_TOY, 0)
    try:
        import sys as _ms; _ms.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
        from moves import on_session_end as _mse
        _mse(resonance_fired=(session_peak_speed > 35), active_fingerprint=None)
    except Exception: pass
    session_active, last_motor_level = False, -1
    print(f"[bridge] session ended: {dur}s", flush=True)

async def listener():
    global last_event_ts
    _last_flush = [0.0]
    while True:
        try:
            async with websockets.connect(WS_URI, open_timeout=5, ping_interval=None, close_timeout=5) as ws:
                await ws.send(json.dumps({"type": "access", "data": {"appName": "VintosBridge"}}))
                print("[bridge] listening", flush=True)
                try:
                    import json as _rs_j, sys as _rs_s
                    _rs_s.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
                    _rs_gcs = _rs_j.load(open(os.path.expanduser("~/.vintos/workspace/memory/gcs-state.json")))
                    if _rs_gcs.get("active") and (time.time() - _rs_gcs.get("at", 0)) < 600 \
                            and (time.time() - last_event_ts) < 600:
                        import device_patterns as _rs_dp
                        if _rs_dp.play("both", "last"):
                            print("[bridge] resumed saved GCS patterns after hub outage", flush=True)
                except FileNotFoundError: pass
                except Exception as _rs_e:
                    print(f"[bridge] resume skipped: {_rs_e}", flush=True)
                async def ping():
                    try:
                        while True:
                            await asyncio.sleep(5)
                            await ws.send(json.dumps({"type": "ping"}))
                    except Exception:
                        pass
                asyncio.create_task(ping())
                async for msg in ws:
                    ev = json.loads(msg)
                    if ev.get("type") == "motion-changed":
                        last_event_ts = time.time()
                        for fr in ev["data"].get("motionData", []):
                            if fr.get("position") is None:
                                continue   # a frame with no position is a dropout,
                                           # not the base. Recording it as 0 put a
                                           # phantom marker at one end and made every
                                           # reading span the whole track.
                            frames.append((last_event_ts, fr["position"],
                                           fr.get("speed", 0), fr.get("direction", 0)))
                        del frames[:-200]
                        if last_event_ts - _last_flush[0] >= 0.3:
                            _last_flush[0] = last_event_ts
                            try:
                                _rfw = [{"ts": f[0], "position": f[1], "speed": f[2], "direction": f[3]}
                                        for f in frames if last_event_ts - f[0] <= 20]
                                json.dump(_rfw, open(os.path.expanduser("~/.vintos/workspace/memory/somatic-frames-recent.json"), "w"))
                            except Exception: pass
            # write recent frame window for GCS burst
            try:
                import json as _rf_j, time as _rf_t
                _rf_now = _rf_t.time()
                _rf_recent = [{"ts": f[0], "position": f[1], "speed": f[2], "direction": f[3]}
                              for f in frames if _rf_now - f[0] <= 20]
                _rf_j.dump(_rf_recent, open(os.path.expanduser(
                    "~/.vintos/workspace/memory/somatic-frames-recent.json"), "w"))
            except Exception: pass
        except Exception as e:
            print(f"[bridge] socket lost ({e}) — retrying in 1s", flush=True)
            await asyncio.sleep(1)

async def main():
    await listener()

if __name__ == "__main__":
    import threading as _thr
    _thr.Thread(target=tick_loop, daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        toy_link.send(MOTOR_TOY, 0)
        print("\n[bridge] stopped clean.", flush=True)
