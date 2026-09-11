import json, os
from datetime import datetime

import sys, copy, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
from store_guard import serialized, transactions, write_json, compare_and_swap

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
OBS_PATH = os.path.join(MEMORY, "causal-observations.json")

def load_observations():
    try:
        return json.load(open(OBS_PATH))
    except:
        return {"observations": []}

def save_observations(data):
    write_json(OBS_PATH, data)

@serialized("OBS_PATH")
def add_observation(dimension, direction, delta, context_snippet, source="causality-engine"):
    data = load_observations()
    data["observations"].append({
        "id": "CO-" + uuid.uuid4().hex,
        "timestamp": datetime.now().isoformat(),
        "dimension": dimension,
        "direction": direction,
        "delta": round(abs(delta), 4),
        "context": context_snippet[:300],
        "source": source,
        "clustered": False
    })
    # Keep last 200 observations
    data["observations"] = data["observations"][-200:]
    save_observations(data)

if __name__ == "__main__":
    # Initialize file if needed
    if not os.path.exists(OBS_PATH):
        compare_and_swap(OBS_PATH, None, {"observations": []})
        print("Initialized causal-observations.json")
    else:
        data = load_observations()
        print(f"Observations: {len(data['observations'])}")
