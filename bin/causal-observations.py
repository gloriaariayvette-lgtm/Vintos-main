import json, os
from datetime import datetime

def _sg_write(_p, _o, _who="organ"):
    """review 46: this store has more than one writing organ; the write goes through the store lock."""
    try:
        import sys as _s, os as _o2
        _s.path.insert(0, _o2.path.dirname(_o2.path.abspath(__file__)))
        _s.path.insert(0, _o2.path.expanduser("~/.vintos/workspace/scripts"))
        from store_guard import write_json as _wj
        _wj(_p, _o, reader=_who); return True
    except Exception:
        return False


MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
OBS_PATH = os.path.join(MEMORY, "causal-observations.json")

def load_observations():
    try:
        return json.load(open(OBS_PATH))
    except:
        return {"observations": []}

def save_observations(data):
    if not _sg_write(OBS_PATH, data, "causal-observations"):
            raise RuntimeError("observation store write refused")

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
