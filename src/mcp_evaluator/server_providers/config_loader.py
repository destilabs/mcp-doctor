from __future__ import annotations

import json
from pathlib import Path

from .config_provider import ConfigurableProvider


def load_provider_configs(config_path: Path | str) -> list[ConfigurableProvider]:
    path = Path(config_path)
    if not path.exists():
        return []

    with open(path) as f:
        data = json.load(f)

    providers = []
    for provider_config in data.get("providers", []):
        providers.append(ConfigurableProvider.from_dict(provider_config))

    return providers


def get_default_config_paths() -> list[Path]:
    base_dir = Path(__file__).parent.parent.parent.parent
    return [
        base_dir / "server_providers.json",
        base_dir / "server_providers.local.json",
    ]


def load_all_providers() -> list[ConfigurableProvider]:
    all_providers = []
    for config_path in get_default_config_paths():
        providers = load_provider_configs(config_path)
        all_providers.extend(providers)
    return all_providers

