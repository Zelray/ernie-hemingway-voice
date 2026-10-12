"""Validate PR acceptance and feature-spec sections without evaluating their text."""
import os
import re
import sys


def section(body, heading):
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    match = re.search(rf"(?m)^##\s+{heading}\s*$", body)
    if not match:
        return ""
    rest = body[match.end():]
    return re.split(r"(?m)^##\s+", rest, maxsplit=1)[0].strip()


def check(title, body):
    errors = []
    if not section(body, "Acceptance"):
        errors.append("PR requires content in ## Acceptance (P1)")
    if re.match(r"^feat(?:\([^)]*\))?!?:", title) and not section(body, "Spec"):
        errors.append("feat PR requires content in ## Spec")
    return errors


if __name__ == "__main__":
    body = sys.stdin.read() if "--stdin" in sys.argv else os.environ.get("PR_BODY", "")
    errors = check(os.environ.get("PR_TITLE", ""), body)
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    print("PR BODY PASSED")
