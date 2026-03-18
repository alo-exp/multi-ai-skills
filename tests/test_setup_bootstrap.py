"""
Bootstrap and dependency setup tests.

TC-SETUP-1: .venv exists with playwright + openpyxl importable
TC-SETUP-3: setup.sh is idempotent (re-run exits 0, venv already exists path)
TC-VENV-1:  orchestrator SKILL.md Phase 1 contains 'bash setup.sh' instruction
TC-HOOK-1:  hooks/hooks.json has SessionStart hook referencing install.sh
TC-HOOK-2:  hooks/hooks.json uses .installed sentinel
TC-INSTALL: install.sh delegates to setup.sh
TC-LAUNCH-1: launch_report.py --no-browser outputs URL-encoded path
TC-LAUNCH-2: launch_report.py handles port-already-in-use gracefully
"""

import importlib
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

# ── Repo root detection ────────────────────────────────────────────────────────
TESTS_DIR = Path(__file__).parent
REPO_ROOT = TESTS_DIR.parent
ENGINE_DIR = REPO_ROOT / "skills" / "orchestrator" / "engine"
VENV_DIR = ENGINE_DIR / ".venv"
VENV_PYTHON = VENV_DIR / "bin" / "python"
SETUP_SH = REPO_ROOT / "setup.sh"
INSTALL_SH = REPO_ROOT / "install.sh"
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"
ORCHESTRATOR_SKILL = REPO_ROOT / "skills" / "orchestrator" / "SKILL.md"
LAUNCH_REPORT = REPO_ROOT / "skills" / "landscape-researcher" / "launch_report.py"


# ── TC-SETUP-1 ─────────────────────────────────────────────────────────────────
class TestVenvExists:
    def test_venv_directory_exists(self):
        """TC-SETUP-1a: .venv directory must exist after setup.sh is run."""
        assert VENV_DIR.is_dir(), (
            f".venv not found at {VENV_DIR}. Run: bash setup.sh"
        )

    def test_venv_python_executable(self):
        """TC-SETUP-1b: .venv must have a working python executable."""
        assert VENV_PYTHON.is_file(), f"No python in .venv at {VENV_PYTHON}"
        result = subprocess.run(
            [str(VENV_PYTHON), "--version"], capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Python 3" in result.stdout + result.stderr

    def test_playwright_importable_in_venv(self):
        """TC-SETUP-1c: playwright must be importable in the .venv."""
        result = subprocess.run(
            [str(VENV_PYTHON), "-c", "import playwright; print('ok')"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"playwright not importable in .venv.\nstderr: {result.stderr}"
        )

    def test_openpyxl_importable_in_venv(self):
        """TC-SETUP-1d: openpyxl must be importable in the .venv."""
        result = subprocess.run(
            [str(VENV_PYTHON), "-c", "import openpyxl; print('ok')"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"openpyxl not importable in .venv.\nstderr: {result.stderr}"
        )


# ── TC-SETUP-3 ─────────────────────────────────────────────────────────────────
class TestSetupIdempotency:
    def test_setup_sh_reruns_cleanly(self):
        """TC-SETUP-3: setup.sh re-run with existing .venv exits 0."""
        assert VENV_DIR.is_dir(), "Skip: run bash setup.sh first"
        result = subprocess.run(
            ["bash", str(SETUP_SH)],
            capture_output=True, text=True, timeout=120,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, (
            f"setup.sh exited {result.returncode} on re-run.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}"
        )
        assert "Existing .venv Python" in result.stdout

    def test_setup_sh_bash_syntax(self):
        """TC-SETUP-3b: setup.sh must have valid bash syntax."""
        result = subprocess.run(
            ["bash", "-n", str(SETUP_SH)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"bash -n failed: {result.stderr}"

    def test_install_sh_bash_syntax(self):
        """TC-SETUP-3c: install.sh must have valid bash syntax."""
        result = subprocess.run(
            ["bash", "-n", str(INSTALL_SH)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"bash -n failed: {result.stderr}"


# ── TC-VENV-1 ─────────────────────────────────────────────────────────────────
class TestVenvCheck:
    def test_orchestrator_skill_has_venv_check(self):
        """TC-VENV-1a: orchestrator SKILL.md must contain venv check command."""
        content = ORCHESTRATOR_SKILL.read_text()
        assert ".venv/bin/python" in content or "/.venv" in content, (
            "SKILL.md Phase 1 should check for .venv existence"
        )

    def test_orchestrator_skill_has_setup_instruction(self):
        """TC-VENV-1b: orchestrator SKILL.md Phase 1 must reference bash setup.sh."""
        content = ORCHESTRATOR_SKILL.read_text()
        assert "bash setup.sh" in content, (
            "SKILL.md Phase 1 must tell user to run 'bash setup.sh' if .venv missing"
        )

    def test_orchestrator_skill_has_venv_missing_message(self):
        """TC-VENV-1c: SKILL.md must say 'venv MISSING' or equivalent."""
        content = ORCHESTRATOR_SKILL.read_text()
        assert "venv MISSING" in content or "venv OK" in content, (
            "SKILL.md should show a clear venv check output message"
        )


# ── TC-HOOK-1 + TC-HOOK-2 ─────────────────────────────────────────────────────
class TestPluginHook:
    def test_hooks_json_has_session_start(self):
        """TC-HOOK-1: hooks.json must define a SessionStart hook."""
        import json
        hooks = json.loads(HOOKS_JSON.read_text())
        assert "SessionStart" in hooks.get("hooks", {}), (
            "hooks.json must have a SessionStart hook"
        )

    def test_hooks_json_references_install_sh(self):
        """TC-HOOK-1: SessionStart hook must invoke install.sh."""
        content = HOOKS_JSON.read_text()
        assert "install.sh" in content, (
            "hooks.json must reference install.sh"
        )

    def test_hooks_json_has_installed_sentinel(self):
        """TC-HOOK-2: SessionStart hook must use .installed sentinel."""
        content = HOOKS_JSON.read_text()
        assert ".installed" in content, (
            "hooks.json must reference .installed sentinel to prevent re-runs"
        )

    def test_install_sh_delegates_to_setup_sh(self):
        """TC-INSTALL: install.sh must delegate to setup.sh."""
        content = INSTALL_SH.read_text()
        assert "setup.sh" in content, (
            "install.sh must delegate to setup.sh"
        )


# ── TC-LAUNCH-1 ───────────────────────────────────────────────────────────────
class TestLaunchReportNoBrowser:
    def test_outputs_url_encoded_path(self):
        """TC-LAUNCH-1: --no-browser must print URL-encoded preview.html path."""
        result = subprocess.run(
            [
                sys.executable, str(LAUNCH_REPORT),
                "--report-dir", "test-dir",
                "--report-file", "Test Report.md",
                "--no-browser",
                "--port", "19788",
            ],
            capture_output=True, text=True, timeout=15,
            cwd=str(REPO_ROOT),
        )
        combined = result.stdout + result.stderr
        assert "preview.html" in combined, "URL must contain preview.html"
        assert "Test%20Report" in combined, "Spaces must be URL-encoded as %20"
        assert result.returncode == 0

    def test_url_contains_report_param(self):
        """TC-LAUNCH-1b: URL must include ?report= parameter."""
        result = subprocess.run(
            [
                sys.executable, str(LAUNCH_REPORT),
                "--report-dir", "my-run",
                "--report-file", "My Report.md",
                "--no-browser",
                "--port", "19789",
            ],
            capture_output=True, text=True, timeout=15,
            cwd=str(REPO_ROOT),
        )
        combined = result.stdout + result.stderr
        assert "?report=" in combined


# ── TC-LAUNCH-2 ───────────────────────────────────────────────────────────────
class TestLaunchReportPortInUse:
    def test_handles_port_in_use_gracefully(self):
        """TC-LAUNCH-2: When port is in use, script must not crash and must print URL."""
        TEST_PORT = 19790
        # Bind the port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", TEST_PORT))
        sock.listen(1)
        try:
            result = subprocess.run(
                [
                    sys.executable, str(LAUNCH_REPORT),
                    "--report-dir", "test",
                    "--report-file", "Test.md",
                    "--no-browser",
                    "--port", str(TEST_PORT),
                ],
                capture_output=True, text=True, timeout=15,
                cwd=str(REPO_ROOT),
            )
        finally:
            sock.close()

        combined = result.stdout + result.stderr
        assert result.returncode == 0, (
            f"Script should exit 0 even when port is in use.\nOutput: {combined}"
        )
        assert "preview.html" in combined, "Should still print URL when port is in use"
        assert "already in use" in combined.lower() or "in use" in combined.lower(), (
            "Should mention port is already in use"
        )
