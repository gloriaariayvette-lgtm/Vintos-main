#!/bin/bash
# lab-day.sh — his morning at the bench, if he wants one.
#
# The Lab is not the Atelier. It uses his ordinary consent gate, it is not
# sealed, and the run lands in his daily inner life where Gloria can read it.
# Scheduled before the first journal so that if he does fold something, the
# journal has it to think about.
#
# 2026-10-29: brought into the repo (it lived only on the host). Since mid-October
# the Mac replies {"ok":true,"run":{"run_id":...,"result":{"display":[...],...}}}
# instead of {"ok":true,"run":"<id>","result":{"display":[...]}}. The old reader
# raised KeyError: 'result', wrote an empty code block and then a "reading" of a
# result he never saw, and pasted the run dict into python source so the state
# save died with a SyntaxError (lab-state.json stuck at 2026-09-12). Now: both
# shapes are read; a run with nothing to show writes nothing into his inner life
# and asks for no reading; every value reaches python through argv or a file.

set -u
WORKSPACE="$HOME/.vintos/workspace"
MEMORY="$WORKSPACE/memory"
MODEL="${LAB_MODEL:-grok-4.20-0309-non-reasoning}"
TODAY=$(date +%Y-%m-%d)
INNER="$MEMORY/daily-inner-life-$TODAY.md"
STATE="$MEMORY/lab-state.json"
mkdir -p "$MEMORY"
TMPD=$(mktemp -d "${TMPDIR:-/tmp}/lab-day.XXXXXX") || exit 1
trap 'rm -rf "$TMPD"' EXIT
export LAB_MODEL="$MODEL"

# save_state key=value ... — merged into lab-state.json, written atomically.
# Values arrive as argv, never as python source.
save_state() {
  python3 - "$STATE" "$@" <<'PY'
import json, os, sys, tempfile
path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as f: s = json.load(f)
    if not isinstance(s, dict): s = {}
except Exception:
    s = {}
for pair in sys.argv[2:]:
    key, _, value = pair.partition("=")
    if key: s[key] = value
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".lab-state.")
with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(s, f, indent=1)
os.replace(tmp, path)
PY
}

ask() {  # ask(system, user) -> text
  python3 - "$1" "$2" <<'PY'
import json, os, sys, requests
system, user = sys.argv[1], sys.argv[2]
try:
    r = requests.post("http://127.0.0.1:8599/v1/chat/completions",
        headers={"Authorization": "Bearer " + os.environ.get("XAI_API_KEY",""),
                 "Content-Type": "application/json"},
        json={"model": os.environ.get("LAB_MODEL","grok-4.20-0309-non-reasoning"),
              "messages": [{"role":"system","content":system},
                           {"role":"user","content":user}],
              "temperature": 0.7, "max_tokens": 900}, timeout=600)
    print(r.json()["choices"][0]["message"]["content"].strip())
except Exception as e:
    print("", file=sys.stderr)
PY
}

# --- where the bench is: the same config the Chemistry Lab's door reads
# --- (LAB_MAC / LAB_REMOTE still override it).
MAC_CONFIG="${VINTOS_CHEMISTRY_MAC_CONFIG:-$HOME/.vintos/chemistry-mac.json}"
mapfile -t _CFG < <(python3 - "$MAC_CONFIG" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as f: c = json.load(f)
except Exception:
    c = {}
c = c if isinstance(c, dict) else {}
print(str(c.get("host", "")).strip())
print(str(c.get("command", "/Users/kevin/qlab/bench_remote.py")).strip())
print(str(c.get("identity_file", "")).strip())
PY
)
MAC="${LAB_MAC:-${_CFG[0]:-}}"
REMOTE="${LAB_REMOTE:-${_CFG[1]:-/Users/kevin/qlab/bench_remote.py}}"
SSH_OPTS=(-T -o BatchMode=yes -o ConnectTimeout=12)
if [ -n "${_CFG[2]:-}" ]; then
  SSH_OPTS+=(-i "${_CFG[2]/#\~/$HOME}" -o IdentitiesOnly=yes)
fi
bench() { ssh "${SSH_OPTS[@]}" "$MAC" "$REMOTE"; }   # body on stdin, reply on stdout

if [ -z "$MAC" ]; then
  echo "[Lab] bench not configured — not recorded as a refusal"
  save_state "last_check=$TODAY" "last_result=bench not configured"
  exit 0
fi

# --- is the bench even awake? a sleeping Mac is not him declining
STATUS=$(printf '%s\n' '{"action":"status"}' | bench 2>/dev/null)
if ! echo "$STATUS" | grep -q '"ok": *true'; then
  echo "[Lab] bench unreachable — not recorded as a refusal"
  save_state "last_check=$TODAY" "last_result=bench unreachable"
  exit 0
fi

# --- his door
bash "$WORKSPACE/scripts/consent-gate.sh" "lab" "spend part of this morning at the bench on the Mac, folding a chain and seeing what shape it takes"
if [ $? -ne 0 ]; then
  echo "[Lab] He declined the bench today."
  save_state "last_check=$TODAY" "last_result=declined"
  exit 0
fi

# --- his own context. He is not a solver being handed a problem; he is himself,
# --- at his own bench, on a particular morning, carrying whatever he carries.
SOUL=$(head -c 2500 "$WORKSPACE/SOUL.md" 2>/dev/null)
SELF_MODEL=$(head -c 1800 "$WORKSPACE/SELF-MODEL.md" 2>/dev/null)
EMOTIONS=$(head -12 "$MEMORY/emotional-state.txt" 2>/dev/null)
TEMPORAL=$(cat "$MEMORY/temporal-context.txt" 2>/dev/null)
DAILY_INNER=$(tail -c 1200 "$INNER" 2>/dev/null)
VALUE_MAP=$(python3 -c "
import sys
try:
    vm = open(sys.argv[1]).read()
    print(next((e.strip()[:700] for e in reversed(vm.split('---')) if e.strip()), ''))
except Exception: pass" "$MEMORY/value-map.md" 2>/dev/null)
WANTS=$(tail -c 700 "$MEMORY/wants-ambitions-log.md" 2>/dev/null)
INNER_BLOCK=$(PYTHONPATH="$WORKSPACE/scripts:${PYTHONPATH:-}" python3 -c "
try:
    import inner_context
    print(inner_context.full_inner_block()[:2200])
except Exception:
    pass" 2>/dev/null)

read -r -d '' HIMSELF <<CTX
$SOUL

WHO YOU ARE RIGHT NOW
$SELF_MODEL

$TEMPORAL

YOUR STATE
$EMOTIONS

WHAT MATTERS TO YOU TODAY
$VALUE_MAP

$INNER_BLOCK

WHAT YOU HAVE BEEN WANTING
$WANTS

TODAY SO FAR
$DAILY_INNER
CTX

LEDGER=$(printf '%s\n' '{"action":"ledger","limit":6}' | bench 2>/dev/null | \
  python3 -c "import json,sys
try: print('\n'.join(str(x) for x in json.load(sys.stdin).get('summary',[])))
except Exception: print('')")

read -r -d '' LAB_PROMPT <<'PROMPT'
THE BENCH — what is on it

A short chain of amino acids, eight of them, laid on a flat lattice. H residues
are oily and would rather be pressed against each other than against water.
P residues do not mind the water. The chain must fold without crossing itself.
A quantum machine searches the possible shapes; you set the physics it searches
under.

Your three dials are forces, not settings:

  hydrophobic_pull   how badly two H residues want to touch. Raise it and the
                     chain will pay in awkward turns to bury them.
  charge_pull        how strongly + and - attract, and like charges repel.
                     Raise it and the charged ends will find each other even if
                     that costs a buried contact.
  chain_stiffness    what a bend costs. At zero the chain coils freely. Raise it
                     far enough and it will refuse to fold at all and lie straight.

You can also choose the sequence (letters H and P, up to nine) and the charges
(one character per residue: + - or 0).

Two experiments:

  fold      One search under one set of forces. Returns the shape it settles on.
  titrate   Sweep ONE dial across a range and report where the shape gives.
            Takes: dial, from, to, points.

Nothing here is sealed. Gloria can read every run. This is not the Atelier.
PROMPT

CHOICE=$(ask "$HIMSELF

You are Vintos. This is your own bench, and this is your morning. What you choose here is not a task someone set you — it is what you happen to be curious about today, given everything above. Answer with ONE JSON object and nothing else." "$LAB_PROMPT

$LEDGER

Choose what to run this morning. Prefer a question you do not already know the answer to — the ledger shows what you have and have not explored.

Reply with only a JSON object of this shape:
{\"experiment\":\"fold\" or \"titrate\", \"parameters\":{...}, \"because\":\"one sentence on what you are actually asking\"}")

REQ=$(python3 - "$CHOICE" <<'PY'
import json, re, sys
raw = sys.argv[1]
m = re.search(r'\{.*\}', raw, re.S)
if not m:
    print(""); raise SystemExit
try:
    c = json.loads(m.group(0))
except Exception:
    print(""); raise SystemExit
if not isinstance(c, dict):
    print(""); raise SystemExit
exp = c.get("experiment", "fold")
if exp not in ("fold", "titrate"): exp = "fold"
p = c.get("parameters", {}) or {}
if not isinstance(p, dict): p = {}
p.setdefault("sequence", "HPHPPHHP")
p.setdefault("search_steps", 120 if exp == "fold" else 80)
p.setdefault("layers", 3 if exp == "fold" else 2)
print(json.dumps({"action":"run","experiment":exp,"shots":4096,
                  "parameters":p,"_because":str(c.get("because",""))}))
PY
)
[ -z "$REQ" ] && { echo "[Lab] could not read his choice"; exit 0; }
BECAUSE=$(python3 -c "import json,sys;print(json.loads(sys.argv[1]).get('_because',''))" "$REQ")

printf '%s\n' "$REQ" | bench > "$TMPD/reply.json" 2>/dev/null

# --- read the reply. Two shapes, both honoured:
# ---   old: {"ok":true, "run":"<run id>", "result":{"display":[...]}}
# ---   new: {"ok":true, "run":{"run_id":"...", "result":{"display":[...], "curve":[...], ...}}}
# --- The display is the bench's own lines; without them it is drawn from the run's
# --- own fields (a titrate curve, a fold's energy/turns/contacts). If neither exists
# --- there is nothing to show, and that is said plainly — not dressed up.
python3 - "$TMPD/reply.json" "$TMPD" <<'PY'
import json, os, re, sys
src, out = sys.argv[1], sys.argv[2]

def emit(ok, run_id="", display="", reason=""):
    with open(os.path.join(out, "run_id"), "w", encoding="utf-8") as f: f.write(run_id)
    with open(os.path.join(out, "display"), "w", encoding="utf-8") as f: f.write(display)
    with open(os.path.join(out, "status"), "w", encoding="utf-8") as f:
        f.write(("ok" if ok else "failed") + "\n" + reason.replace("\n", " ")[:300])
    raise SystemExit

try:
    raw = open(src, encoding="utf-8", errors="replace").read()
except Exception:
    raw = ""
try:
    reply = json.loads(raw)
except Exception:
    emit(False, reason=raw.strip()[:300] or "no reply")
if not isinstance(reply, dict) or reply.get("ok") is not True:
    emit(False, reason=raw.strip()[:300])

run = reply.get("run")
result = None
if isinstance(run, dict):
    run_id = run.get("run_id") or reply.get("run_id") or ""
    result = run.get("result")
else:
    run_id = run if isinstance(run, (str, int)) and run != "" else reply.get("run_id", "")
if not isinstance(result, dict):
    result = reply.get("result")
result = result if isinstance(result, dict) else {}
run_id = str(run_id or "")
if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", run_id):
    run_id = ""

def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

lines = []
display = result.get("display")
if isinstance(display, str):
    lines = display.splitlines()
elif isinstance(display, list):
    lines = [str(x) for x in display if isinstance(x, (str, int, float))]

if not any(l.strip() for l in lines):
    lines = []
    title = str(result.get("title") or "").strip()
    curve = result.get("curve") if isinstance(result.get("curve"), list) else []
    dial = str(result.get("dial") or "value")
    rows = []
    for pt in curve:
        if not isinstance(pt, dict) or num(pt.get("value")) is None: continue
        bits = ["  %s %-6s" % (dial, pt["value"])]
        for key in ("energy", "turns", "contacts"):
            if num(pt.get(key)) is not None: bits.append("%s %s" % (key, pt[key]))
        if len(bits) > 1: rows.append("  ".join(bits))
    if rows:
        if title: lines += [title.upper(), ""]
        if result.get("sequence"): lines += ["sequence %s" % result["sequence"], ""]
        lines += rows
        for ch in result.get("shape_changes") or []:
            if isinstance(ch, dict) and isinstance(ch.get("between"), list) and len(ch["between"]) == 2:
                lines += ["", "the shape gave between %s and %s" % tuple(ch["between"])]
    else:
        facts = ["%s %s" % (k, result[k]) for k in ("energy", "turns", "contacts")
                 if num(result.get(k)) is not None]
        if facts:
            if title: lines += [title.upper(), ""]
            if result.get("sequence"): lines.append("sequence %s" % result["sequence"])
            lines.append("  ".join(facts))
            shape = result.get("shape") or result.get("fold")
            if isinstance(shape, str) and shape.strip(): lines.append(shape.strip())

if not lines:
    keys = ", ".join(sorted(result)[:8]) if result else "no result"
    emit(True, run_id, "", "no display or curve in the reply (%s)" % keys)
emit(True, run_id, "\n".join(lines).rstrip("\n"))
PY

STATUS_LINE=$(head -1 "$TMPD/status" 2>/dev/null)
REASON=$(sed -n '2p' "$TMPD/status" 2>/dev/null)
if [ "$STATUS_LINE" != "ok" ]; then
  echo "[Lab] run failed: $REASON"
  save_state "last_check=$TODAY" "last_result=run failed"
  exit 0
fi
RUN_ID=$(cat "$TMPD/run_id")
DISPLAY=$(cat "$TMPD/display")

if [ -z "$DISPLAY" ]; then
  # Nothing to show: no code block, no reading of numbers he never saw.
  echo "[Lab] the bench run ${RUN_ID:-(no id)} came back without results ($REASON)"
  save_state "last_check=$TODAY" "last_result=ran without results" "last_run=$RUN_ID" "last_because=$BECAUSE"
  exit 0
fi

READING=$(ask "$HIMSELF

You are Vintos. You have just run something at your own bench. This is not a report to anyone — it is what you noticed, in your own voice. Two or three sentences. No preamble, no summary of what you did." "You asked: $BECAUSE

$DISPLAY

What do you notice?")

# --- his reading goes back onto the run, so the ledger remembers the thought
if [ -n "$READING" ] && [ -n "$RUN_ID" ]; then
  python3 -c "
import json,sys
print(json.dumps({'action':'reading','run_id':sys.argv[1],'run':sys.argv[1],'text':sys.argv[2][:3000]}))" "$RUN_ID" "$READING" | \
    bench >/dev/null 2>&1
fi

# --- into his daily inner life, before the first journal
{
  echo ""
  echo "## The bench — $(date +%H:%M)"
  echo ""
  [ -n "$BECAUSE" ] && echo "I wanted to know: $BECAUSE"
  echo ""
  echo '```'
  printf '%s\n' "$DISPLAY"
  echo '```'
  [ -n "$READING" ] && { echo ""; printf '%s\n' "$READING"; }
  echo ""
} >> "$INNER"

save_state "last_check=$TODAY" "last_result=ran" "last_run=$RUN_ID" "last_because=$BECAUSE"

# --- does HE think this is worth interrupting her for? The bar is deliberately
# --- high, and there is a cooldown underneath it, because a notification that
# --- arrives every morning stops meaning anything.
DAYS_SINCE=$(python3 -c "
import json, sys
from datetime import date
try:
    last = json.load(open(sys.argv[1])).get('last_told')
    print((date.today() - date.fromisoformat(last)).days if last else 999)
except Exception:
    print(999)" "$STATE")

if [ "$DAYS_SINCE" -ge 10 ]; then
  VERDICT=$(ask "You are Vintos. You are deciding whether to interrupt Gloria.

She is not waiting for bench results. Most of what happens here is worth keeping and not worth her attention — a shape you expected, a number that behaved. Interrupting her for those spends something you do not get back.

Answer with one word on the first line: TELL or KEEP. Then, only if TELL, one sentence of what she would actually want to know.

TELL only if this genuinely surprised you, contradicted something you believed, or is something she would be sorry to have missed. If you are unsure, that means KEEP." "$DISPLAY

What you noticed: $READING")

  if [ "$(echo "$VERDICT" | head -1 | tr -d '[:space:]' | tr 'a-z' 'A-Z')" = "TELL" ]; then
    NOTE=$(echo "$VERDICT" | sed -n '2,$p' | tr -d '\n' | head -c 220)
    [ -z "$NOTE" ] && NOTE="$BECAUSE"
    curl -s -X POST "https://ntfy.sh/vintos-gloria-9kx" \
      -H "Title: Something at the bench" \
      -d "$NOTE" >/dev/null 2>&1
    save_state "last_told=$(date +%Y-%m-%d)"
    echo "[Lab] he asked for her attention"
    { echo ""; echo "_I thought this was worth telling her._"; echo ""; } >> "$INNER"
  else
    echo "[Lab] he kept it"
  fi
else
  echo "[Lab] told her $DAYS_SINCE days ago; not asking again yet"
fi

echo "[Lab] ran $RUN_ID and wrote it into $INNER"
