#!/usr/bin/env python3
"""Humor learns from play and explicit ratings; Taste cannot punish by default."""
import importlib.util
import json
import os
import tempfile
import unittest
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    if "requests" not in sys.modules:
        sys.modules["requests"] = types.SimpleNamespace(post=lambda *a, **k: None)
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class HumorTasteTests(unittest.TestCase):
    def test_both_humor_practice_copies_obey_no_silence_verdict(self):
        for rel in ("scripts/humor-practice.py", "bin/humor-practice.py"):
            src = (ROOT / rel).read_text()
            self.assertNotIn("score = gloria_score if gloria_score is not None else 1", src)
            self.assertNotIn("Be brutal", src)
            self.assertNotIn("Most should be 2s and 3s", src)
            self.assertIn('d["reception"] = "ungraded"', src)
            self.assertIn('source="humor_app_rating"', src)

    def test_material_portfolio_allows_only_one_self_mismatch(self):
        hp = load("humor_practice_test", ROOT / "scripts/humor-practice.py")
        rows = ([{"material_kind": "self_mismatch", "signal": n / 10}
                 for n in range(9)] +
                [{"material_kind": "shared_play", "signal": .7},
                 {"material_kind": "wordplay", "signal": .6}])
        chosen = hp._balanced_moments(rows)
        self.assertLessEqual(sum(r["material_kind"] == "self_mismatch" for r in chosen), 1)
        self.assertEqual(sum(r["material_kind"] != "self_mismatch" for r in chosen), 2)

    def test_app_rating_can_arrive_after_self_review(self):
        hp = load("humor_practice_rating_test", ROOT / "scripts/humor-practice.py")
        with tempfile.TemporaryDirectory() as td:
            hp.DRAFTS_FILE = os.path.join(td, "drafts.json")
            hp.PROFILE_FILE = os.path.join(td, "profile.json")
            Path(hp.DRAFTS_FILE).write_text(json.dumps(
                {"drafts": [{"joke": "The moon filed a noise complaint."}]}))
            Path(hp.PROFILE_FILE).write_text(json.dumps(
                {"landed": [], "flopped": [], "gloria_ratings": []}))
            hp.llm = lambda *a, **k: "1. craft=4 delight=5 mechanism=absurdity note=keep the image"
            hp.review_drafts()
            row = json.loads(Path(hp.DRAFTS_FILE).read_text())["drafts"][0]
            self.assertEqual(row["reception"], "ungraded")
            self.assertTrue(row["self_reviewed"])
            profile = json.loads(Path(hp.PROFILE_FILE).read_text())
            profile["gloria_ratings"] = [{"joke": row["joke"], "gloria_rating": 5}]
            Path(hp.PROFILE_FILE).write_text(json.dumps(profile))
            hp.review_drafts()
            row = json.loads(Path(hp.DRAFTS_FILE).read_text())["drafts"][0]
            self.assertEqual(row["reception"], "landed")
            self.assertEqual(row["self_review"]["delight"], 5)

    def test_inferred_reaction_schema_accepts_old_and_new_rows(self):
        hr = load("humor_reaction_test", ROOT / "bin/humor_reaction.py")
        self.assertEqual(hr._reaction_key("old row"), "old row")
        self.assertEqual(hr._reaction_key({"act": "new row"}), "new row")

    def test_conversational_laughter_never_impersonates_app_rating(self):
        for rel in ("bin/server.py", "bin/merged_full_route.py"):
            src = (ROOT / rel).read_text()
            self.assertNotIn('_hp.setdefault("landed", []).append(_last_vintos)', src)
            self.assertIn('"evidence": "inferred_laughter"', src)
        server = (ROOT / "bin/server.py").read_text()
        self.assertNotIn('_humor["landed"]', server)
        self.assertIn('_humor.get("gloria_ratings", [])', server)

    def test_negative_taste_signal_does_not_move_attraction_center(self):
        tv = load("taste_vector_test", ROOT / "bin/taste-vector.py")
        with tempfile.TemporaryDirectory() as td:
            tv.TASTE_VECTOR_FILE = os.path.join(td, "taste-vector.json")
            initial = {"vector": [1.0, 0.0], "strength": .4, "coherence": .7,
                       "contradictions": [], "aversions": [], "signal_count": 1}
            Path(tv.TASTE_VECTOR_FILE).write_text(json.dumps(initial))
            tv.embed = lambda text: [0.0, 1.0]
            tv.update_from_signal("muddy compression", .6, positive=False)
            after = json.loads(Path(tv.TASTE_VECTOR_FILE).read_text())
            self.assertEqual(after["vector"], initial["vector"])
            self.assertEqual(after["aversions"][0]["text"], "muddy compression")

    def test_daily_taste_carry_excludes_dislikes(self):
        ts = load("taste_salience_test", ROOT / "scripts/taste_salience.py")
        with tempfile.TemporaryDirectory() as td:
            ts.SAL = os.path.join(td, "salience.json")
            Path(ts.SAL).write_text(json.dumps({
                "likes||warm brass": {"score": 2, "kind": "likes", "text": "warm brass"},
                "dislikes||mud": {"score": 3, "kind": "dislikes", "text": "mud"},
            }))
            block = ts.top_block()
            self.assertIn("warm brass", block)
            self.assertNotIn("mud", block)

    def test_reflection_writes_candidates_not_profile_identity(self):
        src = (ROOT / "bin/taste-reflection.py").read_text()
        self.assertIn('"state": "candidate"', src)
        self.assertIn('"may_shape_context": False', src)
        self.assertNotIn('_tr_tv_update(item', src)
        self.assertIn('humor_drafts.get("drafts", [])', src)

    def test_deploy_manifest_owns_every_changed_runtime(self):
        deploy = (ROOT / "scripts/deploy-atelier.sh").read_text()
        for name in ("humor-practice.py", "humor_detector.py", "humor_reaction.py", "merged_full_route.py",
                     "taste-reflection.py", "taste-vector.py", "taste_salience.py", "gloria-model-update.sh",
                     "joke_fermentation.py"):
            self.assertIn(name, deploy)


if __name__ == "__main__":
    unittest.main()
