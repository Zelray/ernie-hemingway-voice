"""Run changed tests on fork-point code, rejecting new tests that already pass."""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import quality_common
from test_reports import classify

NON_CODE = {".md", ".rst", ".txt", ".yml", ".yaml", ".json", ".jsonl"}
SKIP_TYPES = {"docs", "chore", "ci", "refactor", "build", "style", "test"}
GATE_TESTS = {"tests/test_instruction_gate.py", "tests/test_gate_tools.py", "tests/test_ratchet.py",
              "tests/test_pr_body.py", "tests/test_proven_red.py", "tests/test_report_verdicts.py",
              "tests/test_mutation_smoke.py"}


def git(*args, cwd):
    return subprocess.check_output(["git", *args], cwd=cwd)


def unit(name):
    p = Path(name)
    return p.suffix == ".py" and (p.name.startswith("test_") or p.name.endswith("_test.py"))


def gate(name):
    return name.startswith("scripts/") or name in GATE_TESTS


def support(name):
    return name.startswith("tests/") or Path(name).name == "conftest.py"


def source(name):
    return not (unit(name) or support(name) or name.startswith(("agents/", "docs/", ".github/", ".githooks/"))
                or Path(name).suffix in NON_CODE or name in {"Makefile", ".gitignore", ".gitattributes", "pyproject.toml"})


def pytest_report(root, name, report):
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONPATH": os.pathsep.join(
        str(root / p) for p in (".", "pipeline", "pipeline/eval", "scripts"))}
    # Head config is test support, but an inherited config must not turn on plugins.
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", name,
                             "--disable-plugin-autoload", f"--junitxml={report}"],
                            cwd=root, env=env, capture_output=True, text=True, timeout=120)
    if not report.exists() or result.returncode not in (0, 1, 2):
        raise ValueError(f"runner could not execute {name}: exit {result.returncode}\n{result.stdout}{result.stderr}")
    cases = list(ET.parse(report).iter("testcase"))
    if not cases:
        raise ValueError(f"runner measured no tests in {name}")
    return result, cases


def key(case):
    return case.get("classname", ""), case.get("name", "")


def warn(message):
    print(f"::warning::proven-red: {message}" if os.environ.get("GITHUB_ACTIONS") else f"proven-red warning: {message}")


def main(argv=None, repo=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("head")
    parser.add_argument("--title", default="")
    args = parser.parse_args(argv)
    repo = Path(repo) if repo is not None else Path(quality_common.ROOT)
    fork = git("merge-base", args.base, args.head, cwd=repo).decode().strip()
    changed = git("diff", "--name-only", f"{fork}..{args.head}", cwd=repo).decode().splitlines()
    live = git("diff", "--name-only", "--diff-filter=d", f"{fork}..{args.head}", cwd=repo).decode().splitlines()
    sources = [p for p in changed if source(p)]
    application_files = {name for revision in (fork, args.head)
                         for name in git("ls-tree", "-r", "--name-only", revision, cwd=repo).decode().splitlines()
                         if source(name) and not gate(name) and name.endswith(".py")}
    tests = [p for p in live if unit(p) and not gate(p)]
    print(f"proven-red inspected {len(changed)} changed paths, {len(sources)} source paths, {len(tests)} unit files")
    if not sources or all(gate(p) for p in sources):
        print("proven-red skipped: no application source changes; gates use scratch negative controls")
        return 0
    if not tests:
        title = args.title or git("log", "-1", "--format=%s", args.head, cwd=repo).decode().strip()
        kind = re.match(r"^([a-z]+)(?:\([^)]*\))?!?:", title)
        if kind and kind[1] in SKIP_TYPES:
            warn(f"unverified title type {kind[1]} bypasses proof; no changed unit tests")
            return 0
        print("proven-red failed: application source changed without a changed unit test")
        return 1
    with tempfile.TemporaryDirectory(prefix="ernie-proven-red-") as temp:
        head_root = Path(temp) / "head"
        git("worktree", "add", "--detach", "--quiet", str(head_root), args.head, cwd=repo)
        try:
            for index, name in enumerate(tests):
                result, cases = pytest_report(head_root, name, Path(temp) / f"control-{index}.xml")
                if result.returncode or any(c.find("skipped") is not None or c.find("error") is not None for c in cases):
                    raise ValueError(f"HEAD test control is not green: {name}\n{result.stdout}")
        finally:
            git("worktree", "remove", "--force", str(head_root), cwd=repo)
        root = Path(temp) / "old"
        git("worktree", "add", "--detach", "--quiet", str(root), fork, cwd=repo)
        try:
            old_names = {}
            for index, name in enumerate(tests):
                if (root / name).is_file():
                    result, cases = pytest_report(root, name, Path(temp) / f"old-{index}.xml")
                    if result.returncode or any(c.find("skipped") is not None or c.find("error") is not None for c in cases):
                        raise ValueError(f"fork-point control is not green: {name}\n{result.stdout}")
                    old_names[name] = {key(c) for c in cases}
                else:
                    old_names[name] = set()
            for name in live:
                if unit(name) or support(name) or name == "pyproject.toml":
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(git("show", f"{args.head}:{name}", cwd=repo))
            failures = []
            for index, name in enumerate(tests):
                result, cases = pytest_report(root, name, Path(temp) / f"head-{index}.xml")
                verdicts = [classify(node, application_files) for case in cases for node in case
                            if node.tag in {"failure", "error"}]
                assertions = verdicts.count("assertion")
                missing = verdicts.count("missing")
                print(f"{name}: {len(cases)} tests, {assertions} assertion failures, {missing} missing references")
                if "exception" in verdicts:
                    raise ValueError(f"test infrastructure error in {name}\n{result.stdout}")
                if result.returncode == 0:
                    failures.append(f"{name} passes on old code")
                for case in cases:
                    if key(case) not in old_names[name] and case.find("failure") is None and case.find("error") is None:
                        failures.append(f"{name}::{case.get('name')} is new but passes or skips on old code")
                if missing and not assertions:
                    warn(f"{name} goes red only on missing references; review its assertions")
            if failures:
                print("\n".join(failures))
                return 1
        finally:
            git("worktree", "remove", "--force", str(root), cwd=repo)
    print("PROVEN RED PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError, ET.ParseError) as error:
        print(f"proven-red cannot run: {error}", file=sys.stderr)
        sys.exit(2)
