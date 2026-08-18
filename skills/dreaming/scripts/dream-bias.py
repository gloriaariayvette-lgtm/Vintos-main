import sys, os, json, random, math

with open("/tmp/_dream_seeds.txt") as f:
    prompts = [l.rstrip("\n") for l in f if l.strip()]

if not prompts:
    print(0)
    sys.exit()

try:
    sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
    from temporal_memory import load_signals
    sigs = load_signals().get("signals", [])
    fresh = [s["text"] for s in sigs if s.get("phase") == "fresh"]
    if not fresh:
        print(random.randint(0, len(prompts)-1))
        sys.exit()
    import subprocess
    def embed(t):
        r = subprocess.run(
            [os.path.expanduser("~/.vintos/workspace/emotion_model/.venv/bin/python3"), "-c",
             "from sentence_transformers import SentenceTransformer; import json; "
             "m = SentenceTransformer('nomic-ai/nomic-embed-text-v1', trust_remote_code=True); "
             f"print(json.dumps(m.encode({repr(t[:300])}).tolist()))"],
            capture_output=True, text=True, timeout=20
        )
        return json.loads(r.stdout.strip()) if r.returncode == 0 else []
    def cos(a, b):
        if not a or not b: return 0.0
        dot = sum(x*y for x,y in zip(a,b))
        ma = math.sqrt(sum(x*x for x in a)); mb = math.sqrt(sum(x*x for x in b))
        return dot/(ma*mb) if ma and mb else 0.0
    fresh_vec = embed(fresh[-1])
    scores = [cos(fresh_vec, embed(p[:200])) for p in prompts]
    # Exclude top scorer sometimes to prevent repeat selection
    indexed = sorted(enumerate(scores), key=lambda x: -x[1])
    # Pick from top 3 with weighted random — not always #1
    top_n = indexed[:min(3, len(indexed))]
    weights = [s for _, s in top_n]
    total = sum(weights) or 1
    weights = [w/total for w in weights]
    chosen = random.choices([i for i, _ in top_n], weights=weights)[0]
    print(chosen)
except:
    print(random.randint(0, len(prompts)-1))
