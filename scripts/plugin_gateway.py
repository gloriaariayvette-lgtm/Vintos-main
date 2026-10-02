#!/usr/bin/env python3
"""Shared Wants/Forge/Lab/Atelier client and durable plugin-result receipts."""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone

from plugin_catalog import policy, instructions, PLUGINS
from plugin_send_guard import PolicyHold, outbound_findings

MEMORY = os.environ.get("VINTOS_MEMORY", os.path.expanduser("~/.vintos/workspace/memory"))
CONFIG = os.environ.get("VINTOS_PLUGIN_RELAY_CONFIG", os.path.expanduser("~/.vintos/plugin-relay.json"))
REMOTE = "/Users/kevin/Documents/Codex/2026-09-10/first-please-review-everything-claude-committed/forge-loop-local/scripts/plugin_relay_remote.py"
HOST_RE = re.compile(r"^[A-Za-z0-9_.-]+@[A-Za-z0-9_.:-]+$")
COMMAND_RE = re.compile(r"^/[A-Za-z0-9_./@+-]+$")


def _config():
    path = Path(CONFIG)
    if path.stat().st_mode & 0o077: raise ValueError("plugin relay config requires mode 0600")
    data = json.loads(path.read_text())
    if not HOST_RE.fullmatch(str(data.get("host", ""))): raise ValueError("plugin relay host must be user@tailscale-host")
    command = str(data.get("command", REMOTE))
    if not COMMAND_RE.fullmatch(command): raise ValueError("plugin relay command must be one absolute path")
    data["command"] = command
    return data


def _command(cfg):
    out = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
           "-o", "StrictHostKeyChecking=accept-new"]
    identity = str(cfg.get("identity_file", "")).strip()
    if identity: out += ["-i", os.path.expanduser(identity), "-o", "IdentitiesOnly=yes"]
    if cfg.get("port"): out += ["-p", str(int(cfg["port"]))]
    return out + [cfg["host"], shlex.quote(cfg["command"])]


def _send(request, timeout=210, transport=None):
    if transport: return transport(request)
    cfg = _config()
    try:
        done = subprocess.run(_command(cfg), input=json.dumps(request), text=True,
                              capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("plugin relay timed out after send; outcome unknown and not retried") from exc
    if done.returncode and not done.stdout.strip(): raise RuntimeError("plugin relay unavailable")
    try: result = json.loads(done.stdout)
    except Exception as exc: raise RuntimeError("plugin relay returned unreadable output") from exc
    if not isinstance(result, dict) or not result.get("ok"):
        if isinstance(result, dict) and isinstance(result.get("receipt"), dict):
            raise PolicyHold(result["receipt"])
        raise RuntimeError("plugin relay refused or failed: " + str((result or {}).get("detail", "unknown"))[:500])
    return result


def _hold_path():
    return Path(MEMORY) / "plugin-policy-holds.jsonl"


def _policy_hold(kind, surface, plugin, tool, findings):
    hold_id = hashlib.sha256((kind + ":" + findings["request_sha256"]).encode()).hexdigest()
    receipt = {"hold_id":hold_id, "type":kind, "at":datetime.now(timezone.utc).isoformat(),
        "surface":surface, "plugin":plugin, "tool":tool,
        "request_sha256":findings["request_sha256"], "rules":findings.get("rules", []),
        "links":findings.get("links", []), "state":"awaiting_explicit_approval" if kind == "LINK_APPROVAL_REQUIRED" else "blocked"}
    # Never chmod the folder: it is the shared memory directory, and chmod 700 there cancelled the Atelier
    # user's granted access, so the Forge could not start (2026-09-24). The ledger file itself is 0600.
    ledger = _hold_path(); ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(str(ledger)+".lock", "a+") as lock:
        os.chmod(str(ledger)+".lock", 0o600); fcntl.flock(lock, fcntl.LOCK_EX)
        prior = [] if not ledger.exists() else [json.loads(x) for x in ledger.read_text().splitlines() if x.strip()]
        if not any(x.get("event") == "held" and x.get("hold_id") == hold_id for x in prior):
            with open(ledger, "a", encoding="utf-8") as stream:
                stream.write(json.dumps({"event":"held", **receipt}, sort_keys=True)+"\n")
                stream.flush(); os.fsync(stream.fileno())
        os.chmod(ledger, 0o600)
    return receipt


def _consume_link_approval(hold_id, request_sha256):
    ledger = _hold_path()
    if not ledger.exists(): return False
    with open(str(ledger)+".lock", "a+") as lock:
        os.chmod(str(ledger)+".lock", 0o600); fcntl.flock(lock, fcntl.LOCK_EX)
        rows = [json.loads(x) for x in ledger.read_text().splitlines() if x.strip()]
        approvals = [x for x in rows if x.get("event") == "approved" and x.get("hold_id") == hold_id and
                     x.get("request_sha256") == request_sha256]
        consumed = sum(1 for x in rows if x.get("event") == "approval_consumed" and x.get("hold_id") == hold_id and
                       x.get("request_sha256") == request_sha256)
        if len(approvals) <= consumed: return False
        with open(ledger, "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event":"approval_consumed", "hold_id":hold_id,
                "request_sha256":request_sha256, "at":datetime.now(timezone.utc).isoformat()}, sort_keys=True)+"\n")
            stream.flush(); os.fsync(stream.fileno())
        os.chmod(ledger, 0o600)
        return True


def approve_link(hold_id):
    """Record Gloria's exact-message approval from the administrative CLI."""
    if not re.fullmatch(r"[0-9a-f]{64}", str(hold_id)): raise ValueError("invalid hold id")
    ledger = _hold_path()
    if not ledger.exists(): raise KeyError("unknown link hold")
    with open(str(ledger)+".lock", "a+") as lock:
        os.chmod(str(ledger)+".lock", 0o600); fcntl.flock(lock, fcntl.LOCK_EX)
        rows = [json.loads(x) for x in ledger.read_text().splitlines() if x.strip()]
        held = next((x for x in reversed(rows) if x.get("event") == "held" and
                     x.get("hold_id") == hold_id and x.get("type") == "LINK_APPROVAL_REQUIRED"), None)
        if not held: raise KeyError("unknown link hold")
        row = {"event":"approved", "hold_id":hold_id, "request_sha256":held["request_sha256"],
               "at":datetime.now(timezone.utc).isoformat(), "authority":"gloria_cli"}
        with open(ledger, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True)+"\n"); stream.flush(); os.fsync(stream.fileno())
        os.chmod(ledger, 0o600)
    return row


def _store(surface, plugin, tool, arguments, result, visibility):
    root = Path(MEMORY) / "plugin-results"
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    artifact = root / (digest + ".json")
    if not artifact.exists():
        fd, temporary = tempfile.mkstemp(prefix=".plugin-", dir=str(root))
        try:
            with os.fdopen(fd, "wb") as stream: stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
            os.chmod(temporary, 0o600); os.replace(temporary, artifact)
        finally:
            try: os.unlink(temporary)
            except OSError: pass
    receipt = {"receipt_id":digest, "at":datetime.now(timezone.utc).isoformat(), "surface":surface,
        "plugin":plugin, "tool":tool, "arguments_sha256":hashlib.sha256(json.dumps(arguments,sort_keys=True).encode()).hexdigest(),
        "result_sha256":digest, "artifact":str(artifact), "visibility":visibility,
        "truth_status":"connected_tool_output_not_independent_validation"}
    ledger = Path(MEMORY) / "plugin-receipts.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(str(ledger)+".lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(ledger, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(receipt, sort_keys=True)+"\n"); stream.flush(); os.fsync(stream.fileno())
    os.chmod(ledger, 0o600)
    return receipt


def call(surface, plugin, tool, arguments, purpose, *, transport=None, to_self=False):
    if plugin == "nvidia_nim":
        from bionemo_gateway import call as hosted_call
        return hosted_call(surface, plugin, tool, arguments, purpose, transport=transport)
    if plugin == "nvmolkit":
        from nvmolkit_gateway import call as local_call
        return local_call(surface, plugin, tool, arguments, purpose, transport=transport)
    entry = policy(plugin, surface, tool)
    if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 1000: raise ValueError("bounded purpose required")
    if not isinstance(arguments, dict): raise ValueError("arguments must be an object")
    request = {"action":"call", "surface":surface, "plugin":plugin, "tool":tool,
               "arguments":arguments, "purpose":purpose}
    if to_self:
        # a reply to his own address (his agents' letters): the Mac relay verifies it against the mailbox's own
        # address and counts it apart from the two daily sends to people (2026-10-02)
        request["to_self"] = True
    outbound = entry.get("outbound_policy") or {}
    if tool in outbound.get("tools", ()):
        findings = outbound_findings(arguments)
        if tool != "gmail.send_email":
            findings["rules"] = sorted(set(findings["rules"] + ["provider_held_content_unavailable_for_inspection"]))
        if findings["rules"]:
            raise PolicyHold(_policy_hold("CONFIDENTIAL_INFORMATION_BLOCKED", surface, plugin, tool, findings))
        if findings["links"]:
            receipt = _policy_hold("LINK_APPROVAL_REQUIRED", surface, plugin, tool, findings)
            if not _consume_link_approval(receipt["hold_id"], findings["request_sha256"]): raise PolicyHold(receipt)
            request["link_approval"] = {"hold_id":receipt["hold_id"],
                                         "request_sha256":findings["request_sha256"]}
    response = _send(request, transport=transport)
    receipt = _store(surface, plugin, tool, arguments, response["result"], entry["visibility"])
    output = {"ok":True, "receipt":receipt, "summary":summary(response["result"])}
    if response.get("link_gate"): output["link_gate"] = response["link_gate"]
    return output


MAX_SKILL_INPUT_FILES = 4
MAX_SKILL_INPUT_BYTES = 8 * 1024 * 1024


def _skill_inputs(paths):
    root=(Path(MEMORY)/"chemistry-lab").resolve(); out=[]; total=0
    for raw in paths or []:
        offered=Path(raw).expanduser()
        if offered.is_symlink(): raise ValueError("skill inputs must not be symlinks")
        path=offered.resolve()
        if len(out)>=MAX_SKILL_INPUT_FILES: raise ValueError("too many skill input files")
        if path.is_symlink() or not path.is_file() or os.path.commonpath((str(root),str(path))) != str(root):
            raise ValueError("skill inputs must be regular Chemistry Lab artifacts")
        data=path.read_bytes(); total += len(data)
        if total>MAX_SKILL_INPUT_BYTES: raise ValueError("skill inputs exceed relay limit")
        out.append({"name":path.name,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),
                    "data_b64":base64.b64encode(data).decode()})
    return out


def _journal_skill(skill, receipt, summary_text, files):
    if receipt.get("surface") != "lab": return
    path=Path(MEMORY)/"chemistry-lab"/"notebook.jsonl"; path.parent.mkdir(parents=True,exist_ok=True)
    row={"at":datetime.now(timezone.utc).isoformat(),"kind":"plugin_instrument","skill":skill,
         "receipt_id":receipt["receipt_id"],"summary":str(summary_text)[:1800],
         "artifacts":[str(Path(f).relative_to(Path(MEMORY))) if Path(MEMORY) in Path(f).parents else str(Path(f).name) for f in files],
         "truth_status":"plugin_analysis_not_independent_validation"}
    with open(path,"a",encoding="utf-8") as stream:
        stream.write(json.dumps(row,sort_keys=True)+"\n"); stream.flush(); os.fsync(stream.fileno())


def run_skill(surface, skill, instruction, *, operation=None, input_files=None, transport=None):
    from plugin_catalog import skill_policy
    skill_policy(skill, surface, operation)
    inputs=_skill_inputs(input_files)
    response = _send({"action":"skill", "surface":surface, "skill":skill, "operation":operation,
                      "instruction":instruction,"inputs":inputs}, timeout=660, transport=transport)
    if surface == "lab" and skill in ("sequence_viewer", "structure_viewer"):
        root = Path(MEMORY)/"chemistry-lab"/"artifacts"/skill.replace("_","-")
    else:
        root = Path(MEMORY)/"plugin-results"/"skills"
    root.mkdir(parents=True, exist_ok=True); os.chmod(root,0o700)
    files=[]
    total_output=0
    for item in response.get("files",[]):
        rel=Path(item["path"])
        if rel.is_absolute() or ".." in rel.parts: raise ValueError("unsafe skill artifact path")
        data=base64.b64decode(item["data_b64"], validate=True)
        total_output += len(data)
        if total_output > 8 * 1024 * 1024: raise ValueError("skill artifacts exceed relay limit")
        if hashlib.sha256(data).hexdigest()!=item["sha256"]: raise RuntimeError("skill artifact integrity mismatch")
        target=root/(item["sha256"]+"-"+rel.name); target.write_bytes(data); os.chmod(target,0o600); files.append(str(target))
    result={"skill":skill,"operation":operation,"summary":response.get("summary",""),"input_receipts":response.get("input_receipts",[]),"files":files}
    receipt=_store(surface,"skill:"+skill,"skill.run",{"instruction_sha256":hashlib.sha256(instruction.encode()).hexdigest(),
        "input_sha256":[i["sha256"] for i in inputs]},result,"project")
    _journal_skill(skill,receipt,response.get("summary",""),files)
    return {"ok":True,"receipt":receipt,"summary":response.get("summary",""),"files":files}


def summary(value, limit=1200):
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    return text if len(text) <= limit else text[:limit] + "… [full result in receipt artifact]"


def load_receipt(receipt_id, surface):
    if not re.fullmatch(r"[0-9a-f]{64}", str(receipt_id)): raise ValueError("invalid receipt id")
    rows = []
    path = Path(MEMORY)/"plugin-receipts.jsonl"
    if path.exists():
        rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    row = next((x for x in reversed(rows) if x.get("receipt_id") == receipt_id), None)
    if not row: raise KeyError("unknown receipt")
    if row["visibility"] == "private" and row["surface"] != surface: raise PermissionError("private receipt belongs to another surface")
    data = json.loads(Path(row["artifact"]).read_text())
    if hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest() != row["result_sha256"]:
        raise RuntimeError("plugin artifact integrity mismatch")
    return {"receipt":row, "result":data}


def tool_schemas(plugin, transport=None):
    """What each of a plugin's tools expects, as the connector declares it. Calls and sends nothing."""
    from plugin_catalog import SKILLS
    if plugin not in PLUGINS and plugin not in SKILLS: raise ValueError("unknown plugin")
    return _send({"action":"schema", "plugin":plugin}, transport=transport)


def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest="action",required=True)
    sub.add_parser("instructions")
    sch=sub.add_parser("schema"); sch.add_argument("--plugin",required=True)
    skill=sub.add_parser("skill"); skill.add_argument("--surface",required=True); skill.add_argument("--skill",required=True)
    skill.add_argument("--instruction",required=True); skill.add_argument("--operation"); skill.add_argument("--input",action="append",default=[])
    approve=sub.add_parser("approve-link"); approve.add_argument("hold_id")
    invoke=sub.add_parser("call"); invoke.add_argument("--surface",required=True);invoke.add_argument("--plugin",required=True)
    invoke.add_argument("--tool",required=True);invoke.add_argument("--arguments",default="{}");invoke.add_argument("--purpose",required=True)
    args=parser.parse_args()
    if args.action == "instructions": print(json.dumps(instructions(),indent=2)); return
    if args.action == "approve-link": print(json.dumps(approve_link(args.hold_id),indent=2)); return
    if args.action == "schema": print(json.dumps(tool_schemas(args.plugin),indent=2)); return
    if args.action == "skill": print(json.dumps(run_skill(args.surface,args.skill,args.instruction,operation=args.operation,input_files=args.input),indent=2)); return
    print(json.dumps(call(args.surface,args.plugin,args.tool,json.loads(args.arguments),args.purpose),indent=2))


if __name__ == "__main__": main()
