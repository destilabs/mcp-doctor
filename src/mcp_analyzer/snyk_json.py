from __future__ import annotations

import json
from typing import Any, Dict, List

from .snyk_types import SnykIssue


def parse_json_loose(text: str) -> Any:
    """Parse JSON content, trimming any non-JSON prelude.

    Some Snyk versions may emit log lines before the JSON payload; we locate the
    first '{' or '[' and parse from there.
    """
    s = text.lstrip()
    idxs = [i for i in (s.find("{"), s.find("[")) if i != -1]
    start = min(idxs) if idxs else -1
    if start > 0:
        s = s[start:]
    return json.loads(s)


def normalize_issues(data: Any) -> List[SnykIssue]:
    """Normalize various Snyk JSON shapes into a list of SnykIssue objects."""
    issues: List[SnykIssue] = []

    # Collect raw issue dicts
    raw: List[Dict[str, Any]] = []
    if isinstance(data, dict):
        if isinstance(data.get("vulnerabilities"), list):
            raw = data["vulnerabilities"]  # type: ignore[assignment]
        elif isinstance(data.get("issues"), list):
            raw = data["issues"]  # type: ignore[assignment]
        elif isinstance(data.get("issues"), dict) and isinstance(
            data["issues"].get("vulnerabilities"), list
        ):
            raw = data["issues"]["vulnerabilities"]  # type: ignore[index]
        elif isinstance(data.get("results"), list):
            for entry in data["results"]:  # type: ignore[index]
                if not isinstance(entry, dict):
                    continue
                if isinstance(entry.get("vulnerabilities"), list):
                    raw.extend(entry["vulnerabilities"])  # type: ignore[index]
                elif isinstance(entry.get("issues"), list):
                    raw.extend(entry["issues"])  # type: ignore[index]
                elif isinstance(entry.get("issues"), dict) and isinstance(
                    entry["issues"].get("vulnerabilities"), list
                ):
                    raw.extend(entry["issues"]["vulnerabilities"])  # type: ignore[index]
    elif isinstance(data, list):
        raw = data

    for item in raw:
        pkg = item.get("package") or item.get("packageName") or item.get("pkgName")
        ver = item.get("version") or item.get("pkgVersion")
        identifiers = item.get("identifiers") or {}
        cves = item.get("cves") or identifiers.get("CVE")
        url = item.get("url") or item.get("identifierUrl") or item.get("idUrl")
        issues.append(
            SnykIssue(
                id=str(item.get("id") or item.get("issueId") or "unknown"),
                title=str(item.get("title") or item.get("problem") or ""),
                severity=str(item.get("severity") or "unknown"),
                package=pkg,
                version=ver,
                cves=cves,
                url=url,
            )
        )

    return issues

