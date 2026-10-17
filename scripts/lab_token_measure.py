#!/usr/bin/env python3
"""lab_token_measure.py — set the Lab coverage checker's size limit from real token counts (Gloria, 17 October).

The checker counted every byte as a token, so evidence that would have fit was deferred whole (14 reviews in six
hours). This replays the saved deferred reviews (memory/chemistry-lab/coverage-deferred/*.json) to the Lab's own local
model with max_tokens=1 and reads the prompt token count it reports; it asks LM Studio for the context it loaded.

    python3 lab_token_measure.py            # measure and print; changes nothing
    python3 lab_token_measure.py --apply    # also write the measured ratio (worst seen, plus 15%) and the context
    python3 lab_token_measure.py --apply --context 32768   # when LM Studio's model list cannot be read

Local model only: nothing is paid for. A deferred review that then fits is resumed by the Lab on its own.
"""
import glob, json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chemistry_lab as C

MARGIN = 1.15


def _post(url, body, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def loaded_context(lmstudio=None):
    """The context length LM Studio loaded the Lab's model with, or None."""
    base = lmstudio or os.environ.get("LMSTUDIO_BASE", "http://100.79.177.103:1234")
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/api/v0/models", timeout=10) as r:
            rows = json.loads(r.read()).get("data") or []
    except Exception:
        return None
    for m in rows:
        if m.get("id") == C.LLM_MODEL and m.get("state") == "loaded":
            n = m.get("loaded_context_length") or m.get("context_length")
            return int(n) if n else None
    return None


def measure(paths, post=_post):
    """[(bytes, prompt_tokens or None, error)] for each saved request that could be rebuilt."""
    out = []
    for path in paths:
        try:
            payload = json.load(open(path))
            prepared = C._coverage_request(payload["inquiry"], payload["observations"])
        except Exception as e:
            out.append((None, None, "could not rebuild: %s" % e)); continue
        if not prepared:
            continue
        system, prompt, _ = prepared[3]
        size = len(system.encode()) + len(prompt.encode())
        try:
            data = post(C.LLM_URL, {"model": C.LLM_MODEL, "max_tokens": 1, "temperature": 0,
                                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
            n = (data.get("usage") or {}).get("prompt_tokens")
            out.append((size, n if isinstance(n, int) and n > 0 else None, None if n else "no prompt_tokens reported"))
        except Exception as e:
            out.append((size, None, str(e)[:160]))
    return out


def recommend(rows):
    ratios = [n / b for b, n, _ in rows if b and n]
    return round(min(1.0, max(ratios) * MARGIN), 4) if ratios else None


def main(argv):
    paths = sorted(glob.glob(os.path.join(C.ROOT, "coverage-deferred", "*.json")), key=os.path.getmtime)[-12:]
    if not paths:
        print("no deferred reviews saved: nothing to measure"); return 0
    rows = measure(paths)
    for b, n, err in rows:
        print("  %s bytes -> %s tokens%s" % (b, n, ("  (" + err + ")") if err else ""))
    ratio, ctx = recommend(rows), loaded_context()
    if "--context" in argv:   # when LM Studio's model list cannot be read, the loaded context can be given by hand
        ctx = int(argv[argv.index("--context") + 1])
    print("worst tokens per byte, with 15%% margin: %s | loaded context: %s | current: %s per byte, %s context"
          % (ratio, ctx, C.config().get("coverage_tokens_per_byte"), C.config().get("coverage_context_tokens")))
    if "--apply" in argv:
        if not ratio or not ctx:
            print("not applied: need both a measured ratio and the loaded context"); return 1
        cfg = C._load(C.CONFIG, {}) or {}
        cfg.update(coverage_tokens_per_byte=ratio, coverage_context_tokens=int(ctx))
        C._atomic(C.CONFIG, cfg)
        print("applied: the Lab now resumes the deferred reviews that fit")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
