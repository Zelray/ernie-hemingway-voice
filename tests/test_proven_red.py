"""Exercise proven-red decisions against real temporary git ranges."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.STDOUT).decode().strip()


def commit(root, title):
    git(root, "add", ".")
    git(root, "-c", "user.name=Gate fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", title)
    return git(root, "rev-parse", "HEAD")


def run_proof(root, base, head):
    # Invoke the module entry, selecting the repository through its supported parameter.
    code = ("import sys; from pathlib import Path; "
            f"sys.path.insert(0,{str(ROOT / 'scripts')!r}); import proven_red; "
            f"sys.exit(proven_red.main([{base!r},{head!r}], repo=Path({str(root)!r})))")
    return subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("mode,expected", [("red", 0), ("green", 1), ("mixed", 1), ("no_test", 1)])
def test_proven_red_real_git_range(tmp_path, mode, expected):
    git(tmp_path, "init", "-q")
    (tmp_path / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    base = commit(tmp_path, "feat: initial fixture")
    (tmp_path / "value.py").write_text("VALUE = 2\n", encoding="utf-8")
    if mode != "no_test":
        (tmp_path / "tests").mkdir()
        text = "from value import VALUE\n\ndef test_value():\n    assert VALUE > 0\n" if mode == "green" else "from value import VALUE\n\ndef test_value():\n    assert VALUE == 2\n"
        if mode == "mixed":
            text += "\ndef test_already_green():\n    assert VALUE > 0\n"
        (tmp_path / "tests/test_value.py").write_text(text, encoding="utf-8")
    head = commit(tmp_path, "fix: change value")
    result = run_proof(tmp_path, base, head)
    assert result.returncode == expected, result.stdout + result.stderr
    assert git(tmp_path, "worktree", "list", "--porcelain").count("worktree ") == 1


def test_framework_range_with_hook_attributes_skips_application_proof(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    base = commit(tmp_path, "feat: initial fixture")
    (tmp_path / ".gitattributes").write_text(".githooks/* text eol=lf\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_value.py").write_text(
        "from value import VALUE\n\ndef test_value():\n    assert VALUE == 1\n", encoding="utf-8")
    head = commit(tmp_path, "chore: add existing behavior checks and hook attributes")
    result = run_proof(tmp_path, base, head)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipped: no application source changes" in result.stdout


def test_characterization_of_unchanged_module_does_not_block_new_module_proof(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    base = commit(tmp_path, "feat: initial fixture")
    (tmp_path / "helper.py").write_text("HELPER = 2\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_value.py").write_text(
        "from value import VALUE\n\ndef test_value():\n    assert VALUE == 1\n", encoding="utf-8")
    (tmp_path / "tests/test_helper.py").write_text(
        "from helper import HELPER\n\ndef test_helper():\n    assert HELPER == 2\n", encoding="utf-8")
    head = commit(tmp_path, "feat: add helper")
    result = run_proof(tmp_path, base, head)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PROVEN RED PASSED" in result.stdout
    assert "test_value.py" in result.stdout


def test_new_module_without_importing_tests_still_fails_proof(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    base = commit(tmp_path, "feat: initial fixture")
    (tmp_path / "helper.py").write_text("HELPER = 2\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_value.py").write_text(
        "from value import VALUE\n\ndef test_value():\n    assert VALUE == 1\n", encoding="utf-8")
    head = commit(tmp_path, "feat: add helper")
    result = run_proof(tmp_path, base, head)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "without a changed unit test" in result.stdout
