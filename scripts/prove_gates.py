"""Prove installed gates reject scratch violations, then verify restored controls."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from quality_common import ROOT, inventory


def run(root, args, expected):
    result = subprocess.run([sys.executable, *args], cwd=root, capture_output=True,
                            text=True, encoding="utf-8", timeout=120)
    if result.returncode != expected:
        raise ValueError(f"{args}: expected exit {expected}, got {result.returncode}\n{result.stdout}{result.stderr}")
    return result.stdout


def main():
    # The tests use actual scratch Git ranges for proven-red and corrupted contracts.
    run(ROOT, ["-m", "pytest", "-q", "tests/test_ratchet.py", "tests/test_pr_body.py",
               "tests/test_proven_red.py", "tests/test_report_verdicts.py", "tests/test_instruction_gate.py"], 0)
    with tempfile.TemporaryDirectory(prefix="ernie-gate-proof-") as temp:
        root = Path(temp)
        for name in inventory():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, path)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        # Copy existing history without any remote or private branch data.
        subprocess.run(["git", "fetch", "--quiet", str(ROOT), "HEAD"], cwd=root, check=True)
        subprocess.run(["git", "reset", "--mixed", "FETCH_HEAD"], cwd=root, check=True, capture_output=True)
        control = ["-m", "pytest", "-q", "tests/test_instruction_gate.py::test_contract_names_and_fields"]
        run(root, control, 0)
        path = root / "AGENTS.project.md"
        original = path.read_text(encoding="utf-8")
        try:
            path.write_text(original.replace("`SpanRegistry`", "`InventedRegistry`"), encoding="utf-8")
            run(root, control, 1)
            run(root, ["scripts/gates.py"], 1)
            print("instruction gate and combined command rejected an invented contract symbol")
        finally:
            path.write_text(original, encoding="utf-8")
        run(root, control, 0)
        subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=root, check=True)
        hook = subprocess.run(["git", "hook", "run", "pre-commit"], cwd=root, capture_output=True, text=True)
        if hook.returncode or "RATCHET PASSED" not in hook.stdout + hook.stderr:
            raise ValueError(f"Git hook green control failed: {hook.stdout}{hook.stderr}")
        try:
            path.write_text(original.replace("`SpanRegistry`", "`InventedRegistry`"), encoding="utf-8")
            hook = subprocess.run(["git", "hook", "run", "pre-commit"], cwd=root, capture_output=True, text=True)
            if hook.returncode == 0 or "InventedRegistry" not in hook.stdout + hook.stderr:
                raise ValueError("Git hook did not reject the contract violation")
            print("Git pre-commit invocation rejected the contract violation")
        finally:
            path.write_text(original, encoding="utf-8")
        run(root, ["scripts/ratchet.py"], 0)
        violation = root / "pipeline/gate_violation.py"
        try:
            violation.write_text("import os, sys\n", encoding="utf-8")
            run(root, ["scripts/ratchet.py"], 1)
            run(root, ["scripts/ratchet.py", "--update"], 1)
            print("ratchet rejected new lint and refused to update a rise")
        finally:
            violation.unlink()
        run(root, ["scripts/ratchet.py"], 0)
        run(root, ["scripts/pr_body_check.py", "--stdin"], 1)
        print("PR body gate rejected an empty body; positive and comment-only controls passed")
        run(root, ["scripts/mutation_smoke.py"], 0)
        print("mutation smoke killed three logic changes with passing original controls")
    print("ALL NEGATIVE CONTROLS PASSED")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
