#!/usr/bin/env python3
"""The shim's local pool (Gloria 2026-11-05): a /pool/<task>/ call goes to the best model for the task on the
machine with room; when the pool can't place it, the task's old direct lane answers instead.

No network, no ssh, no ~/.vintos: room reports, model lists and urllib are faked; config is a tempdir.
"""
import os, sys, json, socket, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTD = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOTD, "bin"))
sys.path.insert(0, os.path.join(ROOTD, "scripts"))
TMP = tempfile.mkdtemp(prefix="shim-pool-")
os.environ["HOME"] = TMP
os.environ.pop("SPARK_WORKSPACE", None)
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic"
os.environ["XAI_API_KEY"] = "test-xai"

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:140]) if d else ""))

import local_pool as LP
import vintos_claude_shim as S
S.LOG = os.path.join(TMP, "shim.log"); S.USAGE_LOG = os.path.join(TMP, "usage.jsonl")
GiB = LP.GiB

CFG = os.path.join(TMP, "pool"); os.makedirs(CFG)
MACHINES = [
    {"name": "aegis", "ssh": None, "memory": "gpu", "reserve_bytes": 1 * GiB, "max_busy_percent": 85},
    {"name": "studio", "ssh": "studio", "memory": "unified", "reserve_bytes": 32 * GiB},
    {"name": "macbook", "ssh": "mb", "memory": "unified", "reserve_bytes": 8 * GiB},
    {"name": "imac", "ssh": "im", "memory": "unified", "reserve_bytes": 3 * GiB},
]
BACKENDS = [
    {"label": "aeon-12b", "machine": "aegis", "kind": "lmstudio", "model": S.AEGIS_GEMMA_MODEL, "url": "http://aegis/v1/chat/completions", "loaded_context": 32000},
    {"label": "aeon-12b", "machine": "studio", "kind": "llama", "model": "aeon-gemma-4-12b", "url": "http://studio:8840/v1/chat/completions", "loaded_context": 32768},
    {"label": "gemma-26b", "machine": "macbook", "kind": "lmstudio", "model": S.GEMMA_MODEL, "url": S.GEMMA_URL, "loaded_context": 32000},
    {"label": "e4b-duo", "machine": "imac", "kind": "llama", "model": "e4b-duo", "url": "http://imac:8840/v1/chat/completions", "loaded_context": 8192},
]
TASKS = {"quick": {"models": ["e4b-duo", "aeon-12b"]}, "aeon": {"models": ["aeon-12b"]},
         "subconscious": {"models": ["gemma-26b"]}, "general": {"models": ["aeon-12b", "gemma-26b"]}}
for name, obj in (("machines", MACHINES), ("backends", BACKENDS), ("tasks", TASKS)):
    json.dump(obj, open(os.path.join(CFG, name + ".json"), "w"))

ROOMS = {}
def room(free_gib, loaded=(), gpu=None):
    r = {"memory": {"available_bytes": int(free_gib * GiB)}, "lmstudio_loaded": list(loaded), "gpus": []}
    if gpu is not None: r["gpus"] = [{"free_bytes": int(gpu[0] * GiB), "busy_percent": gpu[1]}]
    return r
SERVING = {"http://studio:8840/v1/chat/completions": ["aeon-gemma-4-12b"], "http://imac:8840/v1/chat/completions": ["e4b-duo"]}

def fresh_pool(rooms):
    ROOMS.clear(); ROOMS.update(rooms)
    p = LP.Pool(config_dir=CFG, room_reader=lambda m: ROOMS.get(m["name"]), models_reader=lambda url: SERVING.get(url))
    p.refresh(); return p

ALL_ROOM = {"aegis": room(0, [S.AEGIS_GEMMA_MODEL], gpu=(6, 10)), "studio": room(60), "macbook": room(20, [S.GEMMA_MODEL]), "imac": room(7)}

print("--- choosing ---")
p = fresh_pool(ALL_ROOM)
bs, v = p.choose("quick", 2000)
check("quick: the iMac E4B first, then AEON at home on Aegis, then the Studio (more room doesn't jump the line)",
      [(b["label"], b["machine"]) for b in bs] == [("e4b-duo", "imac"), ("aeon-12b", "aegis"), ("aeon-12b", "studio")], bs)
bs, v = p.choose("quick", 10000)
check("a call bigger than the iMac's 8k context skips it", [b["machine"] for b in bs][:1] == ["aegis"]
      and any(x.get("reason") == "context too small" for x in v), v)
p = fresh_pool(dict(ALL_ROOM, aegis=room(0, [S.AEGIS_GEMMA_MODEL], gpu=(0.5, 10))))
check("AEON spills to the Studio only when Aegis has no room", [b["machine"] for b in p.choose("aeon", 100)[0]] == ["studio"])
p = fresh_pool(dict(ALL_ROOM, imac=room(2)))
bs, v = p.choose("quick", 100)
check("a machine under its reserve is skipped, not squeezed", "imac" not in [b["machine"] for b in bs]
      and any(x["machine"] == "imac" and x["reason"] == "too full or busy" for x in v), v)
p = fresh_pool(dict(ALL_ROOM, aegis=room(0, [S.AEGIS_GEMMA_MODEL], gpu=(6, 95))))
check("a busy Aegis GPU is skipped", "aegis" not in [b["machine"] for b in p.choose("aeon", 100)[0]])
p = fresh_pool(dict(ALL_ROOM, macbook=room(20, [])))
check("LM Studio listing a model that isn't loaded doesn't count (no JIT-load stacking)",
      p.choose("subconscious", 100)[0] == [])
p = fresh_pool(dict(ALL_ROOM, studio=None))
check("an unreachable machine is unavailable, not empty", "studio" not in [b["machine"] for b in p.choose("aeon", 100)[0]])
p = fresh_pool(ALL_ROOM)
check("unknown task -> nothing", p.choose("nope", 1)[0] == [])
p.at = time.time() - LP.STALE_S - 1
check("a stale reading -> nothing (fallback lane answers)", p.choose("quick", 1)[0] == [])
check("no config -> nothing", (lambda q: (q.refresh(), q.choose("quick", 1)[0])[1])(LP.Pool(config_dir=os.path.join(TMP, "none"))) == [])

print("--- the shim's chains ---")
check("/pool/quick -> pool, then Aegis AEON, then the 26B",
      S.provider_chain({}, "/pool/quick/v1/chat/completions") == ["pool:quick", "aegis_gemma", "gemma"])
check("/pool/subconscious falls back to the 26B only",
      S.provider_chain({}, "/pool/subconscious/v1/chat/completions") == ["pool:subconscious", "gemma"])
check("/gemma-aegis may spill to another AEON, then its old chain",
      S.provider_chain({}, "/gemma-aegis/v1/chat/completions") == ["pool:aeon", "aegis_gemma", "gemma", "xai"])
check("/gemma-aegis-local stays on Aegis only", S.provider_chain({}, "/gemma-aegis-local/v1/chat/completions") == ["aegis_gemma"])
check("pool paths are chat paths", S.pool_task("/pool/quick/v1/chat/completions") == "quick" and S.pool_task("/v1/chat/completions") is None
      and S.pool_task("/pool/") is None)

class _FakeHTTP:
    def __init__(self, body): self.status, self._b = 200, json.dumps(body).encode()
    def read(self): return self._b
CALLS = []
def fake(handlers):
    def _open(req, timeout=None):
        url = req.full_url; body = json.loads(req.data)
        CALLS.append((url, body))
        for key, h in handlers.items():
            if key in url:
                out = h(body)
                if isinstance(out, Exception): raise out
                return _FakeHTTP(out)
        raise AssertionError("unexpected url " + url)
    return _open
def oai(text, **msg): return lambda body: {"id": "c1", "model": body["model"], "choices": [{"message": dict({"role": "assistant", "content": text}, **msg), "finish_reason": "stop"}],
                                           "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}
AEGIS_OK = lambda body: {"model_instance_id": S.AEGIS_GEMMA_MODEL, "response_id": "a1", "output": [{"type": "message", "content": "from aegis"}],
                         "stats": {"input_tokens": 3, "total_output_tokens": 2, "reasoning_output_tokens": 0}}
def run(path, rooms, **handlers):
    S.POOL = fresh_pool(rooms); CALLS.clear(); S.urllib.request.urlopen = fake(handlers)
    s, h, b = S.handle_chat({"model": "x", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 50, "temperature": 0.2}, path)
    return s, h, json.loads(b)

print("--- answering ---")
s, h, b = run("/pool/quick/v1/chat/completions", ALL_ROOM, **{"imac:8840": oai("Nairobi")})
sent = CALLS[0][1]
check("quick goes to the iMac with its model forced and thinking off",
      s == 200 and CALLS[0][0] == "http://imac:8840/v1/chat/completions" and sent["model"] == "e4b-duo"
      and sent["chat_template_kwargs"] == {"enable_thinking": False} and b["choices"][0]["message"]["content"] == "Nairobi", (s, CALLS))
check("the reply says which machine answered", h.get("x-vintos-pool-machine") == "imac" and h["x-vintos-provider"] == "pool_imac", h)
check("sampling passes through", sent.get("temperature") == 0.2 and sent.get("max_tokens") == 50, sent)

s, h, b = run("/pool/quick/v1/chat/completions", dict(ALL_ROOM, aegis=room(0, [S.AEGIS_GEMMA_MODEL], gpu=(0.5, 10))),
              **{"imac:8840": oai("x", reasoning_content="thinking..."), "studio:8840": oai("from studio")})
check("a reply that thought breaks the contract; the next choice answers",
      s == 200 and h["x-vintos-pool-machine"] == "studio" and b["choices"][0]["message"]["content"] == "from studio", (s, h, b))

s, h, b = run("/pool/aeon/v1/chat/completions", dict(ALL_ROOM, studio=room(10)), **{"172.18.16.1": AEGIS_OK})
check("AEON on Aegis goes through its own native lane (thinking-off check kept)",
      s == 200 and h["x-vintos-provider"] == "aegis_gemma" and h["x-vintos-pool-machine"] == "aegis"
      and CALLS[0][1].get("reasoning") == "off", (s, h, CALLS[:1]))

s, h, b = run("/pool/quick/v1/chat/completions", {}, **{"172.18.16.1": AEGIS_OK})
check("pool has no reading -> the old Aegis lane answers", s == 200 and h["x-vintos-provider"] == "aegis_gemma"
      and "x-vintos-pool-machine" not in h, (s, h))

s, h, b = run("/pool/aeon/v1/chat/completions", dict(ALL_ROOM, studio=room(10)),
              **{"172.18.16.1": lambda body: socket.timeout("timed out"), "100.79.177.103": oai("from the 26b")})
check("Aegis timed out via the pool -> not resent on its old lane; the next lane answers",
      s == 200 and h["x-vintos-provider"] == "gemma" and sum("172.18.16.1" in u for u, _ in CALLS) == 1, (s, h, [u for u, _ in CALLS]))

s, h, b = run("/pool/subconscious/v1/chat/completions", ALL_ROOM, **{"100.79.177.103": oai("felt")})
check("subconscious stays on the 26B", s == 200 and h["x-vintos-provider"] == "gemma" and h["x-vintos-pool-machine"] == "macbook"
      and CALLS[0][1]["model"] == S.GEMMA_MODEL, (s, h))

s, h, b = run("/pool/quick/v1/chat/completions", ALL_ROOM, **{"imac:8840": lambda body: ConnectionRefusedError("refused"),
              "studio:8840": lambda body: ConnectionRefusedError("refused"), "172.18.16.1": lambda body: ConnectionRefusedError("refused"),
              "100.79.177.103": lambda body: ConnectionRefusedError("refused")})
check("everything down -> 502 naming the pool's tries, never 200 empty",
      s == 502 and "pool:" in json.dumps(b) and "e4b-duo@imac" in json.dumps(b), (s, b))

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
