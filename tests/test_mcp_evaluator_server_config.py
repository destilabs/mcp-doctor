from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.mcp_evaluator.server_config import ServerConfig, detect_server_config


def test_server_config_initialization_defaults() -> None:
    config = ServerConfig(target="http://example.com")

    assert config.target == "http://example.com"
    assert config.timeout == 30
    assert config.headers == {}
    assert config.env_vars == {}
    assert config.working_dir is None


def test_server_config_initialization_with_custom_values() -> None:
    config = ServerConfig(
        target="http://example.com",
        timeout=60,
        headers={"Authorization": "Bearer token"},
        env_vars={"ENV": "test"},
        working_dir="/tmp",
    )

    assert config.target == "http://example.com"
    assert config.timeout == 60
    assert config.headers == {"Authorization": "Bearer token"}
    assert config.env_vars == {"ENV": "test"}
    assert config.working_dir == "/tmp"


def test_detect_server_config_generic_server() -> None:
    config = detect_server_config("http://example.com")

    assert config.target == "http://example.com"
    assert config.timeout == 30
    assert config.headers == {}


def test_detect_server_config_with_provider_without_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TEST_API_KEY", raising=False)

    config_file = tmp_path / "server_providers.json"
    config_data = {
        "providers": [
            {
                "name": "test-provider",
                "match_patterns": ["test-server.com"],
                "header_env_mappings": {"X-API-Key": "TEST_API_KEY"},
            }
        ]
    }
    config_file.write_text(json.dumps(config_data))

    from src.mcp_evaluator.server_providers import config_loader

    monkeypatch.setattr(
        config_loader, "get_default_config_paths", lambda: [config_file]
    )

    config = detect_server_config("https://test-server.com/mcp")

    assert config.target == "https://test-server.com/mcp"
    assert "X-API-Key" not in config.headers


def test_detect_server_config_with_provider_with_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TEST_API_KEY", "secret-key")

    config_file = tmp_path / "server_providers.json"
    config_data = {
        "providers": [
            {
                "name": "test-provider",
                "match_patterns": ["test-server.com"],
                "header_env_mappings": {"X-API-Key": "TEST_API_KEY"},
            }
        ]
    }
    config_file.write_text(json.dumps(config_data))

    from src.mcp_evaluator.server_providers import config_loader

    monkeypatch.setattr(
        config_loader, "get_default_config_paths", lambda: [config_file]
    )

    config = detect_server_config("https://test-server.com/mcp")

    assert config.target == "https://test-server.com/mcp"
    assert config.headers["X-API-Key"] == "secret-key"


def test_detect_server_config_preserves_custom_kwargs() -> None:
    config = detect_server_config(
        "http://example.com",
        timeout=90,
        headers={"Custom": "Header"},
        env_vars={"VAR": "value"},
        working_dir="/custom",
    )

    assert config.timeout == 90
    assert config.headers == {"Custom": "Header"}
    assert config.env_vars == {"VAR": "value"}
    assert config.working_dir == "/custom"


def test_detect_server_config_merges_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TEST_API_KEY", "secret-key")

    config_file = tmp_path / "server_providers.json"
    config_data = {
        "providers": [
            {
                "name": "test-provider",
                "match_patterns": ["test-server.com"],
                "header_env_mappings": {"X-API-Key": "TEST_API_KEY"},
            }
        ]
    }
    config_file.write_text(json.dumps(config_data))

    from src.mcp_evaluator.server_providers import config_loader

    monkeypatch.setattr(
        config_loader, "get_default_config_paths", lambda: [config_file]
    )

    config = detect_server_config(
        "https://test-server.com/mcp",
        headers={"Custom": "Header"},
    )

    assert config.headers["X-API-Key"] == "secret-key"
    assert config.headers["Custom"] == "Header"
