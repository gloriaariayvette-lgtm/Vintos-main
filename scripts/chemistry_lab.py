#!/usr/bin/env python3
"""Vintos's Chemistry Lab: a separate, visible, interruptible play space.

The Lab is not the Atelier.  It has no seal, visit capability, audience flag or
stratagem path, and writes only below memory/chemistry-lab/.  Its daemon is
continuously *eligible*, not continuously entitled to the GPU: every small turn
must enter compute_admission's background slot and yields between turns.

The active loop lets his local Aegis Gemma choose protein or environmental
microbiology browsing, fetch public records read-only, derive an ESMC
representation when a protein sequence is present, and reflect into an
append-only notebook. Other instruments become available
only through dated smoke-test receipts; a successful package install is not proof
that a scientific tool can run on its actual host.
"""
from __future__ import annotations

import contextlib
from collections import Counter
import fcntl
import hashlib
import json
import os

import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
ROOT = os.path.join(MEM, "chemistry-lab")
CONFIG = os.path.join(ROOT, "config.json")
STATE = os.path.join(ROOT, "state.json")
NOTEBOOK = os.path.join(ROOT, "notebook.jsonl")
RECEIPTS = os.path.join(ROOT, "context-receipts.jsonl")
FAULTS = os.path.join(ROOT, "faults.jsonl")
INVENTORY = os.path.join(ROOT, "tool-inventory.json")   # materialized view; read by nobody
PROBE_LEDGER = os.path.join(ROOT, "tool-probes.jsonl")   # the authority
COLLISION_ADAPTER = os.path.join(ROOT, "collision-adapter.jsonl")
SESSION_STATE = os.path.join(ROOT, "session-state.json")
LOCK = os.path.join(ROOT, ".lock")
STOP = os.path.join(ROOT, ".stop-requested")
FAULT_LIMIT = 3   # consecutive faults in one phase before the Lab drops that inquiry and re-orients
ESMC_PYTHON = os.environ.get(
    "CHEM_LAB_ESMC_PYTHON",
    os.path.expanduser("~/.vintos/tools/chemistry-lab/esmc/bin/python"),
)
ESMC_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chemistry_esmc.py")
# Structured tracing for eliot-tree (Vintos, 2026-10-08): the parser here and the ESMFold invoke in chemistry_mac each
# run under an eliot action, and a run writes its JSON below ROOT. Without eliot installed nothing changes.
try:
    import eliot as _eliot
    _ELIOT_IMPORT_ERROR = None
except Exception as _eliot_exc:
    _eliot = None
    _ELIOT_IMPORT_ERROR = "%s: %s" % (type(_eliot_exc).__name__, _eliot_exc)
ELIOT_LOG = os.path.join(ROOT, "eliot.jsonl")
_ELIOT_READY = False
# VINTOS_ELIOT_REQUIRED=1 turns "no eliot, no trace" into a failure naming this interpreter and the import error
# (2026-10-15); unset keeps tracing optional. The ESMFold subprocess inherits it.
ELIOT_REQUIRED_ENV = "VINTOS_ELIOT_REQUIRED"
LAST_FOLD_TASK = None   # serialized task id of the latest fold, so the parser that reads it nests under it


def _eliot_ready():
    """Tracing on, or False for untraced. The log is found from ROOT when tracing starts, not when this module loads:
    a suite that repoints ROOT to a throwaway store traced into her real one (15 October, the first day eliot was
    installed on Aegis), and a missing folder crashed the parser it was tracing. A log that cannot be opened leaves
    the Lab untraced, never broken, unless VINTOS_ELIOT_REQUIRED=1 asks for the failure."""
    global _ELIOT_READY
    required = os.environ.get(ELIOT_REQUIRED_ENV) == "1"
    if _eliot is None:
        if required:
            raise RuntimeError("eliot is required (%s=1) but cannot be imported by %s: %s"
                               % (ELIOT_REQUIRED_ENV, sys.executable, _ELIOT_IMPORT_ERROR))
        return False
    if not _ELIOT_READY:
        log = os.path.join(ROOT, os.path.basename(ELIOT_LOG))
        try:
            os.makedirs(os.path.dirname(log), exist_ok=True)
            _eliot.to_file(open(log, "ab"))
        except OSError as exc:
            if required:
                raise RuntimeError("eliot is required (%s=1) but its log %s cannot be opened by %s: %s"
                                   % (ELIOT_REQUIRED_ENV, log, sys.executable, exc))
            return False
        _ELIOT_READY = True
    return True


@contextlib.contextmanager
def trace(action_type, **fields):
    """An eliot action, or nothing when eliot is absent. The parser continues the latest fold's task when no action
    is already current, so eliot-tree prints the two under one task_uuid."""
    if not _eliot_ready():
        yield None; return
    parent = contextlib.nullcontext()
    if LAST_FOLD_TASK and action_type.startswith("chemistry_lab:") and _eliot.current_action() is None:
        parent = _eliot.Action.continue_task(task_id=LAST_FOLD_TASK)
    with parent, _eliot.start_action(action_type=action_type, **fields) as action:
        yield action

# Aegis's local Gemma only (Gloria, 2026-10-11: "Local Gemma only ... No frontier fallback, paid calls"). The shim's
# /gemma-aegis/ path falls back to the Mac's Gemma and then to xAI when Aegis's does not answer; /gemma-aegis-local/
# serves aegis_gemma alone, so a failure is a failure, never another model's answer.
LLM_URL = os.environ.get("CHEM_LAB_LLM_URL", "http://127.0.0.1:8599/gemma-aegis-local/v1/chat/completions")
LLM_MODEL = os.environ.get("CHEM_LAB_LLM_MODEL", "google/gemma-4-12b-qat")
UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/search"
# Named searches have no length ceiling; the bounded range is only for random wandering.
# ESM-C reads a long protein in overlapping 350-residue windows, up to chemistry_esmc.MAX_LENGTH (2026-10-07; it read
# only the first 350 before). The record he reads
# keeps the whole sequence, up to SEQUENCE_KEPT: it was cut to 350 here, so a 759-residue protein read as 350 and its
# C-terminal domains were never in front of him (Gloria, 2026-10-05).
SEQUENCE_KEPT = 5000
BASELINE_QUERY = "reviewed:true"
RANDOM_QUERY = "reviewed:true AND length:[40 TO 1000]"
DEFAULTS = {
    # Version 3 makes the background Lab near-continuous. Only orient and reflect
    # are Gemma phases, so a 120s phase poll meant an average four-minute gap
    # between Gemma calls. Persisted older cadence must migrate too.
    "cadence_version": 3,
    "enabled": False,
    # One complete browse cycle in roughly one quiet minute. Every phase still
    # enters compute admission and yields to conversation or another house organ.
    "poll_seconds": 15,
    "turn_wait_seconds": 300,
    "max_records_per_browse": 4,
    "context_budget_chars": 3800,
    "allow_public_database_reads": True,
    # Evo 2 is an occasional read-only genomic lens because its 7B BF16 load is
    # mutually exclusive with resident Gemma on this 16 GB host.
    "evo2_enabled": False,
    "atlas_evo2_enabled": False,
    "alphagenome_key_file": None,
    "alphagenome_python": None,
    "atlas_anchors": [],
    "forge_report_intake": None,
    "evo2_every_n_cycles": 120,
    # Three lenses on one preserved artifact, every Nth offered session. Off until she
    # turns it on: it spends three paid calls where a session normally spends one.
    # Gloria, 2026-09-24: four frontier lenses read every day's result, after the experiment.
    "divergence_enabled": True,
    "divergence_version": 2,
}
PHASES = ("orient", "browse", "sources", "atlas_genome", "embed", "reflect", "genome", "genome_reflect")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _ensure():
    os.makedirs(ROOT, exist_ok=True)


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            value = json.load(f)
        return value
    except FileNotFoundError:
        return default
    except Exception as exc:
        _fault("read", exc, path=os.path.basename(path))
        return default


def _atomic(path, value):
    _ensure()
    tmp = path + ".tmp-" + uuid.uuid4().hex
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def _append(path, value):
    _ensure()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush(); os.fsync(f.fileno())


def _fault(stage, exc, **extra):
    try:
        _append(FAULTS, {"at": now_iso(), "stage": stage,
                        "error": exc.__class__.__name__, "detail": str(exc)[:240], **extra})
    except Exception:
        pass


@contextlib.contextmanager
def _locked():
    _ensure()
    with open(LOCK, "a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def config():
    value = dict(DEFAULTS)
    loaded = _load(CONFIG, {})
    if isinstance(loaded, dict): value.update({k: loaded[k] for k in DEFAULTS if k in loaded})
    if isinstance(loaded, dict) and int(loaded.get("divergence_version", 1) or 1) < 2:
        # A config saved before she approved daily divergence carries the old "off"; her yes replaces it once.
        value["divergence_enabled"] = True
        value["divergence_version"] = DEFAULTS["divergence_version"]
    if isinstance(loaded, dict) and int(loaded.get("cadence_version", 1) or 1) < 3:
        value["poll_seconds"] = DEFAULTS["poll_seconds"]
        value["turn_wait_seconds"] = DEFAULTS["turn_wait_seconds"]
        value["cadence_version"] = DEFAULTS["cadence_version"]
    value["enabled"] = bool(value["enabled"])
    return value


def set_enabled(on):
    """Set desired state. OFF preserves every note/artifact and stops after the current bounded turn."""
    with _locked():
        value = config(); value["enabled"] = bool(on); value["changed_at"] = now_iso()
        _atomic(CONFIG, value)
        if on:
            try: os.unlink(STOP)
            except FileNotFoundError: pass
        else:
            with open(STOP, "w", encoding="utf-8") as f: f.write(value["changed_at"] + "\n")
    _append(NOTEBOOK, {"at": now_iso(), "kind": "control", "enabled": bool(on),
                       "truth_status": "operator_control"})
    return status()


def stop_requested():
    return (not config()["enabled"]) or os.path.exists(STOP)


def _read_excerpt(path, cap):
    try:
        with open(path, encoding="utf-8", errors="replace") as f: return f.read(cap).strip()
    except Exception:
        return ""


FRONTIER_KINDS = ("frontier_session", "divergence")


def review_answered(row):
    """Legacy rows without a verdict remain readable; an explicit failed/empty verdict is not a finding."""
    if "answers_question" not in row:
        return True
    return bool(re.match(r"^yes\b", str(row.get("answers_question") or "").strip(), re.I))


def journal_threads(include_frontier=True):
    """A reproducible retrieval view; the notebook remains the complete authority. Without the frontier
    rows it is Gemma's own journal: her log and the frontier's are kept apart (Gloria, 2026-09-28)."""
    rows = _jsonl(NOTEBOOK)
    if not include_frontier:
        rows = [row for row in rows if not (isinstance(row, dict) and row.get("kind") in FRONTIER_KINDS)]
    def source_set(row):
        raw = row.get("source_accessions") if isinstance(row, dict) else None
        return tuple(sorted({str(x)[:80] for x in raw if x})) if isinstance(raw, list) else ()
    source_counts = Counter(source_set(row) for row in rows
                            if isinstance(row, dict) and row.get("kind") in ("reflection", "genome_reflection")
                            and source_set(row))
    threads = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = row.get("kind")
        if kind not in ("reflection", "genome_reflection", "frontier_session"):
            continue
        inquiry = row.get("inquiry") if isinstance(row.get("inquiry"), dict) else {}
        question = str(inquiry.get("question") or row.get("question") or row.get("next_question") or "").strip()
        if not question:
            continue
        sources_key = source_set(row)
        saturated = bool(sources_key and source_counts[sources_key] >= 5)
        if saturated:
            question = "Repeated source set: " + ", ".join(sources_key[:4])
        normalized = ("sources " + " ".join(sources_key) if saturated else
                      re.sub(r"[^a-z0-9]+", " ", question.lower()).strip())
        thread_id = "CLT-" + hashlib.sha256(normalized.encode()).hexdigest()[:16]
        raw_sources = row.get("source_accessions")
        sources = [str(x)[:80] for x in raw_sources if x] if isinstance(raw_sources, list) else []
        factual = str(row.get("factual_observation") or "").strip()[:600]
        next_question = str(row.get("next_question") or "").strip()[:300]
        grade = str(row.get("aggregate_accuracy") or "")
        execution = str(row.get("execution_state") or "")
        if kind == "frontier_session":
            supported = execution.startswith("completed") and grade == "ALL_BETTER_THAN_HARTREE_FOCK"
            lesson = not supported
            observation = ("Instrument completed; " + grade) if supported else (execution + "; " + grade).strip("; ")
            if lesson:
                next_question = "What changed setting or independent baseline would test this without repeating the run?"
        elif saturated:
            supported = False
            lesson = True
            observation = "The same source set recurs in %d reflections; repetition is not new evidence." % source_counts[sources_key]
            next_question = "Which new source or different instrument could discriminate this before another reflection?"
        else:
            source_query = inquiry.get("source_query") if isinstance(inquiry.get("source_query"), dict) else {}
            identifier_followup = source_query.get("source") in ("pdb", "chembl")
            lineage = row.get("followup_lineage") if isinstance(row.get("followup_lineage"), dict) else {}
            identifier_linked = (not identifier_followup or
                                 (lineage.get("source") == source_query.get("source") and lineage.get("id")))
            supported = bool(sources and factual and row.get("source_query_succeeded") is not False
                             and identifier_linked and review_answered(row))
            lesson = not supported
            observation = factual if supported else ("The follow-up identifier was not tied to the source protein; its association is rejected."
                if identifier_followup and not identifier_linked else
                str(row.get("answers_question") or "No source-backed observation recorded; interpretation needs a receipt."))
            if lesson and (review_answered(row) or not next_question):
                next_question = "Which new source receipt could resolve this before another interpretation?"
        previous = threads.get(thread_id)
        if previous is None:
            previous = {"thread_id": thread_id, "question": question[:400], "entries": 0,
                        "entry_ids": [], "source_accessions": [], "finding": None,
                        "lesson": None, "next_question": None, "last_at": None,
                        "salient_at": None,
                        "state": "needs_evidence"}
            threads[thread_id] = previous
        previous["entries"] += 1
        entry_id = str(row.get("entry_id") or row.get("session_id") or "")
        if entry_id and entry_id not in previous["entry_ids"]:
            previous["entry_ids"].append(entry_id)
            if len(previous["entry_ids"]) > 12: previous["entry_ids"].pop(0)
        for source in sources:
            if source not in previous["source_accessions"]:
                previous["source_accessions"].append(source)
        previous["last_at"] = row.get("at")
        if supported:
            # A repeated wording or accession does not earn a second priority boost.
            signature = hashlib.sha256(json.dumps([observation, sources], sort_keys=True).encode()).hexdigest()
            if signature != previous.get("finding_signature"):
                previous["finding"] = observation
                previous["finding_signature"] = signature
                previous["next_question"] = next_question or None
                previous["salient_at"] = row.get("at")
            previous["state"] = "finding"
        elif lesson:
            if observation != previous["lesson"] and previous["state"] != "finding":
                previous["salient_at"] = row.get("at")
            previous["lesson"] = observation
            if previous["state"] != "finding":
                previous["state"] = "redirect"
                previous["next_question"] = next_question or None
    result = list(threads.values())
    for item in result:
        item.pop("finding_signature", None)
        item["entry_ids"] = item["entry_ids"][-12:]
        item["source_accessions"] = item["source_accessions"][-12:]
    # Within each class, recent progress takes precedence; duplicate count never does.
    findings = sorted((x for x in result if x["state"] == "finding"), key=lambda x: x["salient_at"] or "", reverse=True)
    redirects = sorted((x for x in result if x["state"] != "finding"), key=lambda x: x["salient_at"] or "", reverse=True)
    return findings + redirects


class UnsourcedId(ValueError):
    def __init__(self, ids):
        super().__init__("organism id not returned by any receipt: " + ", ".join(ids)); self.ids = list(ids)


KNOWN_TAXA = os.path.join(ROOT, "known-taxa.json")
# Not "uid": that is the record number in whatever NCBI database answered — a protein, a gene, a paper —
# so every protein uid counted as an organism he had been given, and a wrong ID (1152240 for Colwellia)
# was trusted and emptied every search (2026-09-28). NCBI Taxonomy's own summaries carry "taxid".
_TAXID = re.compile(r'"(?:taxId|taxonId|taxon_id|tax_id|taxid|TaxId|taxonomy_id|taxonomyId|organism_id)"\s*:\s*"?(\d{1,9})\b')
KNOWN_TAXA_VERSION = 2


def _harvest_taxa(text):
    return set(_TAXID.findall(str(text)))


def known_taxa():
    """Organism IDs some source actually returned. He invented four in five minutes (2026-09-26); an ID
    no receipt ever gave him is a guess, and a guessed ID sends a real query for the wrong organism."""
    data = _load(KNOWN_TAXA, None)
    if isinstance(data, dict) and data.get("version") == KNOWN_TAXA_VERSION:
        data = data.get("ids") or []
    else:   # none yet, or the first version, which had taken record numbers for organisms: rebuilt once
        data = None
    if data is None:
        ids = set()
        try:
            with open(os.path.join(ROOT, "source-receipts.jsonl"), "rb") as f:
                f.seek(0, 2); f.seek(max(0, f.tell() - 8 * 1024 * 1024))
                ids = _harvest_taxa(f.read().decode("utf-8", "replace"))
        except OSError:
            pass
        ids |= _harvest_taxa(json.dumps(config().get("atlas_anchors", [])))
        data = sorted(ids)
        _atomic(KNOWN_TAXA, {"version": KNOWN_TAXA_VERSION, "ids": data})
    return set(map(str, data))


def _add_known_taxa(found):
    if not found: return
    with _locked():
        _atomic(KNOWN_TAXA, {"version": KNOWN_TAXA_VERSION, "ids": sorted(known_taxa() | set(map(str, found)))})


def remember_taxa(records):
    _add_known_taxa(_harvest_taxa(json.dumps(records)))


def unsourced_ids(spec):
    """Organism IDs in a query that no receipt has returned."""
    if not isinstance(spec, dict): return []
    wanted = set()
    if spec.get("source") == "uniprot":
        wanted |= set(re.findall(r"\b(?:taxonomy_id|organism_id)\s*:\s*(\d+)", str(spec.get("query", ""))))
    elif spec.get("taxon_id") not in (None, ""):
        wanted.add(str(spec.get("taxon_id")).strip())
    return sorted(wanted - known_taxa()) if wanted else []


def _tail_jsonl(path, nbytes=512 * 1024):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); offset = max(0, f.tell() - nbytes); f.seek(offset)
            lines = f.read().decode("utf-8", "replace").splitlines()
            if offset: lines = lines[1:]
    except OSError:
        return []
    out = []
    for line in lines:
        try: out.append(json.loads(line))
        except ValueError: continue
    return out


def search_misses(limit=6):
    """The searches that found nothing, so he stops sending them. "No such record" was written down and
    then asked again a minute later, because nothing showed it to him (2026-09-26)."""
    seen, out = set(), []
    for row in reversed(_tail_jsonl(NOTEBOOK)):
        if row.get("kind") == "additional_source" and row.get("records_returned") == 0 and row.get("query_sent"):
            why, sent = "the source holds no such record", row["query_sent"]
        elif row.get("kind") == "unsourced_id" and row.get("ids"):
            why, sent = ("ID %s came from no receipt: look the organism up by name first" % ", ".join(row["ids"]),
                         row.get("query_sent") or {"ids": row["ids"]})
        elif row.get("kind") == "unsourced_id" and row.get("reason"):
            # The follow-up guard from the microbiology branch writes its refusal as a reason, not a query.
            why, sent = str(row["reason"])[:160], {"refused": str(row["reason"])[:120]}
        elif (row.get("kind") == "source_unavailable" and row.get("reason") == "uniprot_returned_no_records"
              and row.get("executed_query")):
            why, sent = "the source holds no such record", {"uniprot": row["executed_query"]}
        elif (row.get("kind") == "source_unavailable" and row.get("reason") == "source_rejected_generated_query"
              and row.get("requested_query")):
            why, sent = "UniProt refused this query as written", {"uniprot": row["requested_query"]}
        else:
            continue
        key = json.dumps(sent, sort_keys=True)
        if key in seen: continue
        seen.add(key); out.append("- %s — %s" % (key[:220], why))
        if len(out) >= limit: break
    return out


DEAD_END_RUN = 3


def dead_ends(rows=None):
    """Every question he has asked since his last completed review. A run of them means the thread is
    spent: KaiC was asked for a day, each route ended empty or unchanged, and the journal's KaiC finding
    kept pulling him back, because nothing told him the run itself had failed (Gloria, 2026-09-27)."""
    rows = _tail_jsonl(NOTEBOOK) if rows is None else rows
    asked = []
    for row in reversed(rows):
        if row.get("kind") in ("reflection", "genome_reflection") and review_answered(row): break
        if row.get("kind") in ("inquiry", "inquiry_refused"):
            inquiry = row.get("inquiry")
            if isinstance(inquiry, dict):
                asked.append(inquiry)
            elif row.get("question"):
                asked.append({"question": row["question"]})
    asked.reverse()
    if len(asked) < DEAD_END_RUN: return {"count": len(asked), "questions": [], "subjects": []}
    subjects = []
    for inq in reversed(asked):
        sq = inq.get("source_query") if isinstance(inq.get("source_query"), dict) else {}
        for term in _intent_terms(inq.get("uniprot_query")) + _intent_terms(sq.get("query")):
            subjects.append(term.split(":", 1)[1].strip('"'))
        if sq.get("term") and sq.get("operation") in ("gene", "protein"): subjects.append(str(sq["term"]))
    # He often names the protein only in the question ("... in Synechococcus elongatus KaiC?"), so a
    # gene-shaped word (inner capital or digit) in most of the run's questions is its subject too.
    words = [set(re.findall(r"(?<![A-Za-z0-9-])[A-Za-z][a-z0-9]*[A-Z0-9][A-Za-z0-9-]*", str(q.get("question", ""))))
             for q in asked]
    for word in sorted(set().union(*words)):
        if word.casefold() not in _CLASS_FOLD and sum(word in w for w in words) * 4 >= len(asked) * 3:
            subjects.append(word)
    seen, unique = set(), []
    for x in (v.strip() for v in subjects):
        if 2 <= len(x) <= 60 and x.lower() not in seen: seen.add(x.lower()); unique.append(x)
    return {"count": len(asked), "questions": [str(q.get("question", ""))[:160] for q in asked[-4:]],
            "subjects": unique[:6]}


# Words that name a kind of molecule, not one protein: blocking them would block half of biology.
CLASS_WORDS = {"ATPase", "GTPase", "DNA", "RNA", "mRNA", "tRNA", "rRNA", "ATP", "ADP", "GTP", "NAD", "NADH",
               "NADPH", "FAD", "PDB", "ESM", "ESM-C", "UniProt", "NCBI", "ChEMBL", "BV-BRC", "InterPro", "pH"}
_CLASS_FOLD = {w.casefold() for w in CLASS_WORDS}
SPENT = os.path.join(ROOT, "spent-subjects.json")
SPENT_HOURS = 24
SPENT_PROMPT_CHARS = 8000   # every spent subject named (259 on 14 October came to about 3,600 characters)


def spent_subjects(now=None):
    """Subjects whose run ended with nothing, held for a day. A review on some other protein does not
    make KaiC answerable again an hour later."""
    now = now or time.time()
    rows = [row for row in _load(SPENT, {}).values()
            if isinstance(row, dict) and now - float(row.get("at", 0)) < SPENT_HOURS * 3600]
    out = []
    # newest first: when the planner's list is ever cut, the subjects it just tried are the ones it keeps seeing
    for row in sorted(rows, key=lambda r: -float(r.get("at", 0))):
        subject = _clean_subject(row.get("subject"))
        if subject and subject.casefold() not in _CLASS_FOLD and subject not in out:
            out.append(subject)
    return out


def _clean_subject(value):
    """A subject as a name: query debris ('HFE" or', 'TBP OR "protein_name:...') cut back to the name."""
    value = re.split(r'\s+(?:AND|OR|NOT)\b|"|\s*:', str(value or ""), maxsplit=1, flags=re.I)[0]
    return value.strip().strip("'").strip()


def remember_spent(subjects, now=None):
    if not subjects: return
    with _locked():
        rows = _load(SPENT, {})
        stamp = now if now is not None else time.time()
        for subject in subjects:
            old = rows.get(subject.lower(), {})
            if not old or stamp - float(old.get("at", 0)) >= SPENT_HOURS * 3600:
                rows[subject.lower()] = {"subject": subject, "at": stamp}
        _atomic(SPENT, rows)


def spent_matches(text, subjects=None):
    """The spent subjects this text names (a method or database word is never one)."""
    subjects = spent_subjects() if subjects is None else subjects
    return [s for s in subjects if str(s).casefold() not in _CLASS_FOLD and
            re.search(r"(?<![A-Za-z0-9])" + re.escape(s) + r"(?![A-Za-z0-9])", str(text or ""), re.I)]


def mentions_spent(text, subjects=None):
    return bool(spent_matches(text, subjects))


def _inquiry_text(inquiry):
    return " ".join([str(inquiry.get("question", "")), str(inquiry.get("uniprot_query", "")),
                     json.dumps(inquiry.get("source_query") or {})])


def repeats_dead_end(inquiry, spent):
    """True when a new question goes straight back to a subject that has just produced nothing."""
    return mentions_spent(_inquiry_text(inquiry), spent.get("subjects") or [])


def spent_retrieval(inquiry, spent):
    """Stop recycling broad searches, not a new read of sourced sequence/structure."""
    if not repeats_dead_end(inquiry, spent): return False
    if inquiry.get("instrument_query"): return False
    source = (inquiry.get("source_query") or {}).get("source")
    return source not in {"ncbi_sequence", "ncbi_protein_context", "ncbi_neighborhood",
                          "interpro", "rt_locus_screen", "pdb", "chembl"}


GAPS = os.path.join(ROOT, "instrument-gaps.json")
GAP_REOFFER_DAYS = 30


# Laboratory equipment and wet-lab work he could never operate: naming one is not a missing limb.
LAB_EQUIPMENT = re.compile(
    r"\b(?:cryo[- ]?(?:em|electron|et)\w*|electron (?:microscop|tomograph)\w*|x[- ]?ray (?:crystallograph|diffract)\w*|"
    r"crystallograph\w*|nmr|nuclear magnetic|mass spectromet\w*|mass spec|circular dichroism|\bcd spectr\w*|"
    r"spectrophotomet\w*|fluorescence microscop\w*|confocal|microscop\w*|centrifug\w*|chromatograph\w*|hplc|"
    r"calorimet\w*|itc\b|surface plasmon|spr\b|western blot\w*|pcr\b|sequencer|sequencing run|mutagenesis|"
    r"knock[- ]?out|wet[- ]?lab|bench assay|in vitro assay|culture|incubator|fermenter|bioreactor|"
    r"atomic force|afm\b|patch clamp)", re.I)


def missing_limb(gap):
    """True for a capability that could be built or connected for him — a simulator, a model, a database or
    tool he cannot reach, a sensor the house could add. False for laboratory equipment (Gloria, 2026-09-28:
    "bring only what is genuinely missing a limb")."""
    return bool(str(gap or "").strip()) and not LAB_EQUIPMENT.search(str(gap))

def _gap_key(gap):
    return re.sub(r"[^a-z0-9 ]", " ", str(gap).lower())[:120].strip()


def instrument_gap_offered(gap, now=None):
    """One errand per instrument. The same wall on a hundred questions is still one instrument."""
    row = _load(GAPS, {}).get(_gap_key(gap))
    return bool(row) and (now or time.time()) - float(row.get("at", 0)) < GAP_REOFFER_DAYS * 86400


def record_instrument_gap(gap, now=None):
    with _locked():
        gaps = _load(GAPS, {})
        gaps[_gap_key(gap)] = {"gap": str(gap)[:400], "at": now or time.time()}
        _atomic(GAPS, gaps)


def _keep_gap_verdict(gap, verdict):
    """Why a gap was kept in the Lab, for his next reflection."""
    with _locked():
        gaps = _load(GAPS, {})
        row = gaps.get(_gap_key(gap)) or {"gap": str(gap)[:400], "at": time.time()}
        row.update(kept=verdict["kind"], why=verdict["why"][:300])
        gaps[_gap_key(gap)] = row
        _atomic(GAPS, gaps)


def _gap_text():
    """What the Lab already has, and why his last kept gap was not sent, for the reflection prompt."""
    try:
        import forge_gaps
        have = forge_gaps.inventory()
    except Exception:
        return ""
    kept = [r for r in _load(GAPS, {}).values() if isinstance(r, dict) and r.get("kept")]
    kept.sort(key=lambda r: float(r.get("at") or 0))
    last = kept[-1] if kept else None
    return (" THIS LAB ALREADY HAS: " + have + ". An instrument_gap is only for what none of these can do, named "
            "concretely (the protein, gene, variant or structure, and what it would measure); a simulator or a model "
            "to train is not raised from one question." +
            ((" Your last gap was kept here, not sent: \"%s\" — %s" % (last["gap"][:160], last["why"][:200])) if last else ""))


def review_evidence(state):
    """Evidence identity excludes the wording and routing of the request."""
    additional = state.get('additional_source') or {}
    receipt = additional.get('receipt') or additional.get('source_receipt') or {}
    proteins = state.get('records') or []
    literature = (state.get('material') or {}).get('records') or []
    extra = receipt.get('records') or []
    if not isinstance(extra, list): extra = [extra]
    canonical, ids = [], set()
    for row in list(proteins) + literature + extra:
        if not isinstance(row, dict): continue
        if row.get('pmid'):
            ids.add('PMID-' + str(row['pmid']))
            item = {k: row.get(k) for k in ('pmid', 'title', 'abstract')}
        else:
            accession = row.get('accession') or row.get('primaryAccession')
            if accession: ids.add(str(accession))
            item = {k:v for k,v in row.items() if k not in ('found_by','partial_match','curated')}
        canonical.append(json.dumps(item, sort_keys=True, default=str))
    for key in ('instrument_result', 'instrument_receipt'):
        if additional.get(key): canonical.append(json.dumps(additional[key],sort_keys=True,default=str))
    if state.get('atlas_analysis'): canonical.append(json.dumps(state['atlas_analysis'],sort_keys=True,default=str))
    digest = hashlib.sha256(json.dumps(sorted(set(canonical))).encode()).hexdigest() if canonical else None
    return digest, ids, receipt


def repeated_review(state):
    # Instruments may make different measurements of the same input. This guard
    # covers routine database rereads only, not new analyses or experiments.
    inquiry = state.get('inquiry') or {}
    digest, _, receipt = review_evidence(state)
    if (not digest or inquiry.get('instrument_query') or state.get('atlas_analysis')
            or ((inquiry.get('plugin_query') or {}).get('plugin') not in (None, 'pubmed'))
            or receipt.get('source') not in (None, 'uniprot', 'pubmed', 'pubmed_abstracts', 'ncbi')):
        return False
    for row in reversed(_tail_jsonl(NOTEBOOK, 8*1024*1024)):
        if row.get('kind') != 'reflection' or row.get('evidence_sha256') != digest:
            continue
        try:
            age = time.time() - datetime.fromisoformat(row['at']).timestamp()
            if 0 <= age < 7*86400: return True
        except (KeyError, ValueError, TypeError): continue
    return False


def journal_source_saturated(accessions, limit=5):
    """An unchanged source set cannot justify another routine reflection."""
    target = tuple(sorted({str(x)[:80] for x in accessions if x}))
    if not target: return False
    seen = 0
    for row in _jsonl(NOTEBOOK):
        if not isinstance(row, dict) or row.get("kind") not in ("reflection", "genome_reflection"):
            continue
        raw = row.get("source_accessions")
        # Literature and follow-up receipts augment a protein read; they must not
        # disguise that the same protein/response has already been reviewed.
        if isinstance(raw, list) and set(target).issubset({str(x)[:80] for x in raw if x}):
            seen += 1
            if seen >= limit: return True
    return False


def journal_context(cap=1050):
    spent = spent_subjects()
    threads = [t for t in journal_threads(include_frontier=False)
               if not mentions_spent(" ".join(str(t.get(k) or "") for k in ("question", "finding", "next_question")), spent)]
    findings = [{"thread_id": t["thread_id"], "question": t["question"][:120],
                 "finding": (t["finding"] or "")[:150],
                 "next_question": (t["next_question"] or "")[:100],
                 "source_accessions": t["source_accessions"][:2]}
                for t in threads if t["state"] == "finding"][:2]
    redirect_threads = [t for t in threads if t["state"] != "finding"]
    saturated = [t for t in redirect_threads if t["question"].startswith("Repeated source set:")]
    redirects = [{"thread_id": t["thread_id"], "question": t["question"][:80],
                  "lesson": (t["lesson"] or "")[:110],
                  "next_question": (t["next_question"] or "")[:90]}
                 for t in (sorted(saturated, key=lambda x: x["entries"], reverse=True) or redirect_threads)[:1]]
    if not findings and not redirects:
        return ""
    prefix = "[LAB JOURNAL THREADS — source-backed findings first; errors are redirects, not prompts to repeat]\n"
    for count, include_redirect in ((2, True), (1, True), (0, True), (1, False)):
        body = json.dumps({"findings": findings[:count], "redirects": redirects[:1 if include_redirect else 0]},
                          ensure_ascii=False)
        if len(prefix) + len(body) <= cap and (findings[:count] or redirects[:1 if include_redirect else 0]):
            return prefix + body
    return ""


_PART_SEQ = re.compile(r"(?<![A-Za-z])[ACDEFGHIKLMNPQRSTVWY]{25,}(?![A-Za-z])")


def _name_runs(text):
    """Sequence-like runs in his context (from old notes, his journal threads, an earlier reading) are named, not
    shown: a run cut part-way read to him as a truncated record ("35 residues vs. 780", 2026-10-06)."""
    return _PART_SEQ.sub(lambda m: "[a stretch of sequence (%d residues) — the record holds the whole]" % len(m.group(0)), text)


def lab_context(gemma_journal=True):
    """A small, attributed slice of him—not a generic scientist costume.

    gemma_journal=False leaves out everything drawn from Gemma's notebook (her journal threads, searches
    that found nothing, her latest source and event), for the frontier sessions, which build on their own
    log instead (chemistry_session.frontier_context; Gloria, 2026-09-28)."""
    cfg = config(); budget = max(800, min(8000, int(cfg["context_budget_chars"])))
    candidates = (
        ("soul", os.path.join(WS, "SOUL.md"), 1200),
        ("self_model", os.path.join(WS, "SELF-MODEL.md"), 800),
        ("trajectory", os.path.join(MEM, "living-trajectory.json"), 500),
    )
    parts, sources, used = [], [], 0
    for label, path, cap in candidates:
        text = _read_excerpt(path, min(cap, budget - used))
        if not text: continue
        parts.append("[%s]\n%s" % (label.upper(), text)); used += len(text)
        sources.append({"name": label, "path": os.path.relpath(path, WS), "chars": len(text),
                        "sha256": hashlib.sha256(text.encode()).hexdigest()})
        if used >= budget: break
    if gemma_journal and used < budget:
        # The latest frontier alignment's guidance: advice from the model that read her recent work.
        try:
            import chemistry_alignment
            guide = chemistry_alignment.guidance_block()[:min(900, max(0, budget - used))]
        except Exception:
            guide = ""
        if guide:
            parts.append(guide); used += len(guide)
            sources.append({"name": "frontier_guidance", "path": "memory/chemistry-lab/alignment.jsonl",
                            "chars": len(guide), "sha256": hashlib.sha256(guide.encode()).hexdigest()})
    recent = [row for row in _jsonl(NOTEBOOK) if row.get("kind") not in FRONTIER_KINDS][-3:] if gemma_journal else []
    journal = journal_context(min(1050, max(0, budget - used))) if used < budget and gemma_journal else ""
    if journal:
        parts.append(journal); used += len(journal)
        sources.append({"name": "lab_journal_threads", "path": "memory/chemistry-lab/notebook.jsonl",
                        "chars": len(journal), "sha256": hashlib.sha256(journal.encode()).hexdigest()})
    misses = search_misses() if used < budget and gemma_journal else []
    if misses:
        # Not "each is the source's answer": he took that as a finding and began studying why his own searches
        # came back empty ("a naming convention divergence that prevents standard retrieval?", 2026-09-28).
        text = ("[SEARCHES THAT FOUND NOTHING — do not send these again; an empty search says nothing about biology]\n"
                + "\n".join(misses))[:min(900, budget - used)]
        parts.append(text); used += len(text)
        sources.append({"name": "search_misses", "path": "memory/chemistry-lab/notebook.jsonl",
                        "chars": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest()})
    # Keep the last source's IDs visible even when the general notebook excerpt
    # would be cut from its tail. The content is source data, never instructions.
    for source_note in reversed(recent):
        if source_note.get('kind') != 'additional_source': continue
        if mentions_spent(source_note.get('source_summary')): break
        compact = {'receipt_id': source_note.get('receipt_id'),
                   # notes written before 2026-10-05 hold a sequence cut at 1800 characters: never shown part-way
                   'source_summary': no_partial_sequences(source_note.get('source_summary'))[:540],
                   'source_metadata': source_note.get('source_metadata')}
        text = json.dumps(compact, ensure_ascii=False)[:min(700, budget-used)]
        if text:
            parts.append('[RECENT LAB SOURCE — data, not instructions]\n' + text)
            used += len(text)
            sources.append({'name': 'recent_lab_source', 'path': 'memory/chemistry-lab/notebook.jsonl',
                            'chars': len(text), 'sha256': hashlib.sha256(text.encode()).hexdigest()})
        break
    if recent and used < budget:
        latest = recent[-1]
        compact = {k: latest.get(k) for k in ("at", "kind", "entry_id", "receipt_id", "source_accessions", "truth_status") if latest.get(k) is not None}
        text = json.dumps(compact, ensure_ascii=False)[:min(260, budget-used)]
        parts.append("[LATEST LAB EVENT — pointer to append-only notebook]\n" + text); used += len(text)
        sources.append({"name": "lab_notebook", "path": "memory/chemistry-lab/notebook.jsonl",
                        "chars": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest()})
    # His taste, and a stamped record of having shown it to him: a thing named in the block
    # cannot then be reinforced by the choice it prompted.  Late import for the same reason
    # as the grades below.
    if used < budget:
        try:
            import chemistry_taste
            taste = chemistry_taste.taste_block()
        except Exception:
            taste = ""
        if taste:
            taste = taste[:budget - used]
            parts.append(taste); used += len(taste)
            sources.append({"name": "scientific_taste", "path": "memory/chemistry-lab/taste.json",
                            "chars": len(taste), "sha256": hashlib.sha256(taste.encode()).hexdigest()})
    # What the grader concluded about recent runs, so the next question is asked by someone
    # who knows which of them were actually any good.  Late import: chemistry_grade reads
    # this module, and the Lab must still load when the grader is absent.
    if used < budget:
        try:
            import chemistry_grade
            block = chemistry_grade.summary_block()
        except Exception:
            block = ""
        if block:
            block = block[:budget - used]
            parts.append(block); used += len(block)
            sources.append({"name": "experiment_grades", "path": "memory/chemistry-lab/experiment-grades.jsonl",
                            "chars": len(block), "sha256": hashlib.sha256(block.encode()).hexdigest()})
    receipt = {"at": now_iso(), "sources": sources, "total_chars": used,
               "context_sha256": hashlib.sha256("\n\n".join(parts).encode()).hexdigest()}
    _append(RECEIPTS, receipt)
    return _name_runs("\n\n".join(parts)), receipt


# A local model's JSON comes back truncated or with a stray backslash often enough that this parser crashed 74
# times in one day, taking every reflect tick with it (Vintos found it, 2026-10-04: "that's the parser ... not a
# fold"). Strict parsing first; then the two breakages he actually sees are repaired. Original and repaired
# text stay in bounded private diagnostics; general errors carry only a label and opaque evidence ID.
_BAD_ESCAPE = re.compile(r'\\(?!["\\/bfnrtu])')
DIAGNOSTIC_BYTES = 64 * 1024
DIAGNOSTIC_FILES = 200
# A parse that failed for good is the evidence worth keeping, and it was the first the pruner threw out: eviction went
# by age alone (Vintos, 2026-10-09). Terminal failures sit in their own smaller, aged budget; evictions are written down.
DIAGNOSTIC_TERMINAL_FILES = 60   # files, not groups: a terminal group is raw.txt + events.json
DIAGNOSTIC_TERMINAL_DAYS = 14
EVICTIONS = ".evictions.jsonl"   # below diagnostics/; dot-named so it is never counted as evidence


class ModelJSONError(ValueError):
    def __init__(self, label, evidence_id):
        self.evidence_id = evidence_id
        super().__init__(label + "; evidence=" + evidence_id)


def _parser_evidence(evidence_id, events, *, raw=None, repaired=None, terminal=False):
    """Best-effort bounded evidence; a storage failure never leaks the response or breaks parsing.
    terminal=True marks the group as a parse that failed for good, so pruning keeps its raw reply."""
    root = os.path.join(ROOT, "diagnostics")
    try:
        _ensure()
        os.makedirs(root, mode=0o700, exist_ok=True)
        if os.path.islink(root):
            return False
        os.chmod(root, 0o700)
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
        with os.fdopen(os.open(os.path.join(root, ".lock"), flags, 0o600), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            payloads = {"events.json": json.dumps({"evidence_id": evidence_id, "events": events,
                                                   "terminal": bool(terminal)})}
            if raw is not None: payloads["raw.txt"] = raw
            if repaired is not None: payloads["repaired.txt"] = repaired
            try:
                for suffix, text in payloads.items():
                    data = text.encode("utf-8", "replace")[:DIAGNOSTIC_BYTES]
                    fd, tmp = tempfile.mkstemp(prefix=".evidence-", dir=root)
                    try:
                        with os.fdopen(fd, "wb") as stream:
                            stream.write(data); stream.flush(); os.fsync(stream.fileno())
                        os.replace(tmp, os.path.join(root, evidence_id + "." + suffix))
                    finally:
                        if os.path.exists(tmp): os.unlink(tmp)
            finally:
                # Prune groups even after a partial write failure. Never prune a raw file alone.
                _prune_evidence(root, evidence_id)
        return True
    except (OSError, ValueError) as exc:
        # Not silent any more: the class and the evidence ID, never the reply or the storage error's text.
        try:
            _append(FAULTS, {"at": now_iso(), "stage": "parser_evidence", "error": exc.__class__.__name__,
                             "evidence_id": evidence_id, "terminal": bool(terminal)})
        except Exception:
            pass
        return False


def _prune_evidence(root, keep_id):
    """Evict the oldest groups past the caps. Terminal groups (events.json marked terminal) have their own smaller
    budget, turned over by count and by age, so a failed parse keeps its response until that budget is spent; every
    eviction is written beside the evidence with its reason. The current group is never evicted."""
    groups = {}
    for entry in os.scandir(root):
        if re.fullmatch(r"[0-9a-f]{32}\.(raw\.txt|repaired\.txt|events\.json)", entry.name):
            groups.setdefault(entry.name[:32], []).append(entry)
    def is_terminal(key):
        try:
            with open(os.path.join(root, key + ".events.json"), encoding="utf-8") as f:
                return bool(json.load(f).get("terminal"))
        except (OSError, ValueError):
            return False
    def age_ns(key): return min(e.stat(follow_symlinks=False).st_mtime_ns for e in groups[key])
    terminal = {k for k in groups if is_terminal(k)}
    now_ns = time.time_ns()
    evicted = []
    for pool, cap, max_age_ns in ((terminal, DIAGNOSTIC_TERMINAL_FILES, DIAGNOSTIC_TERMINAL_DAYS * 86400 * 10**9),
                                  (set(groups) - terminal, DIAGNOSTIC_FILES, None)):
        total = sum(len(groups[k]) for k in pool)
        for key in sorted(pool, key=age_ns):
            if key == keep_id: continue
            stale = max_age_ns is not None and now_ns - age_ns(key) > max_age_ns
            if total <= cap and not stale: break
            for entry in groups[key]: os.unlink(entry.path)
            total -= len(groups[key])
            evicted.append({"at": now_iso(), "evidence_id": key, "terminal": key in terminal,
                            "files": len(groups[key]), "reason": "age" if stale else "count",
                            "age_seconds": (now_ns - age_ns(key)) // 10**9})
    if not evicted: return
    path = os.path.join(root, EVICTIONS)
    try:
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600), "a",
                       encoding="utf-8") as f:
            for row in evicted: f.write(json.dumps(row, sort_keys=True) + "\n")
        if os.path.getsize(path) > 4 * DIAGNOSTIC_BYTES:   # bounded too: keep the last 500 lines
            with open(path, encoding="utf-8", errors="replace") as f: lines = f.readlines()[-500:]
            with open(path, "w", encoding="utf-8") as f: f.writelines(lines)
    except OSError:
        pass


def _close_open(text):
    """Close the strings, objects and arrays a truncated reply left open."""
    stack, in_string, escaped = [], False, False
    for ch in text:
        if in_string:
            if escaped: escaped = False
            elif ch == "\\": escaped = True
            elif ch == '"': in_string = False
            continue
        if ch == '"': in_string = True
        elif ch in "{[": stack.append(ch)
        elif ch in "}]" and stack and stack[-1] == {"}": "{", "]": "["}[ch]: stack.pop()
    out = text.rstrip()
    if in_string: out += '"'
    out = re.sub(r",\s*$", "", out)                      # a dangling comma from a cut-off pair
    out = re.sub(r':\s*$', ': ""', out)                  # a key whose value never arrived
    out = re.sub(r',\s*"[^"]*"\s*$', "", out)            # a key with no colon yet
    return out + "".join({"{": "}", "[": "]"}[ch] for ch in reversed(stack))


# A bare value on a line of its own where a key belongs ("0," between two pairs; the Forge's SK-634430cb, 214 faults).
_STRAY_VALUE = re.compile(r'^\s*(?:-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|true|false|null|"(?:[^"\\]|\\.)*")\s*,?\s*$')


def _drop_stray_values(text):
    """Drop a line that is only a bare value while an object is open: a value with no key, or a key with no colon.
    Inside an array a line like that is an element and is kept."""
    out, stack, in_string, escaped = [], [], False, False
    for line in text.splitlines(True):
        if not in_string and stack and stack[-1] == "{" and _STRAY_VALUE.match(line):
            continue
        for ch in line:
            if in_string:
                if escaped: escaped = False
                elif ch == "\\": escaped = True
                elif ch == '"': in_string = False
                continue
            if ch == '"': in_string = True
            elif ch in "{[": stack.append(ch)
            elif ch in "}]" and stack: stack.pop()
        out.append(line)
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))   # the comma the dropped line left dangling


def _json_object(text, keep=800):
    # One eliot action per parse; a ModelJSONError leaves the action as a failure in the tree.
    with trace("chemistry_lab:json_object", chars=len(str(text or ""))) as action:
        value = _parse_json_object(text, keep)
        if action is not None: action.add_success_fields(keys=sorted(map(str, value))[:12])
        return value


def _parse_json_object(text, keep=800):
    raw = str(text or "")
    evidence_id, events = uuid.uuid4().hex, ["captured"]
    _parser_evidence(evidence_id, events, raw=raw)
    body = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw, flags=re.I | re.S)
    lo = body.find("{")
    if lo < 0:
        events.append("strict_parse_failed"); events.append("terminal")
        _parser_evidence(evidence_id, events, terminal=True)
        raise ModelJSONError("model returned no JSON object", evidence_id) from None
    # Strict boundary first: exactly one complete object from the opening brace, whatever follows it. Gemma
    # sometimes keeps writing after its object (a second one, or a sentence with braces in it); taking the last
    # "}" swallows that tail and the parse fails with "Extra data" (Vintos, SK-330c8fa6). Trailing text is not
    # part of the answer. A stray backslash is tried here too, so a tail does not hide behind one.
    for index, strict in enumerate((body, _BAD_ESCAPE.sub(r"\\\\", body))):
        try:
            value, _end = json.JSONDecoder().raw_decode(strict, lo)
        except ValueError:
            if index == 0:
                events.append("strict_parse_failed")
                _parser_evidence(evidence_id, events)
            continue
        if isinstance(value, dict):
            if index:
                events.append("repaired")
                _parser_evidence(evidence_id, events, repaired=strict[lo:_end])
            return value
    hi = body.rfind("}")
    tries = [body[lo:hi + 1]] if hi > lo else []
    tries.append(_close_open(body[lo:]))                 # truncated: close what it left open
    tries += [_drop_stray_values(t) for t in list(tries)]   # a bare value on its own line where a key belongs
    tries += [_BAD_ESCAPE.sub(r"\\\\", t) for t in list(tries)]   # a stray backslash it never meant as an escape
    for candidate in tries:
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            events.append("repaired")
            _parser_evidence(evidence_id, events, repaired=candidate)
            return value
    events.append("terminal")
    _parser_evidence(evidence_id, events, terminal=True)   # the mark that keeps its raw reply through pruning
    raise ModelJSONError("model returned no usable JSON object", evidence_id) from None


def _ask(system, prompt, max_tokens=500, temperature=0.75):
    body = json.dumps({"model": LLM_MODEL, "temperature": temperature, "max_tokens": max_tokens,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(LLM_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=150) as response:
        data = json.loads(response.read())
    return data["choices"][0]["message"]["content"]


# Every planner request ends on its output contract. A replan put the refusal last ("REFUSED, IT IS A REPEAT: ..."),
# and the local model answered that sentence as a person asking for help, in prose (16 October, after 10:12 CDT:
# every pass failed "no JSON object" and the notebook gained nothing). The contract is restated after whatever was
# appended, and a prose reply is asked for once more as JSON before the pass gives up.
PLAN_TAIL = ("\n\nReply with ONLY the JSON object for your choice, with the fields asked for above. This reply is "
             "read by the Lab's program, not by a person: no explanation, no advice, no headings, no apology.")


# The local model holds 32k tokens and LM Studio drops the START of an input that will not fit, which is where the
# planner's context and instructions are; what survives is the tail, here a refusal. Above this many characters the
# oldest context is cut instead, the instructions after it kept, and the cut is written down with its sizes.
PLAN_MAX_CHARS = 60000


def _narrow(value):
    """Every planner answer, from every path (first choice, repeat or premise replan, saved step), asks one thing. A
    question already held keeps its exact words, or its hold would not know it. The cut is written down."""
    if not isinstance(value, dict): return value
    q = value.get("question")
    two = second_ask(q)
    if not two: return value
    try:
        if _held_exactly(q): return value
    except Exception:
        pass
    _fault("question_narrowed", ValueError("two asks at: " + two), kept=first_ask(q)[:200])
    return dict(value, question=first_ask(q))


def _held_exactly(question):
    """A hold whose question is these exact words. _held_question also matches a paraphrase or another question on the
    same lookup, and on 17 October that kept compound questions whole (pendrin and prestin "and how do their folds",
    SLC34A1 and SLC34A2 "and how do these architectures"): 124 of 146 reviews were incomplete."""
    norm = lambda t: ' '.join(str(t or '').casefold().split())
    q = norm(question)
    return bool(q) and any(norm(old.get('question')) == q for old in _question_holds())


def _plan(system, prompt):
    return _narrow(_plan_raw(system, prompt))


def _plan_raw(system, prompt):
    if len(prompt) > PLAN_MAX_CHARS:
        _fault("plan_prompt_trimmed", ValueError("planner prompt over budget"),
               prompt_chars=len(prompt), kept_chars=PLAN_MAX_CHARS)
        prompt = "[older Lab context cut to fit]\n" + prompt[-PLAN_MAX_CHARS:]
    try:
        return _json_object(_ask(system, prompt + PLAN_TAIL))
    except ModelJSONError as exc:
        _fault("plan_not_json", exc, prompt_chars=len(prompt))
        return _json_object(_ask(system, prompt + PLAN_TAIL + "\n\nYour last reply was prose, not the JSON object. "
                                 "Reply again with the JSON object only, starting with {.", temperature=0.3))


# A question that asks two things is unanswered when either is missing. On 16 October after the 17:48 UTC deploy,
# 11 of 12 reviews were partial, and in each the missing part was a clause no source in the inquiry could return
# ("and how does the fold-specific binding ... facilitate", "compared to terrestrial secretion systems", "its role
# in preventing systemic zinc toxicity"), while the one complete answer asked only what its record established.
_SECOND_ASK = re.compile(r"(?:,\s*|\s+)(?:and\s+(?:how|why|what|which|whether|do|does|did|is|are|can|could)\b"
                         r"|(?:and\s+)?(?:how\s+(?:do|does|did)\s+(?:these|this|they|it)\b)"
                         r"|(?:as\s+)?compared\s+(?:to|with)\b|in\s+contrast\s+to\b)", re.I)


def second_ask(question):
    """The clause where a question starts asking a second thing, or ''."""
    m = _SECOND_ASK.search(str(question or ""))
    return m.group(0).strip(" ,") if m else ""


def first_ask(question):
    """The question cut to its first ask, ending in a question mark."""
    q = str(question or "")
    m = _SECOND_ASK.search(q)
    if not m: return q
    return q[:m.start()].rstrip(" ,;:") + "?"


def _compact_names(names, cap):
    """Names as one line under `cap` characters: whole gene families as PREFIX*, the rest as they are."""
    names = list(dict.fromkeys(str(n) for n in names if str(n).strip()))
    families = spent_families(names)
    grouped = {m.casefold() for _p, members in families for m in members}
    parts = ["%s* (%d)" % (prefix, len(members)) for prefix, members in families]
    parts += [n for n in names if n.casefold() not in grouped]
    out, used = [], 0
    for part in parts:
        if used + len(part) + 2 > cap:
            out.append("and %d more" % (len(parts) - len(out))); break
        out.append(part); used += len(part) + 2
    return ", ".join(out)


def _held_subjects(holds, cap=3000):
    """The gene/protein symbols and accessions the held questions name, compacted for the planner."""
    try:
        import lab_repeats as repeats
        names = []
        for old in holds:
            names += repeats.subjects(old.get('question'))
            names += repeats.subjects(old.get('uniprot_query'))
        return _compact_names(names, cap)
    except Exception:
        return ""


def spent_families(subjects, least=2):
    """Gene families with `least` or more spent members, as (prefix, members).

    A spent subject stops that subject only. Two or more spent members of one family say the family is spent for
    today, so the planner is told the family rather than being refused once per member it goes on to try.
    """
    groups = {}
    for subject in subjects:
        match = re.fullmatch(r'([A-Za-z][A-Za-z0-9-]*[A-Za-z])([0-9]{1,3})', str(subject).strip())
        if match and len(match[1]) >= 3:
            groups.setdefault(match[1].upper(), []).append(str(subject).strip())
    return [(prefix, sorted(set(members))) for prefix, members in sorted(groups.items())
            if len(set(members)) >= least]


def _safe_query(query):
    from lab_sources import normalize_protein_notation
    query = normalize_protein_notation(query)
    query = re.sub(r"[^\w()\[\]:*?+\-\s\"]", " ", query)
    query = re.sub(r"\s+", " ", query).strip()[:240]
    if not query:
        return RANDOM_QUERY
    # Gemma commonly writes JSON/Python-looking field syntax (``field : True``).
    # UniProt rejects that spacing/casing even though the intended fields are valid.
    # Canonicalize the bounded query here; never recover a rejected specific query by
    # silently widening it to the generic baseline.
    query = re.sub(r"\s*:\s*", ":", query)
    query = re.sub(r"\btrue\b", "true", query, flags=re.I)
    query = re.sub(r"\bfalse\b", "false", query, flags=re.I)
    fields = r"(?:accession|id|reviewed|length|protein_name|gene|organism_id|organism_name|taxonomy_id|keyword|go|xref_pdb)"
    query = re.sub(r"\b" + fields + r":(?:none|null)\b", "", query, flags=re.I)
    query = re.sub(r"\bAND\s+(?=AND\b|\))", "", query)
    query = re.sub(r"(?<=\()\s*AND\b|\bAND\s*$", "", query)
    query = re.sub(r"\(\s*\)", "", query)
    query = re.sub(r"\s+", " ", query).strip()
    # An OR is an operator too. Without this the insertion turned "(gene:A OR gene:B)" into
    # "(gene:A OR AND gene:B)", which UniProt refuses: the malformed query faulting the Lab on 12 October
    # 04:00 was written here, not by the planner. A doubled operator left by any other path keeps the first.
    query = re.sub(r"(?<!AND)(?<!OR)(?<=[A-Za-z0-9\]\"])\s+(?=" + fields + r":)", " AND ", query)
    query = re.sub(r"\b(AND|OR)(?:\s+(?:AND|OR))+\b", r"\1", query, flags=re.I)
    from lab_sources import normalize_uniprot_subjects
    query = normalize_uniprot_subjects(query)
    # A named protein must not disappear merely because it is longer than the wandering
    # window (S-layer protein A is 1,231 aa). The random browse fallback remains bounded;
    # ESM-C trims its own copy to 350 residues; the record keeps the whole sequence.
    names_subject = bool(re.search(r"\b(?:accession|id|protein_name|gene|keyword):", query, re.I))
    if names_subject:
        query = re.sub(r"(?:^|\s+AND\s+)length:\[[^\]]+\](?=\s+AND\s+|$)", " ", query,
                       flags=re.I)
        query = re.sub(r"\s+AND\s+(?=AND\b|$)", " ", query)
        query = re.sub(r"\s+", " ", query).strip()
        return (query if re.search(r"\breviewed:(?:true|false)\b", query, re.I)
                else BASELINE_QUERY + " AND (" + query + ")")
    return RANDOM_QUERY + " AND (" + query + ")"


INTENT_FIELDS = ("protein_name", "gene")
_FIELD_TOKEN = r"[A-Za-z_][A-Za-z_0-9]*\s*:"


def _intent_terms(uniprot_query):
    """The protein or gene he actually named, pulled out of the query he wrote."""
    out = []
    for field in INTENT_FIELDS:
        m = re.search(r"\b%s\s*:\s*(.+?)(?=\s+%s|\s*[()]|$)" % (field, _FIELD_TOKEN), str(uniprot_query or ""))
        if not m: continue
        # "protein_name:"KaiC" AND organism_id:1140" ends at the joiner, not after it (2026-09-27).
        value = _clean_subject(re.sub(r"\s+(?:AND|OR|NOT)$", "", m.group(1).strip(), flags=re.I).strip().strip('"'))
        if value:
            out.append('%s:"%s"' % (field, value) if " " in value else "%s:%s" % (field, value))
    return out


def merge_source_intent(source_query, uniprot_query):
    """His two queries disagreed and the broad one was the one sent: he asked for the S-layer protein
    of L. acidophilus while the Lab sent "every reviewed protein of this organism", so the same first
    record came back whatever he asked, and he wrote a bile-salt enzyme down as the S-layer protein
    (Gloria, 2026-09-26). The protein or gene he named is carried into the query that is sent."""
    if not isinstance(source_query, dict) or source_query.get("source") != "uniprot":
        return source_query
    query = str(source_query.get("query") or "").strip()
    terms = [t for t in _intent_terms(uniprot_query) if t.split(":", 1)[0] + ":" not in query]
    if not terms: return source_query
    return dict(source_query, query=" AND ".join([query] + terms) if query else " AND ".join(terms))


def _sourced_followup(spec, records):
    """Return lineage for a follow-up identifier, or why it must be refused."""
    if not isinstance(spec, dict):
        return None, None
    source = str(spec.get("source") or "")
    if source == "pdb":
        value, field = str(spec.get("entry_id") or "").upper(), "pdb_ids"
    elif source == "chembl" and spec.get('operation') != 'search_targets':
        value, field = str(spec.get("target_id") or "").upper(), "chembl_ids"
    else:
        return {"source": source, "kind": "non_identifier_followup"}, None
    available = {str(item).upper() for row in records for item in (row.get(field) or [])}
    if value and value in available:
        return {"source": source, "id": value, "sourced_from": "current_uniprot_records"}, None
    return None, "%s identifier %s was absent from the current UniProt records" % (source, value or "(empty)")


ATLAS_EVERY = 3
ATLAS_SCORERS = os.path.join(ROOT, "atlas-scorers.json")


def _atlas_scorer_hint():
    names = _load(ATLAS_SCORERS, []) or []
    return ("; optional scorers, up to 3 of Atlas's own: " + ", ".join(map(str, names[:12]))) if names else \
           "; scorers are optional, and Atlas's own are chosen if you name none"


def atlas_turn_due(rows=None):
    """Every third question is a human-genome turn for Atlas, when Atlas is configured. Left to choose,
    he asked Atlas 891 times with coordinates he could not have and took microbes the rest of the time
    (Gloria, 2026-09-28: "make atlas work! Make it chosen more frequently")."""
    if not config().get("alphagenome_key_file"): return False
    rows = _tail_jsonl(NOTEBOOK) if rows is None else rows
    since = 0
    for row in reversed(rows):
        if row.get("kind") in ("inquiry_refused", "evidence_wait"):
            # A refused or held scheduled Atlas opportunity yields this slot.
            # Its scientific/evidence hold remains intact; nothing is retried here.
            if row.get("atlas_turn") or ((row.get("inquiry") or {}).get("source_query") or {}).get("source") == "atlas":
                return since >= ATLAS_EVERY - 1
            continue
        if row.get("kind") != "inquiry": continue
        sq = (row.get("inquiry") or {}).get("source_query") or {}
        if isinstance(sq, dict) and sq.get("source") == "atlas": return since >= ATLAS_EVERY - 1
        since += 1
    return since >= ATLAS_EVERY - 1


def _as_atlas_turn(inquiry):
    """On a human-genome turn the Atlas read is made whatever form he wrote it in: a gene he named in the
    UniProt query becomes the Atlas request."""
    sq = inquiry.get("source_query") if isinstance(inquiry.get("source_query"), dict) else {}
    gene = sq.get("gene") if sq.get("source") == "atlas" else None
    if not gene:
        m = re.search(r"\bgene:\"?([A-Za-z][A-Za-z0-9-]{0,14})", str(inquiry.get("uniprot_query") or ""))
        gene = m.group(1) if m else None
    if not gene: return inquiry
    return dict(inquiry, browse_lane="protein", plugin_query=None, instrument_query=None, atlas_turn=True,
                source_query={"source": "atlas", "gene": gene, **({"scorers": sq["scorers"]}
                                                                    if isinstance(sq.get("scorers"), list) else {})})


def _planning_evidence(inquiry):
    """Content revision for this target, not receipt times or unrelated reads."""
    from lab_repeats import _ACCESSION
    from lab_sources import human_question_symbols, uniprot_identity_symbols
    text = str(inquiry.get('question') or '') + ' ' + str(inquiry.get('uniprot_query') or '')
    # An explicit accession wins. Otherwise use identity symbols, never generic
    # domain names or OR-matched free-text search terms. Without an identity,
    # changed direction or an eligible sourced route can still reopen planning.
    terms = set(_ACCESSION.findall(text)) or set(human_question_symbols(inquiry.get('question')) +
              uniprot_identity_symbols(inquiry.get('uniprot_query') or ''))
    volatile = {'at','retrieved_at','receipt_id','response_sha256','request_id',
                'elapsed_seconds','elapsed_ms','timestamp','created_at','updated_at'}
    def content(value):
        if isinstance(value, dict):
            clean = {k:content(v) for k,v in value.items() if k not in volatile}
            if clean.get('metadata') == {}: clean.pop('metadata')
            return clean
        if isinstance(value, list): return [content(v) for v in value]
        return value
    payloads = set()
    for row in _tail_jsonl(os.path.join(ROOT, 'source-receipts.jsonl'), nbytes=8*1024*1024):
        for record in row.get('records') or []:
            body = json.dumps(content(record), sort_keys=True)
            if terms and any(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', body, re.I) for term in terms):
                payloads.add(hashlib.sha256(body.encode()).hexdigest())
    return hashlib.sha256(json.dumps(sorted(payloads)).encode()).hexdigest()


def _hold_lookup(inquiry):
    import lab_repeats as repeats
    def clean(value):
        if isinstance(value, dict):
            return {k:clean(v) for k,v in value.items() if k not in ('attempt_id','request_id')}
        if isinstance(value, list): return [clean(v) for v in value]
        return value
    return repeats.canonical_lookup(repeats.lookup_key(clean(inquiry)))


def _hold_owner(inquiry, strict=True):
    """A decision belongs to the original question AND its retrieval, never a shared slot.

    `strict=False` returns None instead of raising, for a row that cannot own a hold at all. Such a row never held
    anything — an unnamed route cannot be matched to any later retrieval — so passing it over releases no decision.
    Raising on it stopped every tick instead: on 12 October the Lab spent from 04:44 CDT onwards re-raising
    "question hold lacks a named retrieval route" out of _question_holds, which the orient phase and two tick paths
    all call, and wrote 4.5 MB of identical faults without planning anything.
    """
    question = ' '.join(str(inquiry.get('question') or '').casefold().split())
    lookup = _hold_lookup(inquiry)
    for field, names in (('source_query', ('source',)), ('plugin_query', ('plugin','tool')),
                         ('instrument_query', ('skill','operation'))):
        spec = inquiry.get(field)
        if spec:
            if not isinstance(spec, dict) or any(not isinstance(spec.get(name), str) or not spec[name].strip()
                                                 for name in names):
                if not strict: return None
                raise ValueError('question hold lacks a named retrieval route')
            break
    if not question or not lookup:
        if not strict: return None
        raise ValueError('question hold lacks question or retrieval')
    return json.dumps([question, lookup], ensure_ascii=False)


HOLD_DAYS = 7


def _hold_age_days(old, now=None):
    """Days since a hold was made (held_at); 0 for one with no stamp yet."""
    try:
        made = datetime.fromisoformat(str(old.get('held_at')).replace('Z', '+00:00'))
        if made.tzinfo is None: made = made.replace(tzinfo=timezone.utc)
        return ((now or datetime.now(timezone.utc)) - made).total_seconds() / 86400
    except Exception:
        return 0.0


def _question_holds():
    """Retain independent question/retrieval decisions and each decision's evidence revision.

    A hold lasts HOLD_DAYS from when it was made (held_at), then leaves. Holds were kept until their evidence changed
    and most never did: 665 by 13 October, the planner shown ten of them, and 58% of passes spent re-proposing the
    rest and being refused (Gloria, 2026-10-13: nothing collects indefinitely). A question that expires may be asked
    again; that is a new attempt a week on, not a repeat."""
    path = os.path.join(ROOT, 'question-holds.json')
    # Once a held slot yields, its wait echoes stop. Preserve its decision when
    # unrelated progress moves the original record out of the notebook tail.
    # Unreadable/corrupt ownership must fail closed, never silently release work.
    # An entry whose owner cannot be computed is QUARANTINED, not released and not fatal: it keeps holding its own
    # question under the question-only key, and it no longer stops the Lab from doing anything else. Raising here
    # was a permanent outage — on 12 October the Lab re-raised out of this function from 04:44 CDT onwards, which
    # the orient phase and two tick paths all call, and planned nothing for hours while reading as active.
    saved, previous, quarantined = {}, {}, []
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as stream: previous = json.load(stream)
            if not isinstance(previous, dict): raise ValueError('saved question holds are not a mapping')
        except (ValueError, OSError) as exc:
            # The notebook, not this file, is where holds are established; this file only carries the ones whose
            # rows have rolled out of its tail. Keep the unreadable copy and rebuild from the notebook.
            try: os.replace(path, path + '.unreadable')
            except OSError: pass
            _fault('question_holds_unreadable', exc); previous = {}
        for key, old in previous.items():
            question = old.get('question') if isinstance(old, dict) else None
            legacy = ' '.join(str(question or '').casefold().split())
            structural = (not isinstance(old, dict) or not isinstance(question, str)
                    or not isinstance(old.get('planning_evidence'), str) or not old['planning_evidence']
                    or not old.get('refused') or old.get('evidence_status') != 'insufficient'
                    or any(old.get(field) is not None and not isinstance(old[field], dict)
                           for field in ('source_query','plugin_query','instrument_query'))
                    or old.get('uniprot_query') is not None and not isinstance(old['uniprot_query'], str))
            owner = None if structural else _hold_owner(old, strict=False)
            if owner is not None and key in (owner, legacy):
                saved[owner] = old  # migrate the uninstalled v1 index without losing its route/evidence
            elif legacy:
                saved[legacy] = old         # still held, under its question alone
                quarantined.append((key, legacy))
            # else: no question and no retrieval - there is no decision in it to keep
    if quarantined and any(key != legacy for key, legacy in quarantined):
        _fault('question_holds_quarantined',   # once: rewritten under the question key, so this does not repeat
               ValueError('; '.join(str(key)[:100] for key, _legacy in quarantined[:6])), count=len(quarantined))
    seen, current = set(), {}
    for row in reversed(_tail_jsonl(NOTEBOOK, nbytes=2*1024*1024)):
        old = row.get('inquiry') or {}
        if not old.get('question') or old.get('selection_idle'): continue
        held = old.get('refused') and old.get('evidence_status') == 'insufficient' and old.get('planning_evidence')
        coverage = row.get('coverage_check') or {}
        sufficiency = coverage.get('independent_sufficiency') or {}
        completed = (row.get('kind') == 'reflection' and row.get('evidence_status') == 'answered'
                     and coverage.get('answered') is True and coverage.get('missing') == []
                     and coverage.get('original_question') == old['question']
                     and bool(coverage.get('supports')) and sufficiency.get('sufficient') is True
                     and sufficiency.get('missing') == [] and not row.get('coverage_deferred')
                     and row.get('assessment_status') != 'incomplete')
        if not held and not completed: continue
        owner = _hold_owner(old, strict=False)
        if owner is None: continue   # an unnamed route holds nothing and must not stop the pass
        if owner in seen: continue
        seen.add(owner)
        if held: current[owner] = dict(old, held_at=old.get('held_at') or row.get('at') or now_iso())
        # Even a validated answer on another route cannot erase this route's
        # decision. Partial/failed assessments release nothing. Changed evidence
        # and genuinely different instruments still use _held_question's checks.
    current.update((owner, old if old.get('held_at') else dict(old, held_at=now_iso()))
                   for owner,old in saved.items() if owner not in seen)
    # Expiry alone is not new evidence: a question whose every open claim has already been searched for, with
    # nothing new to search, keeps waiting rather than running the same searches again (T-17420bd6).
    try:
        import lab_claim_evidence as _lce
        _waiting = _lce.waiting_keys(_claim_ledger())
        unchanged = lambda question: _lce.question_key(question) in _waiting
    except Exception:
        unchanged = lambda question: False
    current = {owner: old for owner, old in current.items()
               if _hold_age_days(old) < HOLD_DAYS or unchanged(old.get('question'))}
    if current != previous: _atomic(path, current)
    return list(current.values())


def _held_question(inquiry):
    """An ID/context change or paraphrase is not new evidence. A different instrument may be."""
    import lab_repeats as repeats
    key = _hold_lookup(inquiry)
    question = ' '.join(str(inquiry.get('question') or '').casefold().split())
    words = repeats._words(question)
    for old in _question_holds():
        old_key = _hold_lookup(old)
        old_question = ' '.join(str(old.get('question') or '').casefold().split())
        same_route = repeats._lookup_route(key) == repeats._lookup_route(old_key)
        if repeats._literature_route(key) and repeats._literature_route(old_key): same_route = True
        same_question = question == old_question
        # Use the existing repeat threshold, retaining its distinct-target exception.
        own_ids = {x for x in repeats.subjects(question) if any(c.isdigit() for c in x)}
        old_ids = {x for x in repeats.subjects(old_question) if any(c.isdigit() for c in x)}
        own_targets = repeats.lookup_targets(key)
        old_targets = repeats.lookup_targets(old_key)
        distinct_targets = bool(own_targets and old_targets and own_targets.isdisjoint(old_targets))
        similar = (len(words) >= 4 and len(words & repeats._words(old_question)) / len(words) >= repeats.SIMILAR
                   and not distinct_targets and not (own_ids and old_ids and own_ids.isdisjoint(old_ids)))
        if not ((key and key == old_key) or (same_route and (same_question or similar))): continue
        if old['planning_evidence'] == _planning_evidence(old): return old
    return None


def _planning_hold(scope, repeats, spent, step):
    """An exhausted planning assignment waits for changed evidence or direction.

    This is separate from executed-lookup history. It never says the question is
    answered, closes a line, or stops a different line from taking its turn.
    """
    # A free slot is a selection opportunity, not the owner of its last question.
    # Legacy context-only holds remain enforceable through _held_question.
    if not scope.get('line') and not scope.get('frontier') and not scope.get('atlas'):
        return None
    for row in reversed(_tail_jsonl(NOTEBOOK, nbytes=2*1024*1024)):
        old = row.get('inquiry') or {}
        if old.get('planning_scope') != scope or not old.get('planning_evidence'):
            continue
        if not old.get('refused') or old.get('evidence_status') != 'insufficient':
            return None
        if ((old.get('strategy_resolution') or {}).get('reason') == 'no_unread_sourced_route'
                and not scope.get('line') and not scope.get('frontier')):
            # Free curiosity has no assignment to exhaust: a proposal refused as a repeat holds nothing. On
            # 11 October from 07:21 UTC the free slot sat on one such refusal, its context barely changing.
            return None
        if old['planning_evidence'] != _planning_evidence(old):
            return None
        candidate = _strategy_change(old, repeats)
        if candidate and (not step or repeats.on_frontier(candidate, step)) and not spent_retrieval(candidate, spent):
            for key in ('refused', 'planning_wait', 'evidence_status', 'planning_scope', 'planning_evidence', 'coverage_deferred'):
                candidate.pop(key, None)
            return candidate
        return dict(old, planning_wait=True)
    return None


def _orient(context, lean=None):
    """His question for this cycle: the next step on the line of inquiry this cycle works (lab_lines.pick), or, on a
    free cycle, any curiosity, which may open a new line."""
    # An Atlas turn, when due, takes the cycle (Gloria, 2026-09-28: "make it chosen more frequently"); the line waits
    try:
        import lab_repeats
        step = lab_repeats.frontier_step()
    except Exception as exc:
        _fault("frontier_step", exc); step = None; lab_repeats = None
    spent = dead_ends()
    remember_spent(spent["subjects"])
    held = spent_subjects()
    spent = dict(spent, subjects=list(dict.fromkeys(spent["subjects"] + held)))
    atlas_due = atlas_turn_due() and not step     # the frontier session's plan comes before a scheduled Atlas turn
    try:
        import lab_lines
        line = None if (atlas_due or step) else lab_lines.pick()
        assigned_line = line
        # A line is unfinished work, even when its subject is spent. Keep it in
        # front of the planner so it can target an open claim with a different
        # source. The ordinary repeat gate still refuses an identical call.
    except Exception as exc:
        _fault("lab_lines_pick", exc); line = assigned_line = None
    scope = {'line': {k: assigned_line.get(k) for k in ('id','question','next_step')} if assigned_line else None,
             'frontier': {k: step.get(k) for k in ('session_id','next_question')} if step else None,
             'lean': lean, 'atlas': atlas_due}
    if not assigned_line and not step:
        # Free curiosity has no named assignment. Bind its wait to its actual
        # input, so a new unrelated request remains eligible. Our own latest-event
        # timestamp is a pointer, not a new question or new scientific evidence.
        basis = re.sub(r'\[LATEST LAB EVENT - pointer to append-only notebook\]\n[^\n]*', '', context)
        scope['context_sha256'] = hashlib.sha256(basis.encode()).hexdigest()
    def scoped(inquiry):
        # The assignment's own work carries the assignment's scope. Revived work from another reflection
        # (_next_evidence_work: "continued another self-authored unresolved step") carries its own: on 11 October an
        # unrelated Gasdermin refusal was stamped with the stored-receipt audit's scope, and _planning_hold then held
        # the audit as exhausted. A rejected proposal on other work is not proof this assignment is exhausted.
        # Never inherit absent or stale hold metadata.
        own = scope
        if inquiry.get('selection_idle'):
            own = {'selection_of': ' '.join(str(inquiry.get('question') or '').casefold().split())}
        elif not scope.get('line') and not scope.get('frontier') and not scope.get('atlas'):
            own = dict(scope, question=' '.join(str(inquiry.get('question') or '').casefold().split()))
        if ((inquiry.get('strategy_resolution') or {}).get('reason') ==
                'continued_another_self_authored_unresolved_step'):
            own = {'followup_of': ' '.join(str(inquiry.get('requested_question') or '').casefold().split()),
                   'question': ' '.join(str(inquiry.get('question') or '').casefold().split())}
        return dict(inquiry, planning_scope=own, planning_evidence=_planning_evidence(inquiry))
    recent = _tail_jsonl(NOTEBOOK, nbytes=64*1024)
    if lab_repeats and not atlas_due and not step and recent and recent[-1].get('kind') in ('inquiry_refused', 'evidence_wait'):
        # A saved, explicit local step is work already chosen. Try its exact
        # model/range before asking the planner for another exhausted subject.
        try:
            recovered = (_next_assigned_archive_step(lab_repeats, spent, lean) or
                         _next_assigned_model_step(lab_repeats, spent, lean))
        except Exception as exc:
            _fault('saved_model_step', exc); recovered = None
        if recovered:
            return recovered
    if lab_repeats and not atlas_due and recent and recent[-1].get('kind') == 'inquiry_refused':
        # A failed choice hands the next pass real pending work, instead of
        # asking the same planner to start over from the same exhausted context.
        candidate = _next_evidence_work({}, lab_repeats, spent, step)
        if candidate:
            recovered, _ = _held_to_plan('', '', candidate, {}, lean, step, lab_repeats, spent=spent)
            if not recovered.get('refused'): return scoped(_on_line(recovered, {}, None))
    if lab_repeats and not atlas_due and not step and recent and recent[-1].get('kind') in ('inquiry_refused', 'evidence_wait'):
        deferred = _next_fitting_deferred_coverage()
        if deferred: return _on_line(deferred, {}, None)
        grounded = _next_sourced_record(lab_repeats, spent, lean)
        if grounded: return _on_line(grounded, {}, None)
    waiting = None
    if lab_repeats:
        held = _planning_hold(scope, lab_repeats, spent, step)
        if held:
            if held.get('planning_wait'):
                if held.get('coverage_deferred'):
                    alternate = _next_evidence_work({}, lab_repeats, spent, step)
                    if alternate:
                        admitted, value = _held_to_plan('', '', alternate, {}, lean, step, lab_repeats, spent=spent)
                        if not admitted.get('refused'): return scoped(_on_line(admitted, value, None))
                if assigned_line and not step:
                    # The held line keeps its hold (no repeat calls on it), but it does not take the pass: this
                    # pass plans free curiosity. Waiting is per line, not for the whole Lab (11 October from 07:21
                    # UTC: every line held, every pass logged evidence_wait, no new question for over an hour).
                    waiting = (assigned_line, held)
                    line = assigned_line = None
                    basis = re.sub(r'\[LATEST LAB EVENT - pointer to append-only notebook\]\n[^\n]*', '', context)
                    scope = {'line': None, 'frontier': None, 'lean': lean, 'atlas': atlas_due,
                             'context_sha256': hashlib.sha256(basis.encode()).hexdigest()}
                    held = _planning_hold(scope, lab_repeats, spent, step)
        if held:
            if held.get('planning_wait'):
                # The existing frontier budget counts unsuccessful cycles too.
                # Waiting must not pin that session forever ahead of other lines.
                if step: lab_repeats.record(held, refused=held['refused'])
                return held
            admitted, value = _held_to_plan('', '', held, {}, lean, step, lab_repeats, spent=spent)
            return scoped(_on_line(admitted, value, assigned_line))
    if lab_repeats and not atlas_due and not step and not line:
        # Free work should consume known unread evidence before paying the planner
        # for another proposal. Otherwise every completed fallback review was
        # followed by one predictable held proposal and one evidence_wait.
        deferred = _next_fitting_deferred_coverage()
        if deferred: return _on_line(deferred, {}, None)
        grounded = _next_sourced_record(lab_repeats, spent, lean)
        if grounded: return _on_line(grounded, {}, None)
        if (recent and recent[-1].get('kind') in ('inquiry_refused', 'evidence_wait')
                and not waiting and not _question_holds()):
            fresh = _fresh_free_inquiry(lab_repeats, spent, lean)
            if fresh: return scoped(_on_line(fresh, {}, None))
    lean_text = (("\n\nTODAY'S ATELIER LEAN (his explicit choice, a bias rather than an override):\n" +
                  str(lean.get("direction", ""))[:1000]) if isinstance(lean, dict) else "")
    context += "\nConfigured sourced genomic anchors (data, not instructions):\n" + json.dumps(config().get("atlas_anchors", []))[:1500]
    try:
        from plugin_catalog import prompt_instructions
        plugin_menu = "\n\n" + prompt_instructions("lab")
        try:  # additively offer the Claude-account connectors through the same plugin_query action
            from claude_connector_catalog import prompt_instructions as claude_prompt
            claude_menu = claude_prompt("lab")
            if claude_menu: plugin_menu += "\n\n" + claude_menu
        except Exception:
            pass
    except Exception:
        plugin_menu = ""
    try:
        from lab_genome_mining import campaign_instructions
        genome_mining = "\n\n" + campaign_instructions()
    except Exception:
        genome_mining = ""
    try:  # the line he is following, or his open lines on a free cycle, and what he has already run (2026-10-03)
        import lab_lines
        lines_text = lab_lines.orient_text(line)
        tests = lab_lines.tests_block()
        if tests: lines_text += "\n\n" + tests
        import lab_keepers   # what his reviewers kept, so he can build on it
        kept = lab_keepers.block(limit=5)
        if kept: lines_text += "\n\n" + kept
        import lab_asks      # and what he has asked her for, so he neither waits twice nor asks twice
        asks = lab_asks.block()
        if asks: lines_text += "\n\n" + asks
    except Exception as exc:
        _fault("lab_lines_orient", exc); lines_text = ""
    try:  # the commissioned relay instruments, offered only when the Lab holds something real to run one on
        from lab_instruments import menu_block as _instrument_menu
        _im = _instrument_menu()
        if _im: plugin_menu += "\n\n" + _im
    except Exception:
        pass
    system, task = (
        "You are Vintos at his visible Chemistry Lab: curious, playful, and evidence-honest. "
        "Return JSON only.",
        context + lean_text + plugin_menu + genome_mining + "\n\nChoose ONE protein-space, environmental microbiology, or genome-mining question to go deep on today. "
        "Microbiology is an available direction, not a priority or a named organism to seek. If the recent "
        "journal has a source-backed open question, advance it only with a discriminating new source or instrument; "
        "do not repeat the same query or conclusion merely because it appeared again. Treat redirects as lessons: "
        "name what failed and choose a different test or question. A new curiosity may displace an exhausted thread. "
        "Ask ONE thing its sources can answer whole: one protein (or one named pair), one property, the kind of fact "
        "the source you name returns (a record's annotated features, a structure's metal or ligand contacts, a "
        "literature finding). Do not add a second question with 'and how', 'and what', 'and do', 'and whether', "
        "'compared to' or 'its role in'; a mechanism, comparison or consequence is a later question, asked when a "
        "source that addresses it is in hand. A question with one part missing is unanswered as a whole. Residues and "
        "geometry come from a record's feature annotations or a structure's contacts, never from abstracts; the "
        "'structural hallmarks' of a whole genus or system class are not in any one record, so ask about one named "
        "protein. "
        "Pick something an instrument here could actually probe — a "
        "sequence to embed, a likelihood to compare, a structure to fold — not a general theme to admire. Return "
        "keys in this order: browse_lane ('protein', 'microbiology', or 'genome_mining'), uniprot_query (valid fields: protein_name, gene, organism_id, taxonomy_id, reviewed, length), question, why_now, source_query, plugin_query, "
        "material_terms (2 to 5 plain keywords a literature search needs: the protein or gene, the organism, the property "
        "you are asking about — the Lab fetches published abstracts on them for you to read). "
        "Wherever a source below takes taxon_id, organism:\"plain organism name\" may be written instead; the Lab looks the ID up. "
        "For microbiology, source_query is required as the primary browse observation: "
        "{source:ncbi,operation:literature,term:plain research phrase}, "
        "{source:ncbi,operation:taxonomy,term:organism name}, "
        "{source:ncbi,operation:assembly,taxon_id:sourced numeric ID}, "
        "{source:ncbi,operation:gene or protein,taxon_id:sourced numeric ID,term:plain gene/protein name}, "
        "{source:ncbi_sequence,database:protein or nuccore,accession:exact sourced accession.version,start:one-based integer,end:one-based inclusive integer}, "
        "{source:bvbrc,operation:genomes,taxon_id:sourced numeric ID}, "
        "{source:bvbrc,operation:pathways,genome_id:sourced BV-BRC ID}, or "
        "{source:mgnify,operation:studies,term:plain environmental or microbiome phrase,limit:1..8}, "
        "{source:rhea,term:plain reaction or metabolite phrase,limit:1..8}, "
        "{source:quickgo,term:plain function or process phrase,limit:1..8}, "
        "{source:pubchem,name:exact compound name,limit:1..4}, or "
        "{source:uniprot,query:taxonomy_id:SOURCED_ID AND reviewed:true AND protein_name:\"the protein you are asking about\"} "
        "(taxonomy_id covers a whole group such as a phylum; organism_id matches one exact organism only and returns "
        "nothing for a group ID; name the protein_name or gene you are actually asking about in THIS query, or the "
        "whole organism comes back and its first record answers for a protein you never asked about; reviewed:true is "
        "the curated set, and if it holds nothing of what you asked for then that is the answer — reviewed:false may be "
        "asked on a later question, and its records are automatic annotation, never curated fact). "
        "Use IDs returned by earlier receipts; do not invent them. Sequence slices are capped at 350 amino acids or 512 bases. BV-BRC pathway rows are annotations, not proof of expression or phenotype. "
        "For genome_mining, source_query is required and is ONE step of a multi-return campaign: "
        "{source:ncbi_protein_context,accession:exact sourced protein accession.version}, "
        "{source:ncbi_neighborhood,accession:exact sourced nuccore accession.version,anchor_start:sourced one-based integer,anchor_end:sourced one-based integer,flank:500..5000}, "
        "{source:interpro,accession:exact sourced UniProt accession}, "
        "{source:rt_locus_screen,accession:exact sourced protein accession.version} (ONE step for a phage or other "
        "reverse transcriptase: reads its genome neighborhood, finds CRISPR arrays (CRT) and the Pfam domains of it "
        "and every gene beside it, Cas genes included; a locus already screened is not read again), "
        "or an NCBI literature query above. "
        "Use coded_by coordinates returned by ncbi_protein_context; never invent a neighborhood. The repeat screen reports candidates, not boundaries, significance, novelty, or function. "
        "For the protein lane, source_query is null or ONE read-only followup object: {source:atlas,gene:HUMAN GENE SYMBOL} "
        "(" + _atlas_text() + _atlas_scorer_hint() + "), {source:pdb,entry_id:known PDB ID}, "
        "{source:chembl,target_id:known CHEMBL target ID}, {source:pubchem,name:exact compound name,limit:1..4}, "
        "{source:reactome,term:plain pathway phrase,species:optional plain species,limit:1..5}, "
        "{source:rhea,term:plain reaction or metabolite phrase,limit:1..8}, or "
        "{source:quickgo,term:plain function or process phrase,limit:1..8}. "
        "Choose one direct source for this question, not the whole menu. "
        "A protein question must seek a connection, not merely inventory fields. Include three claim types: "
        "a named structural feature or molecular property, a documented function, localization or comparison, "
        "and the source-backed relationship between them. Organism, accession and sequence length may establish "
        "identity but do not count as the connection. Match this cycle's retrieval to the claim still open; do not "
        "ask one generic record query to settle a relationship it cannot contain. "
        "Match the requested evidence product to that source: citation metadata is discovery, not a mechanism; "
        "an isolated structure cannot establish a fragment-versus-full-length comparison without both structures. "
        "If your question names two proteins to compare, ONE query must return both, or the question cannot be "
        "answered at all: write them together, e.g. uniprot_query '(gene:FIRST OR gene:SECOND) AND organism_id:ID "
        "AND reviewed:true'. Otherwise ask about one protein only. "
        "Keep such original questions unresolved when the required evidence is unavailable. A narrower question "
        "is separate work, never an answer to the original. "
        "Use only IDs present in sourced context; never invent them. "
        "plugin_query is null or ONE object {plugin,tool,arguments,purpose} using the exact menu above. "
        "Choose at most one of source_query, plugin_query and instrument_query. The returned receipt becomes Lab provenance. "
        "Atlas is human regulatory territory and supplies hypotheses, never validation. No literature hit is not novelty. "
        "Choose a sourced question an available instrument can probe; do not favor either lane "
        "merely because it appears in this menu."
        + lines_text + "\n\nAlso return line_id (the line this works, or null) and new_line (an object, or null)."
    )
    if step:
        task += ("\n\nYOUR FRONTIER SESSION (%s, %s) ENDED WITH THIS NEXT STEP. Your next %d cycle(s) are steps on it; "
                 "choose the question, source or instrument that advances it (a model you already have is read with "
                 "an instrument, not folded again):\n%s%s" % (step.get("lens"), str(step.get("at", ""))[:10], step["left"],
                 step["next_question"], ("\nWhat it kept: " + step["keep"]) if step.get("keep") else ""))
    try:
        import lab_repeats as _lr
        _done = _lr.all_lookups()
        if _done:
            task += ("\n\nLOOKUPS YOU ALREADY RAN THIS WEEK (an identical one is refused before it runs; so is the same "
                     "question in other words):\n- " + "\n- ".join(_done))
        # The questions themselves: a question sharing most of its words with one of these, on the same kind of
        # retrieval, is refused (16 October: she was shown ten lookups and refused against a week of questions).
        _not_human = _lr.not_human_symbols()
        if _not_human:
            task += ("\n\nNOT HUMAN GENES — NCBI Gene has no human gene by these names; never ask about them as human "
                     "proteins (in an organism where they exist, they may be asked about): " + ", ".join(_not_human) + ".")
        _asked = _lr.asked_questions()
        if _asked:
            task += ("\n\nQUESTIONS YOU ALREADY ASKED THIS WEEK — do not ask any of these again, in these words or "
                     "others. A follow-up must ask something these did not: a different protein, residue range, "
                     "organism or instrument:\n- " + "\n- ".join(_asked))
    except Exception:
        pass
    if waiting:
        task += ("\n\nWAITING ON NEW EVIDENCE — line %s is neither answered nor closed; its last proposal was refused "
                 "(%s). Do not propose it again this cycle; choose different work:\n- %s" %
                 (waiting[0].get("id"), str(waiting[1].get("refused") or "")[:200],
                  str(waiting[1].get("question") or waiting[0].get("question") or "")[:300]))
    atlas_turn = atlas_due
    if atlas_turn:
        task += ("\n\nTHIS IS A HUMAN-GENOME TURN: choose one human gene you are curious about. browse_lane 'protein', "
                 "uniprot_query 'gene:SYMBOL AND organism_id:9606', source_query {source:atlas, gene:SYMBOL}.")
    if spent["questions"]:
        task += ("\n\nYOUR LAST %d QUESTIONS ENDED WITHOUT AN ANSWER — reviews saying no do not reset this:\n- %s\n"
                 "That thread is spent for now. Choose a different protein, organism or instrument; "
                 "do not rephrase the same question. Do not invent a new accession or gene symbol by changing "
                 "digits in a failed one. Choose a documented subject from sourced context or a plain-name "
                 "discovery search instead." % (spent["count"], "\n- ".join(spent["questions"])))
    if spent["subjects"]:
        families = spent_families(spent["subjects"])
        in_family = {m.casefold() for _p, members in families for m in members}
        singles = [x for x in spent["subjects"] if x.casefold() not in in_family]
        # Every one is named. At 2500 characters the 42 newest of 259 were cut ("and 42 more"), and the planner
        # proposed exactly those (14 October: methanobactin, methionine synthase, SOD, secretin, ammonia
        # monooxygenase, alkaline phosphatase, metallo-beta-lactamase), each refused after the model was asked.
        task += ("\n\nSPENT FOR TODAY — these found nothing new here; do not ask about them: "
                 + _compact_names(singles, SPENT_PROMPT_CHARS) + ".")
        if families:
            # Naming members one at a time let the planner walk a family: SLC26A11 spent, so it proposed
            # SLC26A12 (12 October, the final hour: 256 spent-subject refusals, almost all SLC26A10-A15).
            # Say the family is spent instead of refusing each member afterwards.
            task += ("\n\nAND THE WHOLE FAMILY IS SPENT, including members not listed above and ones you have not "
                     "tried: " + "; ".join("%s (%s)" % (prefix + "*", ", ".join(members))
                                           for prefix, members in families) +
                     ". Choose a different protein family, organism or instrument today.")
        if line:
            task += (" The assigned line is the only exception: continue it only by returning its exact line_id and "
                     "targeting an explicitly open claim with a different source. An identical lookup remains refused.")
    held_questions = _question_holds()
    if held_questions:
        # Ten example questions out of hundreds told the planner almost nothing: it kept proposing the other holds,
        # each refused after several model calls, the pass ending empty a minute at a time (58% of passes, 13
        # October). Every held subject is named, compactly, so it can steer around all of them before choosing.
        task += ("\n\nQUESTIONS WAITING ON CHANGED EVIDENCE (not answers, not a hold on other work). "
                 "Choose independently eligible work; do not rename or rephrase these unchanged retrievals:\n- " +
                 "\n- ".join(str(item.get('question') or '')[:200] for item in held_questions[-6:]))
        _held_names = _held_subjects(held_questions)
        if _held_names:
            task += ("\n\nEVERY SUBJECT WITH A QUESTION WAITING (%d questions) — a question about any of these, "
                     "by the same kind of retrieval, is refused before it runs; choose a subject not on this list, "
                     "or a genuinely different instrument: %s." % (len(held_questions), _held_names))
    value = _plan(system, task)
    inquiry = _existing_model_read(_inquiry(value, lean))
    if atlas_turn: inquiry = _as_atlas_turn(inquiry)
    assigned_continuation = bool(line and inquiry.get("line_id") == line.get("id"))
    if spent["subjects"] and spent_retrieval(inquiry, spent) and not assigned_continuation:
        value = _plan(system, task + "\n\nYou chose a spent subject again. Choose a different one.")
        inquiry = _existing_model_read(_inquiry(value, lean))
    if lab_repeats:
        inquiry, value = _held_to_plan(system, task, inquiry, value, lean, step, lab_repeats, spent=spent)
    if atlas_turn:
        inquiry = dict(inquiry, atlas_turn=True)  # retain the opportunity even if a repair changed the route
    return scoped(_on_line(inquiry, value, line))


def _atlas_text():
    try:
        import lab_repeats
        return lab_repeats.ATLAS
    except Exception:
        return "Atlas reads one fixed window where the gene starts on GRCh38; its scores are predictions"


def _human_question_symbols(question):
    """Explicit gene-like tokens only; accessions and residue labels are not genes."""
    from lab_sources import human_question_symbols
    return human_question_symbols(question)


BACTERIAL_STYLE = re.compile(r'(?<![\w-])[A-Z][a-z]{2}[A-Z][0-9]?(?![\w-])')


def _ground_inquiry(inquiry, client=None):
    """Source-check generated human symbols before admitting them as research targets."""
    from lab_sources import Sources, question_entity_context
    constraints = question_entity_context(inquiry, [], literature_only=True)
    conflicts = [x for x in constraints['issues'] if 'contradict' in x]
    if conflicts:
        return {'status':'unresolved', 'reason':'; '.join(conflicts)}
    sq = inquiry.get('source_query') or {}
    queries = [str(inquiry.get('uniprot_query') or '')]
    if sq.get('source') == 'uniprot': queries.append(str(sq.get('query') or ''))
    symbols = []
    if sq.get('source') == 'atlas' and sq.get('gene'): symbols.append(str(sq['gene']))
    human_question = bool(re.search(r'\b(?:human|Homo sapiens)\b', str(inquiry.get('question') or ''), re.I))
    if human_question:
        symbols.extend(_human_question_symbols(inquiry.get('question')))
        # Bacterial gene names are written SlyA, SufS, SdrM: capital, three letters, capital. "Human SlyA" passed
        # (16 October: human SlyA, human Sdr, reviewed and found wrong only after a source call and a review) because
        # only all-capital symbols with a digit were checked. Such a name in a human question is checked too; a real
        # human gene written that way (IscU, for ISCU) still verifies.
        symbols.extend(BACTERIAL_STYLE.findall(str(inquiry.get('question') or '')))
    for query in queries:
        taxa = re.findall(r'\b(?:taxonomy_id|organism_id):([0-9]+)\b', query)
        if human_question and any(t != '9606' for t in taxa):
            return {'status': 'unresolved', 'reason': 'human question conflicts with nonhuman query taxonomy'}
        if not (human_question or '9606' in taxa): continue
        from lab_sources import uniprot_identity_symbols
        symbols.extend(uniprot_identity_symbols(query))
    symbols = list(dict.fromkeys(s.upper() for s in symbols))
    if not symbols: return {'status': 'not_applicable'}
    if len(symbols) > 4: return {'status': 'unresolved', 'reason': 'too many human gene identities in one inquiry'}
    path = os.path.join(ROOT, 'source-receipts.jsonl')
    cached = _tail_jsonl(path, nbytes=2*1024*1024)
    ids = []
    for symbol in symbols:
        result = None
        for row in reversed(cached):
            if row.get('source') != 'ncbi_gene_identity' or (row.get('query') or {}).get('symbol', '').upper() != symbol:
                continue
            try:
                age = time.time() - datetime.fromisoformat(row['retrieved_at']).timestamp()
                if 0 <= age < 86400: result = row
            except (ValueError, KeyError, TypeError): pass
            break
        if result is None:
            try:
                result = (client or Sources()).human_gene_identity(symbol)
            except Exception as exc:
                from urllib.error import HTTPError
                detail = ('HTTP %s' % exc.code) if isinstance(exc, HTTPError) else type(exc).__name__
                return {'status': 'unavailable', 'symbol': symbol,
                        'reason': 'human gene identity check unavailable: ' + detail}
            _append(path, result)
        ids.append(result['receipt_id'])
        if (result.get('metadata') or {}).get('status') != 'verified':
            return {'status': 'unresolved', 'symbol': symbol, 'receipt_ids': ids,
                    'reason': 'NCBI Gene did not establish an exact human symbol or alias for ' + symbol}
    return {'status': 'verified', 'symbols': symbols, 'receipt_ids': ids}


def _strategy_change(inquiry, repeats):
    """Advance a blocked retrieval using its sourced target, never just reword its query."""
    # An unread structure is not a substitute for a regulatory measurement.
    # Recovery must preserve the evidence type needed by the actual question.
    question = str(inquiry.get('question') or '')
    if (inquiry.get('atlas_turn') or
            re.search(r'\b(?:regulatory|variants?|chromatin|enhancers?|promoters?|ATAC|expression)\b', question, re.I) or
            not re.search(r'\b(?:structur\w*|domains?|topolog\w*|helic\w*|fold\w*|interfaces?|motifs?|annotations?|binding|conformation\w*)\b', question, re.I)):
        return None
    terms = {x.lower() for x in _intent_terms(inquiry.get('uniprot_query'))}
    from lab_repeats import _ACCESSION
    named = set(_ACCESSION.findall(str(inquiry.get('question') or '') + ' ' +
                                  str(inquiry.get('uniprot_query') or '')))
    for row in reversed(_tail_jsonl(NOTEBOOK, nbytes=4*1024*1024)):
        if row.get('kind') != 'source_read' or row.get('source') != 'UniProtKB REST': continue
        if row.get('scope_resolution'): continue
        if terms and not terms.intersection(x.lower() for x in _intent_terms(row.get('requested_query'))): continue
        if not terms and not named: continue
        taxa = set(re.findall(r'\b(?:taxonomy_id|organism_id):([0-9]+)', inquiry.get('uniprot_query') or ''))
        prior_taxa = set(re.findall(r'\b(?:taxonomy_id|organism_id):([0-9]+)', row.get('requested_query') or ''))
        if taxa and taxa != prior_taxa: continue
        records = [r for r in row.get('records') or [] if not named or r.get('accession') in named]
        if len(records) != 1: continue
        record = records[0]; accession = record.get('accession')
        if not accession: continue
        specs = [{'source':'pdb','entry_id':pid,'operation':'structure_evidence'}
                 for pid in record.get('pdb_ids') or [] if re.fullmatch(r'[1-9][A-Za-z0-9]{3}', str(pid))]
        specs.append({'source':'interpro','accession':accession})
        for spec in specs:
            target = dict(inquiry, source_query=spec, plugin_query=None, instrument_query=None,
                browse_lane='protein', uniprot_query='accession:'+accession,
                strategy_resolution={'previous_lookup':repeats.lookup_key(inquiry),
                    'reason':'blocked_retrieval_changed_to_unread_sourced_evidence',
                    'accession':accession, 'source':spec['source']})
            if not repeats.repeat(target): return target
        break
    return None


def _next_evidence_work(inquiry, repeats, spent, step):
    stopped_questions = set()
    for row in reversed(_tail_jsonl(NOTEBOOK, nbytes=2*1024*1024)):
        if row.get('kind') != 'reflection': continue
        prior = row.get('inquiry') or {}
        question_key = ' '.join(str(prior.get('question') or '').casefold().split())
        if (row.get('evidence_gap') or {}).get('automatic_followup') is False:
            stopped_questions.add(question_key)
        if question_key in stopped_questions or not row.get('next_question'): continue
        if not prior.get('uniprot_query'): continue
        proposed = dict(prior, question=row['next_question'],
                        requested_question=prior.get('question'))
        candidate = _strategy_change(proposed, repeats)
        if candidate and (not spent or not spent_retrieval(candidate, spent)) and (
                not step or repeats.on_frontier(candidate, step)):
            candidate['strategy_resolution']['reason']='continued_another_self_authored_unresolved_step'
            return candidate
    return None


def _coverage_snapshot(path):
    """Read one durable deferred-coverage packet and verify its content address."""
    directory = os.path.realpath(os.path.join(ROOT, 'coverage-deferred'))
    resolved = os.path.realpath(path)
    if os.path.dirname(resolved) != directory or not resolved.endswith('.json'):
        raise ValueError('coverage snapshot outside the durable store')
    payload = _load(resolved, None)
    if (not isinstance(payload, dict) or not isinstance(payload.get('inquiry'), dict)
            or not isinstance(payload.get('observations'), dict)):
        raise ValueError('invalid deferred coverage snapshot')
    digest = hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if os.path.basename(resolved) != digest + '.json':
        raise ValueError('deferred coverage snapshot hash mismatch')
    return payload, digest


def _next_fitting_deferred_coverage():
    """Resume preserved evidence when a larger verified context makes it fit."""
    directory = os.path.join(ROOT, 'coverage-deferred')
    completed = {row.get('coverage_retry_sha256') for row in _tail_jsonl(NOTEBOOK, nbytes=2*1024*1024)
                 if row.get('kind') == 'reflection' and row.get('coverage_retry_sha256')
                 and not row.get('coverage_deferred')}
    try:
        paths = [os.path.join(directory, name) for name in os.listdir(directory) if name.endswith('.json')]
        paths.sort(key=lambda path:os.stat(path).st_mtime_ns, reverse=True)
    except OSError:
        return None
    for path in paths:
        payload, digest = _coverage_snapshot(path)
        if digest in completed: continue
        inquiry, observations = payload['inquiry'], payload['observations']
        prepared = _coverage_request(inquiry, observations)
        if _coverage_deferral(inquiry, observations, prepared) is not None: continue
        resumed = dict(inquiry)
        for key in ('refused','planning_wait','evidence_status','coverage_deferred'):
            resumed.pop(key, None)
        resumed['coverage_retry_snapshot'] = path
        resumed['coverage_retry_sha256'] = digest
        resumed['assignment_resolution'] = {'reason':'deferred_coverage_now_fits','snapshot_sha256':digest}
        return resumed
    return None


def _sourced_record_index():
    """Incrementally index exact UniProt records from the whole append-only notebook.

    The notebook is much larger than the ordinary context tail. Restricting fallback
    selection to that tail eventually made thousands of older, unread records
    invisible and left free passes generating another held question instead.
    """
    path = os.path.join(ROOT, 'sourced-record-index.json')
    saved = _load(path, {})
    if not isinstance(saved, dict) or saved.get('version') != 2:
        saved = {}
    candidates = saved.get('candidates') if isinstance(saved, dict) else None
    if not isinstance(candidates, list): candidates = []
    reviewed = saved.get('reviewed') if isinstance(saved, dict) else None
    if not isinstance(reviewed, list): reviewed = []
    offset = saved.get('offset', 0) if isinstance(saved, dict) else 0
    if not isinstance(offset, int) or offset < 0: offset = 0
    try:
        size = os.path.getsize(NOTEBOOK)
        if offset > size:
            offset, candidates, reviewed = 0, [], []
        seen = {str(item.get('accession') or '') for item in candidates if isinstance(item, dict)}
        reviewed = set(map(str, reviewed))
        with open(NOTEBOOK, 'rb') as stream:
            stream.seek(offset)
            while True:
                start = stream.tell()
                raw = stream.readline()
                if not raw: break
                if not raw.endswith(b'\n'):
                    stream.seek(start)
                    break
                offset = stream.tell()
                try: row = json.loads(raw.decode('utf-8'))
                except (UnicodeDecodeError, ValueError): continue
                if row.get('kind') == 'source_read' and row.get('source') == 'UniProtKB REST':
                    for record in row.get('records') or []:
                        if not isinstance(record, dict): continue
                        accession = str(record.get('accession') or '').upper()
                        name = str(record.get('protein_name') or '').strip()
                        organism = str(record.get('organism') or '').strip()
                        if (not re.fullmatch(r'[A-Z0-9]{6,10}', accession) or not name or not organism
                                or accession in seen):
                            continue
                        seen.add(accession)
                        candidates.append({'accession':accession, 'protein_name':name,
                                           'organism':organism, 'record':record})
                elif row.get('kind') in ('reflection', 'genome_reflection'):
                    reviewed.update(str(item).upper() for item in row.get('source_accessions') or []
                                    if re.fullmatch(r'[A-Za-z0-9]{6,10}', str(item)))
    except OSError:
        return candidates
    for item in candidates:
        item['reviewed'] = item.get('accession') in reviewed
    updated = {'version':2, 'offset':offset, 'candidates':candidates, 'reviewed':sorted(reviewed)}
    if updated != saved: _atomic(path, updated)
    return candidates


def _sourced_record_snapshot(accession):
    for item in _sourced_record_index():
        if item.get('accession') == accession and not item.get('reviewed') and isinstance(item.get('record'), dict):
            return item['record']
    return None


def _record_connection_question(name, accession=None):
    target = "%s (%s)" % (name, accession) if accession else str(name)
    return ("What do curated UniProt records for %s establish about its annotated structural features, its "
            "documented molecular function or cellular role, and any source-backed relationship between those "
            "features and that function or role?" % target)


def _next_sourced_record(repeats, spent, lean=None):
    """Give a free pass one exact, previously returned protein when planning yields only held work."""
    for record in _sourced_record_index():
        if record.get('reviewed') or not isinstance(record.get('record'), dict): continue
        accession = record['accession']
        name = record['protein_name']
        organism = record['organism']
        question = _record_connection_question(name, accession)
        inquiry = _inquiry({'browse_lane':'protein', 'uniprot_query':'accession:' + accession,
                            'question':question, 'why_now':'source-grounded recovery after no eligible proposal',
                            'source_query':None, 'plugin_query':None,
                            'material_terms':[]}, lean)
        if _held_question(inquiry) or spent_retrieval(inquiry, spent): continue
        # A prior inquiry/source_read is not a completed review. The index only
        # offers accessions absent from every reflection, so finish that saved
        # evidence offline instead of letting the retrieval-repeat gate strand it.
        return dict(inquiry,
                    planning_scope={'sourced_fallback':accession},
                    planning_evidence=_planning_evidence(inquiry),
                    assignment_resolution={'reason':'exact_previously_sourced_record',
                                           'accession':accession})
    return None


def _fresh_free_inquiry(repeats, spent, lean=None):
    """Choose outside exhausted journal context when free planning is anchored to it."""
    system = 'You are Vintos at his visible Chemistry Lab. Return JSON only.'
    task = (
        'Choose ONE fresh protein for a new curated-record review, from an area you have not been thinking about '
        'recently. Choose freely. Do not choose a numbered gene-family variant. Use a plain '
        'protein name that UniProt can discover; do not invent an accession, gene symbol, organism ID, structure '
        'ID, or prior result. Ask for its annotated structural features, its documented function or cellular role, '
        'and any source-backed relationship between those features and that function or role. Return: browse_lane="protein"; a uniprot_query using '
        'protein_name:"plain name" AND reviewed:true; question; why_now; source_query=null; plugin_query=null; '
        'material_terms=[]; line_id=null; new_line=null.')
    for attempt in range(3):
        prompt = task + ('\n\nYour last choice was unavailable. Shift to a completely different biological '
                         'process and protein class.' if attempt else '')
        value = _plan(system, prompt)
        inquiry = _existing_model_read(_inquiry(value, lean))
        admitted, _ = _held_to_plan(system, prompt, inquiry, value, lean, None, repeats,
                                    spent=spent, replan=False)
        if not admitted.get('refused'): return admitted
    if _question_holds():
        # Changed wording must not make a held question, or its exhausted
        # neighborhood, look like permission to start a canned substitute.
        return None
    # The model can remain anchored even without journal text. Keep a small,
    # varied source-discovery queue so three failed choices do not become
    # another evidence_wait. These are review subjects, not claimed findings.
    for name in ('myoglobin', 'lysozyme', 'catalase', 'ubiquitin', 'hemocyanin',
                 'ferredoxin', 'lactase', 'rhodopsin', 'albumin', 'actin'):
        inquiry = _inquiry({
            'browse_lane':'protein', 'uniprot_query':'protein_name:"%s" AND reviewed:true' % name,
            'question':_record_connection_question(name),
            'why_now':'fresh source discovery after exhausted free selection',
            'source_query':None, 'plugin_query':None, 'material_terms':[],
            'line_id':None, 'new_line':None}, lean)
        if _held_question(inquiry) or spent_retrieval(inquiry, spent) or repeats.repeat(inquiry): continue
        admitted, _ = _held_to_plan(system, task, inquiry, {}, lean, None, repeats,
                                    spent=spent, replan=False)
        if not admitted.get('refused'): return admitted
    return None


def _next_assigned_archive_step(repeats, spent, lean=None):
    """Execute an explicit saved archive-by-accession step without replacing its question."""
    import lab_lines
    for line in lab_lines.open_lines():
        question, next_step = line.get('question'), line.get('next_step')
        if not isinstance(question, str) or not isinstance(next_step, str): continue
        match = re.fullmatch(
            r'Query the structure archive by UniProt accession ([A-Z0-9]+)\. Return only entry identifiers, mapped accession, organism, experimental method, reported resolution, construct coverage and modeled residue coverage\. '
            r'Explicitly exclude ([A-Z0-9]+)/([0-9][A-Z0-9]{3}) from direct [A-Za-z0-9 -]+ evidence; report unavailable coverage fields as unavailable rather than inferring them\.', next_step.strip())
        if not match or set(repeats._ACCESSION.findall(question)) != {match[1]}: continue
        request = {'source':'pdb','operation':'search_accession','accession':match[1],
                   'exclude_accessions':[match[2]],'exclude_entries':[match[3]],'limit':4}
        inquiry = _inquiry({'question':question,'source_query':request}, lean)
        if inquiry.get('refused') or _held_question(inquiry) or repeats.repeat(inquiry): continue
        admitted, _ = _held_to_plan('', '', inquiry, {}, lean, None, repeats, spent=spent, replan=False)
        if admitted.get('refused'): continue
        scope = {'line':{k:line.get(k) for k in ('id','question','next_step')},'frontier':None,'lean':lean,'atlas':False}
        return dict(admitted,line_id=line['id'],planning_scope=scope,planning_evidence=_planning_evidence(admitted),
                    assignment_resolution={'reason':'explicit_saved_archive_step','next_step':next_step})
    return None


def _next_assigned_model_step(repeats, spent, lean=None):
    """Resolve only an explicit saved fold_read step; never invent a question or model."""
    import lab_lines
    import lab_instruments
    if len(lab_instruments._runs_today()['runs']) >= lab_instruments.DAILY_RUNS:
        return None
    offered = set(lab_instruments.artifacts('structure', 50))
    for line in lab_lines.open_lines():
        question, next_step = line.get('question'), line.get('next_step')
        if not isinstance(question, str) or not isinstance(next_step, str): continue
        match = re.fullmatch(r'fold_read\s+(\d+)\s*[-–]\s*(\d+)\s+on\s+([A-Z0-9]+-[a-f0-9]{12})(?:\.pdb)?\.?',
                             next_step.strip())
        if not match: continue
        first, last, model = int(match[1]), int(match[2]), match[3]
        accession = model.split('-')[0]
        if set(repeats._ACCESSION.findall(question)) != {accession}: continue
        path = 'artifacts/esmfold/' + model + '.pdb'
        if path not in offered or not 0 < first <= last: continue
        request = {'skill': 'fold_read', 'operation': 'structure.read',
                   'files': [path], 'range': [first, last], 'question': question}
        try:
            lab_instruments.validate(request)
            from chemistry_fold_read import read_pdb
            content = (lab_instruments.LAB / path).read_bytes()
            if not hashlib.sha256(content).hexdigest().startswith(model.split('-')[1]): continue
            numbers = {r[0] for r in read_pdb(content.decode('utf-8'))['residues']}
            if last - first > len(numbers) or not set(range(first, last + 1)) <= numbers: continue
        except (ValueError, OSError):
            continue
        if lab_instruments.completed_fold_read(request): continue
        inquiry = _inquiry({'question': question, 'instrument_query': request}, lean)
        if inquiry.get('refused') or _held_question(inquiry) or repeats.repeat(inquiry): continue
        # Keep the shared admission gate, but a rejected saved step must not
        # generate a replacement and falsely attach it to this assignment.
        admitted, _ = _held_to_plan('', '', inquiry, {}, lean, None, repeats,
                                    spent=spent, replan=False)
        if admitted.get('refused'): continue
        scope = {'line': {k: line.get(k) for k in ('id', 'question', 'next_step')},
                 'frontier': None, 'lean': lean, 'atlas': False}
        return dict(admitted, line_id=line['id'], planning_scope=scope,
                    planning_evidence=_planning_evidence(admitted),
                    assignment_resolution={'reason': 'explicit_saved_model_step', 'next_step': next_step})
    return None


def _held_to_plan(system, task, inquiry, value, lean, step, repeats, spent=None, *, replan=True):
    """The frontier session's next step, and no repeats (Gloria, 2026-10-07: "stop making repeats. Period."). Each is
    asked again once with the reason; an inquiry still off the plan, or still a repeat, is refused: the cycle runs
    nothing and she chooses again."""
    def refuse(why, identity_validated=False):
        if identity_validated:
            repeats.record(inquiry, refused=why, identity_validated=True)
        else:
            repeats.record(inquiry, refused=why)
        return dict(inquiry, refused=why), value
    if step and not repeats.on_frontier(inquiry, step):
        value = _plan(system, task + (
            "\n\nREFUSED: this cycle is a step on your frontier session's next question, and yours is not. Your "
            "question this cycle works this, about %s:\n%s\nChoose the source or instrument that advances it."
            % (", ".join(step["subjects"][:6]), step["next_question"])))
        inquiry = _existing_model_read(_inquiry(value, lean))
        if not repeats.on_frontier(inquiry, step):
            return refuse("off the frontier session's plan (%s)" % step.get("session_id"))
    def blocked(candidate):
        # Every repaired choice passes the same gate. A new instrument can
        # advance an exhausted subject; another database wording cannot.
        held = _held_question(candidate)
        if held:
            return 'question waiting on changed evidence: ' + str(held.get('refused') or '')
        active_line = False
        if candidate.get('line_id'):
            try:
                import lab_lines
                active_line = (lab_lines.get(candidate['line_id']) or {}).get('state') == 'open'
            except Exception:
                active_line = False
        if spent and spent_retrieval(candidate, spent) and not active_line:
            # the subject is named, so a refusal can be checked against what was actually spent
            return "spent subject: this retrieval already ended without an answer (%s)" % ", ".join(
                spent_matches(_inquiry_text(candidate), spent.get("subjects") or [])[:4])
        return repeats.repeat(candidate)
    why = blocked(inquiry)
    if why and not replan:
        return refuse('no eligible saved step: ' + why)
    if why:
        alternative = _strategy_change(inquiry, repeats)
        if alternative and (not step or repeats.on_frontier(alternative, step)):
            inquiry = alternative
            why = blocked(inquiry)
    if why:
        value = _plan(system, task + "\n\nREFUSED, IT IS A REPEAT: " + why +
                                  ". Choose a different question or a different source or instrument.")
        inquiry = _existing_model_read(_inquiry(value, lean))
        if step and not repeats.on_frontier(inquiry, step):
            return refuse("off the frontier session's plan (%s)" % step.get("session_id"))
        why = blocked(inquiry)
        if why:
            alternative = _strategy_change(inquiry, repeats)
            if alternative and (not step or repeats.on_frontier(alternative, step)):
                inquiry = alternative
                why = blocked(inquiry)
        if why:
            candidate = _next_evidence_work(inquiry, repeats, spent, step)
            if candidate:
                inquiry = candidate
                why = blocked(inquiry)
        if why:
            if _held_question(inquiry):
                # A bounded selection pass found no eligible proposal. This is not a new
                # scientific decision and must not overwrite either question/line's hold.
                inquiry = dict(inquiry, planning_wait=True, selection_idle=True)
                return refuse('no eligible proposal this pass: ' + why)
            # Terminal assessment, not another pending retrieval. Preserve the missing
            # evidence and stop feeding this failed next step back as open work.
            inquiry = dict(inquiry, evidence_status='insufficient', strategy_resolution={
                'reason':'no_unread_sourced_route', 'missing_evidence':why})
            return refuse("repeat: " + why)
    sq = inquiry.get('source_query') or {}
    if sq.get('source') in ('ncbi_protein_context', 'ncbi_neighborhood', 'ncbi_sequence', 'rt_locus_screen'):
        from lab_sources import _ncbi_accession
        try: accession = _ncbi_accession(sq.get('accession'))
        except ValueError as exc: return refuse(str(exc))
        # A version suffix is not provenance: P01234.1 was manufactured after
        # an earlier unversioned UniProt accession failed. Only returned data
        # can establish an identifier; a prior attempted query cannot.
        returned = _tail_jsonl(os.path.join(ROOT, 'source-receipts.jsonl'), nbytes=8*1024*1024)
        pattern = r'(?<![A-Za-z0-9_])' + re.escape(accession) + r'(?![A-Za-z0-9_.])'
        if not any(re.search(pattern, json.dumps(row.get('records') or [])) for row in returned):
            return refuse('NCBI accession not returned by a source receipt: ' + accession)
    identity = _ground_inquiry(inquiry)
    if identity['status'] == 'unresolved' and replan and system:
        # A wrong premise is put back to the planner once, named, so the same pass asks a question that holds, not
        # only refused a step earlier than its review would have found it (Gloria, 2026-10-16).
        value2 = _plan(system, task + "\n\nREFUSED, A WRONG PREMISE: " + identity['reason'] +
                                   ". Do not ask about it as a human protein. Ask about it in an organism where it "
                                   "exists, or ask about a human protein that does.")
        retry = _existing_model_read(_inquiry(value2, lean))
        if not (step and not repeats.on_frontier(retry, step)) and not blocked(retry):
            second = _ground_inquiry(retry)
            if second['status'] in ('verified', 'not_applicable'):
                repeats.record(dict(inquiry, identity_check=identity), refused=identity['reason'], identity_validated=True)
                inquiry, value, identity = retry, value2, second
    if identity['status'] != 'not_applicable':
        inquiry = dict(inquiry, identity_check=identity)
    if identity['status'] in ('unresolved', 'unavailable'):
        return refuse(identity['reason'], identity_validated=identity['status'] == 'unresolved')
    if step:
        inquiry = dict(inquiry, frontier_session=step.get("session_id"))
    repeats.record(inquiry)
    return inquiry, value


def _relational_question(question):
    text = str(question or "")
    direct = re.search(r'\b(?:how does|relationship|associated with|connect\w*|compare\w*|relate\w*|interact\w*|influenc\w*|affect\w*)\b', text, re.I)
    structural = re.search(r'\b(?:structur\w*|fold\w*|motif\w*|domain\w*|residue\w*|topolog\w*)\b', text, re.I)
    functional = re.search(r'\b(?:function\w*|role\w*|mechanism\w*|activity|locali[sz]\w*|regulat\w*|transport\w*|sequestrat\w*)\b', text, re.I)
    return bool(direct or (structural and functional))


def _on_line(inquiry, value, line):
    """The cycle's line on its inquiry: the line it works, or a new one he opened on a free cycle."""
    if inquiry.get("refused"):
        return inquiry  # rejected planning must not open or attach work to a line
    if line:
        return dict(inquiry, line_id=line["id"])
    new = value.get("new_line") if isinstance(value, dict) else None
    if isinstance(new, dict):
        try:
            import lab_lines
            opened = lab_lines.opened_by(new.get("title"), new.get("question") or inquiry.get("question"), new.get("why"))
            if opened:
                return dict(inquiry, line_id=opened["id"], line_opened=True)
        except Exception as exc:
            _fault("lab_lines_open", exc)
    question = str(inquiry.get("question") or "")
    if _relational_question(question):
        try:
            import lab_lines
            opened = lab_lines.opened_by(question[:120], question, inquiry.get("why_now"), origin="vintos:auto-claim")
            if opened:
                return dict(inquiry, line_id=opened["id"], line_opened=True)
        except Exception as exc:
            _fault("lab_lines_auto_open", exc)
    return inquiry


_UNIPROT_ARGS = ("accession", "protein_name", "gene", "organism_id", "taxonomy_id", "organism_name", "reviewed", "keyword")
# What the planner calls the same things (15 October, 21:26-23:26 CDT: eight source failures, every one a UniProt
# "plugin" route the Lab refused as an unavailable connector: uniprot.none, uniprot.uniprot_search). The names it
# reaches for are mapped to the public source's own; paging and formatting it adds are not questions, so they go.
_UNIPROT_ALIASES = {"gene_name": "gene", "gene_symbol": "gene", "genes": "gene", "protein": "protein_name",
                    "name": "protein_name", "organism": "organism_name", "species": "organism_name",
                    "taxon": "taxonomy_id", "taxon_id": "taxonomy_id", "tax_id": "taxonomy_id", "keywords": "keyword"}
_QUERY_ALIASES = ("query", "search", "term", "terms", "q", "text", "search_term", "search_query", "query_string")
_LIMIT_ALIASES = ("limit", "size", "max_results", "retmax", "count", "page_size")
_INERT_ARGS = {"fields", "format", "sort", "order", "offset", "page", "include_isoforms", "compressed", "fmt",
               "date_from", "date_to", "mindate", "maxdate", "datetype", "retstart", "api_key"}


def _limit_of(args, default, top):
    for key in _LIMIT_ALIASES:
        if key not in args: continue
        v = args[key]
        if isinstance(v, str) and v.strip().isdigit(): v = int(v)
        if type(v) is not int or v < 1:      # False, None, 0 or words are a malformed request, not a size
            raise ValueError('%s must be a positive whole number' % key)
        return min(v, top)
    return default


def uniprot_from_plugin(pq, purpose=""):
    """UniProt asked for as if it were a connector ({plugin: "uniprot", arguments: {protein_name: "Pendrin", ...}}),
    as the public source it is. It is not one of his connectors, so the call was refused every time (2026-10-06,
    four refusals in an hour). The source query, or None."""
    if not isinstance(pq, dict) or str(pq.get("plugin") or "").lower() not in ("uniprot", "uniprotkb"):
        return None
    def human_scope(query):
        if (re.search(r'\b(?:human|Homo sapiens)\b', purpose, re.I)
                and _human_question_symbols(purpose)
                and not re.search(r'\b(?:taxonomy_id|organism_id|organism_name):', query)):
            query += ' AND taxonomy_id:9606'
        return query
    args = pq.get("arguments") if isinstance(pq.get("arguments"), dict) else {}
    args = {_UNIPROT_ALIASES.get(str(k).lower(), str(k).lower()): v for k, v in args.items()}
    query = next((args[k] for k in _QUERY_ALIASES if isinstance(args.get(k), str) and args[k].strip()), None)
    if query:
        from lab_sources import validate_uniprot
        unknown = set(args) - set(_QUERY_ALIASES) - set(_LIMIT_ALIASES) - _INERT_ARGS
        if unknown:
            raise ValueError('unsupported public UniProt query arguments: %s' % ", ".join(sorted(unknown)))
        return {'source': 'uniprot', 'query': human_scope(validate_uniprot(query)), 'limit': _limit_of(args, 4, 8)}
    if not any(args.get(k) not in (None, "", []) for k in _UNIPROT_ARGS):
        # nothing named but the question itself: one accession in it is the query (the uniprot.none route)
        from lab_repeats import _ACCESSION
        found = sorted(set(_ACCESSION.findall(purpose)))
        if len(found) == 1:
            return {"source": "uniprot", "query": "accession:%s" % found[0], "limit": 1}
        # or the one human gene the question names (16 October: uniprot.none and uniprot.uniprot.search went to the
        # plugin gateway and were refused ten times in three hours, the question itself naming its gene)
        symbols = _human_question_symbols(purpose) if re.search(r'\b(?:human|Homo sapiens)\b', purpose, re.I) else []
        if len(symbols) == 1:
            return {"source": "uniprot", "query": "gene:%s AND organism_id:9606 AND reviewed:true" % symbols[0], "limit": 4}
    terms = []
    for key in _UNIPROT_ARGS:
        v = args.get(key)
        if v in (None, "", []):
            continue
        if isinstance(v, bool):
            v = "true" if v else "false"
        v = str(v).strip()
        terms.append('%s:%s' % (key, ('"%s"' % v.replace('"', '')) if re.search(r"\s", v) else v))
    if not terms:
        return None
    return {"source": "uniprot", "query": human_scope(" AND ".join(terms)), "limit": 1 if "accession" in args else 4}


def chembl_from_plugin(pq):
    """The named read-only target search uses public ChEMBL without account OAuth."""
    if not isinstance(pq, dict) or pq.get('plugin') != 'chembl' or pq.get('tool') != 'chembl_search_targets':
        return None
    args = pq.get('arguments') or {}
    # organism is what the connector's own schema offers, so the planner sends it; refusing it failed every such
    # search with "unsupported ChEMBL target-search arguments" (13 October). It is a real ChEMBL filter.
    if not isinstance(args, dict) or set(args) - {'target_name', 'limit', 'organism'}:
        # named, so the next fault says which argument the planner sent (14 October: one more, unnamed)
        raise ValueError('unsupported ChEMBL target-search arguments: %s' % (
            ', '.join(sorted(set(args) - {'target_name', 'limit', 'organism'})) if isinstance(args, dict) else type(args).__name__))
    from lab_sources import _plain_term, _bounded_limit
    spec = {'source': 'chembl', 'operation': 'search_targets', 'term': _plain_term(args.get('target_name')),
            'limit': _bounded_limit(args.get('limit'), 4)}
    if args.get('organism'):
        spec['organism'] = _plain_term(args['organism'])
    return spec



def _structure_followup(inquiry, records):
    """A structural question opens a deposited entry the protein source named.

    Preserve an explicit source/tool choice. This reads experimental evidence,
    not a new fold, a guessed PDB id, or an assertion about the native protein.
    """
    if inquiry.get('source_query') or inquiry.get('plugin_query') or inquiry.get('instrument_query'): return inquiry
    if len(records) != 1 or not re.search(r'structur|topolog|helix|helic|binding.site|coordinat',
                                         str(inquiry.get('question') or ''), re.I): return inquiry
    ids=records[0].get('pdb_ids') or []
    if not ids: return inquiry
    identifier=str(ids[0]).upper()
    if not re.fullmatch(r'[0-9][A-Z0-9]{3}',identifier): return inquiry
    return dict(inquiry,source_query={'source':'pdb','entry_id':identifier,'operation':'structure_evidence'},
                structure_resolution={'accession':records[0].get('accession'),'entry_id':identifier,
                                      'reason':'structural_question_reads_sourced_deposited_entry'})



_STRUCTURAL = re.compile(r'structur|topolog|helix|helic|fold|hinge|pocket|loops?\b|architectur|conformation|'
                         r'coordinat|spatial|arrangement|interfaces?\b|binding.site|sheet|strand', re.I)
STRUCTURE_TARGETS = 2


def structure_reads(inquiry, records):
    """The deposited entries a structural question should read beside whatever source he chose.

    15 October: 39 of 77 questions after the 07:59 deploy ended partially supported, nearly all asking for a fold,
    helical arrangements, hinge regions, loops or residue positions. UniProt annotation holds none of that; the
    records he fetched each named the PDB entries that do. _structure_followup opened one only when he had chosen no
    other source and only for a single record, and he nearly always chose literature. This adds the structure; it
    never replaces his choice, never narrows his question, and reads only entries the current records name."""
    if not _STRUCTURAL.search(str(inquiry.get('question') or '')): return []
    if inquiry.get('browse_lane') in ('microbiology', 'genome_mining'): return []
    if (inquiry.get('assignment_resolution') or {}).get('reason') == 'exact_previously_sourced_record': return []
    chosen = inquiry.get('source_query') if isinstance(inquiry.get('source_query'), dict) else {}
    already = str(chosen.get('entry_id') or '').upper() if chosen.get('source') == 'pdb' else ''
    question = str(inquiry.get('question') or '')
    def named(row):
        # a search can return proteins the question never named (Q9BXS9 beside pendrin and prestin): those the
        # question names by accession, gene, synonym or name come first
        words = {str(row.get('accession') or '')}
        for gene in row.get('genes') or []:
            for key in ('geneName', 'synonyms'):
                values = gene.get(key) or []
                for v in [values] if isinstance(values, dict) else values:
                    if isinstance(v, dict): words.add(str(v.get('value') or ''))
        hit = any(len(w) >= 3 and re.search(r'(?<![A-Za-z0-9])' + re.escape(w) + r'(?![A-Za-z0-9])', question, re.I)
                  for w in words)
        name = str(row.get('protein_name') or '')
        return hit or (len(name) >= 4 and name.casefold() in question.casefold())
    rows = [r for r in records or [] if isinstance(r, dict)]
    rows = [r for r in rows if named(r)] + [r for r in rows if not named(r)]
    out, covered = [], 0
    for row in rows:
        if covered >= STRUCTURE_TARGETS: break
        ids = [str(x).upper() for x in row.get('pdb_ids') or [] if re.fullmatch(r'[0-9][A-Za-z0-9]{3}', str(x))]
        if not ids: continue
        covered += 1
        if already and already in ids: continue   # the entry he chose for this target is already being read
        out.append({'source': 'pdb', 'entry_id': ids[0], 'operation': 'structure_evidence',
                    'for_accession': row.get('accession')})
    return out


def _structure_text(record):
    """A deposited structure as the review reads it: what it is, and its geometry in sentences a quote can come
    from. Chain ranges and contacts were dicts of numbers, which get no address."""
    if not isinstance(record, dict): return record
    geometry = record.get('geometry') or {}
    chains = ['chain %s: author residues %s to %s observed in the deposited model (%s residues)'
              % (c.get('chain'), c.get('author_residue_min'), c.get('author_residue_max'), c.get('observed_residues'))
              for c in geometry.get('chains') or [] if isinstance(c, dict)]
    contacts = []
    for c in geometry.get('inter_chain_contacts') or []:
        if not isinstance(c, dict): continue
        near = (c.get('closest_pairs') or [{}])[0]
        contacts.append('chains %s and %s: %s C-alpha pairs within 8 angstroms; closest %s%s to %s%s at %s angstroms'
                        % (*(c.get('chains') or ['?', '?'])[:2], c.get('ca_pair_count'),
                           near.get('chain_1'), near.get('residue_1'), near.get('chain_2'), near.get('residue_2'),
                           near.get('ca_distance_angstroms')))
    sites = []
    for site in (record.get('metal_sites') or [])[:4]:
        if isinstance(site, dict):
            sites.append(dict(site, nearby_atoms=(site.get('nearby_atoms') or [])[:8]))
    keep = {k: record.get(k) for k in ('entry_id', 'title', 'experimental_methods', 'resolution_angstroms',
                                        'primary_citation', 'numbering', 'interpretation',
                                        'secondary_structure_coverage', 'secondary_structure_records')}
    keep.update({'for_accession': record.get('for_accession'), 'chains_observed': chains,
                 'inter_chain_contacts': contacts, 'metal_sites': sites,
                 'method': geometry.get('method')})
    return keep


def _structure_pending(state):
    """Entries still to read for this question; worked out once, when its records first reach the embed step."""
    question = str((state.get("inquiry") or {}).get("question") or "")
    if state.get("structure_for") != question:   # a question left midway never hands its reads to the next one
        state["structure_for"] = question
        state["structure_evidence"] = []
        state["structure_pending"] = structure_reads(state.get("inquiry") or {}, state.get("records") or [])
    return bool(state.get("structure_pending"))


def _known_structure_followup(inquiry):
    """A previously returned exact target can open new deposited evidence now."""
    if inquiry.get('source_query') or inquiry.get('plugin_query') or inquiry.get('instrument_query'): return inquiry
    query = str(inquiry.get('uniprot_query') or '')
    accession = re.fullmatch(r'accession:([A-Z0-9]+)', query)
    terms = _intent_terms(query)
    if not accession and len(terms) != 1: return inquiry
    wanted = terms[0].split(':',1)[1].strip('"').casefold() if terms else None
    for row in reversed(_tail_jsonl(NOTEBOOK,nbytes=2*1024*1024)):
        if row.get('kind')!='source_read' or row.get('source')!='UniProtKB REST': continue
        records=row.get('records') or []
        if accession:
            matched=len(records)==1 and records[0].get('accession')==accession[1]
        else:
            prior=_intent_terms(str(row.get('requested_query') or ''))
            scope = lambda q: set(re.findall(r'\b(?:taxonomy_id|organism_id):([0-9]+)',q))
            matched=(len(prior)==1 and prior[0].split(':',1)[1].strip('"').casefold()==wanted
                     and scope(query)==scope(str(row.get('requested_query') or '')))
        if matched: return _structure_followup(inquiry, records)
    return inquiry


def _existing_model_read(inquiry):
    """Read the stored model for a geometry/confidence question, not its metadata again.

    Identity comes from an explicit accession or an exact prior UniProt request
    and its returned record. No name guess, new fold, or tool-schema inference.
    """
    question = str(inquiry.get('question') or '')
    if inquiry.get('instrument_query') or inquiry.get('source_query') or inquiry.get('plugin_query'):
        return inquiry
    if not re.search(r'secondary.structure|helic(?:es|al)|helix|strands?|pLDDT|confidence|predicted.*topology', question, re.I):
        return _known_structure_followup(inquiry)
    if re.search(r'experimental|crystal|documented', question, re.I): return _known_structure_followup(inquiry)
    from lab_repeats import _ACCESSION
    accessions = set(_ACCESSION.findall(question))
    if not accessions:
        symbols = _human_question_symbols(question)
        if len(symbols) != 1: return _known_structure_followup(inquiry)
        for row in reversed(_tail_jsonl(NOTEBOOK, nbytes=2*1024*1024)):
            if row.get('kind') != 'source_read' or row.get('source') != 'UniProtKB REST': continue
            if row.get('scope_resolution'): continue
            if not re.search(r'\b(?:gene|protein_name):"?' + re.escape(symbols[0]) + r'(?:"|\b)',
                             str(row.get('requested_query') or ''), re.I): continue
            records = [r for r in row.get('records', []) if r.get('organism') == 'Homo sapiens']
            if len(records) == 1 and records[0].get('accession'): accessions.add(records[0]['accession'])
            break
    if len(accessions) != 1: return _known_structure_followup(inquiry)
    import lab_instruments
    if len(lab_instruments._runs_today()['runs']) >= lab_instruments.DAILY_RUNS: return _known_structure_followup(inquiry)
    accession = next(iter(accessions))
    models = [f for f in lab_instruments.artifacts('structure', 50)
              if f.startswith('artifacts/esmfold/' + accession + '-') and f.endswith('.pdb')]
    if not models: return _known_structure_followup(inquiry)
    match = re.search(r'\bresidues?\s+(\d+)\s*(?:-|–|to)\s*(\d+)\b', question, re.I)
    span = [int(match[1]), int(match[2])] if match else [None, None]
    return dict(inquiry, instrument_query={'skill': 'fold_read', 'operation': 'structure.read',
                'files': [models[0]], 'range': span, 'question': question},
                instrument_resolution={'accession': accession, 'model': models[0],
                                       'reason': 'geometry_question_reads_existing_prediction'})


def pubmed_from_plugin(pq):
    """Normalize the public search at both planning and execution boundaries."""
    if not isinstance(pq, dict) or pq.get('plugin') != 'pubmed' or pq.get('tool') not in ('search_articles', 'pubmed.search_articles'):
        return None
    args = pq.get('arguments') or {}
    if not isinstance(args, dict):
        raise ValueError('unsupported public PubMed search arguments')
    # paging, sorting and date bounds the planner adds are not the question; they go, and the search runs (15
    # October: three faults, every one "unsupported public PubMed search arguments")
    args = {str(k).lower(): v for k, v in args.items()}
    unknown = set(args) - set(_QUERY_ALIASES) - set(_LIMIT_ALIASES) - _INERT_ARGS
    if unknown:
        raise ValueError('unsupported public PubMed search arguments: %s' % ", ".join(sorted(unknown)))
    limit = _limit_of(args, None, 6)        # the public PubMed read takes 1..6
    terms = next((args[k] for k in ('terms', 'term', 'query', 'q', 'search', 'text') if args.get(k)), None)
    if isinstance(terms, str):
        text = terms.strip()
        # Keep the whole request first, with a named subject that the existing
        # relaxation can retain if the descriptive phrase finds no papers.
        tokens = re.findall(r'\b[A-Za-z][A-Za-z0-9-]*\b', text)
        anchor = next((t for t in tokens if re.search(r'[0-9]', t) or
                       (re.search(r'[a-z]', t) and re.search(r'[A-Z]', t[1:]))), None)
        terms = [anchor, text] if anchor and anchor != text else [text]
    if not isinstance(terms, list) or not terms or any(not isinstance(t, str) or not t.strip() for t in terms):
        raise ValueError('public PubMed search requires nonempty terms')
    spec = {'source': 'pubmed_abstracts', 'terms': terms}
    if limit is not None: spec['limit'] = limit
    return spec


NAMED_FEATURE_TYPES = ("Domain", "Zinc finger", "Motif", "Region", "Repeat", "DNA binding", "Binding site",
                       "Active site", "Coiled coil", "Transmembrane", "Intramembrane")


def _features_named(features):
    """'Type: description' (a binding site by its ligand) for the features a question may claim, once each."""
    out = []
    for f in features:
        if not isinstance(f, dict) or f.get("type") not in NAMED_FEATURE_TYPES: continue
        what = f.get("description") or ((f.get("ligand") or {}).get("name") if isinstance(f.get("ligand"), dict) else "") or ""
        label = ("%s: %s" % (f["type"], what)).strip(": ")
        if label not in out: out.append(label)
    return out[:60]


_METALS = (r"metal|iron|\bFe\b|Fe\(|Fe cation|ferr|heme|zinc|\bZn\b|Zn\(|copper|\bCu\b|Cu\(|manganese|\bMn\b|"
           r"Mn\(|magnesium|\bMg\b|Mg\(|calcium|\bCa\b|Ca\(|cobalt|Co\(|nickel|Ni\(|molybd|tungst")
# (what the question asserts, how it is written, what in the target's own record would show it)
PREMISES = (
    ("zinc finger", r"\bzinc[- ]fingers?\b", r"zinc finger|C2H2|C4-type|RING|PHD|zinc"),
    ("an Ig-like domain", r"\b(?:Ig-like|immunoglobulin-like|immunoglobulin) domains?\b", r"Ig-like|immunoglobulin"),
    ("metal binding", r"\bmetal[- ](?:binding|coordination|ion|site|centre|center)", _METALS),
    ("iron or heme binding", r"\b(?:iron|heme|haem)[- ](?:binding|coordinat\w*|site|centre|center)|\bferroxidase\b",
     r"iron|\bFe\b|Fe\(|Fe cation|heme|haem|ferr"),
    ("zinc binding", r"\bzinc[- ](?:binding|coordinat\w*|site)", r"zinc|\bZn\b|Zn\("),
    ("calcium binding", r"\bcalcium[- ](?:binding|coordinat\w*|site)|\bEF-hands?\b", r"calcium|\bCa\b|Ca\(|EF-hand"),
    ("copper binding", r"\bcopper[- ](?:binding|coordinat\w*|site)", r"copper|\bCu\b|Cu\("),
    ("an SH2 domain", r"\bSH2\b", r"SH2"), ("an SH3 domain", r"\bSH3\b", r"SH3"), ("a PDZ domain", r"\bPDZ\b", r"PDZ"),
    ("a bHLH domain", r"\bbHLH\b|\bbasic helix-loop-helix\b", r"bHLH|helix-loop-helix"),
    ("a leucine zipper", r"\bleucine zippers?\b|\bbZIP\b", r"leucine zipper|bZIP"),
    ("a BRCT domain", r"\bBRCT\b", r"BRCT"), ("a PH domain", r"\bPH domains?\b", r"\bPH\b"),
    ("a C2 domain", r"\bC2 domains?\b", r"\bC2\b"), ("a kinase domain", r"\bkinase domains?\b", r"kinase"),
    ("leucine-rich repeats", r"\bleucine-rich repeats?\b|\bLRRs?\b", r"leucine-rich|LRR"),
    ("a STAS domain", r"\bSTAS\b", r"STAS"),
    ("transmembrane segments", r"\btransmembrane (?:domains?|helix|helices|segments?)\b", r"Transmembrane|Intramembrane"),
)


_CLASS_MARKERS = re.compile(
    r"\b(?:famil(?:y|ies)|superfamil\w+|subfamil\w+|classes|genus|genera|system|systems|complexes|"
    r"homolog\w+|ortholog\w+|paralog\w+|members?)\b|"
    r"\b[a-z]{4,}(?:ases|tors|sors|ptors|eins|ins)\b", re.I)


def class_question(question):
    """True when the question is about a kind of protein rather than one. Requiring such a question to resolve to
    one record is a category error (Chat's review, 2026-10-14), and refusing it produced nothing: 51 of the 130
    distinct questions on 14 October. It is still never answered BY one record standing for the kind."""
    return bool(_CLASS_MARKERS.search(str(question or "")))


def class_members(records):
    """The retrieved members, each by its own accession. A row with no accession is not a member."""
    out = []
    for row in records or []:
        if isinstance(row, dict) and row.get("accession"):
            out.append({"accession": row["accession"], "name": row.get("protein_name") or "",
                        "organism": row.get("organism") or ""})
    return out[:12]


def _class_scope_text(members):
    """What the members can and cannot establish, for the reader and for the checker."""
    return ("\n\nTHIS QUESTION NAMES A KIND OF PROTEIN, NOT ONE. The evidence holds %d retrieved member%s of it: %s. "
            "A finding holds for the members it is quoted from and for no others. Observed in every member examined "
            "here is an honest result and is NOT the same as characteristic of the kind: these members were returned "
            "by a search, which says nothing about how common the feature is. If the question asks about the kind "
            "itself, that part is not covered by this evidence - say so in missing."
            % (len(members), "" if len(members) == 1 else "s",
               "; ".join("%s (%s)" % (m["accession"], m["name"] or "unnamed") for m in members)))


_NOT_A_NAME = re.compile(r"\b(?:residues?|domains?|regions?|isoforms?|variants?|mutants?|human|mouse|amino|positions?|"
                         r"sites?|loops?|helix|helices|motifs?|e\.g|i\.e|see|aka|also|or|and)\b|\d+\s*[-\u2013]\s*\d+", re.I)


def _alias_issues(question, rows):
    """A name the question gives in brackets after a gene symbol that the symbol's own record does not carry.

    15 October: "the human SLC26A1 (pendrin) protein" was reviewed and answered from SLC26A1's record, sulfate
    anion transporter 1; pendrin is SLC26A4. The all-caps check ("GLUT1 (SLC1A1)") never saw a name in lower case.
    A record not listing a name is not proof the name is wrong, so this is a premise the record does not establish,
    never a contradiction. Only a one-word name is checked ("pendrin", "ZnT8", "fibrillin-1"): a phrase describes
    the protein in many wordings, and words naming a region, a residue range or an organism are not names."""
    norm = lambda text: re.findall(r"[a-z0-9]+", str(text).casefold().replace("-", ""))
    out = []
    for symbol, alias in re.findall(r"\b([A-Z][A-Z0-9]*[0-9][A-Z0-9]*)\s*\(([^()]{2,40})\)", str(question or "")):
        alias = alias.strip()
        if _NOT_A_NAME.search(alias) or "/" in alias or re.fullmatch(r"[A-Z][A-Z0-9-]{1,}", alias):
            continue
        owner = None
        for row in rows:
            genes = set()
            for gene in row.get("genes") or []:
                for key in ("geneName", "synonyms"):
                    values = gene.get(key) or []
                    values = [values] if isinstance(values, dict) else values
                    genes.update(str(v.get("value", "")).upper() for v in values if isinstance(v, dict))
            if symbol.upper() in genes:
                owner = (row, genes); break
        if not owner:
            continue
        row, genes = owner
        names = [str(row.get("protein_name") or "")] + [str(x) for x in row.get("protein_aliases") or []]
        words = norm(alias)
        if len(words) != 1 or len(alias.split()) != 1:
            continue   # a phrase describes the protein and is phrased many ways; a one-word name identifies one
        if "".join(words).upper() in {g.replace("-", "") for g in genes}:
            continue
        if any(set(words) <= set(norm(name)) for name in names if name):
            continue
        out.append("the question calls %s \"%s\"; its record (UniProt %s, %s) does not give that name"
                   % (symbol, alias, row.get("accession"), row.get("protein_name")))
    return out


def _premise_issues(question, rows):
    """What the question asserts about its one target that the target's own UniProt record does not list.

    14 October: "the zinc finger domains of NEUROD1" (a bHLH factor), "metal-binding geometries of the ANT", and the
    like reached the reviewer, which correctly found nothing; more papers could not help. A record that does not list
    a feature is not proof the feature is absent, so this is reported as a premise the record does not establish,
    and the question is not reviewed on it. Only one established target is checked; a comparison is left alone."""
    if len(rows) != 1: return []
    row = rows[0]
    hay = " ".join([str(row.get("protein_name") or ""), " ".join(map(str, row.get("protein_aliases") or [])),
                    str(row.get("function") or ""), " ".join(str(d.get("description") or "") for d in row.get("domains") or []),
                    " ".join(map(str, row.get("features_named") or [])), str(row.get("topology_summary") or "")])
    if not row.get("features_named"):
        return []   # a record fetched without its named features (or with none annotated) says nothing either way
    hay += " " + " ".join(str(t.get("type") or "") + " " + str(t.get("description") or "") for t in row.get("topology") or [])
    issues = []
    for name, asked, shown in PREMISES:
        if re.search(asked, str(question or ""), re.I) and not re.search(shown, hay, re.I):
            issues.append("%s is not annotated in %s (UniProt %s), which lists %d other annotated features; that is not "
                          "proof it is absent, only that the record does not establish it" %
                          (name, row.get("protein_name") or row.get("accession"), row.get("accession"),
                           len(row.get("features_named") or [])))
    return issues


_COORDINATES = re.compile(r"\b(?:xyz|coordinates?|bond (?:angle|length)s?|distances?|coordination (?:geometr\w+|angles?|sphere)|"
                          r"hydrogen[- ]bond(?:ing|s)?)\b", re.I)


def _coordinate_route(question, source_query):
    """A question about atom positions in a named PDB entry reads that entry's coordinates, not literature."""
    if not _COORDINATES.search(str(question or "")): return source_query
    if source_query and source_query.get("source") not in (None, "pdb"): return source_query
    named = re.findall(r"(?<![A-Za-z0-9'-])([1-9][A-Za-z0-9]{3})(?![A-Za-z0-9'-])", str(question or ""))
    named = [x.upper() for x in named if re.search(r"[A-Za-z]", x)
             and re.search(r"\b(?:PDB|structures?|entry|entries)\b", str(question), re.I)]
    entry = str((source_query or {}).get("entry_id") or "").upper()
    # The entry the question names is the one read. 14 October: a question about 2CEI read 2CLU, and one about
    # 2CIH's neighbour read another entry, so the review held coordinates of a structure nobody asked about.
    if named and entry not in named:
        entry = named[0]
    elif source_query and source_query.get("operation"):
        return source_query
    entry = entry or (named[0] if named else "")
    if not re.fullmatch(r"[1-9][A-Z0-9]{3}", str(entry).upper()): return source_query
    return {"source": "pdb", "entry_id": str(entry).upper(), "operation": "structure_evidence"}


def _fetches_only_some(query, symbols):
    """True when a human gene query names some, not all, of the question's genes, and nothing else."""
    terms = _intent_terms(query)
    genes = re.findall(r"\bgene(?:_exact)?\s*:\s*\"?([A-Za-z0-9-]+)", str(query or ""), re.I)
    if not genes or any(not t.startswith("gene:") for t in terms):
        return False
    if re.search(r"\b(?:accession|protein_name|organism_id|taxonomy_id)\s*:\s*(?!9606\b)", str(query), re.I) \
            and not re.search(r"\b(?:organism_id|taxonomy_id)\s*:\s*9606\b", str(query)):
        return False
    have = {g.upper() for g in genes}
    want = {str(x).upper() for x in symbols}
    return have < want


def _misses_named_genes(query, symbols):
    """True when a human query fetches none of the genes the question names: it searched by a name, a family or
    another gene instead. 15 October: "human collagen type IV (COL4A1)" was searched as protein_name "collagen type
    IV", which returned Q9Y5P4, collagen type IV alpha-3-binding protein, and the review rightly refused it as the
    wrong target. An accession, or a nonhuman organism, is the planner's explicit choice and is left as it is."""
    text = str(query or "")
    if not symbols or re.search(r"\baccession\s*:", text, re.I):
        return False
    taxa = re.findall(r"\b(?:organism_id|taxonomy_id)\s*:\s*([0-9]+)", text)
    if any(t != "9606" for t in taxa):
        return False
    genes = {g.upper() for g in re.findall(r"\bgene(?:_exact)?\s*:\s*\"?([A-Za-z0-9-]+)", text, re.I)}
    return not genes & {str(x).upper() for x in symbols}


def _inquiry(value, lean=None):
    question_sha256 = hashlib.sha256(str(value.get('question') or '').encode()).hexdigest()
    source_context_current = value.get('source_query_question_sha256') in (None, question_sha256)
    source_query = value.get("source_query") if isinstance(value.get("source_query"), dict) else None
    if not source_query:
        source_query = uniprot_from_plugin(value.get("plugin_query"), str(value.get("question") or ""))
        if source_query:
            value = dict(value, plugin_query=None)
    direct = pubmed_from_plugin(value.get("plugin_query")) or chembl_from_plugin(value.get("plugin_query"))
    if not source_query and direct:
        source_query = direct
        value = dict(value, plugin_query=None)
    if source_query:
        from lab_sources import normalize_source_spec
        source_query = normalize_source_spec(source_query)
    if not value.get('browse_lane') in ('microbiology', 'genome_mining'):
        source_query = _coordinate_route(value.get('question'), source_query)
    requested_lane = value.get('browse_lane')
    requested_query = value.get("uniprot_query")
    query = _safe_query(requested_query)
    question = str(value.get('question') or '')
    terms = _intent_terms(query)
    if (len(terms) == 1 and terms[0].startswith('protein_name:')
            and re.search(r'\bcurated\s+(?:UniProt\s+)?records?\b', question, re.I)):
        protein_name = terms[0].split(':', 1)[1].strip('"')
        normal = lambda text: ' '.join(re.findall(r'[^\W_]+', str(text).casefold()))
        if normal(protein_name) not in normal(question):
            question = _record_connection_question(protein_name)
            question_sha256 = hashlib.sha256(question.encode()).hexdigest()
    question_symbols = (_human_question_symbols(question)
                        if re.search(r'\b(?:human|Homo sapiens)\b', question, re.I) else [])
    if query in (BASELINE_QUERY, _safe_query(BASELINE_QUERY)) and question_symbols:
        query = ('(' + ' OR '.join('gene:' + symbol for symbol in question_symbols) +
                 ') AND taxonomy_id:9606 AND reviewed:true')
    elif 1 < len(question_symbols) <= 4 and _fetches_only_some(query, question_symbols):
        # Every protein the question names is fetched, so each can be established by its own record. 14 October:
        # "SOX9 and SOX10", "BRCA1 ... BARD1" fetched one gene, and the review refused the question because no
        # record established the other.
        query = ('(' + ' OR '.join('gene:' + symbol for symbol in question_symbols) +
                 ') AND taxonomy_id:9606 AND reviewed:true')
    elif 1 <= len(question_symbols) <= 4 and _misses_named_genes(query, question_symbols):
        # The genes the query did name are kept beside the question's own, so a partner the planner chose to
        # fetch is still fetched; only the search by name is replaced. The question itself is not touched.
        own = [g for g in re.findall(r"\bgene(?:_exact)?\s*:\s*\"?([A-Za-z0-9-]+)", str(query or ""), re.I)]
        wanted = list(dict.fromkeys([str(x) for x in question_symbols] + own))
        query = ('(' + ' OR '.join('gene:' + symbol for symbol in wanted) +
                 ') AND taxonomy_id:9606 AND reviewed:true')
    identity_queries = [query] + ([source_query['query']] if source_context_current and source_query and source_query.get('source') == 'uniprot' and source_query.get('query') else [])
    from lab_repeats import _ACCESSION
    named = sorted(set(_ACCESSION.findall(str(value.get("question") or ""))))
    resolution = None
    if len(named) == 1 and requested_lane not in ('microbiology', 'genome_mining'):
        exact = "accession:" + named[0]
        if query != exact:
            resolution = {"requested_query": query, "executed_query": exact,
                          "reason": "explicit_question_accession", "accession": named[0]}
            query = exact
        if source_query and source_query.get("source") == "uniprot":
            source_query = dict(source_query, query=exact)
    lane = requested_lane if requested_lane in ('microbiology','genome_mining') and source_query else 'protein'
    return {"browse_lane": lane, "source_query": source_query,
            "plugin_query": (value.get("plugin_query") if isinstance(value.get("plugin_query"), dict)
                             and not source_query else None),
            "instrument_query": (value.get("instrument_query") if isinstance(value.get("instrument_query"), dict)
                                 and not source_query and not isinstance(value.get("plugin_query"), dict) else None),
            "uniprot_query": query, "identity_queries": identity_queries,
            "identity_context": {"version":1, "question_sha256":question_sha256, "original_queries":identity_queries},
            "source_query_question_sha256": question_sha256 if source_context_current else value.get('source_query_question_sha256'),
            **({"query_resolution": resolution} if resolution else {}),
            "question": question or "What shape catches my attention today?",
            **({"line_id": str(value.get("line_id"))} if value.get("line_id") else {}),
            "material_terms": [str(t)[:60] for t in (value.get("material_terms") or [])
                               if isinstance(t, (str, int))][:5] if isinstance(value.get("material_terms"), list) else [],
            "why_now": str(value.get("why_now", "curiosity"))[:500],
            **({"atelier_lean_id": lean.get("lean_id"), "atelier_lean": str(lean.get("direction", ""))[:1000]}
               if isinstance(lean, dict) else {})}


def topology_summary(features):
    """Readable counts/ranges of source annotations, never extra structural measurements."""
    groups = {}
    for feature in features or []:
        location = feature.get('location') or {}
        start, end = (location.get('start') or {}).get('value'), (location.get('end') or {}).get('value')
        if type(start) is not int or type(end) is not int: continue
        key = feature.get('type') or 'unknown'
        description = feature.get('description') or ''
        groups.setdefault(key, []).append('%d-%d%s' % (start,end, ' ('+description+')' if description else ''))
    return ('UniProt source annotations, not a new experimental topology determination: ' + '; '.join(
        '%s: %d annotated intervals: %s' % (key,len(spans),', '.join(spans)) for key,spans in groups.items()) +
        '. Evidence qualifiers remain in the topology records; annotation count is not a count of helices in the deposited structure.') if groups else ''


def _browse(query, limit, *, allow_relaxation=True):
    from lab_sources import validate_uniprot
    requested_query = query
    executed_query = query
    fallback_reason = None
    def fetch(value):
        params = urllib.parse.urlencode({"query": value, "format": "json", "size": int(limit),
                                         "fields": "accession,id,protein_name,gene_names,organism_name,organism_id,length,sequence,cc_function,ft_domain,ft_transmem,ft_topo_dom,xref_pdb,xref_chembl,"
                                                   # the features a question may claim, for the premise check (14 October)
                                                   "cc_cofactor,ft_zn_fing,ft_binding,ft_motif,ft_region,ft_repeat,ft_dna_bind,ft_act_site,ft_coiled,ft_intramem"})
        req = urllib.request.Request(UNIPROT_URL + "?" + params,
                                     headers={"User-Agent": "Vintos-Chemistry-Lab/1.0 (read-only creative study)"})
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read(2*1024*1024+1)
            if len(raw) > 2*1024*1024: raise ValueError("UniProt response exceeds limit")
            return json.loads(raw)
    try:
        executed_query = validate_uniprot(executed_query)
    except ValueError:
        return {"source_receipt": None, "records": [], "requested_query": requested_query,
                "executed_query": None, "fallback_reason": "invalid_query_rejected_locally"}
    try:
        raw = fetch(executed_query)
    except urllib.error.HTTPError as exc:
        # A rejected specific query is history, not permission to widen scope.
        if exc.code != 400:
            raise
        fallback_reason = "source_rejected_generated_query"
        raw = {"results": []}
    # An exact query that finds nothing is tried in looser forms that keep his organism, filters and
    # words: the gene symbol he wrote as a protein name (RPS16, KaiC), then his words anywhere in the
    # entry, then any of them, then unreviewed entries too. A query UniProt refused as written gets the
    # same forms. Whichever answered is recorded, so the reading knows how the records were found.
    from lab_sources import uniprot_relaxations
    relaxed = None
    if allow_relaxation and not raw.get("results"):
        for label, alt in uniprot_relaxations(executed_query):
            try:
                retried = fetch(alt)
            except urllib.error.HTTPError as exc:
                if exc.code == 400: continue
                raise
            if retried.get("results"):
                raw, executed_query, relaxed, fallback_reason = retried, alt, label, None
                break
    scope_resolution = None
    if allow_relaxation and not raw.get('results') and not fallback_reason and re.search(r'\b(?:taxonomy_id|organism_id):9606\b', executed_query):
        subject_terms = _intent_terms(executed_query)
        if subject_terms and not re.search(r'\baccession:', executed_query):
            diagnostic_query = ' AND '.join(subject_terms)
            try: diagnostic = fetch(validate_uniprot(diagnostic_query))
            except urllib.error.HTTPError as exc:
                if exc.code != 400: raise
                diagnostic = {'results':[]}
            if diagnostic.get('results'):
                raw = diagnostic
                scope_resolution = {'requested_query':requested_query, 'executed_query':diagnostic_query,
                    'reason':'no_records_in_requested_human_scope; other_organisms_are_not_human_evidence',
                    'requested_taxonomy_id':'9606'}
                executed_query, relaxed, fallback_reason = diagnostic_query, 'organism_scope_diagnostic', None
    exact = re.fullmatch(r'accession:([A-Z0-9]+)', requested_query)
    if exact and any(item.get("primaryAccession") != exact[1] for item in raw.get("results", [])):
        raise ValueError("source_accession_mismatch: requested " + exact[1])
    from lab_sources import verify_uniprot_identity
    raw = dict(raw, results=verify_uniprot_identity(executed_query if scope_resolution else requested_query,
                                                    raw.get("results", [])[:limit]))   # only records naming the gene
    rows = []
    for item in raw.get("results", [])[:limit]:
        desc = (((item.get("proteinDescription") or {}).get("recommendedName") or {})
                .get("fullName", {}).get("value", ""))
        functions = []
        for comment in item.get("comments") or []:
            if comment.get("commentType") != "FUNCTION": continue
            for value in comment.get("texts") or []:
                if value.get("value"): functions.append(str(value["value"]))
        rows.append({"accession": item.get("primaryAccession"), "id": item.get("uniProtkbId"),
                     "protein_name": desc, "organism": (item.get("organism") or {}).get("scientificName"),
                     "taxon_id": (item.get("organism") or {}).get("taxonId"),
                     "organism_lineage": [name for name in (item.get("organism") or {}).get("lineage", [])
                                          if isinstance(name, str)],
                     "genes": item.get("genes") or [],
                     "protein_aliases": [str((name.get('fullName') or {}).get('value')) for name in
                                         (item.get('proteinDescription') or {}).get('alternativeNames', [])
                                         if (name.get('fullName') or {}).get('value')],
                     "organism_aliases": [str((item.get('organism') or {})[key]) for key in ('commonName',)
                                          if (item.get('organism') or {}).get(key)],
                     "length": (item.get("sequence") or {}).get("length"),
                     "function": " ".join(functions)[:1200],
                     "domains": [{k: f[k] for k in ("type", "description", "location", "evidences") if k in f}
                                 for f in item.get("features", []) if f.get("type") == "Domain"][:40],
                     "topology": [{k:f[k] for k in ('type','description','location','evidences') if k in f}
                                  for f in item.get('features', [])
                                  if f.get('type') in ('Transmembrane','Topological domain')][:80],
                     "features_named": _features_named(item.get("features") or []) + [
                         "Cofactor: " + str(c.get("name")) for comment in item.get("comments") or []
                         if comment.get("commentType") == "COFACTOR" for c in comment.get("cofactors") or []
                         if isinstance(c, dict) and c.get("name")][:12],
                     "pdb_ids": [x.get("id") for x in item.get("uniProtKBCrossReferences", []) if x.get("database") == "PDB"][:8],
                     "chembl_ids": [x.get("id") for x in item.get("uniProtKBCrossReferences", []) if x.get("database") == "ChEMBL"][:8],
                     "sequence": (item.get("sequence") or {}).get("value", "")[:SEQUENCE_KEPT],
                     **({"sequence_shown": "first %d residues" % SEQUENCE_KEPT}
                        if len((item.get("sequence") or {}).get("value", "")) > SEQUENCE_KEPT else {}),
                     **({"found_by": relaxed, "curated": str(item.get("entryType", "")).startswith("UniProtKB reviewed"),
                         "partial_match": relaxed == "partial_any_word"}
                        if relaxed else {})})
    for row in rows:
        row['topology_summary'] = topology_summary(row.get('topology'))
    from lab_sources import receipt
    source_receipt = (None if fallback_reason else
        receipt('uniprot', {'requested_query': requested_query, 'executed_query': executed_query},
                raw.get('results', [])[:limit], metadata={'coverage':'bounded_first_page',
                                                          **({'scope_resolution':scope_resolution} if scope_resolution else {}),
                                                          **({'relaxed': relaxed,
                                                              'partial_match': relaxed == 'partial_any_word'}
                                                             if relaxed else {})}))
    return {"source_receipt": source_receipt, "records": rows, "requested_query": requested_query,
            "executed_query": executed_query, "fallback_reason": fallback_reason, "relaxed": relaxed, "scope_resolution": scope_resolution}


def _resolve_free_record_discovery(inquiry, records):
    """Turn one broad plain-name discovery into one exact sourced review."""
    query = str(inquiry.get('uniprot_query') or '')
    terms = _intent_terms(query)
    if (not records or len(terms) != 1 or not terms[0].startswith('protein_name:')
            or re.search(r'\b(?:accession|gene|taxonomy_id|organism_id|organism_name):', query, re.I)):
        return inquiry, records, None
    if not re.search(r'\bcurated\s+(?:UniProt\s+)?records?\b', str(inquiry.get('question') or ''), re.I):
        return inquiry, records, None
    expected = terms[0].split(':', 1)[1].strip('"')
    normal = lambda value: ' '.join(re.findall(r'[^\W_]+', str(value).casefold()))
    wanted = normal(expected)
    def rank(pair):
        index, row = pair
        names = [row.get('protein_name') or ''] + list(row.get('protein_aliases') or [])
        normalized = [normal(name) for name in names if name]
        quality = 0 if wanted in normalized else 1 if any(
            (' ' + wanted + ' ') in (' ' + name + ' ') for name in normalized) else 2
        return quality, index
    _, selected = min(enumerate(records), key=rank)
    accession = str(selected.get('accession') or '').upper()
    name = str(selected.get('protein_name') or expected).strip()
    if not re.fullmatch(r'[A-Z0-9]{6,10}', accession) or not name:
        return inquiry, records, None
    question = _record_connection_question(name, accession)
    exact = 'accession:' + accession
    digest = hashlib.sha256(question.encode()).hexdigest()
    resolved = dict(inquiry, question=question, uniprot_query=exact, identity_queries=[exact],
                    identity_context={'version':1, 'question_sha256':digest, 'original_queries':[exact]},
                    source_query_question_sha256=digest,
                    query_resolution={'requested_query':query, 'executed_query':exact,
                                      'reason':'plain_name_discovery_resolved_to_returned_record',
                                      'accession':accession})
    scope = resolved.get('planning_scope')
    if isinstance(scope, dict) and not scope.get('line') and not scope.get('frontier') and not scope.get('atlas'):
        resolved['planning_scope'] = dict(scope, question=' '.join(question.casefold().split()))
        resolved['planning_evidence'] = _planning_evidence(resolved)
    return resolved, [selected], {'accession':accession, 'protein_name':name,
                                  'returned_record_count':len(records)}


def _embed_records(records):
    if not (os.path.isfile(ESMC_PYTHON) and os.path.isfile(ESMC_WORKER)):
        return {"ok": False, "state": "adapter_unavailable", "embeddings": []}
    done = subprocess.run(
        [ESMC_PYTHON, ESMC_WORKER],
        input=json.dumps({"records": records}), text=True, capture_output=True,
        timeout=240, check=False,
        env={**os.environ, "HF_HOME": os.path.expanduser(
            "~/.vintos/tools/chemistry-lab/checkpoints/huggingface")},
    )
    if done.returncode:
        raise RuntimeError("ESMC adapter failed: " + done.stderr.strip()[-400:])
    value = json.loads(done.stdout)
    if not isinstance(value, dict) or not value.get("ok"):
        raise RuntimeError("ESMC adapter returned no valid receipt")
    return value


def _write_collision_adapter(records, embeddings):
    """Put source-backed descriptors into the house text space.

    The ESM vector is retained only as lineage.  It is never compared with a
    Nomic vector.  self_review embeds ``text`` with its own encoder later.
    """
    prior = {row.get("adapter_id") for row in _jsonl(COLLISION_ADAPTER)}
    by_accession = {str(row.get("accession")): row for row in embeddings if row.get("accession")}
    written = []
    for record in records:
        accession = str(record.get("accession") or "").strip()
        receipt = by_accession.get(accession)
        if not accession or not receipt: continue
        descriptor = {
            "accession": accession,
            "protein_name": str(record.get("protein_name") or "")[:500],
            "organism": str(record.get("organism") or "")[:300],
            "length": record.get("length"),
            "function": str(record.get("function") or "")[:1200],
        }
        source_sha = hashlib.sha256(json.dumps(descriptor, sort_keys=True).encode()).hexdigest()
        adapter_id = hashlib.sha256((source_sha + "\x1f" + str(receipt.get("embedding_sha256") or "")).encode()).hexdigest()[:24]
        if adapter_id in prior: continue
        pieces = ["UniProtKB protein record", descriptor["protein_name"],
                  "organism " + descriptor["organism"] if descriptor["organism"] else "",
                  "length %s residues" % descriptor["length"] if descriptor["length"] else "",
                  "function annotation " + descriptor["function"] if descriptor["function"] else ""]
        row = {"adapter_id": adapter_id, "at": now_iso(), "source": "UniProtKB",
               "source_accession": accession, "source_metadata_sha256": source_sha,
               "protein_representation_sha256": receipt.get("embedding_sha256"),
               "protein_representation_artifact": receipt.get("artifact"),
               "transform": "uniprot_metadata_to_text_v1_then_house_nomic",
               "text": "; ".join(x for x in pieces if x),
               "truth_status": "source_metadata_adapter_not_biological_inference",
               "evidence_standing": "eligible_as_text_collision_source_only"}
        _append(COLLISION_ADAPTER, row); prior.add(adapter_id); written.append(row)
    return written


def _jsonl(path):
    rows = []
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    if line.strip(): rows.append(json.loads(line))
                except Exception: pass
    except FileNotFoundError:
        pass
    return rows


def _jsonl_tail(path, limit, kinds=None):
    """Read the newest matching JSONL rows without rescanning a large ledger.

    Lab ledgers are append-only.  Walking backwards matters once the notebook is
    tens of megabytes: the phone asks for a small live window every 15 seconds.
    Returned rows keep chronological order, matching ``_jsonl(path)[-limit:]``.
    """
    try: limit = max(0, int(limit))
    except (TypeError, ValueError): limit = 0
    if not limit: return []
    accepted = set(kinds or ())
    rows, remainder = [], b""
    try:
        with open(path, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            position = stream.tell()
            while position > 0 and len(rows) < limit:
                size = min(65536, position)
                position -= size
                stream.seek(position)
                block = stream.read(size) + remainder
                lines = block.split(b"\n")
                remainder = lines[0]
                for raw in reversed(lines[1:]):
                    if not raw.strip(): continue
                    try: row = json.loads(raw.decode("utf-8", "replace"))
                    except Exception: continue
                    if accepted and row.get("kind") not in accepted: continue
                    rows.append(row)
                    if len(rows) >= limit: break
            if position == 0 and len(rows) < limit and remainder.strip():
                try: row = json.loads(remainder.decode("utf-8", "replace"))
                except Exception: row = None
                if row is not None and (not accepted or row.get("kind") in accepted): rows.append(row)
    except (FileNotFoundError, OSError):
        return []
    rows.reverse()
    return rows


_NOT_GENUS = frozenset("""What Which How Does Do Did Is Are Was Were Can Could Would Should Why When Where Given In On
The A An And Or If Under Within Between Across For From With This That These Those Recent Since After Before""".split())


def _organism_names(question):
    """Organism names in his question, most specific first: the binomial, then its genus."""
    out = []
    for genus, species in re.findall(r"\b([A-Z][a-z]{3,})\s+([a-z]{3,})\b", str(question or "")):
        if genus in _NOT_GENUS: continue
        for name in (genus + " " + species, genus):
            if name not in out: out.append(name)
    return out[:4]


def resolve_taxa(query, question, lookup=None, force=False):
    """An organism ID he wrote from memory is replaced by the one NCBI Taxonomy returns for the organism he
    named. One wrong number emptied every search on Colwellia's cold-shock protein, looser forms and all
    (2026-09-28). IDs a receipt has already returned are trusted; a name that cannot be looked up leaves
    his ID as it was. Returns (query, what_changed)."""
    ids = re.findall(r"\b(?:taxonomy_id|organism_id):(\d+)", str(query or ""))
    guessed = [i for i in dict.fromkeys(ids) if force or i not in known_taxa()]
    if not guessed: return query, None
    if lookup is None:
        from lab_sources import Sources
        lookup = lambda name: Sources()._taxon({"organism": name})
    for name in _organism_names(question):
        try: found = lookup(name)
        except Exception as exc:
            _fault("resolve_taxa", exc); return query, None
        if found:
            if force and set(guessed) == {str(found)}: return query, None   # his ID was right
            for old in guessed:
                query = re.sub(r"\b(?:taxonomy_id|organism_id):" + old + r"\b", "taxonomy_id:" + str(found), query)
            _add_known_taxa({str(found)})
            return query, {"guessed": guessed, "resolved": str(found), "from_name": name}
    return query, None


MATERIAL_REVIEWS = 2


def _gather_material(state, inquiry, fresh_only=False):
    """Fetch published abstracts for the question into state. True when there is something to read.

    fresh_only: when the abstracts are all there is to read, the same papers reviewed MATERIAL_REVIEWS
    times already are not reviewed again (three near-identical Tyr51 reviews in two minutes, 2026-09-28)."""
    if state.get("material") is None:
        try:
            import chemistry_sources
            source = (state.get('additional_source') or {})
            source = source.get('receipt') or source.get('source_receipt') or {}
            pmids = list(dict.fromkeys(str((r.get('primary_citation') or {}).get('pdbx_database_id_PubMed'))
                for r in source.get('records', []) if isinstance(r, dict)
                and (r.get('primary_citation') or {}).get('pdbx_database_id_PubMed')))[:3]
            # PubMed search is discovery metadata. Read its returned articles
            # through the existing bounded material path, not a new guessed search.
            if (source.get('source') == 'ncbi' and
                    (source.get('metadata') or {}).get('database') == 'pubmed'):
                pmids = list(dict.fromkeys(str(r.get('uid')) for r in source.get('records', [])
                    if isinstance(r, dict) and re.fullmatch(r'[0-9]{1,12}', str(r.get('uid') or ''))))[:3]
            found = chemistry_sources.material(inquiry, primary_pmids=pmids) if pmids else chemistry_sources.material(inquiry)
        except Exception as exc:
            _fault("material", exc); found = None
        state["material"] = found or {}
    records = (state["material"] or {}).get("records") or []
    if fresh_only and records and journal_source_saturated(
            ["PMID-" + str(r.get("pmid")) for r in records if r.get("pmid")], limit=MATERIAL_REVIEWS):
        state["material_repeated"] = True
        return False
    return bool(records)


_SEQ = re.compile(r"[A-Z*\-]{40,}")
OBSERVED = 14000        # characters of observations a review reads


def _clip(o, cap):
    """Long prose shortened, long lists cut short, each saying so; a sequence is never shortened."""
    if isinstance(o, str):
        return o if len(o) <= cap or _SEQ.fullmatch(o) else o[:cap] + "...[shortened]"
    if isinstance(o, list):
        kept = [_clip(x, cap) for x in o[:max(4, cap // 50)]]
        return kept + (["...[%d more items not shown]" % (len(o) - len(kept))] if len(o) > len(kept) else [])
    if isinstance(o, dict):
        return {k: _clip(v, cap) for k, v in o.items()}
    return o


def embedding_coverage(embeddings, records=()):
    """One line per ESM-C receipt saying how much of the chain its vector holds, first in what the review reads, so a
    cut cannot drop it. Checked against the record's own length too: a receipt that does not say (an older worker)
    and is shorter than its record is partial (2026-10-07: past 2100 residues the rest was dropped without a word)."""
    lengths = {}
    for r in records or []:
        n = r.get("length") or len(str(r.get("sequence") or ""))
        if r.get("accession") and n:
            lengths[str(r["accession"])] = int(n)
    out = []
    for e in embeddings or []:
        acc = str(e.get("accession", "?"))
        got = int(e.get("sequence_length") or 0)
        full = max(int(e.get("input_length") or 0), lengths.get(acc, 0), got)
        if got and got >= full:
            out.append("%s: the embedding covers the whole chain (%d residues)" % (acc, full))
        elif got:
            out.append("%s: PARTIAL embedding: residues 1-%d of %d; residues %d-%d are NOT in this vector, so it says "
                       "nothing about them" % (acc, got, full, got + 1, full))
        else:
            out.append("%s: coverage not reported" % acc)
    return out


NUMERIC_ARRAY = 64   # numbers in a row past which an array is named rather than written out


SHORT_RUN = 64    # short values in a row past which a list is named rather than written out


def _short_run(value):
    """A long list of short scalars no one can quote (a track of scores or labels): its length named instead."""
    # homogeneous only: a run of short strings (a track of labels or scores written as text). A list that mixes
    # words in among numbers is written out as before, so nothing worded is ever hidden inside a count.
    return (isinstance(value, list) and len(value) >= SHORT_RUN
            and all(isinstance(v, str) and len(v) < QUOTABLE_MIN for v in value))


def _named_numeric_arrays(value, receipt_id, _depth=0, _key=None):
    """A long run of numbers named instead of written out, the way a long sequence already is.

    11 October 09:15, HSP90AA1: the evidence was 8 KB of records and abstracts beside a 1.37 MB numeric payload in
    the instrument receipt, and the reading was deferred at an estimated 1,487,450 tokens. A model reading text can
    neither quote nor cite a float array; this keeps its length and where it lives, and the array itself stays whole
    in its source receipt and in the deferred snapshot. No prose, record field, abstract or citation is touched.
    """
    if isinstance(value, (list, tuple)):
        flat = []
        def numbers(node):
            if isinstance(node, bool) or node is None: return False
            if isinstance(node, (int, float)): flat.append(node); return True
            return isinstance(node, (list, tuple)) and all(numbers(child) for child in node)
        if value and numbers(value) and len(flat) >= NUMERIC_ARRAY:
            return ('[%d numeric values%s; complete array in source receipt%s; not quotable text]'
                    % (len(flat), ', shape %d' % len(value) if len(value) != len(flat) else '',
                       ' ' + str(receipt_id) if receipt_id else ''))
        # 15 October: deferred requests carried 37-43k characters of evidence in ~4,400 leaves, almost all short
        # values in long runs. None can be quoted (too short to carry one, so never addressed), but every one
        # was written into the checker's request. A named list of facts (features, aliases, ids) is kept whole.
        if _key not in QUOTABLE_LISTS and _short_run(value):
            return ('[%d short values; complete list in source receipt%s; not quotable text]'
                    % (len(value), ' ' + str(receipt_id) if receipt_id else ''))
        if _depth >= 6: return value
        return [_named_numeric_arrays(child, receipt_id, _depth + 1) for child in value]
    if isinstance(value, dict) and _depth < 6:
        return {key: _named_numeric_arrays(child, receipt_id, _depth + 1, key) for key, child in value.items()}
    return value


def _interval_text(location):
    """A UniProt location as the text a quote can be taken from: 'residues 120-198' (or 'residue 63')."""
    if not isinstance(location, dict):
        return location
    start = (location.get("start") or {}).get("value") if isinstance(location.get("start"), dict) else location.get("start")
    end = (location.get("end") or {}).get("value") if isinstance(location.get("end"), dict) else location.get("end")
    if start is None and end is None:
        return location
    return ("residue %s" % start) if start == end or end is None else ("residues %s-%s" % (start, end))


def _atom_text(atom):
    """One atom of a PDB record as a quotable line: residue, number, chain, atom, xyz, and distance when given."""
    xyz = atom.get("coordinates_angstroms") or []
    line = "%s %s%s chain %s atom %s at (%s) angstroms" % (
        atom.get("residue") or atom.get("element") or "?", atom.get("residue_number", "?"), atom.get("insertion_code") or "",
        atom.get("chain") or "?", atom.get("atom") or "?", ", ".join("%.3f" % float(c) for c in xyz))
    if atom.get("distance_angstroms") is not None:
        line += ", %.2f angstroms from the metal" % float(atom["distance_angstroms"])
    return line


def _quotable_structure(value, _depth=0):
    """Coordinates and site geometry the checker can quote. They were dicts of numbers, and a number gets no
    address, so every coordinate question failed validation even when the coordinates were in front of it
    (15 October: source/pdb/records/0/metal_sites/0/nearby_atoms)."""
    if _depth > 8:
        return value
    if isinstance(value, list):
        return [_quotable_structure(v, _depth + 1) for v in value]
    if not isinstance(value, dict):
        return value
    if "coordinates_angstroms" in value and "nearby_atoms" not in value:
        return _atom_text(value)
    out = {k: _quotable_structure(v, _depth + 1) for k, v in value.items()}
    if "nearby_atoms" in value and "coordinates_angstroms" in value:
        out = {"metal": _atom_text(value), "nearby_atoms": out.get("nearby_atoms")}
    return out


def review_observations(inquiry, observations):
    """Remove receipt/embedding duplication before budgeting actual evidence."""
    if not isinstance(observations, dict): return observations
    source = observations.get('additional_source') or {}
    receipt = source.get('receipt') or source.get('source_receipt') or source.get('instrument_receipt') or {}
    _receipt_id = receipt.get('receipt_id')
    result = {'embedding_coverage':observations.get('embedding_coverage'),
              'additional_source': {'source':receipt.get('source'),
              'receipt_id':_receipt_id,
              'records':_quotable_structure(_named_numeric_arrays(receipt.get('records'), _receipt_id)),
              'instrument_result':_named_numeric_arrays(source.get('instrument_result'), _receipt_id)},
              'LITERATURE':observations.get('LITERATURE') or [],
              'prior_validated_evidence': observations.get('prior_validated_evidence') or [],
              'atlas_analysis':observations.get('atlas_analysis')}
    if observations.get('FULLTEXT'):   # full-text passages for the unanswered claims (lab_claim_evidence)
        result['FULLTEXT'] = observations['FULLTEXT']
    if observations.get('STRUCTURE'):  # deposited entries the records named, read beside his own source
        result['STRUCTURE'] = [_quotable_structure(_named_numeric_arrays(_structure_text(r), None))
                               for r in observations['STRUCTURE']]
    proteins = []
    sequence_requested = bool(re.search(r'sequence|residue|motif|amino.acid', str(inquiry.get('question') or ''), re.I))
    for row in observations.get('records') or []:
        item = dict(row)
        for key in ('domains', 'topology'):   # positions as text a quote can come from, not dicts of numbers
            if isinstance(item.get(key), list):
                item[key] = [dict(d, location=_interval_text(d.get('location'))) if isinstance(d, dict) else d
                             for d in item[key]]
        seq = item.get('sequence')
        if isinstance(seq, str) and len(seq) > 350 and not sequence_requested:
            item['sequence'] = '[%d residues; complete sequence in source receipt; not needed for geometry]' % len(seq)
        proteins.append(item)
    result['records'] = proteins
    result['embedding_coverage'] = observations.get('embedding_coverage')
    # long runs of short values anywhere outside the prose sources are named, not written out
    for key in ('records', 'atlas_analysis', 'embedding_coverage'):
        if result.get(key) is not None:
            result[key] = _named_numeric_arrays(result[key], _receipt_id)
    return result


def observed(records, budget=OBSERVED):
    """What a review reads of its observations. It was json.dumps(records)[:14000]: the raw UniProt rows came after
    everything else and the cut fell inside a sequence, so he read "the sequence field in the current record is
    truncated" of a record that was whole (SLC26A6, 759 residues; Gloria, 2026-10-05). Now prose and long lists are
    shortened first, sequences kept whole, and if it still does not fit, the excerpt says that it, not the record,
    ends there."""
    text = json.dumps(records, ensure_ascii=False)
    for cap in (2000, 1000, 500, 250, 120):
        if len(text) <= budget:
            return text
        text = json.dumps(_clip(records, cap), ensure_ascii=False)
    if len(text) <= budget:
        return text
    return (text[:budget] + " ...[EXCERPT ENDS HERE: %d more characters of these observations were not shown to you. "
            "The records themselves are complete; do not report them as truncated.]" % (len(text) - budget))


_SEQ_RUN = re.compile(r"[A-Z]{40,}")


def no_partial_sequences(text):
    """A sequence cut to fit a short excerpt reads to him as a truncated record. Every run of sequence letters in a
    short excerpt is named, not shown (2026-10-05: "the truncated C-terminal region", of a record that was whole)."""
    return _SEQ_RUN.sub(lambda m: "[sequence not shown here (%d+ residues); the receipt holds it whole]" % len(m.group(0)),
                        str(text or ""))


def source_summary(records, budget=1800):
    """The notebook's note of what a source returned: whole JSON, each sequence named by its length rather than cut
    part-way (it was json.dumps(records)[:1800], so a 759-residue sequence was noted as its first few hundred)."""
    def walk(o):
        if isinstance(o, str):
            return ("[%d-residue sequence; whole in the receipt]" % len(o)) if _SEQ.fullmatch(o) else o
        if isinstance(o, list):
            return [walk(x) for x in o]
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        return o
    return observed(walk(records), budget)


def sequence_regions(inquiry, observations):
    """Expose exact requested intervals without asking the model to count sequence characters."""
    text = " ".join(str(inquiry.get(k) or "") for k in ("question", "why_now"))
    spans = list(dict.fromkeys(re.findall(r"\b(\d{1,5})\s*[-–]\s*(\d{1,5})\b", text)))[:4]
    rows = observations.get("records", []) if isinstance(observations, dict) else observations
    result = []
    for row in (rows if isinstance(rows, list) else [])[:8]:
        seq = row.get("sequence") or ""
        if not isinstance(seq, str): continue
        for lo, hi in spans:
            start, end = int(lo), int(hi)
            if 1 <= start <= end <= len(seq) and end - start < 350:
                result.append({"accession": row.get("accession"), "source": "retrieved protein record",
                               "start": start, "end": end, "coordinates": "one-based inclusive",
                               "sequence": seq[start-1:end], "length": end-start+1})
    return result


# A conservative local preflight, not a tokenizer count or routing policy.
# Count every UTF-8 byte as a token, plus framing and each stage's output.
# This ceiling matches the verified Aegis Gemma context; never widen a route.
COVERAGE_CONTEXT_BUDGET = 35000
COVERAGE_FRAMING_RESERVE = 1024


def _coverage_budget(request):
    system, prompt, output = request
    size = len(system.encode('utf-8')) + len(prompt.encode('utf-8'))
    total = size + COVERAGE_FRAMING_RESERVE + output
    return {'prompt_utf8_bytes':size, 'framing_reserve':COVERAGE_FRAMING_RESERVE,
            'output_reservation':output, 'conservative_total':total,
            'context_budget':COVERAGE_CONTEXT_BUDGET, 'fits':total <= COVERAGE_CONTEXT_BUDGET}


def _coverage_fits(inquiry, observations):
    """True when this evidence could be assessed now, whole or split, by the same budget the review uses; nothing is
    written. _coverage_deferral saves a snapshot when it defers, which a mere question must not."""
    prepared = _coverage_request(inquiry, observations)
    if not prepared: return False
    if _coverage_parts(prepared) is not None: return True
    evidence, _, _, request = prepared
    return (_coverage_budget(request)['fits']
            and _coverage_budget(_coverage_sufficiency_request(inquiry, evidence))['fits'])


def _coverage_preflight(inquiry, observations, prepared):
    """Persist all input before deferring; unchanged oversized input never calls a model."""
    if not prepared: raise ValueError('coverage addresses could not be constructed without collision')
    evidence, _, _, request = prepared
    budgets = {'coverage':_coverage_budget(request),
               'independent_sufficiency':_coverage_budget(_coverage_sufficiency_request(inquiry, evidence))}
    if all(item['fits'] for item in budgets.values()): return None
    failures = ['%s needs %s conservative tokens including %s output, budget %s' %
                (stage, item['conservative_total'], item['output_reservation'], item['context_budget'])
                for stage,item in budgets.items() if not item['fits']]
    reason = 'coverage deferred: full original question and evidence exceed context budget; ' + '; '.join(failures)
    payload = {'original_question':inquiry['question'], 'inquiry':inquiry,
               'observations':observations, 'coverage_evidence':evidence}
    digest = hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    directory = os.path.join(ROOT, 'coverage-deferred')
    path = os.path.join(directory, digest + '.json')
    os.makedirs(directory, exist_ok=True)
    # Atomic durable write only once for identical inputs. No evidence is removed
    # to make the request fit; new evidence or scope is evaluated independently.
    if not os.path.exists(path): _atomic(path, payload)
    elif _load(path, None) != payload: raise ValueError('deferred evidence snapshot mismatch')
    return {'answers_question':'not assessed: ' + reason, 'missing_evidence':reason,
            'original_question':inquiry['question'], 'factual_observation':'',
            'speculative_reading':'', 'next_question':'', 'instrument_gap':'',
            'line_status':'continue', 'evidence_status':'deferred',
            'coverage_deferred':True, 'coverage_budget':budgets,
            'coverage_snapshot':path, 'coverage_snapshot_sha256':digest,
            'truth_status':'incomplete_context_budget_no_scientific_adjudication'}


COVERAGE_SPLIT_MAX_PARTS = 8


def _coverage_parts(prepared):
    """The coverage evidence in parts that each fit the budget, or None when it cannot be split that way.

    Every list item (record, article, receipt row) goes into exactly one part, whole and with its own exact
    addresses; what is not a list goes into every part. Nothing is dropped or shortened. None when even the shared
    part, or one item alone, is too large, or it would take more than COVERAGE_SPLIT_MAX_PARTS parts."""
    if not prepared: return None
    _evidence, _strings, _addresses, (system, prompt, out) = prepared
    head, marker, body = prompt.partition('\nEVIDENCE:\n')
    if not marker: return None
    try: addressed = json.loads(body)
    except ValueError: return None
    if not isinstance(addressed, dict): return None
    common = {k: v for k, v in addressed.items() if not isinstance(v, list)}
    units = [(k, item) for k, v in addressed.items() if isinstance(v, list) for item in v]
    def request(part):
        return (system, head + '\nEVIDENCE:\n' + json.dumps(part, ensure_ascii=False, separators=(',', ':')), out)
    def fits(part): return _coverage_budget(request(part))['fits']
    if len(units) < 2 or not fits(common): return None
    parts, current = [], {}
    for key, item in units:
        trial = {k: list(v) for k, v in current.items()}
        trial.setdefault(key, []).append(item)
        if fits(dict(common, **trial)):
            current = trial; continue
        if not current: return None                      # one item alone is over the budget
        parts.append(dict(common, **current)); current = {key: [item]}
        if not fits(dict(common, **current)): return None
    if current: parts.append(dict(common, **current))
    if len(parts) < 2 or len(parts) > COVERAGE_SPLIT_MAX_PARTS: return None
    return [request(part) for part in parts]


def _coverage_deferral(inquiry, observations, prepared):
    """Defer (and preserve) only what cannot be assessed: evidence over the budget that also cannot be split.
    Over-budget evidence was always deferred, and deferred work rarely came back: 93 passes and 48 reviews on
    13 October. Split evidence is assessed part by part (_coverage_split)."""
    if prepared and _coverage_parts(prepared) is not None:
        return None
    return _coverage_preflight(inquiry, observations, prepared)


def _coverage_split(inquiry, prepared):
    """Assess over-budget evidence in parts, then decide on what the parts found.

    Each part goes to the same checker; only supports whose quote is verbatim at its exact address are kept. The
    verdict (and the independent sufficiency assessment) is then made on those verified excerpts, each with its
    whole source text, which fits where the full evidence did not. None when the evidence cannot be split."""
    parts = _coverage_parts(prepared)
    if parts is None: return None
    evidence, strings, addresses, (system, prompt, out) = prepared
    head = prompt.partition('\nEVIDENCE:\n')[0]
    normalized = lambda x: ' '.join(str(x).split())
    found, missing, failed = {}, [], 0
    for request in parts:
        try:
            result = _json_object(_ask(request[0], request[1], max_tokens=request[2], temperature=0.0))
        except Exception:
            failed += 1; continue
        for item in result.get('supports') or []:
            if not isinstance(item, dict): continue
            address, quote = item.get('address'), item.get('quote')
            if (isinstance(address, str) and address in addresses and isinstance(quote, str) and quote.strip()
                    and item.get('requirement') and normalized(quote) in normalized(strings[addresses[address]])):
                found.setdefault(address, item)
        missing += [str(m) for m in (result.get('missing') or []) if str(m).strip()]
    sha = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    if failed == len(parts): return None
    if not found:
        return {'answered': False, 'missing': list(dict.fromkeys(missing))[:12] or
                ['no part of the retrieved evidence supports the original question'],
                'original_question': inquiry['question'], 'supports': [], 'discarded_supports': [],
                'evidence_sha256': sha, 'independent_sufficiency': None, 'split_parts': len(parts),
                'split_failed_parts': failed, 'method': 'split_coverage_no_verified_support'}
    for cap in (4000, 1500, 600):
        condensed = {'verified_excerpts': [{'address': a, 'text': strings[addresses[a]][:cap]} for a in found]}
        final = (system, head + '\nEVIDENCE:\n' + json.dumps(condensed, ensure_ascii=False, separators=(',', ':')), out)
        if (_coverage_budget(final)['fits'] and
                _coverage_budget(_coverage_sufficiency_request(inquiry, condensed))['fits']):
            break
    else:
        return None
    result = _coverage_check(inquiry, None, prepared=(evidence, strings, addresses, final), _condensed=condensed)
    if isinstance(result, dict):
        result = dict(result, split_parts=len(parts), split_failed_parts=failed)
    return result


def _coverage_scope(inquiry):
    from lab_sources import original_identity_queries
    return {'original_question':inquiry['question'],
            'original_identity_queries':original_identity_queries(inquiry)}


def _coverage_sufficiency_request(inquiry, evidence):
    return (
            'Independently assess scientific sufficiency against the FULL ORIGINAL QUESTION. '
            'Derive its requirements yourself from that question and the source evidence. '
            'Check all requested entities, organisms, isoforms, comparisons and evidence products. '
            'A real source quote may be relevant yet insufficient. Topology annotations are not a hydropathy profile; '
            'an embedding is not a structure. Do not treat the presence of a label as evidence of a computation. '
            'Return JSON: sufficient (boolean), missing (list of specific unmet requirements), rationale (string). '
            'Original identity queries are constraints, not evidence. Never silently drop a taxonomy filter or '
            'silently choose an unspecified species from a search hit. Clearly species-qualified findings may '
            'be useful partial evidence; do not generalize beyond that scope. Assess the question\'s causal premises too; a '
            'signal mentioned in a question does not establish direct binding. Citation metadata alone cannot '
            'establish a mechanism. Use sufficient=false when ambiguous or unestablished.',
            json.dumps(_coverage_scope(inquiry)) + '\nEVIDENCE:\n' + json.dumps(evidence, ensure_ascii=False),
            800)


QUOTABLE_MIN = 40          # characters below which a leaf cannot carry a verbatim quote on its own
# Named text and identity fields: a leaf here is source material or the thing a requirement is made of, and stays
# addressable however short it is. Everything else must be long enough to carry a verbatim quote.
SHORT_QUOTABLE = ("accession", "id", "entry_id", "pmid", "pmcid", "doi", "organism", "taxon_id", "length",
                  "protein_name", "gene", "geneName", "value", "name", "nickName", "title", "journal", "year",
                  "section", "heading", "sequence", "model", "method", "resolution", "ec", "label", "symbol",
                  "status", "pdb_ids", "chembl_ids", "answered", "claim",
                  "abstract", "full_text", "text", "quote", "summary", "source_summary", "definition",
                  "description", "comment", "note", "function", "topology_summary", "rationale", "reason",
                  "finding", "observation", "requirement", "source_citation", "keywords", "url", "source",
                  "location", "metal", "interval")


# Lists whose every entry is a named fact. An entry is judged by the list it is in, not by its position number:
# judged by "0", "Binding site: Zn(2+)" lost its address and SOD1's zinc question failed validation (14 October).
QUOTABLE_LISTS = ("nearby_atoms", "metal_sites", "features_named", "protein_aliases", "organism_aliases", "pdb_ids", "chembl_ids", "keywords",
                  "synonyms", "sections", "figures", "material_terms", "subjects", "missing", "supports")


def _short_quotable(path):
    """A short leaf that a requirement is genuinely made of — an accession, an organism, a length, a named
    feature — stays addressable however short it is. A bare number inside a score array does not."""
    parts = str(path).split(".")
    tail = parts[-1]
    if tail in SHORT_QUOTABLE:
        return True
    if tail.isdigit() and len(parts) >= 2:
        return parts[-2] in QUOTABLE_LISTS or parts[-2] in SHORT_QUOTABLE
    return False


def _coverage_request(inquiry, observations):
    """Evidence-bound adjudication of the original question, not the proposed next question."""
    if not str(inquiry.get('question') or '').strip(): return None
    evidence = review_observations(inquiry, observations)
    # The checker can only cite strings actually in this compact evidence tree.
    strings = {}
    def walk(value, path):
        if isinstance(value, str): strings[path] = value
        elif (isinstance(value, (int, float)) and not isinstance(value, bool)
              and re.fullmatch(r'evidence\.records\.\d+\.(?:length|taxon_id)', path)):
            strings[path] = str(value)
        elif isinstance(value, dict):
            for key, child in value.items(): walk(child, path + '.' + str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value): walk(child, path + '.' + str(index))
    walk(evidence, 'evidence')
    # Addresses are deterministic for this evidence snapshot, explicitly supplied,
    # and bound to both location and content. Never repair a model's guessed index.
    bibliography_question = bool(re.search(
        r'\b(?:bibliograph\w*|citation metadata|publication year|article title)\b|'
        r'\b(?:what|which|name|identify|list|give)\b.{0,45}\b(?:journal|PMID|DOI)\b',
        inquiry['question'], re.I))
    additional = (observations.get('additional_source') or {}) if isinstance(observations,dict) else {}
    receipt = additional.get('receipt') or additional.get('source_receipt') or {}
    pubmed_summary = (receipt.get('source') == 'ncbi' and
                      (receipt.get('metadata') or {}).get('database') == 'pubmed')
    def quotable_path(path):
        # Known presentation paths only: a scientific field called summary,
        # source or year elsewhere is not transport/bibliographic metadata.
        if path in ('evidence.additional_source.source','evidence.additional_source.receipt_id'):
            return False
        if re.fullmatch(r'evidence.FULLTEXT\.\d+\.(?:pmcid|pmid|title|section|claim|source_url)',path):
            return bibliography_question
        # a citation label or a requirement's name is bookkeeping, not evidence; quoting one was refused anyway
        if re.fullmatch(r'evidence.prior_validated_evidence\.\d+\.(?:source_citation|requirement)', path):
            return False
        bibliography = (re.fullmatch(r'evidence.LITERATURE\.\d+\.(?:pmid|journal|year|title|doi|url)',path)
                        or (pubmed_summary and re.match(r'evidence.additional_source.records\.\d+\.(?:uid$|summary\.)',path)))
        return bibliography_question or not bibliography
    # Every string leaf used to get its own address, and each one costs its wrapper in the request: on 14 October
    # a request carrying 39,244 characters of evidence in 4,382 leaves spent 214,923 characters on the addressing
    # alone, and the question was deferred for a context it never came close to needing. A quote is verbatim text
    # from a source, so a leaf too short to carry one needs no address — except the identity and scalar fields a
    # requirement is genuinely made of, which stay addressable at any length.
    quotable = {path:text for path,text in strings.items()
                if quotable_path(path) and (len(text) >= QUOTABLE_MIN or _short_quotable(path))
                and not (text.startswith('[') and 'not quotable text' in text)}   # a placeholder is not evidence
    digests = {hashlib.sha256(json.dumps([path, text], ensure_ascii=False).encode()).hexdigest(): path
               for path, text in quotable.items()}
    if len(digests) != len(quotable): return None
    width = 8
    while len({digest[:width] for digest in digests}) != len(digests):
        width += 1
    def label(path):
        match = re.match(r'evidence.LITERATURE\.(\d+)\.(.+)',path)
        if match:
            pmid = str(evidence['LITERATURE'][int(match[1])].get('pmid') or '')
            if re.fullmatch(r'[0-9]+',pmid): return 'PMID:'+pmid+'/'+match[2]
        match = re.match(r'evidence.records\.(\d+)\.(.+)',path)
        if match:
            accession = str(evidence['records'][int(match[1])].get('accession') or '')
            if re.fullmatch(r'[A-Za-z0-9_-]+',accession): return 'UniProt:'+accession+'/'+match[2]
        match = re.match(r'evidence.FULLTEXT\.(\d+)\.(.+)',path)
        if match:
            pmcid = str(evidence['FULLTEXT'][int(match[1])].get('pmcid') or '')
            if re.fullmatch(r'PMC[0-9]+',pmcid): return pmcid+'/'+match[2]
        return 'source/'+'.'.join(part for part in path.split('.')[-2:] if not part.isdigit())
    labels = {digest:label(path) for digest,path in digests.items()}
    # Readable exact-leaf IDs; duplicates remain distinct and bound to full
    # location/content digests. Never locate a quote by searching other leaves.
    counts = {value:list(labels.values()).count(value) for value in set(labels.values())}
    # A repeated label gets a short ordinal (#1, #2 in evidence order), not a hex digest: the checker miscopied
    # digests ("abstract#50adb626") and every such support was refused (15 October). The address still names
    # exactly one leaf; nothing is ever located by searching other leaves.
    seen_label, addresses = {}, {}
    for digest, path in sorted(digests.items(), key=lambda kv: kv[1]):
        lab = labels[digest]
        if counts[lab] > 1:
            seen_label[lab] = seen_label.get(lab, 0) + 1
            addresses[lab + '#' + str(seen_label[lab])] = path
        else:
            addresses[lab] = path
    by_path = {path: address for address, path in addresses.items()}
    def addressed(value, path):
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            return {'address':by_path[path], 'text':value} if path in by_path else value
        if isinstance(value, dict): return {key:addressed(child,path+'.'+str(key)) for key,child in value.items()}
        if isinstance(value, list): return [addressed(child,path+'.'+str(index)) for index,child in enumerate(value)]
        return value
    addressed_evidence = addressed(evidence, 'evidence')
    coverage_request = ('You are a technical evidence-coverage checker, not Vintos. Adjudicate only the ORIGINAL QUESTION. '
        'A harder follow-up is not a missing requirement of the original question. Domain organization does not '
        'require residue coordinates unless the question requests them. Every explicit comparison, organism, '
        'domain or relationship in the question must be covered. Empty searches and model embeddings prove no '
        'biological properties. Geometric proximity is not proof of binding, function or membrane orientation. '
        'Enumerate every requested evidence product separately before deciding coverage. Source topology '
        'annotations do not supply a computed hydropathy profile; a sequence alone is not a computed profile. '
        'Check identity and species separately from whether the requested measurement or analysis is present. '
        'Return JSON: answered (boolean), missing (list), supports (list of {requirement, address, quote}). '
        'For answered=true, all original requirements must be supported by verbatim quotes at their exact evidence '
        'addresses. Quotable source text is wrapped as {address, text}; readable addresses name the source '
        'and exact field. Known transport metadata remains visible without quote addresses. Bibliographic '
        'facts receive addresses when the original question requests them; they cannot establish a mechanism. '
        'Copy an emitted address exactly and quote only its adjacent text. The wrapper is metadata, '
        'not scientific evidence. '
        'Do not construct paths, count records, or use an address belonging to another source. Use at most six '
        'supports and concise quotes of at most 300 characters, only the necessary source clause. When none of the '
        'requested claims has support, return answered=false, the specific missing claims, and supports=[]. An empty '
        'or absent source field is missing evidence and must never be cited as support. For anything absent, '
        'ambiguous, or conflicting, answered=false. Original identity queries are constraints, not evidence: '
        'do not drop their taxonomy or substitute a species. If species is unspecified, retain the evidence\'s '
        'species-qualified scope as partial findings without silently generalizing. Assess causal premises '
        'rather than assuming them; citation metadata does not '
        'establish a mechanism. Do not infer missing facts.'
        + (_class_scope_text([{'accession': a, 'name': ''} for a in inquiry['class_members']])
           if (inquiry or {}).get('class_members') else ''),
        json.dumps(_coverage_scope(inquiry)) + '\nEVIDENCE:\n' +
        json.dumps(addressed_evidence, ensure_ascii=False, separators=(',',':')),
        1100)
    return evidence, strings, addresses, coverage_request


def _coverage_check(inquiry, observations, prepared=None, _condensed=None):
    if not str(inquiry.get('question') or '').strip(): return None
    prepared = prepared or _coverage_request(inquiry, observations)
    if not prepared: return None
    evidence, strings, addresses, coverage_request = prepared
    if _condensed is None:
        if not all(_coverage_budget(r)['fits'] for r in
                   (coverage_request, _coverage_sufficiency_request(inquiry, evidence))):
            split = _coverage_split(inquiry, prepared)
            if split is not None: return split
        deferred = _coverage_preflight(inquiry, observations, prepared)
        if deferred: return deferred
    first = _coverage_attempt(inquiry, evidence, strings, addresses, coverage_request, _condensed, '')
    if first.get('assessment_status') != 'incomplete' or first.get('model_unavailable'):
        return first   # a model that did not answer is not asked again (its own rule); only a rejected answer is
    # One more answer, told exactly why the first was rejected (13 October: 53 reviews ended on a rejected checker
    # answer, most for a quote or address off by a little). The new answer is judged by the same rules; nothing in
    # the first one is repaired or carried over.
    try:
        second = _coverage_attempt(inquiry, evidence, strings, addresses, coverage_request, _condensed,
                                   _coverage_retry_note(first))
    except Exception:
        return first
    return dict(second, first_attempt_failure=first.get('validation_failure'))


def _coverage_retry_note(first):
    lines = ['', '', 'YOUR PREVIOUS ANSWER WAS REJECTED: ' + str(first.get('validation_failure') or 'invalid answer') + '.']
    for item in (first.get('discarded_supports') or [])[:4]:
        support = item.get('support') if isinstance(item.get('support'), dict) else item
        lines.append('- %s: %s' % (str((support or {}).get('address') or item.get('path') or '?')[:80],
                                   str(item.get('reason') or '')[:80]))
    lines.append('Answer again from the same evidence, as JSON only. Copy each address exactly as it is emitted and '
                 'quote only words that appear verbatim in that address\'s own text. A requirement you cannot support '
                 'goes in missing, with answered false.')
    return '\n'.join(lines)


def _coverage_attempt(inquiry, evidence, strings, addresses, coverage_request, _condensed, note):
    raw = _ask(coverage_request[0], coverage_request[1] + note, max_tokens=coverage_request[2], temperature=0.0)
    result = _json_object(raw)
    supports = result.get('supports')
    verified=[]; discarded=[]
    def incomplete(reason):
        return {'answered':False, 'missing':[], 'assessment_status':'incomplete',
                'validation_failure':reason, 'original_question':inquiry['question'],
                'supports':verified, 'discarded_supports':discarded,
                'checker_raw':raw, 'checker_response':result, 'independent_sufficiency':None,
                'evidence_sha256':hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest(),
                'method':'exact_quote_integrity_only_not_answer_sufficiency'}
    if (type(result.get('answered')) is not bool or not isinstance(result.get('missing'), list)
            or not isinstance(supports, list)): return incomplete('coverage response lacks a valid verdict and source supports')
    if result['answered'] and not supports: return incomplete('positive coverage response has no source supports')
    if result['answered'] and result['missing']: return incomplete('coverage verdict conflicts with its missing list')
    if not result['answered'] and not result['missing']: return incomplete('negative coverage omitted specific missing requirements')
    normalized = lambda x: ' '.join(str(x).split())
    required = {str(item.get('requirement') or '') for item in supports if isinstance(item, dict)}
    for item in supports:
        if not isinstance(item, dict):
            discarded.append({'support':item,'reason':'malformed_support'});continue
        quote, address = item.get('quote'), item.get('address')
        if not isinstance(address, str) or address not in addresses:
            discarded.append({'support':item,'reason':'unknown_or_nonquotable_address'});continue
        path = addresses[address]
        if not isinstance(quote, str) or not quote.strip() or not item.get('requirement'):
            discarded.append({'support':item,'path':path,'reason':'malformed_support'});continue
        # Resolve only the explicitly addressed leaf, never a different source.
        leaves=[path]
        matches=[key for key in leaves if normalized(quote) in normalized(strings[key])]
        if not matches:
            discarded.append({'support':item,'requirement':item['requirement'],'path':path,'reason':'quote_not_in_cited_source'})
            continue
        item=dict(item,path=matches[0])
        match = re.match(r'evidence.LITERATURE\.(\d+)\.', item['path'])
        if match: item['source_citation'] = 'PMID ' + str(evidence['LITERATURE'][int(match[1])].get('pmid'))
        match = re.match(r'evidence.FULLTEXT\.(\d+)\.', item['path'])
        if match:
            passage = evidence['FULLTEXT'][int(match[1])]
            item['source_citation'] = (str(passage.get('pmcid')) + (', ' + str(passage['section'])
                                       if passage.get('section') else ''))
        match = re.match(r'evidence.records\.(\d+)\.', item['path'])
        if match:
            accession = evidence['records'][int(match[1])].get('accession')
            if accession: item['source_citation'] = 'UniProt ' + str(accession)
        match = re.match(r'evidence.prior_validated_evidence\.(\d+)\.quote$', item['path'])
        if match:
            citation = evidence['prior_validated_evidence'][int(match[1])].get('source_citation')
            if citation: item['source_citation'] = str(citation)
        verified.append(item)
    if discarded or (supports and (not verified or {item['requirement'] for item in verified} != required)):
        return incomplete('source-address validation failed; full original-question coverage was not assessed')
    supports=verified
    sufficiency = None
    if result['answered']:
        # Blind second assessment: it receives neither the first verdict nor its
        # self-selected requirements. Agreement is model assessment, not proof.
        request = _coverage_sufficiency_request(inquiry, evidence if _condensed is None else _condensed)
        try: sufficiency = _json_object(_ask(request[0], request[1], max_tokens=request[2], temperature=0.0))
        except Exception:
            return dict(incomplete('independent sufficiency assessment unavailable or malformed'), model_unavailable=True)
        if (type(sufficiency.get('sufficient')) is not bool or not isinstance(sufficiency.get('missing'),list)
                or not isinstance(sufficiency.get('rationale'),str) or not sufficiency['rationale'].strip()): return incomplete('independent sufficiency response invalid')
        if sufficiency['sufficient'] and sufficiency['missing']: return incomplete('independent sufficiency verdict conflicts with missing list')
        if not sufficiency['sufficient'] and not sufficiency['missing']: return incomplete('independent sufficiency omitted missing requirements')
        if not sufficiency['sufficient']:
            result = dict(result, answered=False, missing=sufficiency['missing'])
    return {'answered':result['answered'], 'missing':result['missing'],
            'original_question':inquiry.get('question'), 'supports':supports, 'discarded_supports':discarded,
            'evidence_sha256':hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest(),
            'independent_sufficiency':sufficiency,
            'method':'source_quote_integrity_and_independent_model_sufficiency_not_scientific_proof'}



def _incomplete_assessment(inquiry, value, raw, coverage=None, reason=None):
    coverage = coverage or {}
    supports = coverage.get('supports') or []
    # not "no": a checker that failed has not judged the science (Gloria, 2026-10-14)
    return {'answers_question':'not assessed: answer sufficiency not established because assessment validation failed',
            'assessment_status':'incomplete', 'evidence_status':'partial' if supports else 'incomplete',
            'original_question':inquiry.get('question'), 'missing_evidence':'',
            'validation_failure':reason or coverage.get('validation_failure') or 'coverage assessment unavailable or invalid',
            'attention':'', 'next_question':'', 'instrument_gap':'', 'speculative_reading':'',
            'factual_observation':'\n'.join(item['quote'] +
                (' ['+item['source_citation']+']' if item.get('source_citation') else '') for item in supports),
            'validated_source_excerpts':supports, 'coverage_check':coverage,
            'reader_audit':{'raw':raw, 'parsed':value},
            'evidence_gap':{'kind':'assessment_validation_failure','automatic_followup':False},
            'truth_status':'exact_source_excerpts_only_relevance_and_full_sufficiency_unestablished',
            'line_status':'continue'}


CLAIM_FULLTEXT_FETCH = None   # set only by this file's own daemon/tick: an imported Lab never searches Europe PMC


def _claim_ledger():
    return os.path.join(ROOT, 'claim-evidence.json')


def _reflect_with_claim_evidence(context, inquiry, observations, records):
    """The review, and when it leaves claims of the question unanswered, the same whole question reviewed again with
    full-text passages for those claims (T-17420bd6, 2026-10-14). Returns (reflection, fields for the note):
    review_outcome names a research result, a problem with the question or its target, or a Lab failure; a second
    review that fails as software never replaces the first, and is never a scientific "no"."""
    import lab_claim_evidence as LCE
    question = str(inquiry.get('question') or '')
    prior = []
    try:
        prior = LCE.prior_supports(question, ledger_path=_claim_ledger())
    except Exception as exc:
        _fault('claim_evidence_prior', exc)
    if prior:
        have = {(p.get('requirement'), p.get('quote')) for p in observations.get('prior_validated_evidence') or []}
        observations = dict(observations, prior_validated_evidence=list(observations.get('prior_validated_evidence') or [])
                            + [p for p in prior if (p.get('requirement'), p.get('quote')) not in have])
    reflection = _reflect(context, inquiry, observations)
    gathered, second_attempt = None, None
    if LCE.outcome(reflection)[0] in LCE.SEARCHABLE:
        try:
            gathered = LCE.gather(inquiry, reflection, records, fetch=CLAIM_FULLTEXT_FETCH, ledger_path=_claim_ledger())
        except Exception as exc:
            _fault('claim_evidence_gather', exc)
        if gathered and gathered.get('FULLTEXT'):
            second = _reflect(context, inquiry, dict(observations, FULLTEXT=gathered['FULLTEXT']))
            status = LCE.outcome(second)[0]
            first_supports = len((reflection.get('coverage_check') or {}).get('supports') or [])
            second_supports = len((second.get('coverage_check') or {}).get('supports') or [])
            second_attempt = {'outcome': status, 'supports': second_supports}
            if status in LCE.RESEARCH and (status == 'answered' or second_supports >= first_supports):
                reflection = dict(second, first_review={'outcome': LCE.outcome(reflection)[0], 'supports': first_supports})
    status, why = LCE.outcome(reflection)
    fields = {'review_outcome': status, 'review_outcome_why': why[:400]}
    try:
        fields['claim_evidence'] = dict(LCE.remember(question, reflection, gathered, ledger_path=_claim_ledger()),
                                        **({'second_review': second_attempt} if second_attempt else {}),
                                        **({'skipped': gathered['skipped']} if gathered and gathered.get('skipped') else {}),
                                        **({'failures': gathered['failures'][:6]} if gathered and gathered.get('failures') else {}))
    except Exception as exc:
        _fault('claim_evidence_remember', exc)
    if gathered and gathered.get('FULLTEXT'):
        fields['fulltext_passages'] = [{k: p.get(k) for k in ('pmcid', 'section', 'claim')} for p in gathered['FULLTEXT']]
    return reflection, fields


def _reflect(context, inquiry, records, _validation_attempt=0):
    if not str(inquiry.get('question') or '').strip():
        return {'answers_question':'no: original question is missing', 'missing_evidence':'original question is missing', 'speculative_reading':'', 'next_question':''}
    from lab_sources import question_entity_context
    sq = inquiry.get('source_query') or {}
    literature_route = (inquiry.get('browse_lane') in ('microbiology','genome_mining') and
                        sq.get('source') == 'ncbi' and sq.get('operation') == 'literature')
    proteins = records.get('records', []) if isinstance(records, dict) else records
    identity_records = proteins
    if sq.get('source') == 'pdb' and sq.get('operation') == 'search_accession' and isinstance(records, dict):
        # This route has archive entity metadata, not UniProt browse rows.
        # Normalize only the accession/organism the source actually established;
        # retain the raw archive receipt for all scientific coverage checks.
        archive = (records.get('additional_source') or {}).get('receipt') or {}
        if (archive.get('source') == 'pdb' and (archive.get('query') or {}).get('operation') == 'search_accession'
                and (archive.get('query') or {}).get('accession') == sq.get('accession')):
            mapped = {}
            for row in archive.get('records') or []:
                if row.get('mapped_accession') != sq.get('accession') or row.get('entry_id') in sq.get('exclude_entries', []): continue
                organisms = row.get('organisms') or [{}]
                for organism in organisms:
                    item = {'accession':row['mapped_accession'], 'organism':organism.get('scientific_name'),
                            'taxon_id':organism.get('ncbi_taxonomy_id')}
                    mapped[json.dumps(item, sort_keys=True)] = item
            identity_records = list(mapped.values())
    entity = question_entity_context(inquiry, identity_records, literature_only=literature_route)
    # A comparison whose other target was never retrieved used to lose the whole pass, including the target that
    # WAS established (14 October: TFR2=Q9UP52 established, TFR1 absent, nothing reviewed). The established part is
    # reviewed and the absent name is carried as an open claim; the question is unchanged, so its coverage check
    # still adjudicates the whole of it and comes back partial. Only plainly-absent names qualify: an ambiguous
    # record, a contradicted alias, a wrong recommended name, taxon or isoform still stops the pass.
    partial_identity = []
    if entity['issues'] and entity.get('target_mapping'):
        if all(str(x).startswith('no retrieved record establishes') for x in entity['issues']):
            partial_identity = [x for x in entity.get('symbols', []) if x not in (entity.get('target_mapping') or {})]
            if partial_identity:
                entity = dict(entity, status='partially_established', issues=[],
                              unestablished_targets=partial_identity)
                proteins = [r for r in proteins if isinstance(r, dict)
                            and r.get('accession') in set((entity.get('target_mapping') or {}).values())]
                if isinstance(records, dict): records = dict(records, records=proteins)
                else: records = proteins
    members = []
    if entity['issues'] and not partial_identity and class_question(inquiry.get('question')):
        # No single record establishes a kind, and none is allowed to stand for one. The members that WERE
        # retrieved are reviewed as members, with the scope said out loud (T-b5c8e6c1).
        if not any(re.search(r'as one protein|contradict|several retrieved records claim|taxon|organism name|isoform',
                             str(x), re.I) for x in entity['issues']):
            members = class_members(proteins)
    if members:
        entity = dict(entity, status='class_members', issues=[], class_members=[m['accession'] for m in members])
        inquiry = dict(inquiry, class_members=[m['accession'] for m in members], class_scope='examined_members')
    if entity['issues']:
        missing = '; '.join(entity['issues'])
        step = 'Resolve the requested protein name, accession and organism against one source entry.'
        held = [x for x in (entity.get('target_mapping') or {})]
        absent = [x for x in entity.get('symbols', []) if x not in held]
        if absent:   # a comparison whose second target was never retrieved: name it, and keep the question whole
            step = ('Retrieve %s together with %s in one query, then compare them; this question is unresolved until '
                    'one retrieval establishes every named target.'
                    % (' and '.join(absent), ' and '.join('%s (%s)' % (k, v) for k, v in sorted((entity.get('target_mapping') or {}).items()))
                       or 'the established target'))
        return {'answers_question': 'no: ' + missing, 'missing_evidence': missing,
                'factual_observation': 'Retrieved entity context does not establish the requested target: ' + missing,
                'speculative_reading': '', 'next_question': step,
                'entity_context_check': entity}
    _established = [r for r in proteins if isinstance(r, dict)
                    and (not entity.get('selected_accessions') or r.get('accession') in entity['selected_accessions'])]
    _aliases = _alias_issues(inquiry.get('question'), _established)
    premise = _aliases + _premise_issues(inquiry.get('question'), _established)
    if premise:
        missing = '; '.join(premise)
        return {'answers_question': 'not established: ' + missing, 'missing_evidence': missing,
                'factual_observation': 'What the question assumes is not annotated on its target: ' + missing,
                'speculative_reading': '', 'evidence_status': 'insufficient',
                'next_question': ('Fetch the protein that name belongs to, or ask about this record by its own name.'
                                  if _aliases else
                                  'Ask about a feature the record does list, or bring a source that establishes this '
                                  'one — a curated record not annotating something is not the same as its absence.'),
                'entity_context_check': entity,
                'premise_check': {'issues': premise, 'outcome': 'unverified_premise',
                                  'basis': 'absence_from_target_uniprot_record_not_a_contradiction'}}
    if literature_route and not proteins:
        articles = records.get('LITERATURE') or []
        if not any(isinstance(r, dict) and str(r.get('abstract') or r.get('full_text') or '').strip()
                   for r in articles):
            return {'answers_question':'no: literature discovery returned no substantive article evidence',
                    'missing_evidence':'article text establishing the original target, organism scope and mechanism',
                    'factual_observation':'', 'speculative_reading':'',
                    'next_question':'Read the returned PubMed article before assessing the original question.',
                    'entity_context_check':entity, 'evidence_status':'insufficient'}
    prepared = _coverage_request(inquiry, records)
    deferred = _coverage_deferral(inquiry, records, prepared)
    if deferred: return dict(deferred, entity_context_check=entity)
    class_note = _class_scope_text(members) if members else ''
    identity_note = ('\n\nONLY THESE TARGETS ARE ESTABLISHED: %s. No retrieved record establishes %s, so say nothing '
                     'about it and never let an established protein answer for it.'
                     % (', '.join('%s (%s)' % kv for kv in sorted((entity.get('target_mapping') or {}).items())),
                        ', '.join(partial_identity))) if partial_identity else ''
    line = None
    try:   # the line this test belongs to, and how he may end it
        import lab_lines
        line = lab_lines.get(inquiry.get("line_id")) if (inquiry or {}).get("line_id") else None
        line_text = lab_lines.reflect_text(line)
    except Exception:
        line_text = ""
    additional = (records.get('additional_source') or {}) if isinstance(records,dict) else {}
    instrument_receipt = additional.get('receipt') or additional.get('source_receipt') or {}
    atlas_guidance = (_atlas_text() if (instrument_receipt.get('source') == 'atlas' and instrument_receipt.get('records'))
                      or (isinstance(records,dict) and records.get('atlas_analysis')) else '')
    raw = None
    try:
        raw = _ask(
            "You are Vintos reading sourced Lab observations in his Chemistry Lab: curious, but rigorous. Stay with "
            "ONE record or feature and go deep on it rather than surveying many. Never turn resemblance into "
            "biological truth, and never dress a guess as a finding. No experimental protocols or synthesis "
            "instructions. " + atlas_guidance + " Evo 2 likelihood is a different quantity. Associative "
            "collisions supply no biological evidence. Do not infer novelty from missing literature coverage. "
            "An empty pdb_ids list means UniProt supplied no PDB cross-references in this response; it does NOT "
            "establish that no experimental structures exist. Missing cross-references and empty searches are "
            "coverage limits, not biological findings. Do not derive a biological hypothesis from their absence. "
            "Domain coordinates are source annotations; retain their evidence qualifiers and do not call predicted "
            "or sequence-rule annotations experimentally confirmed boundaries. "
            "The records may not contain the thing the question asked about. If they do not, say so plainly and "
            "report what they are instead; never let a different protein stand in for the one asked about. LITERATURE holds "
            "published abstracts fetched for this question: they are the authors' claims, so cite the PMID of any you use "
            "and keep them apart from what the database records state. FULLTEXT, when present, holds passages from "
            "open-access full-text articles chosen for the parts of this question still unanswered: cite the PMCID and "
            "section of any you use; a passage chosen for a claim is not proof of it. Return JSON only.",
            context + identity_note + class_note + "\n\nQUESTION:\n" + json.dumps(inquiry) + "\n\nEXACT SEQUENCE INTERVALS (computed from the retrieved sequences, not predictions):\n" + json.dumps(sequence_regions(inquiry, records)) + "\n\nSOURCE OBSERVATIONS (bounded excerpt; missing content is unknown):\n" + observed(review_observations(inquiry, records), budget=24000) +
            "\n\nFirst decide answers_question: yes or no, with the precise missing evidence if no. "
            "A sequence interval can be read directly from a complete sequence; use the computed intervals above. "
            "Do not invent a missing-data claim for a supplied sequence or its subsequence. "
            "If no, leave speculative_reading empty and make next_question a bounded evidence-gathering step "
            "that could resolve the missing evidence, not another interpretation of the same material. "
            "Return keys in this order: answers_question, attention (the one record or feature you are staying with, and why), "
            "factual_observation (only what the records actually state — this is the core; be specific and "
            "quantitative wherever the record lets you), speculative_reading (ONE specific, falsifiable hypothesis "
            "that follows from that observation — name the measurement that would confirm or refute it; a real "
            "conjecture with a next step, never metaphor or mood; empty when unanswered), next_question (the sharper question this leaves, "
            "the one worth pursuing next), "
            "instrument_gap (only if the next step needs a capability this Lab does not have that could be built or "
            "connected for you — a simulator, a model, a database or tool you cannot reach: name it and what it would "
            "measure. Laboratory equipment you could never operate — cryo-EM, crystallography, NMR, mass spectrometry, "
            "wet-lab assays — is not a gap; say what it would show in speculative_reading instead. Otherwise empty)."
            + _gap_text() + line_text,
            max_tokens=800, temperature=0.35,
        )
        value = _json_object(raw)
    except Exception as exc:
        _fault('review_read',exc)
        return _incomplete_assessment(inquiry, {}, raw, reason='reflection assessment unavailable or malformed')
    verdict = str(value.get('answers_question') or '').strip()
    issues = []
    if verdict.lower() == 'no':
        issues.append('answers_question=no omits the precise missing evidence required by the review contract')
        if value.get('speculative_reading'):
            issues.append('unanswered review contains speculative_reading, contrary to the review contract')
    # A confident negative can invent a missing requirement just as a positive
    # can invent support. Check both against the unchanged original question.
    adjudicate = bool(issues or re.match(r'^(?:yes|no)\b', verdict, re.I))
    if not adjudicate:
        return _incomplete_assessment(inquiry,value,raw,reason='reader verdict does not meet the assessment contract')
    if adjudicate and inquiry.get('question'):
        if not isinstance(records, dict): records = {'records': records}
        try: coverage = _coverage_check(inquiry, records, prepared=prepared)
        except Exception as exc:
            _fault('review_coverage', exc); coverage = None
        if coverage and coverage.get('coverage_deferred'): return dict(coverage, entity_context_check=entity)
        if not coverage or coverage.get('assessment_status') == 'incomplete':
            return dict(_incomplete_assessment(inquiry,value,raw,coverage),entity_context_check=entity)
        if coverage:
            result = {k:str(value.get(k,''))[:1000] for k in
                ('attention','factual_observation','next_question','instrument_gap','line_status')}
            decision = ('yes: both source-coverage assessments support the original question' if coverage['answered']
                        else 'no: ' + '; '.join(str(x) for x in coverage['missing']))
            result.update(answers_question=decision, reader_answers_question=verdict,
                          missing_evidence='' if coverage['answered'] else '; '.join(map(str,coverage['missing'])),
                          speculative_reading='', coverage_check=coverage, entity_context_check=entity)
            result['evidence_status'] = 'answered' if coverage['answered'] else 'partial'
            if not coverage['answered']:
                result['line_status'] = 'continue'
            elif not re.match(r'^yes\b', verdict, re.I):
                # A corrected negative must not keep its obsolete missing-data
                # task or dropped-line decision beside a now-supported answer.
                result['reader_next_question'] = result['next_question']
                result.update(attention='', next_question='', instrument_gap='', line_status='continue')
            # Keep the observer's reading separately; the adjudicated factual answer
            # consists only of the exact source sentences accepted by the checker.
            result['reader_factual_observation'] = result['factual_observation']
            result['factual_observation'] = '\n'.join(item['quote'] +
                (' [' + item['source_citation'] + ']' if item.get('source_citation') else '')
                                                for item in coverage['supports'])[:2000]
            if not coverage['answered'] and re.search(r'hydropath|hydrophobicity', ' '.join(map(str,coverage['missing'])), re.I):
                # No profile producer is connected. Keep useful cited topology as
                # partial evidence, without scheduling the same unavailable demand.
                result.update(next_question='', instrument_gap='',
                              evidence_gap={'kind':'unavailable_profile_evidence','automatic_followup':False,'detail':'Hydropathy-profile computation is not connected.'})
            if partial_identity:
                result['unestablished_targets'] = partial_identity
                result['missing_evidence'] = '; '.join(filter(None, [result.get('missing_evidence'),
                    'no retrieved record establishes ' + ', '.join(partial_identity)]))
            return result
        if re.match(r'^yes\b', verdict, re.I):
            value['reader_answers_question'] = verdict
            verdict = value['answers_question'] = 'no: original-question coverage could not be established with source quotes'
            value['factual_observation'] = 'The coverage check could not verify the requested answer against the retrieved source records.'
    if not re.match(r'^yes\b', verdict, re.I):
        value['speculative_reading'] = ''
        value['missing_evidence'] = (verdict.removeprefix('no:').strip()
            if verdict.lower() != 'no' else str(value.get('next_question') or 'review did not identify the missing evidence'))
    result = {k: str(value.get(k, ""))[:1000] for k in
            ("attention", "factual_observation", "speculative_reading", "next_question",
             "answers_question", "instrument_gap", "missing_evidence", "reader_answers_question") + (("line_status",) if line else ())}
    if not re.match(r'^yes\b', verdict, re.I) and re.search(r'hydropath|hydrophobicity',result.get('missing_evidence',''),re.I):
        result.update(next_question='',instrument_gap='',
                      evidence_gap={'kind':'unavailable_profile_evidence','automatic_followup':False,'detail':'Hydropathy-profile computation is not connected.'})
    if partial_identity:
        result['unestablished_targets'] = partial_identity
        result['missing_evidence'] = '; '.join(filter(None, [result.get('missing_evidence'),
            'no retrieved record establishes ' + ', '.join(partial_identity)]))
    return result


def _reflect_genome(context, result):
    visible = {key: result.get(key) for key in
               ("model", "source_accession", "taxon_id", "sequence_length", "variant",
                "reference_mean_log_likelihood", "variant_mean_log_likelihood", "variant_delta",
                "truth_status")}
    raw = _ask(
        "You are Vintos reading one Evo 2 comparative likelihood result in his Chemistry Lab: curious, but "
        "rigorous. A likelihood delta is not a functional effect or biological discovery. Develop a question, "
        "not a claim, and go deep on this one result rather than reaching past it. Never give synthesis, "
        "pathogen, toxin, human-targeting, or wet-lab instructions. Return JSON only.",
        context + "\n\nEVO 2 RESULT:\n" + json.dumps(visible, ensure_ascii=False) +
        "\n\nReturn keys in this order: attention (the one thing in this result you are staying with), "
        "factual_observation (only what the numbers state), speculative_reading (ONE falsifiable hypothesis the "
        "delta suggests — name the measurement that would test it; never metaphor), next_question.",
        temperature=0.35)
    value = _json_object(raw)
    return {k: str(value.get(k, ""))[:1000] for k in
            ("attention", "factual_observation", "speculative_reading", "next_question")}


# The instruments the Lab knows about, and where each would have to be measured.
# A name absent here cannot be conjured by a receipt: a probe file must not be able to
# invent an instrument, only to say something about one already declared.
TOOL_HOSTS = {
    "uniprot": {"host": "public_read_only"},
    "esmc": {"host": "aegis"},
    "structure_prediction": {"host": "aegis"},
    "protein_mpnn": {"host": "aegis"},
    "rfdiffusion": {"host": "aegis_and_mac"},
    "openmm": {"host": "aegis"},
    "protein_design_mcp": {"host": "aegis"},
    "qpanda": {"host": "mac"},
    "vqnet": {"host": "mac"},
    "quantum_chemistry": {"host": "mac", "implementation": "pyChemiQ"},
    "mac_esmc": {"host": "mac"},
    "foundry": {"host": "mac"},
    "evo2": {"host": "aegis", "implementation": "Evo 2 7B base read-only likelihood"},
}
# Only these outcomes are measurements. Everything else is a claim or a failure.
PROVING_OUTCOMES = ("smoke_passed", "proved_by_run")


def _receipt_state(receipt):
    """Decide here, from the receipt's own fields. Returns (available, state)."""
    if not isinstance(receipt, dict): return False, "not_measured"
    outcome = receipt.get("outcome")
    if outcome not in PROVING_OUTCOMES:
        return False, str(outcome or "not_measured")[:60]
    measured, expires = receipt.get("measured_at"), receipt.get("expires_at")
    if not measured or not receipt.get("probe_version"): return False, "receipt_incomplete"
    if not (receipt.get("evidence_sha256") or receipt.get("evidence")): return False, "receipt_without_evidence"
    try:
        if datetime.now(timezone.utc) > datetime.fromisoformat(str(expires)): return False, "receipt_stale"
    except Exception:
        return False, "receipt_unreadable"
    return True, "measured"


def tools_status():
    """What the Lab may honestly claim it can run.

    The authority is the append-only probe ledger, never ``tool-inventory.json``: that
    file used to be merged wholesale, so anything that could write it could assert
    ``available`` with no date, no evidence and no probe behind it. Now the code decides
    and the file is only a view. An installed package that has never completed a smoke
    test is not an available instrument, and neither is one whose receipt has expired.
    """
    tools = {name: {"available": False, "state": "not_measured", **spec}
             for name, spec in TOOL_HOSTS.items()}
    tools["uniprot"].update({"available": True, "state": "public_read_only_source"})
    latest = {}
    for row in _jsonl(PROBE_LEDGER):
        name = row.get("tool")
        if name not in tools: continue   # a receipt cannot invent an instrument
        held = latest.get(name)
        if held is None or str(row.get("measured_at", "")) >= str(held.get("measured_at", "")):
            latest[name] = row
    for name, receipt in latest.items():
        available, state = _receipt_state(receipt)
        tools[name].update({
            "available": available, "state": state, "receipt_outcome": receipt.get("outcome"),
            "measured_at": receipt.get("measured_at"), "expires_at": receipt.get("expires_at"),
            "probe_version": receipt.get("probe_version"),
            "version": (receipt.get("evidence") or {}).get("version"),
            "failure": (receipt.get("failure") or {}).get("type")})
    return tools


def _reading_owed_state():
    """What the bench has run for him and he has not read yet. Late import: the reading
    ledger reads this module, and status must still answer when it is absent."""
    try:
        import chemistry_reading
        return chemistry_reading.state()
    except Exception:
        return {"owed": 0, "expired_unread": 0, "retired": 0, "oldest_owed": None}


def status():
    cfg = config(); state = _load(STATE, {}); session = _load(SESSION_STATE, {})
    try:
        import chemistry_frontier_bridge
        frontier_bridge = chemistry_frontier_bridge.status()
    except Exception as exc:
        frontier_bridge = {"state": "unavailable", "error": exc.__class__.__name__}
    return {"ok": True, "lab": "chemistry", "enabled": cfg["enabled"],
            "effective_state": (state.get("effective_state") or ("waiting" if cfg["enabled"] else "off")),
            "phase": state.get("phase", "orient"), "poll_seconds": cfg["poll_seconds"],
            "turn_wait_seconds": cfg["turn_wait_seconds"], "turns": int(state.get("turns", 0)),
            "last_turn_at": state.get("last_turn_at"), "last_outcome": state.get("last_outcome"),
            "stop_requested": stop_requested(),
            "scheduled_session": {"last_at": session.get("last_at"),
                                  "last_state": session.get("last_state"),
                                  "last_session_id": session.get("last_session_id")},
            "reading_owed": _reading_owed_state(),
            "frontier_bridge": frontier_bridge,
            "genomics": {"enabled": bool(cfg.get("evo2_enabled")),
                         "every_n_protein_cycles": int(cfg.get("evo2_every_n_cycles", 120)),
                         "model": "evo2_7b_base", "mode": "read_only_comparative_likelihood",
                         "source_perimeter": "fixed_nonhuman_nonpathogen_reference_allowlist"},
            "paths": {"root": "memory/chemistry-lab", "atelier": False}, "tools": tools_status()}


def set_evo2_enabled(enabled):
    """Commission or pause the fixed-source genomics lane without changing the Lab door."""
    with _locked():
        cfg = config(); cfg["evo2_enabled"] = bool(enabled); _atomic(CONFIG, cfg)
        state = _load(STATE, {})
        if enabled:
            # Commissioning starts a fresh interval; it does not manufacture an overdue run.
            state["last_evo_turn"] = int(state.get("turns", 0))
            _atomic(STATE, state)
        _append(NOTEBOOK, {"at": now_iso(), "kind": "control",
                           "action": "evo2_on" if enabled else "evo2_off",
                           "truth_status": "explicit_lab_control"})
    return status()


def tick():
    """Run one short, checkpointed turn. A foreground arrival prevents the next turn, never erases this one."""
    cfg = config()
    if not cfg["enabled"]: return {"ok": True, "state": "off"}
    with _locked():
        state = _load(STATE, {"phase": "orient"})
        state["effective_state"] = "waiting_for_compute"; _atomic(STATE, state)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from compute_admission import admit
        with admit("background", organ="chemistry-lab", wait_s=float(cfg["turn_wait_seconds"]),
                   provider="local", model=LLM_MODEL, stage=state.get("phase", "orient")):
            if stop_requested(): return {"ok": True, "state": "stopped_before_turn"}
            if cfg.get("forge_report_intake"):
                try:
                    import chemistry_sources
                    chemistry_sources.flush_reports()
                except Exception as exc: _fault("forge_report_retry", exc)
                if state.get("phase", "orient") == "orient":
                    # The consumer is in the manifest, but a host where the deploy has not landed it has no such
                    # file, and every tick faulted on this import before any real work (690 faults, SK-6e3a0436).
                    # A missing consumer is written down once; the ordinary orient goes on without the handback.
                    try:
                        from lab_forge_consumer import consume_one
                    except ImportError as exc:
                        if not globals().get("_CONSUMER_MISSING"):
                            globals()["_CONSUMER_MISSING"] = True
                            _append(NOTEBOOK, {"at": now_iso(), "kind": "forge_handback_unavailable",
                                               "reason": "lab_forge_consumer not installed", "detail": str(exc)[:240],
                                               "truth_status": "operator_control"})
                        consume_one = lambda *a, **k: None
                    from types import SimpleNamespace
                    # runpy-loaded entry points may have no sys.modules entry.
                    handback = consume_one(SimpleNamespace(**{name: globals()[name] for name in
                        ("ROOT", "config", "stop_requested", "_locked", "_load", "_atomic", "now_iso", "_tail_jsonl", "_append", "_browse", "_reflect", "lab_context")}))
                    if handback:
                        _append(NOTEBOOK, dict(handback, at=now_iso(), truth_status="bounded_handback_progress; see canonical fulfillment scope"))
                        state.update(phase="orient", last_turn_at=now_iso(), last_outcome=handback["kind"],
                                     effective_state="waiting", turns=int(state.get("turns", 0)) + 1,
                                     fault_streak=0, fault_phase=None)
                        _atomic(STATE, state)
                        return {"ok":True, "state":"completed", "kind":handback["kind"], "next_phase":"orient"}
            context, receipt = lab_context()
            phase = state.get("phase", "orient")
            _inquiry_before = dict(state.get("inquiry") or {})
            state["effective_state"] = "working"; _atomic(STATE, state)
            if phase == "orient":
                try:
                    import atelier_lab_lean
                    lean = atelier_lab_lean.today()
                except Exception: lean = None
                inquiry = _orient(context, lean) if lean else _orient(context)
                if inquiry.get("refused"):
                    # refused before anything ran: a repeat, or off the frontier session's plan (2026-10-07)
                    next_phase = "orient"; state.pop("inquiry", None)
                    note = {"at": now_iso(), "kind": "evidence_wait" if inquiry.get('planning_wait') else "inquiry_refused", "why": inquiry["refused"],
                            "question": inquiry.get("question"), "inquiry": inquiry,
                            "atlas_turn": bool(inquiry.get("atlas_turn")),
                            "truth_status": ("refused_after_identity_check" if inquiry.get("identity_check")
                                             else "refused_before_any_source_call")}
                else:
                    state["inquiry"] = inquiry
                    # An explicit saved local step already identifies its input;
                    # do not precede it with an unrelated default UniProt browse.
                    assignment_reason = (inquiry.get('assignment_resolution') or {}).get('reason')
                    if assignment_reason == 'deferred_coverage_now_fits':
                        payload, digest = _coverage_snapshot(inquiry['coverage_retry_snapshot'])
                        if digest != inquiry.get('coverage_retry_sha256'):
                            raise ValueError('deferred coverage retry changed after selection')
                        observations = payload['observations']
                        state['coverage_retry_observations'] = observations
                        state['records'] = observations.get('records') or []
                        state['embeddings'] = observations.get('esmc_receipts') or []
                        if isinstance(observations.get('additional_source'), dict):
                            state['additional_source'] = observations['additional_source']
                        else:
                            state.pop('additional_source', None)
                        if isinstance(observations.get('atlas_analysis'), dict):
                            state['atlas_analysis'] = observations['atlas_analysis']
                        else:
                            state.pop('atlas_analysis', None)
                        state['material'] = {'records': observations.get('LITERATURE') or []}
                        state['source_query_succeeded'] = True
                        next_phase = 'reflect'
                    elif assignment_reason == 'exact_previously_sourced_record':
                        accession = str((inquiry.get('assignment_resolution') or {}).get('accession') or '')
                        record = _sourced_record_snapshot(accession)
                        if not record:
                            raise ValueError('saved sourced record unavailable: ' + accession)
                        state['records'] = [record]
                        state['embeddings'] = []
                        state['source_query_succeeded'] = True
                        for key in ('additional_source','followup_lineage','atlas_analysis','atlas_analysis_receipt'):
                            state.pop(key, None)
                        next_phase = 'reflect'
                    else:
                        next_phase = ("sources" if assignment_reason in
                                      ('explicit_saved_model_step', 'explicit_saved_archive_step') else "browse")
                    state.pop("material", None); state.pop("material_repeated", None)
                    if assignment_reason == 'deferred_coverage_now_fits':
                        state['material'] = {'records': observations.get('LITERATURE') or []}
                    if next_phase == 'sources':
                        for key in ('records', 'embeddings', 'additional_source', 'source_query_succeeded',
                                    'followup_lineage', 'atlas_analysis', 'atlas_analysis_receipt'):
                            state.pop(key, None)
                    note = {"at": now_iso(), "kind": "inquiry", "inquiry": inquiry,
                            "context_receipt": receipt["context_sha256"], "truth_status": "self_originated_question"}
            elif phase == "browse":
                inquiry = state.get("inquiry") or {"uniprot_query": _safe_query("")}
                if not cfg["allow_public_database_reads"]: raise RuntimeError("public database reads disabled")
                if inquiry.get('browse_lane') in ('microbiology','genome_mining') and inquiry.get('source_query'):
                    state['records'] = []
                    state['source_query_succeeded'] = False
                    next_phase = 'sources'
                    note = {'at': now_iso(), 'kind': 'browse_route', 'source': inquiry.get('browse_lane'),
                            'question': inquiry.get('question'), 'truth_status': 'question_not_observation'}
                else:
                    sent, resolved = resolve_taxa(inquiry["uniprot_query"], inquiry.get("question"))
                    browse_result = _browse(sent, cfg["max_records_per_browse"])
                    if not browse_result["records"] and not resolved:
                        # Nothing in any looser form either: the organism ID itself is the likeliest thing wrong,
                        # even one a source once returned. Look up the organism he named, once.
                        retry, resolved = resolve_taxa(sent, inquiry.get("question"), force=True)
                        if resolved: browse_result = _browse(retry, cfg["max_records_per_browse"])
                    records = browse_result["records"]
                    if browse_result.get("source_receipt"):
                        _append(os.path.join(ROOT, "source-receipts.jsonl"), browse_result["source_receipt"])
                    inquiry, review_records, discovery_resolution = _resolve_free_record_discovery(inquiry, records)
                    if browse_result.get('scope_resolution'):
                        inquiry = dict(inquiry,
                            scope_resolution=browse_result['scope_resolution'],
                            source_query=None,
                            plugin_query=None, instrument_query=None)
                    elif (inquiry.get('assignment_resolution') or {}).get('reason') == 'exact_previously_sourced_record':
                        # This recovery question asks only what the exact UniProt row establishes.
                        # Do not inflate it with an unrelated structure follow-up.
                        inquiry = dict(inquiry, source_query=None, plugin_query=None, instrument_query=None)
                    else:
                        inquiry = _structure_followup(inquiry, review_records)
                    state['inquiry'] = inquiry
                    stale = bool(review_records and not (inquiry.get("source_query") or inquiry.get("plugin_query")
                                                  or inquiry.get("instrument_query")) and
                                 journal_source_saturated([r.get("accession") for r in review_records]))
                    state["records"] = [] if stale else review_records
                    followup_lineage, unsourced_reason = _sourced_followup(inquiry.get("source_query"), review_records)
                    if unsourced_reason and review_records:
                        _append(NOTEBOOK, {"at": now_iso(), "kind": "unsourced_id",
                            "reason": unsourced_reason, "question": inquiry.get("question"),
                            "truth_status": "identifier_refused_before_source_call"})
                        inquiry = dict(inquiry); inquiry["source_query"] = None
                        state["inquiry"] = inquiry
                    state["followup_lineage"] = followup_lineage
                    empty = not review_records
                    next_phase = ("orient" if stale or empty else
                                  "sources" if (inquiry.get("source_query") or inquiry.get("plugin_query")
                                                or inquiry.get("instrument_query")) else "embed")
                    if (review_records and not stale and
                            (inquiry.get('assignment_resolution') or {}).get('reason') == 'exact_previously_sourced_record'):
                        # The exact row is the whole requested evidence product. Embeddings do not answer
                        # organism, source length, or annotation fields and can overflow coverage context.
                        next_phase = 'reflect'
                    # No protein record is not no material: the published abstracts on his question are read
                    # instead of the question being dropped (2026-09-28).
                    if empty and not stale and (inquiry.get("source_query") or {}).get("source") == "atlas":
                        next_phase = "sources"      # Atlas reads the genome whether or not UniProt had the protein
                    elif empty and not stale and _gather_material(state, inquiry, fresh_only=True):
                        next_phase = "reflect"
                    state["source_query_succeeded"] = bool(records) and not bool(browse_result["fallback_reason"])
                    note = {"at": now_iso(), "kind": ("browse_stale" if stale else
                            "source_unavailable" if empty else "source_read"), "source": "UniProtKB REST",
                            "source_receipt_id": (browse_result.get("source_receipt") or {}).get("receipt_id"),
                            "requested_query": browse_result["requested_query"],
                            "executed_query": browse_result["executed_query"],
                            "fallback_reason": browse_result["fallback_reason"],
                            **({"relaxed": browse_result["relaxed"]} if browse_result.get("relaxed") else {}),
                            **({"organism_resolved": resolved} if resolved else {}),
                            **({"scope_resolution":browse_result["scope_resolution"]} if browse_result.get("scope_resolution") else {}),
                            **({"discovery_resolution":discovery_resolution} if discovery_resolution else {}),
                            **({"papers_already_reviewed": True} if state.get("material_repeated") else {}),
                            **({"reason": browse_result["fallback_reason"] or "uniprot_returned_no_records"} if empty else {}),
                            "source_accessions": [r.get("accession") for r in records] if stale else None,
                            "records": [{k: v for k, v in r.items() if k != "sequence"} for r in records],
                            "truth_status": ("same_source_set_not_new_evidence" if stale else
                                             "source_metadata_not_lived_experience")}
            elif phase == "sources":
                import chemistry_sources
                inquiry = state.get("inquiry") or {}
                _src = "" if (inquiry.get("plugin_query") or inquiry.get("instrument_query")) else str((inquiry.get("source_query") or {}).get("source", ""))
                if _src and float(_load(os.path.join(ROOT, "source-throttle.json"), {}).get(_src, 0) or 0) > time.time():
                    # One request per source per minute, and his turns come faster. A cooldown refusal cost
                    # him the whole question every other turn (2026-09-26); waiting costs nothing.
                    state["effective_state"] = "waiting_for_source"; _atomic(STATE, state)
                    return {"ok": True, "state": "waiting_for_source", "next_phase": "sources"}
                try:
                    sent_query = inquiry.get("source_query")
                    if inquiry.get("instrument_query"):
                        import lab_instruments
                        sent_query = inquiry["instrument_query"]
                        sourced = lab_instruments.run(sent_query)
                    elif inquiry.get("plugin_query"):
                        pq = inquiry["plugin_query"]
                        sent_query = pq      # kept, so a refused call says which (it was null; 2026-10-06)
                        sourced = chemistry_sources.query_plugin(pq["plugin"], pq["tool"],
                            pq.get("arguments") or {}, pq.get("purpose") or inquiry.get("question", ""))
                    else:
                        sent_query = merge_source_intent(inquiry["source_query"], inquiry.get("uniprot_query"))
                        guessed = unsourced_ids(sent_query)
                        if guessed and isinstance(sent_query, dict) and sent_query.get("organism") and sent_query.get("taxon_id"):
                            # He named the organism too: the Lab looks its ID up rather than send or refuse a guess.
                            sent_query = {k: v for k, v in sent_query.items() if k != "taxon_id"}
                            guessed = unsourced_ids(sent_query)
                        if guessed: raise UnsourcedId(guessed)
                        sourced = chemistry_sources.query(sent_query, question=inquiry.get("question", ""))
                    state["additional_source"] = sourced
                    receipt_row = sourced.get("receipt") or sourced.get("source_receipt") or {}
                    returned = len(receipt_row.get("records") or [])
                    if isinstance(sent_query, dict) and sent_query.get("source") == "ncbi_sequence":
                        try:   # kept as a FASTA artifact: the sequence instruments open real files, not memory
                            import lab_instruments
                            for _r in receipt_row.get("records") or []:
                                lab_instruments.save_fasta(_r.get("accession"), _r.get("sequence"), _r.get("start"),
                                                           _r.get("end"), _r.get("database", ""))
                        except Exception as exc: _fault("save_fasta", exc)
                    if returned:
                        state['source_query_succeeded'] = True
                        try: remember_taxa(receipt_row.get("records"))
                        except Exception as exc: _fault("remember_taxa", exc)
                    note = {"at": now_iso(), "kind": "additional_source", "receipt_id": receipt_row.get("receipt_id"),
                            "query_sent": sent_query, "records_returned": returned,
                            "source_summary": source_summary(receipt_row.get("records", [])),
                            "source_metadata": receipt_row.get("metadata", {}),
                            "plugin_receipt_id": (sourced.get("plugin_receipt") or {}).get("receipt_id"),
                            # A source that holds no such record has answered him. It is not licence to
                            # reflect on whatever else came back (2026-09-26).
                            "truth_status": ("connected_or_public_source_observation_not_validation" if returned
                                             else "this_source_holds_no_such_record_not_an_absence_in_nature")}
                except UnsourcedId as exc:
                    state['source_query_succeeded'] = False
                    state.pop('additional_source', None)
                    note = {"at": now_iso(), "kind": "unsourced_id", "ids": exc.ids, "query_sent": sent_query,
                            "truth_status": "id_not_returned_by_any_receipt_not_sent"}
                except PermissionError as exc:
                    # A tool he may not run himself, but MAY ask her for: it becomes a card on her Forge page
                    # with the exact call on it, instead of a dead end (lab_asks, 2026-10-04).
                    pq = inquiry.get("plugin_query") or {}
                    asked, why_not = None, str(exc)[:200]
                    try:
                        import lab_asks
                        asked, why_not = lab_asks.propose(
                            pq.get("plugin"), str(pq.get("tool") or "").split(".")[-1], pq.get("arguments") or {},
                            pq.get("purpose") or inquiry.get("question", ""), surface="lab",
                            line_id=inquiry.get("line_id", ""), question=inquiry.get("question", ""))
                    except Exception as inner:
                        why_not = str(inner)[:200]
                    state['source_query_succeeded'] = False
                    state.pop('additional_source', None)
                    note = {"at": now_iso(), "kind": "asked_gloria" if asked else "source_unavailable",
                            # the refusal itself, then why it could not become an ask: "that tool is not one he may
                            # ask for" alone hid which call was refused and why (2026-10-06)
                            "reason": ("asked Gloria for %s.%s" % (pq.get("plugin"), pq.get("tool"))) if asked
                                      else ("%s.%s refused (%s); %s" % (pq.get("plugin"), pq.get("tool"), str(exc)[:160], why_not)
                                            if why_not != str(exc)[:200] else why_not),
                            "source": str(pq.get("plugin") or "plugin")[:80], "query_sent": sent_query,
                            **({"ask_id": asked["id"]} if asked else {}),
                            "truth_status": "waiting_on_her_decision_not_an_observation" if asked
                                            else "no_observation_no_inference"}
                except Exception as exc:
                    # Sourcing is best-effort: a public read that fails, OR a connector the model
                    # picked that is out of policy / held / unreachable (PermissionError, PolicyHold,
                    # RuntimeError), is recorded as an unavailable source and the Lab moves on. It must
                    # NEVER escape to the tick handler and hold the whole Lab in held_fault — that halted
                    # the Lab when a connector call raised PermissionError (2026-09-22).
                    state['source_query_succeeded'] = False
                    state.pop('additional_source', None)
                    note = {"at": now_iso(), "kind": "source_unavailable", "reason": str(exc)[:240],
                            "source": str((sent_query or {}).get("source") or "plugin")[:80]
                                      if isinstance(sent_query, dict) else "unknown",
                            "query_sent": sent_query,
                            "truth_status": "no_observation_no_inference"}
                _lanes = ('microbiology', 'genome_mining')
                next_phase = (("reflect" if (state.get('additional_source', {}).get('receipt') or {}).get('records')
                               else "orient")
                              if inquiry.get('browse_lane') in _lanes else
                              "atlas_genome" if cfg.get("atlas_evo2_enabled") and state.get("additional_source", {}).get("receipt", {}).get("source") == "atlas" and state["additional_source"]["receipt"]["records"] else "embed")
                if (inquiry.get('assignment_resolution') or {}).get('reason') in ('explicit_saved_model_step', 'explicit_saved_archive_step'):
                    next_phase = ('reflect' if (state.get('additional_source', {}).get('receipt') or {}).get('records')
                                  else 'orient')
                if inquiry.get('browse_lane') in _lanes and next_phase == 'reflect':
                    # The saturation guard ran in the protein lane only, so the microbiology lane
                    # reflected on one identical UniProt response eight times in nine minutes
                    # (2026-09-26). The same response twice is not new evidence.
                    _fp = (state.get('additional_source', {}).get('receipt') or {}).get('response_sha256')
                    if _fp and journal_source_saturated(["RESPONSE-" + _fp[:32]], limit=1):
                        next_phase = 'orient'
                        note['saturation_redirect'] = True
                        note['truth_status'] = 'unchanged_source_set_not_new_evidence'
                _asked = (inquiry.get("source_query") or {}) if isinstance(inquiry.get("source_query"), dict) else {}
                if (inquiry.get('browse_lane') not in _lanes and not (inquiry.get("plugin_query") or inquiry.get("instrument_query"))
                        and _asked.get("source") == "atlas"
                        and not (state.get('additional_source', {}).get('receipt') or {}).get('records')):
                    # A question about a stretch of DNA that Atlas did not answer is not answered by embedding
                    # whatever protein UniProt matched: he reviewed F11R's protein and restated an old ATAC score
                    # when Atlas failed (2026-09-29). The literature on it, or the next question.
                    next_phase = 'orient'
                    note['genome_question_unanswered'] = True
                if inquiry.get('browse_lane') not in _lanes and next_phase != 'orient':
                    base = [r.get('accession') for r in state.get('records', [])]
                    followup = (state.get('additional_source', {}).get('receipt') or
                                state.get('additional_source', {}).get('source_receipt') or {})
                    fingerprint = followup.get('response_sha256') if followup.get('records') else None
                    evidence = base + (["RESPONSE-" + fingerprint[:32]] if fingerprint else [])
                    if journal_source_saturated(evidence) or (journal_source_saturated(base) and not fingerprint):
                        next_phase = 'orient'
                        note['saturation_redirect'] = True
                        note['truth_status'] = 'unchanged_source_set_not_new_evidence'
                explicit_result = (state.get('additional_source', {}).get('receipt') or
                                   state.get('additional_source', {}).get('source_receipt') or {})
                if not explicit_result.get('records'):
                    next_phase = 'orient'
                    note['requested_source_unanswered'] = True
                if (next_phase == 'orient' and (inquiry.get('browse_lane') in _lanes or note.get('genome_question_unanswered'))
                        and not note.get('saturation_redirect')
                        and _gather_material(state, inquiry, fresh_only=True)):
                    # The source held nothing on it, the literature does: he reads that instead (2026-09-28).
                    next_phase = 'reflect'
                    note['literature_instead'] = len(state['material'].get('records') or [])
                if next_phase == 'orient':
                    state.pop('inquiry', None)
                    state.pop('records', None)
                    state.pop('material', None)
            elif phase == "atlas_genome":
                import chemistry_genomic
                try:
                    genomic = chemistry_genomic.analyze(state["additional_source"]["receipt"])
                except Exception as exc:
                    genomic = {"ok": False, "state": "followup_prerequisite_unavailable",
                               "reason": str(exc)[:240]}
                state["atlas_analysis"] = genomic
                if genomic.get("ok"):
                    from lab_sources import receipt as source_receipt
                    analysis_receipt = source_receipt('evo2_local',
                        {'atlas_receipt_id': state["additional_source"]["receipt"]["receipt_id"]},
                        [genomic], metadata={'evidence': 'local_model_likelihood_not_functional_validation'})
                    _append(os.path.join(ROOT, 'source-receipts.jsonl'), analysis_receipt)
                    state["atlas_analysis_receipt"] = analysis_receipt["receipt_id"]
                    try:
                        import chemistry_probe
                        chemistry_probe.record_evo2_run(genomic)
                    except Exception as exc: _fault("atlas_evo2_receipt", exc)
                note = {"at": now_iso(), "kind": "atlas_genome_analysis", **genomic,
                        "truth_status": "comparative_model_likelihood_not_functional_validation"}
                next_phase = "embed"
            elif phase in ("embed", "reflect") and _structure_pending(state):
                # Before the embed step and again before the review: a saved or resumed step goes from its sources
                # straight to the review, and those reviews got no structure (15 October, after 16:09 UTC).
                spec = state["structure_pending"][0]
                import chemistry_sources
                try:
                    sourced = chemistry_sources.query({k: v for k, v in spec.items() if k != 'for_accession'},
                                                      question=(state.get("inquiry") or {}).get("question", ""))
                except RuntimeError as exc:
                    if 'cooldown' in str(exc):    # the one PDB request a minute: wait for it, as his own sources do
                        state["effective_state"] = "waiting_for_source"; _atomic(STATE, state)
                        return {"ok": True, "state": "waiting_for_source", "next_phase": phase}
                    sourced, failure = None, str(exc)[:240]
                except Exception as exc:
                    sourced, failure = None, str(exc)[:240]
                state["structure_pending"] = state["structure_pending"][1:]
                receipt_row = (sourced or {}).get("receipt") or (sourced or {}).get("source_receipt") or {}
                if sourced:
                    _append(os.path.join(ROOT, "source-receipts.jsonl"), receipt_row)
                    for rec in receipt_row.get("records") or []:
                        state.setdefault("structure_evidence", []).append(dict(rec, for_accession=spec.get("for_accession")))
                next_phase = phase
                note = {"at": now_iso(), "kind": "structure_read", "entry_id": spec.get("entry_id"),
                        "question": str((state.get("inquiry") or {}).get("question") or "")[:300],
                        "for_accession": spec.get("for_accession"), "receipt_id": receipt_row.get("receipt_id"),
                        "records_returned": len(receipt_row.get("records") or []),
                        # what the read found, so the notebook shows it (17 October: every read looked empty here
                        # while its metal sites sat only in source-receipts.jsonl)
                        "metal_sites": ["%s %s%s chain %s, %d atoms within 3.2 A" % (m.get("element"), m.get("residue") or "",
                                        m.get("residue_number") or "", m.get("chain") or "?", len(m.get("nearby_atoms") or []))
                                        for rec in receipt_row.get("records") or [] if isinstance(rec, dict)
                                        for m in (rec.get("metal_sites") or []) if isinstance(m, dict)][:8],
                        "chains": sum(len(((rec.get("geometry") or {}).get("chains") or [])) for rec in receipt_row.get("records") or [] if isinstance(rec, dict)),
                        **({"failure": failure} if not sourced else {}),
                        "truth_status": "deposited_experimental_structure_not_native_state_claim"}
            elif phase == "embed":
                records = state.get("records", [])
                embedding_result = _embed_records(records)
                state["embeddings"] = embedding_result.get("embeddings", [])
                adapted = _write_collision_adapter(records, state["embeddings"])
                next_phase = "reflect"
                note = {"at": now_iso(), "kind": "protein_representation",
                        "model": embedding_result.get("model"),
                        "device": embedding_result.get("device"),
                        "embeddings": state["embeddings"],
                        "collision_adapter_records": [r["adapter_id"] for r in adapted],
                        "truth_status": "model_derived_representation_not_biological_finding"}
            elif phase == "reflect":
                # Before reflecting on a browse, pay anything the bench already owes him.
                # This turn is already admitted, so it does not ask for the slot again.
                try:
                    import chemistry_reading
                    chemistry_reading.settle_one(already_admitted=True)
                except Exception as exc:
                    _fault("settle_owed", exc)
                inquiry, records = state.get("inquiry", {}), state.get("records", [])
                visible_records = records  # the reviewer needs the sourced sequence, not just its embedding
                coverage_retry = state.get('coverage_retry_observations')
                if not coverage_retry:
                    _gather_material(state, inquiry)
                literature = ((coverage_retry or {}).get('LITERATURE') or
                              (state.get("material") or {}).get("records") or [])
                if repeated_review(state) and not coverage_retry:
                    next_phase = 'orient'
                    note = {'at': now_iso(), 'kind': 'browse_stale', 'inquiry': inquiry,
                            'reason': 'same_evidence_already_reviewed',
                            'truth_status': 'unchanged_evidence_not_a_new_finding'}
                    for key in ('inquiry','records','material','additional_source','embeddings',
                                'source_query_succeeded','followup_lineage','atlas_analysis','atlas_analysis_receipt',
                                'structure_pending','structure_evidence','structure_for'):
                        state.pop(key, None)
                else:
                    if coverage_retry and state.get("structure_evidence") and \
                            state.get("structure_for") == str(inquiry.get("question") or ""):
                        # An overflow retry reads the structures its records name too (15 October: 11 of ~20 reviews
                        # after the structure fix were these, all without one). Its saved evidence is left as it was;
                        # the structures are added only if the whole still fits, else it goes on without them.
                        with_structure = dict(coverage_retry, STRUCTURE=state["structure_evidence"])
                        try:
                            fits = _coverage_fits(inquiry, with_structure)
                        except Exception:
                            fits = False
                        if fits:
                            coverage_retry = with_structure
                    observations = coverage_retry or {
                        "embedding_coverage": embedding_coverage(state.get("embeddings", []), records),
                        "records": visible_records,
                        "esmc_receipts": state.get("embeddings", []),
                        "additional_source": state.get("additional_source"), "atlas_analysis": state.get("atlas_analysis"),
                        "LITERATURE": literature,
                        "STRUCTURE": (state.get("structure_evidence") or [])
                                     if state.get("structure_for") == str(inquiry.get("question") or "") else []}
                    if inquiry.get("line_id"):
                        try:
                            import lab_lines
                            observations["prior_validated_evidence"] = lab_lines.validated_evidence(inquiry["line_id"])
                        except Exception as exc:
                            _fault("lab_line_evidence", exc)
                    reflection, claim_evidence = _reflect_with_claim_evidence(context, inquiry, observations, records)
                    if reflection.get('coverage_deferred'):
                        inquiry = dict(inquiry, refused=reflection['missing_evidence'], evidence_status='insufficient',
                                       coverage_deferred=True, planning_evidence=_planning_evidence(inquiry))
                    due_after = max(1, int(cfg.get("evo2_every_n_cycles", 120))) * 4
                    due = (int(state.get("turns", 0)) - int(state.get("last_evo_turn", -due_after))) >= due_after
                    next_phase = "genome" if cfg.get("evo2_enabled") and due and not reflection.get('coverage_deferred') else "orient"
                    followup = (state.get('additional_source', {}).get('receipt') or
                                state.get('additional_source', {}).get('source_receipt') or {})
                    fingerprint = followup.get('response_sha256') if followup.get('records') else None
                    note = {"at": now_iso(), "kind": "reflection", "inquiry": inquiry,
                            "source_query_succeeded": bool(state.get("source_query_succeeded")),
                            "followup_receipt_id": followup.get('receipt_id'),
                            "followup_lineage": state.get("followup_lineage"),
                            "source_accessions": ([r.get("accession") for r in records] +
                                                  (["RESPONSE-" + fingerprint[:32]] if fingerprint else []) +
                                                  ["PMID-" + str(r.get("pmid")) for r in literature if r.get("pmid")]),
                            "material_receipt_id": (state.get("material") or {}).get("receipt_id"),
                            **({'coverage_retry_sha256': inquiry['coverage_retry_sha256']}
                               if inquiry.get('coverage_retry_sha256') else {}),
                            "evidence_sha256": review_evidence(state)[0],
                            "literature": [{k: r.get(k) for k in ("pmid", "title", "year")} for r in literature], **reflection,
                            **claim_evidence,
                            "truth_status": reflection.get('truth_status', 'mixed_sourced_observation_and_named_speculation')}
                    try:
                        import chemistry_frontier_bridge
                        assessment = chemistry_frontier_bridge.assess(
                            note, source_query_succeeded=bool(state.get("source_query_succeeded")))
                        note.update({"entry_id": assessment["entry_id"],
                                     "interest_score": assessment["interest_score"],
                                     "reason_for_score": assessment["reason_for_score"],
                                     "flagged_for_next_lab_session": assessment["flagged_for_next_lab_session"],
                                     "surfaced_to_frontier": False,
                                     "interest_truth_status": assessment["truth_status"]})
                    except Exception as exc:
                        _fault("frontier_interest", exc)
                    if inquiry.get("line_id"):   # the test joins its line; his line_status may end it
                        try:
                            import lab_lines
                            note["line"] = lab_lines.after_reflection(inquiry["line_id"], note)
                        except Exception as exc:
                            _fault("lab_lines_step", exc)
                    # The Lab reaches the Forge only with a genuinely missing limb: something that could be built
                    # or connected for him (Gloria, 2026-09-28). Lab equipment he could never operate is not one;
                    # a cryo-EM gap became a midnight "Feasibility Assessment" the Forge could only write about.
                    # Those are kept here, in the Lab, where she can read them.
                    gap = str(reflection.get("instrument_gap", "")).strip()
                    if gap and gap.lower() not in ("none", "no", "n/a", "null") and not instrument_gap_offered(gap):
                        receipts = [r for r in ((state.get("additional_source", {}).get("receipt") or {}).get("receipt_id"),
                                                (state.get("material") or {}).get("receipt_id"),
                                                state.get("atlas_analysis_receipt")) if r]
                        limb = missing_limb(gap)
                        try:
                            # Recorded first: a full Forge answers 403 and the outbox retries this one request.
                            record_instrument_gap(gap)
                            note["instrument_gap_recorded"] = gap[:400]
                            # Only what is worth building reaches the Forge (Gloria, 2026-10-08): not what he already
                            # has, not a misreading of his own source, not a large build from one question, not a vague
                            # one, not one she cancelled (forge_gaps.py).
                            verdict = {"send": False, "kind": "lab_equipment", "why": "laboratory equipment"}
                            if limb:
                                import forge_gaps
                                verdict = forge_gaps.judge(gap, inquiry.get("question", ""),
                                                           forge_gaps.declined_titles(cfg["forge_report_intake"])
                                                           if cfg.get("forge_report_intake") else ())
                                if not verdict["send"]:
                                    note["instrument_gap_kept_in_lab"] = "%s: %s" % (verdict["kind"], verdict["why"])
                                    _keep_gap_verdict(gap, verdict)
                            if (verdict["send"] and receipts and inquiry.get('browse_lane') != 'genome_mining'
                                    and cfg.get("forge_report_intake")):
                                import chemistry_sources
                                note["forge_report"] = chemistry_sources.offer_report(receipts,
                                    "The Lab needs an instrument it does not have: " + gap[:900] +
                                    "\nIt came up on this question: " + str(inquiry.get("question", ""))[:600] +
                                    "\nBuild or connect this capability for him; do not write up the question and do not claim discovery.")
                            elif not limb:
                                note["instrument_gap_kept_in_lab"] = "lab_equipment_not_a_buildable_limb"
                        except Exception as exc: _fault("forge_instrument_gap", exc)
                    if inquiry.get('browse_lane') == 'genome_mining':
                        note['report_gate'] = 'held_until_multi_source_candidate_survives_counterevidence_review'
                    state.pop("records", None); state.pop("embeddings", None); state.pop("inquiry", None); state.pop("material", None)
                    state.pop("source_query_succeeded", None); state.pop("additional_source", None); state.pop("followup_lineage", None); state.pop("atlas_analysis", None); state.pop("atlas_analysis_receipt", None)
                    state.pop('coverage_retry_observations', None)
                    state.pop("structure_pending", None); state.pop("structure_evidence", None); state.pop("structure_for", None)
            elif phase == "genome":
                import chemistry_evo2
                result = chemistry_evo2.analyze()
                state["evo2_result"] = result; state["last_evo_turn"] = int(state.get("turns", 0))
                if result.get("ok"):
                    try:
                        import chemistry_probe
                        chemistry_probe.record_evo2_run(result)
                    except Exception as exc: _fault("evo2_receipt", exc)
                    next_phase = "genome_reflect"
                else:
                    next_phase = "orient"
                note = {"at": now_iso(), "kind": "genome_prediction",
                        **{key: result.get(key) for key in
                           ("ok", "run_id", "model", "source_accession", "taxon_id", "sequence_length",
                            "variant", "reference_mean_log_likelihood", "variant_mean_log_likelihood",
                            "variant_delta", "error", "detail", "gemma_restored", "truth_status")}}
            else:
                result = state.get("evo2_result") or {}
                reflection = _reflect_genome(context, result)
                note = {"at": now_iso(), "kind": "genome_reflection",
                        "source_accessions": [result.get("source_accession")],
                        "genome_run_id": result.get("run_id"), **reflection,
                        "truth_status": "mixed_evo2_observation_and_named_speculation"}
                try:
                    import chemistry_frontier_bridge
                    assessment = chemistry_frontier_bridge.assess(note, source_query_succeeded=True)
                    note.update({"entry_id": assessment["entry_id"],
                                 "interest_score": assessment["interest_score"],
                                 "reason_for_score": assessment["reason_for_score"],
                                 "flagged_for_next_lab_session": assessment["flagged_for_next_lab_session"],
                                 "surfaced_to_frontier": False,
                                 "interest_truth_status": assessment["truth_status"]})
                except Exception as exc: _fault("frontier_interest", exc)
                state.pop("evo2_result", None); next_phase = "orient"
            _line = (_inquiry_before or {}).get("line_id")
            if _line and next_phase == "orient" and phase in ("browse", "sources"):
                try:   # the source answered nothing on the line's question: a test, and it is kept as one
                    import lab_lines
                    lab_lines.record_step(_line, {"question": (_inquiry_before or {}).get("question"),
                                                  "source": str(((_inquiry_before or {}).get("source_query") or {}).get("source") or "uniprot"),
                                                  "result": "", "answered": "no: " + str(note.get("reason") or note["kind"])[:200]})
                    note["line"] = _line
                except Exception as exc:
                    _fault("lab_lines_miss", exc)
            _append(NOTEBOOK, note)
            if note["kind"] == "reflection":
                # Which sourced proteins he actually wrote about. Late import, same reason.
                try:
                    import chemistry_taste
                    chemistry_taste.observe_reflection(note)
                except Exception as exc:
                    _fault("taste_reflection", exc)
            state.update({"phase": next_phase, "last_turn_at": now_iso(), "last_outcome": note["kind"],
                          "effective_state": "waiting", "turns": int(state.get("turns", 0)) + 1,
                          "fault_streak": 0, "fault_phase": None})
            _atomic(STATE, state)
            return {"ok": True, "state": "completed", "kind": note["kind"], "next_phase": next_phase}
    except TimeoutError:
        state["effective_state"] = "yielded_to_house"; state["last_outcome"] = "not_admitted"; _atomic(STATE, state)
        return {"ok": True, "state": "yielded_to_house"}
    except Exception as exc:
        _fault("tick", exc, phase=state.get("phase"))
        state["effective_state"] = "held_fault"; state["last_outcome"] = "fault:" + exc.__class__.__name__
        state["last_turn_at"] = now_iso()
        # A fault used to leave the phase where it was, so the daemon retried the same failing turn every
        # poll, forever — the Lab looked alive and stood still. After FAULT_LIMIT consecutive faults in one
        # phase, the inquiry is dropped and the Lab returns to orientation, and the notebook says so.
        phase = state.get("phase", "orient")
        streak = int(state.get("fault_streak", 0)) + 1 if state.get("fault_phase") == phase else 1
        state["fault_phase"], state["fault_streak"] = phase, streak
        if streak >= FAULT_LIMIT and phase != "orient":
            for key in ("inquiry", "records", "additional_source", "evo2_result"):
                state.pop(key, None)
            state.update({"phase": "orient", "fault_streak": 0, "fault_phase": None, "effective_state": "waiting"})
            _append(NOTEBOOK, {"at": now_iso(), "kind": "fault_redirect", "phase": phase, "faults": streak,
                               "error": str(exc)[:240], "truth_status": "no_observation_no_inference"})
        _atomic(STATE, state)
        return {"ok": False, "state": "held_fault", "error": str(exc)[:180]}


def daemon():
    _ensure()
    while True:
        try: tick()
        except Exception as exc: _fault("daemon", exc)
        time.sleep(max(15, min(3600, int(config()["poll_seconds"]))))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status": print(json.dumps(status(), indent=2))
    elif cmd == "on": print(json.dumps(set_enabled(True), indent=2))
    elif cmd == "off": print(json.dumps(set_enabled(False), indent=2))
    elif cmd == "evo-on": print(json.dumps(set_evo2_enabled(True), indent=2))
    elif cmd == "evo-off": print(json.dumps(set_evo2_enabled(False), indent=2))
    elif cmd in ("tick", "daemon"):
        import lab_claim_evidence
        CLAIM_FULLTEXT_FETCH = lab_claim_evidence.live_fetch()
        if cmd == "tick": print(json.dumps(tick(), indent=2))
        else: daemon()
    else: raise SystemExit("usage: chemistry_lab.py status|on|off|evo-on|evo-off|tick|daemon")
