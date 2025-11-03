from __future__ import annotations

from typing import Protocol


class ServerProvider(Protocol):
    def matches(self, target: str) -> bool: ...

    def configure_headers(self) -> dict[str, str]: ...

    def configure_env_vars(self) -> dict[str, str]: ...

