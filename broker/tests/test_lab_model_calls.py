#!/usr/bin/env python3
"""The Lab records every model call exactly as sent and answered. Scratch HOME only; no model or network."""

import importlib.util
import io
import json
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-lab-calls-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
os.environ["VINTOS_LAB_CAMPAIGNS"] = "0"
sys.modules["lab_investigations"] = types.SimpleNamespace(turn=lambda *a, **k: None)

NET_CALLS = []
def _no_network(*a, **k):
    NET_CALLS.append(a[:1]); raise AssertionError("this suite must never reach the network")
sys.modules["lab_http"] = types.SimpleNamespace(open_request=_no_network)
spec = importlib.util.spec_from_file_location("chemistry_lab_calls_test", os.path.join(REPO, "scripts", "chemistry_lab.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:180]) if detail and not ok else ""))

check("test is in a scratch workspace", HOME in M.MODEL_CALLS and not M.MODEL_CALLS.startswith("/home/gloria"), M.MODEL_CALLS)

# The model endpoint is a stub: the Lab's one urlopen returns a canned reply and records what it was sent.
SENT = []
class _Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False
def _fake_urlopen(req, timeout=None):
    SENT.append(json.loads(req.data))
    return _Response(json.dumps({"choices": [{"message": {"content": '{"question": "q"}'}, "finish_reason": "stop"}],
                                 "usage": {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13}}).encode())
M.urllib.request.urlopen = _fake_urlopen

def planner_step():
    return M._ask("SYSTEM TEXT", "PROMPT TEXT", max_tokens=321, temperature=0.3)

reply = planner_step()
rows = [json.loads(l) for l in open(M.MODEL_CALLS)]
row = rows[-1] if rows else {}
check("the reply is returned unchanged", reply == '{"question": "q"}' and reply.completion is not None)
check("one call, one record", len(rows) == 1 and len(SENT) == 1, rows)
check("the exact system and prompt are kept", row.get("system") == "SYSTEM TEXT" and row.get("prompt") == "PROMPT TEXT")
check("the exact raw reply is kept", row.get("reply") == '{"question": "q"}')
check("the step that asked is named", row.get("caller") == "planner_step", row.get("caller"))
check("sampling settings are kept", row.get("temperature") == 0.3 and row.get("max_tokens") == 321)
check("completion metadata is kept", isinstance(row.get("completion"), dict))

# Recording can never change or stop a turn.
original_append = M._append
def _broken_append(path, value):
    if path == M.MODEL_CALLS:
        raise OSError("disk full")
    return original_append(path, value)
M._append = _broken_append
check("a failed record does not stop the call", planner_step() == '{"question": "q"}')
M._append = original_append

# The file rotates at its cap instead of growing without bound.
M.MODEL_CALLS_CAP = 1
planner_step()
check("the log rotates at its cap", os.path.exists(M.MODEL_CALLS + ".1") and len(open(M.MODEL_CALLS).readlines()) == 1)

check("nothing reached the network", NET_CALLS == [], NET_CALLS)
print("\n%d/%d passed" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
