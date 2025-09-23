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
        {"prompt": "demo", "tools_called": ["t"], "tools_args": [["arg"]]},
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

    dataset_id = upload_dataset_to_langsmith(
        dataset,
        "demo-dataset",
        api_key="test-key",
        endpoint="https://example.com",
        project_name="demo-project",
        description="demo description",
    )

    assert dataset_id == "dataset-id"
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
    assert StubClient.instance.runs
    assert StubClient.instance.runs[0]["project_name"] == "demo-project"


def test_upload_dataset_to_langsmith_missing_sdk(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "langsmith", raising=False)

    with pytest.raises(LangSmithUploadError):
        upload_dataset_to_langsmith(
            [
                {"prompt": "demo", "tools_called": ["t"], "tools_args": [["a"]]},
            ],
            "demo",
        )
