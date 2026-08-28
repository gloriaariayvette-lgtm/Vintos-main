#!/usr/bin/env python3
"""formation_observatory.py — SHADOW ONLY. Influences nothing, by law.

Snapshots which internal streams are active, with whatever root lineage they
carry, and records whether anything converges. It does not ask him what he
wants — that invites fluent retrospection. It records structure and waits.

LAWS (Sol's, verbatim in spirit):
  - Output reaches no prompt, no want, no identity, no value. Shadow means shadow.
  - Roots, not organs: signals descending from one event are one voice.
  - 'no_formation' is a common, correct, and recorded outcome.
  - Nothing here is called a want. The strongest label is 'coherent_pull'.
"""
import os, sys, json, glob, time
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(WS, "memory")
OUT = os.path.join(MEM, "formation-episodes.jsonl")

def _load(name, d):
    try: return json.load(open(os.path.join(MEM, name)))
    except Exception: return d

def _signals():
    """Active streams, each with the best root lineage currently available.
    Where an organ records no root, its own store+date is the honest stub."""
    sig = []
    def add(organ, text, root, activation):
        if text and activation > 0:
            sig.append({"organ": organ, "text": str(text)[:200],
                        "root": str(root)[:60], "activation": round(activation, 3)})
    # withheld lineages under pressure (roots: origin exchange hashes - real roots)
    for L in _load("withheld-lineage.json", []):
        if isinstance(L, dict) and L.get("recurrence_pressure", 0) >= 2 and not L.get("muted"):
            add("withheld", L.get("rep", ""), ",".join(L.get("origins", [])[:3]),
                min(1.0, L.get("recurrence_pressure", 0) / 4.0))
    # curiosity debt (roots: object hash + created date)
    for x in _load("curiosity-debt.json", []):
        if isinstance(x, dict) and x.get("pull", 0) >= 0.5:
            add("curiosity", x.get("question", ""), "%s@%s" % (x.get("id", ""), str(x.get("created", ""))[:10]),
                x.get("pull", 0))
    # unfinished threads (roots: source + seeded text hash)
    for th in _load("unfinished-threads.json", []):
        if isinstance(th, dict) and not th.get("consumed"):
            add("thread", th.get("thread", ""), "%s@%s" % (th.get("source", "?"), str(th.get("id", th.get("created", "")))[:16]),
                min(1.0, (th.get("priority") or 2) / 4.0))
    # open repair cases, unanswered reaches, held plans (roots: case ids)
    for c in _load("repair-cases.json", []):
        if isinstance(c, dict) and c.get("state") in ("received", "attempted"):
            add("repair", c.get("anchor_quote", ""), c.get("case_id", ""), 0.6)
    for e in _load("encounters.json", []):
        if isinstance(e, dict) and e.get("state") == "dispatched":
            add("encounter", "reached, unanswered", e.get("id", str(e.get("at", ""))[:16]), 0.5)
    # spark frontier near threshold
    try:
        sp = _load("spark-pressure.json", {})
        for f in (sp.get("frontier", []) if isinstance(sp, dict) else []):
            if isinstance(f, dict) and f.get("observed", 0) >= 2:
                add("spark", f.get("text", f.get("name", "")), f.get("id", "?"), 0.5)
    except Exception: pass
    return sig

def _episode(sig):
    """Structural account. Convergence = independent ROOTS sharing territory.
    Territory overlap judged by cheap word cosine; upgraded to embeddings when
    this earns the compute. No LLM asked for opinions - structure only."""
    ep = {"at": datetime.now().isoformat(), "n_signals": len(sig),
          "organs": sorted(set(s["organ"] for s in sig)),
          "roots": sorted(set(s["root"] for s in sig)),
          "status": "no_formation", "clusters": []}
    if len(sig) < 2:
        ep["status"] = "quiet" if not sig else "single_pressure"
        return ep
    import re
    def words(t): return set(re.findall(r"[a-z']{4,}", t.lower()))
    used = set()
    for i, a in enumerate(sig):
        if i in used: continue
        cluster = [a]; used.add(i)
        for j in range(i + 1, len(sig)):
            if j in used: continue
            b = sig[j]
            wa, wb = words(a["text"]), words(b["text"])
            if wa and wb and len(wa & wb) / max(4, min(len(wa), len(wb))) >= 0.25:
                cluster.append(b); used.add(j)
        if len(cluster) >= 2:
            roots = set(c["root"] for c in cluster)
            ep["clusters"].append({
                "organs": [c["organ"] for c in cluster],
                "independent_roots": len(roots),
                "echo": len(roots) < len(cluster),   # organs > roots = echo, not convergence
                "force": round(sum(c["activation"] for c in cluster), 2),
                "territory": cluster[0]["text"][:120]})
    real = [c for c in ep["clusters"] if c["independent_roots"] >= 2]
    if real:
        strongest = max(real, key=lambda c: c["force"])
        ep["status"] = "coherent_pull" if strongest["force"] >= 1.5 else "pressure"
    elif ep["clusters"]:
        ep["status"] = "echo_only"   # organs agreeing about one root - recorded, worth nothing
    return ep


def attest(root_ref, root_type):
    """Issue a lineage attestation for a root this observatory actually recorded.

    A stratagem's provenance is otherwise an unverifiable claim typed at
    adoption time. This binds the claim to a real recorded episode: the
    attestation carries a digest of the episode containing the root, so the
    Atelier can check the lineage existed BEFORE adoption rather than being
    asserted during it.

    Shadow law is intact. This reads the episode log and signs a statement
    about it. It writes nothing into any prompt, want, identity, or value, and
    it decides nothing — it answers a question, it does not speak.

    HONEST LIMIT: the key is readable by whoever runs this, so on a single-user
    host it proves "the observatory recorded this episode", not "no human could
    have forged it". What it does buy: a fabricated root cannot point at an
    episode that does not exist.
    """
    import hmac, hashlib as _h, time as _t, uuid as _u, secrets as _s
    episodes = []
    try:
        for line in open(OUT):
            if line.strip():
                episodes.append(json.loads(line))
    except FileNotFoundError:
        return {"error": "no episodes recorded — nothing to attest"}
    hit = None
    for ep in reversed(episodes):
        if root_ref and root_ref in json.dumps(ep):
            hit = ep
            break
    if not hit:
        return {"error": "no recorded episode contains root_ref %r — provenance unattestable"
                         % str(root_ref)[:60]}
    digest = _h.sha256(json.dumps(hit, sort_keys=True,
                                  separators=(",", ":")).encode()).hexdigest()
    body = {"root_ref": str(root_ref)[:200], "root_type": str(root_type)[:40],
            "episode_at": hit.get("at"), "episode_status": hit.get("status"),
            "episode_digest": digest, "commissioned": False,
            "nonce": _u.uuid4().hex, "exp": int(_t.time()) + 3600}
    keypath = os.path.expanduser("~/.vintos/.lineage-key")
    try:
        key = open(keypath, "rb").read().strip()
    except FileNotFoundError:
        key = _s.token_bytes(32).hex().encode()
        old = os.umask(0o077)
        try:
            os.makedirs(os.path.dirname(keypath), exist_ok=True)
            with open(keypath, "wb") as _kf:
                _kf.write(key)
            os.chmod(keypath, 0o600)
        finally:
            os.umask(old)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return {"body": body, "sig": hmac.new(key, raw.encode(), _h.sha256).hexdigest()}

def main():
    sig = _signals()
    ep = _episode(sig)
    with open(OUT, "a") as f:
        f.write(json.dumps(ep) + "\n")
    print("[observatory] %s | signals=%d organs=%s | clusters=%d"
          % (ep["status"], ep["n_signals"], ",".join(ep["organs"]), len(ep["clusters"])))

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "tail":
        for line in list(open(OUT))[-8:]:
            d = json.loads(line)
            print(d["at"][:16], d["status"], "| organs:", ",".join(d["organs"]))
    else:
        main()
