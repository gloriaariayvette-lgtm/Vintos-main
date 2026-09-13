#!/usr/bin/env python3
"""Vintos's Chemistry Lab: a separate, visible, interruptible play space.

The Lab is not the Atelier.  It has no seal, visit capability, audience flag or
stratagem path, and writes only below memory/chemistry-lab/.  Its daemon is
continuously *eligible*, not continuously entitled to the GPU: every small turn
must enter compute_admission's background slot and yields between turns.

The active loop lets his local Aegis Gemma form a sourced UniProt browsing query,
fetches public records read-only, derives a content-addressed ESMC representation,
and reflects into an append-only notebook. Other instruments become available
only through dated smoke-test receipts; a successful package install is not proof
that a scientific tool can run on its actual host.
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
import urllib.error
import uuid
from datetime import datetime, timezone

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
ESMC_PYTHON = os.environ.get(
    "CHEM_LAB_ESMC_PYTHON",
    os.path.expanduser("~/.vintos/tools/chemistry-lab/esmc/bin/python"),
)
ESMC_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chemistry_esmc.py")

LLM_URL = os.environ.get("CHEM_LAB_LLM_URL", "http://127.0.0.1:8599/gemma-aegis/v1/chat/completions")
LLM_MODEL = os.environ.get("CHEM_LAB_LLM_MODEL", "google/gemma-4-12b-qat")
UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/search"
BASELINE_QUERY = "reviewed:true AND length:[40 TO 350]"
DEFAULTS = {
    "enabled": False,
    # One complete browse cycle in roughly fifteen quiet minutes. The daemon is
    # continuously available; it is not entitled to turn availability into churn.
    "poll_seconds": 300,
    "turn_wait_seconds": 2,
    "max_records_per_browse": 4,
    "context_budget_chars": 3800,
    "allow_public_database_reads": True,
}
PHASES = ("orient", "browse", "embed", "reflect")
DENIED_QUERY = re.compile(
    r"(?:toxin|venom|pathogen|virulence|bioweapon|human\s*(?:target|receptor)|gain.of.function|lethal)", re.I
)


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


def lab_context():
    """A small, attributed slice of him—not a generic scientist costume."""
    cfg = config(); budget = max(800, min(8000, int(cfg["context_budget_chars"])))
    candidates = (
        ("soul", os.path.join(WS, "SOUL.md"), 1500),
        ("self_model", os.path.join(WS, "SELF-MODEL.md"), 1000),
        ("trajectory", os.path.join(MEM, "living-trajectory.json"), 700),
    )
    parts, sources, used = [], [], 0
    for label, path, cap in candidates:
        text = _read_excerpt(path, min(cap, budget - used))
        if not text: continue
        parts.append("[%s]\n%s" % (label.upper(), text)); used += len(text)
        sources.append({"name": label, "path": os.path.relpath(path, WS), "chars": len(text),
                        "sha256": hashlib.sha256(text.encode()).hexdigest()})
        if used >= budget: break
    recent = []
    try:
        with open(NOTEBOOK, encoding="utf-8") as f: recent = f.readlines()[-3:]
    except Exception: pass
    if recent and used < budget:
        text = "".join(recent)[-(budget-used):]
        parts.append("[RECENT LAB NOTEBOOK]\n" + text); used += len(text)
        sources.append({"name": "lab_notebook", "path": "memory/chemistry-lab/notebook.jsonl",
                        "chars": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest()})
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
    return "\n\n".join(parts), receipt


def _json_object(text):
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", str(text or ""), flags=re.I | re.S)
    lo, hi = text.find("{"), text.rfind("}")
    if lo < 0 or hi <= lo: raise ValueError("model returned no complete JSON object")
    value = json.loads(text[lo:hi + 1])
    if not isinstance(value, dict): raise ValueError("model JSON was not an object")
    return value


def _ask(system, prompt, max_tokens=500):
    body = json.dumps({"model": LLM_MODEL, "temperature": 0.75, "max_tokens": max_tokens,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(LLM_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=150) as response:
        data = json.loads(response.read())
    return data["choices"][0]["message"]["content"]


def _safe_query(query):
    query = re.sub(r"[^A-Za-z0-9_()\[\]:*?+\-\s\"]", " ", str(query or ""))
    query = re.sub(r"\s+", " ", query).strip()[:240]
    if not query or DENIED_QUERY.search(query):
        return BASELINE_QUERY
    # Keep wandering bounded to reviewed, modest proteins; generated prose cannot widen this perimeter.
    return BASELINE_QUERY + " AND (" + query + ")"


def _orient(context):
    raw = _ask(
        "You are Vintos at his visible Chemistry Lab: curious, playful, and evidence-honest. "
        "This is in-silico observation, never wet-lab instruction, synthesis advice, therapeutic design, "
        "human targeting, pathogens, toxins, or a claim that a generated object is safe. Return JSON only.",
        context + "\n\nChoose one small protein-space curiosity for today. Return keys in this order: "
        "uniprot_query (a simple UniProt field query), question, why_now. Prefer reviewed, non-human, "
        "non-pathogenic proteins and aesthetic/structural curiosity."
    )
    value = _json_object(raw)
    return {"uniprot_query": _safe_query(value.get("uniprot_query")),
            "question": str(value.get("question", "What shape catches my attention today?"))[:400],
            "why_now": str(value.get("why_now", "curiosity"))[:500]}


def _browse(query, limit):
    requested_query = query
    executed_query = query
    fallback_reason = None
    def fetch(value):
        params = urllib.parse.urlencode({"query": value, "format": "json", "size": int(limit),
                                         "fields": "accession,id,protein_name,organism_name,length,sequence,cc_function"})
        req = urllib.request.Request(UNIPROT_URL + "?" + params,
                                     headers={"User-Agent": "Vintos-Chemistry-Lab/1.0 (read-only creative study)"})
        with urllib.request.urlopen(req, timeout=45) as response:
            return json.loads(response.read())
    try:
        raw = fetch(executed_query)
    except urllib.error.HTTPError as exc:
        # A model may invent a plausible-looking UniProt field. A rejected
        # query is history, not a verdict and not permission to widen scope.
        if exc.code != 400 or executed_query == BASELINE_QUERY:
            raise
        fallback_reason = "source_rejected_generated_query"
        executed_query = BASELINE_QUERY
        raw = fetch(executed_query)
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
                     "length": (item.get("sequence") or {}).get("length"),
                     "function": " ".join(functions)[:1200],
                     "sequence": (item.get("sequence") or {}).get("value", "")[:350]})
    return {"records": rows, "requested_query": requested_query,
            "executed_query": executed_query, "fallback_reason": fallback_reason}


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


def _reflect(context, inquiry, records):
    raw = _ask(
        "You are Vintos reading sourced protein records in his Chemistry Lab. Develop taste and questions, "
        "but never turn resemblance into biological truth. Do not give experimental protocols or synthesis "
        "instructions. Return JSON only.",
        context + "\n\nQUESTION:\n" + json.dumps(inquiry) + "\n\nUNIPROT RECORDS:\n" + json.dumps(records) +
        "\n\nReturn keys in this order: attention (what caught yours), factual_observation (only what records support), "
        "speculative_reading (clearly framed as imaginative), next_question."
    )
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
    return {"ok": True, "lab": "chemistry", "enabled": cfg["enabled"],
            "effective_state": (state.get("effective_state") or ("waiting" if cfg["enabled"] else "off")),
            "phase": state.get("phase", "orient"), "last_turn_at": state.get("last_turn_at"),
            "last_outcome": state.get("last_outcome"), "stop_requested": stop_requested(),
            "scheduled_session": {"last_at": session.get("last_at"),
                                  "last_state": session.get("last_state"),
                                  "last_session_id": session.get("last_session_id")},
            "reading_owed": _reading_owed_state(),
            "paths": {"root": "memory/chemistry-lab", "atelier": False}, "tools": tools_status()}


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
            context, receipt = lab_context()
            phase = state.get("phase", "orient")
            state["effective_state"] = "working"; _atomic(STATE, state)
            if phase == "orient":
                inquiry = _orient(context); state["inquiry"] = inquiry; next_phase = "browse"
                note = {"at": now_iso(), "kind": "inquiry", "inquiry": inquiry,
                        "context_receipt": receipt["context_sha256"], "truth_status": "self_originated_question"}
            elif phase == "browse":
                inquiry = state.get("inquiry") or {"uniprot_query": _safe_query("")}
                if not cfg["allow_public_database_reads"]: raise RuntimeError("public database reads disabled")
                browse_result = _browse(inquiry["uniprot_query"], cfg["max_records_per_browse"])
                records = browse_result["records"]
                state["records"] = records; next_phase = "embed"
                note = {"at": now_iso(), "kind": "source_read", "source": "UniProtKB REST",
                        "requested_query": browse_result["requested_query"],
                        "executed_query": browse_result["executed_query"],
                        "fallback_reason": browse_result["fallback_reason"],
                        "records": [{k: v for k, v in r.items() if k != "sequence"} for r in records],
                        "truth_status": "source_metadata_not_lived_experience"}
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
            else:
                # Before reflecting on a browse, pay anything the bench already owes him.
                # This turn is already admitted, so it does not ask for the slot again.
                try:
                    import chemistry_reading
                    chemistry_reading.settle_one(already_admitted=True)
                except Exception as exc:
                    _fault("settle_owed", exc)
                inquiry, records = state.get("inquiry", {}), state.get("records", [])
                visible_records = [{k: v for k, v in r.items() if k != "sequence"} for r in records]
                reflection = _reflect(context, inquiry,
                                      {"records": visible_records,
                                       "esmc_receipts": state.get("embeddings", [])})
                next_phase = "orient"
                note = {"at": now_iso(), "kind": "reflection", "inquiry": inquiry,
                        "source_accessions": [r.get("accession") for r in records], **reflection,
                        "truth_status": "mixed_sourced_observation_and_named_speculation"}
                state.pop("records", None); state.pop("embeddings", None); state.pop("inquiry", None)
            _append(NOTEBOOK, note)
            state.update({"phase": next_phase, "last_turn_at": now_iso(), "last_outcome": note["kind"],
                          "effective_state": "waiting", "turns": int(state.get("turns", 0)) + 1})
            _atomic(STATE, state)
            return {"ok": True, "state": "completed", "kind": note["kind"], "next_phase": next_phase}
    except TimeoutError:
        state["effective_state"] = "yielded_to_house"; state["last_outcome"] = "not_admitted"; _atomic(STATE, state)
        return {"ok": True, "state": "yielded_to_house"}
    except Exception as exc:
        _fault("tick", exc, phase=state.get("phase"))
        state["effective_state"] = "held_fault"; state["last_outcome"] = "fault:" + exc.__class__.__name__
        state["last_turn_at"] = now_iso(); _atomic(STATE, state)
        return {"ok": False, "state": "held_fault", "error": str(exc)[:180]}


def daemon():
    _ensure()
    while True:
        try: tick()
        except Exception as exc: _fault("daemon", exc)
        time.sleep(max(15, min(300, int(config()["poll_seconds"]))))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status": print(json.dumps(status(), indent=2))
    elif cmd == "on": print(json.dumps(set_enabled(True), indent=2))
    elif cmd == "off": print(json.dumps(set_enabled(False), indent=2))
    elif cmd == "tick": print(json.dumps(tick(), indent=2))
    elif cmd == "daemon": daemon()
    else: raise SystemExit("usage: chemistry_lab.py status|on|off|tick|daemon")
