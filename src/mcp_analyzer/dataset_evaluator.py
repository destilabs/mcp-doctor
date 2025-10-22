"""Evaluate tool calling accuracy for datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


class EvaluationError(Exception):
    """Raised when evaluation fails."""


@dataclass
class ToolCallMatch:
    """Result of matching a single tool call."""

    expected_tool: str
    actual_tool: Optional[str]
    tool_match: bool
    expected_args: List[Any]
    actual_args: Optional[List[Any]]
    params_match: Optional[bool]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expected_tool": self.expected_tool,
            "actual_tool": self.actual_tool,
            "tool_match": self.tool_match,
            "expected_args": self.expected_args,
            "actual_args": self.actual_args,
            "params_match": self.params_match,
        }


@dataclass
class TaskEvaluation:
    """Evaluation result for a single task."""

    task_index: int
    prompt: str
    expected_tools: List[str]
    actual_tools: List[str]
    tool_matches: List[ToolCallMatch]
    tool_accuracy: float
    tool_order_accuracy: float
    param_accuracy: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_index": self.task_index,
            "prompt": self.prompt,
            "expected_tools": self.expected_tools,
            "actual_tools": self.actual_tools,
            "tool_matches": [m.to_dict() for m in self.tool_matches],
            "tool_accuracy": self.tool_accuracy,
            "tool_order_accuracy": self.tool_order_accuracy,
            "param_accuracy": self.param_accuracy,
        }


@dataclass
class EvaluationReport:
    """Comprehensive evaluation report."""

    dataset_path: str
    total_tasks: int
    task_evaluations: List[TaskEvaluation]
    overall_tool_accuracy: float
    overall_tool_order_accuracy: float
    overall_param_accuracy: Optional[float]
    perfect_matches: int
    tool_only_matches: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_path": self.dataset_path,
            "total_tasks": self.total_tasks,
            "task_evaluations": [t.to_dict() for t in self.task_evaluations],
            "overall_tool_accuracy": self.overall_tool_accuracy,
            "overall_tool_order_accuracy": self.overall_tool_order_accuracy,
            "overall_param_accuracy": self.overall_param_accuracy,
            "perfect_matches": self.perfect_matches,
            "tool_only_matches": self.tool_only_matches,
        }


def normalize_params(params: Any) -> Any:
    """Normalize parameters for comparison."""
    if params is None:
        return {}
    if isinstance(params, dict):
        return {k: normalize_params(v) for k, v in params.items()}
    if isinstance(params, list):
        if len(params) == 1 and isinstance(params[0], dict):
            return params[0]
        return [normalize_params(item) for item in params]
    return params


def compare_params(expected: Any, actual: Any) -> bool:
    """Compare two parameter sets with normalization."""
    normalized_expected = normalize_params(expected)
    normalized_actual = normalize_params(actual)

    if isinstance(normalized_expected, dict) and isinstance(normalized_actual, dict):
        if set(normalized_expected.keys()) != set(normalized_actual.keys()):
            return False
        return all(
            compare_params(normalized_expected[k], normalized_actual[k])
            for k in normalized_expected.keys()
        )
    
    if isinstance(normalized_expected, list) and isinstance(normalized_actual, list):
        if len(normalized_expected) != len(normalized_actual):
            return False
        return all(
            compare_params(e, a) for e, a in zip(normalized_expected, normalized_actual)
        )
    
    return normalized_expected == normalized_actual


def evaluate_task(
    task: Dict[str, Any],
    actual_calls: List[Dict[str, Any]],
    *,
    evaluate_params: bool = True,
) -> TaskEvaluation:
    """Evaluate a single task against actual tool calls."""
    expected_tools = task.get("tools_called", [])
    expected_args = task.get("tools_args", [])
    
    actual_tools = [call.get("tool_name", "") for call in actual_calls]
    
    matches: List[ToolCallMatch] = []
    
    max_len = max(len(expected_tools), len(actual_tools))
    
    for i in range(max_len):
        expected_tool = expected_tools[i] if i < len(expected_tools) else None
        expected_arg = expected_args[i] if i < len(expected_args) else []
        actual_tool = actual_tools[i] if i < len(actual_tools) else None
        actual_arg = actual_calls[i].get("arguments", []) if i < len(actual_calls) else None
        
        if expected_tool is None:
            matches.append(
                ToolCallMatch(
                    expected_tool="<none>",
                    actual_tool=actual_tool,
                    tool_match=False,
                    expected_args=[],
                    actual_args=actual_arg,
                    params_match=None if not evaluate_params else False,
                )
            )
            continue
        
        tool_match = expected_tool == actual_tool
        
        params_match: Optional[bool] = None
        if evaluate_params and tool_match and actual_arg is not None:
            params_match = compare_params(expected_arg, actual_arg)
        elif not evaluate_params:
            params_match = None
        elif not tool_match:
            params_match = None
        
        matches.append(
            ToolCallMatch(
                expected_tool=expected_tool,
                actual_tool=actual_tool,
                tool_match=tool_match,
                expected_args=expected_arg,
                actual_args=actual_arg,
                params_match=params_match,
            )
        )
    
    tool_accuracy = (
        sum(1 for m in matches if m.tool_match) / len(matches) if matches else 0.0
    )
    
    tool_order_accuracy = 1.0 if expected_tools == actual_tools else 0.0
    
    param_accuracy: Optional[float] = None
    if evaluate_params:
        param_matches = [m for m in matches if m.params_match is not None]
        param_accuracy = (
            sum(1 for m in param_matches if m.params_match) / len(param_matches)
            if param_matches
            else 0.0
        )
    
    return TaskEvaluation(
        task_index=0,
        prompt=task.get("prompt", ""),
        expected_tools=expected_tools,
        actual_tools=actual_tools,
        tool_matches=matches,
        tool_accuracy=tool_accuracy,
        tool_order_accuracy=tool_order_accuracy,
        param_accuracy=param_accuracy,
    )


def load_dataset(dataset_path: Path) -> List[Dict[str, Any]]:
    """Load dataset from JSON file."""
    if not dataset_path.exists():
        raise EvaluationError(f"Dataset file not found: {dataset_path}")
    
    try:
        content = dataset_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"Invalid JSON in dataset file: {exc}") from exc
    
    if not isinstance(data, list):
        raise EvaluationError("Dataset must be a JSON array of tasks")
    
    return data


def evaluate_dataset(
    dataset: Sequence[Dict[str, Any]],
    actual_results: Sequence[Any],
    *,
    evaluate_params: bool = True,
    dataset_path: str = "<unknown>",
) -> EvaluationReport:
    """Evaluate an entire dataset against actual LLM results.
    
    Supports two formats:
    1. Simple: List of tool call arrays
    2. Detailed: List of objects with query, tool_calls, tokens, etc.
    """
    if len(dataset) != len(actual_results):
        raise EvaluationError(
            f"Dataset has {len(dataset)} tasks but got {len(actual_results)} results"
        )
    
    task_evaluations: List[TaskEvaluation] = []
    
    for idx, (task, actual_result) in enumerate(zip(dataset, actual_results)):
        if isinstance(actual_result, dict) and "tool_calls" in actual_result:
            actual_calls = actual_result["tool_calls"]
        elif isinstance(actual_result, list):
            actual_calls = actual_result
        else:
            raise EvaluationError(
                f"Task {idx}: actual_result must be a list of tool calls or an object with 'tool_calls'"
            )
        
        eval_result = evaluate_task(task, actual_calls, evaluate_params=evaluate_params)
        eval_result.task_index = idx
        task_evaluations.append(eval_result)
    
    overall_tool_accuracy = (
        sum(e.tool_accuracy for e in task_evaluations) / len(task_evaluations)
        if task_evaluations
        else 0.0
    )
    
    overall_tool_order_accuracy = (
        sum(e.tool_order_accuracy for e in task_evaluations) / len(task_evaluations)
        if task_evaluations
        else 0.0
    )
    
    overall_param_accuracy: Optional[float] = None
    if evaluate_params:
        param_evals = [e for e in task_evaluations if e.param_accuracy is not None]
        overall_param_accuracy = (
            sum(e.param_accuracy for e in param_evals) / len(param_evals)
            if param_evals
            else 0.0
        )
    
    perfect_matches = sum(
        1
        for e in task_evaluations
        if e.tool_order_accuracy == 1.0
        and (not evaluate_params or e.param_accuracy == 1.0)
    )
    
    tool_only_matches = sum(
        1 for e in task_evaluations if e.tool_order_accuracy == 1.0
    )
    
    return EvaluationReport(
        dataset_path=dataset_path,
        total_tasks=len(dataset),
        task_evaluations=task_evaluations,
        overall_tool_accuracy=overall_tool_accuracy,
        overall_tool_order_accuracy=overall_tool_order_accuracy,
        overall_param_accuracy=overall_param_accuracy,
        perfect_matches=perfect_matches,
        tool_only_matches=tool_only_matches,
    )


__all__ = [
    "EvaluationError",
    "ToolCallMatch",
    "TaskEvaluation",
    "EvaluationReport",
    "evaluate_task",
    "evaluate_dataset",
    "load_dataset",
]

