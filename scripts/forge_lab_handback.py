"""Pull owned Forge partial acquisitions into Lab evidence; never fulfill or replay a request."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request
from forge_genomic_result import verified_result

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
            existing = next((row for row in stored.values() if row.get("project_id") == pid), None)
            if existing:
                # Recover a crash after the canonical ledger write but before the outbox pointer.
                if existing.get("original_request") == str(owned[1]["question"])[:2000]:
                    pointer = {"cycle_id":existing["cycle_id"], "state":existing["state"],
                               "original_request_fulfilled":False}
                    if owned[1].get("capability_handback") != pointer:
                        owned[1]["capability_handback"] = pointer
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
                handle = verified_result(resolution["result"], resolution["request"])
            except (ValueError, KeyError, TypeError): continue
            row = {"project_id":pid, "cycle_id":cycle["id"], "outbox_key":owned[0],
                   "original_request":handback["original_request"], "original_request_fulfilled":False,
                   "state":"capability_available_verification_required", "sequence_handle":handle,
                   "artifact":artifact, "accepted_receipt":accepted}
            with locked():
                # Recheck ownership after the read; never import another project's evidence.
                outbox = load(outbox_path, {})
                current = outbox.get(owned[0], {})
                if current.get("project_id") != pid or current.get("state") != "accepted": continue
                stored = load(handbacks_path, {})
                if cycle["id"] in stored: continue
                if record: record(row)
                stored[cycle["id"]] = row
                atomic(handbacks_path, stored)
                current["capability_handback"] = {"cycle_id":cycle["id"], "state":row["state"],
                                                  "original_request_fulfilled":False}
                atomic(outbox_path, outbox)
                collected.append(row)
    return collected
