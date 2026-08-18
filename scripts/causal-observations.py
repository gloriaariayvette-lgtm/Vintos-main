import json, os
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
OBS_PATH = os.path.join(MEMORY, "causal-observations.json")

def load_observations():
    try:
        return json.load(open(OBS_PATH))
    except:
        return {"observations": []}

def save_observations(data):
    with open(OBS_PATH, "w") as f:
        json.dump(data, f, indent=2)

def add_observation(dimension, direction, delta, context_snippet, source="causality-engine"):
    data = load_observations()
    data["observations"].append({
        "id": datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{dimension[:4]}",
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
        save_observations({"observations": []})
        print("Initialized causal-observations.json")
    else:
        data = load_observations()
        print(f"Observations: {len(data['observations'])}")
