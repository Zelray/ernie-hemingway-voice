"""Counts may hold or fall; --update never raises an existing baseline."""
import argparse
import ast
import json
import re
import tomllib
import subprocess
import sys
from collections import Counter
from pathlib import Path

from accessibility import missing_labels
from quality_common import ROOT, code_lines, inventory, python_files

LEGACY = {
    "pipeline/02_pilot_generate.py", "pipeline/03_flatten_pilot.py",
    "pipeline/05_dress_rehearsal_flatten.py", "pipeline/07_acceptance_gate.py",
    "pipeline/09_assemble.py", "pipeline/bucket4_cadence_gate.py",
    "pipeline/bucket4_to_generate.py", "pipeline/gen_bucket1_requests.py",
    "pipeline/gen_bucket1_select.py", "pipeline/gen_bucket2.py",
    "pipeline/gen_bucket2_requests.py", "pipeline/gen_bucket3_farewell.py",
    "pipeline/gen_bucket3_sun.py", "pipeline/gen_bucket4.py",
    "pipeline/gen_bucket4_pool.py", "pipeline/gen_bucket4_select.py",
    "pipeline/hand_fix_bucket1.py", "pipeline/promote_bucket2.py",
    "pipeline/reserve_bucket1.py", "pipeline/show_bucket1_keepers.py",
}

BASELINE = ROOT / ".ratchet-baseline.json"
LINT_RULES = ("E401", "E402", "E702", "E741", "F401")


def internal_module_roots(files, paths):
    """Import roots exposed by maintained application/tool files on pytest's path."""
    roots = set()
    for name in files:
        file = Path(name)
        if file.parts[0] == "tests":
            continue
        for path in paths:
            try:
                relative = file.relative_to(path).with_suffix("")
            except ValueError:
                continue
            first = relative.parts[0]
            if first.isidentifier() and first != "__init__":
                roots.add(first)
    return roots


def validate_ruff(problems, root, files):
    """Validate linter input before any counters can trust it."""
    if not isinstance(problems, list):
        raise ValueError("Ruff returned no problem list")
    normalized = []
    for row in problems:
        if not isinstance(row, dict):
            raise ValueError("Ruff problem must be an object")
        code, filename, location = row.get("code"), row.get("filename"), row.get("location")
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z]+[0-9]+", code):
            raise ValueError("Ruff problem code must be a rule identifier")
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("Ruff problem filename must be a nonempty string")
        if not isinstance(location, dict) or any(
            type(location.get(key)) is not int or location[key] <= 0 for key in ("row", "column")
        ):
            raise ValueError("Ruff problem location must contain positive integer row and column")
        try:
            name = (root / filename).resolve().relative_to(root.resolve()).as_posix()
        except (ValueError, OSError) as error:
            raise ValueError("Ruff problem filename is outside the inventory root") from error
        if name not in files:
            raise ValueError(f"Ruff problem filename is not in the Python inventory: {name}")
        normalized.append(row | {"filename": name})
    return normalized


def resolved_name(node, aliases):
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return f"{resolved_name(node.value, aliases)}.{node.attr}"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def import_aliases(tree):
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = item.name if item.asname else item.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"
        elif isinstance(node, ast.Assign):
            value = resolved_name(node.value, aliases)
            for target in node.targets:
                if isinstance(target, ast.Name) and value:
                    aliases[target.id] = value
    return aliases


def child_count(node):
    """Count only child/DOM structure, not dataset or scored outcome lengths."""
    attributes = {"children", "child_nodes", "childNodes", "child_count", "childElementCount"}
    calls = {"getchildren", "query_selector_all", "querySelectorAll", "find_elements", "locator"}
    nodes = list(ast.walk(node))
    structural = any(
        isinstance(item, ast.Attribute) and item.attr in attributes
        or isinstance(item, ast.Name) and item.id in attributes
        or isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr in calls
        for item in nodes
    )
    count = any(
        isinstance(item, ast.Attribute) and item.attr in {"child_count", "childElementCount", "length"}
        or isinstance(item, ast.Call) and (
            isinstance(item.func, ast.Name) and item.func.id == "len"
            or isinstance(item.func, ast.Attribute) and item.func.attr == "count"
        ) for item in nodes
    )
    return structural and count


def existence_assertion(node):
    if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return existence_assertion(node.operand)
    if isinstance(node, ast.Compare):
        if any(isinstance(item, ast.Constant) and item.value is None for item in [node.left, *node.comparators]):
            return True
        return any(child_count(item) for item in [node.left, *node.comparators])
    return child_count(node)


def scan_tests(tree, roots, e2e=False):
    """Return source lines for quality violations without importing test/application code."""
    found = {"internal_mocks": [], "existence_assertions": [], "fixed_e2e_sleeps": []}
    aliases = import_aliases(tree)
    mock_calls = {"patch", "patch.object", "unittest.mock.patch", "unittest.mock.patch.object",
                  "monkeypatch.setattr", "pytest.MonkeyPatch.setattr"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call = resolved_name(node.func, aliases)
            if call in mock_calls:
                target = node.args[0] if node.args else next(
                    (item.value for item in node.keywords if item.arg == "target"), None)
                if target is not None and resolved_name(target, aliases).split(".")[0] in roots:
                    found["internal_mocks"].append(node.lineno)
            if e2e and call.split(".")[-1] in {"sleep", "wait_for_timeout"}:
                found["fixed_e2e_sleeps"].append(node.lineno)
        elif isinstance(node, ast.Assert) and existence_assertion(node.test):
            found["existence_assertions"].append(node.lineno)
    return found


def measurements(root=ROOT):
    files = python_files(root)
    result = subprocess.run([sys.executable, "-m", "ruff", "check", "--output-format=json", *files],
                            cwd=root, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise ValueError(f"Ruff could not run: {result.stderr}")
    problems = validate_ruff(json.loads(result.stdout), root, files)
    if (result.returncode == 0) != (not problems):
        raise ValueError("Ruff status disagrees with its problem list")
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    paths = config.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("pythonpath", ["."])
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        raise ValueError("pytest pythonpath must be a list of paths")
    roots = internal_module_roots(files, paths)
    counts = Counter(row["code"] for row in problems)
    out = {f"lint_{rule}": counts.get(rule, 0) for rule in sorted(set(LINT_RULES) | set(counts))}
    out.update(files_over_400=0, internal_mocks=0, existence_assertions=0, fixed_e2e_sleeps=0,
               new_file_lint=0, accessibility_labels=0)
    units = {key: [] for key in out}
    for row in problems:
        name = row["filename"]
        units[f"lint_{row['code']}"].append(f"{name}:{row['location']['row']}")
        if name not in LEGACY:
            out["new_file_lint"] += 1
            units["new_file_lint"].append(f"{name}:{row['location']['row']}")
    html = [p for p in inventory(root) if p.startswith("demo/") and p.endswith(".html")]
    if not html:
        raise ValueError("accessibility scan has no HTML files")
    for name in html:
        for line in missing_labels((root / name).read_text(encoding="utf-8")):
            out["accessibility_labels"] += 1
            units["accessibility_labels"].append(f"{name}:{line}")
    for name in files:
        text = (root / name).read_text(encoding="utf-8")
        if code_lines(text) > 400:
            out["files_over_400"] += 1
            units["files_over_400"].append(f"{name}:1 ({code_lines(text)} code lines)")
        if not name.startswith("tests/"):
            continue
        for key, lines in scan_tests(ast.parse(text), roots, name.startswith("tests/e2e/")).items():
            out[key] += len(lines)
            units[key].extend(f"{name}:{line}" for line in lines)
    tests = [name for name in files if name.startswith("tests/")]
    e2e = [name for name in tests if name.startswith("tests/e2e/")]
    coverage = " (no E2E coverage)" if not e2e else ""
    print(f"ratchet scanned {len(files)} Python files; {len(tests)} test files; "
          f"{len(e2e)} E2E files{coverage}; Ruff reported {len(problems)} problems")
    return out, units


def compare(current, baseline):
    for side, counters in (("current", current), ("baseline", baseline)):
        if not isinstance(counters, dict):
            raise ValueError(f"{side} counters must be an object")
        for name, value in counters.items():
            if not isinstance(name, str) or not name:
                raise ValueError(f"{side} counter names must be nonempty strings")
            if type(value) is not int or value < 0:
                raise ValueError(f"{name}: {side} must be a nonnegative whole number")
    failures = []
    for name in sorted(set(current) | set(baseline)):
        allowed = baseline.get(name, 0)
        if name not in baseline:
            failures.append(f"{name}: configured counter missing from baseline")
        elif name not in current:
            failures.append(f"{name}: baseline counter has no implementation")
        elif current[name] > allowed:
            failures.append(f"{name}: {allowed} allowed, {current[name]} found")
        elif allowed - current[name] > 5:
            failures.append(f"{name}: stale baseline {allowed}, found {current[name]}; run --update")
        elif current[name] < allowed:
            print(f"improved {name}: {allowed} -> {current[name]}; run --update")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    current, units = measurements()
    if not BASELINE.exists():
        raise ValueError("missing baseline; initial counts must be seeded in a reviewed change")
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    if not isinstance(baseline, dict) or not baseline:
        raise ValueError("baseline must be a nonempty object")
    failures = compare(current, baseline)
    if args.update:
        # A stale excess can be lowered, but rises and removed counters cannot.
        failures = [f for f in failures if ": stale baseline " not in f]
    for name, value in current.items():
        print(f"{name}: {value} / {baseline.get(name, 0)}")
        if args.details:
            for unit in units[name]:
                print(f"  {unit}")
    if failures:
        print("\n".join(failures))
        return 1
    if args.update:
        BASELINE.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    print("RATCHET PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"ratchet cannot run: {error}", file=sys.stderr)
        sys.exit(2)
