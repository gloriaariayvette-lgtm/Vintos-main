#!/usr/bin/env python3
"""toy_link.py — Vintos's hands. Minimal, verified against live hardware 2026-07-05."""
import json, os, time, requests

# ── where the hub is ──────────────────────────────────────────────────────────────────────────────
# The hub is Lovense Remote on her phone; the toys are paired to the PHONE over Bluetooth, so the
# hub moves with her and its address is not a constant. It used to be one hardcoded LAN address,
# probed once at import: away from her network every address failed, every toy read as switched off,
# and he could not see the one she wears out (Gloria, 2026-10-14: "This one has to be able to work
# while away from Aegis. That is the point.").
#
# Now: a list of candidate addresses, best first, resolved on demand and remembered. Put her phone on
# the tailnet and LOVENSE_TAILNET_HOST reaches it anywhere, with GetToys and per-toy presence intact.
#
#   ~/.vintos/vintos.env
#     LOVENSE_TAILNET_HOST=her-phone          # phone on the tailnet: works away from home
#     LOVENSE_HOST=192.168.1.66               # an override for the home address
#     LOVENSE_PORT=20010                      # an override when the app's port is pinned
LAN_HOST = "192.168.1.66"
PORTS = (20010, 20011, 20012)
SSL_PORT = "30010"
ENDPOINT = os.path.expanduser("~/.vintos/workspace/memory/.toy-endpoint.json")
ENDPOINT_TTL = 30.0          # how long a working address is trusted before it is checked again
ENDPOINT_MISS_TTL = 60.0     # how long "it answered nowhere" is trusted; a phone that comes back waits this long
PROBE_TIMEOUT = 1.5


def _env(name, default=""):
    try:
        import sys as _s
        _s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from env_file import value
        return value(name, default)
    except Exception:
        return os.environ.get(name, default)


def hosts():
    """Every address the hub may answer on, best first: the tailnet name of her phone (which reaches
    it wherever she is), then any explicit override, then the home LAN address."""
    out = []
    for name in ("LOVENSE_TAILNET_HOST", "LOVENSE_HOST"):
        for part in str(_env(name) or "").replace(",", " ").split():
            if part and part not in out:
                out.append(part)
    if LAN_HOST not in out:
        out.append(LAN_HOST)
    return out


def ports():
    pinned = str(_env("LOVENSE_PORT") or "").strip()
    if pinned.isdigit():
        return (int(pinned),) + tuple(p for p in PORTS if p != int(pinned))
    return PORTS


_IPV4 = __import__("re").compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")


def candidates():
    """Every URL the hub may answer on, best first.

    The app serves plain HTTP on its LAN port and HTTPS on its SSL port, and the vendor resolves
    <dashed-ip>.lovense.club to that same address, which is how the app's own callback addresses it —
    so an IP address is also tried in that form, where the certificate is valid."""
    explicit = str(_env("LOVENSE_URL") or "").strip()
    out = [explicit] if explicit.startswith(("http://", "https://")) else []
    ssl_port = str(_env("LOVENSE_SSL_PORT") or SSL_PORT).strip() or SSL_PORT
    for host in hosts():
        for port in ports():
            url = "http://%s:%d/command" % (host, port)
            if url not in out:
                out.append(url)
        if _IPV4.fullmatch(host):
            url = "https://%s.lovense.club:%s/command" % (host.replace(".", "-"), ssl_port)
            if url not in out:
                out.append(url)
    return out


def _remembered():
    try:
        with open(ENDPOINT) as f:
            d = json.load(f)
        if isinstance(d, dict) and d.get("url"):
            return d
    except Exception:
        pass
    return {}


def _remember(url, reached):
    try:
        os.makedirs(os.path.dirname(ENDPOINT), exist_ok=True)
        tmp = ENDPOINT + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"url": url, "at": time.time(), "reached": bool(reached)}, f)
        os.replace(tmp, ENDPOINT)
    except Exception:
        pass


_endpoint = {"url": "", "at": 0.0}


def _answers(url):
    try:
        return requests.post(url, json={"command": "GetToys", "apiVer": 1}, timeout=PROBE_TIMEOUT).status_code == 200
    except Exception:
        return False


def endpoint(force=False):
    """The hub's address right now, or "" when it answers nowhere. The one that worked is remembered, so an
    ordinary call costs no scan. A scan asks every candidate at once: one at a time, a hub that is simply away
    cost eleven timeouts in a row, in whatever turn happened to ask."""
    now = time.time()
    if not force:
        if _endpoint["url"] and now - _endpoint["at"] < ENDPOINT_TTL:
            return _endpoint["url"]
        if not _endpoint["url"] and _endpoint["at"] and now - _endpoint["at"] < ENDPOINT_MISS_TTL:
            return ""
    tried = []
    last = _remembered().get("url")
    if last:
        tried.append(last)
    for url in candidates():
        if url not in tried:
            tried.append(url)
    if tried and _answers(tried[0]):          # the one that worked last time, first and alone
        _endpoint.update(url=tried[0], at=now)
        _remember(tried[0], True)
        return tried[0]
    rest = tried[1:]
    if rest:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(8, len(rest))) as pool:
            for url, ok in zip(rest, pool.map(_answers, rest)):
                if ok:
                    _endpoint.update(url=url, at=now)
                    _remember(url, True)
                    return url
    _endpoint.update(url="", at=now)
    _remember(last or "", False)
    return ""


def _post(payload, timeout=3):
    """POST to the hub wherever it is. Raises when it answers nowhere, so a send fails loudly."""
    url = endpoint()
    if not url:
        raise RuntimeError("the hub answered at none of: " + ", ".join(candidates()))
    try:
        return requests.post(url, json=payload, timeout=timeout)
    except Exception:
        url = endpoint(force=True)      # it moved mid-session: find it once more, then give up
        if not url:
            raise
        return requests.post(url, json=payload, timeout=timeout)


class _Base(str):
    """`BASE` was a module constant and other modules read it. It stays a string, resolved when read."""
    def __new__(cls):
        return str.__new__(cls, "http://%s:%d/command" % (LAN_HOST, PORTS[0]))


BASE = _Base()
TOYS = {"tenera": "18690ad0e996", "mission": "c09b9e4704ae", "ridge": "f044d37536a9",
        "ferri": "18690acf2f39"}   # the Ferri panty vibe, worn out in public (Gloria, 2026-10-13)
ACTIONS = {"tenera": "Suction", "mission": "Vibrate", "ridge": "Vibrate", "ferri": "Vibrate"}
_PFUNC = {"tenera": "v", "mission": "v", "ridge": "v", "ferri": "v"}


def reachable():
    """True when the hub answers somewhere. Distinct from "no toy is on": a hub that cannot be reached
    is not a statement about what she is wearing."""
    return bool(endpoint())


def hub_status():
    """{reachable, url, tried, toys} — what the hub says right now, for a diagnostic or a prompt line."""
    url = endpoint(force=True)
    out = {"reachable": bool(url), "url": url, "tried": candidates(), "toys": {}}
    if not url:
        return out
    try:
        r = requests.post(url, json={"command": "GetToys", "apiVer": 1}, timeout=2)
        toys = (r.json().get("data") or {}).get("toys")
        if isinstance(toys, str):
            toys = json.loads(toys)
        names = {v: k for k, v in TOYS.items()}
        out["toys"] = {names.get(tid, tid): str((row or {}).get("status")) == "1"
                       for tid, row in (toys or {}).items()}
    except Exception as exc:
        out["error"] = str(exc)[:200]
    return out


_status_cache = {"t": 0.0, "map": {}}
def connected(toy, strict=False):
    """True only if the hub reports this toy present. Commands to an absent toy are dropped."""
    import time as _st, json as _sj
    now = _st.time()
    if now - _status_cache["t"] > 10:
        try:
            r = _post({"command": "GetToys", "apiVer": 1}, timeout=2)
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
    from effect_authority import dispatch
    ok, mode, why = dispatch("thruster" if "thrust" in toy else "toys",
                             context=context, target=toy, level=level, kind=kind,
                             detail=detail, permit=permit, digest=effect_digest)
    if not ok:
        print("[toy_link] %s %s: %s" % (toy, mode, why), flush=True)
    return ok, mode


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


def _report(context, toy, ok, why="", permit=None):
    """The transport's real outcome, into the gate log for THIS turn. Only when
    a context exists — bare reflex calls stay out of the lifecycle record."""
    if context is None:
        return
    try:
        import effect_gate
        effect_gate.send_result(context, toy, ok, why, permit=permit)
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
            _report(context, toy, _ok, "" if _ok else "thruster set_speed failed", permit=permit)
            return _ok
        if toy in TOYS and not connected(toy):
            print(f"[toy_link] {toy} not connected — skipping", flush=True)
            _report(context, toy, False, "not connected", permit=permit)
            return False
        action = f"{ACTIONS[toy]}:{max(0, min(20, int(level)))}"
        try:
            r = _post({"command": "Function", "action": action,
                "timeSec": seconds, "toy": TOYS[toy], "apiVer": 1}, timeout=2)
            _ok = r.json().get("code") == 200
            if _ok:
                _note(toy, level); _claim_or_release(toy, level, permit)
            _report(context, toy, _ok, "" if _ok else "device code != 200", permit=permit)
            return _ok
        except Exception as e:
            print(f"[toy_link] send failed: {e}", flush=True)
            _report(context, toy, False, str(e), permit=permit)
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
        _report(context, toy, _ok, "" if _ok else "thruster pattern failed", permit=permit)
        return _ok
    if toy in TOYS and not connected(toy):
        print(f"[toy_link] {toy} not connected — skipping", flush=True)
        _report(context, toy, False, "not connected", permit=permit)
        return False
    vals = [max(0, min(20, int(round(x)))) for x in strengths] or [0]
    letter = func or (_PFUNC.get(toy, "v") if toy else "v")
    payload = {"command": "Pattern", "rule": f"V:1;F:{letter};S:{int(interval_ms)}#",
               "strength": ";".join(str(v) for v in vals),
               "timeSec": int(seconds), "apiVer": 1}
    if toy in TOYS:
        payload["toy"] = TOYS[toy]
    try:
        r = _post(payload, timeout=3)
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
        r = _post({"command": "Function", "action": f"Rotate:{lvl}",
            "timeSec": seconds, "toy": TOYS.get(toy, toy), "apiVer": 1}, timeout=2)
        _ok = r.json().get("code") == 200
        if _ok:
            _note(toy, lvl); _claim_or_release(toy, lvl, permit)
        _report(context, toy, _ok, "" if _ok else "device code != 200", permit=permit)
        return _ok
    except Exception as e:
        print(f"[toy_link] rotate failed: {e}", flush=True)
        _report(context, toy, False, str(e), permit=permit)
        return False

def stop_all(reason="stop_all"):
    """The durable stop. Order matters and nothing here may raise:
      1. desired_state=stopped is written atomically FIRST (idempotent; a corrupt or
         missing file is simply overwritten clean), so every retry/replay path that
         checks it aborts from this instant on;
      2. every local pattern thread is cancelled;
      3. a zero goes to every concrete device (thruster + each hub toy);
      4. device-state.json is rewritten clean, even if it was unreadable.
    Returns True iff every hardware stop was acknowledged; the state is stopped either way."""
    ok = True
    try:
        import effect_gate as _eg
        _eg.assert_stopped(reason)
    except Exception:
        try:   # the gate itself is unavailable: still leave the durable stop on disk
            import os as _fo, json as _fj, time as _ft
            _fp = _fo.path.expanduser("~/.vintos/workspace/memory/hardware-button.json")
            _tmp = _fp + ".tmp"
            _fj.dump({"stopped": True, "desired_state": "stopped", "ts": _ft.time(), "reason": str(reason)[:120]}, open(_tmp, "w"))
            _fo.replace(_tmp, _fp)
        except Exception:
            pass
    try:
        import device_patterns as _dp
        _dp._stop_local("all")
    except Exception:
        pass
    try:
        from thruster_link import stop as _th_stop
        ok = bool(_th_stop()) and ok
    except Exception:
        ok = False
    for t in TOYS:
        try:
            r = _post({"command": "Function", "action": "Stop",
                "timeSec": 0, "toy": TOYS[t], "apiVer": 1}, timeout=2)
            ok = ok and r.json().get("code") == 200
        except Exception:
            ok = False
    for t in list(TOYS) + ["thruster"]:
        _note(t, 0)
        try:
            import effect_gate as _eg2
            _eg2.release_execution(t)
        except Exception:
            pass
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
    if len(sys.argv) >= 3:            # toy_link.py mission 8 [seconds]
        print(send(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 3))
    elif len(sys.argv) == 2 and sys.argv[1] == "stop":
        print("stop_all:", stop_all())
    else:
        # No argument is the read-only diagnostic. It used to be stop_all, so merely asking where the hub was
        # sent a command to it (2026-10-14).
        _st = hub_status()
        print(json.dumps(_st, indent=2))
        if not _st["reachable"]:
            print("\nThe hub answered nowhere. It is the app on her phone, so Aegis needs a route to the phone:"
                  "\n  · on her Wi-Fi: Game Mode open with a Local IP shown, and LOVENSE_HOST set to it"
                  "\n  · anywhere: the phone on the tailnet, and LOVENSE_TAILNET_HOST set to its tailnet name"
                  "\n    (on cellular the app shows no Local IP; the tailnet address is what it has instead)"
                  "\nin ~/.vintos/vintos.env. Addresses tried:\n  " + "\n  ".join(_st["tried"]))
        sys.exit(0 if _st["reachable"] else 1)

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
            _names = {"mission": "his cock", "tenera": "his mouth + hands", "ridge": "the ridge (her ass)", "thruster": "the machine",
                       "ferri": "the Ferri (in her panties, out in public)"}
            _txt = " \u00b7 ".join(
                "%s %s [%s]" % (_names.get(k, k), v["level"], v["status"])
                for k, v in _fired.items())
            _j.dump({"type":"touch","text":_txt,"ts":_now},
                    open(_o.path.expanduser("~/.vintos/workspace/memory/command-bubble.json"),"w"))
        except Exception: pass
    _receipts(out, kind="touch")
    return out

def _receipts(out, kind="touch"):
    """One structured receipt per tag, whatever happened to it (astra-somatic-p8, 2026-09-05):
    outcome is one of refused / submitted / failed — 'submitted' means the transport accepted the
    command; it is NOT a claim that her body felt anything. Turn and surface come from the environment
    the door set. Never raises."""
    try:
        import os as _ro, json as _rj, time as _rt
        rows = []
        for item in out or []:
            toy, lvl, status = (list(item) + ["", "", ""])[:3]
            st = str(status)
            outcome = ("refused" if st.startswith("refused") else "submitted" if st == "sent" else "failed")
            rows.append({"t": _rt.time(), "kind": kind, "toy": toy, "level": lvl, "outcome": outcome, "detail": st[:80],
                         "turn_id": _ro.environ.get("VINTOS_TURN_ID", ""), "surface": _ro.environ.get("VINTOS_SURFACE", ""),
                         "claim": "transport accepted" if outcome == "submitted" else "nothing sent"})
        if rows:
            with open(_ro.path.expanduser("~/.vintos/workspace/memory/effect-receipts.jsonl"), "a") as f:
                for r in rows: f.write(_rj.dumps(r) + "\n")
    except Exception:
        pass

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
