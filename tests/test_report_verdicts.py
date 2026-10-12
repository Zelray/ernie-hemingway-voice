"""Negative controls for assertion proof and application-reference diagnostics."""
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROVEN_RED = ROOT / "scripts/proven_red.py"


def report_nodes(root, body):
    (root / "test_value.py").write_text(f"def test_value():\n    {body}\n", encoding="utf-8")
    report = root / "report.xml"
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "test_value.py",
                             "--disable-plugin-autoload", f"--junitxml={report}"],
                            cwd=root, capture_output=True, text=True, timeout=60)
    assert result.returncode == 1, result.stdout + result.stderr
    return [node for case in ET.parse(report).iter("testcase") for node in case
            if node.tag in {"failure", "error"}]


def test_report_accepts_an_actual_assertion(tmp_path):
    from test_reports import classify

    nodes = report_nodes(tmp_path, "assert 1 == 2")
    assert [classify(node) for node in nodes] == ["assertion"]


@pytest.mark.parametrize("body", [
    "raise ValueError('assert failed')",
    "assert int('invalid') == 2",
    "raise TypeError('AssertionError: assertion unavailable')",
    "raise RuntimeError('assert result')",
    "assert 1 / 0 == 2",
    "try:\n        assert False\n    except AssertionError as error:\n        raise RuntimeError('assert failed') from error",
    "assert False\n\ndef test_runtime():\n    raise ValueError('assert unavailable')",
])
def test_report_rejects_runtime_failures_even_with_assertion_text(tmp_path, body):
    from test_reports import classify

    nodes = report_nodes(tmp_path, body)
    expected = ["assertion", "exception"] if "def test_runtime" in body else ["exception"]
    assert [classify(node) for node in nodes] == expected


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.STDOUT).decode().strip()


def commit(root):
    git(root, "add", ".")
    git(root, "-c", "user.name=Report fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "fix: report fixture")
    return git(root, "rev-parse", "HEAD")


def proof(root, base, head):
    # Set ROOT before loading the real CLI, including its exit-2 exception handler.
    code = ("import runpy, sys; from pathlib import Path; "
            f"sys.path.insert(0, {str(ROOT / 'scripts')!r}); import quality_common; "
            f"quality_common.ROOT = Path({str(root)!r}); "
            f"sys.argv = ['proven_red', {base!r}, {head!r}]; "
            f"runpy.run_path({str(PROVEN_RED)!r}, run_name='__main__')")
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    return subprocess.run([sys.executable, "-c", code], cwd=root, env=env,
                          capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("old_source,new_source,test_source,expected,counts", [
    ("VALUE = 1\n", "VALUE = 2\n",
     "import value\n\ndef test_value():\n    assert value.VALUE == 2\n", 0, "1 assertion failures, 0 missing references"),
    ("def answer():\n    raise ValueError('assert result')\n", "def answer():\n    return 2\n",
     "import value\n\ndef test_value():\n    assert value.answer() == 2\n", 2, "0 assertion failures, 0 missing references"),
    ("def answer():\n    return int('invalid')\n", "def answer():\n    return 2\n",
     "import value\n\ndef test_value():\n    assert value.answer() == 2\n", 2, "0 assertion failures, 0 missing references"),
    ("VALUE = 1\n", "VALUE = 1\nFEATURE = 2\n",
     "import value\n\ndef test_value():\n    assert value.FEATURE == 2\n", 0, "0 assertion failures, 1 missing references"),
    ("VALUE = 1\n", "VALUE = 1\nFEATURE = 2\n",
     "from value import FEATURE\n\ndef test_value():\n    assert FEATURE == 2\n", 0, "0 assertion failures, 1 missing references"),
    ("def answer():\n    import absent_report_dependency\n    return 2\n", "def answer():\n    return 2\n",
     "import value\n\ndef test_value():\n    assert value.answer() == 2\n", 2, "0 assertion failures, 0 missing references"),
    ("import absent_report_dependency\nVALUE = 2\n", "VALUE = 2\n",
     "from value import VALUE\n\ndef test_value():\n    assert VALUE == 2\n", 2, "0 assertion failures, 0 missing references"),
    ("def answer():\n    return NEW_VALUE\n", "NEW_VALUE = 2\ndef answer():\n    return NEW_VALUE\n",
     "import value\n\ndef test_value():\n    assert value.answer() == 2\n", 0, "0 assertion failures, 1 missing references"),
    ("def answer():\n    raise ValueError('assert result')\nVALUE = 1\n", "def answer():\n    return 2\nVALUE = 2\n",
     "import value\n\ndef test_value():\n    assert value.VALUE == 2\n\ndef test_answer():\n    assert value.answer() == 2\n",
     2, "1 assertion failures, 0 missing references"),
])
def test_proven_red_classifies_real_pytest_reports(tmp_path, old_source, new_source,
                                                 test_source, expected, counts):
    git(tmp_path, "init", "-q")
    (tmp_path / "value.py").write_text(old_source, encoding="utf-8")
    base = commit(tmp_path)
    (tmp_path / "value.py").write_text(new_source, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_value.py").write_text(test_source, encoding="utf-8")
    head = commit(tmp_path)
    result = proof(tmp_path, base, head)
    output = result.stdout + result.stderr
    assert result.returncode == expected, output
    assert counts in output
    if expected == 0 and "1 missing references" in counts:
        assert "goes red only on missing references" in output
    if expected == 2:
        assert "test infrastructure error" in output
    assert git(tmp_path, "worktree", "list", "--porcelain").count("worktree ") == 1


def test_new_application_module_is_a_missing_reference(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    base = commit(tmp_path)
    (tmp_path / "feature.py").write_text("VALUE = 2\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_value.py").write_text(
        "from feature import VALUE\n\ndef test_value():\n    assert VALUE == 2\n", encoding="utf-8")
    head = commit(tmp_path)
    result = proof(tmp_path, base, head)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 assertion failures, 1 missing references" in result.stdout
    assert "goes red only on missing references" in result.stdout


@pytest.mark.parametrize("message,text,expected", [
    ("assert 1 == 2", "", "assertion"),
    ("AssertionError: expected two", "", "assertion"),
    ("RuntimeError: assert result", "", "exception"),
    ("ValueError: AssertionError", "", "exception"),
    ("collection failure", "E   ModuleNotFoundError: No module named 'external_dependency'", "exception"),
    ("AttributeError: module 'external_dependency' has no attribute 'FEATURE'", "", "exception"),
    ("ImportError: cannot import name 'FEATURE' from 'external_dependency'", "", "exception"),
    ("NameError: name 'FEATURE' is not defined", "tests/test_value.py:4: NameError", "exception"),
    ("AttributeError: 'NoneType' object has no attribute 'FEATURE'", "tests/test_value.py:4: AttributeError", "exception"),
    ("assert earlier", "E   AssertionError: earlier\nE   RuntimeError: assert result\ntests/test_value.py:4: RuntimeError", "exception"),
    ("collection failure", "E   AssertionError: earlier\nE   ModuleNotFoundError: No module named 'external_dependency'", "exception"),
    ("collection failure", "value.py:2: AssertionError\nE   RuntimeError: assert result", "exception"),
    ("failed on setup", "E   assert 1 == 2\ntests/test_value.py:2: AssertionError", "assertion"),
])
def test_report_classifier_uses_final_diagnostics(message, text, expected):
    from test_reports import classify

    node = ET.Element("failure", message=message)
    node.text = text
    assert classify(node, ["value.py"]) == expected


@pytest.mark.parametrize("tag,message,text", [
    ("failure", "AttributeError: module 'value' has no attribute 'FEATURE'", ""),
    ("failure", "ModuleNotFoundError: No module named 'feature'", ""),
    ("error", "collection failure", "E   ImportError: cannot import name 'FEATURE' from 'value' (value.py)"),
    ("error", "collection failure", "E   ModuleNotFoundError: No module named 'feature'"),
])
def test_report_classifier_checks_application_inventory(tag, message, text):
    from test_reports import classify

    node = ET.Element(tag, message=message)
    node.text = text
    assert classify(node, ["value.py", "feature.py"]) == "missing"
    assert classify(node, []) == "exception"


def test_setup_assertion_is_an_infrastructure_error():
    from test_reports import classify

    node = ET.Element("error", message='failed on setup with "assert 1 == 2"')
    node.text = "E   assert 1 == 2\ntests/test_value.py:2: AssertionError"
    assert classify(node) == "exception"
