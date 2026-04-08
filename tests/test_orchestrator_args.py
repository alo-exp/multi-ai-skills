"""Unit tests for orchestrator argument parsing.

Tests UT-OR-01 through UT-OR-12.

NOTE: parse_args and _resolve_output_dir live in cli.py (engine package).
      cli.py imports engine_setup at module level and calls _ensure_venv()
      and _ensure_dependencies().  We stub those out via sys.modules before
      importing cli so the side effects never fire.
"""

import sys
import types
import unittest.mock
from pathlib import Path

# Engine directory
ENGINE_DIR = str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine")


def _import_cli():
    """Import cli module with all side-effecting dependencies neutralised."""
    if "cli" in sys.modules:
        return sys.modules["cli"]

    # Add engine dir to path so that `import cli` finds the right file
    if ENGINE_DIR not in sys.path:
        sys.path.insert(0, ENGINE_DIR)

    # --- Stub engine_setup to prevent venv/dependency bootstrap ---
    mock_engine_setup = types.ModuleType("engine_setup")
    mock_engine_setup._load_dotenv = lambda: None
    mock_engine_setup._ensure_venv = lambda: None
    mock_engine_setup._ensure_dependencies = lambda: None
    sys.modules["engine_setup"] = mock_engine_setup

    # --- Stub heavy runtime deps ---
    for mod_name in ("playwright", "playwright.async_api", "agent_fallback",
                     "browser_use", "anthropic"):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    mock_platforms = types.ModuleType("platforms")
    mock_platforms.ALL_PLATFORMS = {
        "claude_ai": unittest.mock.MagicMock(),
        "chatgpt": unittest.mock.MagicMock(),
        "copilot": unittest.mock.MagicMock(),
        "perplexity": unittest.mock.MagicMock(),
        "grok": unittest.mock.MagicMock(),
        "deepseek": unittest.mock.MagicMock(),
        "gemini": unittest.mock.MagicMock(),
    }
    sys.modules["platforms"] = mock_platforms

    # config.py, rate_limiter, prompt_loader are real modules in ENGINE_DIR —
    # don't stub them; sys.path already points there so they import fine.

    import cli  # noqa: PLC0415

    # Clean up stub keys that would pollute other test modules.
    # Keep only "cli" and the mocks that are genuinely unavailable at test time.
    for _key in ("engine_setup",):
        sys.modules.pop(_key, None)

    return cli


cli_module = _import_cli()
parse_args = cli_module.parse_args
_resolve_output_dir = cli_module._resolve_output_dir


class TestOrchestratorArgs:
    """Tests for orchestrator parse_args()."""

    def test_ut_or_01_prompt_flag_required(self):
        """UT-OR-01: --prompt or --prompt-file is required."""
        import pytest
        with pytest.raises(SystemExit):
            with unittest.mock.patch("sys.argv", ["orchestrator.py"]):
                parse_args()

    def test_ut_or_02_prompt_text(self):
        """UT-OR-02: --prompt accepts literal text."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "Hello world"]):
            args = parse_args()
        assert args.prompt == "Hello world"
        assert args.prompt_file is None

    def test_ut_or_03_prompt_file(self):
        """UT-OR-03: --prompt-file accepts a file path."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt-file", "/tmp/test.md"]):
            args = parse_args()
        assert args.prompt_file == "/tmp/test.md"
        assert args.prompt is None

    def test_ut_or_04_mode_default_regular(self):
        """UT-OR-04: Default mode is REGULAR."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test"]):
            args = parse_args()
        assert args.mode == "REGULAR"

    def test_ut_or_05_mode_deep(self):
        """UT-OR-05: --mode DEEP is accepted (case insensitive)."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test", "--mode", "deep"]):
            args = parse_args()
        assert args.mode == "DEEP"

    def test_ut_or_06_task_name(self):
        """UT-OR-06: --task-name is stored correctly."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test", "--task-name", "My Run"]):
            args = parse_args()
        assert args.task_name == "My Run"

    def test_ut_or_07_resolve_output_dir_with_task_name(self):
        """UT-OR-07: _resolve_output_dir with task-name returns reports/<task-name>."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test", "--task-name", "My Run"]):
            args = parse_args()
        resolved = _resolve_output_dir(args)
        assert resolved.endswith("reports/My Run"), f"Expected path ending with 'reports/My Run', got: {resolved}"

    def test_ut_or_08_platforms_default_all(self):
        """UT-OR-08: Default --platforms is 'all'."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test"]):
            args = parse_args()
        assert args.platforms == "all"

    def test_ut_or_09_platforms_custom(self):
        """UT-OR-09: --platforms accepts comma-separated list."""
        with unittest.mock.patch("sys.argv", [
            "orchestrator.py", "--prompt", "test",
            "--platforms", "claude_ai,chatgpt"
        ]):
            args = parse_args()
        assert args.platforms == "claude_ai,chatgpt"

    def test_ut_or_10_tier_default_free(self):
        """UT-OR-10: Default tier is 'free'."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test"]):
            args = parse_args()
        assert args.tier == "free"

    def test_ut_or_11_headless_flag(self):
        """UT-OR-11: --headless flag is stored as True."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test", "--headless"]):
            args = parse_args()
        assert args.headless is True

    def test_ut_or_12_followup_flag(self):
        """UT-OR-12: --followup flag defaults to False and is set to True when supplied."""
        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test"]):
            args = parse_args()
        assert args.followup is False

        with unittest.mock.patch("sys.argv", ["orchestrator.py", "--prompt", "test", "--followup"]):
            args = parse_args()
        assert args.followup is True
