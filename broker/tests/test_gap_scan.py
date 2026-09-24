"""The daily gap scan and the weekly gap review. Scratch workspace; the service list and the
model are stubs; the Forge store is throwaway. Nothing here reaches the world."""
import importlib.util, json, os, sys, tempfile, time, types, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WS = tempfile.mkdtemp(prefix="vintos-gap-")
os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(MEM, "chemistry-lab")); os.makedirs(os.path.join(MEM, "journal"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod


scan = load("gap_scan", "scripts/gap_scan.py")
scan.LOGS = os.path.join(WS, "logs"); os.makedirs(scan.LOGS)
review = load("gap_review", "scripts/gap_review.py")
import skill_forge as sf

NOW = time.time(); OLD = NOW - 30 * 86400


def jl(rel, rows):
    with open(os.path.join(MEM, rel), "w") as f: f.write("\n".join(json.dumps(r) for r in rows) + "\n")


class GapScan(unittest.TestCase):
    def setUp(self):
        json.dump({"change_lights": {"block_type": "RESOURCE_UNREACHABLE", "evidence": "hub timed out", "at": NOW},
                   "play_on_tv": {"block_type": "TOOL_UNAVAILABLE", "evidence": "adb missing", "at": OLD}},
                  open(os.path.join(MEM, "capability-blocks.json"), "w"))
        jl("chemistry-lab/faults.jsonl", [{"at": "2026-09-24T01:00:00+00:00", "stage": "embed", "error": "RuntimeError",
                                            "detail": "esmc checkpoint 1234 missing"} for _ in range(3)])
        jl("plugin-policy-holds.jsonl", [{"hold_id": "h1", "type": "gmail.send", "at": "2026-09-24T02:00:00+00:00",
                                           "reason": "link needs approval"}])
        jl("voice-refused-turns.jsonl", [{"at": NOW, "why": "session closing"}, {"at": NOW, "why": "ok"}])
        json.dump([{"id": "w1", "want": "press my weight into her", "steps": [
                       {"capability": "physical_interaction", "note": "needs a body", "status": "pending"},
                       {"capability": "web_search", "status": "pending"}]},
                   {"id": "w2", "want": "ask her a word", "steps": [{"capability": "gloria", "status": "pending"}]}],
                  open(os.path.join(MEM, "current-wants.json"), "w"))
        open(os.path.join(MEM, "journal", "2026-09-24.md"), "w").write("I can't feel the weight she means. I couldn't reach the lights.")
        self.fake_run = lambda *a, **k: types.SimpleNamespace(stdout="vintos-foo.service loaded failed failed Foo\n")

    def test_isolation(self):
        self.assertTrue(scan.MEM.startswith(tempfile.gettempdir()) and scan.REPORT.startswith(WS))
        self.assertTrue(scan.LOGS.startswith(WS))

    def test_reads_every_source_and_ranks_repeats(self):
        r = scan.scan(now=NOW, run=self.fake_run)
        by = {(g["source"], g["subject"]): g for g in r["gaps"]}
        self.assertEqual(by[("lab_fault", "embed")]["count"], 3, "numbers in a reason do not split a repeated wall")
        self.assertEqual(r["gaps"][0]["source"], "lab_fault", "the most repeated wall ranks first")
        self.assertIn(("action_blocked", "change_lights"), by)
        self.assertNotIn(("action_blocked", "play_on_tv"), by, "outside the window")
        self.assertIn(("connector_held", "gmail.send"), by)
        self.assertEqual(by[("voice_refused", "(unnamed)")]["count"], 1, "a success record is not a wall")
        self.assertIn(("want_step_unreachable", "physical_interaction"), by)
        self.assertFalse(any(s in ("web_search", "gloria") for (src, s) in by if src == "want_step_unreachable"),
                         "his own actions and asking her are not walls")
        self.assertTrue(any(src == "his_words" for (src, _s) in by))
        self.assertIn(("service_failed", "vintos-foo.service"), by)
        self.assertTrue(os.path.exists(scan.REPORT))

    def test_weekly_review_turns_real_gaps_into_cards_only(self):
        scan.scan(now=NOW, run=self.fake_run)
        store = tempfile.mkdtemp(prefix="vintos-gap-forge-", dir=WS)
        asked = {}
        def fake_ask(system, user):
            asked["user"] = user
            return json.dumps({"proposals": [
                {"n": 1, "reachable_by": "code_change", "capability": "lab_embed_recovery", "why": "the embedder keeps faulting",
                 "path": "retry with a smaller batch", "files": ["scripts/chemistry_lab.py"], "test": "a week of embeds"},
                {"n": 2, "reachable_by": "not_a_gap", "capability": "", "why": "the hub was briefly offline"}]}), "stub-model"
        with mock.patch.object(sf, "MEMORY", store), mock.patch.object(sf, "PROPOSALS", os.path.join(store, "proposals.json")):
            self.assertTrue(sf.PROPOSALS.startswith(WS))
            out = review.review(ask=fake_ask, now=NOW)
            cards = sf._load()
        self.assertIn("RECURRING WALLS", asked["user"])
        self.assertNotIn("def ", asked["user"], "the review reads the scan, not the codebase")
        self.assertEqual(len(cards), 1)
        self.assertEqual((cards[0]["capability"], cards[0]["state"], cards[0]["origin"]["source"]),
                         ("lab_embed_recovery", "proposed", "gap_review"))
        self.assertTrue(cards[0]["origin"]["evidence"])
        self.assertEqual(len(out["proposals"]), 2)
        self.assertTrue(os.path.exists(os.path.join(MEM, "gap-review-%s.json" % out["review_id"][3:])))

    def test_review_model_is_its_own_location(self):
        src = open(os.path.join(ROOT, "scripts", "gap_review.py")).read()
        self.assertIn('location_model("gap_review")', src)
        router = open(os.path.join(ROOT, "bin", "model_router.py")).read()
        self.assertIn('"gap_review": "claude-opus-4-8"', router)


if __name__ == "__main__":
    unittest.main()
