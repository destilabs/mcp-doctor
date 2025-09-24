"""Snyk checker integration for NPX-launched servers.

This module extracts the package behind an NPX command and runs the Snyk CLI
(`snyk test npm:<package> --json`) against it, parsing results into a concise
structure.

Note: This relies on the Snyk CLI being installed and authenticated on the
host system. Subprocess boundaries are kept thin for easy test monkeypatching.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, Dict, List, Optional

from .snyk_types import SnykExecutionError, SnykNotInstalledError, SnykIssue
from .snyk_extract import extract_package_from_npx
from .snyk_json import parse_json_loose, normalize_issues


class SnykPackageChecker:
    """Runs `snyk test npm:<package> --json` for a given npm package."""

    def __init__(self, snyk_cmd: str = "snyk", timeout: int = 120) -> None:
        self.snyk_cmd = snyk_cmd
        self.timeout = timeout

    def extract_package_from_npx(self, npx_command: str) -> str:
        return extract_package_from_npx(npx_command)

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
        # Use the purl-like npm spec for direct package tests
        package_spec = f"npm:{package}"
        cmd = [self.snyk_cmd, "test", package_spec, "--json"]
        if severity_threshold:
            cmd.append(f"--severity-threshold={severity_threshold}")
        if include_dev:
            cmd.append("--dev")
        return cmd

    # Fallback method removed for simplicity and predictability.

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
            data = parse_json_loose(stdout)
        except json.JSONDecodeError as exc:
            preview = stdout[:200].replace("\n", " ")
            raise SnykExecutionError(
                f"Failed to parse Snyk JSON: {exc}. Stdout preview: {preview!r}"
            ) from exc
        return {"data": data, "returncode": proc.returncode}

    def _normalize_issues(self, payload: Dict[str, Any]) -> List[SnykIssue]:
        """Normalize Snyk output into a list of SnykIssue.

        We support a minimal shape so unit tests can simulate the structure.
        """
        data = payload.get("data")
        return normalize_issues(data)

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
