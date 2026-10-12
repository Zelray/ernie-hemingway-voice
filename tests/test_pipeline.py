"""Offline outcome tests of dataset integrity, rhythm, and evaluation."""
import importlib.util
from pathlib import Path

import pytest

import spine
import stylometry
from bucket4_cadence_gate import cadence_check
from fidelity_gate import fidelity_gate
from score_generations import ab_assignment, score_capability, tally

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("assemble", ROOT / "pipeline/09_assemble.py")
assemble = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assemble)


def test_existing_spine_outcomes():
    spine._smoke_test()


def test_existing_sentence_metrics():
    stylometry._smoke_test()


def test_cadence_rejects_both_extremes_and_accepts_measured_reference():
    choppy = "It was good. The coffee was hot. He was tired. The road was long. She left. The end."
    flowing = ("When the morning came and the light was on the water and the boats were "
               "moving out past the breakwater into the long grey swell of the sea, he "
               "thought that perhaps it would be a fine day after all and that the fish "
               "would be running and the nets would come back heavy and silver and full.")
    good = ("Start slow. Run in the morning when the streets are empty and the air is cold "
            "in your chest, and do not run far the first day or the second. Walk when you have "
            "to walk. Your legs will hurt and that is all right. Go out the next day and the "
            "day after, and after a while the running is easy and good and you do not think "
            "about it any more.")
    assert "too_choppy_mean" in cadence_check(choppy)[1]
    assert "too_flowery_mean" in cadence_check(flowing)[1]
    assert cadence_check(good)[0] is True


def test_cardinal_loss_is_rejected_without_machine_dictionary():
    passed, hard, _, _ = fidelity_gate("He had to kill the bulls.", "He had to kill five bulls.")
    assert passed is False
    assert any("CARDINAL" in item for item in hard)


def test_quote_normalization_preserves_named_entities():
    _, _, _, metrics = fidelity_gate("I went back to Rinaldi's bed.", "I went back to Rinaldi’s bed.")
    assert metrics["lost_entities"] == []
    assert metrics["added_entities"] == []


def test_near_twins_stay_in_one_holdout_group():
    text = "in the late summer of that year we lived in a house in a village"
    items = [{"id": "a", "bucket": 1, "assistant": text},
             {"id": "b", "bucket": 1, "assistant": text + " near the mountains"}]
    groups, pairs = assemble.near_dup_groups(items, assemble.five_gram_sets(items))
    assert groups == [[0, 1]]
    assert pairs == 1
    ids, rows, _ = assemble.pick_holdout(items, groups)
    assert ids == {"a", "b"}
    assert [row["id"] for row in rows] == ["a", "b"]


@pytest.mark.parametrize("a_is_ft", [True, False])
@pytest.mark.parametrize("coherent,degenerate,expected", [(True, False, "win"), (False, False, "loss"), (True, True, "loss")])
def test_incoherent_or_degenerate_winner_is_a_real_text_loss(a_is_ft, coherent, degenerate, expected):
    verdict = {"more_hemingway": "A" if a_is_ft else "B",
               "a_coherent": coherent if a_is_ft else True,
               "b_coherent": True if a_is_ft else coherent}
    result = tally([{"id": "fixture", "task": "rewrite", "a_is_ft": a_is_ft,
                     "ft_degenerate": degenerate, "verdict": verdict}])
    assert result["real_text"][expected] == 1
    assert result["overall"]["n"] == 1
    assert result["real_text"]["win_rate"] == (1.0 if expected == "win" else 0.0)


def test_exact_answer_dedup_keeps_first_bucket():
    items = [{"id": "second", "bucket": 2, "ahash": "same"},
             {"id": "first", "bucket": 1, "ahash": "same"}]
    kept, dropped = assemble.exact_dedup(items)
    assert kept == [{"id": "first", "bucket": 1, "ahash": "same"}]
    assert dropped == ["second"]


def test_blind_assignment_is_stable_and_uses_both_positions():
    assignments = [ab_assignment(str(i), "epoch3") for i in range(30)]
    assert assignments == [ab_assignment(str(i), "epoch3") for i in range(30)]
    assert set(assignments) == {True, False}


def test_capability_counts_actual_probe_answers():
    data = {"capability": [{"id": "math", "kind": "math", "expect": ["4"],
                            "base": "4", "epoch3": "wrong"},
                           {"id": "fact", "kind": "fact", "expect": ["paris"],
                            "base": "PARIS", "epoch3": "Paris"}]}
    result = score_capability(data, ["epoch3"])
    assert result["base"]["pass"] == 2
    assert result["epoch3"]["pass"] == 1
    assert result["epoch3"]["rate"] == 0.5


def test_imitation_cannot_enter_real_text_slice():
    result = tally([{"id": "fixture", "task": "practical_qa", "a_is_ft": True,
                     "ft_degenerate": False, "verdict": {"more_hemingway": "A", "a_coherent": True, "b_coherent": True}}])
    assert result["real_text"]["n"] == 0
    assert result["imitation"]["win"] == 1
