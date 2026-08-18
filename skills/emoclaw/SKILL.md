---
name: emoclaw
description: "Give your AI emotions that grow from its own memories. Emoclaw builds a unique emotional state that shifts with every conversation, decays between sessions, and evolves over time through self-calibration. Train it on your agent's identity files and watch it develop its own emotional fingerprint."
metadata: {"clawdbot": {"emoji": "\ud83e\udec0"}}
---

# Emotion Skill

Emotions for AI agents — built from memories, shaped by relationships, always changing.

Emoclaw trains a lightweight model on your agent's identity and conversation history, producing a persistent emotional state that evolves with every interaction. Emotions decay naturally between sessions, shift based on who's talking and what's being said, and gradually recalibrate as your agent grows. The result is injected into the system prompt as an `[EMOTIONAL STATE]` block, giving your AI a felt sense of its own inner life.

## Quick Reference

| Situation | Action |
|-----------|--------|
| First-time setup | `python scripts/setup.py` (or manual steps below) |
| Check current state | `python -m emotion_model.scripts.status` |
| Inject state into prompt | `python -m emotion_model.scripts.inject_state` |
| Start the daemon | `bash scripts/daemon.sh start` |
| Send a message to daemon | See [Daemon Protocol](#daemon-protocol) |
| Retrain after new data | `python -m emotion_model.scripts.train` |
| Resume interrupted training | `python -m emotion_model.scripts.train --resume` |
| Add new training data | Add `.jsonl` entries to `emotion_model/data/`, re-run prepare + train |
| Upgrade from v0.1 | See `references/upgrading.md` |
| Change baselines | Edit `emoclaw.yaml` → `dimensions[].baseline` |
| Add a new channel | Edit `emoclaw.yaml` → `channels` list |
| Add a relationship | Edit `emoclaw.yaml` → `relationships.known` |
| Customize summaries | Create a `summary-templates.yaml` and point config at it |

## Setup

### Quick Setup

```bash
python skills/emoclaw/scripts/setup.py
```

This copies the bundled `emotion_model` engine to your project root, creates a venv, installs the package, and copies the config template. Then edit `emoclaw.yaml` to customize for your agent.

### Manual Setup

If you prefer to set up manually:

#### 1. Install the package

```bash
cd <project-root>
python3 -m venv emotion_model/.venv
source emotion_model/.venv/bin/activate
pip install -e emotion_model/
```

Required: Python 3.10+, PyTorch, sentence-transformers, PyYAML.

#### 2. Copy and customize the config

```bash
cp skills/emoclaw/assets/emoclaw.yaml ./emoclaw.yaml
```

Edit `emoclaw.yaml` to set:
- `name` — your agent's name
- `dimensions` — emotional dimensions with baselines and decay rates
- `relationships.known` — map of relationship names to embedding indices
- `channels` — communication channels your agent uses
- `longing` — absence-based desire growth (can be disabled)
- `model.device` — `cpu` recommended (MPS has issues with sentence-transformers)

See `references/config-reference.md` for the full schema.

### 3. Bootstrap (new agent)

If starting from scratch with identity/memory files:

```bash
# Extract passages from your identity files
python scripts/extract.py

# Auto-label passages using Claude API (requires ANTHROPIC_API_KEY)
python scripts/label.py

# Prepare train/val split and train
python -m emotion_model.scripts.prepare_dataset
python -m emotion_model.scripts.train
```

Or run the full pipeline:

```bash
python scripts/bootstrap.py
```

### 4. Verify

```bash
python -m emotion_model.scripts.status
python -m emotion_model.scripts.diagnose
```

## Usage

### Option A: Daemon (Recommended)

The daemon loads the model once and listens on a Unix socket, avoiding the ~2s sentence-transformer load time per message.

```bash
# Start
bash scripts/daemon.sh start

# Or directly
python -m emotion_model.daemon
python -m emotion_model.daemon --config path/to/emoclaw.yaml
```

### Option B: Direct Python Import

```python
from emotion_model.inference import EmotionEngine

engine = EmotionEngine(
    model_path="emotion_model/checkpoints/best_model.pt",
    state_path="memory/emotional-state.json",
)

block = engine.process_message(
    message_text="Good morning!",
    sender="alice",        # or None for config default
    channel="chat",        # or None for config default
    recent_context="...",  # optional conversation context
)
print(block)
```

### Option C: One-shot State Injection

For system prompt injection without the daemon:

```bash
python -m emotion_model.scripts.inject_state
```

This reads the persisted state, applies time-based decay, and outputs the `[EMOTIONAL STATE]` block.

## Integration

### System Prompt Injection

Add the output block to your system prompt. The block format:

```
[EMOTIONAL STATE]
Valence: 0.55 (balanced)
Arousal: 0.35 (balanced)
Dominance: 0.50 (balanced)
Safety: 0.70 (open)
Desire: 0.20 (neutral)
Connection: 0.50 (balanced)
Playfulness: 0.40 (balanced)
Curiosity: 0.50 (balanced)
Warmth: 0.45 (balanced)
Tension: 0.20 (relaxed)
Groundedness: 0.60 (balanced)

This feels like: present, alive, between one thing and the next
[/EMOTIONAL STATE]
```

### Daemon Protocol

Send JSON over the Unix socket:

```json
{"text": "Good morning!", "sender": "alice", "channel": "chat"}
```

Special commands:
```json
{"command": "ping"}
{"command": "state"}
```

### Heartbeat Integration

Call the daemon or `inject_state` script from your heartbeat/cron to keep the state block fresh:

```bash
# In your heartbeat script
STATE_BLOCK=$(python -m emotion_model.scripts.inject_state 2>/dev/null)
# Inject $STATE_BLOCK into system prompt
```

## Architecture

The model processes each message through this pipeline:

```
Message Text ──→ [Frozen MiniLM Encoder] ──→ 384-dim embedding
                                                    │
Conversation Context ──→ [Feature Builder] ──→ context vector
                                                    │
Previous Emotion ──────────────────────────→ emotion vector
                                                    │
                                            ┌───────┴───────┐
                                            │ Input Project  │
                                            │ (Linear+LN+GELU)│
                                            └───────┬───────┘
                                                    │
                                            ┌───────┴───────┐
                                            │     GRU       │
                                            │ (hidden state) │ ← emotional residue
                                            └───────┬───────┘
                                                    │
                                            ┌───────┴───────┐
                                            │ Emotion Head  │
                                            │ (MLP+Sigmoid) │
                                            └───────┬───────┘
                                                    │
                                            N-dim emotion vector [0,1]
```

The GRU hidden state persists across sessions — this is the "emotional residue" that carries forward mood, context, and relational memory.

See `references/architecture.md` for full details.

## Configuration

All configuration lives in `emoclaw.yaml`. The package falls back to built-in defaults if no YAML is found.

Config search order:
1. `EMOCLAW_CONFIG` environment variable
2. `./emoclaw.yaml` (project root)
3. `./skills/emoclaw/emoclaw.yaml`

Key sections:
- `dimensions` — name, labels, baseline, decay half-life, loss weight
- `relationships` — known senders with embedding indices
- `channels` — communication channels (determines context vector size)
- `longing` — absence-based desire modulation
- `model` — architecture hyperparameters
- `training` — training hyperparameters
- `calibration` — self-calibrating baseline drift (opt-in)

See `references/config-reference.md` for the complete schema.

## Bootstrap Pipeline

### Step 1: Extract Passages

`scripts/extract.py` reads identity and memory files, splitting them into labeled passages:

```bash
python scripts/extract.py
# Output: emotion_model/data/extracted_passages.jsonl
```

Source files are configured in `emoclaw.yaml` → `bootstrap.source_files` and `bootstrap.memory_patterns`.

### Step 2: Auto-Label

`scripts/label.py` uses the Claude API to score each passage on every emotion dimension:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/label.py
# Output: emotion_model/data/passage_labels.jsonl
```

Each passage gets a 0.0-1.0 score per dimension plus a natural language summary.

### Step 3: Prepare & Train

```bash
python -m emotion_model.scripts.prepare_dataset
python -m emotion_model.scripts.train
```

## Retraining

To add new training data:

1. Add entries to `emotion_model/data/` in JSONL format:
   ```json
   {"text": "message text", "labels": {"valence": 0.7, "arousal": 0.4, ...}}
   ```
2. Re-run the preparation and training:
   ```bash
   python -m emotion_model.scripts.prepare_dataset
   python -m emotion_model.scripts.train
   ```

### Incremental Retraining

The training script saves a rich checkpoint (`training_checkpoint.pt`) that preserves the full optimizer state, learning rate schedule, and early stopping counter. To continue training from where you left off:

```bash
# Resume from the last checkpoint automatically
python -m emotion_model.scripts.train --resume

# Or specify a checkpoint file
python -m emotion_model.scripts.train --resume emotion_model/checkpoints/training_checkpoint.pt
```

This is a true continuation — optimizer momentum, cosine annealing position, and patience counter all pick up exactly where they stopped.

## Growth Model

As the AI accumulates real conversation data:

1. **Passive collection** — Log messages + model predictions
2. **Correction events** — When emotion feels wrong, log the correction
3. **Periodic retraining** — Incorporate new data, retrain
4. **Baseline adjustment** — Baselines may shift as the AI develops

The system is designed to grow with the AI, not remain static.

## Resources

- `references/architecture.md` — Model architecture deep-dive
- `references/config-reference.md` — Full YAML config schema
- `references/dimensions.md` — Emotion dimension documentation
- `references/calibration-guide.md` — Baseline, decay, and self-calibration tuning
- `references/upgrading.md` — Version upgrade guide
- `assets/emoclaw.yaml` — Template config for new AIs
- `assets/summary-templates.yaml` — Generic summary templates
- `assets/example-summary-templates.yaml` — Example personality-specific templates
- `engine/` — Bundled `emotion_model` Python package (copied to project root by setup.py)
