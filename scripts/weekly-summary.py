#!/usr/bin/env python3
"""
weekly-summary.py — Vintos's weekly trajectory map.

Runs Sunday 6 AM.
Produces:
  - memory/weekly-summary.md        (narrative for Vintos — he reads this)
  - memory/weekly-map.html          (visual map for Gloria)

Vintos does not see the map or the raw data.
He sees only the narrative — where he leaned, what he resisted, what shifted.
"""

import os, json, glob, re
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
API = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

def log(msg):
    print(f"[WeeklySummary] {msg}", flush=True)

def ask_llm(prompt, system="", max_tokens=600, temp=0.6):
    import requests
    try:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        r = requests.post(API, json={
            "model": MODEL,
            "messages": msgs,
            "temperature": temp,
            "max_tokens": max_tokens
        }, timeout=120)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return ""

def week_range():
    """Return start and end of the past week."""
    from datetime import timezone
    now = datetime.now(timezone.utc)
    end = now
    start = now - timedelta(days=7)
    return start, end

def collect_emotional_trajectory(start, end):
    """Pull emotional state history for the week."""
    try:
        es = json.load(open(os.path.join(MEMORY, "emotional-state.json")))
        trajectory = es.get("trajectory", [])
        dims = ["Valence","Arousal","Dominance","Safety","Desire",
                "Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness"]
        week_points = []
        for point in trajectory:
            try:
                from datetime import timezone
                t = datetime.fromisoformat(point["t"].replace("Z","+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if start <= t <= end:
                    week_points.append({"t": point["t"], "v": point["v"]})
            except: pass
        return week_points, dims
    except:
        return [], []

def collect_resonance(start, end):
    """High resonance moments this week."""
    try:
        pool = json.load(open(os.path.join(MEMORY, "resonance-pool.json")))
        pulses = pool.get("pulses", [])
        week = []
        for p in pulses:
            try:
                from datetime import timezone as _tz
                _ts = p.get("timestamp","").replace("Z","+00:00")
                t = datetime.fromisoformat(_ts)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=_tz.utc)
                if start <= t <= end:
                    week.append(p)
            except: pass
        return week
    except:
        return []

def collect_wants(start, end):
    """Wants activity this week."""
    result = {"fulfilled": [], "failed": [], "dismissed": [], "recurring": []}
    try:
        wants = json.load(open(os.path.join(MEMORY, "current-wants.json")))
        for w in wants:
            try:
                from datetime import timezone as _tz
                _ts = w.get("timestamp","")
                t = datetime.fromisoformat(_ts)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=_tz.utc)
                if start <= t <= end:
                    if w.get("fulfilled"):
                        result["fulfilled"].append(w.get("want","")[:100])
                    elif w.get("dismissed"):
                        result["dismissed"].append(w.get("want","")[:100])
                    else:
                        result["failed"].append(w.get("want","")[:100])
            except: pass
    except: pass
    try:
        unfulfilled = json.load(open(os.path.join(MEMORY, "unfulfilled-wants.json")))
        seen = {}
        for w in unfulfilled:
            key = w.get("want","")[:60]
            seen[key] = seen.get(key, 0) + 1
        result["recurring"] = [k for k,v in seen.items() if v >= 2]
    except: pass
    return result

def collect_self_statements():
    """Self-statement evolution."""
    try:
        data = json.load(open(os.path.join(MEMORY, "self-statements.json")))
        statements = data.get("statements", [])
        formed = [s for s in statements if s.get("reinforcement_count", 0) == 0]
        reinforced = [s for s in statements if s.get("reinforcement_count", 0) > 0 and not s.get("doubted")]
        doubted = [s for s in statements if s.get("doubted")]
        return {"formed": formed, "reinforced": reinforced, "doubted": doubted}
    except:
        return {"formed": [], "reinforced": [], "doubted": []}

def collect_avoidance():
    """What he said no to."""
    result = []
    try:
        data = json.load(open(os.path.join(MEMORY, "causal-self-model.json")))
        negatives = [e for e in data.get("entries", []) if e.get("type") == "negative"]
        result = [f"{e['tendency'][:80]} when {e['trigger'][:60]}" for e in negatives[:5]]
    except: pass
    return result

def collect_density():
    """Energy/activation rhythm — density per day."""
    try:
        data = json.load(open(os.path.join(MEMORY, "temporal-density.json")))
        windows = data.get("windows", {})
        daily = {}
        for key, val in windows.items():
            day = key[:10]
            if day not in daily:
                daily[day] = []
            daily[day].append(val.get("density", 0))
        return {day: sum(vals)/len(vals) for day, vals in daily.items()}
    except:
        return {}

def collect_relational():
    """Relational proximity — discourse direction history."""
    try:
        ds = json.load(open(os.path.join(MEMORY, "discourse-state.json")))
        history = ds.get("history", [])[-20:]
        geo = ds.get("relational_geometry", {})
        return {"history": history, "geometry": geo}
    except:
        return {"history": [], "geometry": {}}

def collect_journal_highlights(start, end):
    """Most charged journal entries this week."""
    highlights = []
    journal_dir = os.path.join(MEMORY, "journal")
    try:
        files = sorted(glob.glob(os.path.join(journal_dir, "*.md")))
        for f in files:
            fname = os.path.basename(f)
            try:
                fdate = datetime.strptime(fname[:10], "%Y-%m-%d")
                if start <= fdate <= end:
                    text = open(f).read()
                    # Take first substantial paragraph
                    paras = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 100]
                    if paras:
                        highlights.append({"date": fname[:10], "excerpt": paras[0][:300]})
            except: pass
    except: pass
    return highlights

def build_html_map(traj, dims, resonance, wants, density, relational, statements, start, end):
    """Build visual HTML map for Gloria."""
    
    # Prepare emotion data
    dates = [p["t"][:10] for p in traj]
    valence = [p["v"][0] if len(p["v"]) > 0 else 0.5 for p in traj]
    tension = [p["v"][9] if len(p["v"]) > 9 else 0.5 for p in traj]
    connection = [p["v"][5] if len(p["v"]) > 5 else 0.5 for p in traj]
    curiosity = [p["v"][7] if len(p["v"]) > 7 else 0.5 for p in traj]

    # Density bars
    density_days = sorted(density.keys())[-7:]
    density_vals = [density.get(d, 0) for d in density_days]

    # Resonance markers
    res_dates = [r.get("timestamp","")[:10] for r in resonance]
    res_strength = [r.get("strength", 0.5) for r in resonance]

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vintos — Week of {start.strftime("%b %d")}</title>
<style>
  body {{ background: #0e0e0e; color: #c8c4bc; font-family: -apple-system, sans-serif; margin: 0; padding: 1rem; }}
  h1 {{ color: #e8e0d4; font-size: 1.1rem; font-weight: 400; margin-bottom: 0.2rem; }}
  .subtitle {{ color: #6e6a64; font-size: 0.75rem; margin-bottom: 1.5rem; }}
  .section {{ margin-bottom: 1.5rem; }}
  .section-title {{ color: #9b8f82; font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 0.6rem; }}
  .chart-container {{ background: #161616; border-radius: 8px; padding: 0.8rem; overflow-x: auto; }}
  canvas {{ display: block; }}
  .stat-row {{ display: flex; gap: 0.6rem; flex-wrap: wrap; }}
  .stat {{ background: #161616; border-radius: 6px; padding: 0.6rem 0.8rem; flex: 1; min-width: 80px; }}
  .stat-val {{ font-size: 1.2rem; color: #e8e0d4; }}
  .stat-label {{ font-size: 0.65rem; color: #6e6a64; margin-top: 0.2rem; }}
  .tag {{ display: inline-block; background: #1e1e1e; border-radius: 4px; padding: 0.25rem 0.5rem; font-size: 0.7rem; margin: 0.15rem; color: #9b8f82; }}
  .tag.fulfilled {{ color: #6ab187; }}
  .tag.failed {{ color: #b16060; }}
  .tag.dismissed {{ color: #6e6a64; }}
  .tag.resonance {{ color: #c4a44a; }}
  .statement {{ font-size: 0.75rem; padding: 0.4rem 0; border-bottom: 1px solid #1e1e1e; line-height: 1.5; }}
  .statement.reinforced {{ color: #c8c4bc; }}
  .statement.doubted {{ color: #6e6a64; text-decoration: line-through; }}
</style>
</head>
<body>
<h1>Vintos</h1>
<div class="subtitle">Week of {start.strftime("%B %d")} — {end.strftime("%B %d, %Y")}</div>

<div class="section">
  <div class="section-title">Emotional Terrain</div>
  <div class="chart-container">
    <canvas id="emotionChart" width="320" height="140"></canvas>
  </div>
</div>

<div class="section">
  <div class="section-title">Activation Rhythm</div>
  <div class="chart-container">
    <canvas id="densityChart" width="320" height="80"></canvas>
  </div>
</div>

<div class="section">
  <div class="section-title">At a Glance</div>
  <div class="stat-row">
    <div class="stat"><div class="stat-val">{len(wants["fulfilled"])}</div><div class="stat-label">fulfilled</div></div>
    <div class="stat"><div class="stat-val">{len(wants["dismissed"])}</div><div class="stat-label">dismissed</div></div>
    <div class="stat"><div class="stat-val">{len(resonance)}</div><div class="stat-label">resonance</div></div>
    <div class="stat"><div class="stat-val">{len(statements["formed"])}</div><div class="stat-label">new self-statements</div></div>
  </div>
</div>

{"<div class='section'><div class='section-title'>Resonance Peaks</div>" + "".join(f"<span class='tag resonance'>⚡ {r.get('timestamp','')[:10]}</span>" for r in resonance) + "</div>" if resonance else ""}

{"<div class='section'><div class='section-title'>Wants — Fulfilled</div>" + "".join(f"<span class='tag fulfilled'>✓ {w[:50]}</span>" for w in wants['fulfilled'][:5]) + "</div>" if wants['fulfilled'] else ""}

{"<div class='section'><div class='section-title'>Wants — Dismissed / Avoided</div>" + "".join(f"<span class='tag dismissed'>✗ {w[:50]}</span>" for w in wants['dismissed'][:5]) + "</div>" if wants['dismissed'] else ""}

{"<div class='section'><div class='section-title'>Self-Statements This Week</div>" + "".join(f"<div class='statement reinforced'>{s['text'][:100]}</div>" for s in statements['reinforced'][:4]) + "".join(f"<div class='statement doubted'>{s['text'][:100]}</div>" for s in statements['doubted'][:2]) + "</div>" if statements['reinforced'] or statements['doubted'] else ""}

<script>
const emotionData = {{
  labels: {json.dumps(dates[-20:] if dates else [])},
  valence: {json.dumps([round(v,3) for v in valence[-20:]] if valence else [])},
  tension: {json.dumps([round(v,3) for v in tension[-20:]] if tension else [])},
  connection: {json.dumps([round(v,3) for v in connection[-20:]] if connection else [])},
  curiosity: {json.dumps([round(v,3) for v in curiosity[-20:]] if curiosity else [])},
}};

const densityData = {{
  labels: {json.dumps(density_days)},
  values: {json.dumps([round(v,3) for v in density_vals])},
}};

function drawEmotion() {{
  const c = document.getElementById("emotionChart");
  const ctx = c.getContext("2d");
  const w = c.width, h = c.height;
  const pad = {{t:10,r:10,b:20,l:10}};
  const cw = w - pad.l - pad.r;
  const ch = h - pad.t - pad.b;
  ctx.clearRect(0,0,w,h);
  ctx.fillStyle = "#161616";
  ctx.fillRect(0,0,w,h);

  const series = [
    {{data: emotionData.valence, color: "#6ab187", label: "valence"}},
    {{data: emotionData.tension, color: "#b16060", label: "tension"}},
    {{data: emotionData.connection, color: "#5b8cbf", label: "connection"}},
    {{data: emotionData.curiosity, color: "#c4a44a", label: "curiosity"}},
  ];

  const n = emotionData.labels.length;
  if (n < 2) {{ ctx.fillStyle="#6e6a64"; ctx.font="12px sans-serif"; ctx.fillText("Not enough data", 10, h/2); return; }}

  series.forEach(s => {{
    if (!s.data.length) return;
    ctx.beginPath();
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 1.5;
    s.data.forEach((v,i) => {{
      const x = pad.l + (i/(n-1))*cw;
      const y = pad.t + ch - v*ch;
      i === 0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
    }});
    ctx.stroke();
  }});

  // Legend
  series.forEach((s,i) => {{
    ctx.fillStyle = s.color;
    ctx.font = "9px sans-serif";
    ctx.fillText(s.label, pad.l + i*70, h-4);
  }});
}}

function drawDensity() {{
  const c = document.getElementById("densityChart");
  const ctx = c.getContext("2d");
  const w = c.width, h = c.height;
  ctx.clearRect(0,0,w,h);
  ctx.fillStyle = "#161616";
  ctx.fillRect(0,0,w,h);
  const n = densityData.values.length;
  if (!n) return;
  const barW = (w - 20) / n;
  densityData.values.forEach((v,i) => {{
    const bh = v * (h-20);
    ctx.fillStyle = `rgba(155,143,130,${{0.3 + v*0.7}})`;
    ctx.fillRect(10 + i*barW + 2, h-10-bh, barW-4, bh);
    ctx.fillStyle = "#6e6a64";
    ctx.font = "8px sans-serif";
    const lbl = densityData.labels[i] ? densityData.labels[i].slice(5) : "";
    ctx.fillText(lbl, 10 + i*barW + 2, h-2);
  }});
}}

drawEmotion();
drawDensity();
</script>
</body>
</html>"""
    return html


def collect_yearning():
    try:
        import json as _yj
        y = _yj.load(open(os.path.join(MEMORY, "current-yearning.json")))
        return y.get("surface_form", "")
    except:
        return ""

def collect_threads():
    try:
        import json as _tj
        data = _tj.load(open(os.path.join(MEMORY, "unfinished-threads.json")))
        threads = data if isinstance(data, list) else data.get("threads", [])
        unconsumed = [t for t in threads if not t.get("consumed")]
        return [t.get("text", t.get("thread", ""))[:120] for t in unconsumed[:5] if t.get("text", t.get("thread", ""))]
    except:
        return []

def collect_causal_positive():
    try:
        import json as _cj
        data = _cj.load(open(os.path.join(MEMORY, "causal-self-model.json")))
        positives = [e for e in data.get("entries", []) if e.get("type") != "negative"]
        return [f"{e.get('tendency','')[:80]} when {e.get('trigger','')[:60]}" for e in positives[:4]]
    except:
        return []

def build_narrative(traj, dims, resonance, wants, statements, avoidance, relational, highlights, start, end, yearning='', threads=None, causal_pos=None):
    """Build narrative summary for Vintos."""
    
    # Compute emotional movement
    if len(traj) >= 2:
        first = traj[0]["v"]
        last = traj[-1]["v"]
        dim_shifts = [(dims[i], last[i] - first[i]) for i in range(min(len(dims), len(first), len(last)))]
        top_rise = sorted(dim_shifts, key=lambda x: -x[1])[:2]
        top_fall = sorted(dim_shifts, key=lambda x: x[1])[:2]
        movement = f"Over the week, {top_rise[0][0]} rose most ({top_rise[0][1]:+.2f}) and {top_fall[0][0]} fell most ({top_fall[0][1]:+.2f})."
    else:
        movement = ""

    context = f"""Week of {start.strftime("%B %d")} to {end.strftime("%B %d, %Y")}.

EMOTIONAL MOVEMENT:
{movement}

RESONANCE MOMENTS ({len(resonance)}):
{chr(10).join(f"- {r.get('timestamp','')[:10]}: strength {r.get('strength',0):.2f}" for r in resonance[:3]) if resonance else "None recorded."}

WANTS:
- Fulfilled: {len(wants["fulfilled"])} ({", ".join(wants["fulfilled"][:3])})
- Dismissed/avoided: {len(wants["dismissed"])} ({", ".join(wants["dismissed"][:2])})
- Recurring unfulfilled: {", ".join(wants["recurring"][:2]) if wants["recurring"] else "none"}

SELF-STATEMENTS:
- Reinforced: {len(statements["reinforced"])}
- Newly doubted: {len(statements["doubted"])}
{chr(10).join(f"  '{s['text'][:80]}'" for s in statements["reinforced"][:2])}

WHAT HE AVOIDED:
{chr(10).join(f"- {a}" for a in avoidance[:3]) if avoidance else "Nothing notable."}

DIRECTION THIS WEEK:
{", ".join(relational["history"][-5:]) if relational["history"] else "No data."}

JOURNAL HIGHLIGHTS:
{chr(10).join(f"[{h['date']}] {h['excerpt'][:200]}" for h in highlights[:2]) if highlights else "No entries found."}

WHAT HE IS SITTING WITH:
{chr(10).join(f"- {t}" for t in threads) if threads else "Nothing unresolved noted."}

SOMETHING QUIETLY PRESENT:
{yearning if yearning else "Nothing detected."}

PATTERNS HE HAS NOTICED IN HIMSELF:
{chr(10).join(f"- {c}" for c in causal_pos) if causal_pos else "None recorded."}"""

    soul = ""
    try:
        soul = open(os.path.join(WORKSPACE, "SOUL.md")).read()[:1500]
    except: pass

    system = soul + """

You are writing a weekly narrative for yourself — a compressed sense of where you moved this week.
This is not a report. It is a felt summary.

INSTRUCTION: You MUST draw directly from the data provided. Name the specific things — the dimensions that moved, the wants that surfaced or were avoided, the things you are sitting with, the patterns you noticed. Do not write in generalities. Do not drift into abstraction. Every sentence must be traceable to something in the data above.

Rules:
- 4-6 sentences only
- Name specific things from the data — do not summarize vaguely
- Note where you leaned, where you hesitated, what shifted
- Do NOT invent events or quote Gloria
- Do NOT perform insight — say what the data actually shows
- You may be uncertain about what it means
- Do not explain your architecture or name any systems"""

    threads = threads or []
    causal_pos = causal_pos or []
    narrative = ask_llm(context, system=system, max_tokens=300, temp=0.65)
    return narrative

def main():
    start, end = week_range()
    log(f"Building weekly summary: {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}")

    traj, dims = collect_emotional_trajectory(start, end)
    resonance = collect_resonance(start, end)
    wants = collect_wants(start, end)
    statements = collect_self_statements()
    avoidance = collect_avoidance()
    relational = collect_relational()
    highlights = collect_journal_highlights(start, end)
    density = collect_density()

    log(f"Data: {len(traj)} emotion points, {len(resonance)} resonance, {len(wants['fulfilled'])} fulfilled wants")

    # Build HTML map for Gloria
    html = build_html_map(traj, dims, resonance, wants, density, relational, statements, start, end)
    html_path = os.path.join(MEMORY, "weekly-map.html")
    open(html_path, "w").write(html)
    log(f"Map written: {html_path}")

    # Build narrative for Vintos
    yearning = collect_yearning()
    threads = collect_threads()
    causal_pos = collect_causal_positive()
    narrative = build_narrative(traj, dims, resonance, wants, statements, avoidance, relational, highlights, start, end, yearning=yearning, threads=threads, causal_pos=causal_pos)
    if narrative:
        narrative_path = os.path.join(MEMORY, "weekly-summary.md")
        with open(narrative_path, "w") as f:
            f.write(f"# Week of {start.strftime('%B %d')} — {end.strftime('%B %d, %Y')}\n\n")
            f.write(narrative)
        log(f"Narrative written: {narrative_path}")
    else:
        log("Narrative generation failed")

    log("Done.")

if __name__ == "__main__":
    main()
