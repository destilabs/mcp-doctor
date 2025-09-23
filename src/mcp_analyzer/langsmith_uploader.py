"""Upload generated datasets to LangSmith projects."""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional, Sequence

from .dataset_generator import DatasetGenerationError


class LangSmithUploadError(DatasetGenerationError):
    """Raised when a dataset cannot be uploaded to LangSmith."""


def _build_inputs(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "prompt": entry.get("prompt"),
    }


def _build_outputs(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tools_called": entry.get("tools_called"),
        "tools_args": entry.get("tools_args"),
    }


def upload_dataset_to_langsmith(
    dataset: Sequence[Dict[str, Any]],
    dataset_name: str,
    *,
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None,
    project_name: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Create a LangSmith dataset populated with generated examples.

    Args:
        dataset: Sequence of dataset entries produced by :class:`DatasetGenerator`.
        dataset_name: Name of the LangSmith dataset to create or append to.
        api_key: Optional API key override; defaults to environment variables handled by ``langsmith.Client``.
        endpoint: Custom LangSmith API endpoint when working outside the default region.
        project_name: Optional LangSmith project to associate via metadata and bookkeeping run.
        description: Optional dataset description.

    Returns:
        The dataset identifier returned by LangSmith.

    Raises:
        LangSmithUploadError: When the LangSmith SDK is unavailable or an API call fails.
    """

    try:
        from langsmith import Client
    except (
        ImportError
    ) as exc:  # pragma: no cover - executed only when dependency missing
        raise LangSmithUploadError(
            "Install the 'langsmith' package to upload datasets (pip install langsmith)."
        ) from exc

    client_kwargs: Dict[str, Any] = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if endpoint:
        client_kwargs["api_url"] = endpoint

    try:
        client = Client(**client_kwargs)
    except Exception as exc:  # pragma: no cover - thin wrapper around SDK constructor
        raise LangSmithUploadError("Failed to initialize LangSmith client") from exc

    metadata: Dict[str, Any] = {}
    if project_name:
        metadata["project_name"] = project_name

    create_kwargs: Dict[str, Any] = {}
    if description:
        create_kwargs["description"] = description
    if metadata:
        create_kwargs["metadata"] = metadata

    try:
        dataset_obj = client.create_dataset(dataset_name, **create_kwargs)
    except Exception as exc:  # pragma: no cover - depends on LangSmith client behavior
        raise LangSmithUploadError(
            f"Failed to create LangSmith dataset '{dataset_name}'"
        ) from exc

    for entry in dataset:
        inputs = _build_inputs(entry)
        outputs = _build_outputs(entry)
        try:
            client.create_example(
                inputs=inputs,
                outputs=outputs,
                dataset_id=dataset_obj.id,
            )
        except Exception as exc:  # pragma: no cover - SDK surface
            raise LangSmithUploadError(
                "Failed to create LangSmith dataset example"
            ) from exc

    if project_name:
        try:
            client.create_run(
                name=f"{dataset_name} dataset created",
                project_name=project_name,
                run_type="chain",
                inputs={
                    "dataset_name": dataset_name,
                    "example_count": len(dataset),
                },
                outputs={"status": "created"},
                metadata={
                    "source": "mcp-doctor",
                    "dataset_id": str(dataset_obj.id),
                },
                end_time=dt.datetime.utcnow(),
            )
        except Exception:
            # Creating the bookkeeping run is best-effort; failures should not block upload.
            pass

    return str(dataset_obj.id)
