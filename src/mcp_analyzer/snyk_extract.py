from __future__ import annotations

import shlex
from typing import Optional, Tuple, Dict

from .npx_launcher import parse_npx_command


def extract_package_from_npx(npx_command: str) -> str:
    """Extract the npm package name from an NPX command.

    Example:
        "export TOKEN=1 && npx @scope/tool --flag" -> "@scope/tool"
    """
    clean, _env = parse_npx_command(npx_command)
    parts = shlex.split(clean)
    pkg: Optional[str] = None
    for token in parts[1:]:  # skip 'npx'
        if token.startswith("-"):
            continue
        pkg = token
        break
    if not pkg:
        raise ValueError(f"Failed to extract package from NPX command: {npx_command}")
    return pkg

