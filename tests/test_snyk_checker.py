"""Tests for SnykPackageChecker integration and parsing."""

from __future__ import annotations

import json

import pytest

from mcp_analyzer.snyk_checker import (
    SnykExecutionError,
    SnykPackageChecker,
)


def test_extract_package_from_npx_basic() -> None:
    checker = SnykPackageChecker()
    assert checker.extract_package_from_npx("npx some-package") == "some-package"


def test_extract_package_from_npx_with_flags_and_export() -> None:
    checker = SnykPackageChecker()
    cmd = "export TOKEN=abc && npx -y @scope/tool --cli"
    assert checker.extract_package_from_npx(cmd) == "@scope/tool"


def test_build_command_defaults() -> None:
    checker = SnykPackageChecker(snyk_cmd="snyk")
    cmd = checker.build_command("demo-pkg")
    assert cmd[:2] == ["snyk", "test"]
    assert "npm:demo-pkg" in cmd
    assert "--json" in cmd


def test_check_npx_command_parses_issues(monkeypatch) -> None:
    checker = SnykPackageChecker()

    fake_output = {
        "data": {
            # Match common Snyk JSON: vulnerabilities at the top level
            "vulnerabilities": [
                {
                    "id": "ISSUE-1",
                    "title": "Prototype Pollution",
                    "severity": "high",
                    "packageName": "some-package",
                    "pkgVersion": "1.0.0",
                    "identifiers": {"CVE": ["CVE-2024-0001"]},
                },
                {
                    "id": "ISSUE-2",
                    "title": "XSS Risk",
                    "severity": "medium",
                },
            ]
        },
        "returncode": 1,
    }

    def fake_run(cmd):  # type: ignore[no-redef]
        return fake_output

    monkeypatch.setattr(SnykPackageChecker, "_run_snyk", staticmethod(fake_run))

    result = checker.check_npx_command("npx some-package")
    assert result["package"] == "some-package"
    assert result["summary"]["high"] == 1
    assert result["summary"]["medium"] == 1
    assert len(result["issues"]) == 2


def test_run_snyk_handles_bad_json(monkeypatch) -> None:
    checker = SnykPackageChecker()

    class FakeProc:
        def __init__(self) -> None:
            self.stdout = "not-json"
            self.stderr = ""
            self.returncode = 1

    def fake_subprocess_run(*args, **kwargs):  # type: ignore[no-redef]
        return FakeProc()

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    with pytest.raises(SnykExecutionError):
        checker._run_snyk(["snyk", "check", "packages", "x", "--json"])  # type: ignore[arg-type]
