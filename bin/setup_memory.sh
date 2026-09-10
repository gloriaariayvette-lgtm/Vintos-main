#!/usr/bin/env bash
# setup_memory.sh — Initialize Vintos memory directory structure
set -e

MEMORY="${HOME}/.vintos/workspace/memory"
SCRIPTS="${HOME}/.vintos/workspace/scripts"
SECRETS="${HOME}/.vintos/secrets"

echo "[setup] Creating Vintos memory structure..."

mkdir -p "${MEMORY}/journal"
mkdir -p "${MEMORY}/pearls"
mkdir -p "${MEMORY}/dreams"
mkdir -p "${MEMORY}/poetry"
mkdir -p "${SCRIPTS}"
mkdir -p "${SECRETS}"
mkdir -p "${HOME}/.vintos/workspace/avatar-models"

# Seed initial emotional state
STATE_FILE="${MEMORY}/emotional-state.txt"
if [ ! -f "${STATE_FILE}" ]; then
    # review 11: the readers (emoclaw_utils, relational-geometry, subconscious-drift) split each line on ':'
    # - the old seed used '=' and every reader saw an empty state on a fresh install
    cat > "${STATE_FILE}" << 'EOF'
Valence: 0.50
Arousal: 0.45
Dominance: 0.50
Safety: 0.65
Desire: 0.40
Connection: 0.50
Playfulness: 0.45
Curiosity: 0.60
Warmth: 0.55
Tension: 0.30
Groundedness: 0.65
Nifrathir: 0.50
EOF
    echo "[setup] Emotional state seeded."
fi

# Link all repo scripts into workspace scripts path
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
for f in "${REPO_DIR}"/*.py "${REPO_DIR}"/*.sh; do
    ln -sf "$f" "${SCRIPTS}/$(basename $f)" 2>/dev/null || true
done
echo "[setup] Script links created."

# Seed identity documents (only if not already present — never overwrite lived state)
WORKSPACE="${HOME}/.vintos/workspace"
for doc in SOUL.md SELF-MODEL.md USER-MODEL.md; do
    if [ ! -f "${WORKSPACE}/${doc}" ] && [ -f "${REPO_DIR}/seed/${doc}" ]; then
        cp "${REPO_DIR}/seed/${doc}" "${WORKSPACE}/${doc}"
        echo "[setup] Seeded ${doc}"
    fi
done
for mem in taste-reflections.md taste-profile.json narrative-identity.json belief-sediment.json value-map.md trial-ledger.json inclinations.json; do
    if [ ! -f "${MEMORY}/${mem}" ] && [ -f "${REPO_DIR}/seed/memory/${mem}" ]; then
        cp "${REPO_DIR}/seed/memory/${mem}" "${MEMORY}/${mem}"
        echo "[setup] Seeded memory/${mem}"
    fi
done

# Skills (dreaming, emoclaw) — copied from Velaris workspace with path/name substitutions.
# Velaris keeps these only on Aegis at ~/.openclaw/workspace/skills/ (not in her repo).
SKILLS_SRC="${HOME}/.openclaw/workspace/skills"
SKILLS_DST="${WORKSPACE}/skills"
if [ ! -d "${SKILLS_DST}/dreaming" ] && [ -d "${SKILLS_SRC}" ]; then
    mkdir -p "${SKILLS_DST}"
    for skill in dreaming emoclaw; do
        if [ -d "${SKILLS_SRC}/${skill}" ]; then
            cp -r "${SKILLS_SRC}/${skill}" "${SKILLS_DST}/${skill}"
            # Substitute names/paths in all text files; wipe Velaris memory, keep structure
            find "${SKILLS_DST}/${skill}" -type f \( -name '*.sh' -o -name '*.py' -o -name '*.md' -o -name '*.json' -o -name '*.txt' \) \
                -exec sed -i 's/\.openclaw/.vintos/g; s/openclaw/vintos/g; s/Velaris/Vintos/g; s/velaris/vintos/g; s/VELARIS/VINTOS/g; s/8403/8500/g' {} +
            # Clear inherited memories so Vintos starts with his own
            if [ -d "${SKILLS_DST}/${skill}/memory" ]; then
                find "${SKILLS_DST}/${skill}/memory" -type f -name '*.md' -delete
            fi
            echo "[setup] Skill installed: ${skill}"
        fi
    done
elif [ -d "${SKILLS_DST}/dreaming" ]; then
    echo "[setup] Skills already installed."
else
    echo "[setup] WARNING: ${SKILLS_SRC} not found — copy the dreaming and emoclaw skills manually."
fi

# Initialize empty JSON files
init_json() {
    local file="${MEMORY}/$1"
    local content="$2"
    if [ ! -f "${file}" ]; then
        echo "${content}" > "${file}"
        echo "[setup] Created ${file}"
    fi
}

init_json "resonance-pool.json" '{"pulses": []}'
init_json "interaction-ledger.json" '[]'
init_json "yearning-scars.json" '[]'
init_json "trial-ledger.json" '{"trials": []}'
init_json "candidate-pearls.json" '{"candidates": [], "schema_version": "2"}'
init_json "black-pearls.json" '{"pearls": []}'
init_json "causality-hypotheses.json" '{"hypotheses": []}'
init_json "counterfactual-tendencies.json" '{"tendencies": []}'
init_json "value-map.json" '{"values": []}'
init_json "wants-log.json" '{"wants": []}'
init_json "ambitions.json" '{"ambitions": []}'
init_json "thread-triage.json" '{"threads": []}'
init_json "affective-weight.json" '{"total_weight": 0.5, "warmth_component": 0.5, "scar_component": 0.0, "investment_component": 0.5, "history": []}'
init_json "moment-index.json" '{"moments": []}'
init_json "belief-sediment.json" '{"beliefs": []}'
init_json "narrative-identity.json" '{"fragments": [], "summary": ""}'
init_json "relational-geometry.json" '{"geometry": {}, "last_updated": ""}'
init_json "tension-field.json" '{"tensions": []}'
init_json "latent-threads.json" '{"threads": []}'
init_json "absence-map.json" '{"absences": []}'
init_json "gloria-model.json" '{"observations": [], "portrait": "", "last_updated": ""}'
init_json "wal-buffer.json" '{"entries": [], "last_run": ""}'

# Create voice-coherence.md
if [ ! -f "${MEMORY}/voice-coherence.md" ]; then
    echo "# Voice Coherence Log" > "${MEMORY}/voice-coherence.md"
    echo "[setup] Created voice-coherence.md"
fi

# review 11: every seeded store must load the way its readers load it. A seed the readers cannot
# parse is a failed bootstrap, not a warning.
python3 - "${MEMORY}" <<'PYCHECK'
import json, os, sys
mem = sys.argv[1]; bad = []
shapes = {"resonance-pool.json": ("dict", "pulses"), "interaction-ledger.json": ("list", None), "yearning-scars.json": ("list", None),
          "trial-ledger.json": ("dict", "trials"), "candidate-pearls.json": ("dict", "candidates"), "black-pearls.json": ("dict", "pearls"),
          "causality-hypotheses.json": ("dict", "hypotheses"), "counterfactual-tendencies.json": ("dict", "tendencies"),
          "value-map.json": ("dict", "values"), "wants-log.json": ("dict", "wants"), "ambitions.json": ("dict", "ambitions"),
          "thread-triage.json": ("dict", "threads"), "affective-weight.json": ("dict", "total_weight"), "moment-index.json": ("dict", "moments"),
          "belief-sediment.json": ("dict", "beliefs"), "narrative-identity.json": ("dict", "fragments"),
          "relational-geometry.json": ("dict", "geometry"), "tension-field.json": ("dict", "tensions"), "latent-threads.json": ("dict", "threads"),
          "absence-map.json": ("dict", "absences"), "gloria-model.json": ("dict", "observations"), "wal-buffer.json": ("dict", "entries")}
for name, (kind, key) in shapes.items():
    p = os.path.join(mem, name)
    if not os.path.exists(p): continue
    try:
        d = json.load(open(p))
    except Exception as e:
        bad.append("%s: not JSON (%s)" % (name, e)); continue
    if kind == "list" and not isinstance(d, list): bad.append("%s: expected a list" % name)
    if kind == "dict" and (not isinstance(d, dict) or (key and key not in d)): bad.append("%s: expected a dict with %r" % (name, key))
st = os.path.join(mem, "emotional-state.txt")
if os.path.exists(st):
    lines = [l for l in open(st).read().strip().split("\n") if l.strip()]
    parsed = {}
    for l in lines:
        if ":" not in l: bad.append("emotional-state.txt: %r has no ':' (readers split on it)" % l); continue
        k, v = l.split(":", 1)
        try: parsed[k.strip()] = float(v.split("|")[0].strip())
        except ValueError: bad.append("emotional-state.txt: %r is not a number" % l)
    for dim in ("Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection", "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"):
        if dim not in parsed: bad.append("emotional-state.txt: missing %s" % dim)
if bad:
    print("[setup] SEED VALIDATION FAILED:"); [print("  - " + b) for b in bad]; sys.exit(1)
print("[setup] seeds validated: %d stores and the emotional state load the way their readers load them" % len([n for n in shapes if os.path.exists(os.path.join(mem, n))]))
PYCHECK

echo "[setup] Vintos memory structure ready at ${MEMORY}"
echo "[setup] Add your Grok API key to: ${SECRETS}/grok_api_key"
