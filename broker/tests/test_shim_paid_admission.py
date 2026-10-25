#!/usr/bin/env python3
"""Paid calls through the shim count against the day's paid budget, like every other paid door.

The shim answered most of his organs' calls without ever reserving, so the daily cap covered a
small share of real calls. Now: each Anthropic or x.ai call reserves first; a spent budget holds
that provider and the chain moves on; a stage model_router already reserved is not counted twice;
a ledger that cannot record never silences him.

No network, no ~/.vintos: the provider POST is faked, HOME and the ledger are a tempdir.
"""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTD = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="shim-paid-")
os.environ["HOME"] = TMP
os.environ.pop("SPARK_WORKSPACE", None)
os.environ["VINTOS_PAID_PER_DAY"] = "2"
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
os.environ["XAI_API_KEY"] = "test-xai"
sys.path.insert(0, os.path.join(ROOTD, "scripts"))
sys.path.insert(0, os.path.join(ROOTD, "bin"))

def _no_network(*a, **k): raise AssertionError("no network in tests")
socket.socket.connect = _no_network

import compute_admission as CA
import vintos_claude_shim as S

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:110]) if d else ""))

check("the ledger is the suite's scratch, not his", os.path.realpath(CA._ledger()).startswith(os.path.realpath(TMP)), CA._ledger())

SENT = []
def fake_post(provider, url, body, headers, timeout, call):
    call.sent.add((provider, call.key)); SENT.append((provider, body))
    if provider == "anthropic":
        return 200, {"content": [{"type": "text", "text": "claude says"}], "stop_reason": "end_turn",
                     "model": body["model"], "usage": {"input_tokens": 3, "output_tokens": 2}}, None
    return 200, {"choices": [{"message": {"role": "assistant", "content": "grok says"}, "finish_reason": "stop"}],
                 "model": body.get("model", "grok")}, None
S._post_json = fake_post
S.USAGE_LOG = os.path.join(TMP, "usage.jsonl")

def ask(text, **extra):
    j = {"model": "grok-4.20-0309-non-reasoning", "max_tokens": 400,
         "messages": [{"role": "system", "content": "You are a test."}, {"role": "user", "content": text}]}
    j.update(extra)
    return S.run_chain(j, "/v1/chat/completions")

def reserved_rows(provider):
    return [r for r in CA._paid_rows() if r.get("stage") == "reserved" and r.get("provider") == provider
            and r.get("organ") == "vintos_claude_shim"]

res, _, _ = ask("one")
check("an Anthropic call through the shim reserves first", len(reserved_rows("anthropic")) == 1 and res["provider"] == "anthropic", res.get("provider"))
ask("two")
check("each call reserves once", len(reserved_rows("anthropic")) == 2)

SENT.clear()
res, stages, _ = ask("three")
check("a spent Anthropic budget holds Anthropic: nothing is sent to it", not any(p == "anthropic" for p, _ in SENT), [p for p, _ in SENT])
check("... and the chain moves on to the next provider, as for any refused provider", res is not None and res["provider"] == "xai", res and res.get("provider"))
held = [s for s in stages if s.get("provider") == "anthropic"]
check("... with the reason named", held and "paid budget" in held[0].get("reason", ""), held and held[0].get("reason"))
check("the x.ai call it moved to reserved too", len(reserved_rows("xai")) == 1)

SENT.clear()
before = len(reserved_rows("xai"))
res, _, _ = ask("router already reserved this grok stage", route="grok", paid_reserved=True)
check("a stage model_router already reserved is not counted a second time", len(reserved_rows("xai")) == before and res["provider"] == "xai")
check("... and the marker is not forwarded to x.ai", SENT and "paid_reserved" not in SENT[-1][1], SENT and list(SENT[-1][1]))

real_reserve = CA.reserve_paid
def broken(*a, **k): return False, "reservation could not be persisted: disk full"
CA.reserve_paid = broken
os.environ["VINTOS_PAID_PER_DAY"] = "400"; CA.PAID_PER_DAY = 400
SENT.clear()
res, _, _ = ask("ledger cannot record")
check("a ledger that cannot record does not silence him: the call proceeds", res is not None and res["provider"] == "anthropic", res and res.get("provider"))
CA.reserve_paid = real_reserve

src = open(os.path.join(ROOTD, "bin", "model_router.py")).read()
check("model_router marks its reserved grok stages for the shim", src.count("system_text, reserved=True)") == 2)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
