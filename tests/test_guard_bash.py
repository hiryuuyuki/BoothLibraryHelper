# tests/test_guard_bash.py
# ============================================
# BoothLibraryHelper
# .claude/hooks/guard_bash.py の回帰テスト
# exit 2 = ブロック / exit 0 = 許可
# ============================================
import json
import subprocess
import sys
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "guard_bash.py"


def _run(command: str) -> int:
    p = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True,
        text=True,
    )
    return p.returncode


class TestGitHistoryOperationsBlocked(unittest.TestCase):
    def test_plain_forms(self):
        for cmd in [
            "git commit -m x",
            "git push origin main",
            "git merge main",
            "git rebase main",
            "git cherry-pick abc",
            "git reset --hard HEAD~1",
            "git clean -fd",
        ]:
            with self.subTest(cmd=cmd):
                self.assertEqual(_run(cmd), 2)

    def test_with_global_options(self):
        # git -C <worktree> などのグローバルオプションを前に付けてもすり抜けないこと
        for cmd in [
            "git -C ../blh-wt/x commit -m t",
            "git -C ../blh-wt/x push origin main",
            "git -C ../blh-wt/x reset --hard",
            "git -C ../blh-wt/x clean -fd",
            'git -C "/path with space/wt" push',
            "git -c user.name=a commit -m x",
            "git --no-pager push",
            "git --git-dir=/r/.git --work-tree=/r merge main",
            "git -C a -C b rebase main",
        ]:
            with self.subTest(cmd=cmd):
                self.assertEqual(_run(cmd), 2)


class TestReadOnlyGitAllowed(unittest.TestCase):
    def test_allowed(self):
        for cmd in [
            "git status",
            "git diff --stat",
            "git log --oneline",
            "git -C ../blh-wt/x diff",
            "git -C ../blh-wt/x log --oneline",
            "git -C /home/user/blh-wt/003 status",
            "git worktree add ../blh-wt/1 -b ai/1",
            "git worktree list",
        ]:
            with self.subTest(cmd=cmd):
                self.assertEqual(_run(cmd), 0)


class TestOtherRules(unittest.TestCase):
    def test_blocked(self):
        for cmd in ["rm -rf build", "pip install requests", "cat .env", "printenv", "git push --force"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(_run(cmd), 2)

    def test_allowed(self):
        for cmd in ["python -m pytest -q", "python -m compileall -q app", "ls .venv"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(_run(cmd), 0)

    def test_broken_input_is_blocked(self):
        p = subprocess.run([sys.executable, str(GUARD)], input="{not json", capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
