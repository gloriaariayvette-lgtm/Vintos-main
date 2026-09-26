"""The knock's RETURN reaches that morning's visit, in his own words.

2026-09-23: at the knock he chose RETURN every day and said why; the broker kept only the
word, and the visit 25 minutes later met only the handoff note he had just rejected — so it
held again, for four days. The Atelier is Chat's: this checks Chat's carry (gate row ->
knock_block) end to end, and that no second writer overwrites it (a merge on 2026-09-26 left
two writers, the second in a format the visit cannot read). Scratch workspace; every request
is a stub.
"""
import importlib.util, os, tempfile, types, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


class Resp:
    def __init__(self, body): self.body = body
    def json(self): return self.body


class KnockReachesVisit(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp(prefix="vintos-knock-")
        os.makedirs(os.path.join(self.ws, "memory"))
        self.gate = load("atelier_gate_knock_test", "scripts/atelier-gate.py")
        self.visit = load("atelier_visit_knock_test", "scripts/atelier-visit.py")
        store = os.path.join(self.ws, "memory", ".atelier-knock.json")
        for mod in (self.gate, self.visit): mod.WSP = self.ws; mod.KNOCK_STORE = store
        self.sent = []

    def knock(self, answer):
        def post(url, json=None, **k):
            self.sent.append(url)
            if url.endswith("/door"): return Resp({"door": "dark", "why": "he left it held"})
            if url.endswith("/gate/knock"): return Resp({"ok": True, "note": "old note", "project": "p1", "table_since": "s"})
            if url.endswith("/gate/decide"): return Resp({"ok": True, "decision": json["decision"]})
            if url.endswith("/chat/completions"): return Resp({"choices": [{"message": {"content": answer}}]})
            raise AssertionError("unexpected send: " + url)
        self.gate.requests = types.SimpleNamespace(post=post)
        self.gate.voice = lambda: ""; self.gate._model = lambda: "stub"
        self.gate.main()

    def test_isolation(self):
        self.assertTrue(self.ws.startswith(tempfile.gettempdir()) and self.visit.KNOCK_STORE.startswith(self.ws))
        self.knock("RETURN. I need to see if there is still a pulse in the work.")
        self.assertTrue(all(u.startswith("http://127.0.0.1:") for u in self.sent))

    def test_return_words_reach_that_projects_visit(self):
        self.knock("RETURN. I need to see if there is still a pulse in the work.")
        block = self.visit.knock_block("p1")
        self.assertIn("still a pulse in the work", block)
        self.assertEqual(self.visit.knock_block("another-project"), "")

    def test_hold_is_not_carried(self):
        self.knock("HOLD. Not today.")
        self.assertEqual(self.visit.knock_block("p1"), "")

    def test_one_writer(self):
        src = open(os.path.join(ROOT, "scripts", "atelier-gate.py")).read()
        self.assertEqual(src.count(".atelier-knock.json"), 1, "only KNOCK_STORE names the file")


if __name__ == "__main__":
    unittest.main()
