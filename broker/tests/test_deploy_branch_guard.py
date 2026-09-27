"""The deploy installs only the shared branch, exactly as pushed.

2026-09-26: three deploys from another agent's branch replaced a day of fixes on the main
branch without anyone noticing. A scratch repository and a scratch HOME; the deploy stops at
the guard, before it copies, installs or restarts anything.
"""
import os, shutil, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAIN = "claude/vintos-avatar-ui-redesign-br5lt4"


def git(cwd, *a):
    return subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True, check=True).stdout.strip()


class DeployBranchGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vintos-deploy-branch-")
        self.home = os.path.join(self.tmp, "home"); os.makedirs(self.home)
        origin = os.path.join(self.tmp, "origin.git")
        subprocess.run(["git", "init", "-q", "--bare", origin], check=True)
        self.repo = os.path.join(self.tmp, "repo")
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        git(self.repo, "config", "user.email", "t@example.com"); git(self.repo, "config", "user.name", "t")
        os.makedirs(os.path.join(self.repo, "scripts")); os.makedirs(os.path.join(self.repo, "broker"))
        open(os.path.join(self.repo, "broker", ".keep"), "w").close()
        shutil.copy(os.path.join(ROOT, "scripts", "deploy-atelier.sh"), os.path.join(self.repo, "scripts"))
        git(self.repo, "checkout", "-q", "-b", MAIN)
        git(self.repo, "add", "."); git(self.repo, "commit", "-q", "-m", "one")
        git(self.repo, "remote", "add", "origin", origin); git(self.repo, "push", "-q", "origin", MAIN)

    def deploy(self):
        env = dict(os.environ, HOME=self.home)
        for k in ("VINTOS_DEPLOY_BRANCH", "VINTOS_DEPLOY_ANY_BRANCH", "VINTOS_DEPLOY_ALLOW_DIRTY"): env.pop(k, None)
        return subprocess.run(["bash", os.path.join(self.repo, "scripts", "deploy-atelier.sh"), "--dry-run"],
                              capture_output=True, text=True, env=env, timeout=60)

    def test_isolation(self):
        self.assertTrue(self.repo.startswith(tempfile.gettempdir()) and self.home.startswith(tempfile.gettempdir()))

    def test_another_branch_is_refused(self):
        git(self.repo, "checkout", "-q", "-b", "codex/elsewhere")
        r = self.deploy()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("only '%s' is deployed" % MAIN, r.stderr)

    def test_unpushed_commits_are_refused(self):
        open(os.path.join(self.repo, "note.txt"), "w").write("x")
        git(self.repo, "add", "note.txt"); git(self.repo, "commit", "-q", "-m", "local only")
        r = self.deploy()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not exactly the pushed", r.stderr)

    def test_the_pushed_main_branch_passes_the_guard(self):
        r = self.deploy()
        self.assertIn("source is incomplete", r.stderr, "it got past the guard to the next check")
        self.assertNotIn("is deployed", r.stderr)
        self.assertNotIn("not exactly the pushed", r.stderr)


if __name__ == "__main__":
    unittest.main()
