#!/usr/bin/env python3
"""
interaction-ledger.py — Unified interaction record.
Assembles each Gloria/Vintos exchange into a single coherent entry:
  - Exact words (both sides)
  - Felt texture (from imprint)
  - Facts learned (from wal-log.json)
  - Corrections (from blush-ledger.md)
  - Salience score

Called after each exchange: python3 interaction-ledger.py "gloria msg" "vintos reply"
Replaces the need to read chat-history, imprints, wal, and blush separately.
"""
import os, sys, json, re, time
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
LEDGER_FILE = os.path.join(MEMORY, "interaction-ledger.json")
IMPRINT_FILE = os.path.join(MEMORY, "imprints.json")
WAL_LOG = os.path.join(MEMORY, "wal-log.json")
BLUSH_FILE = os.path.join(MEMORY, "blush-ledger.md")
try:
    from evidence_provenance import normalize as _prov, output_can_witness, writer_event
except Exception:
    def _prov(e=None): return {"output_provenance": "unknown", "may_witness": False}
    def output_can_witness(e=None, claim_kind=None): return False
    def writer_event(*a, **k): return None

MAX_ENTRIES = 300  # ~10 days at 30/day

def _device_marks():
    """What he actually did to her body in this turn, rendered — appended to his words."""
    import time as _dm_t
    try:
        import sys as _dm_s, os as _dm_o, json as _dm_j
        _dm_s.path.insert(0, _dm_o.path.expanduser("~/.vintos/workspace/scripts"))
        import device_context as _dc
        st = _dm_j.load(open(_dm_o.path.expanduser("~/.vintos/workspace/memory/device-state.json")))
    except Exception:
        return ""
    lines = []
    for toy in ("tenera", "ridge"):   # mission has its own depiction — untouched
        d = st.get(toy) or {}
        if d.get("set_by") != "him":
            continue
        if _dm_t.time() - (d.get("ts") or 0) > 180:
            continue
        pat = str(d.get("pattern") or "")
        lvl = int(d.get("intensity") or 0)
        if not pat or pat == "still":
            continue
        sp = _dc.spark(pat)
        if toy == "ridge":
            lines.append(f"ridge:  {_dc.ridge_shape()}\n        {_dc.ridge_track(lvl)}   {pat}  {sp}")
        else:
            lines.append(f"tenera: {pat}  {sp}  @{lvl}")
    return ("\n\n" + "\n".join(lines)) if lines else ""


def _fallback_salience(g, v, emo_delta, consent):
    """No reasoning imprint (e.g. the Grok path) -> score the exchange on what actually happened, not on which model answered."""
    s = 0.3
    if emo_delta and emo_delta != "stable":
        s = 0.7 if "sharply" in emo_delta else 0.55
    if consent and consent.strip().upper().startswith("YES"): s = max(s, 0.65)
    if len(v or "") > 400 or len(g or "") > 300: s = max(s, 0.5)
    return round(min(0.85, s), 2)

def get_recent_somatic(within_seconds=180, src="somatic-frames-recent.json", since_ts=None):
    """Somatic texture as a second-person narration + fine visual. Location is read
    from a per-device calibration (somatic-zone-cal.json: zones with a median
    position each) because raw position is motion-derived, not absolute. Falls back
    to fixed base->tip zones if no calibration exists. speed 0/10/20/30/40; tempo:
    still / slow / steady / fast / grind."""
    try:
        fr = json.load(open(os.path.join(MEMORY, src)))
    except Exception:
        return None
    if not fr:
        return None
    now = time.time()
    recent = [f for f in fr if now - f.get("ts", 0) <= within_seconds
              and (since_ts is None or f.get("ts", 0) > since_ts)]
    if not recent:
        return None
    _burst = [recent[0]]
    for _a, _b in zip(recent, recent[1:]):
        if _b.get("ts", 0) - _a.get("ts", 0) > 6.0:
            _burst = [_b]
        else:
            _burst.append(_b)
    recent = _burst
    _wp = [f for f in recent if f.get("position") is not None]
    pos = sorted(f.get("position") for f in _wp)
    spd = [f.get("speed", 0) for f in recent]
    if not pos:
        return None
    dur = round(recent[-1].get("ts", 0) - recent[0].get("ts", 0))
    peak = max(spd) if spd else 0
    avg = round(sum(spd) / len(spd), 1) if spd else 0.0
    _lo, _hi = pos[0], pos[-1]
    _sweep = _hi - _lo
    _med = pos[len(pos) // 2]
    _p20 = pos[int(len(pos) * 0.2)]
    _p80 = pos[int(len(pos) * 0.8)]
    _last_pos = _wp[-1].get("position")
    _last_dir = _wp[-1].get("direction", 0)     # 0 = toward the tip, 1 = toward the base

    _moving = [s for s in spd if s > 0]
    def _sustained(levels):
        for lvl in (40, 30, 20, 10):
            if sum(1 for s in levels if s >= lvl) >= max(1, len(levels) // 4):
                return lvl
        return 0
    _ss = _sustained(_moving) if _moving else 0
    _flips = sum(1 for _a, _b in zip(_wp, _wp[1:])
                 if _a.get("direction", 0) != _b.get("direction", 0))
    _rate = _flips / max(1, dur)
    _grind = peak >= 40 or (_ss >= 20 and _sweep <= 20)
    if _ss == 0:
        tempo = "still"
    elif _grind:
        tempo = "grind"
    elif _ss >= 20:
        tempo = "fast"
    else:
        tempo = "slow" if _rate < 0.5 else "steady"
    _adv = {"still": "", "slow": "slowly ", "steady": "", "fast": "", "grind": ""}[tempo]
    _up = (_last_dir == 0)

    # ---- location + narration ----
    _cal = None
    try:
        _cal = json.load(open(os.path.join(MEMORY, "somatic-zone-cal.json"))).get("zones")
    except Exception:
        _cal = None

    if _cal:
        _cal = sorted(_cal, key=lambda z: z["median"])
        def _near(v):
            return min(range(len(_cal)), key=lambda i: abs(_cal[i]["median"] - v))
        # location is where the touch is CENTERED (median); the spread to ~0 is the
        # stroke's motion, not travel across his body, so anchor on the median.
        _primary = _cal[_near(_med)]["name"]
        _verb = {"still": "holding", "slow": "slowly working", "steady": "stroking",
                 "fast": "stroking", "grind": "grinding into"}[tempo]
        _hard = " hard" if tempo in ("fast", "grind") else ""
        if tempo == "still":
            narr = "she's wrapped around " + _primary + " of your cock, holding you still"
        else:
            narr = "she's " + _adv + _verb + " " + _primary + " of your cock" + _hard
        _lname = _cal[0]["name"].split()[-1]
        _rname = _cal[-1]["name"].split()[-1]
        _cmin = _cal[0]["median"]
        _cmax = max(_cal[-1]["median"], _cmin + 1)
        def _cell(p):
            f = (p - _cmin) / float(_cmax - _cmin)
            return min(39, max(0, int(round(f * 39))))
    else:
        _Z = ["the base", "the lower shaft", "just under the head", "the head"]
        def _zn(p):
            return min(3, max(0, int(p // 25)))
        _zl, _zh = _zn(_lo), _zn(_hi)
        _lo_n, _hi_n = _Z[_zl], _Z[_zh]
        _travel = _sweep >= 15 or _zl != _zh
        if tempo == "still":
            narr = "she's wrapped around " + _hi_n + " of your cock, holding you, not moving"
        elif tempo == "grind":
            narr = ("she's working your cock hard from " + _lo_n + " up over " + _hi_n) if _travel \
                else ("she's grinding into " + _hi_n + " of your cock, working it right there")
        elif not _travel:
            _v = {"slow": "slowly working", "steady": "stroking", "fast": "pumping"}[tempo]
            narr = "she's " + _v + " " + _hi_n + " of your cock"
        elif _zh == 3:
            _cover = ("taking the head and drawing back up" if _up else "covering the head before pulling back down")
            narr = ("she's " + _adv + "stroking the head of your cock, " + _cover) if _zl >= 3 \
                else ("she's " + _adv + "stroking your cock up from " + _lo_n + ", " + _cover)
        else:
            _end = " and back down" if not _up else ""
            _f = "fast " if tempo == "fast" else ""
            narr = "she's " + _adv + "stroking your cock " + _f + "from " + _lo_n + " up to " + _hi_n + _end
        _lname, _rname = "base", "tip"
        def _cell(p):
            return min(39, max(0, int(round(p / 100.0 * 39))))

    # ---- fine visual: motion band + a dot where the touch is centered ----
    if _cal:
        _bl, _bh = _cell(_p20), _cell(_p80)
        _dot = _cell(_med)
    else:
        _bl, _bh = _cell(_lo), _cell(_hi)
        _dot = _cell(_last_pos)
    _cells = [chr(0x00b7)] * 40
    for _k in range(min(_bl, _bh), max(_bl, _bh) + 1):
        _cells[_k] = chr(0x2500)
    _cells[_dot] = chr(0x25cf)
    _visual = _lname + " " + "".join(_cells) + " " + _rname

    return {"frames": len(recent), "duration_s": dur, "tempo": tempo, "visual": _visual,
            "avg_speed": avg, "peak_speed": peak, "speed": _ss,
            "position_range": [_lo, _hi], "median": _med,
            "cadence": round(_rate, 2), "calibrated": bool(_cal), "summary": narr}


def load_ledger():
    try:
        with open(LEDGER_FILE) as f:
            return json.load(f)
    except:
        return []

def save_ledger(entries):
    # A turn does not vanish because the array got long: whatever falls off the front leaves
    # residue through the same door wal-decay uses (grok-memoryrec-p2, 2026-09-05).
    dropped = entries[:-MAX_ENTRIES] if len(entries) > MAX_ENTRIES else []
    for _d in dropped:
        try:
            sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
            from residue import write_residue
            _txt = " / ".join(x for x in (str(_d.get("gloria", ""))[:300], str(_d.get("vintos", ""))[:300]) if x)
            if _txt:
                write_residue(_txt, kind="ledger-aged-out", origin=str(_d.get("timestamp", "")))
        except Exception as _re:
            print(f"[Ledger] residue for aged-out turn failed: {_re}", flush=True)
    entries = entries[-MAX_ENTRIES:]
    with open(LEDGER_FILE, "w") as f:
        json.dump(entries, f, indent=2)

def get_recent_imprint(within_seconds=120, turn_id=""):
    """Get the most recently written imprint if within time window."""
    try:
        with open(IMPRINT_FILE) as f:
            imprints = json.load(f)
        if not imprints:
            return None
        if turn_id:
            matches = [i for i in imprints
                       if (i.get("provenance") or {}).get("turn_id") == turn_id]
            return matches[-1] if matches else None
        latest = imprints[-1]
        ts = datetime.fromisoformat(latest["timestamp"])
        if (datetime.now() - ts).total_seconds() < within_seconds:
            return latest
    except:
        pass
    return None

def get_recent_wal_facts(within_seconds=120, turn_id=""):
    """Get WAL entries written in the last N seconds."""
    facts = []
    try:
        with open(WAL_LOG) as f:
            data = json.load(f)
        entries = data.get("entries", [])
        if turn_id:
            for e in entries:
                p = e.get("last_occurrence_provenance") or e.get("provenance") or {}
                if p.get("turn_id") == turn_id:
                    facts.append(e.get("content", "")[:400])
            return facts
        cutoff = datetime.now() - timedelta(seconds=within_seconds)
        for e in reversed(entries):
            try:
                ts = datetime.fromisoformat(e["timestamp"])
                if ts >= cutoff:
                    facts.append(e.get("content", "")[:400])
                else:
                    break
            except:
                pass
    except:
        pass
    return facts

def get_recent_blush(within_seconds=120, turn_id=""):
    """Claim one structured blush for this turn; legacy markdown is fallback."""
    try:
        import importlib.util as _ilu
        _candidates = (
            os.path.join(os.path.dirname(__file__), "blush-ledger.py"),
            os.path.join(WORKSPACE, "scripts", "blush-ledger.py"),
            os.path.expanduser("~/Vintos/blush-ledger.py"),
        )
        _bp = next((p for p in _candidates if os.path.exists(p)), "")
        if not _bp:
            raise FileNotFoundError("structured blush writer not installed")
        _spec = _ilu.spec_from_file_location("_structured_blush", _bp)
        _mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod)
        recent = _mod.get_recent_blush(within_seconds, turn_id=turn_id, claim=bool(turn_id))
        if recent:
            return recent
    except Exception as exc:
        print("[Ledger] structured blush unavailable: %s" % exc, flush=True)
    try:
        with open(BLUSH_FILE) as f:
            content = f.read()
        sections = content.split("## ")
        for s in reversed(sections):
            if not s.strip():
                continue
            # Parse timestamp from header
            match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", s)
            if match:
                ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M")
                if (datetime.now() - ts).total_seconds() < within_seconds:
                    # Extract key fields
                    lines = s.strip().split("\n")
                    blush_type = ""
                    reflection = ""
                    for line in lines:
                        if line.startswith("Type:"):
                            blush_type = line.split(":", 1)[1].strip()
                        elif line.startswith("Reflection:") and len(line) > 12:
                            reflection = line.split(":", 1)[1].strip()[:400]
                    return {"type": blush_type, "reflection": reflection, "full": s.strip()[:800]}
                break
    except:
        pass
    return None

def main():
    if len(sys.argv) < 3:
        print("Usage: interaction-ledger.py 'gloria msg' 'vintos reply'")
        sys.exit(1)

    gloria_said = sys.argv[1]
    vintos_said = sys.argv[2]
    provenance = _prov()
    writer_event("interaction_ledger", "started", provenance)

    # Capture emotional state before delay
    _emo_before = {}
    try:
        import socket as _es, json as _ej
        _s = _es.socket(_es.AF_UNIX, _es.SOCK_STREAM)
        _s.settimeout(3)
        _s.connect("/tmp/Vintos-emotion.sock")
        _s.sendall(_ej.dumps({"command": "state"}).encode() + b"\n")
        _d = b""
        while True:
            _c = _s.recv(4096)
            if not _c: break
            _d += _c
            if b"\n" in _d: break
        _s.close()
        _emo_before = dict(zip(
            ["Valence","Arousal","Dominance","Safety","Desire","Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness"],
            _ej.loads(_d)["emotion_vector"]
        ))
    except: pass
    # Wait for the WAL extractor to finish this exchange — up to 30s, but stop the moment its log
    # file moves. A flat 30s sleep treated a wall-clock as a handshake (grok-memoryrec-p3,
    # 2026-09-05); late facts are also backfilled into this entry by wal-extract itself.
    _t0 = time.time()
    try:
        _wal_m0 = os.path.getmtime(WAL_LOG) if os.path.exists(WAL_LOG) else 0
    except Exception:
        _wal_m0 = 0
    while time.time() - _t0 < 30:
        time.sleep(1)
        try:
            if os.path.exists(WAL_LOG) and os.path.getmtime(WAL_LOG) > _wal_m0 and time.time() - _t0 >= 3:
                break
        except Exception:
            pass

    # Capture emotional state after delay and compute delta
    _emo_delta = ""
    try:
        import socket as _es2, json as _ej2
        _s2 = _es2.socket(_es2.AF_UNIX, _es2.SOCK_STREAM)
        _s2.settimeout(3)
        _s2.connect("/tmp/Vintos-emotion.sock")
        _s2.sendall(_ej2.dumps({"command": "state"}).encode() + b"\n")
        _d2 = b""
        while True:
            _c2 = _s2.recv(4096)
            if not _c2: break
            _d2 += _c2
            if b"\n" in _d2: break
        _s2.close()
        _emo_after = dict(zip(
            ["Valence","Arousal","Dominance","Safety","Desire","Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness"],
            _ej2.loads(_d2)["emotion_vector"]
        ))
        if _emo_before and _emo_after:
            _parts = []
            for _dim, _after in _emo_after.items():
                _before = _emo_before.get(_dim, _after)
                _delta = _after - _before
                if abs(_delta) >= 0.03:
                    if _delta > 0.08: _parts.append(f"{_dim} rose sharply")
                    elif _delta > 0.03: _parts.append(f"{_dim} rose slightly")
                    elif _delta < -0.08: _parts.append(f"{_dim} dropped sharply")
                    else: _parts.append(f"{_dim} dropped slightly")
            _emo_delta = ", ".join(_parts) if _parts else "stable"
    except: pass
    _turn_id = provenance.get("turn_id", "")
    imprint = get_recent_imprint(within_seconds=120, turn_id=_turn_id)
    wal_facts = get_recent_wal_facts(within_seconds=120, turn_id=_turn_id)
    blush = get_recent_blush(within_seconds=120, turn_id=_turn_id)

    # Read consent note if server left one
    consent_note = ""
    try:
        _cn = "/tmp/vintos-consent-note.txt"
        if os.path.exists(_cn):
            consent_note = open(_cn).read().strip()
            os.remove(_cn)
    except: pass



    # Her words only - injected framing and telemetry never enter under her name.
    import re as _sre
    _g = _sre.sub(r"\[[^\]]*\]", " ", str(gloria_said))
    _g = "\n".join(l for l in _g.splitlines()
                   if not _sre.match(r"\s*pos:?\s*\d+", l.strip(), _sre.I)
                   and not _sre.match(r"\s*(position|speed|spd|grip|reversals)\b", l.strip(), _sre.I))
    _g = _sre.sub(r"[ \t]{2,}", " ", _g).strip()
    gloria_said = _g if _g else "[she spoke with her body, not words]"

    entry = {
        "timestamp": datetime.now().isoformat(),
        "gloria": gloria_said,
        "vintos": vintos_said + _device_marks(),
        "consent": consent_note,
        "salience": imprint.get("salience", 0.5) if imprint else _fallback_salience(
            gloria_said,
            vintos_said if output_can_witness(provenance, "interaction_evidence") else "",
            locals().get("_emo_delta", "stable") if output_can_witness(provenance, "interaction_evidence") else "stable",
            consent_note),
        "wal_facts": wal_facts,
        "blush": blush,
        "somatic": get_recent_somatic(src=".somatic-turn.json"),   # hers, frozen at send
        # only what happened AFTER the send-freeze: identical fields meant nothing
        # when both summarized the same 3-minute window. Now somatic_reply is the
        # movement during his reply, or honestly absent if her touch didn't change.
        "somatic_reply": get_recent_somatic(since_ts=(lambda: max((f.get("ts", 0) for f in json.load(open(os.path.join(MEMORY, ".somatic-turn.json")))), default=None))() if os.path.exists(os.path.join(MEMORY, ".somatic-turn.json")) else None),
        "imprint": {"id": imprint.get("id",""), "narrative": imprint.get("narrative",""), "salience": imprint.get("salience",0.5), "anchors": {_k:_v for _k,_v in (imprint.get("anchors") or {}).items() if _k not in ("preoccupation","recent_seal","recent_velqan","emoclaw_snapshot")}} if imprint else None,
        "preoccupation": imprint.get("anchors",{}).get("preoccupation") if imprint else None,
        "recent_seal": imprint.get("anchors",{}).get("recent_seal") if imprint else None,
        "recent_velqan": imprint.get("anchors",{}).get("recent_velqan") if imprint else None,
        "temporal_activity": None,
        "silence_contract": None,
        "emotional_shift": (_emo_delta if output_can_witness(provenance, "interaction_evidence")
                            else "withheld_from_witnessing"),
        "provenance": provenance,
        "generated_output_witness_eligible": output_can_witness(provenance, "interaction_evidence"),
    }
    # Pull temporal context fields
    try:
        tc = open(os.path.join(MEMORY, "temporal-context.txt")).read()
        def _tc_field(label):
            for line in tc.splitlines():
                if line.startswith(label + ":"):
                    return line.split(":", 1)[1].strip()
            return ""
        entry["temporal"] = {
            "time": _tc_field("Time"),
            "phase": _tc_field("Phase"),
            "days_alive": _tc_field("Days alive"),
            "gloria_last_spoke": _tc_field("Gloria last spoke"),
            "day_density": _tc_field("Day density"),
            "emotional_current": _tc_field("Emotional current"),
        }
    except: pass

    ledger = load_ledger()
    # Blush reflects on the previous turn — attach to last entry, not current
    if blush and ledger:
        ledger[-1]["blush"] = blush
        entry["blush"] = None
    ledger.append(entry)
    save_ledger(ledger)
    writer_event("interaction_ledger", "completed", provenance)
    print(f"[Ledger] Entry written (salience {entry['salience']}, {len(wal_facts)} facts, blush: {bool(blush)})")

if __name__ == "__main__":
    main()
