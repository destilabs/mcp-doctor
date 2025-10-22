"""Tests for dataset evaluation functionality."""

import json

import pytest

from mcp_analyzer.dataset_evaluator import (
    EvaluationError,
    compare_params,
    evaluate_dataset,
    evaluate_task,
    load_dataset,
    normalize_params,
)


@pytest.fixture
def simple_dataset():
    """Simple test dataset with 2 tasks."""
    return [
        {
            "prompt": "Get all running campaigns",
            "tools_called": ["get_campaigns"],
            "tools_args": [[{"status": "running", "limit": 50}]],
        },
        {
            "prompt": "Create a campaign and add a lead",
            "tools_called": ["create_campaign", "add_lead"],
            "tools_args": [
                [{"name": "Test Campaign", "subject": "Hi"}],
                [{"email": "test@example.com"}],
            ],
        },
    ]


@pytest.fixture
def simple_actual_results():
    """Actual results matching the simple dataset."""
    return [
        [
            {
                "tool_name": "get_campaigns",
                "arguments": [{"status": "running", "limit": 50}],
            }
        ],
        [
            {
                "tool_name": "create_campaign",
                "arguments": [{"name": "Test Campaign", "subject": "Hi"}],
            },
            {
                "tool_name": "add_lead",
                "arguments": [{"email": "test@example.com"}],
            },
        ],
    ]


class TestNormalizeParams:
    """Test parameter normalization."""

    def test_normalize_none(self):
        assert normalize_params(None) == {}

    def test_normalize_dict(self):
        params = {"key": "value", "nested": {"inner": "data"}}
        assert normalize_params(params) == params

    def test_normalize_single_dict_in_list(self):
        params = [{"key": "value"}]
        assert normalize_params(params) == {"key": "value"}

    def test_normalize_multiple_items_in_list(self):
        params = [{"key1": "value1"}, {"key2": "value2"}]
        expected = [{"key1": "value1"}, {"key2": "value2"}]
        assert normalize_params(params) == expected

    def test_normalize_nested_structures(self):
        params = {"list": [{"a": 1}], "dict": {"b": [2]}}
        expected = {"list": {"a": 1}, "dict": {"b": [2]}}
        assert normalize_params(params) == expected


class TestCompareParams:
    """Test parameter comparison."""

    def test_compare_identical_dicts(self):
        assert compare_params({"a": 1, "b": 2}, {"a": 1, "b": 2})

    def test_compare_different_dicts(self):
        assert not compare_params({"a": 1}, {"a": 2})

    def test_compare_different_keys(self):
        assert not compare_params({"a": 1}, {"b": 1})

    def test_compare_with_normalization(self):
        assert compare_params([{"a": 1}], {"a": 1})

    def test_compare_nested_dicts(self):
        expected = {"outer": {"inner": "value"}}
        actual = {"outer": {"inner": "value"}}
        assert compare_params(expected, actual)

    def test_compare_nested_dicts_different(self):
        expected = {"outer": {"inner": "value1"}}
        actual = {"outer": {"inner": "value2"}}
        assert not compare_params(expected, actual)

    def test_compare_lists(self):
        assert compare_params([1, 2, 3], [1, 2, 3])

    def test_compare_lists_different_length(self):
        assert not compare_params([1, 2], [1, 2, 3])

    def test_compare_primitives(self):
        assert compare_params("test", "test")
        assert not compare_params("test", "other")


class TestEvaluateTask:
    """Test single task evaluation."""

    def test_perfect_match_with_params(self):
        task = {
            "prompt": "Test task",
            "tools_called": ["tool1", "tool2"],
            "tools_args": [[{"arg": "value1"}], [{"arg": "value2"}]],
        }
        actual = [
            {"tool_name": "tool1", "arguments": [{"arg": "value1"}]},
            {"tool_name": "tool2", "arguments": [{"arg": "value2"}]},
        ]

        result = evaluate_task(task, actual, evaluate_params=True)

        assert result.tool_accuracy == 1.0
        assert result.tool_order_accuracy == 1.0
        assert result.param_accuracy == 1.0
        assert len(result.tool_matches) == 2
        assert all(m.tool_match for m in result.tool_matches)
        assert all(m.params_match for m in result.tool_matches)

    def test_perfect_tool_match_wrong_params(self):
        task = {
            "prompt": "Test task",
            "tools_called": ["tool1"],
            "tools_args": [[{"arg": "expected"}]],
        }
        actual = [
            {"tool_name": "tool1", "arguments": [{"arg": "different"}]},
        ]

        result = evaluate_task(task, actual, evaluate_params=True)

        assert result.tool_accuracy == 1.0
        assert result.tool_order_accuracy == 1.0
        assert result.param_accuracy == 0.0
        assert result.tool_matches[0].tool_match
        assert not result.tool_matches[0].params_match

    def test_wrong_tool_called(self):
        task = {
            "prompt": "Test task",
            "tools_called": ["tool1"],
            "tools_args": [[{"arg": "value"}]],
        }
        actual = [
            {"tool_name": "tool2", "arguments": [{"arg": "value"}]},
        ]

        result = evaluate_task(task, actual, evaluate_params=True)

        assert result.tool_accuracy == 0.0
        assert result.tool_order_accuracy == 0.0
        assert result.tool_matches[0].params_match is None

    def test_extra_tool_called(self):
        task = {
            "prompt": "Test task",
            "tools_called": ["tool1"],
            "tools_args": [[{"arg": "value"}]],
        }
        actual = [
            {"tool_name": "tool1", "arguments": [{"arg": "value"}]},
            {"tool_name": "tool2", "arguments": []},
        ]

        result = evaluate_task(task, actual, evaluate_params=True)

        assert result.tool_accuracy == 0.5
        assert result.tool_order_accuracy == 0.0
        assert len(result.tool_matches) == 2
        assert result.tool_matches[0].tool_match
        assert not result.tool_matches[1].tool_match

    def test_missing_tool_call(self):
        task = {
            "prompt": "Test task",
            "tools_called": ["tool1", "tool2"],
            "tools_args": [[{"arg": "value1"}], [{"arg": "value2"}]],
        }
        actual = [
            {"tool_name": "tool1", "arguments": [{"arg": "value1"}]},
        ]

        result = evaluate_task(task, actual, evaluate_params=True)

        assert result.tool_accuracy == 0.5
        assert result.tool_order_accuracy == 0.0
        assert len(result.tool_matches) == 2

    def test_evaluate_without_params(self):
        task = {
            "prompt": "Test task",
            "tools_called": ["tool1"],
            "tools_args": [[{"arg": "value"}]],
        }
        actual = [
            {"tool_name": "tool1", "arguments": [{"different": "value"}]},
        ]

        result = evaluate_task(task, actual, evaluate_params=False)

        assert result.tool_accuracy == 1.0
        assert result.tool_order_accuracy == 1.0
        assert result.param_accuracy is None
        assert result.tool_matches[0].params_match is None

    def test_wrong_order(self):
        task = {
            "prompt": "Test task",
            "tools_called": ["tool1", "tool2"],
            "tools_args": [[{"a": 1}], [{"b": 2}]],
        }
        actual = [
            {"tool_name": "tool2", "arguments": [{"b": 2}]},
            {"tool_name": "tool1", "arguments": [{"a": 1}]},
        ]

        result = evaluate_task(task, actual, evaluate_params=True)

        assert result.tool_accuracy == 0.0
        assert result.tool_order_accuracy == 0.0


class TestLoadDataset:
    """Test dataset loading."""

    def test_load_valid_dataset(self, tmp_path, simple_dataset):
        dataset_file = tmp_path / "dataset.json"
        dataset_file.write_text(json.dumps(simple_dataset), encoding="utf-8")

        loaded = load_dataset(dataset_file)

        assert loaded == simple_dataset

    def test_load_nonexistent_file(self, tmp_path):
        dataset_file = tmp_path / "nonexistent.json"

        with pytest.raises(EvaluationError, match="not found"):
            load_dataset(dataset_file)

    def test_load_invalid_json(self, tmp_path):
        dataset_file = tmp_path / "invalid.json"
        dataset_file.write_text("not valid json", encoding="utf-8")

        with pytest.raises(EvaluationError, match="Invalid JSON"):
            load_dataset(dataset_file)

    def test_load_non_array(self, tmp_path):
        dataset_file = tmp_path / "not_array.json"
        dataset_file.write_text('{"key": "value"}', encoding="utf-8")

        with pytest.raises(EvaluationError, match="must be a JSON array"):
            load_dataset(dataset_file)


class TestEvaluateDataset:
    """Test full dataset evaluation."""

    def test_evaluate_full_dataset(self, simple_dataset, simple_actual_results):
        report = evaluate_dataset(
            simple_dataset,
            simple_actual_results,
            evaluate_params=True,
            dataset_path="test.json",
        )

        assert report.total_tasks == 2
        assert report.overall_tool_accuracy == 1.0
        assert report.overall_tool_order_accuracy == 1.0
        assert report.overall_param_accuracy == 1.0
        assert report.perfect_matches == 2
        assert report.tool_only_matches == 2
        assert len(report.task_evaluations) == 2

    def test_evaluate_without_params(self, simple_dataset, simple_actual_results):
        report = evaluate_dataset(
            simple_dataset,
            simple_actual_results,
            evaluate_params=False,
            dataset_path="test.json",
        )

        assert report.total_tasks == 2
        assert report.overall_param_accuracy is None
        for task_eval in report.task_evaluations:
            assert task_eval.param_accuracy is None

    def test_evaluate_mismatched_lengths(self, simple_dataset):
        actual_results = [[{"tool_name": "tool1", "arguments": []}]]

        with pytest.raises(
            EvaluationError, match="Dataset has 2 tasks but got 1 results"
        ):
            evaluate_dataset(
                simple_dataset,
                actual_results,
                evaluate_params=True,
            )

    def test_evaluate_partial_matches(self):
        dataset = [
            {
                "prompt": "Task 1",
                "tools_called": ["tool1"],
                "tools_args": [[{"arg": "value"}]],
            },
            {
                "prompt": "Task 2",
                "tools_called": ["tool2"],
                "tools_args": [[{"arg": "value"}]],
            },
        ]
        actual = [
            [{"tool_name": "tool1", "arguments": [{"arg": "value"}]}],
            [{"tool_name": "tool3", "arguments": [{"arg": "value"}]}],
        ]

        report = evaluate_dataset(dataset, actual, evaluate_params=True)

        assert report.overall_tool_accuracy == 0.5
        assert report.overall_tool_order_accuracy == 0.5
        assert report.perfect_matches == 1
        assert report.tool_only_matches == 1

    def test_report_to_dict(self, simple_dataset, simple_actual_results):
        report = evaluate_dataset(
            simple_dataset,
            simple_actual_results,
            evaluate_params=True,
        )

        report_dict = report.to_dict()

        assert isinstance(report_dict, dict)
        assert "total_tasks" in report_dict
        assert "task_evaluations" in report_dict
        assert "overall_tool_accuracy" in report_dict
        assert isinstance(report_dict["task_evaluations"], list)
        assert all(isinstance(t, dict) for t in report_dict["task_evaluations"])

    def test_empty_dataset(self):
        report = evaluate_dataset([], [], evaluate_params=True)

        assert report.total_tasks == 0
        assert report.overall_tool_accuracy == 0.0
        assert report.overall_tool_order_accuracy == 0.0
        assert report.overall_param_accuracy == 0.0
        assert report.perfect_matches == 0


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_task_with_empty_tools(self):
        task = {
            "prompt": "Test",
            "tools_called": [],
            "tools_args": [],
        }
        actual = []

        result = evaluate_task(task, actual, evaluate_params=True)

        assert result.tool_accuracy == 0.0
        assert result.tool_order_accuracy == 1.0
        assert result.param_accuracy == 0.0

    def test_normalized_params_comparison(self):
        task = {
            "prompt": "Test",
            "tools_called": ["tool1"],
            "tools_args": [[{"arg": "value"}]],
        }
        actual = [
            {"tool_name": "tool1", "arguments": {"arg": "value"}},
        ]

        result = evaluate_task(task, actual, evaluate_params=True)

        assert result.tool_accuracy == 1.0

    def test_complex_nested_params(self):
        task = {
            "prompt": "Test",
            "tools_called": ["tool1"],
            "tools_args": [
                [
                    {
                        "filters": [
                            {"filterId": "seniority", "in": ["CxO"], "out": []},
                            {"filterId": "country", "in": ["US"], "out": []},
                        ]
                    }
                ]
            ],
        }
        actual = [
            {
                "tool_name": "tool1",
                "arguments": [
                    {
                        "filters": [
                            {"filterId": "seniority", "in": ["CxO"], "out": []},
                            {"filterId": "country", "in": ["US"], "out": []},
                        ]
                    }
                ],
            }
        ]

        result = evaluate_task(task, actual, evaluate_params=True)

        assert result.param_accuracy == 1.0

