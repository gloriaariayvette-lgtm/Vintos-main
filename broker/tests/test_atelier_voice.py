#!/usr/bin/env python3
"""The Atelier route uses Vintos's current Claude voice, then Astra."""
import importlib.util, os, sys, types, unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
spec = importlib.util.spec_from_file_location("atelier_voice_test", os.path.join(ROOT, "scripts", "atelier_voice.py"))
VOICE = importlib.util.module_from_spec(spec); spec.loader.exec_module(VOICE)


class VoiceTests(unittest.TestCase):
    def test_current_claude_voice_is_primary(self):
        calls = []
        async def claude(*a, **k): calls.append(("claude", k)); return "entered", ""
        async def sol(*a, **k): calls.append(("sol", k)); return "fallback", ""
        router = types.SimpleNamespace(current_claude_model=lambda: "opus-id", claude_draft=claude, sol_draft=sol)
        old = sys.modules.get("model_router"); sys.modules["model_router"] = router
        try: self.assertEqual(VOICE.ask("room", "door", 5), "entered")
        finally:
            if old is None: sys.modules.pop("model_router", None)
            else: sys.modules["model_router"] = old
        self.assertEqual(calls, [("claude", {"max_tokens": 128, "model": "opus-id"})])

    def test_empty_or_filtered_primary_falls_to_astra(self):
        calls = []
        async def claude(*a, **k): calls.append(("claude", k.get("model"))); return None, ""
        async def sol(*a, **k): calls.append(("sol", k.get("model"))); return "Astra kept the room", ""
        router = types.SimpleNamespace(current_claude_model=lambda: "opus-id", claude_draft=claude, sol_draft=sol)
        old = sys.modules.get("model_router"); sys.modules["model_router"] = router
        try: self.assertEqual(VOICE.ask("sealed", "work", 900), "Astra kept the room")
        finally:
            if old is None: sys.modules.pop("model_router", None)
            else: sys.modules["model_router"] = old
        self.assertEqual(calls, [("claude", "opus-id"), ("sol", VOICE.ASTRA_MODEL)])


if __name__ == "__main__": unittest.main(verbosity=2)
