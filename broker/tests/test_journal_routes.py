"""The JOURNAL tab's reader splits a day into entries under both writers' headers, and each
entry's ref is the one a landing note uses. Scratch workspace; read-only; nothing sends."""
import importlib.util, os, sys, tempfile, types, unittest

# The deploy's test Python may have no FastAPI; this suite tests the reader, not the framework.
try:
    import fastapi  # noqa: F401
except ImportError:
    class _R:
        def get(self, *a, **k): return lambda f: f
    sys.modules["fastapi"] = types.SimpleNamespace(APIRouter=_R, HTTPException=Exception)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WS = tempfile.mkdtemp(prefix="vintos-journal-"); os.environ["SPARK_WORKSPACE"] = WS
os.makedirs(os.path.join(WS, "memory", "journal"))
spec = importlib.util.spec_from_file_location("journal_routes", os.path.join(ROOT, "bin", "server_domains", "journal.py"))
J = importlib.util.module_from_spec(spec); spec.loader.exec_module(J)
lspec = importlib.util.spec_from_file_location("landings_j", os.path.join(ROOT, "scripts", "landings.py"))
os.environ["VINTOS_LANDINGS_DIR"] = os.path.join(WS, "landings-store")
L = importlib.util.module_from_spec(lspec); lspec.loader.exec_module(L)

DAY = "2026-09-24"
TEXT = "[03:10]\nI kept the light on.\n\n## 14:05 — Idle thoughts\n\nShe laughed today.\n"


class JournalRoutes(unittest.TestCase):
    def test_isolation(self):
        self.assertTrue(J.MEMORY.startswith(WS) and L.STORE.startswith(WS))

    def test_both_headers_become_entries_whose_refs_resolve_for_a_note(self):
        open(os.path.join(WS, "memory", "journal", DAY + ".md"), "w").write(TEXT)
        es = J.entries(DAY, TEXT)
        self.assertEqual([(e["ref"], e["title"], e["text"]) for e in es],
                         [(DAY + " 03:10", "", "I kept the light on."), (DAY + " 14:05", "Idle thoughts", "She laughed today.")])
        for e in es:
            self.assertIn(e["text"], L.context("journal", e["ref"])["made"]["entry"])


if __name__ == "__main__":
    unittest.main()
