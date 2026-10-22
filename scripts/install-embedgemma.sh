#!/usr/bin/env bash
# EmbeddingGemma 2 for his media index (scripts/media_embed.py), in a venv of its own so his torch venv (emotion
# model, JEPA) is never upgraded under him. CPU, float32. Gloria runs this once on Aegis; it is safe to run again.
#   bash ~/Vintos-main/scripts/install-embedgemma.sh
# It: makes ~/.vintos/tools/embedgemma-venv, installs CPU torch + sentence-transformers, downloads the model
# (about 1.5 GB), proves it on one text and one work of each kind he has, then indexes a first batch and adds an
# every-two-hours cron line for the rest. Nothing of nomic's is touched.
set -euo pipefail
VENV="$HOME/.vintos/tools/embedgemma-venv"
SCRIPT="$HOME/.vintos/workspace/scripts/media_embed.py"
[ -f "$SCRIPT" ] || { echo "media_embed.py is not installed yet: deploy first"; exit 1; }
command -v ffmpeg >/dev/null || echo "note: no ffmpeg; music is embedded from the file's start only (sudo apt-get install -y ffmpeg)"
mkdir -p "$(dirname "$VENV")"
[ -x "$VENV/bin/python3" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q --index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio "torchcodec>=0.16"   # torchcodec: video decoding (22 October: torchvision can no longer read video)
"$VENV/bin/pip" install -q --upgrade "transformers>=5" "sentence-transformers>=5" av soundfile librosa pillow
echo "== proving it =="
"$VENV/bin/python3" - "$SCRIPT" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("media_embed", sys.argv[1]); M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
enc = M.model_encoder()
print("text:", len(enc(M.QUERY % "a red sky over water")), "dims")
works = M.works()
for kind in ("image", "video", "audio"):
    one = next((p for p in works if M.kind_of(p) == kind), None)
    if not one:
        print(kind + ": none of his to try"); continue
    try:
        print(kind + ":", len(M.embed_work(one, enc)), "dims  (" + one.rsplit("/", 1)[-1] + ")")
    except Exception as e:
        print(kind + ": FAILED -", type(e).__name__, str(e)[:200])
PY
echo "== first batch =="
nice -n 15 "$VENV/bin/python3" "$SCRIPT" index --limit 20
LINE="23 */2 * * * nice -n 15 $VENV/bin/python3 $SCRIPT index >> /tmp/media-embed.log 2>&1"
if crontab -l 2>/dev/null | grep -qF "media_embed.py index"; then
    echo "cron: already scheduled"
else
    (crontab -l 2>/dev/null; echo "$LINE") | crontab - && echo "cron: every two hours, at :23"
fi
# the service his chats and journal ask (the text half of the model, about 1 GB of memory), kept running by cron
SERVE="*/10 * * * * python3 $SCRIPT ensure >> /tmp/media-embed.log 2>&1"
crontab -l 2>/dev/null | grep -qF "media_embed.py ensure" || { (crontab -l 2>/dev/null; echo "$SERVE") | crontab - && echo "cron: service kept up, checked every ten minutes"; }
python3 "$SCRIPT" ensure; sleep 45
python3 "$SCRIPT" near "a red sky over the water" --k 3
python3 "$SCRIPT" status
