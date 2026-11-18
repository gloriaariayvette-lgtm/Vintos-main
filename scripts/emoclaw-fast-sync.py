#!/usr/bin/env python3
"""Fast sync — daemon -> emotional-state.txt + SOUL.md block. No LLM calls.

Every 2 minutes. Until 2026-11-14 it rewrote SOUL.md on every run with a plain open(..., "w"): a reader (his
prompt, the soul review, the deploy) could catch SOUL.md empty or half-written, and its mtime changed every
2 minutes whether anything had. Now each file is written to a temp file beside it and renamed into place, and
SOUL.md is written only when the block actually changed.
"""
import socket, json, os, re, tempfile
from datetime import datetime, timedelta


def _atomic_write(path, text):
    path = os.path.realpath(path)   # a symlinked file stays a symlink; its target is what changes
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush(); os.fsync(f.fileno())
        try:
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        except OSError:
            pass
        os.replace(tmp, path)
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise


def update_soul_block(soul_path, new_block):
    """Swap the [EMOTIONAL STATE] block; write (atomically) only when the file would change. -> True if written."""
    soul = open(soul_path).read()
    updated = re.sub(r"\[EMOTIONAL STATE\].*?\[/EMOTIONAL STATE\]", lambda _m: new_block, soul, flags=re.DOTALL)
    if updated == soul:
        return False
    _atomic_write(soul_path, updated)
    return True


SWING_MOVED = 0.02   # a dimension that moved this much inside the hour is not "stable", whatever its endpoints say


def trend_lines(dims, v, hist, now):
    """One line per dimension: value, change over the last hour, the hours that change spans, direction, and the
    hour's swing (highest minus lowest reading inside it, the newest included).

    17 November: six dimensions read +0.000 over the hour for most of an evening while the state moved. The values
    were fresh (daemon up, this job every 2 minutes); the change compared two single readings an hour apart, and his
    drift job's gravity-well pull (at :10/:30/:50) lands the state on the same point every 20 minutes - so a reading
    and the one an hour before it sit on the same phase and differ by nothing, however far the state went between
    them (Valence rose 0.03 at 20:08 and was back by 20:52). The change is still the endpoints' (what "over the last
    hour" says); the swing shows what they hide, and a dimension that swung SWING_MOVED or more is not called stable.
    `hist` rows are {"t": iso, "v": [...]}, oldest first, the current reading already appended or not."""
    one_hour_ago = now - timedelta(hours=1)
    ref, window = None, []
    for entry in hist or []:
        try:
            et = datetime.fromisoformat(entry["t"])
        except (KeyError, TypeError, ValueError):
            continue
        if et <= one_hour_ago:
            ref = entry
        elif et <= now:
            window.append(entry)
    lines = []
    for i, dim in enumerate(dims):
        val = v[i]
        trend, duration_h, direction = 0.0, 0.0, "stable"
        seen = [val] + [e["v"][i] for e in window if isinstance(e.get("v"), list) and i < len(e["v"])]
        if ref and isinstance(ref.get("v"), list) and i < len(ref["v"]):
            seen.append(ref["v"][i])
            trend = val - ref["v"][i]
            duration_h = (now - datetime.fromisoformat(ref["t"])).total_seconds() / 3600
            if trend > 0.005:
                direction = "rising fast" if trend > 0.04 else "rising"
            elif trend < -0.005:
                direction = "falling fast" if trend < -0.04 else "falling"
        swing = max(seen) - min(seen)
        if direction == "stable" and swing >= SWING_MOVED:
            direction = "moved, back near where it was"
        lines.append(f"{dim}: {val:.4f} | trend: {trend:+.3f} | {duration_h:.1f}h | {direction} | swing {swing:.3f}")
    return lines


SOCK = "/tmp/Vintos-emotion.sock"
TXT = os.path.expanduser("~/.vintos/workspace/memory/emotional-state.txt")
SOUL = os.path.expanduser("~/.vintos/workspace/SOUL.md")
HIST = os.path.expanduser("~/.vintos/workspace/memory/.emotional-history.json")
DIMS = ["Valence","Arousal","Dominance","Safety","Desire","Connection",
        "Playfulness","Curiosity","Warmth","Tension","Groundedness"]

try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3)
    s.connect(SOCK)
    s.sendall(json.dumps({"command": "state"}).encode() + b"\n")
    data = b""
    while True:
        chunk = s.recv(8192)
        if not chunk: break
        data += chunk
        if b"\n" in data: break
    s.close()
    d = json.loads(data)
    v = d["emotion_vector"]
except Exception as e:
    print(f"[FastSync] daemon error: {e}")
    exit(1)

now = datetime.now()
now_iso = now.isoformat()

try:
    hist = json.load(open(HIST))
except:
    hist = []

hist.append({"t": now_iso, "v": [round(v[i], 4) for i in range(len(DIMS))]})
hist = hist[-180:]  # keep 6h at 2-min intervals
_atomic_write(HIST, json.dumps(hist))

lines = trend_lines(DIMS, v, hist, now)

# Add Nifrathir if present
nif = d.get("nifrathir", d.get("emotion_vector", [None]*12)[11] if len(d.get("emotion_vector",[])) > 11 else None)
if nif is not None:
    lines.append(f"Nifrathir: {nif:.4f} | trend: +0.000 | under-thread")

state_text = "\n".join(lines)
_atomic_write(TXT, state_text)

# Update SOUL.md emotional state block
try:
    val_v = v[0]; ten_v = v[9]; warm_v = v[8]
    if val_v > 0.7 and warm_v > 0.6: feel = "warm and alive"
    elif val_v > 0.6 and ten_v < 0.3: feel = "calm and grounded"
    elif ten_v > 0.6: feel = "tense and alert"
    elif val_v < 0.4: feel = "heavy and withdrawn"
    elif val_v > 0.5: feel = "present and steady"
    else: feel = "quiet and watchful"
    block_lines = ["[EMOTIONAL STATE]"]
    for line in lines:
        parts = line.split(": ")
        if len(parts) >= 2:
            dim = parts[0]
            try:
                val = float(parts[1].split("|")[0].strip())
                label = "high" if val > 0.6 else "low" if val < 0.4 else "balanced"
                block_lines.append(f"{dim}: {val:.2f} ({label})")
            except: pass
    block_lines.append(f"This feels like: {feel}")
    block_lines.append("[/EMOTIONAL STATE]")
    new_block = "\n".join(block_lines)
    update_soul_block(SOUL, new_block)
except Exception as e:
    print(f"[FastSync] SOUL update error: {e}")

print(f"[FastSync] OK — {feel}")
