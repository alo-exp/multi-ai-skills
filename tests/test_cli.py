"""Unit tests for cli.py beyond what test_orchestrator_args.py covers.

Covers: show_budget, _resolve_output_dir edge cases, main().
"""

import sys
import types
import unittest.mock
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

ENGINE_DIR = str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine")


def _import_cli():
    """Import cli module with all side-effecting dependencies neutralised."""
    # Remove existing cli to force fresh import
    for key in list(sys.modules.keys()):
        if key in ("cli",):
            del sys.modules[key]

    if ENGINE_DIR not in sys.path:
        sys.path.insert(0, ENGINE_DIR)

    # Stub engine_setup
    mock_engine_setup = types.ModuleType("engine_setup")
    mock_engine_setup._load_dotenv = lambda: None
    mock_engine_setup._ensure_venv = lambda: None
    mock_engine_setup._ensure_dependencies = lambda: None
    sys.modules["engine_setup"] = mock_engine_setup

    # Stub heavy runtime deps
    for mod_name in ("playwright", "playwright.async_api", "agent_fallback",
                     "browser_use", "anthropic"):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    import os
    # Reuse existing platforms package if it already has __path__ (is a real package
    # stub), to avoid breaking submodule attribute lookups in concurrent test files.
    existing_platforms = sys.modules.get("platforms")
    if existing_platforms is None or not hasattr(existing_platforms, "__path__"):
        mock_platforms = types.ModuleType("platforms")
        mock_platforms.__path__ = [os.path.join(ENGINE_DIR, "platforms")]
        mock_platforms.__package__ = "platforms"
        sys.modules["platforms"] = mock_platforms
    else:
        mock_platforms = existing_platforms
    mock_platforms.ALL_PLATFORMS = {
        "claude_ai": MagicMock(),
        "chatgpt": MagicMock(),
    }

    import cli
    sys.modules.pop("engine_setup", None)
    return cli


_cli = _import_cli()


class TestParseArgs:
    """Tests for parse_args() — exercises lines 31-80."""

    def test_parse_args_prompt_text(self):
        """parse_args accepts --prompt text."""
        with patch("sys.argv", ["cli.py", "--prompt", "hello world"]):
            args = _cli.parse_args()
        assert args.prompt == "hello world"
        assert args.mode == "REGULAR"
        assert args.tier == "free"

    def test_parse_args_prompt_file(self, tmp_path):
        """parse_args accepts --prompt-file path."""
        p = tmp_path / "p.md"
        p.write_text("content")
        with patch("sys.argv", ["cli.py", "--prompt-file", str(p)]):
            args = _cli.parse_args()
        assert args.prompt_file == str(p)

    def test_parse_args_mode_deep(self):
        """parse_args accepts --mode DEEP."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--mode", "deep"]):
            args = _cli.parse_args()
        assert args.mode == "DEEP"

    def test_parse_args_budget_flag(self):
        """parse_args accepts --budget flag."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--budget"]):
            args = _cli.parse_args()
        assert args.budget is True

    def test_parse_args_tier_paid(self):
        """parse_args accepts --tier paid."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--tier", "paid"]):
            args = _cli.parse_args()
        assert args.tier == "paid"

    def test_parse_args_task_name(self):
        """parse_args accepts --task-name."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--task-name", "my-run"]):
            args = _cli.parse_args()
        assert args.task_name == "my-run"

    def test_parse_args_condensed_prompt(self):
        """parse_args accepts --condensed-prompt."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--condensed-prompt", "short"]):
            args = _cli.parse_args()
        assert args.condensed_prompt == "short"

    def test_parse_args_prompt_sigs(self):
        """parse_args accepts --prompt-sigs."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--prompt-sigs", "A,B"]):
            args = _cli.parse_args()
        assert args.prompt_sigs == "A,B"

    def test_parse_args_headless_flag(self):
        """parse_args accepts --headless."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--headless"]):
            args = _cli.parse_args()
        assert args.headless is True

    def test_parse_args_fresh_flag(self):
        """parse_args accepts --fresh."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--fresh"]):
            args = _cli.parse_args()
        assert args.fresh is True

    def test_parse_args_followup_flag(self):
        """parse_args accepts --followup."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--followup"]):
            args = _cli.parse_args()
        assert args.followup is True

    def test_parse_args_skip_rate_check(self):
        """parse_args accepts --skip-rate-check."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--skip-rate-check"]):
            args = _cli.parse_args()
        assert args.skip_rate_check is True

    def test_parse_args_platforms(self):
        """parse_args accepts --platforms."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--platforms", "claude_ai,chatgpt"]):
            args = _cli.parse_args()
        assert args.platforms == "claude_ai,chatgpt"

    def test_parse_args_stagger_delay(self):
        """parse_args accepts --stagger-delay."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--stagger-delay", "10"]):
            args = _cli.parse_args()
        assert args.stagger_delay == 10

    def test_parse_args_chrome_profile(self):
        """parse_args accepts --chrome-profile."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--chrome-profile", "Work"]):
            args = _cli.parse_args()
        assert args.chrome_profile == "Work"

    def test_sanitise_chrome_profile_clean(self):
        """_sanitise_chrome_profile allows alphanumeric, hyphen, underscore, space."""
        assert _cli._sanitise_chrome_profile("MultAI-2 Work") == "MultAI-2 Work"

    def test_sanitise_chrome_profile_strips_special(self):
        """_sanitise_chrome_profile replaces invalid chars with hyphen."""
        assert _cli._sanitise_chrome_profile("../../bad") == "------bad"

    def test_sanitise_chrome_profile_empty_fallback(self):
        """_sanitise_chrome_profile falls back to 'MultAI' when result is empty after strip."""
        assert _cli._sanitise_chrome_profile("   ") == "MultAI"

    def test_parse_args_output_dir(self):
        """parse_args accepts --output-dir."""
        with patch("sys.argv", ["cli.py", "--prompt", "x", "--output-dir", "/tmp/out"]):
            args = _cli.parse_args()
        assert args.output_dir == "/tmp/out"

    def test_parse_args_condensed_prompt_file(self, tmp_path):
        """parse_args accepts --condensed-prompt-file."""
        p = tmp_path / "c.md"
        p.write_text("short")
        with patch("sys.argv", ["cli.py", "--prompt", "x",
                                 "--condensed-prompt-file", str(p)]):
            args = _cli.parse_args()
        assert args.condensed_prompt_file == str(p)


class TestShowBudget:
    """Tests for show_budget()."""

    def test_show_budget_prints_table(self, capsys):
        """show_budget prints the rate limit budget table."""
        args = MagicMock()
        args.tier = "free"
        args.mode = "REGULAR"

        mock_summary = {
            "claude_ai": {
                "display_name": "Claude.ai",
                "remaining": 10,
                "total": 12,
                "next_available_in": 0,
                "cooldown": 300,
                "daily_cap": 0,
                "tier": "free",
                "notes": "test",
            }
        }

        mock_limiter = MagicMock()
        mock_limiter.get_budget_summary.return_value = mock_summary

        with patch("cli.RateLimiter", return_value=mock_limiter):
            _cli.show_budget(args)

        captured = capsys.readouterr()
        assert "Rate Limit Budget" in captured.out
        assert "Claude.ai" in captured.out

    def test_show_budget_next_available_in_seconds(self, capsys):
        """show_budget shows 'in Xs' when next_available_in > 0."""
        args = MagicMock()
        args.tier = "free"
        args.mode = "REGULAR"

        mock_summary = {
            "claude_ai": {
                "display_name": "Claude.ai",
                "remaining": 0,
                "total": 12,
                "next_available_in": 120,
                "cooldown": 300,
                "daily_cap": 0,
                "tier": "free",
                "notes": "",
            }
        }
        mock_limiter = MagicMock()
        mock_limiter.get_budget_summary.return_value = mock_summary

        with patch("cli.RateLimiter", return_value=mock_limiter):
            _cli.show_budget(args)

        captured = capsys.readouterr()
        assert "in 120s" in captured.out

    def test_show_budget_cooldown_minutes(self, capsys):
        """show_budget shows cooldown in minutes when >= 60s."""
        args = MagicMock()
        args.tier = "free"
        args.mode = "REGULAR"

        mock_summary = {
            "claude_ai": {
                "display_name": "Claude.ai",
                "remaining": 10,
                "total": 12,
                "next_available_in": 0,
                "cooldown": 300,  # 5 minutes
                "daily_cap": 0,
                "tier": "free",
                "notes": "",
            }
        }
        mock_limiter = MagicMock()
        mock_limiter.get_budget_summary.return_value = mock_summary

        with patch("cli.RateLimiter", return_value=mock_limiter):
            _cli.show_budget(args)

        captured = capsys.readouterr()
        assert "5m" in captured.out

    def test_show_budget_cooldown_seconds_when_lt_60(self, capsys):
        """show_budget shows cooldown in seconds when < 60."""
        args = MagicMock()
        args.tier = "free"
        args.mode = "REGULAR"

        mock_summary = {
            "claude_ai": {
                "display_name": "Claude.ai",
                "remaining": 10,
                "total": 12,
                "next_available_in": 0,
                "cooldown": 30,
                "daily_cap": 0,
                "tier": "free",
                "notes": "",
            }
        }
        mock_limiter = MagicMock()
        mock_limiter.get_budget_summary.return_value = mock_summary

        with patch("cli.RateLimiter", return_value=mock_limiter):
            _cli.show_budget(args)

        captured = capsys.readouterr()
        assert "30s" in captured.out


class TestResolveOutputDir:
    """Tests for _resolve_output_dir."""

    def test_resolve_output_dir_outside_project_exits(self):
        """_resolve_output_dir exits(1) when output_dir is outside project root."""
        import pytest
        args = MagicMock()
        args.task_name = ""
        args.output_dir = "/tmp/outside_project_dir"

        with pytest.raises(SystemExit) as exc_info:
            _cli._resolve_output_dir(args)
        assert exc_info.value.code == 1

    def test_resolve_output_dir_with_task_name(self):
        """_resolve_output_dir uses reports/<task_name> when task_name set."""
        args = MagicMock()
        args.task_name = "my-run"
        args.output_dir = ""

        result = _cli._resolve_output_dir(args)
        assert result.endswith("reports/my-run")

    def test_resolve_output_dir_sanitizes_task_name(self):
        """_resolve_output_dir sanitizes special chars in task_name."""
        args = MagicMock()
        args.task_name = "my run: test!"
        args.output_dir = ""

        result = _cli._resolve_output_dir(args)
        # Special chars replaced with '-'
        assert ":" not in result
        assert "!" not in result

    def test_resolve_output_dir_default_within_project(self):
        """_resolve_output_dir returns output_dir when within project root."""
        args = MagicMock()
        args.task_name = ""
        # Use the actual reports dir within the project
        project_root = Path(__file__).parent.parent
        args.output_dir = str(project_root / "reports")

        result = _cli._resolve_output_dir(args)
        assert result == str(project_root / "reports")


class TestMain:
    """Tests for main()."""

    def test_main_budget_flag_exits_zero(self):
        """main() calls show_budget and exits(0) when --budget flag set."""
        import pytest

        mock_args = MagicMock()
        mock_args.budget = True
        mock_args.task_name = ""
        mock_args.output_dir = str(Path(__file__).parent.parent / "reports")
        mock_args.mode = "REGULAR"
        mock_args.tier = "free"

        with patch.object(_cli, "parse_args", return_value=mock_args), \
             patch.object(_cli, "_resolve_output_dir", return_value="/tmp/out"), \
             patch.object(_cli, "show_budget") as mock_show_budget, \
             pytest.raises(SystemExit) as exc_info:
            _cli.main()

        mock_show_budget.assert_called_once_with(mock_args)
        assert exc_info.value.code == 0

    def test_main_runs_orchestrate(self):
        """main() calls orchestrate and write_status when not --budget."""
        import pytest
        import asyncio

        mock_args = MagicMock()
        mock_args.budget = False
        mock_args.task_name = "test"
        mock_args.output_dir = ""
        mock_args.mode = "REGULAR"
        mock_args.tier = "free"
        mock_args.prompt_file = None

        mock_results = [{"status": "complete"}]

        mock_orchestrate = MagicMock(return_value=mock_results)
        mock_write_status = MagicMock()
        mock_collate = MagicMock()

        mock_orchestrator_mod = types.ModuleType("orchestrator")
        mock_orchestrator_mod.orchestrate = mock_orchestrate
        mock_orchestrator_mod.write_status = mock_write_status

        mock_collate_mod = types.ModuleType("collate_responses")
        mock_collate_mod.collate = mock_collate

        with patch.object(_cli, "parse_args", return_value=mock_args), \
             patch.object(_cli, "_resolve_output_dir", return_value="/tmp/out"), \
             patch("asyncio.run", return_value=mock_results), \
             patch.dict(sys.modules, {
                 "orchestrator": mock_orchestrator_mod,
                 "collate_responses": mock_collate_mod,
             }), \
             pytest.raises(SystemExit) as exc_info:
            _cli.main()

        assert exc_info.value.code == 0

    def test_main_cleans_temp_prompt(self, tmp_path):
        """main() deletes /tmp/ prompt file after orchestration."""
        import pytest

        # Create a file explicitly under /tmp/ so the startswith("/tmp/") check passes
        tmp_prompt_path = Path("/tmp/_multai_test_prompt_cleanup.md")
        tmp_prompt_path.write_text("test prompt", encoding="utf-8")
        tmp_path_str = str(tmp_prompt_path)

        assert Path(tmp_path_str).exists()

        mock_args = MagicMock()
        mock_args.budget = False
        mock_args.task_name = ""
        mock_args.output_dir = str(Path(__file__).parent.parent / "reports")
        mock_args.mode = "REGULAR"
        mock_args.prompt_file = tmp_path_str

        mock_results = [{"status": "complete"}]

        mock_orchestrator_mod = types.ModuleType("orchestrator")
        mock_orchestrator_mod.orchestrate = MagicMock(return_value=mock_results)
        mock_orchestrator_mod.write_status = MagicMock()

        mock_collate_mod = types.ModuleType("collate_responses")
        mock_collate_mod.collate = MagicMock()

        with patch.object(_cli, "parse_args", return_value=mock_args), \
             patch.object(_cli, "_resolve_output_dir", return_value=str(Path(__file__).parent.parent / "reports")), \
             patch("asyncio.run", return_value=mock_results), \
             patch.dict(sys.modules, {
                 "orchestrator": mock_orchestrator_mod,
                 "collate_responses": mock_collate_mod,
             }), \
             pytest.raises(SystemExit):
            _cli.main()

        assert not Path(tmp_path_str).exists()

    def test_main_exit_code_failure_when_all_failed(self):
        """main() exits(1) when no platforms completed."""
        import pytest

        mock_args = MagicMock()
        mock_args.budget = False
        mock_args.task_name = ""
        mock_args.output_dir = str(Path(__file__).parent.parent / "reports")
        mock_args.mode = "REGULAR"
        mock_args.prompt_file = None

        mock_results = [{"status": "failed"}, {"status": "failed"}]

        mock_orchestrator_mod = types.ModuleType("orchestrator")
        mock_orchestrator_mod.orchestrate = MagicMock(return_value=mock_results)
        mock_orchestrator_mod.write_status = MagicMock()

        mock_collate_mod = types.ModuleType("collate_responses")
        mock_collate_mod.collate = MagicMock()

        with patch.object(_cli, "parse_args", return_value=mock_args), \
             patch.object(_cli, "_resolve_output_dir", return_value=str(Path(__file__).parent.parent / "reports")), \
             patch("asyncio.run", return_value=mock_results), \
             patch.dict(sys.modules, {
                 "orchestrator": mock_orchestrator_mod,
                 "collate_responses": mock_collate_mod,
             }), \
             pytest.raises(SystemExit) as exc_info:
            _cli.main()

        assert exc_info.value.code == 1

    def test_main_cleans_temp_prompt_oserror_silenced(self):
        """main() silently ignores OSError when deleting temp prompt file."""
        import pytest

        tmp_prompt_path = Path("/tmp/_multai_test_prompt_oserror.md")
        tmp_prompt_path.write_text("test prompt", encoding="utf-8")
        tmp_path_str = str(tmp_prompt_path)

        mock_args = MagicMock()
        mock_args.budget = False
        mock_args.task_name = ""
        mock_args.output_dir = str(Path(__file__).parent.parent / "reports")
        mock_args.mode = "REGULAR"
        mock_args.prompt_file = tmp_path_str

        mock_results = [{"status": "complete"}]

        mock_orchestrator_mod = types.ModuleType("orchestrator")
        mock_orchestrator_mod.orchestrate = MagicMock(return_value=mock_results)
        mock_orchestrator_mod.write_status = MagicMock()

        mock_collate_mod = types.ModuleType("collate_responses")
        mock_collate_mod.collate = MagicMock()

        with patch.object(_cli, "parse_args", return_value=mock_args), \
             patch.object(_cli, "_resolve_output_dir", return_value=str(Path(__file__).parent.parent / "reports")), \
             patch("asyncio.run", return_value=mock_results), \
             patch.dict(sys.modules, {
                 "orchestrator": mock_orchestrator_mod,
                 "collate_responses": mock_collate_mod,
             }), \
             patch("cli.Path") as mock_path_cls, \
             pytest.raises(SystemExit):
            # Make Path(prompt_file).exists() return True, unlink() raise OSError
            mock_path_inst = MagicMock()
            mock_path_inst.exists.return_value = True
            mock_path_inst.__str__ = lambda self: tmp_path_str
            mock_path_inst.unlink.side_effect = OSError("permission denied")
            mock_path_cls.return_value = mock_path_inst
            _cli.main()
        # No exception propagated — test passes if we reach here
        tmp_prompt_path.unlink(missing_ok=True)

    def test_main_warns_when_default_profile_used(self, caplog):
        """main() emits a warning when chrome_profile is 'Default'."""
        import logging
        import pytest

        mock_args = MagicMock()
        mock_args.budget = True          # exit early — no orchestrate needed
        mock_args.chrome_profile = "Default"
        mock_args.task_name = ""
        mock_args.output_dir = str(Path(__file__).parent.parent / "reports")
        mock_args.mode = "REGULAR"
        mock_args.tier = "free"

        with patch.object(_cli, "parse_args", return_value=mock_args), \
             patch.object(_cli, "_resolve_output_dir", return_value="/tmp/out"), \
             patch.object(_cli, "show_budget"), \
             caplog.at_level(logging.WARNING, logger="cli"), \
             pytest.raises(SystemExit):
            _cli.main()

        assert any("Default" in rec.message for rec in caplog.records)
