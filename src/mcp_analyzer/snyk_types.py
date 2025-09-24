from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


class SnykExecutionError(Exception):
    """Raised when invoking the Snyk CLI fails unexpectedly."""


class SnykNotInstalledError(Exception):
    """Raised when the Snyk CLI is not available on PATH."""


@dataclass
class SnykIssue:
    """Normalized representation of a vulnerability from Snyk output."""

    id: str
    title: str
    severity: str
    package: Optional[str] = None
    version: Optional[str] = None
    cves: Optional[List[str]] = None
    url: Optional[str] = None

