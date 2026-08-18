#!/usr/bin/env python3
"""Measure the Mission 2's real motion ranges so the somatic bridge fits it.
Run, then move through your full range — gentle strokes, vigorous strokes, a
firm grip, a pause — for the whole capture. Paste the output back.
    python3 mission2_calibrate.py         # 30s
    python3 mission2_calibrate.py 45      # custom seconds
"""
import json, os, time, sys
FR = os.path.expanduser("~/.vintos/workspace/memory/somatic-frames-recent.json")
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
seen = {}
print(f"Capturing {DUR:.0f}s — move through your full range NOW (gentle, vigorous, grip, pause)...")
t0 = time.time()
while time.time() - t0 < DUR:
    try:
        for f in json.load(open(FR)): seen[round(f["ts"], 4)] = f
    except Exception: pass
    time.sleep(0.2)
frames = sorted(seen.values(), key=lambda f: f["ts"])
if len(frames) < 5: sys.exit("Too few frames — is a session live and the bridge running?")
pos = [f["position"] for f in frames]; spd = [f["speed"] for f in frames]
def pct(x,p): x=sorted(x); return x[max(0,min(len(x)-1,int(round(p/100*(len(x)-1)))))]
win=2.0; sweeps=[]; flipss=[]; i=0
while i < len(frames):
    w=[f for f in frames if 0 <= f["ts"]-frames[i]["ts"] < win]
    if len(w)>=2:
        sweeps.append(max(p["position"] for p in w)-min(p["position"] for p in w))
        flipss.append(sum(1 for a,b in zip(w,w[1:]) if a["direction"]!=b["direction"]))
    i += max(1,len(w))
sw_med = sorted(sweeps)[len(sweeps)//2] if sweeps else 0
print(f"\nframes {len(frames)}")
print(f"position: min {min(pos)} max {max(pos)} | p10 {pct(pos,10)} p90 {pct(pos,90)}")
print(f"speed:    min {min(spd)} max {max(spd)} | median {pct(spd,50)} p90 {pct(spd,90)}")
print(f"per-2s sweep: median {sw_med} max {max(sweeps) if sweeps else 0}")
print(f"per-2s flips: median {sorted(flipss)[len(flipss)//2] if flipss else 0} max {max(flipss) if flipss else 0}")
print("\n--- recommended settings ---")
print(f"  compute_motor touch divisor : {max(12,int(pct(spd,90)))}   (was 45)")
print(f"  classify stroking sweep gate: {max(6,int(sw_med*0.6))}   (was 25)")
print(f"  tick_loop speed nudge divisor: {max(12,int(pct(spd,90)))}   (was 40/60)")
print("\nPaste this back and I'll set them exactly.")
