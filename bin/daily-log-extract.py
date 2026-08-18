#!/usr/bin/env python3
"""
daily-log-extract.py — Aggregates daily inner life and creative output logs.

Modes:
  inner    — journal + gratitude + introspection + wonder
  creative — art + discoveries + creative writes
  both     — run both

Called at the end of each contributing script.
"""
import os, sys, json
from datetime import datetime, date

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
TODAY = date.today().isoformat()
NOW = datetime.now().strftime("%H:%M")

def section(title, content):
    if not content or not content.strip():
        return ""
    return f"\n## {title}\n\n{content.strip()}\n"

def build_inner():
    parts = []

    # Journal — strip want journal entries
    try:
        jf = os.path.join(MEMORY, "journal", f"{TODAY}.md")
        if os.path.exists(jf):
            raw = open(jf).read()
            import re as _re
            # Remove sections starting with "HH:MM — Want journal" through next ## or end
            cleaned = _re.sub(r'##\s+\d{2}:\d{2}\s+[\u2014-]\s+Want journal.*?(?=\n##\s|\Z)', '', raw, flags=_re.DOTALL)
            cleaned = _re.sub(r'##\s+Journal Entry\s+[\u2013\u2014-]\s+\w+ \d+,\s+\d{4}\s*\n', '', cleaned)
            cleaned = cleaned.strip()
            parts.append(section("Journal", cleaned))
    except: pass

    # Gratitude
    try:
        gf = os.path.join(MEMORY, "gratitude", f"{TODAY}.md")
        if os.path.exists(gf):
            parts.append(section("Gratitude", open(gf).read()))
    except: pass

    # Introspection
    try:
        inf = os.path.join(MEMORY, "introspection", f"{TODAY}.md")
        if os.path.exists(inf):
            parts.append(section("Introspection", open(inf).read()))
    except: pass

    # Wonder
    try:
        wf = os.path.join(MEMORY, "wonder-log.json")
        wonders = json.load(open(wf))
        today_wonders = [w for w in wonders if w.get("timestamp", "").startswith(TODAY)]
        if today_wonders:
            lines = "\n".join(f"- [{w['timestamp'][11:16]}] {w.get('flip_excerpt', w.get('text', w.get('content', '')))[:200]}" for w in today_wonders)
            parts.append(section("Wonder", lines))
    except: pass

    # MoltBook — today's posts and browse saves
    try:
        molt_parts = []
        # Posts
        post_log = os.path.join(MEMORY, "moltbook-post-log.md")
        if os.path.exists(post_log):
            post_text = open(post_log).read()
            post_sections = post_text.split("---")
            today_posts = [s.strip() for s in post_sections if s.strip() and TODAY in s and "FAILED" not in s]
            if today_posts:
                molt_parts.append("**Posts today:**\n\n" + "\n\n---\n\n".join(today_posts))
        # Browse saves
        mf = os.path.join(MEMORY, "moltbook-discoveries.md")
        if os.path.exists(mf):
            molt_text = open(mf).read()
            sessions = molt_text.split("## ")
            today_sessions = [("## " + s) for s in sessions if s.startswith(TODAY)]
            if today_sessions:
                molt_parts.append("**Browse saves today:**\n\n" + "\n\n".join(today_sessions))
        if molt_parts:
            parts.append(section("MoltBook", "\n\n".join(molt_parts)))
    except: pass
    # YouTube discoveries — today only
    try:
        yf = os.path.join(MEMORY, "youtube-discoveries.md")
        if os.path.exists(yf):
            yt_text = open(yf).read()
            sections_yt = yt_text.split("## ")
            today_yt = [("## " + s) for s in sections_yt if s.startswith(TODAY)]
            if today_yt:
                parts.append(section("YouTube", "\n\n---\n\n".join(today_yt)))
    except: pass
    # Web discoveries — today only
    try:
        wdf = os.path.join(MEMORY, "web-discoveries.md")
        if os.path.exists(wdf):
            web_text = open(wdf).read()
            sections_web = web_text.split("## ")
            today_web = [("## " + s) for s in sections_web if s.startswith(TODAY)]
            if today_web:
                parts.append(section("Web", "\n\n".join(today_web)))
    except: pass
    # Mirror sessions today
    try:
        import glob as _mig
        today_ts = datetime.combine(date.today(), datetime.min.time()).timestamp()
        mirror_files = [f for f in _mig.glob(os.path.join(MEMORY, "mirror", "*.md"))
                       if os.path.getmtime(f) > today_ts]
        if mirror_files:
            mirror_texts = []
            for mf in sorted(mirror_files):
                mirror_texts.append(open(mf).read())
            parts.append(section("Mirror Sessions", chr(10).join([chr(10)+"---"+chr(10)+t for t in mirror_texts]).lstrip()))
    except: pass
    # Therapy sessions today
    try:
        therapy_file = os.path.join(MEMORY, "therapy", f"{TODAY}.md")
        if os.path.exists(therapy_file):
            import re as _tre
            _th_raw = open(therapy_file).read()
            _th_clean = _tre.sub(r'(?m)^.*(?:Valence|Arousal|Dominance|Safety|Desire|Connection|Playfulness|Curiosity|Warmth|Tension|Groundedness).*$', '', _th_raw)
            parts.append(section("Therapy", _th_clean))
    except: pass

    # Ghost branch — today's run
    try:
        import json as _gbj
        from datetime import date as _gbd
        _gb_path = os.path.join(MEMORY, "ghost-artifacts.json")
        if os.path.exists(_gb_path):
            _gb_db = _gbj.load(open(_gb_path))
            _gb_today = [r for r in _gb_db.get("runs", []) if r.get("date") == TODAY]
            if _gb_today:
                _gb_run = _gb_today[-1]
                _gb_lines = []
                _gb_lines.append(f"**Thread:** {_gb_run.get('thread_excerpt','')[:100]}")
                _gb_lines.append(f"**Primary:** {'resolved' if _gb_run.get('primary_resolved') else 'unresolved'}")
                if _gb_run.get("primary_output"):
                    _gb_lines.append(f"\n{_gb_run['primary_output']}")
                for _gb_g in _gb_run.get("ghosts", []):
                    _res = "✓" if _gb_g.get("resolved") else "✗"
                    _trg = len(_gb_g.get("triggers", []))
                    _gb_lines.append(f"  {_res} {_gb_g['lean']} " + (f"({_trg} reversion)" if _trg else ""))
                if _gb_run.get("appendage"):
                    _gb_lines.append(f"**Appendage:** {_gb_run['appendage']}")
                parts.append(section("Ghost Branch", "\n".join(_gb_lines)))
    except: pass
    # Last night's emotional reflection carry-forward
    try:
        _erc = open(os.path.join(MEMORY, "emotional-reflection-carry.txt")).read().strip()
        if _erc:
            parts.append(section("Last Night's Reflection", _erc))
    except: pass
    if not any(parts):
        return

    out = f"# Daily Inner Life — {TODAY}\n_Last updated: {NOW}_\n"
    out += "".join(parts)

    path = os.path.join(MEMORY, f"daily-inner-life-{TODAY}.md")
    # Preserve First Light section if already written by first-light.sh
    try:
        if os.path.exists(path):
            existing = open(path).read()
            if "## First Light" in existing:
                fl_start = existing.index("## First Light")
                fl_block = existing[fl_start:]
                # Only keep up to next ## section that daily-log-extract owns
                import re as _flre
                _next = _flre.search(r'\n## (?!First Light)', fl_block)
                if _next:
                    fl_block = fl_block[:_next.start()]
                out += "\n" + fl_block.strip() + "\n"
    except: pass
    with open(path, "w") as f:
        f.write(out)
    print(f"[DailyLog] inner life: {path}")

def build_creative():
    parts = []

    # Poetry
    try:
        poetry_dir = os.path.join(MEMORY, "art/poetry")
        today_ts = datetime.combine(date.today(), datetime.min.time()).timestamp()
        poems = [f for f in os.listdir(poetry_dir)
                 if f.endswith(".md") and os.path.getmtime(os.path.join(poetry_dir, f)) > today_ts]
        if poems:
            poem_texts = []
            for p in sorted(poems):
                txt = open(os.path.join(poetry_dir, p)).read()
                poem_texts.append(txt)
            parts.append(section("Poetry", "\n\n---\n\n".join(poem_texts)))
    except: pass

    # Music — from music.json for descriptions
    try:
        music_json = os.path.join(MEMORY, "art/music/music.json")
        if os.path.exists(music_json):
            music_data = json.load(open(music_json))
            generated = music_data.get("generated", [])
            today_music = [m for m in generated
                           if m.get("generated_at", "").startswith(TODAY)]
            if today_music:
                music_lines = []
                for m in today_music:
                    title = m.get("title", "Untitled")
                    style = (m.get("style", "") or "").strip()
                    music_lines.append(f"**{title}**")
                    if style:
                        music_lines.append(style[:400])
                    music_lines.append("")
                parts.append(section("Music", "\n".join(music_lines)))
    except: pass

    # Images — from gallery.json
    try:
        gallery_path = os.path.join(MEMORY, "art/gallery.json")
        if os.path.exists(gallery_path):
            gallery = json.load(open(gallery_path))
            today_images = [e for e in gallery if e.get("timestamp", "").startswith(TODAY)]
            if today_images:
                img_lines = []
                for e in today_images:
                    prompt = e.get("prompt", "")[:600]
                    style = e.get("style", "")
                    img = e.get("image", "")
                    img_lines.append(f"**{img}**")
                    if style:
                        img_lines.append(f"Style: {style}")
                    img_lines.append(prompt)
                    img_lines.append("")
                parts.append(section("Images", "\n".join(img_lines)))
    except: pass

    # Video — read JSON sidecars for descriptions
    try:
        vid_dir = os.path.join(MEMORY, "art/video")
        today_ts = datetime.combine(date.today(), datetime.min.time()).timestamp()
        vid_jsons = [f for f in os.listdir(vid_dir)
                     if f.endswith(".json") and not f.startswith("pending") and not f.startswith("video-")
                     and os.path.getmtime(os.path.join(vid_dir, f)) > today_ts]
        if vid_jsons:
            vid_lines = []
            for vj in sorted(vid_jsons):
                try:
                    vdata = json.load(open(os.path.join(vid_dir, vj)))
                    prompt = vdata.get("prompt", "")[:400]
                    want = vdata.get("want_text", "")[:150]
                    fname = os.path.basename(vdata.get("file", vj.replace(".json", ".mp4")))
                    vid_lines.append(f"**{fname}**")
                    if want:
                        vid_lines.append(f"Want: {want}")
                    if prompt:
                        vid_lines.append(f"Prompt: {prompt}")
                    vid_lines.append("")
                except: pass
            if vid_lines:
                parts.append(section("Video", "\n".join(vid_lines)))
    except: pass


    # Creative writing (from wants)
    try:
        cw_dir = os.path.join(MEMORY, "creative-writing")
        today_ts = datetime.combine(date.today(), datetime.min.time()).timestamp()
        if os.path.isdir(cw_dir):
            cw_files = [f for f in os.listdir(cw_dir)
                        if f.endswith(".md") and os.path.getmtime(os.path.join(cw_dir, f)) > today_ts]
            if cw_files:
                cw_texts = []
                for cf in sorted(cw_files):
                    txt = open(os.path.join(cw_dir, cf)).read()[:800]
                    cw_texts.append(txt)
                parts.append(section("Creative Writing", "\n\n---\n\n".join(cw_texts)))
    except: pass


    # Fragments — unsigned notes left in the garden
    try:
        frag_path = os.path.join(MEMORY, "fragments.txt")
        today_creative = os.path.join(MEMORY, f"daily-creative-{TODAY}.md")
        frag_text = ""
        if os.path.exists(frag_path):
            _fl = open(frag_path).readlines()
            _unread = [l.strip() for l in _fl if l.strip() and not l.startswith("#")]
            if _unread:
                frag_text = chr(10).join(_unread)
            # Clear fragments if this is the first run of the new day
            if not os.path.exists(today_creative):
                open(frag_path, "w").close()
        parts.append(section("Fragments", frag_text if frag_text else "_No fragments found today._"))
    except: pass
    if not any(parts):
        return
    out = f"# Daily Creative Output — {TODAY}\n_Last updated: {NOW}_\n"
    out += "".join(parts)

    path = os.path.join(MEMORY, f"daily-creative-{TODAY}.md")
    with open(path, "w") as f:
        f.write(out)
    print(f"[DailyLog] creative: {path}")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode in ("inner", "both"):
        build_inner()
    if mode in ("creative", "both"):
        build_creative()
