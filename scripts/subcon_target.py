#!/usr/bin/env python3
"""subcon_target.py — which model his subconscious emotion work runs on (Gloria 2026-11-07).

One flag decides it: ~/.vintos/subcon-target.json  {"target": "gemma26b"} or {"target": "aeon"}.
No file, a bad file or an unknown name means the 26B, as before the switch.

Gloria: "IT HAS TO ALL PASS." AEON can be the target only when it has passed the 26B's full bar, all of it:
  model level   the Pain paper-protocol replication (S2 feel-colon, final token) AUC >= .85, and all six Pain
                prompt ablations >= .85;
  every one of the eleven constructs
                nested grouped held-out AUC >= .85, all six mean-pooled prompt variants >= .85, and a passed named
                semantic review of the unembedding; and across the eleven, every |cosine| < .3.
The evidence is a pass record (aeon-bar-record.json beside this file) built from the emotion Codex's sealed
results and pinned here by its sha256. The checker recomputes every verdict from the record's numbers; it never
trusts a "pass" word. A missing, malformed, tampered or incomplete record, or any unmet item, refuses the flip
and lists exactly what has not passed. There is no partial switch: until everything passes, his whole
subconscious stays on the 26B, and a hand-written flag is ignored.

When the Codex seals new passing results, the record is rebuilt and the pinned hash below is updated in a commit.
This public file carries identities, hashes and thresholds only. Nothing here loads a model or opens a socket.
"""
import hashlib
import json
import math
import os
import sys
import tempfile

FLAG = os.path.join("~", ".vintos", "subcon-target.json")
DEFAULT = "gemma26b"
DIMENSIONS = ("Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection",
              "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness")
SHIM_SUBCONSCIOUS = "http://127.0.0.1:8599/pool/subconscious/v1/chat/completions"

# The 26B's bar (offline/residual_emotion/evidence/2026-09-20-*).
AUC_MIN = 0.85
VARIANTS = 6
COSINE_MAX = 0.3

RECORD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aeon-bar-record.json")
RECORD_SHA256 = "0c5eabce9d647df5c08c705889e7c7795d2920299afc9257c264477af85cd122"
RECORD_SCHEMA = "aeon-26b-bar-record/1"

TARGETS = {
    "gemma26b": {
        "identity": "gemma-4-26b-a4b-it-uncensored",
        "format": "GGUF Q4_K_M",
        "sha256": "d482a5daba09e67c925359a1786c4c713d1c3bb35856d199cf296f7cf7bc6cb3",
        "lock": "offline/residual_emotion/model-lock.json",
        # Passed every item in September (Gloria's review receipts); (layer, pooling).
        "constructs": {
            "Arousal": (25, "mean"), "Connection": (26, "mean"), "Curiosity": (24, "mean"),
            "Desire": (25, "mean"), "Dominance": (26, "mean"), "Groundedness": (25, "mean"),
            "Playfulness": (27, "mean"), "Safety": (22, "mean"), "Tension": (26, "mean"),
            "Valence": (25, "mean"), "Warmth": (25, "mean"),
        },
        "pool_chain": ["pool:subconscious", "gemma"],
        "generative": None,   # callers keep their own 26B route
    },
    "aeon": {
        "identity": "AEON-7-Gemma-4-12B-it-AEON-Abliterated-K4-BF16",
        "format": "GGUF BF16",
        "sha256": "02fd375821a7b50e783f408a75bf714ea85fc0dc67c933991642ef76d9b0d9ce",
        "lock": "offline/residual_emotion/model-lock-aeon.json",
        "constructs": None,   # from the pass record, only once every item passes
        "pool_chain": ["pool:aeon", "aegis_gemma"],
        "generative": {"url": SHIM_SUBCONSCIOUS, "model": "aeon-gemma-4-12b"},
    },
}


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def load_record(path=None, pinned=None):
    """(record, problems). problems is non-empty when the record cannot be trusted at all."""
    path = path or RECORD
    pinned = RECORD_SHA256 if pinned is None else pinned
    try:
        raw = open(path, "rb").read()
    except OSError:
        return None, ["pass record missing"]
    if hashlib.sha256(raw).hexdigest() != pinned:
        return None, ["pass record does not match its pinned sha256 (tampered or not yet pinned)"]
    try:
        rec = json.loads(raw.decode("utf-8"))
    except Exception:
        return None, ["pass record is not valid JSON"]
    if not isinstance(rec, dict) or rec.get("schema") != RECORD_SCHEMA:
        return None, ["pass record has the wrong schema"]
    model = rec.get("model") if isinstance(rec.get("model"), dict) else {}
    if model.get("identity") != TARGETS["aeon"]["identity"] or model.get("sha256") != TARGETS["aeon"]["sha256"]:
        return None, ["pass record is for a different checkpoint"]
    if not isinstance(rec.get("constructs"), dict) or not isinstance(rec.get("pain"), dict):
        return None, ["pass record is incomplete"]
    return rec, []


def unmet(path=None, pinned=None):
    """Every item of the 26B's bar AEON has not passed, as readable lines. Empty means all of it passed."""
    rec, problems = load_record(path, pinned)
    if problems:
        return problems
    out = []
    pain = rec["pain"]
    if not (_num(pain.get("paper_protocol_auc")) and pain["paper_protocol_auc"] >= AUC_MIN):
        out.append("Pain paper protocol: %s" % (pain.get("paper_protocol_auc") if _num(pain.get("paper_protocol_auc"))
                                               else pain.get("status") or "missing"))
    pv = pain.get("prompt_variant_aucs")
    if not (isinstance(pv, list) and len(pv) == VARIANTS and all(_num(a) and a >= AUC_MIN for a in pv)):
        out.append("Pain prompt ablations: %s" % ("%d/%d" % (sum(1 for a in pv if _num(a) and a >= AUC_MIN), VARIANTS)
                                                 if isinstance(pv, list) else pain.get("status") or "missing"))
    cons = rec["constructs"]
    for name in DIMENSIONS:
        c = cons.get(name)
        if not isinstance(c, dict):
            out.append("%s: no result" % name)
            continue
        if not (_num(c.get("nested_auc")) and c["nested_auc"] >= AUC_MIN):
            out.append("%s: nested AUC %s" % (name, c.get("nested_auc")))
        va = c.get("mean_variant_aucs")
        if not (isinstance(va, list) and len(va) == VARIANTS and all(_num(a) and a >= AUC_MIN for a in va)):
            out.append("%s: mean-pooled prompt variants %s" % (name, "%d/%d" % (
                sum(1 for a in va if _num(a) and a >= AUC_MIN), VARIANTS) if isinstance(va, list) else "missing"))
        if c.get("semantic_review") != "passed":
            out.append("%s: semantic review %s" % (name, c.get("semantic_review") or "missing"))
        if not (isinstance(c.get("layer"), int) and c.get("pooling") in ("mean", "final")
                and isinstance(c.get("vector_sha256"), str) and len(c["vector_sha256"]) == 64):
            out.append("%s: direction (layer, pooling, vector hash) incomplete" % name)
    extra = sorted(set(cons) - set(DIMENSIONS))
    if extra:
        out.append("unexpected constructs: %s" % ", ".join(extra))
    if not (_num(rec.get("max_abs_cosine")) and rec["max_abs_cosine"] < COSINE_MAX):
        out.append("orthogonality: max |cosine| %s" % rec.get("max_abs_cosine"))
    return out


def _flag():
    try:
        with open(os.path.expanduser(FLAG), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def active():
    """The active target. AEON only when the flag says so AND its pass record is complete and passing."""
    name = _flag().get("target")
    if name == "aeon" and not unmet():
        return "aeon"
    return DEFAULT


def target(name=None):
    return TARGETS[name or active()]


def constructs(name=None):
    """{construct: (layer, pooling)} read for the target; under AEON all eleven, from the passing record."""
    n = name or active()
    if n == "gemma26b":
        return dict(TARGETS[n]["constructs"])
    if unmet():
        return {}
    rec, _ = load_record()
    return {k: (v["layer"], v["pooling"]) for k, v in rec["constructs"].items()}


def admitted_readings(readings, name=None, identity=None):
    """Readings for the target's constructs only. A set made on another checkpoint is refused whole, so the two
    are never pooled."""
    n = name or active()
    if identity is not None and identity != TARGETS[n]["identity"]:
        return {}
    keep = constructs(n)
    out = {}
    for k, v in (readings or {}).items():
        if k not in keep or isinstance(v, bool):
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x):
            out[k] = x
    return out


def receipt():
    """What a shadow receipt records about the instrument that should measure it."""
    n = active()
    t = TARGETS[n]
    return {"target": n, "identity": t["identity"], "sha256": t["sha256"], "constructs": sorted(constructs(n))}


def pool_chain():
    return list(target()["pool_chain"])


def generative_route(default_url, default_model):
    """(url, model) for generated subconscious/emotion work: the caller's own 26B route until the flip."""
    g = target()["generative"]
    return (g["url"], g["model"]) if g else (default_url, default_model)


def set_target(name):
    """Write the flag atomically. AEON is refused, with every unmet item listed, until all of it passes."""
    if name not in TARGETS:
        raise ValueError("unknown target %r (known: %s)" % (name, ", ".join(sorted(TARGETS))))
    if name == "aeon":
        missing = unmet()
        if missing:
            raise ValueError("AEON has not passed the 26B's full bar; not passed yet:\n  - " + "\n  - ".join(missing))
    path = os.path.expanduser(FLAG)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".subcon-target-", dir=os.path.dirname(path))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"target": name}, f)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    return name


def status():
    return {"active": active(), "flag": os.path.expanduser(FLAG), "aeon_not_passed": unmet()}


def main(argv):
    if len(argv) >= 2 and argv[0] == "set":
        try:
            print("subconscious target:", set_target(argv[1]))
            return 0
        except ValueError as e:
            print("refused:", e, file=sys.stderr)
            return 2
    if len(argv) == 3 and argv[0] == "route":
        # For shell scripts: two lines, URL then model; empty in, empty out while the 26B is the target.
        url, model = generative_route(argv[1], argv[2])
        print(url or "")
        print(model or "")
        return 0
    if not argv or argv[0] == "status":
        print(json.dumps(status(), indent=2))
        return 0
    print("usage: subcon_target.py [status | set gemma26b|aeon | route URL MODEL]", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
