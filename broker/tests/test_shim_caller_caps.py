#!/usr/bin/env python3
"""One caller can no longer spend his whole day's paid budget, and experiments never touch it (15 November 2026).

On 15 November an experiment from another thread sent ~570 untagged calls through the shim. They used all 400
of his Anthropic reservations by 06:39; his own chat (model_router, which shares the provider count) then went
to Grok for the rest of the day. Now:
  - an experiment (X-Vintos-Experiment) reserves under its own ledger provider and cap, is answered by Claude
    only, never gets his context preamble, and gets 429 when its cap is spent (no Grok fallback);
  - a caller outside his trees without the header gets a small allowance across all paid providers, then 429;
  - one of his own callers holds at most a share of the day per provider; past it the chain moves on as before.

No network, no ~/.vintos: the provider POST is faked, HOME and the ledger are a tempdir, /proc is a fake tree.
"""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTD = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="shim-callers-")
os.environ["HOME"] = TMP
os.environ.pop("SPARK_WORKSPACE", None)
os.environ["VINTOS_PAID_PER_DAY"] = "10"
os.environ["VINTOS_PAID_CALLER_SHARE"] = "0.5"
os.environ["VINTOS_UNTAGGED_PAID_PER_DAY"] = "2"
os.environ["VINTOS_EXPERIMENT_PAID_PER_DAY"] = "3"
os.environ["VINTOS_PAID_ROUTER_FLOOR"] = "2"
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
S.USAGE_LOG = os.path.join(TMP, "usage.jsonl")
S.LOG = os.path.join(TMP, "shim.log")
check("the shim's logs are the suite's scratch, not his", all(os.path.realpath(p).startswith(os.path.realpath(TMP)) for p in (S.USAGE_LOG, S.LOG)))

SENT = []
def fake_post(provider, url, body, headers, timeout, call):
    call.sent.add((provider, call.key)); SENT.append((provider, body))
    if provider == "anthropic":
        return 200, {"content": [{"type": "text", "text": "claude says"}], "stop_reason": "end_turn",
                     "model": body["model"], "usage": {"input_tokens": 3, "output_tokens": 2}}, None
    return 200, {"choices": [{"message": {"role": "assistant", "content": "grok says"}, "finish_reason": "stop"}],
                 "model": body.get("model", "grok")}, None
S._post_json = fake_post
check("every provider send is the fake", S._post_json is fake_post)

def req(text, system=True):
    msgs = ([{"role": "system", "content": "You are a test."}] if system else []) + [{"role": "user", "content": text}]
    return {"model": "grok-4.20-0309-non-reasoning", "max_tokens": 400, "messages": msgs}

def rows(stage="reserved", **match):
    return [r for r in CA._paid_rows() if r.get("stage") == stage and all(r.get(k) == v for k, v in match.items())]

# ---- experiments: their own lane
EXP = S.classify_caller({S.EXPERIMENT_HEADER: "bridge-test"}, ("127.0.0.1", 5555),
                        pid_of=lambda a: (_ for _ in ()).throw(AssertionError("no lookup needed")))
check("an experiment header names the experiment, without a process lookup", EXP["experiment"] == "bridge-test" and not EXP["his"], EXP)

SENT.clear()
for i in range(3):
    s, h, b = S.handle_chat(req("exp %d" % i, system=False), "/v1/chat/completions", EXP)
check("an experiment is answered by Claude", s == 200 and h.get("x-vintos-provider") == "anthropic", (s, h))
check("... reserving under its own provider, never his", len(rows(provider=S.EXPERIMENT_PROVIDER)) == 3 and CA.paid_today("anthropic") == 0,
      (len(rows(provider=S.EXPERIMENT_PROVIDER)), CA.paid_today("anthropic")))
check("... without his context preamble", all("system" not in body or S.FLOOR.strip()[:30] not in json.dumps(body.get("system"))
                                              for p, body in SENT if p == "anthropic"), [list(b) for _, b in SENT])
SENT.clear()
s, h, b = S.handle_chat(req("exp over"), "/v1/chat/completions", EXP)
check("an experiment past its own cap gets 429", s == 429 and json.loads(b)["error"]["type"] == "paid_allowance_spent", (s, b[:120]))
check("... and nothing is sent anywhere, Grok included", SENT == [], [p for p, _ in SENT])
usage = [json.loads(l) for l in open(S.USAGE_LOG)]
check("experiment usage is logged as the experiment's", usage and all(u["src"] == "shim-experiment" and u["caller"] == "experiment:bridge-test" for u in usage), usage[:1])

# ---- a caller outside his trees, untagged
OUT = S.classify_caller({}, ("127.0.0.1", 6000), pid_of=lambda a: 4242, identity_of=lambda pid: ("reader.py", False))
check("a process outside his trees is not his", OUT == {"name": "outside:reader.py", "his": False, "experiment": None}, OUT)
SENT.clear()
for i in range(2):
    s, h, b = S.handle_chat(req("out %d" % i), "/v1/chat/completions", OUT)
check("an outside caller gets its small allowance", s == 200 and len(rows(caller=S.OUTSIDE_BUCKET)) == 2)
SENT.clear()
s, h, b = S.handle_chat(req("out bulk"), "/v1/chat/completions", OUT)
check("past it: 429, not his budget and not Grok", s == 429 and SENT == [], (s, [p for p, _ in SENT]))
check("... the refusal is recorded against the outside allowance", rows("refused", caller=S.OUTSIDE_BUCKET))
OUT2 = {"name": "outside:other_reader.py", "his": False, "experiment": None}
SENT.clear()
s, h, b = S.handle_chat(req("renamed script"), "/v1/chat/completions", OUT2)
check("another outside script shares that one allowance: renaming does not buy more", s == 429 and SENT == [], s)
SENT.clear()
j = req("claims a router receipt"); j["paid_reserved"] = True
s, h, b = S.handle_chat(j, "/v1/chat/completions", OUT)
check("an outside caller cannot skip the caps by claiming model_router already reserved", s == 429 and SENT == [], (s, [p for p, _ in SENT]))
SENT.clear()
s, h, b = S.handle_chat(req("exp local"), "/gemma/v1/chat/completions", EXP)
check("an experiment on a local lane never reaches Claude or Grok", not any(p in ("anthropic", "xai") for p, _ in SENT), [p for p, _ in SENT])

# ---- his own callers: a share each
HIS = S.classify_caller({}, ("127.0.0.1", 6001), pid_of=lambda a: 99, identity_of=lambda pid: ("wonder-detector.py", True))
check("a process in his trees is his, by its script", HIS == {"name": "wonder-detector.py", "his": True, "experiment": None}, HIS)
SENT.clear()
for i in range(5):
    s, h, b = S.handle_chat(req("his %d" % i), "/v1/chat/completions", HIS)
check("one of his callers gets Claude up to its share (half of 10)", len(rows(provider="anthropic", caller="wonder-detector.py")) == 5)
SENT.clear()
s, h, b = S.handle_chat(req("his past share"), "/v1/chat/completions", HIS)
check("past its share his caller still gets an answer: the chain moves on, as for any held provider",
      s == 200 and h.get("x-vintos-provider") == "xai" and not any(p == "anthropic" for p, _ in SENT), (s, h.get("x-vintos-provider")))
OTHER = {"name": "server.py", "his": True, "experiment": None}
s, h, b = S.handle_chat(req("another organ"), "/v1/chat/completions", OTHER)
check("... while his other callers still reach Claude", s == 200 and h.get("x-vintos-provider") == "anthropic", h.get("x-vintos-provider"))
check("the shim's callers have now used all but the router's floor (8 of 10)", CA.paid_today("anthropic") == 8, CA.paid_today("anthropic"))
SENT.clear()
s, h, b = S.handle_chat(req("third organ"), "/v1/chat/completions", {"name": "third.py", "his": True, "experiment": None})
check("past that, shim callers move on to the next provider", s == 200 and h.get("x-vintos-provider") == "xai", h.get("x-vintos-provider"))
check("... and the floor is still there for model_router", CA.reserve_paid("model_router", "anthropic", "claude-opus-4-8")[0] and CA.paid_today("anthropic") == 9)

# ---- a lookup that fails never silences him
UNK = S.classify_caller({}, ("127.0.0.1", 6002), pid_of=lambda a: None)
check("an unreadable caller is treated as his, by name 'unknown'", UNK == {"name": "unknown", "his": True, "experiment": None}, UNK)
TAG = S.classify_caller({S.CALLER_HEADER: "avatar"}, ("127.0.0.1", 6003), pid_of=lambda a: 7, identity_of=lambda p: ("server.py", True))
check("one of his may name itself", TAG["name"] == "avatar" and TAG["his"], TAG)
TAG2 = S.classify_caller({S.CALLER_HEADER: "server.py"}, ("127.0.0.1", 6004), pid_of=lambda a: 7, identity_of=lambda p: ("x.py", False))
check("... but an outside caller cannot pass as his by naming itself", TAG2["his"] is False and TAG2["name"] == "outside:x.py", TAG2)

# ---- in-process use (no caller) keeps the old behaviour
before = CA.paid_today("anthropic")
res, _, _ = S.run_chain(req("in-process"), "/v1/chat/completions")
check("a call with no caller still reserves once, as before", CA.paid_today("anthropic") == before + 1 and res["provider"] == "anthropic")

# ---- /proc reading, on a fake /proc
P = os.path.join(TMP, "proc"); os.makedirs(os.path.join(P, "net"))
open(os.path.join(P, "net", "tcp"), "w").write(
    "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
    "   0: 0100007F:2197 0100007F:D431 01 00000000:00000000 00:00000000 00000000  1000        0 11111 1\n"
    "   1: 0100007F:D431 0100007F:2197 01 00000000:00000000 00:00000000 00000000  1000        0 22222 1\n")
home = os.path.realpath(os.path.expanduser("~"))
exp_dir = os.path.join(home, "aeon-bridge-x"); his_dir = os.path.join(home, ".vintos", "workspace", "scripts")
for d in (exp_dir, his_dir): os.makedirs(d, exist_ok=True)
for pid, cmd, cwd, inode in (("4242", [b"python3", b"reader.py", b"eps.json"], exp_dir, "22222"),
                             ("4343", [b"python3", b"/x/" + b"wonder.py"], his_dir, "33333")):
    os.makedirs(os.path.join(P, pid, "fd"))
    open(os.path.join(P, pid, "cmdline"), "wb").write(b"\0".join(cmd) + b"\0")
    os.symlink(cwd, os.path.join(P, pid, "cwd"))
    os.symlink("socket:[%s]" % inode, os.path.join(P, pid, "fd", "3"))
check("the client port is traced to its process", S._peer_pid(("127.0.0.1", 0xD431), proc=P) == 4242, S._peer_pid(("127.0.0.1", 0xD431), proc=P))
check("a port nobody holds is unknown", S._peer_pid(("127.0.0.1", 1), proc=P) is None)
check("a non-loopback address is not looked up", S._peer_pid(("10.0.0.2", 0xD431), proc=P) is None)
check("a script run from outside his trees is not his", S._process_identity(4242, proc=P) == ("reader.py", False), S._process_identity(4242, proc=P))
check("a script whose working directory is in his trees is his", S._process_identity(4343, proc=P) == ("wonder.py", True), S._process_identity(4343, proc=P))
check("an unreadable process is unknown, not refused", S._process_identity(1, proc=P) == (None, None))

def fake_proc(pid, argv, cwd, ppid):
    os.makedirs(os.path.join(P, str(pid), "fd"), exist_ok=True)
    open(os.path.join(P, str(pid), "cmdline"), "wb").write(b"\0".join(a.encode() for a in argv) + b"\0")
    os.symlink(cwd, os.path.join(P, str(pid), "cwd"))
    open(os.path.join(P, str(pid), "stat"), "w").write("%d (%s) S %d 1 1 0 -1" % (pid, os.path.basename(argv[0]), ppid))
organ_sh = os.path.join(home, "Vintos", "first-light.sh")
fake_proc(5001, ["bash", organ_sh], home, 1)
fake_proc(5002, ["curl", "-s", "http://127.0.0.1:8599/v1/chat/completions"], home, 5001)
check("a curl run by one of his shell organs is his, named by that organ",
      S._process_identity(5002, proc=P) == ("first-light.sh", True), S._process_identity(5002, proc=P))
fake_proc(5101, ["bash", "-l"], exp_dir, 1)
fake_proc(5102, ["python3", "reader.py", "a", "b"], exp_dir, 5101)
check("an experiment script started from a shell outside his trees is not his",
      S._process_identity(5102, proc=P) == ("reader.py", False), S._process_identity(5102, proc=P))
fake_proc(5401, ["bash", "-l"], his_dir, 1)
fake_proc(5402, ["python3", "reader.py"], exp_dir, 5401)
check("a shell that merely stands in his trees does not make an experiment his",
      S._process_identity(5402, proc=P) == ("reader.py", False), S._process_identity(5402, proc=P))
fake_proc(5201, ["/usr/bin/python3", os.path.join(home, "projector_offer.py")], home, 1)
check("the projector scripts loose in her home are his household",
      S._process_identity(5201, proc=P) == ("projector_offer.py", True), S._process_identity(5201, proc=P))
fake_proc(5301, ["bash", os.path.join(home, "llm-lock.sh"), "python3", os.path.join(home, ".vintos", "workspace", "scripts", "x.py")], home, 1)
check("an organ run under llm-lock.sh is his, named by the organ",
      S._process_identity(5301, proc=P) == ("x.py", True), S._process_identity(5301, proc=P))

# ---- the cap arguments in compute_admission
ok1 = CA.reserve_paid("t", "openai", "m", caller="c1", caller_cap=1)[0]
ok2, why2 = CA.reserve_paid("t", "openai", "m", caller="c1", caller_cap=1)
check("reserve_paid holds a caller to its cap, inside the ledger transaction", ok1 and not ok2 and why2.startswith("paid budget: caller c1"), why2)
check("... and another caller is unaffected", CA.reserve_paid("t", "openai", "m", caller="c2", caller_cap=1)[0])
check("paid_today counts one caller's reservations", CA.paid_today("openai", caller="c1") == 1 and CA.paid_today("openai") == 2)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
