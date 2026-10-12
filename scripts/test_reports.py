"""Classify pytest diagnostics without treating traceback source as proof."""
import re
from pathlib import PurePosixPath

FRAME = re.compile(r"^(.+\.py):\d+: ([\w.]+)(?::\s*(.*))?$")
DIAGNOSTIC = re.compile(r"^E\s+(.+)$")
EXCEPTION = re.compile(r"^([\w.]+)(?::\s*(.*))?$")
MISSING_MODULE = re.compile(r"^No module named ['\"]([^'\"]+)['\"]")
MISSING_IMPORT = re.compile(r"^cannot import name ['\"][^'\"]+['\"] from ['\"]([^'\"]+)['\"]")
MISSING_ATTRIBUTE = re.compile(r"^module ['\"]([^'\"]+)['\"] has no attribute ['\"][^'\"]+['\"]")
MISSING_NAME = re.compile(r"^name ['\"][^'\"]+['\"] is not defined$")


def final_diagnostic(node):
    """Prefer the last traceback frame, then its E line, then the summary."""
    lines = (node.text or "").splitlines()
    frames = [(index, match) for index, line in enumerate(lines)
              if (match := FRAME.fullmatch(line.strip()))]
    diagnostics = [(index, match[1]) for index, line in enumerate(lines)
                   if (match := DIAGNOSTIC.fullmatch(line.strip()))]
    if frames and (not diagnostics or frames[-1][0] > diagnostics[-1][0]):
        frame = frames[-1][1]
        # Pytest's frame has the exception type; the E line has its message.
        detail = diagnostics[-1][1] if diagnostics else node.get("message", "")
        match = EXCEPTION.fullmatch(detail.strip())
        message = match[2] if match and match[1] == frame[2] else frame[3]
        return frame[2], message or "", frame[1]
    detail = diagnostics[-1][1] if diagnostics else node.get("message", "")
    if detail.startswith("assert "):
        return "AssertionError", detail, ""
    match = EXCEPTION.fullmatch(detail.strip())
    return (match[1], match[2] or "", "") if match else ("", "", "")


def application_modules(files):
    """Include package paths and short imports used by the repo's PYTHONPATH."""
    modules = set()
    for name in files:
        parts = list(PurePosixPath(name).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        for index in range(len(parts)):
            modules.add(".".join(parts[index:]))
        # Directories can be namespace packages without __init__.py.
        for index in range(1, len(parts)):
            modules.add(".".join(parts[:index]))
    return modules


def application_frame(frame, files):
    frame = frame.replace("\\", "/")
    return any(frame == name or frame.endswith("/" + name) for name in files)


def classify(node, application_files=()):
    """Return assertion, missing application reference, or other exception."""
    kind, message, frame = final_diagnostic(node)
    if kind == "AssertionError":
        # Setup/teardown assertions are infrastructure failures, not test proof.
        return "assertion" if node.tag == "failure" else "exception"
    pattern = {"ModuleNotFoundError": MISSING_MODULE, "ImportError": MISSING_IMPORT,
               "AttributeError": MISSING_ATTRIBUTE}.get(kind)
    if pattern:
        match = pattern.match(message)
        if match and match[1] in application_modules(application_files):
            return "missing"
    if kind == "NameError" and MISSING_NAME.fullmatch(message) and application_frame(frame, application_files):
        return "missing"
    return "exception"
