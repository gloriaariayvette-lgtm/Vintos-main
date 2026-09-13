#!/usr/bin/env python3
"""Lab-only SSH doorway to the visible Chemistry bench on the Mac.

This deliberately has a separate config and command from Atelier QLab.  It
accepts JSON, returns JSON, and never retries a timed-out experiment whose
remote outcome is unknown.

**The door on the far side is wider than this one.**  ``bench_remote.py`` accepts
``action: "code"`` and will write a new executable experiment into the bench.  That
capacity belongs to the playground and is not something to quietly delete -- but it is
not the scheduled Lab's to reach.  Saying "this client simply has no code action" was an
argument from omission: an omission is undone by one careless edit.  So the allowlist
below is explicit and enforced at the point of send, and every refusal is returned as a
value rather than raised, in the shape the callers already read.

This is defence in depth on the near side only.  It does not make the far door safe.
The Mac's own ``code`` action still needs its own authenticated authority, separate from
the scheduled named-experiment route; ``docs/open-work.md`` carries that as open.
"""
import argparse
import json
import os
import re
import shlex
import subprocess

CONFIG = os.environ.get("VINTOS_CHEMISTRY_MAC_CONFIG",
                        os.path.expanduser("~/.vintos/chemistry-mac.json"))
DEFAULT_COMMAND = "/Users/kevin/qlab/bench_remote.py"
# The only actions the scheduled Lab may put through this door.  "code" is deliberately
# absent and must stay absent: named experiments in, results out.
ALLOWED_ACTIONS = ("status", "ledger", "run", "reading")
HOST_RE = re.compile(r"^[A-Za-z0-9_.-]+@[A-Za-z0-9_.:-]+$")
COMMAND_RE = re.compile(r"^/[A-Za-z0-9_./@+-]+$")


def _read_config():
    try:
        with open(CONFIG, encoding="utf-8") as stream: cfg = json.load(stream)
    except FileNotFoundError:
        return None, "not configured"
    except Exception as exc:
        return None, "config unreadable: %s" % exc
    if not isinstance(cfg, dict): return None, "config is not an object"
    if not HOST_RE.fullmatch(str(cfg.get("host", ""))):
        return None, "config host must be user@tailscale-host"
    if not COMMAND_RE.fullmatch(str(cfg.get("command", DEFAULT_COMMAND))):
        return None, "config command must be one absolute path"
    return cfg, None


def _command(cfg):
    command = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
               "-o", "StrictHostKeyChecking=accept-new"]
    identity = str(cfg.get("identity_file", "")).strip()
    if identity:
        command += ["-i", os.path.expanduser(identity), "-o", "IdentitiesOnly=yes"]
    if cfg.get("port"): command += ["-p", str(int(cfg["port"]))]
    command += [cfg["host"], shlex.quote(str(cfg.get("command", DEFAULT_COMMAND)))]
    return command


def request(body, timeout=600):
    if not isinstance(body, dict):
        return {"ok": False, "configured": False, "error": "Lab doorway body must be an object"}
    action = str(body.get("action", ""))
    if action not in ALLOWED_ACTIONS:
        return {"ok": False, "configured": False, "refused": "action_not_allowed",
                "error": "the Lab doorway carries %s only; %r is not the scheduled route's to send"
                         % ("/".join(ALLOWED_ACTIONS), action[:40])}
    cfg, error = _read_config()
    if error: return {"ok": False, "configured": False, "error": error}
    try:
        done = subprocess.run(_command(cfg), input=json.dumps(body), text=True,
                              capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "configured": True, "state": "unknown_after_timeout",
                "error": "Mac Lab experiment timed out after send; not retried"}
    except Exception as exc:
        return {"ok": False, "configured": True, "error": "Mac Lab doorway failed: %s" % exc}
    if done.returncode and not done.stdout.strip():
        return {"ok": False, "configured": True,
                "error": "Mac Lab unreachable: " + done.stderr.strip()[-500:]}
    try: reply = json.loads(done.stdout)
    except Exception:
        return {"ok": False, "configured": True, "error": "Mac Lab returned unreadable output",
                "detail": done.stdout[-500:]}
    if not isinstance(reply, dict):
        return {"ok": False, "configured": True, "error": "Mac Lab reply is not an object"}
    reply["configured"] = True
    return reply


def status(timeout=20): return request({"action": "status"}, timeout=timeout)
def ledger(limit=12): return request({"action": "ledger", "limit": int(limit)}, timeout=30)
def run(experiment, parameters=None, shots=4096):
    return request({"action": "run", "experiment": experiment,
                    "parameters": parameters or {}, "shots": int(shots)})
def reading(run_id, text):
    return request({"action": "reading", "run_id": str(run_id), "text": str(text)[:3000]}, timeout=30)


def configure(host, identity_file="", command=DEFAULT_COMMAND):
    if not HOST_RE.fullmatch(host): raise ValueError("host must look like user@tailscale-host")
    if not COMMAND_RE.fullmatch(command): raise ValueError("command must be one absolute path")
    value = {"host": host, "command": command}
    if identity_file: value["identity_file"] = identity_file
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    temporary = CONFIG + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, CONFIG); os.chmod(CONFIG, 0o600)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status")
    setup = sub.add_parser("configure")
    setup.add_argument("--host", required=True); setup.add_argument("--identity-file", default="")
    setup.add_argument("--command", default=DEFAULT_COMMAND)
    args = parser.parse_args()
    if args.action == "configure":
        print(json.dumps({"ok": True, "config": configure(args.host, args.identity_file, args.command)}, indent=2))
    else: print(json.dumps(status(), indent=2))


if __name__ == "__main__": main()
