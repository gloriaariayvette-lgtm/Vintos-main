#!/usr/bin/env python3
"""subcon_target.py — which model his subconscious emotion work runs on (Gloria 2026-11-07).

One flag decides it: ~/.vintos/subcon-target.json
    {"target": "gemma26b"}                          the 26B, as before the switch (also: no file, bad file)
    {"target": "aeon"}                              AEON, for the constructs that passed the 26B's own bar
    {"target": "aeon", "include_tier_b": true}      also the two tier-B readouts, read with their caveat

Residual readings. AEON (Gemma 4 12B abliterated, BF16) is held to exactly the per-construct bar the 26B passed
under the Pain-axis protocol: nested grouped held-out AUC >= .85 with pooling and layer chosen inside each outer
fold, all six mean-pooled prompt variants >= .85, |cosine| to the other directions < .3, and a passed named
semantic review of the unembedding. Nine constructs pass all four. Valence (layer 41) and Groundedness (layer 29)
pass the numbers but failed the semantic review, so they are tier B: off unless the flag opts in. Readings from
the two checkpoints are never mixed; under AEON a construct it has not passed has no reading, never the 26B's.

Generated readings (the live per-turn emotion read): under AEON they go through the shim's /pool/subconscious
lane, which then answers from AEON only. That is the quantized AEON generating text, a different contract from
the BF16 residual measurement; the two are never converted into each other.

This public file carries identities, hashes, layers and admission only. Vector files, host paths and the BF16
reader live in private config (~/.vintos/residual/). Nothing here loads a model or opens a socket.
Source of the AEON fields: the emotion Codex's sealed AEON readout handoff of 2026-11-07 (AEON-READOUT-MAP.json).
"""
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

TARGETS = {
    "gemma26b": {
        "identity": "gemma-4-26b-a4b-it-uncensored",
        "format": "GGUF Q4_K_M",
        "sha256": "d482a5daba09e67c925359a1786c4c713d1c3bb35856d199cf296f7cf7bc6cb3",
        "lock": "offline/residual_emotion/model-lock.json",
        # (layer, pooling, vector sha256 or None where the sealed 26B receipt does not list it)
        "admitted": {
            "Arousal": (25, "mean", None), "Connection": (26, "mean", None), "Curiosity": (24, "mean", None),
            "Desire": (25, "mean", None), "Dominance": (26, "mean", None), "Groundedness": (25, "mean", None),
            "Playfulness": (27, "mean", None), "Safety": (22, "mean", "8f6159d9fc9b6dbe3b865b6fbefcc9354946f636850c6f241cdf25dcc0998862"),
            "Tension": (26, "mean", None), "Valence": (25, "mean", None), "Warmth": (25, "mean", None),
        },
        "tier_b": {},
        "model_checks": {"pain_paper_protocol": "pass", "pain_prompt_variants": "pass"},
        "pool_chain": ["pool:subconscious", "gemma"],
        "generative": None,   # callers keep their own 26B route
    },
    "aeon": {
        "identity": "AEON-7-Gemma-4-12B-it-AEON-Abliterated-K4-BF16",
        "format": "GGUF BF16",
        "sha256": "02fd375821a7b50e783f408a75bf714ea85fc0dc67c933991642ef76d9b0d9ce",
        "lock": "offline/residual_emotion/model-lock-aeon.json",
        "admitted": {
            "Arousal": (37, "mean", "066788c07f209cb583da0beab9d92c47ddd29ddc7808826f5289eaac7d5a8c24"),
            "Connection": (29, "mean", "efe96a227ed454e0a3b8c43420cd0fe6754ccafa6623ee262ac4832efd2a8479"),
            "Curiosity": (30, "mean", "6432d0871b42b0e783888fd193612b7ac43d830f71dc265aa2acadf814b987e3"),
            "Desire": (36, "mean", "a10eb46f7bba2279020103c62cc35f38195285931547dfad04e0e3ba05232053"),
            "Dominance": (29, "mean", "e0ed4104b854e3fa0e50047a03ba9a51e231eeba2e7fcf2ebe7b4162228ece19"),
            "Playfulness": (29, "mean", "59d698fda687a337f85ccbb6700d2b52902eacffa8a1fe61f958808728cf4f0a"),
            "Safety": (28, "mean", "c93d679155686ae568b2f156a18e9bf0cd5013184e1d3940ad7e4bef87f1bc4e"),
            "Tension": (34, "mean", "e2fd43dcdcdeba943f6827fe8073ea4d517a040234d039c1ac31e5af9c5adddc"),
            "Warmth": (37, "mean", "a8a6711e25321ce55984232e9bbd7ce648730d34af4c7b7b9fd0570e23ebccb3"),
        },
        # Numbers pass; the original named semantic review failed. Read only when the flag opts in.
        "tier_b": {
            "Valence": (41, "mean", "d18baeff204d9d1a42e96dd29308e28f1634673b3dd932bfe8762538778ece65",
                        "semantic review failed: familiarity/comfort confound; an approved layer-37 rebuild exists "
                        "but its six prompt variants have not been run"),
            "Groundedness": (29, "mean", "ea9e22b20d9bf61e7575b889a483db59a0aea9ad0daa5e03b9f6d72f21fa0be9",
                             "semantic review failed: appearance versus bodily-sensation confound"),
        },
        # The 26B's record also has a model-level Pain replication. AEON has not run it; the handoff treats Pain
        # as exploratory, outside the eleven-key map. Reported by status(), not a gate on the eleven constructs.
        "model_checks": {"pain_paper_protocol": "not_run", "pain_prompt_variants": "not_run"},
        "pool_chain": ["pool:aeon", "aegis_gemma"],
        "generative": {"url": SHIM_SUBCONSCIOUS, "model": "aeon-gemma-4-12b"},
    },
}


def _flag_path():
    return os.path.expanduser(FLAG)


def _flag():
    try:
        with open(_flag_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def active():
    """The active target's name. Anything but a readable flag naming a known target means the 26B."""
    name = _flag().get("target")
    return name if name in TARGETS else DEFAULT


def tier_b_enabled():
    return active() != DEFAULT and _flag().get("include_tier_b") is True


def target(name=None):
    return TARGETS[name or active()]


def admitted(name=None, include_tier_b=None):
    """{construct: (layer, pooling, vector_sha256)} the active (or named) target may be read for."""
    t = target(name)
    out = {k: tuple(v) for k, v in t["admitted"].items()}
    use_b = tier_b_enabled() if include_tier_b is None else include_tier_b
    if use_b:
        out.update({k: tuple(v[:3]) for k, v in t["tier_b"].items()})
    return out


def admitted_readings(readings, name=None, identity=None, include_tier_b=None):
    """Keep only readings this target has admitted. A reading set made on another checkpoint is refused whole
    (returns {}), so the two are never pooled; a construct the target has not passed is dropped."""
    t = target(name)
    if identity is not None and identity != t["identity"]:
        return {}
    keep = admitted(name, include_tier_b)
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


def receipt(name=None):
    """What a shadow receipt records about the instrument that should measure it."""
    n = name or active()
    t = TARGETS[n]
    return {"target": n, "identity": t["identity"], "sha256": t["sha256"],
            "admitted": sorted(admitted(n, None if name is None else False))}


def pool_chain():
    return list(target()["pool_chain"])


def generative_route(default_url, default_model):
    """(url, model) for a generated emotion/subconscious read: the caller's own 26B route until the flip."""
    g = target()["generative"]
    return (g["url"], g["model"]) if g else (default_url, default_model)


def unrun_model_checks(name):
    return sorted(k for k, v in TARGETS[name]["model_checks"].items() if v != "pass")


def set_target(name, include_tier_b=False):
    """Write the flag atomically; returns the notes the operator should see."""
    if name not in TARGETS:
        raise ValueError("unknown target %r (known: %s)" % (name, ", ".join(sorted(TARGETS))))
    path = _flag_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"target": name}
    if include_tier_b and name != DEFAULT:
        data["include_tier_b"] = True
    fd, tmp = tempfile.mkstemp(prefix=".subcon-target-", dir=os.path.dirname(path))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    notes = ["subconscious target: %s" % name]
    unrun = unrun_model_checks(name)
    if unrun:
        notes.append("note: model-level checks not run on %s: %s" % (name, ", ".join(unrun)))
    return notes


def status():
    n = active()
    return {"active": n, "tier_b_enabled": tier_b_enabled(), "flag": _flag_path(),
            "reading": sorted(admitted()),
            "targets": {k: {"identity": v["identity"], "admitted": sorted(v["admitted"]),
                            "tier_b": {c: x[3] for c, x in v["tier_b"].items()},
                            "unrun_model_checks": unrun_model_checks(k)}
                        for k, v in TARGETS.items()}}


def main(argv):
    if len(argv) >= 2 and argv[0] == "set":
        try:
            for line in set_target(argv[1], include_tier_b="--tier-b" in argv[2:]):
                print(line)
            return 0
        except ValueError as e:
            print("refused:", e, file=sys.stderr)
            return 2
    if not argv or argv[0] == "status":
        print(json.dumps(status(), indent=2))
        return 0
    print("usage: subcon_target.py [status | set gemma26b | set aeon [--tier-b]]", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
