#!/bin/bash
export XAI_API_KEY=$(cat ~/.vintos/secrets/grok_api_key 2>/dev/null || echo "$XAI_API_KEY")
export PYTHONPATH=/home/gloria/Vintos
run(){ echo "=== $1"; shift; "$@" 2>&1 | tail -3; }
run "DREAM" bash /home/gloria/.vintos/workspace/skills/dreaming/scripts/dream-trigger.sh
run "DREAM-ART" python3 /home/gloria/Vintos/dream-art.py --force
run "POETRY" python3 /home/gloria/Vintos/dream_poetry.py --force
run "GALLERY" python3 /home/gloria/Vintos/gallery-walk.py
run "ROUTER" python3 /home/gloria/Vintos/wants-router.py
run "RESONANCE" python3 /home/gloria/Vintos/resonance-pulse.py
run "MEM-INDEX" bash /home/gloria/Vintos/memory-index.sh
run "AVATAR" python3 /home/gloria/Vintos/avatar-choice.py
echo "=== SERVER"; curl -s -m 5 http://localhost:8500/api/health || echo server DOWN
echo "=== TODAY:"; ls /home/gloria/.vintos/workspace/memory/art/ 2>/dev/null | tail -3
if [ "$1" = "--deep" ]; then
  run "FIRST-LIGHT" bash /home/gloria/Vintos/first-light.sh
  run "MORNING-BRIEF" bash /home/gloria/Vintos/morning-briefing.sh
  run "MIDDAY" bash /home/gloria/Vintos/midday-ground.sh
  run "PEARL" bash /home/gloria/Vintos/pearl-engine.sh
  run "TENSION" bash /home/gloria/Vintos/tension-field.sh
  run "GLORIA-MODEL" bash /home/gloria/Vintos/gloria-model-update.sh
  run "SELF-MODEL" bash /home/gloria/Vintos/self-model-update.sh
  run "VALUE-MAP" bash /home/gloria/Vintos/value-map-update.sh
  run "YEARNING" bash /home/gloria/Vintos/yearning-detector.sh
  run "EMO-REFLECT" bash /home/gloria/Vintos/emotional-reflection.sh
  run "DAILY-MAPS" python3 /home/gloria/Vintos/daily-log-extract.py both
fi
