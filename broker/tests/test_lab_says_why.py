#!/usr/bin/env python3
"""A failed source says why, and a DNA question Atlas did not answer is not answered with a protein.

2026-09-29, her Lab screen: he asked whether a C>G variant at chr1:161021137 changes F11R expression.
Atlas failed and the Lab showed only "source_query_unavailable:RuntimeError"; the worker's reason was
discarded twice. The Lab then embedded the F11R protein UniProt had matched and wrote a protein review
restating an old ATAC score.

Scratch HOME; the source client, the Atlas worker and the literature reader are stubs; nothing here
reaches the network.
"""
import contextlib, importlib.util, os, subprocess, sys, tempfile, types
from pathlib import Path

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-lab-why-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos.")
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

# --- the Atlas worker says why, and never says the key ------------------------------------------------
import lab_atlas_worker as W
said = W.failure(PermissionError("denied for key sk-SECRET-123 on\nscorer RNA_SEQ"), "sk-SECRET-123")
check("the worker's failure line names the error and hides the key",
      said == "PermissionError: denied for key [key] on scorer RNA_SEQ", said)

import numpy as np
raw = np.zeros((30, 10)); raw[:, 7] = 5; raw[:, 2] = -9; raw[0, 4] = float("nan")
check("an oversized Atlas matrix keeps its strongest tracks instead of failing the question",
      W.strongest_tracks(raw, limit=60) == [2, 7], W.strongest_tracks(raw, limit=60))
check("a matrix within the limit keeps every track", W.strongest_tracks(raw, limit=1000) == list(range(10)))

import lab_sources as S
key = Path(HOME) / "atlas.key"; key.write_text("sk-SECRET-123"); key.chmod(0o600)
fake = Path(HOME) / "fake-python"
fake.write_text("#!/bin/sh\nprintf 'ValueError: scorer RNA_SEQ unknown' > \"$(dirname \"$3\")/error.txt\"\nexit 1\n")
fake.chmod(0o755)
try:
    S.AtlasProcess(str(key), python=str(fake))({"source": "atlas"}); why = ""
except RuntimeError as exc:
    why = str(exc)
check("a failed Atlas query carries the worker's reason", why == "Atlas query failed: ValueError: scorer RNA_SEQ unknown", why)
silent = Path(HOME) / "silent-python"; silent.write_text("#!/bin/sh\nexit 3\n"); silent.chmod(0o755)
try:
    S.AtlasProcess(str(key), python=str(silent))({"source": "atlas"}); why = ""
except RuntimeError as exc:
    why = str(exc)
check("a worker that dies before saying why is reported as that", "exited 3 before saying why" in why, why)

# --- the Lab keeps the reason, and does not answer a DNA question with a protein ----------------------
spec = importlib.util.spec_from_file_location("chemistry_lab_why_test", os.path.join(REPO, "scripts", "chemistry_lab.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
sys.modules["chemistry_lab"] = M
check("the suite runs in a scratch workspace", HOME in M.ROOT and not M.ROOT.startswith("/home/gloria"), M.ROOT)

@contextlib.contextmanager
def admitted(*a, **k): yield types.SimpleNamespace()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
M.set_enabled(True)

import chemistry_sources as CS
class Failing:
    def query(self, spec): raise RuntimeError("Atlas query failed: ValueError: scorer RNA_SEQ unknown")
CS.configured_sources = lambda: Failing()
CS.flush_reports = lambda: None
cfg = M.config(); cfg["allow_public_database_reads"] = True; M._atomic(M.CONFIG, cfg)
try:
    CS.query({"source": "atlas"}, question="q"); kept = ""
except RuntimeError as exc:
    kept = str(exc)
check("the Lab's source error keeps the reason, not only its type",
      kept == "source_query_unavailable:RuntimeError: Atlas query failed: ValueError: scorer RNA_SEQ unknown", kept)

os.unlink(os.path.join(M.ROOT, "source-throttle.json"))   # the real query above set Atlas's one-minute cooldown
def raising(spec_, question="", **k):
    raise RuntimeError(kept)
sys.modules["chemistry_sources"] = types.SimpleNamespace(query=raising, flush_reports=lambda: None)
VARIANT = {"browse_lane": "protein", "question": "Does the C>G variant at chr1:161021137 lower F11R expression?",
           "source_query": {"source": "atlas", "assembly": "GRCh38", "chromosome": "chr1", "start": 161021136, "end": 161021137},
           "uniprot_query": "reviewed:true AND gene:F11R", "plugin_query": None}
F11R = [{"accession": "Q9Y624", "protein_name": "Junctional adhesion molecule A", "sequence": "MGTKAQ"}]
reads = []
M._gather_material = lambda state, inquiry, fresh_only=False: reads.append(inquiry.get("question")) or None

M._atomic(M.STATE, {"phase": "sources", "turns": 10, "inquiry": dict(VARIANT), "records": list(F11R)})
turn = M.tick()
note = M._jsonl(M.NOTEBOOK)[-1]
check("the notebook shows why Atlas failed", note["kind"] == "source_unavailable" and "scorer RNA_SEQ unknown" in note["reason"], note)
check("a DNA question Atlas did not answer goes to the next question, not to embedding the protein",
      turn["next_phase"] == "orient" and note.get("genome_question_unanswered") is True
      and "inquiry" not in M._load(M.STATE, {}), turn)
check("the literature on it was looked for first", reads == [VARIANT["question"]], reads)

def literature(state, inquiry, fresh_only=False):
    state["material"] = {"records": [{"pmid": "1", "title": "F11R regulation"}]}; return True
M._gather_material = literature
M._atomic(M.STATE, {"phase": "sources", "turns": 11, "inquiry": dict(VARIANT), "records": list(F11R)})
turn = M.tick()
note = M._jsonl(M.NOTEBOOK)[-1]
check("when the literature holds something on it, he reads that instead",
      turn["next_phase"] == "reflect" and note.get("literature_instead") == 1, (turn, note))

def answering(spec_, question="", **k):
    return {"receipt": {"receipt_id": "A" * 64, "response_sha256": "e" * 64, "source": "atlas",
                        "records": [{"scorer": "ATAC", "score": -0.55}]}}
sys.modules["chemistry_sources"] = types.SimpleNamespace(query=answering, flush_reports=lambda: None)
M._atomic(M.STATE, {"phase": "sources", "turns": 12, "inquiry": dict(VARIANT), "records": list(F11R)})
turn = M.tick()
check("an Atlas answer still goes on as before", turn["next_phase"] in ("embed", "atlas_genome"), turn)

check("nothing reached the world: the source client and literature reader were stubs",
      sys.modules["chemistry_sources"].query is answering and M._gather_material is literature)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
