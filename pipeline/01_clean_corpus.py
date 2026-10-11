"""
01_clean_corpus.py  —  Step 1 of the Hemingway data pipeline.

WHAT THIS DOES (plain English):
  Every raw file in this project came from Project Gutenberg. That means each
  one has a legal header at the top and a long license footer at the bottom,
  with the actual book sandwiched in between. This script throws away the
  header and footer and keeps only Hemingway's real words, saving a clean copy
  of each book into a `clean/` folder.

  It also prints a WORD count for each book. Word count (not line count) is the
  honest measure of how much Hemingway we actually have to train on, because
  different files wrap their lines differently.

WHERE IT RUNS:
  This is plain text processing — no GPU needed. It runs on your own machine in
  a couple of seconds once the terminal is working. We do NOT need the cloud for
  this step; the cloud is only for the training step later.

HOW TO RUN (once the terminal is alive again):
  python pipeline/01_clean_corpus.py
"""

from pathlib import Path

# The five public-domain works. (The Old Man and the Sea PDF is intentionally
# left out — it is still under copyright until 2048.)
RAW_FILES = [
    "the-sun-also-rises.txt",
    "farewell-to-arms.txt",
    "in-our-time.txt",
    "men-without-women.txt",
    "three-short-stories-and-ten-poems.txt",
]

# Project Gutenberg always brackets the real text with these two marker lines.
# We search for the text of the marker rather than hard-coding line numbers, so
# this same script will clean ANY Gutenberg book — handy when we later run the
# identical pipeline on a real client's writing.
START_MARKER = "*** START OF THE PROJECT GUTENBERG EBOOK"
END_MARKER = "*** END OF THE PROJECT GUTENBERG EBOOK"

PROJECT_DIR = Path(__file__).resolve().parent.parent   # the ~Hemingway folder
CLEAN_DIR = PROJECT_DIR / "clean"


def strip_gutenberg(text: str) -> str:
    """Return only the book — everything between the START and END markers."""
    lines = text.splitlines()

    start_index = None
    end_index = None
    for i, line in enumerate(lines):
        if START_MARKER in line:
            start_index = i + 1          # the book starts on the NEXT line
        elif END_MARKER in line:
            end_index = i                # the book ends just BEFORE this line
            break

    if start_index is None or end_index is None:
        raise ValueError("Could not find Project Gutenberg start/end markers.")

    body = lines[start_index:end_index]

    # Trim blank lines from the very top and bottom of what's left.
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()

    return "\n".join(body)


def main() -> None:
    CLEAN_DIR.mkdir(exist_ok=True)
    print(f"{'FILE':<42}{'WORDS':>10}")
    print("-" * 52)

    total_words = 0
    for name in RAW_FILES:
        raw_text = (PROJECT_DIR / name).read_text(encoding="utf-8")
        clean_text = strip_gutenberg(raw_text)

        word_count = len(clean_text.split())
        total_words += word_count

        out_path = CLEAN_DIR / name.replace(".txt", "_clean.txt")
        out_path.write_text(clean_text, encoding="utf-8")
        print(f"{name:<42}{word_count:>10,}")

    print("-" * 52)
    print(f"{'TOTAL':<42}{total_words:>10,}")
    print(f"\nClean files written to: {CLEAN_DIR}")


if __name__ == "__main__":
    main()
