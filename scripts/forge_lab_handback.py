"""Pull owned Forge partial acquisitions into Lab evidence; never fulfill or replay a request."""
import json
import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request
from forge_genomic_result import verified_result, direct_verification

def fetch_artifacts(cfg, project):
    from lab_http import open_request
    endpoint = urlsplit(cfg["url"])
    if endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1" or endpoint.path != "/api/lab-intake":
        raise ValueError("handback requires the configured local Forge")
    if not re.fullmatch("[a-f0-9]{32}", project): raise ValueError("invalid project id")
    url = "%s://%s/api/projects/%s/artifacts" % (endpoint.scheme, endpoint.netloc, project)
    with open_request(Request(url), timeout=15) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024: raise ValueError("handback exceeds limit")
    return json.loads(raw)

def ownership(row):
    """Bind the complete original outbox request and its source evidence across the fetch."""
    fields = {key:row.get(key) for key in ("project_id", "state", "question", "receipt_ids")}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, allow_nan=False).encode()).hexdigest()


def pointer(row):
    """Project canonical consumer progress; never reset a durable partial/verified outcome."""
    verification = row.get("verification") or {}
    state = verification.get("state", "pending")
    if state not in ("pending", "running", "verified_present", "verified_absent", "partial", "unresolved"):
        state = "unresolved"
    receipts = verification.get("evidence_receipt_ids")
    bound = verification.get("ownership_sha256") == row.get("ownership_sha256") and bool(row.get("ownership_sha256"))
    evidence = (isinstance(receipts, list) and 1 <= len(receipts) <= 8 and
                all(isinstance(value, str) and re.fullmatch("[a-f0-9]{64}", value) for value in receipts))
    fulfilled = (state in ("verified_present", "verified_absent") and bound and evidence and
                 verification.get("original_request_fulfilled") is True)
    if state in ("verified_present", "verified_absent") and not fulfilled:
        state = "unresolved"
    return {"cycle_id":row["cycle_id"], "state":state, "original_request_fulfilled":fulfilled}


def collect(cfg, root, projects, *, load, atomic, locked, fetch=None, record=None):
    """One idempotent local handback per accepted cycle, tied to the Lab's original outbox."""
    fetch = fetch or fetch_artifacts
    root = Path(root)
    outbox_path = str(root / "forge-report-outbox.json")
    handbacks_path = str(root / "forge-capability-handbacks.json")
    collected = []
    for project in projects or []:
        if project.get("state") != "awaiting_lab": continue
        pid = project.get("id")
        with locked():
            outbox = load(outbox_path, {})
            owned = next(((key,row) for key,row in outbox.items() if row.get("project_id") == pid and row.get("state") == "accepted"), None)
            stored = load(handbacks_path, {})
            if not owned: continue
            bound = ownership(owned[1])
            existing = next((row for row in stored.values() if row.get("project_id") == pid), None)
            if existing:
                # Canonical ownership and verification win over a stale/missing outbox pointer.
                if (existing.get("ownership_sha256") == bound and
                    existing.get("original_request") == str(owned[1]["question"])[:2000]):
                    projected = pointer(existing)
                    if owned[1].get("capability_handback") != projected:
                        owned[1]["capability_handback"] = projected
                        atomic(outbox_path, outbox)
                elif owned[1].get("capability_handback", {}).get("cycle_id") == existing.get("cycle_id"):
                    # Old evidence remains canonical, but must not label a changed request fulfilled.
                    owned[1].pop("capability_handback", None)
                    atomic(outbox_path, outbox)
                continue
        artifacts = fetch(cfg, pid)
        for cycle in artifacts if isinstance(artifacts, list) else []:
            if cycle.get("state") != "accepted": continue
            try:
                artifact = json.loads(cycle["artifact"])
                accepted = json.loads(cycle["receipt"])
                handback = artifact["lab_handback"]
                resolution = artifact["capability_resolution"]
                if (handback["status"] != "capability_available_original_request_unfulfilled" or
                    handback["cycle_id"] != cycle["id"] or accepted["cycle_id"] != cycle["id"] or
                    handback["original_request"] != str(owned[1]["question"])[:2000] or accepted["charged_cents"] != 0):
                    continue
                if resolution.get("route") == "direct_authoritative_verification":
                    if not direct_verification(resolution,handback["original_request"]): continue
                    handle = None
                else:
                    handle = verified_result(resolution["result"], resolution["request"])
            except (ValueError, KeyError, TypeError): continue
            row = {"project_id":pid, "cycle_id":cycle["id"], "outbox_key":owned[0],
                   "original_request":handback["original_request"], "original_request_fulfilled":False,
                   "state":"capability_available_verification_required", "sequence_handle":handle,
                   "artifact":artifact, "accepted_receipt":accepted, "ownership_sha256":bound,
                   "source_receipt_ids":owned[1].get("receipt_ids", []),
                   "verification":{"state":"pending", "ownership_sha256":bound, "evidence_receipt_ids":[],
                                   "original_request_fulfilled":False}}
            with locked():
                # Recheck ownership after the read; never import another project's evidence.
                outbox = load(outbox_path, {})
                current = outbox.get(owned[0], {})
                if (current.get("project_id") != pid or current.get("state") != "accepted" or
                    ownership(current) != bound or
                    str(current.get("question", ""))[:2000] != handback["original_request"]):
                    continue
                stored = load(handbacks_path, {})
                if cycle["id"] in stored: continue
                if record: record(row)
                stored[cycle["id"]] = row
                atomic(handbacks_path, stored)
                current["capability_handback"] = pointer(row)
                atomic(outbox_path, outbox)
                collected.append(row)
    return collected
