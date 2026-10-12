"""Shared file inventory for gates; ignored local artifacts are never inputs."""
import ast
import io
import shutil
import subprocess
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = ("pipeline", "demo", "scripts", "tests")


def inventory(root=ROOT):
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root, capture_output=True, check=True,
    )
    files = sorted({p for p in result.stdout.decode().split("\0") if p})
    deleted = set(subprocess.check_output(["git", "diff", "--cached", "--name-only", "--diff-filter=D"], cwd=root, text=True, stderr=subprocess.PIPE).splitlines())
    missing = [p for p in files if not (root / p).is_file() and p not in deleted]
    if missing:
        raise ValueError(f"missing inventory inputs: {missing}")
    return [p for p in files if p not in deleted]


def copy_public(destination, directories, files=(), root=ROOT):
    """Copy only public inventory paths needed by an isolated gate control."""
    copied = []
    for name in inventory(root):
        if name.split("/")[0] not in directories and name not in files:
            continue
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
        copied.append(name)
    return copied


def python_files(root=ROOT):
    files = [p for p in inventory(root) if p.endswith(".py") and p.split("/")[0] in DOMAINS]
    if not files:
        raise ValueError("source inventory is empty")
    return files


def code_lines(text):
    tree = ast.parse(text)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            docs.update(range(node.lineno, node.end_lineno + 1))
    lines = set()
    ignored = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
               tokenize.DEDENT, tokenize.ENDMARKER, tokenize.ENCODING}
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type not in ignored:
            lines.update(range(token.start[0], token.end[0] + 1))
    return len(lines - docs)
