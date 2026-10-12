"""Negative controls for PR acceptance and specification requirements."""
from pr_body_check import check


def test_pr_body_rejects_empty_comments_and_missing_feature_spec():
    assert check("fix: outcome", "## Acceptance\n<!-- fill -->") == ["PR requires content in ## Acceptance (P1)"]
    assert check("feat: outcome", "## Acceptance\nQuote the requested outcome.") == ["feat PR requires content in ## Spec"]
    assert check("feat: outcome", "## Acceptance\nOutcome\n## Spec\nSmall feature needs no separate spec.") == []
