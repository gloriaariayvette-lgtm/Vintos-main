"""Command line for the sealed residual-emotion experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import analysis, compare, dataset, import_pain_axis, unembedding
from .io import sha256


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate"); validate.add_argument("dataset", type=Path)
    prepare = sub.add_parser("prepare"); prepare.add_argument("dataset", type=Path); prepare.add_argument("output", type=Path)
    paper_prepare = sub.add_parser("prepare-paper"); paper_prepare.add_argument("dataset", type=Path); paper_prepare.add_argument("output", type=Path)
    fit = sub.add_parser("fit"); fit.add_argument("work", type=Path); fit.add_argument("output", type=Path); fit.add_argument("--auc-minimum", type=float, default=0.85)
    paper_fit = sub.add_parser("paper-fit"); paper_fit.add_argument("work", type=Path); paper_fit.add_argument("output", type=Path); paper_fit.add_argument("--auc-minimum", type=float, default=0.85)
    variant_fit = sub.add_parser("paper-variant-fit"); variant_fit.add_argument("work", type=Path); variant_fit.add_argument("output", type=Path); variant_fit.add_argument("--auc-minimum", type=float, default=0.85)
    compare_cmd = sub.add_parser("compare"); compare_cmd.add_argument("emoclaw", type=Path); compare_cmd.add_argument("residual", type=Path); compare_cmd.add_argument("output", type=Path)
    verify = sub.add_parser("verify-model"); verify.add_argument("--lock", type=Path, default=Path(__file__).resolve().parents[1] / "model-lock.json")
    unembed = sub.add_parser("unembed"); unembed.add_argument("direction", type=Path); unembed.add_argument("--lock", type=Path, default=Path(__file__).resolve().parents[1] / "model-lock.json")
    review = sub.add_parser("review-unembedding"); review.add_argument("direction", type=Path); review.add_argument("--reviewer", required=True); review.add_argument("--verdict", choices=("pass", "fail"), required=True); review.add_argument("--note", required=True)
    pain = sub.add_parser("import-pain-axis"); pain.add_argument("source", type=Path); pain.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "validate": result = dataset.validate(args.dataset)
    elif args.command == "prepare": result = dataset.prepare(args.dataset, args.output)
    elif args.command == "prepare-paper": result = dataset.prepare_paper_protocol(args.dataset, args.output)
    elif args.command == "fit": result = analysis.fit(args.work, args.output, args.auc_minimum)
    elif args.command == "paper-fit": result = analysis.paper_fit(args.work, args.output, args.auc_minimum)
    elif args.command == "paper-variant-fit": result = analysis.paper_variant_fit(args.work, args.output, args.auc_minimum)
    elif args.command == "compare": result = compare.join(args.emoclaw, args.residual, args.output)
    elif args.command == "verify-model":
        lock = json.loads(args.lock.read_text(encoding="utf-8")); path = Path(lock["path"])
        actual = sha256(path)
        result = {"identity": lock["identity"], "path": str(path), "expected": lock["sha256"], "actual": actual, "ok": actual == lock["sha256"]}
        if not result["ok"]: raise SystemExit("model hash mismatch")
    elif args.command == "unembed":
        lock = json.loads(args.lock.read_text(encoding="utf-8"))
        model_path = Path(lock["path"])
        if sha256(model_path) != lock["sha256"]: raise SystemExit("model hash mismatch")
        result = unembedding.analyze(model_path, args.direction, args.lock.parent)
    elif args.command == "review-unembedding":
        result = unembedding.review(args.direction, args.reviewer, args.verdict == "pass", args.note)
    else:
        result = import_pain_axis.convert(args.source, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
