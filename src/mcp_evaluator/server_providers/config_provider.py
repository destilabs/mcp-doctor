from __future__ import annotations

import os
from typing import Any


class ConfigurableProvider:
    def __init__(
        self,
        name: str,
        match_patterns: list[str],
        header_env_mappings: dict[str, str],
        env_var_mappings: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.match_patterns = match_patterns
        self.header_env_mappings = header_env_mappings
        self.env_var_mappings = env_var_mappings or {}

    def matches(self, target: str) -> bool:
        return any(pattern in target for pattern in self.match_patterns)

    def configure_headers(self) -> dict[str, str]:
        headers = {}
        for header_name, env_var_name in self.header_env_mappings.items():
            value = os.getenv(env_var_name)
            if value:
                headers[header_name] = value
        return headers

    def configure_env_vars(self) -> dict[str, str]:
        env_vars = {}
        for env_key, env_var_name in self.env_var_mappings.items():
            value = os.getenv(env_var_name)
            if value:
                env_vars[env_key] = value
        return env_vars

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> ConfigurableProvider:
        return cls(
            name=config["name"],
            match_patterns=config["match_patterns"],
            header_env_mappings=config.get("header_env_mappings", {}),
            env_var_mappings=config.get("env_var_mappings"),
        )

