#!/usr/bin/env python3
"""The house-side doorway to Vintos's QLab on the Mac.

The Mac keeps the run.  This client returns the complete result to the active
Atelier visit, which stores it as a sealed project artifact.  It has no chat
hook, no general-memory writer, and no interpretation of its own.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys

CONFIG = os.environ.get("VINTOS_QLAB_CONFIG",
                        os.path.expanduser("~/.vintos/quantum-lab.json"))
DEFAULT_COMMAND = "/Users/kevin/qlab/qremote.py"
HOST_RE = re.compile(r"^[A-Za-z0-9_.-]+@[A-Za-z0-9_.:-]+$")
COMMAND_RE = re.compile(r"^/[A-Za-z0-9_./@+-]+$")


def _read_config():
    if not os.path.exists(CONFIG):
        return None, "not configured"
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        return None, "config unreadable: %s" % e
    if not isinstance(cfg, dict):
        return None, "config is not an object"
    host = str(cfg.get("host", ""))
    command = str(cfg.get("command", DEFAULT_COMMAND))
    if not HOST_RE.fullmatch(host):
        return None, "config host must be user@tailscale-host"
    if not COMMAND_RE.fullmatch(command):
        return None, "config command must be one absolute path"
    return cfg, None


def _command(cfg):
    cmd = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
           "-o", "StrictHostKeyChecking=accept-new"]
    identity = str(cfg.get("identity_file", "")).strip()
    if identity:
        cmd += ["-i", os.path.expanduser(identity), "-o", "IdentitiesOnly=yes"]
    if cfg.get("port"):
        cmd += ["-p", str(int(cfg["port"]))]
    cmd += [cfg["host"], shlex.quote(str(cfg.get("command", DEFAULT_COMMAND)))]
    return cmd


def request(body, timeout=900):
    cfg, error = _read_config()
    if error:
        return {"ok": False, "configured": False, "error": error}
    try:
        done = subprocess.run(_command(cfg), input=json.dumps(body), text=True,
                              capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "configured": True, "error": "QLab timed out"}
    except Exception as e:
        return {"ok": False, "configured": True, "error": "QLab doorway failed: %s" % e}
    if done.returncode and not done.stdout.strip():
        return {"ok": False, "configured": True,
                "error": "QLab unreachable: " + done.stderr.strip()[-500:]}
    try:
        reply = json.loads(done.stdout)
    except Exception:
        return {"ok": False, "configured": True,
                "error": "QLab returned unreadable output", "detail": done.stdout[-500:]}
    if not isinstance(reply, dict):
        return {"ok": False, "configured": True, "error": "QLab reply is not an object"}
    reply["configured"] = True
    if done.stderr.strip():
        reply["ssh_notes"] = done.stderr.strip()[-1000:]
    return reply


def status(timeout=20):
    return request({"action": "status"}, timeout=timeout)


def live_parameters(experiment):
    path = os.path.expanduser("~/.vintos/workspace/memory/quantum-inputs/%s.json" % experiment)
    try:
        with open(path, encoding="utf-8") as f: body = json.load(f)
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


def available_materials():
    root = os.path.expanduser("~/.vintos/workspace/memory/quantum-inputs")
    try: return sorted(os.path.splitext(x)[0] for x in os.listdir(root) if x.endswith(".json"))
    except Exception: return []


def run_seed(experiment, parameters=None, shots=4096):
    if not parameters:
        parameters = live_parameters(experiment)
    return request({"action": "run", "experiment": experiment,
                    "parameters": parameters or {}, "shots": int(shots)})


def run_code(name, source, parameters=None, shots=4096):
    return request({"action": "code", "name": name, "source": source,
                    "parameters": parameters or {}, "shots": int(shots)})


def configure(host, identity_file="", command=DEFAULT_COMMAND):
    if not HOST_RE.fullmatch(host):
        raise ValueError("host must look like user@tailscale-host")
    if not COMMAND_RE.fullmatch(command):
        raise ValueError("command must be one absolute path")
    body = {"host": host, "command": command}
    if identity_file:
        body["identity_file"] = identity_file
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    temporary = CONFIG + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(temporary, CONFIG)
    os.chmod(CONFIG, 0o600)
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status")
    p = sub.add_parser("configure")
    p.add_argument("--host", required=True)
    p.add_argument("--identity-file", default="")
    p.add_argument("--command", default=DEFAULT_COMMAND)
    args = parser.parse_args()
    if args.action == "configure":
        print(json.dumps({"ok": True, "config": configure(args.host, args.identity_file,
                                                            args.command)}, indent=2))
    else:
        print(json.dumps(status(), indent=2))


if __name__ == "__main__":
    main()
