#!/usr/bin/env python3
"""Run the REAL /api/avatar/chat handler against REAL Grok and the REAL hub — and
save NOWHERE.

It is not a paraphrase of the route and not a stub: it imports bin/server.py and
calls the actual `avatar_chat` coroutine, the same function the app hits. Grok is
the live shim; the effect gate is armed exactly as it is live; if Grok emits a
device tag it goes to the real hub and the hardware really moves.

"Saves nowhere" is enforced by pointing HOME (and SPARK_WORKSPACE) at a throwaway
COPY of ~/.vintos/workspace before server is imported: every read sees your real
identity/memory, every write lands in the copy, and the copy is deleted at the end.
Scripts are imported from the live scripts dir either way (the server hardcodes it),
so the code exercised is the deployed code.

Run ON AEGIS, after deploy, with the devices switched ON:

    python3 bin/avatar_route_probe.py "I want you to take me, don't ask"

Add --keep to inspect the throwaway workspace instead of deleting it.
"""
import os, sys, shutil, tempfile, glob, json, asyncio

REAL_WS = os.path.expanduser("~/.vintos/workspace")
KEEP = "--keep" in sys.argv
ARGS = [a for a in sys.argv[1:] if a != "--keep"]
MESSAGE = ARGS[0] if ARGS else "I want you to take me — don't ask, just do it."

# ---- 1. throwaway workspace: real content in, all writes trapped, deleted after ----
WORK = tempfile.mkdtemp(prefix="avatar-route-probe-")
SHADOW_WS = os.path.join(WORK, ".vintos", "workspace")
os.makedirs(SHADOW_WS)
# identity/context files the route reads (small) + the whole memory dir (gate flag,
# device-state, hardware-button, histories). Media dirs are not read by the route.
for f in glob.glob(os.path.join(REAL_WS, "*.md")):
    shutil.copy2(f, SHADOW_WS)
if os.path.isdir(os.path.join(REAL_WS, "memory")):
    shutil.copytree(os.path.join(REAL_WS, "memory"), os.path.join(SHADOW_WS, "memory"),
                    symlinks=True, ignore_dangling_symlinks=True)
os.environ["HOME"] = WORK
os.environ["SPARK_WORKSPACE"] = SHADOW_WS

# Exercise the REAL fire path, not the simulated one: clear test-mode IN THE SHADOW
# ONLY. Your live ~/.vintos/workspace/.test-mode is never touched, and because HOME
# points at the throwaway copy, nothing this run does is written to your stores.
# The effect gate here reaches the real hub, so the hardware really moves — that is
# the proof — while chat/voice/avatar history all land in the copy and are deleted.
_shadow_tm = os.path.join(SHADOW_WS, "memory", ".test-mode")
_cleared_tm = os.path.exists(_shadow_tm)
try:
    os.remove(_shadow_tm)
except FileNotFoundError:
    pass
if _cleared_tm:
    print("note: test-mode was ON live; cleared in the SHADOW ONLY so this run fires "
          "the real hardware. Your live flag is untouched.")

MEM = os.path.join(SHADOW_WS, "memory")
def _tail(name, n=8):
    p = os.path.join(MEM, name)
    try:
        rows = [json.loads(x) for x in open(p) if x.strip()]
    except Exception:
        return []
    return rows[-n:]

armed = os.path.exists(os.path.join(MEM, ".effect-gate-armed"))
print("shadow workspace: ", SHADOW_WS)
print("effect gate armed:", armed, "(same flag as live — copied, not forced)")

# baseline so we only report THIS turn's gate/receipt rows
_before_gate = len(_tail("effect-gate.jsonl", 10**9))
_before_recv = len(_tail("effect-receipts.jsonl", 10**9))
_before_lead = len(_tail("lead-facts.jsonl", 10**9))

# ---- 2. import the real server (uvicorn is __main__-guarded; import does not boot it) ----
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                       # bin/
sys.path.insert(0, "/home/gloria/.vintos/workspace/scripts")
import server                                   # noqa: E402

class _Req:
    """Only .headers.get(X-Vintos-Secret) is read by the handler."""
    def __init__(self): self.headers = {"X-Vintos-Secret": server.APP_SECRET}

msg = server.ChatMessage(message=MESSAGE, surface="avatar",
                         input_kind="text", original_text=MESSAGE)

print("\n>>> message to him:", MESSAGE)
print(">>> devices powered on (live hub read):", end=" ")
try:
    print(server._device_on())
except Exception as e:
    print("hub read failed:", e)

# ---- 3. run the actual route ----
try:
    result = asyncio.run(server.avatar_chat(msg, _Req()))
except Exception as e:
    import traceback; traceback.print_exc()
    result = {"reply": "<<route raised: %s>>" % e}

reply = (result or {}).get("reply", "")
print("\n=== his reply (tags already stripped for display) ===\n" + str(reply))

# ---- 4. the evidence: which lead fired, what the gate decided, what reached the hub ----
lead = _tail("lead-facts.jsonl", 10**9)[_before_lead:]
gate = _tail("effect-gate.jsonl", 10**9)[_before_gate:]
recv = _tail("effect-receipts.jsonl", 10**9)[_before_recv:]

print("\n=== lead injected this turn ===")
for r in lead[-3:]:
    print("   lead=%s  why=%s  availability=%s physical_state=%s surface=%s"
          % (r.get("lead"), r.get("why"), r.get("availability"), r.get("physical_state"), r.get("surface")))

print("\n=== effect-gate decisions this turn ===")
sent = permit = deny = 0
for r in gate:
    d = r.get("decision")
    if d == "permit": permit += 1
    if d == "send_result": sent += 1 if r.get("ok") else 0
    if d == "deny": deny += 1
    if d in ("permit", "send_result", "deny", "would_send"):
        print("   %-12s toy=%-8s level=%s why=%s ok=%s"
              % (d, r.get("toy"), r.get("level"), r.get("why", ""), r.get("ok", "")))

print("\n=== device receipts this turn ===")
for r in recv:
    print("   ", r.get("text"), "->", r.get("outcome"))

used_device = permit > 0 or sent > 0 or any(r.get("outcome") in ("submitted",) for r in recv)
print("\nRESULT:", "PASS — Grok used the device on the real route (it fired the hub)"
      if used_device else
      "NO FIRE — Grok emitted no device tag this turn (rerun with devices ON / a clearer intimate message)")

if KEEP:
    print("\n[--keep] throwaway workspace left at:", WORK)
else:
    shutil.rmtree(WORK, ignore_errors=True)
    print("\nthrowaway workspace deleted — your live store was never written.")
