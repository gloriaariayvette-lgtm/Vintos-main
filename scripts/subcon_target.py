#!/usr/bin/env python3
"""subcon_target.py — which checkpoint his subconscious emotion readings come from (Gloria 2026-11-07).

One flag decides it: ~/.vintos/subcon-target.json  {"target": "aeon"} or {"target": "gemma26b"}.
No file, an unreadable file or an unknown name all mean "gemma26b", the target before the switch.

AEON is held to exactly the bar the 26B passed under the Pain-axis protocol, nothing extra:
  model level   Pain paper protocol (S2 feel-colon, final token, persons separate, 5-fold) AUC >= .85,
                and all six Pain prompt ablations >= .85;
  per construct nested grouped held-out AUC >= .85 (pooling and layer chosen inside each outer fold),
                all six mean-pooled prompt variants >= .85, every |cosine| to the other admitted
                directions < .3, and a named semantic review of the unembedding passed.
Only constructs that clear every per-construct item are read from AEON, and the flag cannot be set to AEON
while a model-level item is unmet. Readings from the two checkpoints are never mixed: under AEON a construct
it has not passed has no reading at all; it never falls back to the 26B's value.

This public file carries identities, hashes and admission only. Host paths, vectors and reader endpoints live
in private config (~/.vintos/residual/), never here. Nothing in this module loads a model or opens a socket.
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

# Per-construct readout: residual layer and pooling of the admitted direction. Evidence lives beside the
# offline instrument (offline/residual_emotion/evidence/) and, for AEON, in the private evidence folders.
TARGETS = {
    "gemma26b": {
        "identity": "gemma-4-26b-a4b-it-uncensored",
        "format": "GGUF Q4_K_M",
        "sha256": "d482a5daba09e67c925359a1786c4c713d1c3bb35856d199cf296f7cf7bc6cb3",
        "lock": "offline/residual_emotion/model-lock.json",
        "model_gates": {"pain_paper_protocol": "pass", "pain_prompt_variants": "pass"},
        "admitted": {
            "Arousal": (25, "mean"), "Connection": (26, "mean"), "Curiosity": (24, "mean"),
            "Desire": (25, "mean"), "Dominance": (26, "mean"), "Groundedness": (25, "mean"),
            "Playfulness": (27, "mean"), "Safety": (22, "mean"), "Tension": (26, "mean"),
            "Valence": (25, "mean"), "Warmth": (25, "mean"),
        },
        "blocked": {},
        "pool_chain": ["pool:subconscious", "gemma"],
    },
    "aeon": {
        "identity": "AEON-7-Gemma-4-12B-it-AEON-Abliterated-K4-BF16",
        "format": "GGUF BF16",
        "sha256": "02fd375821a7b50e783f408a75bf714ea85fc0dc67c933991642ef76d9b0d9ce",
        "lock": "offline/residual_emotion/model-lock-aeon.json",
        # The 26B passed both; neither has been run on AEON yet. Set to "pass" only with the sealed result.
        "model_gates": {"pain_paper_protocol": "not_run", "pain_prompt_variants": "not_run"},
        "admitted": {
            "Arousal": (37, "mean"), "Connection": (29, "mean"), "Curiosity": (30, "mean"),
            "Desire": (36, "mean"), "Dominance": (29, "mean"), "Playfulness": (29, "mean"),
            "Safety": (28, "mean"), "Tension": (34, "mean"),
        },
        "blocked": {
            "Valence": "rebuilt 2x2 direction (layer 37) passes nested AUC, orthogonality and owner review; "
                       "its six mean-pooled prompt variants have not been run",
            "Warmth": "original layer-37 direction cleared the 26B bar but is quarantined by the owner's "
                      "2026-11-05 admission receipt; the rebuilt direction's review is pending",
            "Groundedness": "original direction failed semantic review; the re-derived candidates have no "
                            "nested-protocol, prompt-variant or owner review result yet",
        },
        # Generation for /pool/subconscious: AEON on whichever machine has room, then Aegis's own AEON lane.
        "pool_chain": ["pool:aeon", "aegis_gemma"],
    },
}


def _flag_path():
    return os.path.expanduser(FLAG)


def active():
    """The active target's name. Anything but a readable flag naming a known target whose model-level items all
    pass means the 26B, so a hand-written flag cannot point his subconscious at an unvalidated checkpoint."""
    try:
        with open(_flag_path(), encoding="utf-8") as f:
            name = json.load(f).get("target")
    except Exception:
        return DEFAULT
    return name if name in TARGETS and not blockers(name) else DEFAULT


def target(name=None):
    return TARGETS[name or active()]


def blockers(name):
    """Model-level items still unmet for this target (empty when the flag may point at it)."""
    return sorted(k for k, v in TARGETS[name]["model_gates"].items() if v != "pass")


def admitted(name=None):
    """{construct: (layer, pooling)} the active (or named) target may be read for."""
    return dict(target(name)["admitted"])


def admitted_readings(readings, name=None, identity=None):
    """Keep only readings this target has admitted. A reading set made on another checkpoint is refused whole
    (returns {}), so the two checkpoints are never pooled; a construct the target has not passed is dropped."""
    t = target(name)
    if identity is not None and identity != t["identity"]:
        return {}
    out = {}
    for k, v in (readings or {}).items():
        if k in t["admitted"] and not isinstance(v, bool):
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
            "admitted": sorted(t["admitted"])}


def pool_chain():
    return list(target()["pool_chain"])


def set_target(name):
    """Write the flag atomically. Refuses unknown names and a target with unmet model-level items."""
    if name not in TARGETS:
        raise ValueError("unknown target %r (known: %s)" % (name, ", ".join(sorted(TARGETS))))
    unmet = blockers(name)
    if unmet:
        raise ValueError("%s cannot be the subconscious target yet; unmet: %s" % (name, ", ".join(unmet)))
    path = _flag_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".subcon-target-", dir=os.path.dirname(path))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"target": name}, f)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    return name


def status():
    n = active()
    return {"active": n, "flag": _flag_path(),
            "targets": {k: {"identity": v["identity"], "admitted": sorted(v["admitted"]),
                            "blocked": v["blocked"], "unmet_model_gates": blockers(k)}
                        for k, v in TARGETS.items()}}


def main(argv):
    if len(argv) >= 2 and argv[0] == "set":
        try:
            print("subconscious target:", set_target(argv[1]))
            return 0
        except ValueError as e:
            print("refused:", e, file=sys.stderr)
            return 2
    if not argv or argv[0] == "status":
        print(json.dumps(status(), indent=2))
        return 0
    print("usage: subcon_target.py [status | set gemma26b|aeon]", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
