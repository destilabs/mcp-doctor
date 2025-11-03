from __future__ import annotations


def _calculate_set_ratio(
    expected: list[str], actual: list[str], denominator: str, empty_default: float
) -> float:
    sets = {"expected": set(expected), "actual": set(actual)}
    denominator_set = sets[denominator]

    if not denominator_set:
        return empty_default

    correct = len(sets["expected"] & sets["actual"])
    return correct / len(denominator_set)


def calculate_tool_accuracy(expected: list[str], actual: list[str]) -> float:
    return _calculate_set_ratio(expected, actual, "expected", 1.0)


def calculate_precision(expected: list[str], actual: list[str]) -> float:
    return _calculate_set_ratio(expected, actual, "actual", 0.0)


def calculate_f1_score(expected: list[str], actual: list[str]) -> float:
    precision = calculate_precision(expected, actual)
    recall = calculate_tool_accuracy(expected, actual)

    if precision + recall == 0:
        return 0.0

    return 2 * (precision * recall) / (precision + recall)
