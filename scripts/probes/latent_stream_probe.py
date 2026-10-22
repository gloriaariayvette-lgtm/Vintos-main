#!/usr/bin/env python3
"""Read-only: step 0 of the continuous latent stream (docs/continuous-latent-stream.md). Writes nothing.

What it prints, so the recurrent state is sized to his real stream and not to a guess:
  1. each source the stream would read: present or not, rows, first and last time, and events per day over the
     last 30 days (median and busiest day)
  2. the embedding stores: which model and width each row says it is
  3. the schedules that already run the latent organs (crontab lines), and whether their outputs are fresh
  4. the machine: CPU cores, memory, a GPU or not, the torch venv
    python3 ~/Vintos-main/scripts/probes/latent_stream_probe.py
"""
import glob, json, os, re, shutil, statistics, subprocess, time
from collections import Counter
from datetime import datetime, timedelta, timezone

WS = os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
NOW = datetime.now(timezone.utc)
SINCE = NOW - timedelta(days=30)
TS_KEYS = ("timestamp", "ts", "t", "at", "time", "created_at", "date", "read_at")


def when(v):
    if isinstance(v, (int, float)):
        try: return datetime.fromtimestamp(v / 1000 if v > 1e12 else v, timezone.utc)
        except (OverflowError, OSError, ValueError): return None
    if isinstance(v, str) and re.match(r"\d{4}-\d\d-\d\d", v):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00")[:32])
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def stamp(row):
    if isinstance(row, dict):
        for k in TS_KEYS:
            d = when(row.get(k))
            if d: return d
    return None


def rows_of(path):
    """A JSON list, a JSON object holding one list, or JSON lines. Large files: the last 200,000 lines."""
    if path.endswith(".jsonl"):
        out = []
        with open(path, errors="ignore") as f:
            lines = f.readlines()[-200000:]
        for line in lines:
            try: out.append(json.loads(line))
            except ValueError: pass
        return out
    d = json.load(open(path))
    if isinstance(d, list): return d
    if isinstance(d, dict):
        lists = [v for v in d.values() if isinstance(v, list)]
        return max(lists, key=len) if lists else [d]
    return []


def per_day(stamps):
    days = Counter(s.date() for s in stamps if s >= SINCE)
    if not days: return "none in the last 30 days"
    counts = [days.get((SINCE + timedelta(days=i)).date(), 0) for i in range(31)]
    return "last 30 days: %d events, median %d a day, busiest %d" % (sum(counts), statistics.median(counts), max(counts))


def source(name, path):
    if not os.path.exists(path):
        print("  %-26s MISSING (%s)" % (name, path)); return
    try:
        rows = rows_of(path)
    except Exception as e:
        print("  %-26s unreadable: %s" % (name, str(e)[:80])); return
    st = [s for s in (stamp(r) for r in rows) if s]
    span = ("%s .. %s" % (min(st).date(), max(st).date())) if st else "no timestamps found"
    keys = sorted(rows[-1].keys())[:8] if rows and isinstance(rows[-1], dict) else []
    print("  %-26s %d rows, %s; %s\n  %-26s fields: %s" % (name, len(rows), span, per_day(st), "", ", ".join(keys)))


def markdown_days(name, pattern):
    files = sorted(glob.glob(os.path.join(MEM, pattern)))
    recent = [f for f in files if re.search(r"(\d{4}-\d\d-\d\d)", f) and
              when(re.search(r"(\d{4}-\d\d-\d\d)", f).group(1)) and when(re.search(r"(\d{4}-\d\d-\d\d)", f).group(1)) >= SINCE]
    sections = [len(re.findall(r"^## ", open(f, errors="ignore").read(), re.M)) for f in recent]
    print("  %-26s %d files, %d in 30 days; sections a day: median %s, most %s" % (
        name, len(files), len(recent), statistics.median(sections) if sections else 0, max(sections) if sections else 0))


print("== 1. what the stream would read ==")
source("chat (canonical)", os.path.join(MEM, "chat-canonical.jsonl"))
source("chat (merged)", os.path.join(MEM, "chat-history-merged.json"))
source("interaction ledger", os.path.join(MEM, "interaction-ledger.json"))
source("emotion, dense", os.path.join(MEM, "emotion-trajectory-dense.json"))
source("unfinished threads", os.path.join(MEM, "unfinished-threads.json"))
source("wants", os.path.join(MEM, "current-wants.json"))
source("lab notebook", os.path.join(MEM, "chemistry-lab", "notebook.jsonl"))
source("watch / presence", next((p for p in glob.glob(os.path.join(MEM, "*watch*.json*")) + glob.glob(os.path.join(MEM, "*presence*.json*"))), os.path.join(MEM, "watch-presence.jsonl")))
source("media embeddings", os.path.join(MEM, "media-embeddings.jsonl"))
markdown_days("inner life", "daily-inner-life-*.md")
markdown_days("journal", "journal-*.md")
markdown_days("creative", "daily-creative-*.md")

print("\n== 2. embedding stores ==")
for name in ("embeddings.jsonl", "media-embeddings.jsonl"):
    p = os.path.join(MEM, name)
    if not os.path.exists(p):
        print("  %-26s MISSING" % name); continue
    models, widths, n = Counter(), Counter(), 0
    with open(p, errors="ignore") as f:
        for line in f:
            n += 1
            if n > 5000: break
            try: r = json.loads(line)
            except ValueError: continue
            models[str(r.get("model") or r.get("embed_model") or "(not named)")] += 1
            v = r.get("vec") or r.get("embedding") or r.get("vector")
            if isinstance(v, list): widths[len(v)] += 1
    print("  %-26s %.1f MB; first %d rows: models %s; widths %s" % (name, os.path.getsize(p) / 1e6, min(n, 5000), dict(models), dict(widths)))
idx = glob.glob(os.path.join(MEM, "jepa-self-emb", "*.idx.jsonl"))
print("  %-26s %s" % ("jepa self-head cache", ("%d index files" % len(idx)) if idx else "MISSING"))
for ck in ("jepa-predictor.pt", "jepa-self-head.npz", "lam.pt"):
    p = os.path.join(MEM, ck)
    print("  %-26s %s" % (ck, ("present, %s" % time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(p)))) if os.path.exists(p) else "MISSING"))

print("\n== 3. schedules and freshness ==")
try:
    cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10).stdout
except Exception:
    cron = ""
for organ in ("jepa_predictor", "jepa_self_head", "emotion_densifier", "living_trajectory", "lam.py", "drift_head",
              "relational_head", "media_embed", "emoclaw"):
    lines = [l.strip() for l in cron.splitlines() if organ in l and not l.strip().startswith("#")]
    print("  %-20s %s" % (organ, ("; ".join(re.sub(r"\s+", " ", l)[:110] for l in lines[:2])) if lines else "no crontab line"))
for out in ("jepa-prediction.json", "lam-forecast.json", "living-trajectory.json", "emotion-trajectory-dense.json"):
    p = os.path.join(MEM, out)
    print("  %-30s %s" % (out, ("written %.0f min ago" % ((time.time() - os.path.getmtime(p)) / 60)) if os.path.exists(p) else "MISSING"))

print("\n== 4. the machine ==")
print("  cpu cores:", os.cpu_count())
try:
    mem = dict(l.split(":", 1) for l in open("/proc/meminfo").read().splitlines() if ":" in l)
    print("  memory: %s total, %s available" % (mem.get("MemTotal", "?").strip(), mem.get("MemAvailable", "?").strip()))
except OSError:
    pass
if shutil.which("nvidia-smi"):
    g = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader"], capture_output=True, text=True, timeout=20)
    print("  gpu:", g.stdout.strip() or g.stderr.strip()[:120])
else:
    print("  gpu: none (no nvidia-smi)")
venv = os.path.join(WS, "emotion_model", ".venv", "bin", "python3")
if os.path.exists(venv):
    v = subprocess.run([venv, "-c", "import torch; print(torch.__version__, 'cuda' if torch.cuda.is_available() else 'cpu')"],
                       capture_output=True, text=True, timeout=120)
    print("  torch venv:", (v.stdout.strip() or v.stderr.strip()[-120:]))
else:
    print("  torch venv: MISSING")
