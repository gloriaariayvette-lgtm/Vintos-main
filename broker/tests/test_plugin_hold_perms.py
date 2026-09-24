"""A plugin policy hold must not lock the shared memory folder. Scratch memory only; nothing is sent.

2026-09-24: recording a hold ran chmod 700 on memory/ itself, which cancelled the Atelier user's
granted access to .compute.lock and kept the Forge from starting."""
import importlib.util, os, stat, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MEM = tempfile.mkdtemp(prefix="vintos-hold-perms-")
os.environ["VINTOS_MEMORY"] = MEM
sys.path.insert(0, os.path.join(ROOT, "scripts"))
spec = importlib.util.spec_from_file_location("plugin_gateway_perms_test", os.path.join(ROOT, "scripts", "plugin_gateway.py"))
gw = importlib.util.module_from_spec(spec); spec.loader.exec_module(gw)


class HoldPermissions(unittest.TestCase):
    def test_recording_a_hold_leaves_the_memory_folder_as_it_was(self):
        self.assertTrue(gw.MEMORY.startswith(tempfile.gettempdir()), gw.MEMORY)
        os.chmod(MEM, 0o775)
        gw._policy_hold("LINK_APPROVAL_REQUIRED", "lab", "gmail", "gmail.send",
                        {"request_sha256": "a" * 64, "rules": [], "links": ["https://example.invalid"]})
        self.assertEqual(stat.S_IMODE(os.stat(MEM).st_mode), 0o775, "the shared folder was not re-permissioned")
        self.assertEqual(stat.S_IMODE(os.stat(gw._hold_path()).st_mode), 0o600, "the hold ledger itself stays private")


if __name__ == "__main__":
    unittest.main()
