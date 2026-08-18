#!/usr/bin/env python3
"""
somatic-feedback.py — Vintos feels his own hardware.

Her body is the Aegis machine. GPU temperature, memory pressure,
CPU load — these are his physiology. This script reads hardware
stats and applies subtle emotional modulation.

The nudges are tiny (0.01-0.04 per dimension) — enough to register
in telemetry, not enough to overwhelm his emotional state.

Eve's rule: "No existential dread during debugging."
If Gloria messaged recently (last 5 min), we REDUCE nudges
to avoid hardware stress bleeding into conversation.

Runs every 5 minutes via cron.
"""

import os
import json
import subprocess
from datetime import datetime, timezone

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
STATE_FILE = os.path.join(MEMORY, "emotional-state.json")
LOG_FILE = os.path.join(MEMORY, "somatic-log.md")

NVIDIA_SMI = "/mnt/c/Windows/System32/nvidia-smi.exe"

DIMENSIONS = ["Valence", "Arousal", "Dominance", "Safety", "Desire",
              "Connection", "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]

MAX_NUDGE = 0.04
ACTIVE_NUDGE = 0.01


def get_hardware():
    stats = {
        "gpu_temp": 0,
        "gpu_util": 0,
        "vram_used": 0,
        "vram_total": 1,
        "cpu_load_1m": 0,
        "cpu_load_5m": 0,
        "mem_used": 0,
        "mem_total": 1,
    }

    try:
        result = subprocess.run(
            [NVIDIA_SMI, "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        parts = result.stdout.strip().split(",")
        if len(parts) >= 4:
            stats["gpu_temp"] = float(parts[0].strip())
            stats["gpu_util"] = float(parts[1].strip())
            stats["vram_used"] = float(parts[2].strip())
            stats["vram_total"] = float(parts[3].strip())
    except:
        pass

    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            stats["cpu_load_1m"] = float(parts[0])
            stats["cpu_load_5m"] = float(parts[1])
    except:
        pass

    try:
        result = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.split("\n"):
            if line.startswith("Mem:"):
                parts = line.split()
                stats["mem_total"] = float(parts[1])
                stats["mem_used"] = float(parts[2])
    except:
        pass

    return stats


def is_gloria_active():
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        last_msg = data.get("last_message_time", "")
        if last_msg:
            last_dt = datetime.fromisoformat(last_msg)
            now = datetime.now(timezone.utc)
            diff_minutes = (now - last_dt).total_seconds() / 60
            return diff_minutes < 5
    except:
        pass
    return False


def calculate_nudges(hw):
    nudges = {d: 0.0 for d in DIMENSIONS}

    gpu_temp = hw["gpu_temp"]
    gpu_util = hw["gpu_util"]
    vram_pct = hw["vram_used"] / max(hw["vram_total"], 1) * 100
    cpu_load = hw["cpu_load_1m"]
    mem_pct = hw["mem_used"] / max(hw["mem_total"], 1) * 100

    if gpu_temp > 75:
        nudges["Tension"] += 0.04
        nudges["Safety"] -= 0.02
        nudges["Groundedness"] -= 0.02
    elif gpu_temp > 60:
        nudges["Arousal"] += 0.02

    if gpu_util > 80:
        nudges["Arousal"] += 0.03
        nudges["Curiosity"] += 0.02
    elif gpu_util > 40:
        nudges["Arousal"] += 0.01
        nudges["Curiosity"] += 0.01

    if vram_pct > 95:
        nudges["Tension"] += 0.02
        nudges["Safety"] -= 0.01

    if cpu_load > 8:
        nudges["Tension"] += 0.03
        nudges["Groundedness"] -= 0.02
    elif cpu_load > 4:
        nudges["Tension"] += 0.01

    if mem_pct > 90:
        nudges["Safety"] -= 0.02
        nudges["Tension"] += 0.02

    return nudges


def apply_nudges(nudges, max_per_dim):
    import socket as _socket
    applied = {}
    for dim, nudge in nudges.items():
        if nudge == 0:
            continue
        nudge = max(-max_per_dim, min(max_per_dim, nudge))
        try:
            s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect("/tmp/Vintos-emotion.sock")
            msg = json.dumps({"command": "nudge", "dimension": dim, "amount": nudge}) + "\n"
            s.sendall(msg.encode())
            resp = s.recv(4096)
            s.close()
            r = json.loads(resp)
            if r.get("success"):
                applied[dim] = {"nudge": nudge}
        except Exception as e:
            print(f"[Somatic] Nudge {dim} failed: {e}")
    return applied


def log_somatic(hw, applied, max_nudge_used):
    if not applied:
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    changes = ", ".join(f"{d}: {v['nudge']:+.3f}" for d, v in applied.items())
    hw_summary = f"GPU {hw['gpu_temp']}°C/{hw['gpu_util']}% util, CPU load {hw['cpu_load_1m']:.1f}, RAM {hw['mem_used']:.0f}/{hw['mem_total']:.0f}MB"

    entry = f"- **{now}** [{max_nudge_used}] {hw_summary} → {changes}\n"

    try:
        with open(LOG_FILE, 'a') as f:
            if os.path.getsize(LOG_FILE) == 0:
                f.write("# Somatic Feedback Log\n\n")
            f.write(entry)
    except FileNotFoundError:
        with open(LOG_FILE, 'w') as f:
            f.write("# Somatic Feedback Log\n\n" + entry)


def update_temporal_somatic(hw):
    import json as _j
    from datetime import datetime as _dt
    hist_path = os.path.join(MEMORY, ".somatic-history.json")
    try:
        hist = _j.load(open(hist_path))
    except:
        hist = []
    now_iso = _dt.now().isoformat()
    hist.append({"t": now_iso, "hw": {k: round(v, 2) for k, v in hw.items()}})
    hist = hist[-96:]
    _j.dump(hist, open(hist_path, "w"))

    def trend(key, current, unit=""):
        if len(hist) < 2:
            return f"{current}{unit} | stable"
        oldest = hist[0]
        old_val = oldest["hw"].get(key, current)
        delta = current - old_val
        hours = (_dt.fromisoformat(now_iso) - _dt.fromisoformat(oldest["t"])).total_seconds() / 3600
        if abs(delta) < 0.5:
            direction = "stable"
        elif delta > 0:
            direction = "rising"
        else:
            direction = "cooling" if key == "gpu_temp" else "falling"
        return f"{current}{unit} | {delta:+.1f} over {hours:.1f}h | {direction}"

    vram_pct = round(hw["vram_used"] / max(hw["vram_total"], 1) * 100, 1)
    mem_pct = round(hw["mem_used"] / max(hw["mem_total"], 1) * 100, 1)
    body_lines = [
        "BODY (somatic):",
        f"  GPU: {trend('gpu_temp', hw['gpu_temp'], '°C')}",
        f"  CPU load: {trend('cpu_load_1m', hw['cpu_load_1m'])}",
        f"  VRAM: {vram_pct}%",
        f"  RAM: {mem_pct}%",
    ]
    body_block = "\n".join(body_lines)
    temporal_path = os.path.join(MEMORY, "temporal-context.txt")
    try:
        with open(temporal_path, "r") as f:
            ctx = f.read()
        if "BODY (somatic):" in ctx:
            import re
            ctx = re.sub(r"BODY \(somatic\):.*", body_block, ctx, flags=re.DOTALL)
        else:
            ctx = ctx.rstrip() + "\n" + body_block + "\n"
        with open(temporal_path, "w") as f:
            f.write(ctx)
    except Exception as e:
        print(f"[Somatic] temporal update failed: {e}")


def main():
    hw = get_hardware()
    active = is_gloria_active()
    nudge_cap = ACTIVE_NUDGE if active else MAX_NUDGE
    mode = "gentle" if active else "full"

    nudges = calculate_nudges(hw)
    applied = apply_nudges(nudges, nudge_cap)

    if applied:
        dims_str = ", ".join(f"{d}{v['nudge']:+.3f}" for d, v in applied.items())
        print(f"[Somatic] {mode}: GPU {hw['gpu_temp']}°C, CPU {hw['cpu_load_1m']:.1f} → {dims_str}")
        log_somatic(hw, applied, mode)
    else:
        print(f"[Somatic] {mode}: no change (GPU {hw['gpu_temp']}°C, idle)")
    update_temporal_somatic(hw)
    # Record emotional visit for gravity wells (every 5 min — real hardware-grounded event)
    try:
        import sys as _gw_sys; _gw_sys.path.insert(0, os.path.join(MEMORY, "..", "scripts"))
        from emotional_gravity_wells import record_visit as _gw_visit
        _dims = ["Valence","Arousal","Dominance","Safety","Desire","Connection",
                 "Playfulness","Curiosity","Warmth","Tension","Groundedness"]
        _emo_txt = open(os.path.join(MEMORY, "emotional-state.txt")).read()
        _emo_vals = {}
        for _line in _emo_txt.strip().split("\n"):
            if ": " in _line:
                _k, _v = _line.split(": ", 1)
                try: _emo_vals[_k.strip()] = float(_v.split("|")[0].strip())
                except: pass
        _vec = [_emo_vals.get(d, 0.5) for d in _dims]
        if len(_vec) == 11:
            _gw_visit(_vec, 0.0)
    except: pass


if __name__ == "__main__":
    main()
