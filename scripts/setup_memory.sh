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
    cat > "${STATE_FILE}" << 'EOF'
Valence=0.50
Arousal=0.45
Dominance=0.50
Safety=0.65
Desire=0.40
Connection=0.50
Playfulness=0.45
Curiosity=0.60
Warmth=0.55
Tension=0.30
Groundedness=0.65
Nifrathir=0.50
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

echo "[setup] Vintos memory structure ready at ${MEMORY}"
echo "[setup] Add your Grok API key to: ${SECRETS}/grok_api_key"
