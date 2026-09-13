#!/usr/bin/env python3
"""Read-only Evo 2 scoring behind one provenance-bearing genomic source door.

This is not a sequence-design surface. The public CLI accepts no sequence, prompt,
accession or generation arguments. It fetches one bounded window from a declared
non-human reference source, verifies the source identity and sequence digest, then
asks Evo 2 only for comparative likelihood under one deterministic substitution.
The result is a model preference, not a functional-impact claim.

Evo 2 7B in BF16 cannot coexist with resident Gemma on this 16 GB host. A run holds
the house background-compute lock before reaching this module; this module holds the
Gemma watchdog lock, unloads only Gemma, executes one bounded worker, and restores
Gemma in ``finally``. A crash still leaves the five-minute watchdog as recovery.
Package installation is not availability: only a completed scored pair may mint a
dated Chemistry Lab instrument receipt.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import chemistry_lab as lab

EVO_PYTHON = os.environ.get("CHEM_LAB_EVO2_PYTHON",
                            os.path.expanduser("~/.vintos/tools/chemistry-lab/evo2/bin/python"))
MODEL = "evo2_7b_base"
LMS = os.environ.get("CHEM_LAB_LMS", "/mnt/c/Users/glori/.lmstudio/bin/lms.exe")
GEMMA_MODEL = lab.LLM_MODEL
# The Lab service has PrivateTmp=true.  A /tmp lock would therefore be invisible
# to the host watchdog and both processes could change LM Studio at once.
WATCHDOG_LOCK = os.path.join(lab.MEM, ".gemma-watchdog.lock")
RUNS = os.path.join(lab.ROOT, "evo2-runs.jsonl")
NCBI_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
MAX_BASES = 512
WORKER_TIMEOUT = 900
SAFE_SOURCES = {
    # A fixed Arabidopsis reference window: non-human, non-pathogen, read-only.
    "arabidopsis_chr1": {"accession": "NC_003070.9", "taxon_id": 3702,
                          "organism": "Arabidopsis thaliana", "start": 1, "stop": MAX_BASES},
}
DNA = re.compile(r"^[ACGTN]+$")
DENIED_METADATA = re.compile(r"human|homo sapiens|pathogen|virus|virulence|toxin|venom", re.I)


def _sha(value):
    return hashlib.sha256(str(value).encode("utf-8", "ignore")).hexdigest()


def fetch_source(source_key="arabidopsis_chr1"):
    spec = SAFE_SOURCES.get(source_key)
    if not spec: raise ValueError("source is not in the non-human reference allowlist")
    if int(spec["taxon_id"]) == 9606 or DENIED_METADATA.search(spec["organism"]):
        raise ValueError("source perimeter refused")
    query = urllib.parse.urlencode({"db": "nuccore", "id": spec["accession"],
                                    "seq_start": spec["start"], "seq_stop": spec["stop"],
                                    "rettype": "fasta", "retmode": "text"})
    req = urllib.request.Request(NCBI_EFETCH + "?" + query,
                                 headers={"User-Agent": "Vintos-Chemistry-Lab/1.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        text = response.read(MAX_BASES * 3).decode("ascii", "replace")
    header = next((line.strip() for line in text.splitlines() if line.startswith(">")), "")
    if not header.startswith(">" + spec["accession"] + ":"):
        raise ValueError("source returned a different accession")
    lines = [line.strip().upper() for line in text.splitlines() if line and not line.startswith(">")]
    sequence = "".join(lines)[:MAX_BASES]
    if len(sequence) < 64 or not DNA.fullmatch(sequence): raise ValueError("source returned unreadable DNA")
    return {"source_key": source_key, **spec, "sequence": sequence, "source_header": header[:180],
            "sequence_sha256": _sha(sequence), "source": "NCBI Nucleotide efetch",
            "fetched_at": lab.now_iso(), "truth_status": "public_reference_sequence_receipt"}


def _validate_payload(payload):
    source_key = str(payload.get("source_key") or "")
    spec = SAFE_SOURCES.get(source_key)
    if not spec: raise ValueError("unapproved source")
    if payload.get("accession") != spec["accession"] or int(payload.get("taxon_id") or 0) != spec["taxon_id"]:
        raise ValueError("source provenance mismatch")
    if not str(payload.get("source_header") or "").startswith(">" + spec["accession"] + ":"):
        raise ValueError("source header mismatch")
    if int(payload.get("taxon_id")) == 9606 or DENIED_METADATA.search(str(payload.get("organism") or "")):
        raise ValueError("source perimeter refused")
    sequence = str(payload.get("sequence") or "").upper()
    if not (64 <= len(sequence) <= MAX_BASES) or not DNA.fullmatch(sequence):
        raise ValueError("DNA window outside bounded alphabet or size")
    if _sha(sequence) != payload.get("sequence_sha256"): raise ValueError("sequence digest mismatch")
    return sequence


def _worker(payload):
    """The isolated environment's only model operation: score reference and one variant."""
    sequence = _validate_payload(payload)
    import torch
    from evo2 import Evo2
    model = Evo2(MODEL, use_kernels=True)

    def score(text):
        ids = torch.tensor(model.tokenizer.tokenize(text), dtype=torch.int).unsqueeze(0).to("cuda:0")
        with torch.inference_mode(): outputs, _ = model(ids)
        logits = outputs[0] if isinstance(outputs, (list, tuple)) else outputs
        token_logp = torch.log_softmax(logits[:, :-1].float(), dim=-1).gather(
            -1, ids[:, 1:].long().unsqueeze(-1)).squeeze(-1)
        return float(token_logp.mean().item())

    position = len(sequence) // 2
    old = sequence[position]; new = {"A": "C", "C": "G", "G": "T", "T": "A", "N": "A"}[old]
    variant = sequence[:position] + new + sequence[position + 1:]
    reference_score, variant_score = score(sequence), score(variant)
    return {"ok": True, "model": MODEL, "source_key": payload["source_key"],
            "source_accession": payload["accession"], "taxon_id": payload["taxon_id"],
            "sequence_sha256": payload["sequence_sha256"], "sequence_length": len(sequence),
            "variant": {"position_zero_based": position, "from": old, "to": new},
            "reference_mean_log_likelihood": round(reference_score, 8),
            "variant_mean_log_likelihood": round(variant_score, 8),
            "variant_delta": round(variant_score - reference_score, 8),
            "truth_status": "evo2_model_likelihood_delta_not_functional_effect"}


@contextlib.contextmanager
def _watchdog_exclusion():
    with open(WATCHDOG_LOCK, "a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def _lms(*args):
    if not os.path.isfile(LMS): raise FileNotFoundError("LM Studio CLI unavailable")
    return subprocess.run([LMS, *args], text=True, capture_output=True, timeout=180, check=False)


def _restore_gemma():
    done = _lms("load", GEMMA_MODEL, "--gpu", "max", "-c", "32000", "--parallel", "1")
    if done.returncode != 0: raise RuntimeError("Gemma reload failed")


def analyze(source_key="arabidopsis_chr1", *, manage_gemma=True):
    """Fetch a safe public window, run one bounded pair, and preserve a typed receipt."""
    source = fetch_source(source_key)
    started = time.time(); restored = None
    try:
        with _watchdog_exclusion():
            if manage_gemma:
                unloaded = _lms("unload", GEMMA_MODEL)
                if unloaded.returncode != 0: raise RuntimeError("Gemma unload failed")
                time.sleep(2)
            try:
                done = subprocess.run([EVO_PYTHON, os.path.abspath(__file__), "--worker"],
                                      input=json.dumps(source), text=True, capture_output=True,
                                      timeout=WORKER_TIMEOUT, check=False,
                                      env={**os.environ, "HF_HOME": os.path.expanduser(
                                          "~/.vintos/tools/chemistry-lab/checkpoints/huggingface")})
            finally:
                if manage_gemma:
                    try: _restore_gemma(); restored = True
                    except Exception as exc: restored = False; lab._fault("evo2_restore_gemma", exc)
        if done.returncode != 0:
            raise RuntimeError("Evo 2 worker failed (%s): %s" %
                               (done.returncode, (done.stderr or done.stdout)[-500:]))
        result = json.loads((done.stdout or "").strip().splitlines()[-1])
        if not result.get("ok"): raise RuntimeError("Evo 2 worker returned no result")
        row = {**result, "run_id": "EVO-" + _sha(result)[:16], "at": lab.now_iso(),
               "source_receipt": {key: source[key] for key in
                                  ("source", "source_key", "accession", "taxon_id", "organism",
                                  "start", "stop", "source_header", "sequence_sha256", "fetched_at", "truth_status")},
               "gemma_restored": restored, "elapsed_ms": int((time.time() - started) * 1000)}
        lab._append(RUNS, row); return row
    except Exception as exc:
        row = {"ok": False, "at": lab.now_iso(), "source_key": source_key,
               "error": exc.__class__.__name__, "detail": str(exc)[:500],
               "gemma_restored": restored,
               "truth_status": "typed_evo2_failure_no_instrument_claim"}
        lab._append(RUNS, row); return row


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        try: print(json.dumps(_worker(json.load(sys.stdin)), sort_keys=True))
        except Exception as exc:
            print(json.dumps({"ok": False, "error": exc.__class__.__name__, "detail": str(exc)[:500]}))
            raise SystemExit(1)
    elif len(sys.argv) == 2 and sys.argv[1] == "run":
        print(json.dumps(analyze(), ensure_ascii=False, indent=2))
    else:
        raise SystemExit("usage: chemistry_evo2.py run")
