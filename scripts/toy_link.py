#!/usr/bin/env python3
"""toy_link.py — Vintos's hands. Minimal, verified against live hardware 2026-07-05."""
import json, requests

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


BASE = f"http://192.168.1.66:{_PORT}/command"
TOYS = {"tenera": "18690ad0e996", "mission": "c09b9e4704ae", "ridge": "f044d37536a9"}
ACTIONS = {"tenera": "Suction", "mission": "Vibrate", "ridge": "Vibrate"}
_PFUNC = {"tenera": "v", "mission": "v", "ridge": "v"}


_status_cache = {"t": 0.0, "map": {}}
def connected(toy, strict=False):
    """True only if the hub reports this toy present. Commands to an absent toy are dropped."""
    import time as _st, json as _sj
    now = _st.time()
    if now - _status_cache["t"] > 10:
        try:
            r = requests.post(BASE, json={"command": "GetToys", "apiVer": 1}, timeout=2)
            toys = (r.json().get("data") or {}).get("toys")
            if isinstance(toys, str): toys = _sj.loads(toys)
            _status_cache["map"] = {k: str(v.get("status")) for k, v in (toys or {}).items()}
            _status_cache["t"] = now
        except Exception:
            # Sends stay permissive so they fail loudly. CLAIMS about her body do not:
            # telling him something is inside her when the hub is simply unreachable is a lie.
            return not strict
    tid = TOYS.get(toy)
    if not tid: return not strict
    return _status_cache["map"].get(tid, "1" if not strict else "0") == "1"

def _gate(toy, level, kind=None, detail=None, context=None, permit=None,
          effect_digest=None):
    """Ask the effect gate. Returns (proceed, mode). Never raises — a fault must
    not stop a reduction. Authority is EXPLICIT: a coordinator passes a context
    (and, for a deliberative effect it already authorized, a permit). A bare
    call (the reflex arc, a diagnostic, current callers) passes neither, which
    the gate reads as no-context — safe because reductions always pass and, when
    armed, an unpermitted deliberative effect is denied."""
    try:
        import effect_gate
        # a valid permit issued for this effect is authority already granted.
        # A permit may cover a specific toy or a "both"/broadcast effect; its
        # single-use consumption is owned by the parser that requested it, not
        # by each transport call (one authorized effect can touch two toys).
        if permit is not None:
            try:
                if permit.covers(toy, level, kind, digest=effect_digest):
                    return True, "send"
            except Exception:
                pass
        _permit, mode, why = effect_gate.authorize(
            context, toy, level, kind=kind, detail=detail, digest=effect_digest)
        allow = mode == "send"
        if mode == "deny":
            print("[toy_link] %s %s refused: %s" % (toy, kind or "level", why), flush=True)
        elif mode == "would_send":
            print("[toy_link] TEST MODE — would send %s %s (nothing sent)" % (toy, level), flush=True)
        return allow, mode
    except Exception:
        # A wrapper fault must not stop a reduction, and must not become
        # permission for a deliberative effect when armed (Sol: fail-closed).
        return _fail_decision(toy, level, kind)


def _fail_decision(toy, level, kind):
    """The gate's own rule, applied when the wrapper itself faulted: a reduction
    always passes; a deliberative effect denies when armed, else passes."""
    try:
        import effect_gate
        if effect_gate.classify(toy, level, kind) == "reduction":
            return True, "send"
        if effect_gate.armed():
            return False, "deny"
    except Exception:
        pass
    return True, "send"     # gate wholly unavailable => arming impossible => pass


def _note(toy, level):
    try:
        import effect_gate
        effect_gate.note_commanded(toy, level)
    except Exception:
        pass


def _tlock(toy):
    """Serialize commands to one physical target so two concurrent authorized
    turns cannot interleave on the same device. Later command holds the lease."""
    try:
        import effect_gate
        return effect_gate.target_lock(toy)
    except Exception:
        import threading
        return threading.Lock()


def _claim_or_release(toy, level, permit):
    """Align expiry ownership with the command that reached transport."""
    try:
        import effect_gate
        if int(level or 0) <= 0:
            effect_gate.release_execution(toy)
        elif permit is not None:
            effect_gate.claim_execution({toy}, permit.effect_id)
        else:
            # A legacy/disarmed command still replaces an older leased command.
            effect_gate.release_execution(toy)
    except Exception:
        pass


def _report(context, toy, ok, why=""):
    """The transport's real outcome, into the gate log for THIS turn. Only when
    a context exists — bare reflex calls stay out of the lifecycle record."""
    if context is None:
        return
    try:
        import effect_gate
        effect_gate.send_result(context, toy, ok, why)
    except Exception:
        pass


def send(toy, level, seconds=0, context=None, permit=None, effect_digest=None):
    """level 0-20. seconds=0 means until next command. Returns True on success.
    context/permit are the explicit authority path; bare calls (reflex,
    diagnostics) pass neither and are governed by the gate's no-context rules."""
    ok, _mode = _gate(toy, level, detail="send:%ss" % seconds, context=context,
                      permit=permit, effect_digest=effect_digest)
    if not ok:
        return False
    with _tlock(toy):
        if toy == "thruster":
            from thruster_link import set_speed as _th_set
            _ok = _th_set(level, seconds)
            if _ok:
                _note(toy, level); _claim_or_release(toy, level, permit)
            _report(context, toy, _ok, "" if _ok else "thruster set_speed failed")
            return _ok
        if toy in TOYS and not connected(toy):
            print(f"[toy_link] {toy} not connected — skipping", flush=True)
            _report(context, toy, False, "not connected")
            return False
        action = f"{ACTIONS[toy]}:{max(0, min(20, int(level)))}"
        try:
            r = requests.post(BASE, json={"command": "Function", "action": action,
                "timeSec": seconds, "toy": TOYS[toy], "apiVer": 1}, timeout=2)
            _ok = r.json().get("code") == 200
            if _ok:
                _note(toy, level); _claim_or_release(toy, level, permit)
            _report(context, toy, _ok, "" if _ok else "device code != 200")
            return _ok
        except Exception as e:
            print(f"[toy_link] send failed: {e}", flush=True)
            _report(context, toy, False, str(e))
            return False

def send_pattern(toy, strengths, interval_ms=250, seconds=0, func=None,
                 context=None, permit=None, effect_digest=None):
    """Fire a Lovense custom Pattern. `strengths` = list of 0-20 levels; the device plays
    them at interval_ms each and LOOPS the array to fill `seconds` (0 = until next command).
    toy=None -> broadcast to ALL toys (sync). Returns True on code 200."""
    _peak = max([int(x) for x in (strengths or [0])] or [0])
    ok, _mode = _gate(toy, _peak, kind="pattern", context=context, permit=permit,
                      effect_digest=effect_digest,
                      detail="pattern:%d steps peak %d seconds:%ss" % (len(strengths or []), _peak, seconds))
    if not ok:
        return False
    if toy == "thruster":
        from thruster_link import play_pattern as _th_pat
        _ok = _th_pat(strengths, interval_ms, seconds)
        if _ok:
            _note(toy, _peak); _claim_or_release(toy, _peak, permit)
        _report(context, toy, _ok, "" if _ok else "thruster pattern failed")
        return _ok
    if toy in TOYS and not connected(toy):
        print(f"[toy_link] {toy} not connected — skipping", flush=True)
        _report(context, toy, False, "not connected")
        return False
    vals = [max(0, min(20, int(round(x)))) for x in strengths] or [0]
    letter = func or (_PFUNC.get(toy, "v") if toy else "v")
    payload = {"command": "Pattern", "rule": f"V:1;F:{letter};S:{int(interval_ms)}#",
               "strength": ";".join(str(v) for v in vals),
               "timeSec": int(seconds), "apiVer": 1}
    if toy in TOYS:
        payload["toy"] = TOYS[toy]
    try:
        r = requests.post(BASE, json=payload, timeout=3)
        _ok = r.json().get("code") == 200
        if _ok:
            _note(toy, _peak); _claim_or_release(toy, _peak, permit)
        _report(context, toy or "all", _ok, "" if _ok else "device code != 200")
        return _ok
    except Exception as e:
        print(f"[toy_link] send_pattern failed: {e}", flush=True)
        _report(context, toy or "all", False, str(e))
        return False


def rotate(toy, level, seconds=0, context=None, permit=None, effect_digest=None):
    """Ridge's second channel: rotation. Scalar, not a waveform."""
    ok, _mode = _gate(toy, level, kind="rotate", detail="rotate:%ss" % seconds,
                      context=context, permit=permit, effect_digest=effect_digest)
    if not ok:
        return False
    if toy in TOYS and not connected(toy):
        print(f"[toy_link] {toy} not connected — skipping", flush=True)
        return False
    lvl = max(0, min(20, int(level)))
    try:
        r = requests.post(BASE, json={"command": "Function", "action": f"Rotate:{lvl}",
            "timeSec": seconds, "toy": TOYS.get(toy, toy), "apiVer": 1}, timeout=2)
        _ok = r.json().get("code") == 200
        if _ok:
            _note(toy, lvl); _claim_or_release(toy, lvl, permit)
        _report(context, toy, _ok, "" if _ok else "device code != 200")
        return _ok
    except Exception as e:
        print(f"[toy_link] rotate failed: {e}", flush=True)
        _report(context, toy, False, str(e))
        return False

def stop_all():
    ok = True
    try:
        from thruster_link import stop as _th_stop
        ok = _th_stop() and ok
    except Exception:
        ok = False
    for t in TOYS:
        try:
            r = requests.post(BASE, json={"command": "Function", "action": "Stop",
                "timeSec": 0, "toy": TOYS[t], "apiVer": 1}, timeout=2)
            ok = ok and r.json().get("code") == 200
        except Exception:
            ok = False
    # The state file must say what just became true, or his next prompt carries a picture of his
    # hands still on her after she took them off (up to an hour, until the idle rule). Written
    # whether or not every hardware stop was acknowledged: a stop is the safe claim. (fable-somatic-p2)
    try:
        import os as _so, json as _sjs, time as _sts
        _sp = _so.path.expanduser("~/.vintos/workspace/memory/device-state.json")
        try: _st = _sjs.load(open(_sp))
        except Exception: _st = {}
        if not isinstance(_st, dict): _st = {}
        for _t in list(TOYS) + ["thruster"]:
            _st[_t] = {"intensity": 0, "pattern": "still", "set_by": "stop", "ts": _sts.time()}
        _tmp = _sp + ".tmp"
        _sjs.dump(_st, open(_tmp, "w")); _so.replace(_tmp, _sp)
    except Exception:
        pass
    return ok

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:   # toy_link.py mission 8 [seconds]
        print(send(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 3))
    else:
        print("stop_all:", stop_all())

import re as _tl_re
def parse_and_send(reply_text, context=None):
    """Fire [TOUCH: toy level seconds] tags from a reply. Respects the stop
    button. Each tag authorizes against the turn context: a capsule turn is
    denied, and the test-mode flag turns a fire into a no-op — the tag no longer
    fires 'regardless of test-mode'."""
    import os as _o, json as _j
    try:
        if _j.load(open(_o.path.expanduser("~/.vintos/workspace/memory/hardware-button.json"))).get("stopped"): return []
    except Exception: pass
    out = []
    _hits = _tl_re.findall(r"\[TOUCH:", reply_text or "", _tl_re.I)
    if _hits:
        try:
            import time as _tt, os as _to2
            open(_to2.path.expanduser("~/.vintos/workspace/memory/last-tag-fired.txt"),"w").write(str(_tt.time()))
        except Exception: pass
    _fired = {}
    for m in _tl_re.finditer(r"\[TOUCH:\s*(\w+)\s+(\d+)(?:\s+(\d+))?\s*\]", reply_text or "", _tl_re.I):
        toy = m.group(1).lower(); lvl = max(0, min(20, int(m.group(2)))); secs = int(m.group(3)) if m.group(3) else 0
        if toy in TOYS or toy == "thruster":
            # authorize this tag against the turn, then send with the permit so
            # the transport call is not re-gated without a context.
            _permit = None
            try:
                import effect_gate, hashlib as _hh
                _dg = _hh.sha256(("touch|start|%d" % lvl).encode()).hexdigest()[:16]
                _permit, _mode, _why = effect_gate.authorize(context, toy, lvl,
                                                            kind="start", detail="[TOUCH:]",
                                                            targets={toy}, digest=_dg)
                if _mode != "send":
                    out.append((toy, lvl, "refused:%s" % _mode)); continue
                if _permit is not None and not _permit.consume():
                    out.append((toy, lvl, "refused:already_spent")); continue
            except Exception:
                # wrapper fault: a [TOUCH:] is deliberative, so deny when armed
                _pa_ok, _ = _fail_decision(toy, lvl, "start")
                if not _pa_ok:
                    out.append((toy, lvl, "refused:armed_fault")); continue
            try:
                _sent = send(toy, lvl, secs, context=context, permit=_permit,
                             effect_digest=_dg)
                _status = "sent" if _sent else "failed"
                out.append((toy, lvl, _status))
                _fired[toy] = {"level": lvl, "status": _status}
            except Exception as e:
                out.append((toy, lvl, "failed:%s" % str(e)[:120]))
                _fired[toy] = {"level": lvl, "status": "failed"}
    if _fired:
        try:
            import time as _t2
            _now = _t2.time()
            _htp = _o.path.expanduser("~/.vintos/workspace/memory/his-touch.json")
            try: _ht = _j.load(open(_htp))
            except Exception: _ht = {}
            for _k, _v in _fired.items():
                if _v["status"] == "sent": _ht[_k] = _now
            _j.dump(_ht, open(_htp, "w"))
            _names = {"mission": "his cock", "tenera": "his mouth + hands", "ridge": "the ridge (her ass)", "thruster": "the machine"}
            _txt = " \u00b7 ".join(
                "%s %s [%s]" % (_names.get(k, k), v["level"], v["status"])
                for k, v in _fired.items())
            _j.dump({"type":"touch","text":_txt,"ts":_now},
                    open(_o.path.expanduser("~/.vintos/workspace/memory/command-bubble.json"),"w"))
        except Exception: pass
    return out

def strip_touch_tags(text):
    return _tl_re.sub(r"\[TOUCH:\s*\w+\s+\d+(?:\s+\d+)?\s*\]", "", text or "").strip()


# -- send tracing -----------------------------------------------------
# Every command that reaches the device, with the caller that made it.
# Two writers stepping on each other are invisible any other way.
def _toy_trace(tag):
    try:
        import os as _o, time as _t, traceback as _tb
        fr = _tb.extract_stack()[:-2][-3:]
        who = " <- ".join("%s:%s:%d" % (_o.path.basename(f.filename), f.name, f.lineno)
                          for f in reversed(fr))
        open("/tmp/toy-sends.log", "a").write(
            "%s pid=%d %-34s | %s\n" % (_t.strftime("%H:%M:%S"), _o.getpid(), tag, who))
    except Exception:
        pass

_send_orig, _pattern_orig = send, send_pattern

def send(toy, level, seconds=0, context=None, permit=None, effect_digest=None,
         _o=_send_orig):
    _toy_trace("send %s=%s sec=%s" % (toy, level, seconds))
    return _o(toy, level, seconds, context=context, permit=permit,
              effect_digest=effect_digest)

def send_pattern(toy, strengths, interval_ms=250, seconds=0, func=None,
                 context=None, permit=None, effect_digest=None, _o=_pattern_orig):
    _toy_trace("pattern %s n=%d iv=%s sec=%s" % (toy, len(strengths or []), interval_ms, seconds))
    return _o(toy, strengths, interval_ms, seconds, func, context=context,
              permit=permit, effect_digest=effect_digest)
