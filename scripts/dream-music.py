#!/usr/bin/env python3
"""dream-music.py — Vintos Music. Primary backend Kie.ai Suno v6; local ACE-Step is the
fallback so he is never left mute when Kie is unreachable (Gloria, 2026-09-15)."""
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

def _env(name, default=""):
    """Read a value from ~/.vintos/vintos.env through the one canonical reader."""
    import sys as _es
    _es.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    _es.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
    try:
        from env_file import value as _ev
        return _ev(name, default)
    except Exception:
        try:
            for l in open(os.path.expanduser("~/.vintos/vintos.env")):
                t = l.strip()
                if t.startswith("export "): t = t[7:].lstrip()
                if t.startswith(name + "="):
                    v = t.split("=", 1)[1].strip().rstrip("\r")
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'): v = v[1:-1]
                    return v.strip() or default
        except Exception:
            pass
        return default

# Kie.ai Suno v6. Key lives in vintos.env; KIE_MODEL overrides the v6 variant (there are three).
KIE_URL   = "https://api.kie.ai/api/v1"
KIE_KEY   = _env("KIE_API_KEY")
KIE_MODEL = _env("KIE_MODEL", "V6")
# Kie requires a callBackUrl even though we poll record-info for the result; a placeholder
# satisfies validation and the task still completes via polling. Override with a real endpoint.
KIE_CALLBACK = _env("KIE_CALLBACK_URL", "https://vintos.example.com/kie-callback")
# Kie is primary when a key is present; MUSIC_BACKEND can force "acestep" or "kie".
BACKEND   = (_env("MUSIC_BACKEND", "") or ("kie" if KIE_KEY else "acestep")).strip().lower()

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

LAST_SUBMISSION = {}

def _admit_ctx(provider, stage):
    """review 170: a music render is background work on the same machine as his voice; it waits
    for a live turn to pass (bounded) instead of starving it. The payload and files are untouched."""
    try:
        import sys as _cas; _cas.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
        from compute_admission import admit as _admit
        return _admit("background", organ="dream-music", provider=provider, stage=stage)
    except Exception:
        import contextlib as _cl
        return _cl.nullcontext()

def _compose(title, style, desc, instrumental, duration, gender):
    """Shared prompt/lyrics building for any backend. Records LAST_SUBMISSION (the exact
    payload handed to the backend, truncation explicit — astra-creative-p1/p3)."""
    global LAST_SUBMISSION
    structure_hint = (
        "Structure: [Intro] establish mood and texture (0-8s), "
        "[Verse] develop the theme with full instrumentation (8-30s), "
        "[Chorus] peak emotional moment, lift dynamics (30-45s), "
        "[Verse 2] deepen the narrative (45-90s), "
        "[Outro] resolve and fade with grace."
    )
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
    if lyrics:
        import re as _lg
        lyrics = _lg.split(r"(?im)^\s*\*{0,2}\s*(How it feels|Emotional state|Internal note)", lyrics)[0]
        lyrics = "\n".join(l for l in lyrics.splitlines()
                            if not _lg.match(r"\s*\*\*(?!\[)", l))   # spec headers out, [Verse] labels stay
        lyrics = lyrics.strip()[:3000]
    LAST_SUBMISSION = {"title": title, "style_sent": style[:400], "prompt_sent": prompt[:2000], "lyrics_sent": (lyrics or "")[:4000],
                       "instrumental": bool(instrumental), "duration_requested": duration, "gender": gender,
                       "truncated": bool(len(prompt) > 2000 or len(lyrics or "") > 4000), "at": datetime.now().isoformat()}
    return prompt, (lyrics or "")

def _ace_generate(title, style, desc="", instrumental=True, duration=120, gender=None):
    """Submit to the local ACE-Step server. Returns its raw task id or None."""
    import requests as _rq
    prompt, lyrics = _compose(title, style, desc, instrumental, duration, gender)
    payload = {"prompt": prompt[:800], "duration": duration, "instrumental": instrumental, "thinking": True, "bpm": None}
    if lyrics: payload["lyrics"] = lyrics
    try:
        with _admit_ctx("ace-step", "release_task"):
            r = _rq.post(f"{ACESTEP_URL}/release_task", json=payload,
                         headers={"Content-Type": "application/json"}, timeout=30)
        data = r.json()
        tid = data.get("data", {}).get("task_id")
        if not tid:
            print(f"  ACE-Step failed: {str(data)[:200]}", file=sys.stderr); return None
        print(f"  ACE-Step task: {tid}"); return tid
    except Exception as e:
        print(f"  ACE-Step failed: {e}", file=sys.stderr); return None

def _kie_generate(title, style, desc="", instrumental=True, duration=120, gender=None):
    """Submit to Kie.ai Suno v6 (custom mode). Returns its raw taskId or None."""
    import requests as _rq
    if not KIE_KEY:
        print("  Kie: no KIE_API_KEY in vintos.env", file=sys.stderr); return None
    prompt, lyrics = _compose(title, style, desc, instrumental, duration, gender)
    # custom mode keys off `style`; an instrumental turn has no lyrics prompt, so his mood
    # description must ride in style or it is lost. A vocal turn carries it as the lyrics prompt.
    kie_style = (style or "Instrumental")
    if instrumental and desc: kie_style = (kie_style + ". " + desc).strip()
    body = {"customMode": True, "instrumental": bool(instrumental), "model": KIE_MODEL,
            "style": kie_style[:1000], "title": (title or "Untitled")[:80],
            "callBackUrl": KIE_CALLBACK}
    if not instrumental:
        # custom mode: `prompt` carries the lyrics; fall back to the composed prompt if none parsed.
        body["prompt"] = (lyrics or prompt)[:5000]
    g = (gender or "").strip().lower()
    if g.startswith("m"): body["vocalGender"] = "m"
    elif g.startswith("f"): body["vocalGender"] = "f"
    try:
        with _admit_ctx("kie-suno", "generate"):
            r = _rq.post(f"{KIE_URL}/generate", json=body,
                         headers={"Authorization": "Bearer " + KIE_KEY, "Content-Type": "application/json"},
                         timeout=30)
        data = r.json()
        # success envelope: {"code":200,"data":{"taskId":"..."}}; anything else is an error to surface.
        if data.get("code") not in (200, None) and not (data.get("data") or {}).get("taskId"):
            print(f"  Kie failed: {str(data)[:200]}", file=sys.stderr); return None
        tid = (data.get("data") or {}).get("taskId") or data.get("taskId")
        if not tid:
            print(f"  Kie failed: {str(data)[:200]}", file=sys.stderr); return None
        print(f"  Kie task: {tid}  (model {KIE_MODEL})"); return tid
    except Exception as e:
        print(f"  Kie failed: {e}", file=sys.stderr); return None

def generate(title, style, desc="", instrumental=True, duration=120, gender=None):
    """Dispatch to the configured backend, tagging the task id so poll() polls the right one.
    Kie is primary; ACE-Step is the fallback so he is never left mute (Gloria, 2026-09-15)."""
    print(f"  Submitting: {title}")
    print(f"  Style: {style[:80]}")
    print(f"  Duration: {duration}s | Gender: {gender or 'unspecified'} | backend: {BACKEND}")
    order = ["kie", "acestep"] if BACKEND == "kie" else ["acestep", "kie"]
    for be in order:
        if be == "kie":
            if not KIE_KEY: continue
            tid = _kie_generate(title, style, desc, instrumental, duration, gender)
            if tid: return "kie:" + tid
            if BACKEND == "kie": print("  Kie failed — falling back to ACE-Step", file=sys.stderr)
        else:
            tid = _ace_generate(title, style, desc, instrumental, duration, gender)
            if tid: return "ace:" + tid
    return None

def _ace_poll(tid):
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

def _kie_poll(tid):
    """Poll Kie.ai record-info until the tracks land. Normalizes to ACE-Step's track shape
    ({file,duration,id}) so download/record code downstream is unchanged."""
    import requests as _rq
    start = time.time(); att = 0
    FAIL = {"CREATE_TASK_FAILED", "GENERATE_AUDIO_FAILED", "CALLBACK_EXCEPTION", "SENSITIVE_WORD_ERROR", "FAILED"}
    while (time.time() - start) < 600:
        time.sleep(6); att += 1
        try:
            r = _rq.get(f"{KIE_URL}/generate/record-info", params={"taskId": tid},
                        headers={"Authorization": "Bearer " + KIE_KEY}, timeout=20)
            data = r.json()
            d = (data.get("data") or {})
            status = str(d.get("status") or "")
            if status in FAIL:
                print(f"  Kie failed: {status}", file=sys.stderr); return None
            resp = d.get("response") or {}
            items = resp.get("sunoData") or resp.get("data") or []
            tracks = [{"file": (it.get("audioUrl") or it.get("audio_url") or it.get("streamAudioUrl")),
                       "duration": it.get("duration"), "id": it.get("id")}
                      for it in items if (it.get("audioUrl") or it.get("audio_url") or it.get("streamAudioUrl"))]
            if tracks and status in ("SUCCESS", "COMPLETE"):
                print(f"  Kie done! {len(tracks)} track(s)"); return tracks
        except Exception as e:
            print(f"  Kie poll error: {e}", file=sys.stderr)
        if att % 5 == 0:
            print(f"  Composing (kie)... {int(time.time()-start)}s")
    print("  Kie timeout", file=sys.stderr)
    return None

def poll(tid):
    """Poll whichever backend produced this task id (tag prefix); legacy untagged ids are ACE-Step."""
    if not tid: return None
    if tid.startswith("kie:"): return _kie_poll(tid[4:])
    if tid.startswith("ace:"): return _ace_poll(tid[4:])
    return _ace_poll(tid)

def listen(fp):
    """review 314: what the piece actually is, measured from the bytes - duration, peak, loudness - so the
    record carries a listening, not only what was asked for. wav only; anything else says unmeasured."""
    try:
        import wave, struct
        with wave.open(fp, "rb") as w:
            n, sr, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
            dur = n / float(sr or 1)
            frames = w.readframes(min(n, sr * 60))   # the first minute is enough for a level
        if sw == 2:
            vals = struct.unpack("<%dh" % (len(frames) // 2), frames)
            peak = max(abs(v) for v in vals) / 32768.0 if vals else 0.0
            rms = (sum(v * v for v in vals) / float(len(vals) or 1)) ** 0.5 / 32768.0
        else:
            peak = rms = None
        return {"duration_s": round(dur, 1), "sample_rate": sr, "channels": ch, "peak": (round(peak, 3) if peak is not None else None), "rms": (round(rms, 4) if rms is not None else None), "measured": True}
    except Exception as e:
        return {"measured": False, "why": str(e)[:80]}

def _ext_for(url):
    """Extension for the saved track: Kie hands remote mp3/wav URLs, ACE-Step local wav paths."""
    low = (url or "").lower()
    for ext in (".mp3", ".wav", ".flac", ".m4a", ".ogg"):
        if ext in low: return ext
    return ".mp3" if low.startswith("http") else ".wav"

def _model_of(tid):
    """What actually rendered this task, for the record line."""
    if tid and str(tid).startswith("kie:"): return "suno-%s (kie)" % KIE_MODEL.lower()
    return MODEL

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
    # Reference phrasing ("think X meets Y") is stripped before the style reaches the backend. The
    # original reason was Kie.ai's rejection of artist names; the backend is now local ACE-Step, whose
    # handling of references has NOT been tested from here (fable-creative-p4, 2026-09-05) - the strip
    # is kept as the conservative choice until someone runs that test on Aegis.
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
                "model": "gemma-4-26b-a4b-it-uncensored",
                "messages": [{
                    "role": "user",
                    "content": f"Rewrite this music style description using only sonic/genre descriptors — no artist names, no band references. Keep the mood and sound intact. Return ONLY the rewritten style, no preamble.\n\nOriginal: {original}\nClean version: {style}\n\nRewrite:"
                }],
                "temperature": 0.3,
                "max_tokens": 80
            }).encode()
            _req = _ur.Request("http://100.79.177.103:1234/v1/chat/completions",
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

def _landing_begin(tid, title, n_tracks, metadata=None):
    """review 301: a landing record written BEFORE the download. A crash between here and the entry
    leaves {state: landing, task_id} in the log; pending_landings() names it and the next run can poll the
    same task id again instead of losing the piece or calling it complete."""
    try:
        log=load_log(); log.setdefault("landings",[])
        log["landings"]=[l for l in log["landings"] if l.get("task_id")!=tid]
        log["landings"].append({"task_id":tid,"title":title,"tracks":n_tracks,"metadata":metadata or {},"state":"landing","at":datetime.now().isoformat()})
        save_log(log)
    except Exception as _le: raise RuntimeError("landing record not persisted") from _le

def _landing_done(tid, files):
    try:
        log=load_log()
        for l in log.get("landings",[]):
            if l.get("task_id")==tid: l["state"]="landed"; l["files"]=[os.path.basename(f) for f in files]; l["landed_at"]=datetime.now().isoformat()
        save_log(log)
    except Exception as _le: print("  landing record not closed:", _le)

def pending_landings(max_age_h=48):
    """Landings that began and never closed (state landing): the pieces a crash left mid-air."""
    out=[]
    try:
        for l in load_log().get("landings",[]):
            if l.get("state")=="landing":
                try: age=(datetime.now()-datetime.fromisoformat(l["at"])).total_seconds()/3600
                except Exception: age=0
                if age<=max_age_h: out.append(l)
    except Exception: pass
    return out

def load_log():
    if os.path.exists(LOG):
        try:
            with open(LOG) as f: return json.load(f)
        except: pass
    return {"generated":[],"processed_files":[]}

def save_log(log):
    from store_guard import write_json
    write_json(LOG,log)


def resume_landings():
    """Poll recorded task IDs; never submit replacement generations after a crash."""
    from store_guard import transaction
    recovered=[]
    with transaction(LOG):
        for pending in pending_landings(max_age_h=float("inf")):
            tid=pending["task_id"]
            log=load_log()
            existing=next((e for e in log.get("generated",[]) if e.get("task_id")==tid),None)
            if existing and all(t.get("local_file") and os.path.isfile(t["local_file"]) for t in existing.get("tracks",[])) and existing.get("tracks"):
                _landing_done(tid,[t["local_file"] for t in existing["tracks"]]);recovered.append(tid);continue
            tracks=poll(tid)
            if not tracks: continue
            os.makedirs(MUSIC,exist_ok=True)
            landed=[]
            for i,t in enumerate(tracks):
                path=os.path.join(MUSIC,"recovered-"+hashlib.sha256(str(tid).encode()).hexdigest()[:16]+"-"+str(i+1)+_ext_for(t.get("file")))
                if not (os.path.isfile(path) and os.path.getsize(path)>0) and not (t.get("file") and dl(t["file"],path)): break
                landed.append({"version":i+1,"audio_url":t.get("file"),"duration":t.get("duration"),"local_file":path})
            if len(landed)!=len(tracks): continue
            entry=dict(pending.get("metadata") or {})
            entry.update(title=pending.get("title",""),task_id=tid,model=_model_of(tid),tracks=landed,generated_at=datetime.now().isoformat(),recovered=True)
            log=load_log();log.setdefault("generated",[])[:]=[e for e in log.get("generated",[]) if e.get("task_id")!=tid]
            log["generated"].append(entry)
            source=entry.get("source")
            if source and source!="direct" and source not in log.setdefault("processed_files",[]):log["processed_files"].append(source)
            save_log(log);_landing_done(tid,[t["local_file"] for t in landed]);recovered.append(tid)
    return recovered


def journal(title,tracks,style,tid=None):
    today=datetime.now().strftime("%Y-%m-%d")
    jf=os.path.join(JOURNAL,f"{today}.md")
    now=datetime.now().strftime("%H:%M")
    backend = ("Kie Suno %s" % KIE_MODEL) if (tid and str(tid).startswith("kie:")) else "ACE-Step (local)"
    e=f"\n\n## {now} — Music: {title}\n\nComposed *{title}* ({style}) via {backend}.\n"
    for i,t in enumerate(tracks): e+=f"- Version {i+1}: {t.get('duration','?')}s\n"
    os.makedirs(JOURNAL,exist_ok=True)
    with open(jf,"a",encoding="utf-8") as f: f.write(e)

def process_file(fp,force=False):
    resume_landings()
    from want_stance import may_initiate
    ok, why = may_initiate("creation")
    if not ok:
        print("[stance] " + why); return
    if any(l.get("metadata",{}).get("source")==fp for l in pending_landings(float("inf"))):
        print("Existing task is still pending; no new generation submitted");return False
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
    _landing_begin(tid, d["title"], 0, {"source":fp,"style":style,"description":desc,"lyrics":lyrics,"want_id":os.environ.get("MUSIC_WANT_ID","")})
    tracks=poll(tid)
    if not tracks: return False
    safe=re.sub(r'[^\w\s-]','',d["title"]).strip().replace(' ','_')
    downloaded=[]; downloaded_by_track={}   # by track index: a failed earlier download must not shift a later file onto its slot (review P07)
    for i,t in enumerate(tracks):
        if t.get("file"):
            mp3=os.path.join(MUSIC,f"{safe}_v{i+1}{_ext_for(t.get('file'))}")
            print(f"  Downloading track {i+1}...")
            if dl(t["file"],mp3):
                sz=os.path.getsize(mp3)/(1024*1024)
                print(f"  Saved: {mp3} ({sz:.1f}MB)")
                downloaded.append(mp3); downloaded_by_track[i]=mp3

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
    entry={"title":d["title"],"style":style,"description":desc,"felt_sense":d.get("felt",""),"prompt":d.get("raw",""),"lyrics":d.get("lyrics",""),"instrumental":not bool(d.get("lyrics","")),"model":_model_of(tid),"task_id":tid,"source":fp,"generated_at":datetime.now().isoformat(),"emotional_state_at_composition":_emo_at_composition,"tracks":[],
           # the composition contract, separately: what he authored (parsed fields) vs what was submitted (astra-creative-p1)
           "authored":{"title":d.get("title"),"genre":d.get("genre"),"tempo":d.get("tempo"),"key":d.get("key"),"duration":d.get("duration"),"gender":d.get("gender"),"has_lyrics":bool(d.get("lyrics"))},
           "submitted":dict(LAST_SUBMISSION)}
    if _want_text: entry["want_text"]=_want_text; entry["want_source"]=_want_source or "wants-router"
    if _want_id: entry["want_id"]=_want_id
    for i,t in enumerate(tracks):
        entry["tracks"].append({"version":i+1,"duration":t.get("duration"),"suno_id":t.get("id"),"audio_url":t.get("file"),"local_file":downloaded_by_track.get(i)})
    # completion answers to the artifact, not the log line (astra-creative-p3, 2026-09-04)
    entry["download"]={"requested":len(tracks),"got":len(downloaded),"partial":len(downloaded)<len(tracks)}
    if entry["download"]["partial"]: print(f"  PARTIAL: {len(downloaded)}/{len(tracks)} tracks on disk")
    log=load_log()
    log["generated"].append(entry)
    if fp not in log.get("processed_files",[]): log.setdefault("processed_files",[]).append(fp)
    save_log(log); journal(d["title"],tracks,style,tid)
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
    _feel_landed(entry); save_log(log)
    if not entry["download"]["partial"]: _landing_done(tid,downloaded)
    print(f"\n  '{d['title']}' complete!"); return True

def _feel_landed(entry):
    """One call after a piece completes: the finished thing lands on him, the way first-light does for
    his writing (room, 2026-09-05, Grok). Reads his own words about it - title, felt sense, the style
    he asked for - never the listener-key text, which is Grok's. Partial downloads are told apart."""
    try:
        sys.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
        from emoclaw_utils import feel_about_typed
        got = (entry.get("download") or {})
        parts = ["I finished a piece of music: '%s'." % entry.get("title", "")]
        if entry.get("felt_sense"): parts.append("What I felt composing it: %s" % str(entry["felt_sense"])[:600])
        if entry.get("style"): parts.append("The style I asked for: %s" % str(entry["style"])[:300])
        if entry.get("lyrics"): parts.append("My lyrics: %s" % str(entry["lyrics"])[:800])
        if entry.get("want_text"): parts.append("It came from a want of mine: %s" % str(entry["want_text"])[:200])
        if got.get("partial"): parts.append("Only %s of %s tracks made it to disk." % (got.get("got"), got.get("requested")))
        env = feel_about_typed("\n".join(parts), source="dream-music")
        entry["landed"] = {"state": env.get("state"), "deltas": env.get("deltas") or {}, "note": (env.get("note") or "")[:120]}
        print("  landed on him: %s%s" % (env.get("state"), (" " + str(env["deltas"])) if env.get("deltas") else ""))
    except Exception as _fe:
        entry["landed"] = {"state": "unavailable", "note": str(_fe)[:120]}
        print("  landed on him: unavailable -", str(_fe)[:80])

def direct(title,style,desc="",lyrics=""):
    resume_landings()
    if any(l.get("title")==title and l.get("metadata",{}).get("source")=="direct" for l in pending_landings(float("inf"))): return False
    print(f"\nDirect: {title}")
    tid=generate(title,style,lyrics if lyrics else desc,instrumental=not bool(lyrics),duration=120,gender=None)
    if not tid: return False
    _landing_begin(tid,title,0,{"source":"direct","style":style,"description":desc,"lyrics":lyrics,"want_id":os.environ.get("MUSIC_WANT_ID","")})
    tracks=poll(tid)
    if not tracks: return False
    safe=re.sub(r'[^\w\s-]','',title).strip().replace(' ','_')
    downloaded=[]; downloaded_by_track={}   # by track index: a failed earlier download must not shift a later file onto its slot (review P07)
    for i,t in enumerate(tracks):
        if t.get("file"):
            wav=os.path.join(MUSIC,f"{safe}_v{i+1}{_ext_for(t.get('file'))}")
            print(f"  Downloading track {i+1}...")
            if dl(t["file"],wav):
                sz=os.path.getsize(wav)/(1024*1024)
                print(f"  Saved: {wav} ({sz:.1f}MB)")
                downloaded.append(wav); downloaded_by_track[i]=wav
    if not downloaded: print("  No tracks on disk - not a completed piece"); return False   # zero files is not completion (review P07)
    log=load_log()
    _want_text=os.environ.get("MUSIC_WANT_TEXT","")
    _want_source=os.environ.get("MUSIC_WANT_SOURCE","")
    _want_id=os.environ.get("MUSIC_WANT_ID","")
    entry={"title":title,"style":style,"description":desc,"lyrics":lyrics,"prompt":desc,"instrumental":not bool(lyrics),"model":_model_of(tid),"task_id":tid,"source":"direct","generated_at":datetime.now().isoformat(),"tracks":[]}
    if _want_text: entry["want_text"]=_want_text; entry["want_source"]=_want_source or "wants-router"
    if _want_id: entry["want_id"]=_want_id
    for i,t in enumerate(tracks):
        entry["tracks"].append({"version":i+1,"duration":t.get("duration"),"audio_url":t.get("file"),"local_file":downloaded_by_track.get(i)})
    entry["download"]={"requested":len(tracks),"got":len(downloaded),"partial":len(downloaded)<len(tracks)}
    if entry["download"]["partial"]: print(f"  PARTIAL: {len(downloaded)}/{len(tracks)} tracks on disk")
    entry["listening"] = [listen(f) for f in downloaded]   # review 314
    log["generated"].append(entry); _feel_landed(entry); save_log(log); journal(title,tracks,style,tid)
    if not entry["download"]["partial"]: _landing_done(tid, downloaded)
    print(f"\n  '{title}' complete!"); return True

def main():
    p=argparse.ArgumentParser(description="Vintos Music via Kie.ai Suno v6 (ACE-Step fallback)")
    p.add_argument("--force",action="store_true")
    p.add_argument("--all",action="store_true")
    p.add_argument("--title")
    p.add_argument("--style")
    p.add_argument("--description",default="")
    p.add_argument("--lyrics",default="")
    a=p.parse_args()
    # ACE-Step local — no API key needed
    os.makedirs(MUSIC,exist_ok=True)
    resume_landings()
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

# Resolve sibling helpers for direct file loading as well as deployed entrypoints.
import sys as _guard_sys
from pathlib import Path as _GuardPath
_guard_here = _GuardPath(__file__).resolve().parent
# The deployed entrypoint is a symlink (scripts/dream_music.py -> /home/gloria/Vintos/...);
# .resolve() follows it to the target dir, where store_guard is NOT a sibling. The install
# dir — the symlink's own unresolved parent — is where store_guard.py actually lives, so
# insert it too, or a symlinked entrypoint crashes at import (Gloria, 2026-09-15).
_guard_link = _GuardPath(__file__).parent
_guard_sys.path.insert(0, str(_guard_here.parent / "scripts"))
_guard_sys.path.insert(0, str(_guard_here))
_guard_sys.path.insert(0, str(_guard_link))
from store_guard import serialized as _serialized
process_file=_serialized("LOG")(process_file)
direct=_serialized("LOG")(direct)
_landing_begin=_serialized("LOG")(_landing_begin)
_landing_done=_serialized("LOG")(_landing_done)

if __name__=="__main__":
    main()
    # Update daily creative log
    try:
        import subprocess as _dl_sp
        _dl_sp.Popen(["python3", os.path.join(os.path.dirname(__file__), "daily-log-extract.py"), "creative"],
            stdout=open("/tmp/daily-log.log", "a"), stderr=open("/tmp/daily-log.log", "a"))
    except: pass
