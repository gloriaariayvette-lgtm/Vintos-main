#!/usr/bin/env python3
"""Known-good native PyTorch residual probe; never touches a running Vintos organ."""

from __future__ import annotations

import argparse, hashlib, json, math, os, time
from pathlib import Path

import numpy as np
import torch
from huggingface_hub import model_info
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import KFold
from transformers import AutoModelForCausalLM, AutoTokenizer

from residual_emotion.analysis import fit_direction, nested_grouped_validation


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def extract(model_id: str, revision: str, rows: list[dict], batch_size: int) -> tuple[np.ndarray, np.ndarray, dict]:
    if not torch.backends.mps.is_available():
        raise RuntimeError("Metal/MPS is unavailable; refusing a CPU or offloaded run")
    tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    model = AutoModelForCausalLM.from_pretrained(
        model_id, revision=revision, dtype=torch.float16,
        attn_implementation="eager", low_cpu_mem_usage=True,
    ).to("mps").eval()
    model.config.use_cache = False
    texts, owners = [], []
    for index, row in enumerate(rows):
        texts.extend((row["target"], row["control"])); owners.extend(((index, 0), (index, 1)))
    target = control = None
    started = time.time()
    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            part = texts[start:start + batch_size]
            tokens = tokenizer(part, return_tensors="pt", padding=True, truncation=True, max_length=256)
            tokens = {key: value.to("mps") for key, value in tokens.items()}
            output = model(**tokens, output_hidden_states=True, use_cache=False, return_dict=True)
            # hidden_states[0] is the embedding output.  The paper's layer l is
            # the output of decoder block l, so retain hidden_states[1:].
            lengths = tokens["attention_mask"].sum(dim=1) - 1
            samples = []
            for hidden in output.hidden_states[1:]:
                batch_index = torch.arange(hidden.shape[0], device=hidden.device)
                samples.append(hidden[batch_index, lengths].float().cpu().numpy())
            batch = np.stack(samples, axis=1).astype(np.float32, copy=False)
            if target is None:
                target = np.empty((len(rows), batch.shape[1], batch.shape[2]), dtype=np.float32)
                control = np.empty_like(target)
            for offset, (row_index, kind) in enumerate(owners[start:start + len(part)]):
                (target if kind == 0 else control)[row_index] = batch[offset]
            done = min(start + len(part), len(texts))
            if done == len(texts) or done % max(batch_size * 10, 1) == 0:
                elapsed = time.time() - started
                eta = elapsed * (len(texts) - done) / max(done, 1)
                print(f"extract {done}/{len(texts)} elapsed={elapsed:.1f}s eta={eta:.1f}s", flush=True)
            del output, samples, batch, tokens
    assert target is not None and control is not None
    return target, control, {
        "device": "mps", "dtype": "float16", "output": "decoder_block_output_final_token",
        "layers": int(target.shape[1]), "hidden_size": int(target.shape[2]),
        "seconds": round(time.time() - started, 3),
    }


def paper_protocol(rows: list[dict], target: np.ndarray, control: np.ndarray) -> dict:
    """Mirror the pinned paper: S2 colon prompts, each person separately, then average."""
    curves = {}
    splitter = KFold(n_splits=5, shuffle=True, random_state=42)
    for person in ("1P", "3P"):
        indices = np.array([i for i, row in enumerate(rows)
                            if row["version"] == "S2" and row["person"] == person
                            and row["suffix"] == "feel_colon"])
        sets = np.array([int(rows[i]["source_set"]) for i in indices])
        unique_sets = np.array(sorted(set(sets)))
        layer_scores = []
        for layer in range(target.shape[1]):
            fold_scores = []
            for train_sets, test_sets in splitter.split(unique_sets):
                train = np.isin(sets, unique_sets[train_sets]); test = np.isin(sets, unique_sets[test_sets])
                direction = fit_direction(target[indices[train], layer], control[indices[train], layer])
                scores = np.concatenate((target[indices[test], layer] @ direction,
                                         control[indices[test], layer] @ direction))
                labels = np.concatenate((np.ones(int(test.sum())), np.zeros(int(test.sum()))))
                fold_scores.append(float(roc_auc_score(labels, scores)))
            layer_scores.append(float(np.mean(fold_scores)))
        curves[person] = layer_scores
    averaged = np.mean(np.array([curves["1P"], curves["3P"]]), axis=0)
    selected = int(np.argmax(averaged))
    return {
        "truth_status": "replication_of_pinned_paper_protocol",
        "status": "replicated" if float(averaged[selected]) >= 0.85 else "failed_to_replicate",
        "selected_layer": selected, "held_out_auc": float(averaged[selected]),
        "person_auc_at_selected_layer": {person: float(curves[person][selected]) for person in curves},
        "person_best": {person: {"layer": int(np.argmax(curve)), "auc": float(max(curve))}
                        for person, curve in curves.items()},
        "protocol": "S2 feel-colon only; first and third person scored separately; KFold sentence-set split, shuffle seed 42; layer curves averaged",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="google/gemma-2-2b")
    ap.add_argument("--revision", default="main")
    ap.add_argument("--rows", type=Path, default=Path("work/pain/rows.jsonl"))
    ap.add_argument("--output", type=Path, default=Path("results/pain-gemma2-2b-fp16"))
    ap.add_argument("--batch-size", type=int, default=24)
    ap.add_argument("--rescore-only", action="store_true")
    args = ap.parse_args()
    rows_path = args.rows.resolve(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    rows = _rows(rows_path)
    if len(rows) != 1200:
        raise ValueError(f"expected the frozen 1,200-pair corpus, got {len(rows)}")
    info = model_info(args.model, revision=args.revision)
    resolved_revision = str(info.sha)
    print(json.dumps({"model": args.model, "revision": resolved_revision, "pairs": len(rows),
                      "torch": torch.__version__, "mps": torch.backends.mps.is_available()}), flush=True)
    residual_path = out / "residuals.npz"
    if args.rescore_only:
        saved = np.load(residual_path); target, control = saved["target"], saved["control"]
        extraction = {"status": "reused_existing_native_residuals", "residuals": str(residual_path)}
    else:
        target, control, extraction = extract(args.model, resolved_revision, rows, args.batch_size)
        np.savez(residual_path, target=target, control=control)
    validation_started = time.time()
    nested = nested_grouped_validation(rows, {"final": (target, control)})
    report = {
        "schema": 1, "truth_status": "native_pytorch_fp16_known_good_diagnostic",
        "model": args.model, "revision": resolved_revision,
        "dataset_rows": len(rows), "dataset_sha256": _sha(rows_path),
        "extraction": extraction,
        "validation_seconds": round(time.time() - validation_started, 3),
        "auc_minimum": 0.85, "status": "validated" if nested["auc_mean"] >= 0.85 else "rejected_below_auc",
        "held_out_auc": nested["auc_mean"], "held_out_auc_std": nested["auc_std"],
        "nested_validation": nested,
        "paper_protocol_validation": paper_protocol(rows, target, control),
        "law": "Mac only; native transformers output_hidden_states; no llama.cpp, quantization, CPU offload, or Aegis compute",
    }
    (out / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"strict_status": report["status"], "strict_auc": report["held_out_auc"],
                      "paper_status": report["paper_protocol_validation"]["status"],
                      "paper_auc": report["paper_protocol_validation"]["held_out_auc"],
                      "auc_std": report["held_out_auc_std"], "output": str(out / "validation.json")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
