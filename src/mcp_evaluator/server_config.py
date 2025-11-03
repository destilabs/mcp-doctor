from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .server_providers import get_provider_for_target


@dataclass
class ServerConfig:
    target: str
    timeout: int = 30
    headers: dict[str, str] = field(default_factory=dict)
    env_vars: dict[str, str] = field(default_factory=dict)
    working_dir: str | None = None


def detect_server_config(server_target: str, **kwargs: Any) -> ServerConfig:
    config = ServerConfig(target=server_target, **kwargs)

    provider = get_provider_for_target(server_target)
    if provider:
        config.headers.update(provider.configure_headers())
        config.env_vars.update(provider.configure_env_vars())

    return config
