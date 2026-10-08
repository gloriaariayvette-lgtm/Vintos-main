#!/usr/bin/env python3
"""No one thinks (Gloria, 2026-10-08: "No one is to have thinking on. Who is doing this??"), and his models are never
changed to get round it ("NEVER FUCKING CHANGE HIS MODEL").

Who was: model_router's claude_draft and Study chat asked for thinking outright ({"type": "adaptive"}); Sonnet 5 thinks
when a call does not say otherwise, and five direct calls did not; the relay sent "disabled" to every model but Fable,
which Opus 5.5 refuses. Opus 5.5 and Fable 5.x cannot be told not to think at all, so they are asked for the least.

Also "Why no cache?": his Slack passes are about seven minutes apart and the cache lasted five, so Opus 5.5 wrote
45,429 and 42,283 tokens to cache thirteen minutes apart and read none. Pure functions and source; nothing is sent."""
import os, re, socket, sys

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "bin")); sys.path.insert(0, os.path.join(REPO, "scripts"))
import gen_result as GR
import claude_cache as C
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

OFF = {"claude-opus-4-8": {"type": "disabled"}, "claude-sonnet-5": {"type": "disabled"},
       "claude-haiku-5-5": {"type": "disabled"}, "claude-sonnet-5-5": {"type": "between_tools"},
       "claude-opus-5-5": None, "claude-fable-5-1": None}
for m, want in OFF.items():
    check("%s: %s" % (m, want or "cannot be switched off"), GR.thinking_off(m) == want == C.thinking_off(m),
          (GR.thinking_off(m), C.thinking_off(m)))
for m in OFF:
    b = C.body(m, "rules", "hello", 1500, effort="medium")
    check("claude_cache to %s: thinking off, or effort low where it cannot be" % m,
          b.get("thinking") == OFF[m] if OFF[m] else ("thinking" not in b and b["output_config"] == {"effort": "low"}), b)
    g = GR.least_thinking({"model": m})
    check("the relay and router to %s: the same" % m,
          (g.get("thinking") == OFF[m]) if OFF[m] else (g.get("output_config") == {"effort": "low"} and "thinking" not in g), g)

check("the cache lasts an hour, longer than the gap between his Slack passes", C.CACHE == {"type": "ephemeral", "ttl": "1h"}
      and C.body("claude-opus-5-5", C.Prompt("x", ["rules", "now"]), "hi", 10)["system"][0]["cache_control"]["ttl"] == "1h")
check("an hour's cache write is priced at 2x input in the estimate",
      abs(C.cost({"model": "claude-opus-5-5", "in": 0, "cache_write": 1_000_000, "cache_read": 0, "out": 0}) - 8.0) < 1e-9)

src = {p: open(os.path.join(REPO, p)).read() for p in
       ("bin/model_router.py", "bin/study_chat.py", "bin/vintos_claude_shim.py", "bin/server.py", "bin/music-share.py",
        "scripts/browser_agent.py", "scripts/robot_core.py", "scripts/dot_channel.py")}
asks = [p for p, s in src.items() if re.search(r'"thinking"\s*:\s*\{\s*"type"\s*:\s*"(?:adaptive|enabled)"', s)]
check("nothing asks for thinking", not asks, asks)
check("router, Study chat and relay all go through least_thinking",
      src["bin/model_router.py"].count("GR.least_thinking(body)") == 2 and "least_thinking(body)" in src["bin/study_chat.py"]
      and "GR.least_thinking(body)" in src["bin/vintos_claude_shim.py"])
sonnet = re.findall(r'"model": (?:"claude-sonnet-5"|SONNET_MODEL), "max_tokens": [^,]+, "thinking": \{"type": "disabled"\}',
                    "".join(src[p] for p in ("bin/server.py", "bin/music-share.py", "scripts/browser_agent.py", "scripts/robot_core.py")))
check("the five direct Sonnet 5 calls tell it not to think", len(sonnet) == 5, len(sonnet))
check("his models are unchanged: the Opus 5.5 slot, the Slack opener, the chat default",
      '"opus55": "claude-opus-5-5"' in src["bin/model_router.py"] and 'CLAUDE_MODELS = {"claude": "claude-opus-4-8"' in src["bin/model_router.py"]
      and 'KICKOFF_MODEL = "claude-opus-5-5"' in src["scripts/dot_channel.py"])
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
