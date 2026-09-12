#!/usr/bin/env python3
"""Want enrichment must not erase a generated candidate's admission evidence.

Scratch HOME only; provider calls and every optional writer are stubbed.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[2]
HOME = Path(tempfile.mkdtemp(prefix="vintos-want-enrichment-"))
os.environ["HOME"] = str(HOME)
MEMORY = HOME / ".vintos" / "workspace" / "memory"
MEMORY.mkdir(parents=True)

sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "emoclaw_utils_want_enrichment", ROOT / "scripts" / "emoclaw_utils.py"
)
EU = importlib.util.module_from_spec(spec)
spec.loader.exec_module(EU)


class _Reply:
    def __init__(self, content):
        self.content = content

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


class WantEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.response = ""

        def post(*args, **kwargs):
            self.calls.append((args, kwargs))
            return _Reply(self.response)

        self.old_requests = sys.modules.get("requests")
        sys.modules["requests"] = types.SimpleNamespace(post=post)
        self.old_optional = {}
        replacements = {
            "subconscious_context": types.SimpleNamespace(
                get_subconscious_context_compact=lambda: ""
            ),
            "emoclaw_pressure": types.SimpleNamespace(
                get_pressure_block=lambda **kwargs: ""
            ),
            "wants_meta": types.SimpleNamespace(consult=lambda *args: None),
            "similarity_gate": types.SimpleNamespace(check_want=lambda *args: None),
            "want_completion": types.SimpleNamespace(
                admit=lambda *args: {"state": "ADMIT"}
            ),
            "want_stance": types.SimpleNamespace(admit=lambda *args: None),
        }
        for name, module in replacements.items():
            self.old_optional[name] = sys.modules.get(name)
            sys.modules[name] = module

        EU.generate_steps = lambda *args, **kwargs: []
        EU.check_want_interference = lambda *args, **kwargs: None
        EU.nudge_emotions = lambda *args, **kwargs: None
        for path in MEMORY.glob("*want*.json"):
            path.unlink()

    def tearDown(self):
        if self.old_requests is None:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = self.old_requests
        for name, old in self.old_optional.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old

    def test_fenced_complete_object_parses_and_requests_room_to_finish(self):
        self.response = """```json
{"candidate_kind":"current_desire","present_pull":"make it now",\
"reasoning":"A {shape} kept returning.","self_interpretation":"It is mine.",\
"possible_approach":"Begin with one move."}
```"""
        enriched = EU.enrich_want(
            "I want to make the returning shape", source="web-search"
        )
        payload = self.calls[0][1]["json"]
        prompt = payload["messages"][-1]["content"]
        self.assertEqual(payload["max_tokens"], 600)
        self.assertLess(prompt.index("- candidate_kind:"), prompt.index("- reasoning:"))
        self.assertLess(prompt.index("- present_pull:"), prompt.index("- reasoning:"))
        self.assertEqual(enriched["candidate_kind"], "current_desire")
        self.assertEqual(enriched["present_pull"], "make it now")
        self.assertEqual(enriched["reasoning"], "A {shape} kept returning.")

    def test_incomplete_object_still_holds_instead_of_fabricating_a_pull(self):
        self.response = '{"candidate_kind":"current_desire","present_pull":"now"'
        enriched = EU.enrich_want("I want to try", source="web-search")
        self.assertEqual(enriched["candidate_kind"], "unknown")
        self.assertEqual(enriched["present_pull"], "")

    def test_generated_provenance_survives_empty_enrichment_fallback(self):
        want = EU.GeneratedWant(
            "I want to trace the blue shape",
            {
                "desire": "I want to trace the blue shape",
                "source_kind": "current_desire",
                "present_pull": "the shape pulls now",
                "source": "web-search",
            },
        )
        row = EU.express_want(
            want,
            source="web-search",
            candidate_kind="unknown",
            present_pull="",
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["admission_state"], "ADMIT_CURRENT_CANDIDATE")
        self.assertEqual(row["candidate_kind"], "current_desire")
        self.assertEqual(row["present_pull"], "the shape pulls now")
        self.assertFalse((MEMORY / "held-want-candidates.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
