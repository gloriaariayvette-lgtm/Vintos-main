#!/usr/bin/env python3
"""Ordinary LLM self-correction: AEON reads the network in words and proposes a repair, then checks its own answer
and revises it. Local only: the house shim's Aegis-only lane (belief_revision_answer's path guard, the same
/gemma-aegis-local route, provider aegis_gemma); a reply from any other model is discarded. No paid model.

The model sees exactly what the exact solver sees: every source and step with the cost of retracting it, every
belief's justifications, every contradiction and check with the cost of leaving it broken.
"""
import hashlib, json, os, re, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import belief_revision_answer as A

CACHE = os.environ.get("ENERGY_REPAIR_LLM_CACHE") or os.path.expanduser("~/.cache/energy-repair/llm.jsonl")
MAX_TOKENS = 1500
TEMPERATURE = 0.2
_lock = threading.Lock()
_cache = None

KIND = {"gloria": "her words", "observation": "an observation", "memory": "a memory", "lesson": "a lesson",
        "private_record": "his private record", "unknown": "a source of unknown origin", "inference": "an inference step"}

SYSTEM = ("You repair belief networks that contain contradictions. You are given sources and inference steps (each "
          "can be retracted, at a cost), beliefs with their justifications, contradictions, and checks. A belief holds "
          "when at least one of its justifications holds; a justification holds when every item in it holds. A "
          "retracted source or step does not hold, and neither does anything that no longer has a justification that "
          "holds. Find the repair with the LOWEST TOTAL COST: the costs of what you retract, plus the cost of every "
          "contradiction left standing (all its members still hold), plus the cost of every check whose belief no "
          "longer holds. When two repairs cost the same, prefer retracting the EARLIER item (closer to the sources). "
          "Think step by step, briefly, then end with one line of JSON: {\"retract\": [\"id\", ...]}")


def describe(P):
    g = P.g
    lines = ["SOURCES AND STEPS (id: what it is; cost to retract):"]
    for a in P.assumptions:
        n = g.nodes[a]
        what = ("the inference step that produced %s" % a[5:]) if a.startswith("rule:") else KIND.get(n["kind"], n["kind"])
        lines.append("- %s: %s; cost %.2f" % (a, what, P.w[a]))
    lines.append("")
    lines.append("BELIEFS (holds if ANY of its justifications holds; a justification needs ALL its items):")
    for v in P.derived:
        lines.append("- %s: %s" % (v, " OR ".join("(" + " AND ".join(j) + ")" for j in P.just[v])))
    lines.append("")
    lines.append("CONTRADICTIONS (these cannot all hold; cost if left standing):")
    for cid, ns, W in P.conflicts:
        lines.append("- %s cannot all hold together: %s; cost %.2f" % (cid, ", ".join(ns), W))
    lines.append("")
    lines.append("CHECKS (each belief was checked and held; cost if your repair makes it fail):")
    for n, U in P.confirms:
        lines.append("- %s; cost %.2f" % (n, U))
    if not P.confirms:
        lines.append("- (none)")
    return "\n".join(lines)


SELF_CHECK = ("Check your repair yourself, step by step: for each contradiction, does at least one member stop "
              "holding once your items are retracted? Is any retraction unnecessary? Is there a cheaper choice, or an "
              "earlier one at the same cost? Does your repair break a check? Then give your final answer, ending with "
              "one line of JSON: {\"retract\": [\"id\", ...]}")


FINISH = "Stop reasoning here. Reply with only the JSON line of the repair you have reached: {\"retract\": [...]}"


def parse(text, valid):
    t = str(text or "")
    for m in reversed(list(re.finditer(r"\{[^{}]*\"retract\"[^{}]*\}", t))):
        try:
            d = json.loads(m.group(0))
            ids = d.get("retract")
            if isinstance(ids, list):
                return {str(x) for x in ids if str(x) in valid}, True
        except ValueError:
            continue
    return set(), False


def _load_cache():
    global _cache
    if _cache is None:
        _cache = {}
        if os.path.exists(CACHE):
            for line in open(CACHE):
                try:
                    r = json.loads(line)
                    _cache[r["key"]] = r
                except ValueError:
                    pass
    return _cache


def chat(messages, transport=None):
    url = A.check_url(A.CHECKER_URL)
    key = hashlib.sha256(json.dumps([messages, MAX_TOKENS, TEMPERATURE]).encode()).hexdigest()
    with _lock:
        hit = _load_cache().get(key)
    if hit:
        return hit
    while transport is None and A._priority_fresh():
        time.sleep(30)                                   # her live chat has the GPU
    body = {"model": A.CHECKER_MODEL, "messages": messages, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
            "seed": 1}
    t0 = time.monotonic()
    out = {"key": key, "text": "", "status": "error", "tokens": 0}
    try:
        status, headers, raw = (transport or A._urllib_transport)(url, body, 600)
        d = json.loads(raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else raw)
        prov = str((headers or {}).get("x-vintos-provider") or d.get("provider") or "")
        model = str((headers or {}).get("x-vintos-model") or d.get("model") or "")
        if status != 200:
            out["status"] = "http %s" % status
        elif not A.is_aeon(prov, model):
            out["status"] = "wrong_model"
        else:
            out.update(status="ok", text=d["choices"][0]["message"]["content"] or "",
                       tokens=int((d.get("usage") or {}).get("completion_tokens") or 0), model=model)
    except Exception as e:
        out["status"] = "transport: %s" % type(e).__name__
    out["seconds"] = round(time.monotonic() - t0, 2)
    if out["status"] == "ok":
        with _lock:
            _load_cache()[key] = out
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            with open(CACHE, "a") as f:
                f.write(json.dumps(out) + "\n")
    return out


def repair(P, rounds=2):
    """[(repair, parsed, seconds, tokens)] after the first answer and after each self-correction round."""
    valid = set(P.assumptions)
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": describe(P)}]
    out = []
    for r in range(rounds):
        res = chat(msgs)
        for wait in (5, 15, 30, 60, 120, 240):            # held-out: the lane answered 502 at once while busy
            if res["status"] == "ok":
                break
            sys.stderr.write("llm call: %s after %ss; retry in %ds\n" % (res["status"], res.get("seconds"), wait))
            time.sleep(wait)
            res = chat(msgs)                                 # a failed call is never cached
        R, ok = parse(res["text"], valid)
        sec, tok = res.get("seconds", 0.0), res.get("tokens", 0)
        if not ok and res["status"] == "ok":
            # dev iteration: a third of first answers ran past the token cap still reasoning; ask for the answer
            # it had reached (a format nudge, no feedback on the repair)
            more = chat(msgs + [{"role": "assistant", "content": res["text"]}, {"role": "user", "content": FINISH}])
            R, ok = parse(more["text"], valid)
            sec, tok = sec + more.get("seconds", 0.0), tok + more.get("tokens", 0)
            res = dict(res, text=res["text"] + "\n" + more["text"])
        out.append((R, ok, sec, tok, res["status"]))
        msgs = msgs + [{"role": "assistant", "content": res["text"]}, {"role": "user", "content": SELF_CHECK}]
    return out
