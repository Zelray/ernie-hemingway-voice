"""Static label lint for form controls; rendered interaction still needs review."""
from html.parser import HTMLParser


class Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.controls = []
        self.labels = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "label" and values.get("for"):
            self.labels.add(values["for"])
        if tag in {"input", "textarea", "select"} and values.get("type") != "hidden":
            self.controls.append((self.getpos()[0], values))


def missing_labels(text):
    parser = Controls()
    parser.feed(text)
    return [line for line, attrs in parser.controls
            if not (attrs.get("aria-label") or attrs.get("aria-labelledby") or attrs.get("id") in parser.labels)]
