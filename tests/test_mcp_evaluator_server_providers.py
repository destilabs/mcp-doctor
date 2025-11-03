from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.mcp_evaluator.server_providers import (
    ConfigurableProvider,
    load_provider_configs,
)


def test_configurable_provider_matches_url() -> None:
    provider = ConfigurableProvider(
        name="test",
        match_patterns=["example.com", "test.org"],
        header_env_mappings={},
    )

    assert provider.matches("https://api.example.com/mcp")
    assert provider.matches("http://test.org/api")
    assert provider.matches("example.com")


def test_configurable_provider_does_not_match_other_urls() -> None:
    provider = ConfigurableProvider(
        name="test",
        match_patterns=["example.com"],
        header_env_mappings={},
    )

    assert not provider.matches("https://google.com")
    assert not provider.matches("http://different.org")


def test_configurable_provider_configure_headers_with_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_API_KEY", "secret-key")
    provider = ConfigurableProvider(
        name="test",
        match_patterns=["example.com"],
        header_env_mappings={"X-API-Key": "TEST_API_KEY"},
    )

    headers = provider.configure_headers()

    assert headers == {"X-API-Key": "secret-key"}


def test_configurable_provider_configure_headers_without_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_API_KEY", raising=False)
    provider = ConfigurableProvider(
        name="test",
        match_patterns=["example.com"],
        header_env_mappings={"X-API-Key": "TEST_API_KEY"},
    )

    headers = provider.configure_headers()

    assert headers == {}


def test_configurable_provider_configure_multiple_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_KEY", "key123")
    monkeypatch.setenv("AUTH_TOKEN", "token456")
    provider = ConfigurableProvider(
        name="test",
        match_patterns=["example.com"],
        header_env_mappings={
            "X-API-Key": "API_KEY",
            "Authorization": "AUTH_TOKEN",
        },
    )

    headers = provider.configure_headers()

    assert headers == {"X-API-Key": "key123", "Authorization": "token456"}


def test_configurable_provider_configure_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_VAR", "value123")
    provider = ConfigurableProvider(
        name="test",
        match_patterns=["example.com"],
        header_env_mappings={},
        env_var_mappings={"TARGET_VAR": "SOURCE_VAR"},
    )

    env_vars = provider.configure_env_vars()

    assert env_vars == {"TARGET_VAR": "value123"}


def test_configurable_provider_from_dict() -> None:
    config = {
        "name": "test-provider",
        "match_patterns": ["example.com", "test.org"],
        "header_env_mappings": {"X-API-Key": "TEST_KEY"},
        "env_var_mappings": {"VAR": "SOURCE_VAR"},
    }

    provider = ConfigurableProvider.from_dict(config)

    assert provider.name == "test-provider"
    assert provider.match_patterns == ["example.com", "test.org"]
    assert provider.header_env_mappings == {"X-API-Key": "TEST_KEY"}
    assert provider.env_var_mappings == {"VAR": "SOURCE_VAR"}


def test_load_provider_configs_from_file(tmp_path: Path) -> None:
    config_file = tmp_path / "providers.json"
    config_data = {
        "providers": [
            {
                "name": "provider1",
                "match_patterns": ["example.com"],
                "header_env_mappings": {"X-Key": "KEY1"},
            },
            {
                "name": "provider2",
                "match_patterns": ["test.org"],
                "header_env_mappings": {"Authorization": "TOKEN"},
            },
        ]
    }
    config_file.write_text(json.dumps(config_data))

    providers = load_provider_configs(config_file)

    assert len(providers) == 2
    assert providers[0].name == "provider1"
    assert providers[1].name == "provider2"


def test_load_provider_configs_nonexistent_file(tmp_path: Path) -> None:
    config_file = tmp_path / "nonexistent.json"

    providers = load_provider_configs(config_file)

    assert providers == []


def test_load_provider_configs_empty_providers(tmp_path: Path) -> None:
    config_file = tmp_path / "empty.json"
    config_file.write_text(json.dumps({"providers": []}))

    providers = load_provider_configs(config_file)

    assert providers == []

