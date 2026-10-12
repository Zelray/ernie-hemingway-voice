"""Mutate isolated source copies; require assertion failures, then remove copies."""
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from quality_common import ROOT, copy_public
from test_reports import classify

MUTATIONS = [
    ("pipeline/spine.py", "if start < e and s < end:", "if False:", "tests/test_pipeline.py::test_existing_spine_outcomes"),
    ("pipeline/09_assemble.py", "NEAR_DUP_JACCARD = 0.60", "NEAR_DUP_JACCARD = 1.01", "tests/test_pipeline.py::test_near_twins_stay_in_one_holdout_group"),
    ("pipeline/eval/score_generations.py", 'outcome = "loss"          # COHERENCE GATE', 'outcome = "win"           # COHERENCE GATE', "tests/test_pipeline.py::test_incoherent_or_degenerate_winner_is_a_real_text_loss"),
]


def run_test(root, selector):
    report = root / "mutation.xml"
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", selector, f"--junitxml={report}"],
                            cwd=root, env=env, capture_output=True, text=True, timeout=60)
    if not report.is_file():
        raise ValueError(f"test runner produced no report: {result.stdout}{result.stderr}")
    cases = list(ET.parse(report).iter("testcase"))
    diagnostics = [node for case in cases for node in case if node.tag in {"failure", "error"}]
    failures = [node for node in diagnostics if classify(node) == "assertion"]
    if (len(failures) != len(diagnostics) or not cases or result.returncode not in (0, 1)
            or any(case.find("skipped") is not None for case in cases)):
        raise ValueError(f"test runner could not execute: {result.stdout}{result.stderr}")
    return result, failures


def main():
    with tempfile.TemporaryDirectory(prefix="ernie-mutation-") as temp:
        root = Path(temp)
        copy_public(root, ("pipeline", "tests", "scripts"), ("pyproject.toml",), root=ROOT)
        for name, before, after, selector in MUTATIONS:
            path = root / name
            original = path.read_text(encoding="utf-8")
            if original.count(before) != 1:
                raise ValueError(f"{name}: mutation anchor must occur exactly once")
            result, failures = run_test(root, selector)
            if result.returncode or failures:
                raise ValueError(f"{name}: unmutated control failed: {result.stdout}")
            try:
                path.write_text(original.replace(before, after), encoding="utf-8")
                result, failures = run_test(root, selector)
                if result.returncode != 1 or not failures:
                    raise ValueError(f"{name}: mutation survived or failed without an assertion: {result.stdout}")
                print(f"killed {name}: {len(failures)} assertion failure(s)")
            finally:
                path.write_text(original, encoding="utf-8")
    print(f"MUTATION SMOKE PASSED ({len(MUTATIONS)} mutations)")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError, ET.ParseError) as error:
        print(f"mutation smoke failed: {error}", file=sys.stderr)
        sys.exit(1)
