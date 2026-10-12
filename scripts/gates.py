"""Portable full verification command, also exposed as make gates."""
import ast
import subprocess
import sys

from quality_common import ROOT, python_files


def main():
    for args in (("-m", "pytest", "-q", "-s"), ("scripts/ratchet.py",), ("scripts/mutation_smoke.py",)):
        result = subprocess.run([sys.executable, *args], cwd=ROOT)
        if result.returncode:
            return result.returncode
    files = python_files()
    for name in files:
        ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)
    print(f"syntax: {len(files)} maintained Python files parsed")
    print("ALL REPOSITORY GATES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
