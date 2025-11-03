from __future__ import annotations

from .base import ServerProvider
from .config_loader import load_all_providers


def get_all_providers() -> list[ServerProvider]:
    return load_all_providers()


def get_provider_for_target(target: str) -> ServerProvider | None:
    for provider in get_all_providers():
        if provider.matches(target):
            return provider
    return None

