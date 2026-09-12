"""Launch the existing emotion daemon and attest the parameters actually loaded.

This wrapper changes no model, training data, or inference behavior. Receipts
distinguish a requested checkpoint from a verified match of loaded parameters.
"""
import hashlib
import inspect
import json
import os
from pathlib import Path
import runpy
import time


def parameter_digest(state):
    digest = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        digest.update(json.dumps([name, str(tensor.dtype), list(tensor.shape)]).encode())
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def attest(engine, checkpoint, before):
    receipt = {"schema": "loaded-emotion-1", "pid": os.getpid(), "at": time.time(),
               "requested_checkpoint": str(checkpoint) if checkpoint else None,
               "checkpoint_sha256_before_load": before,
               "loaded_parameters_sha256": None, "checkpoint_parameters_match": None,
               "training_lineage": "not_established"}
    try:
        receipt["loaded_parameters_sha256"] = parameter_digest(engine.model.state_dict())
        if checkpoint:
            import torch
            receipt["checkpoint_sha256_after_load"] = hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest()
            state = torch.load(checkpoint, map_location="cpu", weights_only=True)
            state = state.get("model_state_dict", state.get("state_dict", state))
            receipt["checkpoint_parameters_sha256"] = parameter_digest(state)
            receipt["checkpoint_parameters_match"] = (
                before == receipt["checkpoint_sha256_after_load"] and
                receipt["loaded_parameters_sha256"] == receipt["checkpoint_parameters_sha256"])
    except Exception as exc:
        receipt["verification_error"] = str(exc)[:200]
    return receipt


def main():
    workspace = Path.home() / ".vintos/workspace"
    import sys
    sys.path.insert(0, str(workspace))
    from emotion_model.inference import EmotionEngine
    original = EmotionEngine.__init__

    def initialize(engine, *args, **kwargs):
        bound = inspect.signature(original).bind(engine, *args, **kwargs)
        checkpoint = bound.arguments.get("model_path")
        before = hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest() if checkpoint else None
        original(engine, *args, **kwargs)
        receipt = attest(engine, checkpoint, before)
        from store_guard import write_json
        write_json(str(workspace / "memory/emotion-loaded-checkpoint.json"), receipt)

    EmotionEngine.__init__ = initialize
    runpy.run_module("emotion_model.daemon", run_name="__main__")


if __name__ == "__main__":
    main()
