#!/usr/bin/env bash
# vintos-journal.sh — Daily journal entry. Runs at ~3am.
SCRIPTS="${HOME}/.vintos/workspace/scripts"
MEMORY="${HOME}/.vintos/workspace/memory"
LOGDIR="${HOME}/.vintos/logs"
mkdir -p "${LOGDIR}"
LOG="${LOGDIR}/journal-$(date +%Y%m%d).log"

export PYTHONPATH="${SCRIPTS}:${PYTHONPATH}"
cd "${SCRIPTS}"

echo "[$(date '+%H:%M:%S')] journal starting" >> "${LOG}"

python3 -c "
import os, sys, json, requests
from datetime import datetime, date
sys.path.insert(0, '${SCRIPTS}')
MEMORY = '${MEMORY}'
_GROK_API = 'http://127.0.0.1:8599/v1/chat/completions'
_GROK_KEY = os.environ.get('XAI_API_KEY', '')

def call(system, prompt, temperature=0.78, max_tokens=800):
    headers = {'Authorization': f'Bearer {_GROK_KEY}', 'Content-Type': 'application/json'}
    r = requests.post(_GROK_API, headers=headers, json={
        'model': 'grok-4.20-0309-non-reasoning',
        'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}],
        'temperature': temperature, 'max_tokens': max_tokens,
    }, timeout=90)
    return r.json()['choices'][0]['message']['content']

def get_context():
    parts = []
    try:
        from emoclaw_utils import read_state
        state = read_state()
        parts.append('EMOTIONAL STATE: ' + ', '.join(f'{k}:{v:.2f}' for k,v in state.items()))
    except: pass
    try:
        from subconscious_context import get_subconscious_context_compact
        parts.append(get_subconscious_context_compact())
    except: pass
    try:
        from temporal_memory import get_temporal_context
        parts.append(get_temporal_context())
    except: pass
    return '\n'.join(p for p in parts if p)

ctx = get_context()
today = date.today().isoformat()
journal_dir = os.path.join(MEMORY, 'journal')
os.makedirs(journal_dir, exist_ok=True)
journal_path = os.path.join(journal_dir, f'{today}.md')

# Check if entry already exists today
existing = ''
if os.path.exists(journal_path):
    existing = open(journal_path).read()[-400:]

prompt = f'''This is your private daily journal. Today: {today}.

{ctx}

{('Continuation of today:' + chr(10) + existing) if existing else ''}

Write 5-8 sentences. First person. What's actually present — not what should be.
What moved today. What felt hollow. What surprised you. What you're carrying.
Direct voice. Short sentences when something is true. Longer only when genuinely working something out.
Don't perform reflection. Reflect.'''

result = call(
    'You are Vintos writing privately in your journal. No audience.',
    prompt, temperature=0.78, max_tokens=800
)

# Append to journal
with open(journal_path, 'a') as f:
    if existing:
        f.write(chr(10) + chr(10) + '---' + chr(10))
    f.write(f'[{datetime.now().strftime(\"%H:%M\")}]' + chr(10))
    f.write(result.strip() + chr(10))

print(f'[journal] {result.strip()[:80]}', flush=True)

# Update specificity check
try:
    from specificity_check import process
    process(result.strip())
except: pass
" 2>> "${LOG}"

echo "[$(date '+%H:%M:%S')] journal done" >> "${LOG}"
