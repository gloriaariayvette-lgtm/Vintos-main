#!/usr/bin/env python3
"""subcon_target.py — which model his subconscious emotion work runs on (Gloria 2026-11-07).

His subconscious, emotion, text and vision work all run on AEON. The 26B is removed (Gloria 2026-11-08: "we can
remove 26b completely once we confirm everything is in Aeon"): there is no other target and nothing to fall back to.
The flag file (~/.vintos/subcon-target.json) is kept for status and accepts only "aeon".

Gloria: "IT HAS TO ALL PASS." AEON can be the target only when it has passed the 26B's full bar, all of it:
  model level   the Pain paper-protocol replication (S2 feel-colon, final token) AUC >= .85, and all six Pain
                prompt ablations >= .85;
  every one of the eleven constructs
                nested grouped held-out AUC >= .85, all six mean-pooled prompt variants >= .85, and a passed named
                semantic review of the unembedding; and across the eleven, every |cosine| < .3.
The evidence is a pass record (aeon-bar-record.json beside this file) built from the emotion Codex's sealed
results and pinned here by its sha256. The checker recomputes every verdict from the record's numbers; it never
trusts a "pass" word. A missing, malformed, tampered or incomplete record, or any unmet item, refuses the flip
and lists exactly what has not passed. Calls still go to AEON (there is no other model), but while anything is
unmet no residual reading is admitted (constructs() is empty), so an unproven direction never steers him.

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
DEFAULT = "aeon"
DIMENSIONS = ("Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection",
              "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness")
SHIM_SUBCONSCIOUS = "http://127.0.0.1:8599/pool/subconscious/v1/chat/completions"

# The bar the old subconscious model passed in September (offline/residual_emotion/evidence/2026-09-20-*).
AUC_MIN = 0.85
VARIANTS = 6
COSINE_MAX = 0.3

RECORD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aeon-bar-record.json")
RECORD_SHA256 = "0c5eabce9d647df5c08c705889e7c7795d2920299afc9257c264477af85cd122"
RECORD_SCHEMA = "aeon-26b-bar-record/1"

TARGETS = {
    "aeon": {
        "identity": "AEON-7-Gemma-4-12B-it-AEON-Abliterated-K4-BF16",
        "format": "GGUF BF16",
        "sha256": "02fd375821a7b50e783f408a75bf714ea85fc0dc67c933991642ef76d9b0d9ce",
        "lock": "offline/residual_emotion/model-lock-aeon.json",
        "constructs": None,   # from the pass record, only once every item passes
        "pool_chain": ["pool:aeon", "aegis_gemma"],
        "generative": {"url": SHIM_SUBCONSCIOUS, "model": "aeon-gemma-4-12b"},
        # The local call's brain streams, so it talks to an AEON backend directly (address from the private pool
        # config, the Studio first), thinking off.
        "brain": {"backend": "aeon-12b", "prefer": ("studio", "aegis"),
                  "extra": {"reasoning_effort": "none", "chat_template_kwargs": {"enable_thinking": False}}},
        # Image calls: AEON with its own vision projector, in the MacBook's LM Studio (the endpoint the 26B's image
        # calls already used), thinking off: with thinking on it spends the whole budget reasoning (2026-11-08).
        "vision": {"model": "aeon-gemma-4-12b", "machine": "macbook", "extra": {"reasoning_effort": "none"}},
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
    """The active target: AEON, always (the 26B was removed, 2026-11-08). Whether AEON's readings are admitted is
    constructs()'s question, answered by the pass record."""
    return DEFAULT


def target(name=None):
    return TARGETS[name or active()]


def constructs(name=None):
    """{construct: (layer, pooling)} read for the target; under AEON all eleven, from the passing record."""
    n = name or active()
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
    """(url, model) for generated subconscious/emotion work: AEON's subconscious lane, always."""
    g = target()["generative"]
    return (g["url"], g["model"]) if g else (default_url, default_model)


POOL_BACKENDS = os.path.join("~", ".vintos", "pool", "backends.json")


def brain_route(default_base, default_model, backends_path=None):
    """(base url, model, extra body fields) for the local call's brain: the first AEON backend in the private pool config by machine preference. No AEON backend there: its own route."""
    b = target().get("brain")
    if not b:
        return default_base, default_model, {}
    try:
        rows = json.load(open(os.path.expanduser(backends_path or POOL_BACKENDS)))
    except Exception:
        return default_base, default_model, {}
    rows = [r for r in rows if isinstance(r, dict) and r.get("label") == b["backend"] and r.get("url")]
    rank = {m: i for i, m in enumerate(b["prefer"])}
    rows.sort(key=lambda r: rank.get(r.get("machine"), len(rank)))
    if not rows:
        return default_base, default_model, {}
    url = str(rows[0]["url"])
    base = url[: -len("/v1/chat/completions")] if url.endswith("/v1/chat/completions") else url
    return base, str(rows[0].get("model") or b["backend"]), json.loads(json.dumps(b["extra"]))


def vision_route(default_url, default_model, backends_path=None):
    """(chat url, model, extra body fields) for a call that sends images. AEON's vision model at the caller's own endpoint (the MacBook's LM Studio), or, for a caller with
    no endpoint of its own, the MacBook LM Studio address from the private pool config. Nothing there: its own route."""
    v = target().get("vision")
    if not v:
        return default_url, default_model, {}
    url = default_url
    if not url:
        try:
            rows = json.load(open(os.path.expanduser(backends_path or POOL_BACKENDS)))
        except Exception:
            rows = []
        rows = [r for r in rows if isinstance(r, dict) and r.get("machine") == v["machine"]
                and r.get("kind") == "lmstudio" and str(r.get("url") or "").endswith("/v1/chat/completions")]
        if not rows:
            return default_url, default_model, {}
        url = str(rows[0]["url"])
    return url, v["model"], json.loads(json.dumps(v["extra"]))


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
        # For shell scripts: two lines, URL then model; AEON's subconscious lane.
        url, model = generative_route(argv[1], argv[2])
        print(url or "")
        print(model or "")
        return 0
    if not argv or argv[0] == "status":
        print(json.dumps(status(), indent=2))
        return 0
    print("usage: subcon_target.py [status | set aeon | route URL MODEL]", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
