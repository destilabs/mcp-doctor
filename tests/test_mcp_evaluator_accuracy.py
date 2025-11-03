from __future__ import annotations

import pytest

from src.mcp_evaluator.accuracy_calculator import (
    calculate_f1_score,
    calculate_precision,
    calculate_tool_accuracy,
)


def test_calculate_tool_accuracy_perfect_match() -> None:
    expected = ["tool1", "tool2", "tool3"]
    actual = ["tool1", "tool2", "tool3"]
    assert calculate_tool_accuracy(expected, actual) == 1.0


def test_calculate_tool_accuracy_partial_match() -> None:
    expected = ["tool1", "tool2", "tool3"]
    actual = ["tool1", "tool2"]
    assert calculate_tool_accuracy(expected, actual) == pytest.approx(2 / 3)


def test_calculate_tool_accuracy_no_match() -> None:
    expected = ["tool1", "tool2"]
    actual = ["tool3", "tool4"]
    assert calculate_tool_accuracy(expected, actual) == 0.0


def test_calculate_tool_accuracy_empty_expected() -> None:
    expected: list[str] = []
    actual = ["tool1", "tool2"]
    assert calculate_tool_accuracy(expected, actual) == 1.0


def test_calculate_tool_accuracy_extra_actual_tools() -> None:
    expected = ["tool1", "tool2"]
    actual = ["tool1", "tool2", "tool3", "tool4"]
    assert calculate_tool_accuracy(expected, actual) == 1.0


def test_calculate_precision_perfect() -> None:
    expected = ["tool1", "tool2"]
    actual = ["tool1", "tool2"]
    assert calculate_precision(expected, actual) == 1.0


def test_calculate_precision_with_false_positives() -> None:
    expected = ["tool1", "tool2"]
    actual = ["tool1", "tool2", "tool3", "tool4"]
    assert calculate_precision(expected, actual) == 0.5


def test_calculate_precision_empty_actual() -> None:
    expected = ["tool1", "tool2"]
    actual: list[str] = []
    assert calculate_precision(expected, actual) == 0.0




def test_calculate_f1_score_perfect() -> None:
    expected = ["tool1", "tool2"]
    actual = ["tool1", "tool2"]
    assert calculate_f1_score(expected, actual) == 1.0


def test_calculate_f1_score_balanced() -> None:
    expected = ["tool1", "tool2", "tool3"]
    actual = ["tool1", "tool2", "tool4"]
    precision = 2 / 3
    recall = 2 / 3
    expected_f1 = 2 * (precision * recall) / (precision + recall)
    assert calculate_f1_score(expected, actual) == pytest.approx(expected_f1)


def test_calculate_f1_score_zero_precision_and_recall() -> None:
    expected = ["tool1", "tool2"]
    actual: list[str] = []
    assert calculate_f1_score(expected, actual) == 0.0


def test_calculate_f1_score_no_overlap() -> None:
    expected = ["tool1", "tool2"]
    actual = ["tool3", "tool4"]
    assert calculate_f1_score(expected, actual) == 0.0
