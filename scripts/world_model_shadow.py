#!/usr/bin/env python3
"""MAMEPA in shadow: a small Mamba state model of what Gloria is doing between observations, run live but read
by nothing.

The model was trained offline (JEPA-style, pure PyTorch) on a 5-minute grid of the streams he already receives:
Watch readings, wifi home/away, phone-in-bedroom arrivals, the times of her messages, his avatar app opening, the
kitchen and bedroom phone-presence visits, the three house boards (bathroom with its shower flag, living-room
sofa, office chair) and doorbell face matches of her. Missing readings are marked missing, never filled, and a
stream before its first record is missing, not zero.

Every run:
  1. loads the trained weights from a private path outside the repository (MAMEPA_WEIGHTS or --weights);
  2. rebuilds the last WINDOW_DAYS of the grid from the live stores, opening them for reading only;
  3. advances the state over that window from zero (the model was trained to warm up from zero in 12 hours);
  4. writes memory/world-model-shadow.json atomically: what it expects 30 minutes, 2 hours and 6 hours ahead,
     how unsure it is, and the time and freshness of each input stream; and appends one compact row to
     memory/world-model-shadow-history.jsonl (bounded) so the shadow can be scored later against what happened.

Nothing reads these two files: no prompt, no context, no consumer (broker/tests/test_world_model_shadow.py holds
that). No network, no model calls, no writes anywhere else.

    world_model_shadow.py [--weights PATH] [--print]
"""
import argparse, fcntl, glob, hashlib, json, math, os, sys, tempfile, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
DOOR_DIR = os.environ.get("MAMEPA_DOOR_DIR") or os.path.expanduser("~/doorbell-voice/live/encounters")
OUT_NAME, HIST_NAME = "world-model-shadow.json", "world-model-shadow-history.jsonl"
LOCK_SUFFIX = ".lock"                     # the history's own stable lock file, beside it
HISTORY_ROWS = int(os.environ.get("MAMEPA_HISTORY_ROWS") or 4320)        # 30 days at one run per 10 minutes
WINDOW_DAYS = 8
TZ = ZoneInfo("America/Chicago")
BIN = 300
H = {"30m": 6, "2h": 24, "6h": 72}
CONT = ["heart_rate", "hrv_sdnn", "respiratory_rate", "resting_heart_rate"]
OCC = ["in_kitchen", "in_bedroom", "in_bathroom", "on_sofa", "office_chair"]
BINARY = ["home", "charging"] + OCC
MOTION = ["stationary", "walking", "running", "automotive", "cycling"]
COUNTS = ["her_messages", "bedroom_arrivals", "avatar_opens", "showers", "door_her"]
CH = CONT + BINARY + ["motion"] + COUNTS
BOARD_OCC = {"house-steam": "in_bathroom", "house-press-mic": "on_sofa", "house-touch": "office_chair"}
DOOR_THRESH = float(os.environ.get("FACE_THRESHOLD", "0.36"))     # the face matcher's own threshold
DOOR_NAMES = ("gloria", "eve")                                     # her enrolled names at the door
SOURCES = ["watch-presence-history.jsonl", "sensor-reactions.jsonl", "bedroom-arrivals.jsonl", "interaction-ledger.json",
           "chat-canonical.jsonl", "avatar-presence-log.json", "kitchen-visits.jsonl", "bedroom-visits.jsonl",
           "house-board-visits.jsonl"]
CHANNEL_SOURCE = {**{c: "watch-presence-history.jsonl" for c in CONT + ["charging", "motion"]},
                  "home": "sensor-reactions.jsonl", "bedroom_arrivals": "bedroom-arrivals.jsonl",
                  "her_messages": "interaction-ledger.json", "avatar_opens": "avatar-presence-log.json",
                  "in_kitchen": "kitchen-visits.jsonl", "in_bedroom": "bedroom-visits.jsonl",
                  **{c: "house-board-visits.jsonl" for c in ("in_bathroom", "on_sofa", "office_chair", "showers")},
                  "door_her": "doorbell encounters"}


# ---- reading the stores (read-only) -----------------------------------------------------------------------------
def ts(v):
    if v is None or v == "": return None
    if isinstance(v, (int, float)): return float(v)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None: d = d.replace(tzinfo=TZ)        # naive stamps in these stores are her local time
    return d.timestamp()


def _jl(mem, name):
    p = os.path.join(mem, name)
    if not os.path.exists(p): return []
    out = []
    with open(p, "r", errors="ignore") as f:
        for line in f:
            if line.strip():
                try: out.append(json.loads(line))
                except ValueError: continue
    return out


def _json(mem, name, default):
    p = os.path.join(mem, name)
    try:
        with open(p, "r") as f: return json.load(f)
    except (OSError, ValueError):
        return default


def _span(r):
    f, t = ts(r.get("from_ts") or r.get("from")), ts(r.get("to_ts") or r.get("to"))
    if f is None: return None
    return f, max(f, t if t is not None else f)


def build(mem=MEM, door_dir=DOOR_DIR):
    """(events, spans): events (t, channel, value), counts as events with a 0.0 event marking a stream recorded from
    that moment; occupancy channels as (from, to) visit spans. The same reading rules as the offline training."""
    ev, last = [], {}
    for r in _jl(mem, "watch-presence-history.jsonl"):
        t, k, v = ts(r.get("observed_ts") or r.get("observed_at")), r.get("kind"), r.get("value")
        if t is None: continue
        if k == "battery" and isinstance(v, dict):
            k, v = "charging", 1.0 if v.get("state") in ("charging", "full") else 0.0
        elif k == "motion":
            if v not in MOTION: continue
        elif k in CONT:
            try: v = float(v)
            except (TypeError, ValueError): continue
        else:
            continue
        p = last.get(k)                       # the poller repeats its latest sample: same value within 20 min = same reading
        if p and p[1] == v and t - p[0] < 1200: continue
        last[k] = (t, v)
        ev.append((t, k, v))
    for r in _jl(mem, "sensor-reactions.jsonl"):
        if r.get("sensor") == "presence" and isinstance(r.get("value"), bool):
            try: ev.append((float(r["at"]), "home", 1.0 if r["value"] else 0.0))
            except (KeyError, TypeError, ValueError): continue
    for r in _jl(mem, "bedroom-arrivals.jsonl"):
        t = ts(r.get("at"))
        if t: ev.append((t, "bedroom_arrivals", 1.0))
    seen = set()
    led = _json(mem, "interaction-ledger.json", [])
    for r in (led if isinstance(led, list) else led.get("entries", [])):
        t = ts(r.get("timestamp")) if isinstance(r, dict) else None
        if t and r.get("gloria"):
            seen.add(int(t)); ev.append((t, "her_messages", 1.0))
    for r in _jl(mem, "chat-canonical.jsonl"):
        t = ts(r.get("ts"))
        if t and r.get("role") == "user" and not any(abs(int(t) - s) < 5 for s in seen):
            ev.append((t, "her_messages", 1.0))
    av = _json(mem, "avatar-presence-log.json", [])
    for r in (av if isinstance(av, list) else []):
        t = ts(r.get("timestamp")) if isinstance(r, dict) else None
        if t and r.get("event") == "open": ev.append((t, "avatar_opens", 1.0))
    spans = {c: [] for c in OCC}
    for name, ch in (("kitchen-visits.jsonl", "in_kitchen"), ("bedroom-visits.jsonl", "in_bedroom")):
        for r in _jl(mem, name):
            s = _span(r)
            if s: spans[ch].append(s)
    steam_first = None
    for r in _jl(mem, "house-board-visits.jsonl"):
        ch, s = BOARD_OCC.get(r.get("board")), _span(r)
        if not ch or not s: continue
        spans[ch].append(s)
        if r.get("board") == "house-steam":
            steam_first = s[0] if steam_first is None else min(steam_first, s[0])
            if r.get("shower"): ev.append((s[0], "showers", 1.0))
    if steam_first is not None: ev.append((steam_first, "showers", 0.0))
    for p in sorted(glob.glob(os.path.join(door_dir, "*.local.json"))):
        try:
            with open(p, "r") as f: e = json.load(f).get("event") or {}
        except (OSError, ValueError, AttributeError):
            continue
        t = ts(e.get("ts"))
        if t is None: continue
        idn = e.get("identity") or {}
        try: conf = float(idn.get("confidence") or 0)
        except (TypeError, ValueError): conf = 0.0
        her = str(idn.get("name") or "").lower() in DOOR_NAMES and conf >= DOOR_THRESH
        ev.append((t, "door_her", 1.0 if her else 0.0))       # every encounter says the doorbell was watching
    return sorted(ev), spans


def grid(built, now, days=WINDOW_DAYS):
    """The last `days` (from local midnight) up to the bin holding `now`, 5-minute bins. NaN = missing."""
    ev, spans = built
    start = datetime.fromtimestamp(now - days * 86400, TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    t0 = start.timestamp(); n = int((now - t0) // BIN) + 1
    X = np.full((n, len(CH)), np.nan, np.float32)
    acc = {c: {} for c in CH}
    first = {}
    for t, k, v in ev:
        if t > now: continue
        first.setdefault(k, t)
        i = int((t - t0) // BIN)
        if not 0 <= i < n: continue
        if k == "motion": acc["motion"][i] = float(MOTION.index(v))
        elif k in COUNTS: acc[k][i] = acc[k].get(i, 0.0) + v
        elif k in CONT:
            s = acc[k].setdefault(i, [0.0, 0]); s[0] += v; s[1] += 1
        else: acc[k][i] = v
    for j, c in enumerate(CH):
        for i, v in acc[c].items():
            X[i, j] = v[0] / v[1] if isinstance(v, list) else v
    for c in COUNTS:                        # known to be zero wherever it was being recorded
        if c not in first: continue
        j = CH.index(c); a0 = max(0, int((first[c] - t0) // BIN))
        col = X[a0:, j]; col[np.isnan(col)] = 0.0
    for c in OCC:                           # known from its first visit on: 1 where a visit overlaps the bin
        v = [(f, min(t, now)) for f, t in (spans.get(c) or []) if f <= now]
        if not v: continue
        j = CH.index(c); first[c] = min(f for f, _ in v)
        X[max(0, int((first[c] - t0) // BIN)):, j] = 0.0
        for f, t in v:
            a, b = int((f - t0) // BIN), int((t - t0) // BIN) + 1
            if b > 0 and a < n: X[max(0, a):min(n, b), j] = 1.0
    when = [datetime.fromtimestamp(t0 + i * BIN, TZ) for i in range(n)]
    return X, when, t0


def last_seen(built, now):
    """channel -> the raw time of its newest record at or before now (visits: the end of the newest visit)."""
    ev, spans = built
    out = {}
    for t, k, _ in ev:
        if t <= now: out[k] = max(out.get(k, t), t)
    for c, v in spans.items():
        ends = [min(t, now) for f, t in v if f <= now]
        if ends: out[c] = max(ends)
    return out


def features(X, when, mu, sd, off=()):
    m = ~np.isnan(X)
    Xn = np.where(m, (np.nan_to_num(X) - mu) / sd, 0.0)
    gap = np.zeros_like(X)
    lastseen = np.full(X.shape[1], -1e9)
    for i in range(len(X)):
        lastseen = np.where(m[i], i, lastseen)
        gap[i] = np.log1p(np.minimum(i - lastseen, 2016)) / math.log(2017)
    mf = m.astype(np.float32)
    for c in off:
        j = CH.index(c); Xn[:, j] = 0.0; mf[:, j] = 0.0; gap[:, j] = 0.0
    hod = np.array([(w.hour * 60 + w.minute) / 1440 for w in when]); dow = np.array([w.weekday() / 7 for w in when])
    tf = np.stack([np.sin(2 * np.pi * hod), np.cos(2 * np.pi * hod), np.sin(2 * np.pi * dow), np.cos(2 * np.pi * dow)], 1)
    return np.concatenate([Xn, mf, gap, tf], 1).astype(np.float32), m


# ---- the model (the same architecture the weights were trained with) --------------------------------------------
def _model_classes():
    import torch, torch.nn as nn, torch.nn.functional as F

    def chunked_scan(logA, Bu, C, chunk=16):
        b, L, e, s = Bu.shape
        h, ys = torch.zeros(b, e, s), []
        mask = torch.tril(torch.ones(chunk, chunk, dtype=torch.bool))
        for a in range(0, L, chunk):
            la, bu, c = logA[:, a:a + chunk], Bu[:, a:a + chunk], C[:, a:a + chunk]
            n = la.shape[1]
            cum = la.cumsum(1)
            seg = (cum.unsqueeze(2) - cum.unsqueeze(1)).masked_fill(~mask[:n, :n, None, None], float("-inf"))
            hs = (torch.exp(seg) * bu.unsqueeze(1)).sum(2) + torch.exp(cum) * h.unsqueeze(1)
            ys.append((hs * c.unsqueeze(2)).sum(-1))
            h = hs[:, -1]
        return torch.cat(ys, 1)

    class Mamba(nn.Module):
        def __init__(self, d, d_state=16, expand=2, k=4):
            super().__init__()
            e = d * expand
            self.inp, self.conv = nn.Linear(d, 2 * e), nn.Conv1d(e, e, k, groups=e, padding=k - 1)
            self.dt, self.B, self.C = nn.Linear(e, e), nn.Linear(e, d_state), nn.Linear(e, d_state)
            self.A_log = nn.Parameter(torch.log(torch.arange(1, d_state + 1).float()).repeat(e, 1))
            self.D, self.out, self.norm = nn.Parameter(torch.ones(e)), nn.Linear(e, d), nn.LayerNorm(d)

        def forward(self, x):
            b, L, _ = x.shape
            u, z = self.inp(self.norm(x)).chunk(2, -1)
            u = F.silu(self.conv(u.transpose(1, 2))[..., :L].transpose(1, 2))
            dt, Bm, Cm = F.softplus(self.dt(u)), self.B(u), self.C(u)
            logA = dt.unsqueeze(-1) * -torch.exp(self.A_log)
            dBu = dt.unsqueeze(-1) * Bm.unsqueeze(2) * u.unsqueeze(-1)
            return x + self.out((chunked_scan(logA, dBu, Cm) + self.D * u) * F.silu(z))

    class GRU(nn.Module):
        def __init__(self, d):
            super().__init__(); self.g, self.norm = nn.GRU(d, d, batch_first=True), nn.LayerNorm(d)

        def forward(self, x):
            return x + self.g(self.norm(x))[0]

    class World(nn.Module):
        def __init__(self, din, d=64, core="mamba", layers=2):
            super().__init__()
            self.enc = nn.Sequential(nn.Linear(din, d), nn.GELU(), nn.Linear(d, d))
            self.core = nn.ModuleList([(Mamba(d) if core == "mamba" else GRU(d)) for _ in range(layers)])
            self.hz = nn.Embedding(len(H), d)
            self.pred = nn.Sequential(nn.Linear(2 * d, d), nn.GELU(), nn.Linear(d, d))
            self.read = nn.Sequential(nn.Linear(2 * d, d), nn.GELU(),
                                      nn.Linear(d, 2 * len(CONT) + len(BINARY) + len(MOTION) + len(COUNTS)))

        def state(self, x):
            h = self.enc(x)
            for blk in self.core: h = blk(h)
            return h

        def heads(self, h, k):
            e = self.hz.weight[k].expand(*h.shape[:-1], -1)
            hh = torch.cat([h, e], -1)
            return self.pred(hh), self.read(hh)

    return torch, World


def load(path):
    torch, World = _model_classes()
    b = torch.load(path, map_location="cpu", weights_only=True)
    if list(b.get("channels") or []) != CH or dict(b.get("horizons") or {}) != H or int(b.get("bin_seconds", 0)) != BIN:
        raise SystemExit("these weights were trained on other channels or horizons than this reader builds")
    model = World(int(b["din"]), int(b.get("d", 64)), b.get("core", "mamba"), int(b.get("layers", 2)))
    model.load_state_dict(b["state_dict"]); model.eval()
    return torch, model, b


def expectations(out, mu, sd):
    """One horizon's raw readout row -> expectations with their uncertainty, in natural units."""
    nc, nb, nm = len(CONT), len(BINARY), len(MOTION)
    res = {}
    for j, c in enumerate(CONT):
        m_ = float(out[j] * sd[j] + mu[j]); s_ = float(math.exp(0.5 * max(-6.0, min(6.0, float(out[nc + j])))) * sd[j])
        res[c] = {"mean": round(m_, 2), "sd": round(s_, 2), "p10": round(m_ - 1.2816 * s_, 2), "p90": round(m_ + 1.2816 * s_, 2)}
    for i, c in enumerate(BINARY):
        res[c] = {"p": round(1 / (1 + math.exp(-float(out[2 * nc + i]))), 4)}
    lg = np.array(out[2 * nc + nb:2 * nc + nb + nm], dtype=np.float64); pr = np.exp(lg - lg.max()); pr /= pr.sum()
    res["motion"] = {"probs": {k: round(float(p), 4) for k, p in zip(MOTION, pr)},
                     "entropy_bits": round(float(-(pr * np.log2(pr + 1e-12)).sum()), 3)}
    for i, c in enumerate(COUNTS):
        rate = math.exp(min(20.0, float(out[2 * nc + nb + nm + i])))
        res[c] = {"rate_per_bin": round(rate, 5), "p_any_in_bin": round(1 - math.exp(-rate), 4)}
    return res


def _iso(t):
    return datetime.fromtimestamp(t, TZ).isoformat(timespec="seconds") if t is not None else None


def _atomic(path, obj):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".world-model-shadow-", dir=d)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=1); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp): os.unlink(tmp)
        raise


def _append_bounded(path, row, cap):
    """Append one row; past `cap` rows keep the newest `cap`, rewritten atomically. Locked against an overlapping run
    on a lock file of its own (path + LOCK_SUFFIX) that is never replaced, and the history is opened only once that
    lock is held: a lock on the history itself was lost when the rotation replaced it, and a writer waiting on the
    old file appended its row to the detached copy (13 November review)."""
    with open(path + LOCK_SUFFIX, "a") as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        with open(path, "a") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n"); f.flush()
        with open(path, "r") as f: lines = f.readlines()
        if len(lines) > cap:
            fd, tmp = tempfile.mkstemp(prefix=".world-model-shadow-history-", dir=os.path.dirname(path))
            try:
                with os.fdopen(fd, "w") as f: f.writelines(lines[-cap:])
                os.replace(tmp, path)
            except BaseException:
                if os.path.exists(tmp): os.unlink(tmp)
                raise


def run(weights, now=None, mem=MEM, door_dir=DOOR_DIR, history_rows=HISTORY_ROWS):
    now = time.time() if now is None else float(now)
    torch, model, b = load(weights)
    mu, sd = np.array(b["norm_mu"], np.float32), np.array(b["norm_sd"], np.float32)
    off = list(b.get("inputs_off") or [])
    built = build(mem, door_dir)
    X, when, t0 = grid(built, now)
    F_, m = features(X, when, mu, sd, off)
    if F_.shape[1] != int(b["din"]):
        raise SystemExit("feature width %d does not match the weights (%d)" % (F_.shape[1], int(b["din"])))
    with torch.no_grad():
        h = model.state(torch.tensor(F_).unsqueeze(0))
        rows = {name: model.heads(h[:, -1:], ki)[1][0, 0].numpy() for ki, name in enumerate(H)}
    end = t0 + (len(X) - 1) * BIN
    seen = last_seen(built, now)
    day = max(0, len(X) - 288)
    inputs = {}
    for j, c in enumerate(CH):
        src = CHANNEL_SOURCE[c]
        sp = door_dir if c == "door_her" else os.path.join(mem, src)
        inputs[c] = {"last_record": _iso(seen.get(c)),
                     "age_minutes": round((now - seen[c]) / 60, 1) if c in seen else None,
                     "observed_share_24h": round(float(m[day:, j].mean()), 4),
                     "used_as_input": c not in off,
                     "source": src,
                     "source_mtime": _iso(os.path.getmtime(sp)) if os.path.exists(sp) else None}
    expect = {name: {"at": _iso(end + k * BIN), "channels": expectations(rows[name], mu, sd)} for name, k in H.items()}
    with open(weights, "rb") as f: wsha = hashlib.sha256(f.read()).hexdigest()[:16]
    doc = {"schema": 1, "shadow": True, "read_by": "nothing: a shadow run, scored later against what happened",
           "written_at": _iso(now), "grid_end": _iso(end), "bin_seconds": BIN, "window_days": WINDOW_DAYS,
           "model": {"core": b.get("core"), "jepa": b.get("jepa"), "note": b.get("note"), "weights_sha256_16": wsha,
                     "trained_through": _iso(b.get("cutoff"))},
           "expect": expect, "inputs": inputs}
    os.makedirs(mem, exist_ok=True)
    _atomic(os.path.join(mem, OUT_NAME), doc)
    hist = {"written_at": doc["written_at"], "grid_end": doc["grid_end"], "weights": wsha, "expect": {}}
    for name, e in expect.items():
        row = {}
        for c, v in e["channels"].items():
            if "mean" in v: row[c] = [v["mean"], v["sd"]]
            elif "p" in v: row[c] = v["p"]
            elif "probs" in v: row[c] = [v["probs"][k] for k in MOTION]
            else: row[c] = v["rate_per_bin"]
        hist["expect"][name] = row
    hist["fresh_minutes"] = {c: v["age_minutes"] for c, v in inputs.items()}
    _append_bounded(os.path.join(mem, HIST_NAME), hist, history_rows)
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--weights", default=os.environ.get("MAMEPA_WEIGHTS"))
    ap.add_argument("--print", action="store_true", help="also print the document written")
    a = ap.parse_args(argv)
    if not a.weights or not os.path.exists(a.weights):
        print("world_model_shadow: no weights (set MAMEPA_WEIGHTS or --weights); nothing written", file=sys.stderr)
        return 2
    doc = run(a.weights)
    if a.print: print(json.dumps(doc, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
