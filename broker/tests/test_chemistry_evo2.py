#!/usr/bin/env python3
"""Evo 2 Lab lane: scratch stores and faked model/LMS/network boundaries."""
import contextlib, importlib.util, json, os, subprocess, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-evo2-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos.")

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod
    spec.loader.exec_module(mod); return mod

lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
evo = load("chemistry_evo2", os.path.join(REPO, "scripts", "chemistry_evo2.py"))
probe = load("chemistry_probe", os.path.join(REPO, "scripts", "chemistry_probe.py"))
assert HOME in evo.RUNS and HOME in probe.PROBES and not evo.RUNS.startswith("/home/gloria")
assert evo.WATCHDOG_LOCK.startswith(WS), "watchdog lock must cross the service PrivateTmp boundary"
watchdog = open(os.path.join(REPO, "bin", "gemma-watchdog.sh")).read()
loader = open(os.path.join(REPO, "scripts", "aegis-gemma-load.sh")).read()
assert 'LOCK="/home/gloria/.vintos/workspace/memory/.gemma-watchdog.lock"' in watchdog
assert 'BASE="http://127.0.0.1:1234"' in watchdog and 'MODEL="google/gemma-4-12b-qat"' in watchdog
assert 'unload "$MODEL"' in watchdog and "unload --all" not in watchdog
assert 'LOADER="/home/gloria/.vintos/workspace/scripts/aegis-gemma-load.sh"' in watchdog
assert 'VARIANT="google/gemma-4-12b-qat@q4_0"' in loader
assert '--identifier "$IDENTIFIER"' in loader and '--no-speculative-draft-mtp' in loader

sequence = "ACGT" * 128
source = {"source_key": "arabidopsis_chr1", "accession": "NC_003070.9", "taxon_id": 3702,
          "organism": "Arabidopsis thaliana", "start": 1, "stop": 512,
          "source_header": ">NC_003070.9:1-512 Arabidopsis thaliana chromosome 1 sequence",
          "sequence": sequence, "sequence_sha256": evo._sha(sequence),
          "source": "NCBI Nucleotide efetch", "fetched_at": lab.now_iso(),
          "truth_status": "public_reference_sequence_receipt"}
assert evo._validate_payload(source) == sequence
for bad in (dict(source, taxon_id=9606), dict(source, organism="human"),
            dict(source, source_header=">NC_000001.1:1-512 wrong source"),
            dict(source, sequence_sha256="wrong"), dict(source, source_key="invented")):
    try: evo._validate_payload(bad); raise AssertionError("unsafe or unattested source accepted")
    except ValueError: pass

# The public run path accepts a source key, not caller-supplied sequence or generation text.
evo.fetch_source = lambda source_key="arabidopsis_chr1": dict(source)
model_result = {"ok": True, "model": evo.MODEL, "source_key": "arabidopsis_chr1",
                "source_accession": "NC_003070.9", "taxon_id": 3702,
                "sequence_sha256": source["sequence_sha256"], "sequence_length": 512,
                "variant": {"position_zero_based": 256, "from": "A", "to": "C"},
                "reference_mean_log_likelihood": -0.4, "variant_mean_log_likelihood": -0.5,
                "variant_delta": -0.1,
                "truth_status": "evo2_model_likelihood_delta_not_functional_effect"}
calls = []
evo._lms = lambda *args: calls.append(args) or types.SimpleNamespace(returncode=0, stdout="", stderr="")
real_run = subprocess.run
evo.subprocess.run = lambda *a, **k: types.SimpleNamespace(returncode=0, stdout=json.dumps(model_result) + "\n", stderr="")
evo.time.sleep = lambda seconds: None
row = evo.analyze()
repeated = evo.analyze()
evo.subprocess.run = real_run
assert row["ok"] and row["gemma_restored"] is True and "sequence" not in row
assert row["run_id"] != repeated["run_id"] and row["result_sha256"] == repeated["result_sha256"]
assert calls and all(call[:2] == ("unload", lab.LLM_MODEL) for call in calls), calls
assert lab._jsonl(evo.RUNS)[-1]["truth_status"] == "evo2_model_likelihood_delta_not_functional_effect"

receipt = probe.record_evo2_run(row)
assert receipt["outcome"] == "proved_by_run" and receipt["tool"] == "evo2"
assert lab.tools_status()["evo2"]["available"] is True
assert "sequence_sha256" not in receipt["evidence"], "visible tool receipt keeps a digest, not source material"

# A genome turn is part of the same checkpointed loop and a Gemma reflection follows it.
lab.set_enabled(True)
cfg = lab.config(); cfg["evo2_enabled"] = True; lab._atomic(lab.CONFIG, cfg)
lab._atomic(lab.STATE, {"phase": "genome", "turns": 480})
sys.modules["chemistry_evo2"] = types.SimpleNamespace(analyze=lambda: dict(row))
sys.modules["chemistry_probe"] = types.SimpleNamespace(record_evo2_run=lambda result: receipt)
@contextlib.contextmanager
def admitted(*args, **kwargs): yield object()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
first = lab.tick()
assert first["kind"] == "genome_prediction" and first["next_phase"] == "genome_reflect"
lab._reflect_genome = lambda context, result: {"attention": "the likelihood changed",
    "factual_observation": "the model assigned a lower mean likelihood",
    "speculative_reading": "this opens a question", "next_question": "which contexts change the delta?"}
second = lab.tick()
assert second["kind"] == "genome_reflection" and second["next_phase"] == "orient"
notes = lab._jsonl(lab.NOTEBOOK)
assert notes[-2]["truth_status"] == "evo2_model_likelihood_delta_not_functional_effect"
assert notes[-1].get("entry_id") and "named_speculation" in notes[-1]["truth_status"]
assert lab.set_evo2_enabled(False)["genomics"]["enabled"] is False
assert lab.set_evo2_enabled(True)["genomics"]["enabled"] is True

source_text = open(os.path.join(REPO, "scripts", "chemistry_evo2.py")).read()
assert ".generate(" not in source_text and "usage: chemistry_evo2.py run" in source_text
assert "human targeting" not in json.dumps(row).lower()
print("31/31 passed")
