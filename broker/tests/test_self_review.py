#!/usr/bin/env python3
"""Constitutional and lifecycle tests for the Self-Review Organ."""
import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))


def load_module(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


SR = load_module("self_review_tested", "scripts/self_review.py")
SB = load_module("self_review_builder_tested", "scripts/self_review_builder.py")


class SelfReviewTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.mem = os.path.join(self.t.name, "memory")
        self.scripts = os.path.join(self.t.name, "scripts")
        os.makedirs(self.mem); os.makedirs(self.scripts)
        for mod in (SR, SB):
            mod.WS, mod.MEM = self.t.name, self.mem
        SR.SCRIPTS = self.scripts
        for name in ("EVENTS", "SIGNALS", "COLLISIONS", "INTERPRETATIONS", "PROPOSALS",
                     "DECISIONS", "CHANGES", "SURFACE", "STATE", "FAULTS", "EMBCACHE",
                     "CONFIG", "LOCK"):
            value = getattr(SR, name)
            setattr(SR, name, os.path.join(self.mem, os.path.basename(value)))
        for name in ("PROPOSALS", "DECISIONS", "BUILDS", "CHANGES", "BUILD_ROOT"):
            value = getattr(SB, name)
            setattr(SB, name, os.path.join(self.mem, os.path.basename(value)))
        SB.RUNTIME_MAP = os.path.join(self.mem, "self-review-runtime-map.json")

    def tearDown(self): self.t.cleanup()

    def write_events(self, rows):
        for row in rows: SR.append(SR.EVENTS, row)

    def event(self, eid, system, hours=0, root=None, may=True):
        return {"event_id": eid, "system": system, "root_id": root or system + ":" + eid,
                "occurred_at": (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(),
                "content_summary": "a sufficiently meaningful event about unfinished action " + eid,
                "may_witness": may, "evidence_standing": "eligible" if may else "ineligible"}

    def test_collision_requires_independent_cross_system_events_in_window(self):
        rows = [self.event("a", "dream"), self.event("b", "web_search"),
                self.event("same", "dream"), self.event("old", "music", hours=100)]
        self.write_events(rows)
        SR.embeddings = lambda texts, cap=None: {SR.digest(x, size=32): [1.0, 0.0] for x in texts}
        made, _ = SR.detect_collisions({})
        pairs = {x["pair_key"] for x in made}
        self.assertIn("a|b", pairs)
        self.assertNotIn("a|same", pairs)
        self.assertFalse(any("old" in x for x in pairs))

    def test_tactical_output_cannot_seed_collision(self):
        self.write_events([self.event("a", "dream"), self.event("b", "web_search", may=False)])
        SR.embeddings = lambda texts, cap=None: {SR.digest(x, size=32): [1.0] for x in texts}
        made, _ = SR.detect_collisions({})
        self.assertEqual(made, [])

    def test_embedding_failure_does_not_consume_event(self):
        self.write_events([self.event("a", "dream"), self.event("b", "web_search")])
        SR.embeddings = lambda texts, cap=None: {}
        _, state = SR.detect_collisions({})
        self.assertEqual(state.get("collision_event_ids"), [])

    def test_authority_is_effect_based_not_identity_keyword(self):
        internal = SR.authority_for(["identity_observation"])
        protected = SR.authority_for(["external_contact"])
        self.assertTrue(internal["self_authorization_required"])
        self.assertFalse(internal["gloria_approval_required"])
        self.assertTrue(protected["gloria_approval_required"])

    def test_trigger_requires_accumulation_not_elapsed_time(self):
        one = [{"stream": "collision", "independent_roots": ["a", "b"]}]
        self.assertFalse(SR._trigger(one))
        enough = one + [{"stream": "interpolation", "independent_roots": ["c"]},
                        {"stream": "collision", "independent_roots": ["d"]},
                        {"stream": "collision", "independent_roots": ["e"]}]
        self.assertTrue(SR._trigger(enough))

    def test_builder_refuses_protected_file_without_gloria(self):
        p = {"proposal_id": "p", "gloria_approval_required": False,
             "implementation_files": ["scripts/effect_gate.py"]}
        d = {"proposal_id": "p", "actor": "vintos", "action": "ADOPT", "decision_id": "d"}
        SB.append(SB.PROPOSALS, p); SB.append(SB.DECISIONS, d)
        with self.assertRaises(PermissionError): SB.build("p")

    def test_stranded_build_is_not_silently_complete(self):
        p = {"proposal_id": "p", "gloria_approval_required": False,
             "implementation_files": ["scripts/new_organ.py"]}
        d = {"proposal_id": "p", "actor": "vintos", "action": "ADOPT", "decision_id": "d"}
        SB.append(SB.PROPOSALS, p); SB.append(SB.DECISIONS, d)
        SB.append(SB.BUILDS, {"proposal_id": "p", "build_id": "b", "state": "started"})
        self.assertIn("p", SB.ready())

    def test_builder_understands_git_and_plain_diff_paths(self):
        git = "--- a/scripts/x.py\n+++ b/scripts/x.py\n@@ -1 +1 @@\n-a\n+b\n"
        plain = "--- scripts/x.py\n+++ scripts/x.py\n@@ -1 +1 @@\n-a\n+b\n"
        self.assertEqual(SB._patch_strip(git), 1)
        self.assertEqual(SB._patch_strip(plain), 0)
        self.assertEqual(SB._patch_paths(git), ["scripts/x.py"])

    def test_runtime_map_resolves_split_tree_but_cannot_escape(self):
        split = os.path.join(self.t.name, "split", "server.py")
        os.makedirs(os.path.dirname(split))
        with open(split, "w") as f: f.write("# live\n")
        # For this sandboxed test, make the split root one of the allowed roots.
        old_expand = SB.os.path.expanduser
        SB.os.path.expanduser = lambda p: os.path.join(self.t.name, "split") if p == "~/Vintos" else old_expand(p)
        try:
            with open(SB.RUNTIME_MAP, "w") as f:
                json.dump({"paths": {"bin/server.py": split}}, f)
            self.assertEqual(SB._live_path("bin/server.py"), os.path.realpath(split))
            with open(SB.RUNTIME_MAP, "w") as f:
                json.dump({"paths": {"bin/server.py": "/etc/passwd"}}, f)
            with self.assertRaises(PermissionError): SB._live_path("bin/server.py")
        finally:
            SB.os.path.expanduser = old_expand

    def test_continuous_service_and_visible_decision_door_are_wired(self):
        with open(os.path.join(ROOT, "broker/vintos-self-review.service")) as f: unit = f.read()
        with open(os.path.join(ROOT, "scripts/deploy-atelier.sh")) as f: deploy = f.read()
        with open(os.path.join(ROOT, "bin/server.py")) as f: server = f.read()
        with open(os.path.join(ROOT, "scripts/atelier-visit.py")) as f: visit = f.read()
        self.assertIn("self_review.py watch", unit)
        self.assertIn("Restart=always", unit)
        rw_line = next(x for x in unit.splitlines() if x.startswith("ReadWritePaths="))
        self.assertNotIn("workspace/bin", rw_line)
        self.assertIn("-%h/Vintos", unit)
        self.assertIn('restart "$REVIEW_UNIT_NAME"', deploy)
        self.assertIn("self-review-runtime-map.json", deploy)
        self.assertIn("PASS (exit 0)", deploy)
        self.assertIn('@app.get("/api/self-review")', server)
        self.assertIn('@app.post("/api/self-review/{proposal_id}/decision")', server)
        self.assertIn("self_review_block()", visit)


if __name__ == "__main__":
    unittest.main(verbosity=2)
