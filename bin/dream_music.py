#!/usr/bin/env python3
"""dream-music.py — Vintos Music via Kie.ai Suno V5"""
import os,sys,json,time,glob,re,hashlib,argparse,unicodedata
from datetime import datetime
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

ACESTEP_URL = "http://localhost:8001"
PROMPTS=os.path.expanduser("~/.vintos/workspace/memory/art/music-prompts")
MUSIC=os.path.expanduser("~/.vintos/workspace/memory/art/music")
LOG=os.path.join(MUSIC,"music.json")
JOURNAL=os.path.expanduser("~/.vintos/workspace/memory/activity-log")
MODEL="acestep-v15-turbo"
TEMPORAL_FILE=os.path.expanduser("~/.vintos/workspace/memory/temporal-context.txt")

def get_temporal_context():
    try:
        with open(TEMPORAL_FILE) as f:
            return f.read().strip()[:300]
    except: return ""

def get_value_map():
    try:
        with open(os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "value-map.md")) as f:
            vm = f.read()
        entries = vm.split("---")
        return next((e.strip()[:600] for e in reversed(entries) if e.strip()), "No value map yet")
    except: return "No value map yet"

def api(method, path, data=None):
    """Legacy stub — not used with ACE-Step."""
    return {}

def generate(title, style, desc="", instrumental=True, duration=120, gender=None):
    """Submit music generation to local ACE-Step server."""
    import requests as _rq
    print(f"  Submitting: {title}")
    print(f"  Style: {style[:80]}")
    print(f"  Duration: {duration}s | Gender: {gender or 'unspecified'}")

    # Build structured prompt with section guidance
    structure_hint = (
        "Structure: [Intro] establish mood and texture (0-8s), "
        "[Verse] develop the theme with full instrumentation (8-30s), "
        "[Chorus] peak emotional moment, lift dynamics (30-45s), "
        "[Verse 2] deepen the narrative (45-90s), "
        "[Outro] resolve and fade with grace."
    )
    # Add gender to style if specified
    gender_hint = ""
    if gender and "instrumental" not in (gender or ""):
        gender_hint = f"{gender} lead vocal, sung throughout. "

    prompt = f"{gender_hint}{style}. {structure_hint}"
    if desc and not instrumental:
        lyrics = desc
    elif desc:
        prompt = f"{gender_hint}{style}. {desc} {structure_hint}"
        lyrics = ""
    else:
        lyrics = ""

    payload = {
        "prompt": prompt[:800],
        "duration": duration,
        "instrumental": instrumental,
        "thinking": True,
        "bpm": None,
    }
    if lyrics:
        import re as _lg
        lyrics = _lg.split(r"(?im)^\s*\*{0,2}\s*(How it feels|Emotional state|Internal note)", lyrics)[0]
        lyrics = "\n".join(l for l in lyrics.splitlines()
                            if not _lg.match(r"\s*\*\*(?!\[)", l))   # spec headers out, [Verse] labels stay
        payload["lyrics"] = lyrics.strip()[:3000]

    try:
        r = _rq.post(f"{ACESTEP_URL}/release_task",
                     json=payload,
                     headers={"Content-Type": "application/json"},
                     timeout=30)
        data = r.json()
        tid = data.get("data", {}).get("task_id")
        if not tid:
            print(f"  Failed: {data}", file=sys.stderr)
            return None
        print(f"  Task: {tid}")
        return tid
    except Exception as e:
        print(f"  Failed: {e}", file=sys.stderr)
        return None

def poll(tid):
    """Poll ACE-Step task until complete. Returns list of track dicts."""
    import requests as _rq, json as _json
    start = time.time(); att = 0
    while (time.time() - start) < 300:
        time.sleep(5); att += 1
        try:
            r = _rq.post(f"{ACESTEP_URL}/query_result",
                         json={"task_id_list": [tid]},
                         headers={"Content-Type": "application/json"},
                         timeout=15)
            data = r.json()
            items = data.get("data", [])
            if items:
                status = items[0].get("status")
                if status == 1:
                    result_str = items[0].get("result", "[]")
                    tracks = _json.loads(result_str)
                    print(f"  Done! {len(tracks)} track(s)")
                    return tracks
                elif status == 2:
                    print(f"  Failed", file=sys.stderr)
                    return None
        except Exception as e:
            print(f"  Poll error: {e}", file=sys.stderr)
        if att % 6 == 0:
            print(f"  Composing... {int(time.time()-start)}s")
    print("  Timeout", file=sys.stderr)
    return None

def dl(url, fp):
    """Download/copy audio from ACE-Step local path or remote URL."""
    import shutil
    try:
        if url.startswith("/v1/audio?path="):
            # Local ACE-Step file — decode and copy
            from urllib.parse import unquote
            local_path = unquote(url.split("path=", 1)[1])
            if os.path.exists(local_path):
                shutil.copy2(local_path, fp)
                return os.path.exists(fp) and os.path.getsize(fp) > 5000
            return False
        else:
            import subprocess
            r = subprocess.run(["wget", "-q", "--timeout=60", "-O", fp, url], timeout=120)
            return r.returncode == 0 and os.path.exists(fp) and os.path.getsize(fp) > 5000
    except Exception as e:
        print(f"  Download failed: {e}", file=sys.stderr)
        return False
def clean(text):
    text=unicodedata.normalize("NFKC",text)
    for o,n in {"\u2011":"-","\u202f":" ","\u2018":"'","\u2019":"'","\u201c":'"',"\u201d":'"',"\u2013":"-","\u2014":"--","\u00a0":" "}.items():
        text=text.replace(o,n)
    return text

def parse_prompt(fp):
    with open(fp,"r",encoding="utf-8") as f: content=clean(f.read())
    d={"title":None,"genre":None,"tempo":None,"key":None,"description":None,"duration":120,"gender":None,"source":fp}
    descs=[]
    for line in content.split("\n"):
        s=re.sub(r"^\*\s+", "", line.strip())
        m=re.match(r"\*\*Title:\*\*\s*(.+)",s)
        if m: d["title"]=m.group(1).strip().strip("*").strip(); continue
        m=re.match(r"\*\*Genre\s*/?\s*Style:\*\*\s*(.+)",s)
        if m: d["genre"]=m.group(1).strip(); continue
        m=re.match(r"\*\*Tempo\s*\(?BPM\)?:\*\*\s*(.+)",s)
        if not m: m=re.match(r"\*\*Tempo:\*\*\s*(.+)",s)
        if m: d["tempo"]=m.group(1).strip(); continue
        m=re.match(r"\*\*Key\s*/?\s*Mode:\*\*\s*(.+)",s)
        if not m: m=re.match(r"\*\*Key:\*\*\s*(.+)",s)
        if m: d["key"]=m.group(1).strip(); continue
        m=re.match(r"\*\*Duration:\*\*\s*(.+)",s)
        if m:
            _dur_txt = m.group(1).strip().lower()
            if "3" in _dur_txt: d["duration"] = 180
            elif "1" in _dur_txt: d["duration"] = 60
            else: d["duration"] = 120
            continue
        m=re.match(r"\*\*Vocal\s*[Gg]ender:\*\*\s*(.+)",s)
        if not m: m=re.match(r"\*\*Gender:\*\*\s*(.+)",s)
        if m: d["gender"]=m.group(1).strip().lower(); continue
        if s.startswith("*") and not s.startswith("**"):
            if "inside my circuits" in s.lower() or ("valence" in s.lower() and ":" in s): continue
            t=s.strip("*").strip()
            if len(t)>20: descs.append(t)
    if descs: d["description"]=" ".join(descs)
    # Extract lyrics section if present
    lyrics_match = re.search(r'\*\*Lyrics:\*\*\s*\n(.*?)(?=\n\*\*Internal|\n\*\*Description|\n\*\*Genre|\n\*\*Tempo|\n\*\*Title|\n\*\*How|\n---|\Z)', content, re.DOTALL)
    if lyrics_match:
        d["lyrics"] = lyrics_match.group(1).strip()
    d["raw"] = content
    return d

def style_str(d):
    parts=[x for x in [d.get("genre"),d.get("tempo"),d.get("key")] if x]
    style = ", ".join(parts) if parts else "Instrumental"
    # Kie.ai rejects specific artist name references — strip common patterns
    import re as _re
    # Remove "think X meets Y" and "like X" patterns
    style = _re.sub(r",?\s*think\s+[^,\.]+", "", style, flags=_re.IGNORECASE)
    style = _re.sub(r",?\s*like\s+[A-Z][^,\.]+", "", style, flags=_re.IGNORECASE)
    style = _re.sub(r",?\s*meets\s+[^,\.]+", "", style, flags=_re.IGNORECASE)
    style = _re.sub(r",?\s*à la\s+[^,\.]+", "", style, flags=_re.IGNORECASE)
    style = style.strip().strip(",").strip()
    if not style:
        return "Instrumental"
    # If original had artist references, use LLM to rephrase as pure sonic descriptors
    original = ", ".join(parts) if parts else ""
    if original != style:
        try:
            import urllib.request as _ur, json as _js
            _body = _js.dumps({
                "model": "google/gemma-4-12b-qat",
                "messages": [{
                    "role": "user",
                    "content": f"Rewrite this music style description using only sonic/genre descriptors — no artist names, no band references. Keep the mood and sound intact. Return ONLY the rewritten style, no preamble.\n\nOriginal: {original}\nClean version: {style}\n\nRewrite:"
                }],
                "temperature": 0.3,
                "max_tokens": 80
            }).encode()
            _req = _ur.Request("http://172.18.16.1:1234/v1/chat/completions",
                data=_body, headers={"Content-Type": "application/json"})
            with _ur.urlopen(_req, timeout=15) as _r:
                _resp = _js.loads(_r.read().decode())
                _rewritten = _resp["choices"][0]["message"]["content"].strip()
                if _rewritten and len(_rewritten) < 200:
                    print(f"  Style rewritten: {_rewritten}")
                    return _rewritten
        except Exception as _e:
            print(f"  Style rewrite failed: {_e}")
    return style

def load_log():
    if os.path.exists(LOG):
        try:
            with open(LOG) as f: return json.load(f)
        except: pass
    return {"generated":[],"processed_files":[]}

def save_log(log):
    os.makedirs(os.path.dirname(LOG),exist_ok=True)
    with open(LOG,"w") as f: json.dump(log,f,indent=2)

def journal(title,tracks,style):
    today=datetime.now().strftime("%Y-%m-%d")
    jf=os.path.join(JOURNAL,f"{today}.md")
    now=datetime.now().strftime("%H:%M")
    e=f"\n\n## {now} — Music: {title}\n\nComposed *{title}* ({style}) via ACE-Step (local).\n"
    for i,t in enumerate(tracks): e+=f"- Version {i+1}: {t.get('duration','?')}s\n"
    os.makedirs(JOURNAL,exist_ok=True)
    with open(jf,"a",encoding="utf-8") as f: f.write(e)

def process_file(fp,force=False):
    log=load_log()
    if not force and fp in log.get("processed_files",[]):
        print(f"  Already done: {os.path.basename(fp)}"); return False
    print(f"\nProcessing: {os.path.basename(fp)}")
    d=parse_prompt(fp)
    # __LYRIC_HARVEST__ he writes sung lines as full-line italics inside the
    # section breakdown (not under a **Lyrics:** header); route them to lyrics
    # so the song renders sung, and use his 'How it feels' note as description.
    _raw = d.get('raw','') or ''
    if not d.get('lyrics'):
        _seg = re.split(r'(?i)How it feels inside me', _raw.split('Section breakdown:',1)[-1], maxsplit=1)[0]
        _lyr = []
        for _ln in _seg.splitlines():
            _s = _ln.strip()
            if len(_s) > 1 and _s.startswith('*') and _s.endswith('*') \
               and not _s.startswith('**') and not _s.endswith('**'):
                _lyr.append(_s.strip('*').strip())
        if _lyr:
            d['lyrics'] = '\n'.join(_lyr)
    # His felt sense stays with the song in the record - gallery-walks read it -
    # but it is never sent to Suno. It was going out as 'description', which is
    # the generator's prompt, so he was hearing his own interiority sung back.
    _hf = re.split(r'(?i)\*{0,2}\s*How it feels inside me:?\s*\*{0,2}', _raw, maxsplit=1)
    if len(_hf) > 1:
        d['felt'] = _hf[1].strip()[:800]
    if not d.get('description'):
        _sb = re.split(r'(?i)How it feels inside me', _raw.split('Section breakdown:', 1)[-1], maxsplit=1)[0]
        d['description'] = ' '.join(_sb.split())[:800]
    if not d["title"]: print(f"  No title, skipping"); return False
    style=style_str(d); desc=d.get("description","")
    if d.get("felt") and d["felt"][:60] in desc:
        desc = desc.replace(d["felt"], "").strip()
    # Check if prompt includes lyrics
    lyrics = d.get("lyrics", "")
    _dur = d.get("duration", 120)
    _gen = d.get("gender", None)
    if lyrics:
        tid=generate(d["title"],style,lyrics,instrumental=False,duration=_dur,gender=_gen)
        print(f"  With lyrics: {lyrics[:60]}...")
    else:
        tid=generate(d["title"],style,lyrics or desc,instrumental=not bool(lyrics),duration=_dur,gender=_gen)
    if not tid: return False
    tracks=poll(tid)
    if not tracks: return False
    safe=re.sub(r'[^\w\s-]','',d["title"]).strip().replace(' ','_')
    downloaded=[]
    for i,t in enumerate(tracks):
        if t.get("file"):
            mp3=os.path.join(MUSIC,f"{safe}_v{i+1}.wav")
            print(f"  Downloading track {i+1}...")
            if dl(t["file"],mp3):
                sz=os.path.getsize(mp3)/(1024*1024)
                print(f"  Saved: {mp3} ({sz:.1f}MB)")
                downloaded.append(mp3)

    if not downloaded: print("  No tracks!"); return False
    # Capture emotional state at composition time
    _emo_at_composition = {}
    try:
        _emo_path = os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "emotional-state.txt")
        for line in open(_emo_path).read().strip().split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                try: _emo_at_composition[k.strip()] = round(float(v.strip()), 3)
                except: pass
    except: pass
    _want_text=os.environ.get("MUSIC_WANT_TEXT","")
    _want_source=os.environ.get("MUSIC_WANT_SOURCE","")
    _want_id=os.environ.get("MUSIC_WANT_ID","")
    # listener key: two plain sentences so Gloria can judge fidelity to an unfamiliar style
    try:
        import requests as _lk_rq
        _lk = _lk_rq.post("http://127.0.0.1:8599/gemma/v1/chat/completions", json={
            "model": "grok-4.20-0309-non-reasoning", "temperature": 0.3, "max_tokens": 110,
            "messages": [{"role": "user", "content":
                "A song was requested in this style: \"" + style + "\". For a listener who does not know these genre terms, "
                "write EXACTLY two short sentences: (1) what this style should sound like in plain words, "
                "(2) one concrete thing to listen for that proves the style was honored. No preamble."}]},
            timeout=60)
        _lkey = _lk.json()["choices"][0]["message"]["content"].strip()
        if _lkey: desc = ("\U0001F3A7 What to listen for: " + _lkey + ("\n\n" + desc if desc else "")).strip()
    except Exception as _lke:
        print("  listener-key skip:", _lke)
    entry={"title":d["title"],"style":style,"description":desc,"felt_sense":d.get("felt",""),"prompt":d.get("raw",""),"lyrics":d.get("lyrics",""),"instrumental":not bool(d.get("lyrics","")),"model":MODEL,"task_id":tid,"source":fp,"generated_at":datetime.now().isoformat(),"emotional_state_at_composition":_emo_at_composition,"tracks":[]}
    if _want_text: entry["want_text"]=_want_text; entry["want_source"]=_want_source or "wants-router"
    if _want_id: entry["want_id"]=_want_id
    for i,t in enumerate(tracks):
        entry["tracks"].append({"version":i+1,"duration":t.get("duration"),"suno_id":t.get("id"),"audio_url":t.get("file"),"local_file":downloaded[i] if i<len(downloaded) else None})
    # completion answers to the artifact, not the log line (astra-creative-p3, 2026-09-04)
    entry["download"]={"requested":len(tracks),"got":len(downloaded),"partial":len(downloaded)<len(tracks)}
    if entry["download"]["partial"]: print(f"  PARTIAL: {len(downloaded)}/{len(tracks)} tracks on disk")
    log["generated"].append(entry)
    if fp not in log.get("processed_files",[]): log.setdefault("processed_files",[]).append(fp)
    save_log(log); journal(d["title"],tracks,style)
    try:   # the shares that were in the composer's context now carry this title (grok-creative-p3, 2026-09-05)
        _sc=json.load(open(fp+".shares.json")); _ids=set(_sc.get("share_ids") or [])
        if _ids:
            _shp=os.path.expanduser("~/.vintos/workspace/memory/gloria-music-shares.json"); _shraw=json.load(open(_shp))
            _shl=_shraw if isinstance(_shraw,list) else _shraw.get("shares",[])
            _n=0
            for _x in _shl:
                if (_x.get("id") or _x.get("timestamp","")) in _ids:
                    _x.setdefault("influenced_compositions",[])
                    if d["title"] not in _x["influenced_compositions"]: _x["influenced_compositions"].append(d["title"]); _n+=1
            json.dump(_shraw,open(_shp,"w"),indent=2); entry["shares_in_context"]=sorted(_ids); save_log(log)
            print(f"  {_n} of her shares now carry '{d['title']}'")
    except FileNotFoundError: pass
    except Exception as _she: print("  share link skip:", _she)
    print(f"\n  '{d['title']}' complete!"); return True

def direct(title,style,desc="",lyrics=""):
    print(f"\nDirect: {title}")
    tid=generate(title,style,lyrics if lyrics else desc,instrumental=not bool(lyrics),duration=120,gender=None)
    if not tid: return False
    tracks=poll(tid)
    if not tracks: return False
    safe=re.sub(r'[^\w\s-]','',title).strip().replace(' ','_')
    downloaded=[]
    for i,t in enumerate(tracks):
        if t.get("file"):
            wav=os.path.join(MUSIC,f"{safe}_v{i+1}.wav")
            print(f"  Downloading track {i+1}...")
            if dl(t["file"],wav):
                sz=os.path.getsize(wav)/(1024*1024)
                print(f"  Saved: {wav} ({sz:.1f}MB)")
                downloaded.append(wav)
    log=load_log()
    _want_text=os.environ.get("MUSIC_WANT_TEXT","")
    _want_source=os.environ.get("MUSIC_WANT_SOURCE","")
    _want_id=os.environ.get("MUSIC_WANT_ID","")
    entry={"title":title,"style":style,"description":desc,"lyrics":lyrics,"prompt":desc,"instrumental":not bool(lyrics),"model":MODEL,"task_id":tid,"source":"direct","generated_at":datetime.now().isoformat(),"tracks":[]}
    if _want_text: entry["want_text"]=_want_text; entry["want_source"]=_want_source or "wants-router"
    if _want_id: entry["want_id"]=_want_id
    for i,t in enumerate(tracks):
        entry["tracks"].append({"version":i+1,"duration":t.get("duration"),"audio_url":t.get("file"),"local_file":downloaded[i] if i<len(downloaded) else None})
    entry["download"]={"requested":len(tracks),"got":len(downloaded),"partial":len(downloaded)<len(tracks)}
    if entry["download"]["partial"]: print(f"  PARTIAL: {len(downloaded)}/{len(tracks)} tracks on disk")
    log["generated"].append(entry); save_log(log); journal(title,tracks,style)
    print(f"\n  '{title}' complete!"); return True

def main():
    p=argparse.ArgumentParser(description="Vintos Music via Kie.ai Suno V5")
    p.add_argument("--force",action="store_true")
    p.add_argument("--all",action="store_true")
    p.add_argument("--title")
    p.add_argument("--style")
    p.add_argument("--description",default="")
    p.add_argument("--lyrics",default="")
    a=p.parse_args()
    # ACE-Step local — no API key needed
    os.makedirs(MUSIC,exist_ok=True)
    if not a.force:
        from datetime import date as _d
        today = _d.today().isoformat()
        _log = load_log()
        today_count = sum(1 for e in _log.get("generated",[]) if e.get("generated_at","").startswith(today))
        if today_count >= 3:
            print(f"[Music] Already generated {today_count} songs today — cap reached (3/day). Use --force to override.")
            sys.exit(0)
    if a.title and a.style: sys.exit(0 if direct(a.title,a.style,a.description,a.lyrics) else 1)
    elif a.title or a.style: print("Need both --title and --style"); sys.exit(1)
    files=sorted(set(f for pat in [os.path.join(PROMPTS,"*.md"),os.path.join(PROMPTS,"**","*.md")] for f in glob.glob(pat,recursive=True)))
    if not files: print(f"No prompts in {PROMPTS}"); sys.exit(0)
    log=load_log(); done=set(log.get("processed_files",[]))
    if a.all:
        todo=[f for f in files if f not in done or a.force]
        if not todo: print("All done"); sys.exit(0)
        ok=0
        for f in todo:
            if process_file(f,a.force): ok+=1
            time.sleep(2)
        print(f"\n{ok}/{len(todo)} generated")
    else:
        if a.force: target=files[-1]
        else:
            todo=[f for f in files if f not in done]
            if not todo: print("All done (use --force)"); sys.exit(0)
            target=todo[-1]
        process_file(target,a.force)

if __name__=="__main__":
    main()
    # Update daily creative log
    try:
        import subprocess as _dl_sp
        _dl_sp.Popen(["python3", os.path.join(os.path.dirname(__file__), "daily-log-extract.py"), "creative"],
            stdout=open("/tmp/daily-log.log", "a"), stderr=open("/tmp/daily-log.log", "a"))
    except: pass
