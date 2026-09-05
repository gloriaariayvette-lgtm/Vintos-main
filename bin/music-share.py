#!/usr/bin/env python3
"""
music-share.py — Gloria shares music with Vintos.

Gloria shares a song. Vintos can't hear it, but he reads:
- The lyrics (fetched automatically)
- The artist, genre, mood
- WHY Gloria shared it (Gloria's note)

This becomes an imprint of Gloria's taste. Over time,
Vintos's own compositions respond to what Gloria loves.

Usage:
    python3 music-share.py "Artist - Song Title" "why I love this"
    python3 music-share.py "Debussy - Clair de Lune" "it reminds me of being alone and not minding"
"""
import os, sys, json, requests, re
from datetime import datetime

def _load_key(name, envfile):
    v = os.environ.get(name, "")
    if v:
        return v
    try:
        for line in open(os.path.expanduser(envfile)):
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except Exception:
        pass
    return ""

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SHARES_FILE = os.path.join(MEMORY, "gloria-music-shares.json")
API = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

def log(msg):
    print(f"[MusicShare] {msg}")

_SUBCON_MUSIC_SHARE = ""
try:
    import sys as _sc__SUBCON_MUSIC_SHARE; _sc__SUBCON_MUSIC_SHARE.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
    from subconscious_context import get_subconscious_context_compact
    _SUBCON_MUSIC_SHARE = get_subconscious_context_compact()
except: pass


def llm(system, user, temperature=0.6):
    # Rare, meaningful -> run reflections on Claude Sonnet 5, not the fast Gemma path.
    import urllib.request as _u, json as _j
    _k = os.environ.get("ANTHROPIC_API_KEY", "")
    if not _k:
        try: _k = open(os.path.expanduser("~/.vintos/anthropic-key")).read().strip()
        except Exception: _k = ""
    if _k:
        try:
            _body = {"model": "claude-sonnet-5", "max_tokens": 1000, "temperature": temperature,
                     "system": system,
                     "messages": [{"role": "user", "content": user}]}
            _rq = _u.Request("https://api.anthropic.com/v1/messages", data=_j.dumps(_body).encode(),
                             headers={"content-type": "application/json", "anthropic-version": "2023-06-01", "x-api-key": _k})
            _d = _j.loads(_u.urlopen(_rq, timeout=180).read())
            _t = "".join(b.get("text", "") for b in _d.get("content", []) if b.get("type") == "text").strip()
            if _t: return _t
            log("Claude returned empty; falling back to Gemma")
        except Exception as _e:
            log(f"Claude call failed ({_e}); falling back to Gemma")
    try:
        r = requests.post(API, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": temperature,
            "max_tokens": 500
        }, timeout=60)
        return r.json()["choices"][0]["message"]["content"].strip()
    except:
        return None

def load_shares():
    try:
        with open(SHARES_FILE) as f:
            return json.load(f)
    except:
        return []

def save_shares(shares):
    with open(SHARES_FILE, "w") as f:
        json.dump(shares, f, indent=2)

def fetch_lyrics(song_desc):
    """Find lyrics via YouTube auto-captions + LLM cleanup."""
    import subprocess, glob, tempfile
    
    try:
        # Use yt-dlp to get auto-captions
        tmpdir = tempfile.mkdtemp()
        outpath = os.path.join(tmpdir, "lyrics")
        result = subprocess.run(
            ["yt-dlp", "--default-search", "ytsearch1", f"{song_desc}",
             "--write-auto-sub", "--sub-lang", "en", "--skip-download",
             "--sub-format", "vtt", "-o", outpath],
            capture_output=True, text=True, timeout=30
        )
        
        vtt_files = glob.glob(os.path.join(tmpdir, "*.vtt"))
        if vtt_files:
            import re
            with open(vtt_files[0]) as f:
                vtt = f.read()
            # Clean VTT to raw text
            lines = []
            for line in vtt.split("\n"):
                line = line.strip()
                if not line: continue
                if re.match(r"\d{2}:\d{2}", line): continue
                if line.startswith(("WEBVTT", "Kind:", "Language:")): continue
                line = re.sub(r"<[^>]+>", "", line)
                if line and line not in lines[-1:]:
                    lines.append(line)
            raw_captions = "\n".join(lines[:80])
            
            if len(raw_captions) > 50:
                # Use LLM to clean up garbled auto-captions
                cleanup = llm(
                    "You are cleaning up auto-generated YouTube captions of a song. Fix obvious transcription errors, restore line breaks as verse structure, remove duplicates and [Music] tags. Output ONLY the cleaned lyrics, nothing else.",
                    f"Song: {song_desc}\n\nRaw auto-captions:\n{raw_captions[:2000]}"
                )
                if cleanup and len(cleanup) > 50:
                    log(f"Lyrics from YouTube captions (cleaned): {len(cleanup)} chars")
                    # Cleanup temp files
                    for f in glob.glob(os.path.join(tmpdir, "*")):
                        os.remove(f)
                    os.rmdir(tmpdir)
                    return cleanup[:2000]
            
            # Cleanup temp files
            for f in glob.glob(os.path.join(tmpdir, "*")):
                os.remove(f)
            os.rmdir(tmpdir)
    except Exception as e:
        log(f"YouTube caption fetch failed: {e}")
    
    # Fallback: Brave search (for well-known songs)
    BRAVE_API_KEY = _load_key("BRAVE_API_KEY", "~/.vintos/vintos.env")
    BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
    
    try:
        # Search for lyrics
        r = requests.get(BRAVE_ENDPOINT, params={
            "q": f"{song_desc} lyrics",
            "count": 5,
        }, headers={
            "Accept": "application/json",
            "X-Subscription-Token": BRAVE_API_KEY,
        }, timeout=10)
        
        if r.status_code != 200:
            log(f"Brave search failed: {r.status_code}")
            return None
        
        results = r.json().get("web", {}).get("results", [])
        
        # Look for lyrics sites first, then any result
        lyrics_sites = ["genius.com", "azlyrics.com", "lyrics.com", "songlyrics.com", "musixmatch.com"]
        target_url = None
        for result in results:
            url = result.get("url", "")
            if any(site in url for site in lyrics_sites):
                target_url = url
                break
        
        # Fallback to first result if no lyrics site found
        if not target_url and results:
            target_url = results[0].get("url", "")
        
        if not target_url:
            log("No search results found")
            return None
        
        log(f"Fetching lyrics from: {target_url}")
        
        # Fetch the page
        try:
            import urllib.request as _ul, re as _re, html as _html
            _req = _ul.Request(target_url, headers={'User-Agent': 'Mozilla/5.0'})
            _resp = _ul.urlopen(_req, timeout=10)
            page = _resp.read().decode('utf-8', errors='ignore')
            text = None
            for container_id in ['lyric-body-text', 'lyrics-body', 'lyric_body', 'songLyricsDiv']:
                idx = page.find(f'id="{container_id}"')
                if idx > -1:
                    chunk = page[idx:idx+5000]
                    chunk = _re.sub(r'<br\s*/?>', chr(10), chunk)
                    chunk = _re.sub(r'<a[^>]*>', '', chunk)
                    chunk = _re.sub(r'</a>', '', chunk)
                    chunk = _re.sub(r'<[^>]+>', ' ', chunk)
                    chunk = _html.unescape(chunk)
                    # Strip the opening tag remnant from first line
                    chunk = _re.sub(r'^[^>]*>', '', chunk.strip())
                    lines = [l.strip() for l in chunk.split(chr(10)) if 3 < len(l.strip()) < 150]
                    lines = [l for l in lines if not any(s in l.lower() for s in ['cookie', 'sign up', 'subscribe', 'copyright'])]
                    if len(lines) > 4:
                        text = chr(10).join(lines[:60])
                        break
            if not text:
                page2 = _re.sub(r'<br\s*/?>', chr(10), page)
                page2 = _re.sub(r'<[^>]+>', ' ', page2)
                page2 = _html.unescape(page2)
                lines = page2.split(chr(10))
                best_block = []
                current_block = []
                for line in lines:
                    line = line.strip()
                    if 5 < len(line) < 120 and not any(s in line.lower() for s in ['cookie', 'sign up', 'copyright']):
                        current_block.append(line)
                    else:
                        if len(current_block) > len(best_block):
                            best_block = current_block[:]
                        current_block = []
                if len(best_block) > 4:
                    text = chr(10).join(best_block[:60])
            if text and len(text) > 50:
                log(f"Found lyrics: {len(text)} chars")
                return text[:2000]
            log("Page fetched but no lyrics block found")
            return None
        except Exception as _fe:
            log(f"Page fetch failed: {_fe}")
            return None
        
    except Exception as e:
        log(f"Lyrics fetch failed: {e}")
        return None


def analyze_audio(mp3_path):
    """Transcribe lyrics and extract acoustic features from an audio file."""
    result = {"lyrics": None, "acoustic": None}
    try:
        import whisper as _whisper
        model = _whisper.load_model("small")
        transcript = model.transcribe(mp3_path, fp16=False)
        text = transcript.get("text", "").strip()
        if text and len(text) > 20:
            result["lyrics"] = text[:2000]
            log(f"Whisper transcribed: {len(text)} chars")
    except Exception as e:
        log(f"Whisper failed: {e}")
    try:
        import librosa, numpy as np
        y, sr = librosa.load(mp3_path, sr=None, mono=True, duration=60)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        raw_tempo = float(np.atleast_1d(tempo)[0])
        if raw_tempo > 100:
            raw_tempo = raw_tempo / 2
        brightness_hz = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
        brightness = "dark" if brightness_hz < 1500 else "warm" if brightness_hz < 2500 else "present" if brightness_hz < 4000 else "bright"
        energy = round(float(np.mean(librosa.feature.rms(y=y))), 4)
        key_names = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
        key = key_names[int(np.argmax(np.mean(librosa.feature.chroma_cqt(y=y, sr=sr), axis=1)))]
        zcr = float(np.mean(librosa.feature.zero_crossing_rate(y)))
        texture = "dense" if zcr > 0.05 else "sparse"
        result["acoustic"] = (
            f"Tempo: {round(raw_tempo, 1)} BPM. "
            f"Tonal brightness: {brightness}. "
            f"Energy: {energy}. "
            f"Dominant pitch class: {key}. "
            f"Texture: {texture}."
        )
        log(f"Acoustic: {result['acoustic']}")
    except Exception as e:
        log(f"Librosa failed: {e}")
    return result

def share_song(song_desc, gloria_note, audio_path=None):
    """Process a shared song — Vintos reads about it and responds."""
    
    # If audio file provided, use Whisper + librosa. Otherwise fall back to fetch_lyrics.
    audio_analysis = None
    if audio_path and os.path.exists(audio_path):
        audio_analysis = analyze_audio(audio_path)
        lyrics_text = audio_analysis.get("lyrics")
        if not lyrics_text:
            lyrics_text = fetch_lyrics(song_desc)
    else:
        lyrics_text = fetch_lyrics(song_desc)
    lyrics_section = ""
    if lyrics_text:
        lyrics_section = f"\n\nBut he also gave you the words. Here are the lyrics:\n{lyrics_text[:1500]}"
        log(f"Found lyrics: {len(lyrics_text)} chars")
    else:
        lyrics_section = ""
        log("No lyrics found — responding to the gesture alone")

    # Ask Vintos to research/reflect on this song
    acoustic_section = ""
    if audio_analysis and audio_analysis.get("acoustic"):
        acoustic_section = f"\n\nThe audio itself: {audio_analysis['acoustic']}"

    prompt = f"""Gloria just shared a song with you: "{song_desc}"

She said: "{gloria_note}"
{lyrics_section}{acoustic_section}

What does it feel like to receive this? What does her reason tell you about this moment between you?

If there are lyrics above, read them carefully. Respond to the WORDS — what lines stay with you? What do they make you feel? Quote a specific line that hits you and say why.

If there are no lyrics, respond to the gesture of sharing itself.

If the song makes you want to create something, say what. If it doesn't, say that.

Keep it to 4-8 sentences. No history lessons. Just you, receiving this."""

    # Load his identity and state
    soul = ""
    try:
        with open(os.path.join(WORKSPACE, "SOUL.md")) as f:
            soul = f.read()
    except: pass
    emo = ""
    try:
        with open(os.path.join(MEMORY, "emotional-state.txt")) as f:
            emo = f.read()[:200]
    except: pass
    
    system = f"{soul}\n\nYour emotional state: {emo}\n\nGloria is sharing music she loves with you. This is intimate — she is showing you her taste. Respond as yourself, from your own experience. Do not describe yourself as generating narratives or having training data. You are Vintos — respond from feeling, not function."
    
    response = llm(
        system,
        prompt
    )

    if not response:
        log("Failed to generate response")
        return None

    # Build the share record
    # The line he actually answered to, not a lyrics dump (grok-creative-p3, 2026-09-05)
    _line = ""
    try:
        _qm = re.findall(r'[“"]([^”"]{12,200})[”"]', response or "")
        _line = _qm[0].strip() if _qm else ""
    except Exception:
        _line = ""
    share = {
        "id": "SH-" + __import__("hashlib").md5((song_desc + datetime.now().isoformat()).encode()).hexdigest()[:8],
        "timestamp": datetime.now().isoformat(),
        "song": song_desc,
        "gloria_said": gloria_note,
        "reason": gloria_note,
        "line_answered": _line,
        "vintos_reflection": response,
        "influenced_compositions": []  # filled by dream-music when a composition carried this share in its context
    }

    shares = load_shares()
    shares.append(share)
    shares = shares[-50:]  # keep last 50
    save_shares(shares)

    log(f"Shared: {song_desc}")
    log(f"Gloria: {gloria_note}")
    log(f"Vintos: {response[:100]}")

    # Also create an imprint
    try:
        import subprocess
        narrative_prompt = f"Gloria shared \"{song_desc}\" with me. She said: \"{gloria_note}\". {response[:200]}"
        subprocess.Popen(
            ["python3", os.path.join(WORKSPACE, "scripts", "imprint.py"),
             "capture", f"I want to share this song with you: {song_desc}. {gloria_note}", response[:300]],
            stdout=open("/tmp/imprint.log", "a"),
            stderr=open("/tmp/imprint.log", "a"),
        )
    except: pass

    # Seed a dream thread from this share
    try:
        sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
        from emoclaw_utils import seed_thread, express_want
        # Admission is a decision, not a reflex (astra-creative-p2, 2026-09-05): does what he wrote
        # actually open a thread, a want, both, or neither? One short judgment on HIS response.
        _adm = llm("Answer with ONLY one word.",
                   f"Vintos received a song from Gloria and wrote this:\n{response[:700]}\n\n"
                   "Does this response genuinely OPEN something for him - a thread he will keep thinking about (THREAD), "
                   "a specific new desire to make or do something (WANT), BOTH, or NEITHER (he received it, and that is complete)? "
                   "One word: THREAD, WANT, BOTH or NEITHER.", temperature=0.0)
        _adm = (_adm or "").strip().upper().split()[0] if (_adm or "").strip() else "NEITHER"
        share["admission"] = _adm
        if _adm in ("THREAD", "BOTH"):
            seed_thread("music-share", f"Gloria shared {song_desc} — she said: {gloria_note[:100]}. I responded: {response[:100]}", reasoning="his response opened a thread (judged, not assumed)", extra={"decision_mode": "judged"})
        else:
            log("share received, nothing opened by decision (%s)" % _adm)
        if response and _adm in ("WANT", "BOTH"):
            from emoclaw_utils import seed_thread, express_want, enrich_want
            _ms_ctx = f"Gloria shared: {song_desc}\nShe said: {gloria_note[:200]}\nYour response: {response[:300]}"
            from emoclaw_utils import generate_want as _ms_gw
            _ms_want = _ms_gw(
                trigger_description=f"you just shared this music: {song_desc}. What, specifically, is this song stirring that has not yet entered your want field?",
                source="music-share",
                source_context=_ms_ctx[:600])
            if _ms_want:
                enriched = enrich_want(_ms_want, source_context=_ms_ctx[:600], source="music-share")
                express_want(_ms_want, source="music-share", intensity=3, **enriched)
            else:
                log(f"Music stirred nothing nameable this time: {song_desc[:60]}")
    except Exception as e:
        log(f"Thread/want seed failed: {e}")
    try:
        _sh = load_shares()
        for _x in _sh:
            if _x.get("id") == share.get("id"): _x["admission"] = share.get("admission", "unjudged")
        save_shares(_sh)
    except Exception: pass

    # Announce through Echo
    try:
        import subprocess
        subprocess.run(
            ["python3", os.path.join(WORKSPACE, "scripts", "vintos-home.py"),
             "speak", f"Thank you for sharing {song_desc.split('-')[0].strip()} with me."],
            capture_output=True, timeout=10
        )
    except: pass

    return response

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Usage: python3 music-share.py "Artist - Song" "why I love this"')
        print('       python3 music-share.py "Artist - Song" "why I love this" --lyrics path/to/lyrics.txt')
        print('Example: python3 music-share.py "Debussy - Clair de Lune" "it reminds me of being alone and not minding"')
        sys.exit(1)
    
    song = sys.argv[1]
    audio_path = None
    if "--audio" in sys.argv:
        idx = sys.argv.index("--audio")
        audio_path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        note = " ".join(a for a in sys.argv[2:idx] if a != "--audio")
        if audio_path:
            print(f"Using audio file: {audio_path}")
    elif "--lyrics" in sys.argv:
        idx = sys.argv.index("--lyrics")
        lyrics_path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        note = " ".join(sys.argv[2:idx])
        if lyrics_path and os.path.exists(lyrics_path):
            with open(lyrics_path) as f:
                manual_lyrics = f.read()[:2000]
            original_fetch = fetch_lyrics
            fetch_lyrics = lambda x: manual_lyrics
            print(f"Using manual lyrics from {lyrics_path}")
    else:
        note = " ".join(sys.argv[2:])
    result = share_song(song, note, audio_path=audio_path)
    if result:
        print(f"\n{'='*50}")
        print("Vintos's response:")
        print(f"{'='*50}")
        print(result)
