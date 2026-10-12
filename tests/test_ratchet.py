"""Negative controls for ratchet counts, lint inputs and static labels."""
import ast
import subprocess

import pytest

from accessibility import missing_labels
from ratchet import compare, internal_module_roots, measurements, scan_tests, validate_ruff


def test_static_label_lint_has_positive_and_negative_controls():
    assert missing_labels('<input id="x">') == [1]
    assert missing_labels('<label for="x">Name</label><input id="x">') == []
    assert missing_labels('<textarea aria-label="Text"></textarea>') == []


def test_ratchet_rejects_growth_deletion_and_stale_baselines():
    assert compare({"x": 2}, {"x": 1}) == ["x: 1 allowed, 2 found"]
    assert compare({}, {"x": 1}) == ["x: baseline counter has no implementation"]
    assert compare({"x": 0}, {"x": 6}) == ["x: stale baseline 6, found 0; run --update"]
    with pytest.raises(ValueError, match="nonnegative whole number"):
        compare({"x": 0}, {"x": True})
    assert compare({"x": 0}, {"x": 1}) == []
    assert compare({"x": 0}, {}) == ["x: configured counter missing from baseline"]


def test_internal_roots_follow_inventory_and_pytest_paths():
    files = ["pipeline/spine.py", "pipeline/eval/score_generations.py",
             "pipeline/09_assemble.py", "demo/server.py", "scripts/ratchet.py",
             "tests/test_pipeline.py"]
    assert internal_module_roots(files, [".", "pipeline", "pipeline/eval", "scripts"]) == {
        "pipeline", "spine", "eval", "score_generations", "demo", "scripts", "ratchet"}
    assert internal_module_roots(files, ["."]) == {"pipeline", "demo", "scripts"}


@pytest.mark.parametrize("source", [
    "patch('pipeline.spine.content_hash')",
    "patch('spine.content_hash')",
    "patch.object(spine, 'content_hash')",
    "monkeypatch.setattr('pipeline.spine.content_hash', replacement)",
    "monkeypatch.setattr(spine, 'content_hash', replacement)",
    "from unittest.mock import patch as replace\nreplace('score_generations.tally')",
    "import unittest.mock as mocks\nmocks.patch('demo.server.stream')",
    "from unittest.mock import patch as replace\nreplace.object(spine, 'content_hash')",
    "import pipeline.spine as data\npatch.object(data, 'content_hash')",
    "from pipeline import spine as data\nmonkeypatch.setattr(data, 'content_hash', replacement)",
    "from spine import SpanRegistry as Registry\npatch.object(Registry, 'claim')",
    "import pipeline.spine as data\nalias = data\npatch.object(alias, 'content_hash')",
    "replace = patch\nreplace(target='pipeline.spine.content_hash')",
    "monkeypatch.setattr(target=spine, name='content_hash', value=replacement)",
])
def test_internal_mock_negative_controls(source):
    found = scan_tests(ast.parse(source), {"pipeline", "spine", "score_generations", "demo"})
    assert found["internal_mocks"] == [len(source.splitlines())]


@pytest.mark.parametrize("source", [
    "patch('httpx.AsyncClient')", "patch.object(httpx, 'AsyncClient')",
    "monkeypatch.setattr('os.environ', {})", "monkeypatch.setattr(os, 'getenv', replacement)",
    "setattr(spine, 'attribute', value)", "thing.patch('spine.content_hash')",
    "thing.setattr(spine, 'content_hash', replacement)",
    "from external import spine as data\npatch.object(data, 'content_hash')",
])
def test_external_mock_and_ordinary_attribute_controls(source):
    assert scan_tests(ast.parse(source), {"pipeline", "spine"})["internal_mocks"] == []


@pytest.mark.parametrize("expression", [
    "result", "not result", "result is None", "result is not None", "None != result",
    "len(component.children) == 2", "len(children) > 0", "component.child_count == 2",
    "component.childElementCount == 2", "component.children.length == 2",
    "len(component.getchildren()) == 2", "component.children.count() == 2",
    "len(page.query_selector_all('div')) == 2", "page.locator('li').count() == 2",
    "len(component.children)", "not len(component.children)",
])
def test_existence_and_child_count_negative_controls(expression):
    assert scan_tests(ast.parse(f"assert {expression}"), set())["existence_assertions"] == [1]


@pytest.mark.parametrize("expression", [
    "len(records) == 2", "result['overall']['n'] == 1", "pairs == 1",
    "result['real_text']['n'] == 0", "result['imitation']['win'] == 1",
    "len(groups) == len(expected)", "len(actual) == len(expected) == 13",
    "isinstance(result, dict)", "result is True", "'CARDINAL' in hard", "1 in results",
    "text.count('word') == 2", "data.count() == 2",
])
def test_measured_outcome_assertions_are_not_existence_checks(expression):
    assert scan_tests(ast.parse(f"assert {expression}"), set())["existence_assertions"] == []


def test_e2e_sleep_controls():
    tree = ast.parse("import time as clock\nclock.sleep(1)\npage.wait_for_timeout(100)")
    assert scan_tests(tree, set(), e2e=True)["fixed_e2e_sleeps"] == [2, 3]
    assert scan_tests(tree, set())["fixed_e2e_sleeps"] == []


@pytest.mark.parametrize("bad", [None, True, -1, 1.5, "1"])
@pytest.mark.parametrize("side", ["current", "baseline"])
def test_ratchet_counts_require_nonnegative_integers(bad, side):
    current, baseline = {"x": 0}, {"x": 0}
    (current if side == "current" else baseline)["x"] = bad
    with pytest.raises(ValueError, match=f"{side} must be a nonnegative whole number"):
        compare(current, baseline)


def ruff_row(root):
    return {"code": "F401", "filename": str(root / "scripts/ratchet.py"),
            "location": {"row": 1, "column": 1}}


@pytest.mark.parametrize("change", [
    {"code": None}, {"code": ""}, {"code": 1}, {"code": "invalid"},
    {"filename": None}, {"filename": ""}, {"filename": "../outside.py"},
    {"filename": "scripts/not_in_inventory.py"},
    {"location": None}, {"location": {}}, {"location": {"row": True, "column": 1}},
    {"location": {"row": 0, "column": 1}}, {"location": {"row": "1", "column": 1}},
    {"location": {"row": 1, "column": -1}},
])
def test_ruff_schema_negative_controls(tmp_path, change):
    row = ruff_row(tmp_path) | change
    with pytest.raises(ValueError, match="Ruff"):
        validate_ruff([row], tmp_path, ["scripts/ratchet.py"])


@pytest.mark.parametrize("payload", [None, {}, [None], [1], [{}]])
def test_ruff_problem_list_negative_controls(tmp_path, payload):
    with pytest.raises(ValueError, match="Ruff"):
        validate_ruff(payload, tmp_path, ["scripts/ratchet.py"])


def test_ruff_accepts_absolute_and_relative_inventory_paths(tmp_path):
    row = ruff_row(tmp_path)
    relative = row | {"filename": "scripts/ratchet.py"}
    assert validate_ruff([row, relative], tmp_path, ["scripts/ratchet.py"]) == [relative, relative]
    assert validate_ruff([], tmp_path, ["scripts/ratchet.py"]) == []


def test_measurements_print_denominators_without_e2e(tmp_path, capsys):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for directory in ("scripts", "tests", "demo"):
        (tmp_path / directory).mkdir()
    (tmp_path / "scripts/helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests/test_value.py").write_text("assert VALUE == 1\n", encoding="utf-8")
    (tmp_path / "demo/index.html").write_text('<input aria-label="Name">', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = [".", "scripts"]\n', encoding="utf-8")
    counts, units = measurements(tmp_path)
    assert counts["existence_assertions"] == 0
    assert units["fixed_e2e_sleeps"] == []
    output = capsys.readouterr().out
    assert "1 test files; 0 E2E files (no E2E coverage)" in output
