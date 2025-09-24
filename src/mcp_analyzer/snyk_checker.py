"""Snyk checker integration for NPX-launched servers.

This module extracts the package behind an NPX command and runs the
`snyk check packages` CLI against it, parsing results into a concise structure.

Note: This relies on the Snyk CLI being installed and authenticated on the
host system. We intentionally keep subprocess boundaries thin so tests can
monkeypatch execution.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .npx_launcher import parse_npx_command


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


class SnykPackageChecker:
    """Runs `snyk check packages` for a given npm package."""

    def __init__(self, snyk_cmd: str = "snyk", timeout: int = 120) -> None:
        self.snyk_cmd = snyk_cmd
        self.timeout = timeout

    def extract_package_from_npx(self, npx_command: str) -> str:
        """Extract the npm package name from an NPX command.

        Example:
            "export TOKEN=1 && npx @scope/tool --flag" -> "@scope/tool"
        """
        clean, _ = parse_npx_command(npx_command)
        parts = shlex.split(clean)
        # Expect form: npx [flags] <package> [args]
        pkg: Optional[str] = None
        for token in parts[1:]:  # skip the 'npx'
            if token.startswith("-"):
                continue
            pkg = token
            break
        if not pkg:
            raise ValueError(f"Failed to extract package from NPX command: {npx_command}")
        return pkg

    def build_command(
        self,
        package: str,
        *,
        severity_threshold: Optional[str] = None,
        include_dev: bool = False,
    ) -> List[str]:
        """Construct the Snyk CLI invocation.

        We default to JSON output so callers can parse regardless of exit code.
        """
        cmd = [self.snyk_cmd, "check", "packages", package, "--json"]
        if severity_threshold:
            cmd.append(f"--severity-threshold={severity_threshold}")
        if include_dev:
            cmd.append("--dev")
        return cmd

    def _run_snyk(self, cmd: List[str]) -> Dict[str, Any]:
        """Execute Snyk and parse JSON output.

        Snyk returns non-zero when vulnerabilities are found, so we always
        attempt to parse stdout regardless of return code.
        """
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise SnykNotInstalledError(
                f"Snyk CLI not found: {cmd[0]}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SnykExecutionError(
                f"Snyk command timed out after {self.timeout}s"
            ) from exc

        stdout = proc.stdout.strip()
        if not stdout:
            # Snyk errors may be in stderr; surface a concise message
            raise SnykExecutionError(
                f"Snyk produced no JSON output. Stderr: {proc.stderr.strip()}"
            )

        try:
            # Some Snyk outputs are arrays; normalize into dict
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise SnykExecutionError(f"Failed to parse Snyk JSON: {exc}") from exc
        return {"data": data, "returncode": proc.returncode}

    def _normalize_issues(self, payload: Dict[str, Any]) -> List[SnykIssue]:
        """Normalize Snyk output into a list of SnykIssue.

        We support a minimal shape so unit tests can simulate the structure.
        """
        data = payload.get("data")
        issues: List[SnykIssue] = []

        # Accept a top-level dict with `issues` or a raw list of issues
        raw_issues: List[Dict[str, Any]]
        if isinstance(data, dict) and isinstance(data.get("issues"), list):
            raw_issues = data["issues"]
        elif isinstance(data, list):
            raw_issues = data
        else:
            raw_issues = []

        for item in raw_issues:
            issues.append(
                SnykIssue(
                    id=str(item.get("id") or item.get("issueId") or "unknown"),
                    title=str(item.get("title") or item.get("problem") or ""),
                    severity=str(item.get("severity") or "unknown"),
                    package=item.get("package"),
                    version=item.get("version"),
                    cves=item.get("cves"),
                    url=item.get("url") or item.get("identifierUrl"),
                )
            )
        return issues

    def check_npx_command(
        self,
        npx_command: str,
        *,
        severity_threshold: Optional[str] = None,
        include_dev: bool = False,
    ) -> Dict[str, Any]:
        """Run Snyk for the package behind an NPX command and summarize results."""
        package = self.extract_package_from_npx(npx_command)
        cmd = self.build_command(
            package, severity_threshold=severity_threshold, include_dev=include_dev
        )
        payload = self._run_snyk(cmd)
        issues = self._normalize_issues(payload)

        summary: Dict[str, int] = {}
        for issue in issues:
            sev = issue.severity.lower()
            summary[sev] = summary.get(sev, 0) + 1

        return {
            "package": package,
            "summary": summary,
            "issues": [issue.__dict__ for issue in issues],
            "raw": payload.get("data"),
        }

