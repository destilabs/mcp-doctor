"""Tests for LangSmith dataset upload helper."""

from __future__ import annotations

import sys
import types

import pytest

from mcp_analyzer.langsmith_uploader import (
    LangSmithUploadError,
    upload_dataset_to_langsmith,
)


def test_upload_dataset_to_langsmith_success(monkeypatch) -> None:
    dataset = [
        {
            "prompt": "demo",
            "tools_called": ["t"],
            "tools_args": [["arg"]],
            "retrieved_contexts": ["Tool t outputs useful data."],
            "response": "Used tool t to return arg.",
            "reference": "The assistant should report the result of tool t.",
        },
    ]

    class StubClient:
        instance: "StubClient | None" = None

        def __init__(self, **kwargs) -> None:
            StubClient.instance = self
            self.kwargs = kwargs
            self.dataset_created: tuple[str, dict] | None = None
            self.examples: list[dict] = []
            self.runs: list[dict] = []

        def create_dataset(self, name: str, **kwargs):
            self.dataset_created = (name, kwargs)
            return types.SimpleNamespace(id="dataset-id")

        def create_example(self, *, inputs, outputs, dataset_id):
            self.examples.append(
                {
                    "inputs": inputs,
                    "outputs": outputs,
                    "dataset_id": dataset_id,
                }
            )

        def create_run(self, **kwargs):
            self.runs.append(kwargs)

    module = types.ModuleType("langsmith")
    module.Client = StubClient
    monkeypatch.setitem(sys.modules, "langsmith", module)

    dataset_id, reused = upload_dataset_to_langsmith(
        dataset,
        "demo-dataset",
        api_key="test-key",
        endpoint="https://example.com",
        project_name="demo-project",
        description="demo description",
    )

    assert dataset_id == "dataset-id"
    assert reused is False
    assert StubClient.instance is not None
    assert StubClient.instance.kwargs == {
        "api_key": "test-key",
        "api_url": "https://example.com",
    }
    assert StubClient.instance.dataset_created is not None
    name, kwargs = StubClient.instance.dataset_created
    assert name == "demo-dataset"
    assert kwargs["description"] == "demo description"
    assert kwargs["metadata"]["project_name"] == "demo-project"
    assert StubClient.instance.examples[0]["inputs"]["prompt"] == "demo"
    assert StubClient.instance.examples[0]["outputs"]["tools_called"] == ["t"]
    assert StubClient.instance.examples[0]["outputs"]["retrieved_contexts"] == [
        "Tool t outputs useful data."
    ]
    assert StubClient.instance.examples[0]["outputs"]["response"] == "Used tool t to return arg."
    assert StubClient.instance.examples[0]["outputs"]["reference"] == (
        "The assistant should report the result of tool t."
    )
    assert StubClient.instance.runs
    assert StubClient.instance.runs[0]["project_name"] == "demo-project"


def test_upload_dataset_to_langsmith_missing_sdk(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "langsmith", raising=False)

    with pytest.raises(LangSmithUploadError):
        upload_dataset_to_langsmith(
            [
                {
                    "prompt": "demo",
                    "tools_called": ["t"],
                    "tools_args": [["a"]],
                    "retrieved_contexts": ["Context"],
                    "response": "resp",
                    "reference": "ref",
                }
            ],
            "demo",
        )


def test_upload_dataset_to_langsmith_without_project_name(monkeypatch) -> None:
    """Test upload without project_name to cover the if project_name branch."""
    dataset = [
        {
            "prompt": "demo",
            "tools_called": ["t"],
            "tools_args": [["arg"]],
            "retrieved_contexts": ["Context"],
            "response": "resp",
            "reference": "ref",
        },
    ]

    class StubClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.runs: list[dict] = []

        def create_dataset(self, name: str, **kwargs):
            return types.SimpleNamespace(id="dataset-id")

        def create_example(self, *, inputs, outputs, dataset_id):
            pass

        def create_run(self, **kwargs):
            self.runs.append(kwargs)

    module = types.ModuleType("langsmith")
    module.Client = StubClient
    monkeypatch.setitem(sys.modules, "langsmith", module)

    dataset_id, reused = upload_dataset_to_langsmith(
        dataset,
        "demo-dataset",
        # No project_name provided - this should skip the create_run call
    )

    assert dataset_id == "dataset-id"
    assert reused is False


def test_upload_dataset_to_langsmith_create_run_failure(monkeypatch) -> None:
    """Test that create_run failures don't block upload (covers exception handling in create_run)."""
    dataset = [
        {
            "prompt": "demo",
            "tools_called": ["t"],
            "tools_args": [["arg"]],
            "retrieved_contexts": ["Context"],
            "response": "resp",
            "reference": "ref",
        },
    ]

    class StubClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def create_dataset(self, name: str, **kwargs):
            return types.SimpleNamespace(id="dataset-id")

        def create_example(self, *, inputs, outputs, dataset_id):
            pass

        def create_run(self, **kwargs):
            # This should raise an exception, but it should be caught and ignored
            raise Exception("Run creation failed")

    module = types.ModuleType("langsmith")
    module.Client = StubClient
    monkeypatch.setitem(sys.modules, "langsmith", module)

    # This should succeed despite the create_run failure
    dataset_id, reused = upload_dataset_to_langsmith(
        dataset,
        "demo-dataset",
        project_name="test-project",
    )

    assert dataset_id == "dataset-id"
    assert reused is False


def test_upload_dataset_to_langsmith_reuses_existing(monkeypatch) -> None:
    """If dataset creation fails but the dataset already exists, reuse it."""

    dataset = [
        {
            "prompt": "demo",
            "tools_called": ["t"],
            "tools_args": [["arg"]],
            "retrieved_contexts": ["Context"],
            "response": "resp",
            "reference": "ref",
        },
    ]

    class StubClient:
        def __init__(self, **kwargs) -> None:
            self.examples: list[dict] = []

        def create_dataset(self, name: str, **kwargs):
            raise RuntimeError("Already exists")

        def read_dataset(self, dataset_name: str):
            assert dataset_name == "demo-dataset"
            return types.SimpleNamespace(id="existing-id")

        def create_example(self, *, inputs, outputs, dataset_id):
            self.examples.append({"inputs": inputs, "outputs": outputs, "dataset_id": dataset_id})

        def create_run(self, **kwargs):
            pass

    module = types.ModuleType("langsmith")
    module.Client = StubClient
    monkeypatch.setitem(sys.modules, "langsmith", module)

    dataset_id, reused = upload_dataset_to_langsmith(dataset, "demo-dataset")

    assert dataset_id == "existing-id"
    assert reused is True
