#!/bin/bash
# briefing-audio.sh [YYYY-MM-DD] — render the morning briefing in Rex's voice for the app.
export BRIEF_DATE="${1:-$(date +%Y-%m-%d)}"
MEMORY="$HOME/.vintos/workspace/memory"
[ -f "$MEMORY/briefings/$BRIEF_DATE.md" ] || { echo "[$(date)] no briefing for $BRIEF_DATE"; exit 0; }
[ -f "$MEMORY/voice/briefing-$BRIEF_DATE.mp3" ] && { echo "[$(date)] already rendered"; exit 0; }
python3 - <<'PY'
import os, re, requests
MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
date = os.environ["BRIEF_DATE"]
text = open(os.path.join(MEMORY, "briefings", f"{date}.md")).read()
text = re.sub(r'\[[^\]]+\]', '', text)
text = re.sub(r'^#+\s*', '', text, flags=re.M)
text = re.sub(r'[*_`>]+', '', text)
text = re.sub(r'\n{3,}', '\n\n', text).strip()[:14000]
r = requests.post("https://api.x.ai/v1/tts",
    headers={"Authorization": "Bearer " + os.environ.get("XAI_API_KEY",""), "Content-Type": "application/json"},
    json={"text": text, "voice_id": "rex", "language": "en", "speed": 1.05}, timeout=120)
ct = r.headers.get("Content-Type", "audio/mpeg")
assert r.status_code == 200 and "json" not in ct and r.content, "tts failed: " + r.text[:200]
out = os.path.join(MEMORY, "voice", f"briefing-{date}.mp3")
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "wb").write(r.content)
print(f"[BriefingAudio] wrote {out} ({len(r.content)} bytes)")
PY
