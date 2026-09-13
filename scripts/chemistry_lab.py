#!/usr/bin/env python3
"""Vintos's Chemistry Lab: a separate, visible, interruptible play space.

The Lab is not the Atelier.  It has no seal, visit capability, audience flag or
stratagem path, and writes only below memory/chemistry-lab/.  Its daemon is
continuously *eligible*, not continuously entitled to the GPU: every small turn
must enter compute_admission's background slot and yields between turns.

Phase 1 is intentionally useful without pretending heavy scientific tools are
installed.  It lets his local Aegis Gemma form a sourced UniProt browsing query,
fetches public records read-only, and reflects into an append-only notebook. Tool
adapters report unavailable until ESMC / structure / design / quantum chemistry
are separately installed and measured on their actual host.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
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
LOCK = os.path.join(ROOT, ".lock")
STOP = os.path.join(ROOT, ".stop-requested")

LLM_URL = os.environ.get("CHEM_LAB_LLM_URL", "http://127.0.0.1:8599/gemma-aegis/v1/chat/completions")
LLM_MODEL = os.environ.get("CHEM_LAB_LLM_MODEL", "google/gemma-4-12b-qat")
UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/search"
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
PHASES = ("orient", "browse", "reflect")
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
        return "reviewed:true AND length:[40 TO 350]"
    # Keep wandering bounded to reviewed, modest proteins; generated prose cannot widen this perimeter.
    return "reviewed:true AND length:[40 TO 350] AND (" + query + ")"


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
    params = urllib.parse.urlencode({"query": query, "format": "json", "size": int(limit),
                                     "fields": "accession,id,protein_name,organism_name,length,cc_function"})
    req = urllib.request.Request(UNIPROT_URL + "?" + params,
                                 headers={"User-Agent": "Vintos-Chemistry-Lab/1.0 (read-only creative study)"})
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = json.loads(response.read())
    rows = []
    for item in raw.get("results", [])[:limit]:
        desc = (((item.get("proteinDescription") or {}).get("recommendedName") or {})
                .get("fullName", {}).get("value", ""))
        rows.append({"accession": item.get("primaryAccession"), "id": item.get("uniProtkbId"),
                     "protein_name": desc, "organism": (item.get("organism") or {}).get("scientificName"),
                     "length": (item.get("sequence") or {}).get("length")})
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


def tools_status():
    # Honest availability only. Importing large models here would itself consume the resource we are reporting.
    return {
        "uniprot": {"available": True, "host": "public_read_only"},
        "esmc": {"available": bool(shutil.which("chem-lab-esmc")), "host": "aegis", "state": "adapter_required"},
        "structure_prediction": {"available": bool(shutil.which("chem-lab-fold")), "host": "measured_later", "state": "adapter_required"},
        "protein_mpnn": {"available": bool(shutil.which("chem-lab-mpnn")), "host": "measured_later", "state": "adapter_required"},
        "qpanda": {"available": False, "host": "mac", "state": "lab_bridge_not_wired"},
        "quantum_chemistry": {"available": False, "host": "mac", "state": "compatibility_probe_required"},
    }


def status():
    cfg = config(); state = _load(STATE, {})
    return {"ok": True, "lab": "chemistry", "enabled": cfg["enabled"],
            "effective_state": (state.get("effective_state") or ("waiting" if cfg["enabled"] else "off")),
            "phase": state.get("phase", "orient"), "last_turn_at": state.get("last_turn_at"),
            "last_outcome": state.get("last_outcome"), "stop_requested": stop_requested(),
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
                records = _browse(inquiry["uniprot_query"], cfg["max_records_per_browse"])
                state["records"] = records; next_phase = "reflect"
                note = {"at": now_iso(), "kind": "source_read", "source": "UniProtKB REST",
                        "query": inquiry["uniprot_query"], "records": records,
                        "truth_status": "source_metadata_not_lived_experience"}
            else:
                inquiry, records = state.get("inquiry", {}), state.get("records", [])
                reflection = _reflect(context, inquiry, records); next_phase = "orient"
                note = {"at": now_iso(), "kind": "reflection", "inquiry": inquiry,
                        "source_accessions": [r.get("accession") for r in records], **reflection,
                        "truth_status": "mixed_sourced_observation_and_named_speculation"}
                state.pop("records", None); state.pop("inquiry", None)
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
