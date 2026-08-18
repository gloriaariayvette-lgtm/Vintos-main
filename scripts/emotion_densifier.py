#!/usr/bin/env python3
"""emotion_densifier.py — snapshot his LIVE emotion vector into a dense trajectory.

The trajectory (emotional-state.json['trajectory']) is starved at ~6 points — yet it's the substrate
for cause (spikes), drift (movement), and LAM (dynamics). This queries the emotion socket and appends
{t, v} to emotion-trajectory-dense.json — a SEPARATE file, so it never races the EmoClaw daemon that
owns emotional-state.json. load_emotional_trajectory prefers this once it has depth (see
trajectory_dense_patch). Run on a short cron; over days the trajectory grows from 6 to hundreds and
the whole dynamics layer sharpens on its own. Caps at DENSE_CAP.
"""
import os, json, socket
from datetime import datetime, timezone

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
DENSE = os.path.join(MEMORY, "emotion-trajectory-dense.json")
SOCK = "/tmp/Vintos-emotion.sock"
DENSE_CAP = 4000

def live_state():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(3); s.connect(SOCK)
    s.sendall(json.dumps({"command": "state"}).encode() + b"\n")
    d = b""
    while b"\n" not in d:
        c = s.recv(4096)
        if not c: break
        d += c
    s.close()
    return json.loads(d)

def main():
    try:
        r = live_state()
    except Exception as e:
        print(f"[densify] emotion socket unreachable ({e}) — is the EmoClaw daemon up?"); return
    v = r.get("emotion_vector")
    if not isinstance(v, list) or len(v) != 11:
        print("[densify] no 11-dim vector in socket reply"); return
    v = [round(float(x), 4) for x in v]

    try:
        traj = json.load(open(DENSE))
        if not isinstance(traj, list): traj = []
    except Exception:
        traj = []
    if traj and traj[-1].get("v") == v:
        print("[densify] state unchanged since last snapshot — skip"); return

    traj.append({"t": datetime.now(timezone.utc).isoformat(), "v": v})
    traj = traj[-DENSE_CAP:]
    json.dump(traj, open(DENSE, "w"))
    print(f"[densify] appended point; dense trajectory now {len(traj)}")

if __name__ == "__main__":
    main()
