"""Unit tests for orchestrator.py async functions.

Tests for: _gather_with_timeout, run_single_platform, _staggered_run,
           _launch_chrome, orchestrate, _run_all_platforms, main.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: stub heavy dependencies BEFORE any engine import
# ---------------------------------------------------------------------------

TESTS_DIR = str(Path(__file__).parent)
ENGINE_DIR = str(Path(__file__).parent.parent / "skills" / "orchestrator" / "engine")
for d in (TESTS_DIR, ENGINE_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

# Conftest helpers
from conftest import _stub_engine_setup, install_stubs  # noqa: E402

_stub_engine_setup()

# playwright stubs
_pw = types.ModuleType("playwright")
_pw_api = types.ModuleType("playwright.async_api")
_pw_api.Page = MagicMock
_pw_api.BrowserContext = MagicMock
_mock_async_playwright_cm = MagicMock()
_pw_api.async_playwright = MagicMock(return_value=_mock_async_playwright_cm)
sys.modules["playwright"] = _pw
sys.modules["playwright.async_api"] = _pw_api

# agent_fallback stub
_af = types.ModuleType("agent_fallback")
_af.AgentFallbackManager = MagicMock()
sys.modules["agent_fallback"] = _af

# browser_use stub
_bu = types.ModuleType("browser_use")
sys.modules["browser_use"] = _bu

# anthropic stub
_an = types.ModuleType("anthropic")
sys.modules["anthropic"] = _an

# platforms stub — reuse existing real package if present, else create minimal stub
_existing_platforms = sys.modules.get("platforms")
if _existing_platforms is not None and hasattr(_existing_platforms, "__path__"):
    _platforms_mod = _existing_platforms
else:
    _platforms_mod = types.ModuleType("platforms")
    _platforms_mod.__path__ = [str(Path(ENGINE_DIR) / "platforms")]
    _platforms_mod.__package__ = "platforms"
    sys.modules["platforms"] = _platforms_mod
_platforms_mod.ALL_PLATFORMS = {}  # populated per-test

# Import the real config module directly (it has no heavy deps) and use it
# as the stub base — this avoids polluting RATE_LIMITS, INJECTION_METHODS, etc.
import importlib as _importlib
_real_config = _importlib.import_module("config")

# Build a proxy that wraps the real config but overrides detect_* functions
# (which we want to mock in tests) and adds MagicMock for detect_* defaults.
_config = types.ModuleType("config")
_config.__dict__.update(_real_config.__dict__)
# Override detect functions so tests can patch them on orch module
_config.detect_chrome_executable = MagicMock(return_value="/usr/bin/google-chrome")
_config.detect_chrome_user_data_dir = MagicMock(return_value="/tmp/chrome-data")
sys.modules["config"] = _config

# Do NOT stub prompt_loader globally — patch orch.load_prompts per-test or in fixtures.
# The orchestrator accesses load_prompts via a module-level import, so we patch orch.load_prompts.

# Do NOT stub rate_limiter — let orchestrator import it naturally.
# Define _FakeRateLimiter for use in tests that need to override RateLimiter behavior.

class _FakeRateLimiter:
    def __init__(self, **kw):
        pass

    def load_state(self):
        pass

    def record_usage(self, **kw):
        pass

    def preflight_check(self, platform, mode):
        result = MagicMock()
        result.allowed = True
        return result

    def get_staggered_order(self, names, mode, stagger_delay=5):
        return [(n, 0) for n in names]

# retry_handler stub
_rh = types.ModuleType("retry_handler")
_rh.handle_login_retries = AsyncMock()
_rh.handle_agent_fallbacks = AsyncMock()
sys.modules["retry_handler"] = _rh

# Do NOT stub status_writer or tab_manager — they have no heavy deps and
# can be imported naturally by orchestrator.

# Now import the real orchestrator
import importlib

if "orchestrator" in sys.modules:
    del sys.modules["orchestrator"]

import orchestrator as orch  # noqa: E402


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_platform_cls(result_status="complete", raises=None):
    """Returns a fake platform class whose .run() returns a mock result."""
    result = MagicMock()
    result.platform = "test_platform"
    result.display_name = "Test Platform"
    result.status = result_status
    result.chars = 100
    result.file = "/tmp/test.md"
    result.mode_used = "REGULAR"
    result.error = None
    result.duration_s = 1.5

    cls = MagicMock()
    instance = MagicMock()
    instance.display_name = "Test Platform"
    instance.agent_manager = None
    instance.prompt_sigs = []
    if raises:
        instance.run = AsyncMock(side_effect=raises)
    else:
        instance.run = AsyncMock(return_value=result)
    cls.return_value = instance
    return cls


def _make_args(**kw):
    """Build a minimal args namespace."""
    args = MagicMock()
    args.fresh = False
    args.headless = False
    args.chrome_profile = "MultAI"
    args.platforms = "all"
    args.mode = "REGULAR"
    args.tier = "free"
    args.skip_rate_check = False
    args.stagger_delay = 0
    args.followup = False
    for k, v in kw.items():
        setattr(args, k, v)
    return args


# ---------------------------------------------------------------------------
# Tests: _gather_with_timeout
# ---------------------------------------------------------------------------

class TestGatherWithTimeout:
    async def test_gather_with_timeout_returns_results(self):
        """Fast tasks complete successfully."""
        async def fast():
            return 42

        tasks = [asyncio.create_task(fast()), asyncio.create_task(fast())]
        results = await orch._gather_with_timeout(tasks, global_timeout=5, launched_names=["a", "b"])
        assert results == [42, 42]

    async def test_gather_with_timeout_cancels_on_ceiling(self):
        """Slow task with short timeout yields TimeoutError in results."""
        async def slow():
            await asyncio.sleep(100)
            return "never"

        tasks = [asyncio.create_task(slow())]
        results = await orch._gather_with_timeout(tasks, global_timeout=0.01, launched_names=["slow"])
        assert len(results) == 1
        assert isinstance(results[0], asyncio.TimeoutError)

    async def test_gather_with_timeout_mixed(self):
        """One fast task completes; one slow task times out."""
        async def fast():
            return "done"

        async def slow():
            await asyncio.sleep(100)
            return "never"

        t_fast = asyncio.create_task(fast())
        t_slow = asyncio.create_task(slow())
        # Wait for fast task to complete before setting tiny timeout
        await asyncio.sleep(0.05)
        results = await orch._gather_with_timeout([t_fast, t_slow], global_timeout=0.001, launched_names=["f", "s"])
        assert len(results) == 2
        # fast result is the string
        assert results[0] == "done"
        assert isinstance(results[1], asyncio.TimeoutError)


# ---------------------------------------------------------------------------
# Tests: run_single_platform
# ---------------------------------------------------------------------------

class TestRunSinglePlatform:
    async def test_run_single_platform_success(self):
        """Returns result dict on success."""
        ctx = MagicMock()
        ctx.new_page = AsyncMock(return_value=MagicMock())
        cls = _make_platform_cls()
        with patch.object(orch, "ALL_PLATFORMS", {"myplatform": cls}):
            result = await orch.run_single_platform(
                "myplatform", ctx, "full", "condensed", ["sig"], "REGULAR", "/tmp/out"
            )
        assert result["status"] == "complete"
        assert result["chars"] == 100

    async def test_run_single_platform_uses_condensed(self):
        """use_condensed=True causes condensed prompt to be used."""
        ctx = MagicMock()
        page = MagicMock()
        ctx.new_page = AsyncMock(return_value=page)

        mode_cfg = MagicMock()
        mode_cfg.use_condensed = True
        cls = _make_platform_cls()
        with patch.object(orch, "ALL_PLATFORMS", {"myplatform": cls}), \
             patch.object(orch, "REGULAR_MODE", {"myplatform": mode_cfg}):
            await orch.run_single_platform(
                "myplatform", ctx, "full prompt long", "short condensed", ["sig"], "REGULAR", "/tmp/out"
            )
        # run() was called with condensed prompt
        instance = cls.return_value
        call_args = instance.run.call_args
        assert call_args[0][1] == "short condensed"

    async def test_run_single_platform_reuses_existing_page(self):
        """existing_page is passed directly; context.new_page NOT called."""
        ctx = MagicMock()
        ctx.new_page = AsyncMock()
        existing = MagicMock()
        cls = _make_platform_cls()
        with patch.object(orch, "ALL_PLATFORMS", {"myplatform": cls}):
            await orch.run_single_platform(
                "myplatform", ctx, "full", "condensed", ["sig"], "REGULAR", "/tmp/out",
                existing_page=existing,
            )
        ctx.new_page.assert_not_called()

    async def test_run_single_platform_exception(self):
        """Exception in platform.run() returns status=FAILED dict."""
        ctx = MagicMock()
        ctx.new_page = AsyncMock(return_value=MagicMock())
        cls = _make_platform_cls(raises=RuntimeError("boom"))
        with patch.object(orch, "ALL_PLATFORMS", {"myplatform": cls}):
            result = await orch.run_single_platform(
                "myplatform", ctx, "full", "condensed", ["sig"], "REGULAR", "/tmp/out"
            )
        assert result["status"] == "failed"
        assert "boom" in result["error"]


# ---------------------------------------------------------------------------
# Tests: _staggered_run
# ---------------------------------------------------------------------------

class TestStaggeredRun:
    async def test_staggered_run_with_delay(self):
        """delay_seconds > 0 causes asyncio.sleep to be called."""
        ctx = MagicMock()
        ctx.new_page = AsyncMock(return_value=MagicMock())
        cls = _make_platform_cls()
        limiter = _FakeRateLimiter()

        with patch.object(orch, "ALL_PLATFORMS", {"myplatform": cls}), \
             patch("orchestrator.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await orch._staggered_run(
                "myplatform", 2.0, ctx, "full", "condensed", ["sig"],
                "REGULAR", "/tmp/out", MagicMock(), limiter,
            )
        mock_sleep.assert_called_once_with(2.0)

    async def test_staggered_run_records_usage(self):
        """limiter.record_usage() is called with the result status."""
        ctx = MagicMock()
        ctx.new_page = AsyncMock(return_value=MagicMock())
        cls = _make_platform_cls()
        limiter = MagicMock()
        limiter.record_usage = MagicMock()

        with patch.object(orch, "ALL_PLATFORMS", {"myplatform": cls}):
            await orch._staggered_run(
                "myplatform", 0, ctx, "full", "condensed", ["sig"],
                "REGULAR", "/tmp/out", MagicMock(), limiter,
            )
        limiter.record_usage.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: _launch_chrome
# ---------------------------------------------------------------------------

class TestLaunchChrome:
    async def test_launch_chrome_connects_existing(self):
        """connect_over_cdp succeeds — returns (browser, context, None)."""
        p = MagicMock()
        browser = MagicMock()
        context = MagicMock()
        browser.contexts = [context]
        p.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        args = _make_args(fresh=False, headless=True)

        with patch("sys.platform", "linux"):
            b, c, proc = await orch._launch_chrome(p, args, "/tmp/pw-data", "/usr/bin/google-chrome")

        assert b is browser
        assert c is context
        assert proc is None

    async def test_launch_chrome_fresh_flag(self):
        """args.fresh=True skips the connect attempt and launches a new Chrome."""
        p = MagicMock()
        # connect_over_cdp should NOT be called
        p.chromium.connect_over_cdp = AsyncMock()

        browser = MagicMock()
        context = MagicMock()
        browser.contexts = [context]

        # After popen, connect succeeds
        p.chromium.connect_over_cdp.return_value = browser

        args = _make_args(fresh=True, headless=True)

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll = MagicMock(return_value=None)
        mock_proc.stderr = MagicMock()

        with patch("orchestrator.subprocess.Popen", return_value=mock_proc), \
             patch("orchestrator.asyncio.sleep", new=AsyncMock()), \
             patch("urllib.request.urlopen"):
            p.chromium.connect_over_cdp = AsyncMock(return_value=browser)
            with patch("sys.platform", "linux"):
                b, c, proc = await orch._launch_chrome(p, args, "/tmp/pw-data", "/usr/bin/google-chrome")

        assert b is browser
        assert proc is mock_proc

    async def test_launch_chrome_connect_fails_launches_new(self):
        """connect_over_cdp raises — falls through to subprocess launch."""
        p = MagicMock()
        browser = MagicMock()
        context = MagicMock()
        browser.contexts = [context]

        call_count = [0]

        async def _connect(*args, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("connection refused")
            return browser

        p.chromium.connect_over_cdp = _connect
        args = _make_args(fresh=False, headless=True)

        mock_proc = MagicMock()
        mock_proc.pid = 99
        mock_proc.poll = MagicMock(return_value=None)
        mock_proc.stderr = MagicMock()

        with patch("orchestrator.subprocess.Popen", return_value=mock_proc), \
             patch("orchestrator.asyncio.sleep", new=AsyncMock()), \
             patch("urllib.request.urlopen"), \
             patch("sys.platform", "linux"):
            b, c, proc = await orch._launch_chrome(p, args, "/tmp/pw-data", "/usr/bin/chrome")

        assert b is browser
        assert proc is mock_proc


# ---------------------------------------------------------------------------
# Tests: orchestrate
# ---------------------------------------------------------------------------

class TestOrchestrate:
    def _make_orchestrate_mocks(self):
        browser = MagicMock()
        context = MagicMock()
        browser.contexts = [context]
        proc = None

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=MagicMock(chromium=MagicMock(connect_over_cdp=AsyncMock(return_value=browser))))
        cm.__aexit__ = AsyncMock(return_value=False)
        return browser, context, proc, cm

    async def test_orchestrate_all_platforms(self):
        """orchestrate() runs all platforms when args.platforms='all'."""
        _platforms_mod.ALL_PLATFORMS = {
            "claude_ai": _make_platform_cls(),
            "chatgpt": _make_platform_cls(),
        }
        args = _make_args(platforms="all")

        fake_results = [{"platform": "claude_ai", "status": "complete"}, {"platform": "chatgpt", "status": "complete"}]

        with patch("orchestrator._launch_chrome", new=AsyncMock(return_value=(MagicMock(), MagicMock(), None))), \
             patch("orchestrator._run_all_platforms", new=AsyncMock(return_value=fake_results)), \
             patch("orchestrator._ensure_playwright_data_dir", return_value="/tmp/pw-data"), \
             patch("orchestrator.async_playwright") as mock_apw, \
             patch("orchestrator.Path.mkdir"), \
             patch("orchestrator.Path.exists", return_value=False):
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=MagicMock())
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_apw.return_value = cm

            browser_mock = MagicMock()
            browser_mock.close = AsyncMock()

            async def fake_run_all(*a, **kw):
                return fake_results

            with patch("orchestrator._launch_chrome", new=AsyncMock(return_value=(browser_mock, MagicMock(), None))), \
                 patch("orchestrator._run_all_platforms", new=AsyncMock(return_value=fake_results)):
                results = await orch.orchestrate(args, "/tmp/test-out")

        assert len(results) == 2

    async def test_orchestrate_unknown_platform_exits(self):
        """Unknown platform name causes sys.exit(1)."""
        _platforms_mod.ALL_PLATFORMS = {"claude_ai": _make_platform_cls()}
        args = _make_args(platforms="nonexistent_platform")

        with patch("orchestrator.Path.mkdir"), \
             patch("orchestrator.Path.exists", return_value=False), \
             pytest.raises(SystemExit) as exc_info:
            await orch.orchestrate(args, "/tmp/test-out")

        assert exc_info.value.code == 1

    async def test_orchestrate_skip_rate_check(self):
        """args.skip_rate_check=True bypasses preflight_check."""
        _platforms_mod.ALL_PLATFORMS = {"claude_ai": _make_platform_cls()}
        args = _make_args(platforms="all", skip_rate_check=True)

        fake_results = [{"platform": "claude_ai", "status": "complete"}]
        browser_mock = MagicMock()
        browser_mock.close = AsyncMock()

        with patch("orchestrator.async_playwright") as mock_apw, \
             patch("orchestrator.Path.mkdir"), \
             patch("orchestrator.Path.exists", return_value=False), \
             patch("orchestrator._ensure_playwright_data_dir", return_value="/tmp/pw-data"), \
             patch("orchestrator._launch_chrome", new=AsyncMock(return_value=(browser_mock, MagicMock(), None))), \
             patch("orchestrator._run_all_platforms", new=AsyncMock(return_value=fake_results)):
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=MagicMock())
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_apw.return_value = cm

            results = await orch.orchestrate(args, "/tmp/test-out")

        # Just verifying no exception was raised and result is returned
        assert isinstance(results, list)

    async def test_orchestrate_specific_platforms(self):
        """args.platforms='claude_ai,chatgpt' runs only those two."""
        all_platforms = {
            "claude_ai": _make_platform_cls(),
            "chatgpt": _make_platform_cls(),
            "gemini": _make_platform_cls(),
        }
        args = _make_args(platforms="claude_ai,chatgpt")

        fake_results = [{"platform": "claude_ai", "status": "complete"}]
        browser_mock = MagicMock()
        browser_mock.close = AsyncMock()

        with patch.object(orch, "ALL_PLATFORMS", all_platforms), \
             patch("orchestrator.async_playwright") as mock_apw, \
             patch("orchestrator.Path.mkdir"), \
             patch("orchestrator.Path.exists", return_value=False), \
             patch("orchestrator._ensure_playwright_data_dir", return_value="/tmp/pw-data"), \
             patch("orchestrator._launch_chrome", new=AsyncMock(return_value=(browser_mock, MagicMock(), None))), \
             patch("orchestrator._run_all_platforms", new=AsyncMock(return_value=fake_results)) as mock_run_all:
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=MagicMock())
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_apw.return_value = cm

            results = await orch.orchestrate(args, "/tmp/test-out")

        # _run_all_platforms was called with only the 2 selected platforms
        call_platform_names = mock_run_all.call_args[0][2]
        assert "claude_ai" in call_platform_names
        assert "chatgpt" in call_platform_names
        assert "gemini" not in call_platform_names


# ---------------------------------------------------------------------------
# Tests: _run_all_platforms
# ---------------------------------------------------------------------------

class TestRunAllPlatforms:
    async def test_run_all_platforms_staggered(self):
        """Multiple platforms are launched via _staggered_run as tasks."""
        ctx = MagicMock()
        ctx.new_page = AsyncMock(return_value=MagicMock())
        cls = _make_platform_cls()
        _platforms_mod.ALL_PLATFORMS = {"p1": cls, "p2": _make_platform_cls()}

        limiter = _FakeRateLimiter()
        args = _make_args()

        results = await orch._run_all_platforms(
            ctx, args, ["p1", "p2"], "full", "condensed", ["sig"], "/tmp/out", MagicMock(), limiter
        )
        assert len(results) == 2

    async def test_run_all_platforms_exception_to_dict(self):
        """Exception tasks are converted to error dicts."""
        ctx = MagicMock()
        ctx.new_page = AsyncMock(return_value=MagicMock())
        _platforms_mod.ALL_PLATFORMS = {
            "p1": _make_platform_cls(raises=RuntimeError("crash"))
        }

        limiter = _FakeRateLimiter()
        args = _make_args()

        # _gather_with_timeout returns the exception (not raised)
        with patch.object(orch, "_gather_with_timeout", new=AsyncMock(return_value=[RuntimeError("crash")])):
            results = await orch._run_all_platforms(
                ctx, args, ["p1"], "full", "condensed", ["sig"], "/tmp/out", MagicMock(), limiter
            )
        assert results[0]["status"] == "failed"

    async def test_run_all_platforms_timeout_dict(self):
        """asyncio.TimeoutError in results → status=timeout."""
        ctx = MagicMock()
        _platforms_mod.ALL_PLATFORMS = {"p1": _make_platform_cls()}
        limiter = _FakeRateLimiter()
        args = _make_args()

        with patch.object(orch, "_gather_with_timeout", new=AsyncMock(return_value=[asyncio.TimeoutError("timed out")])):
            results = await orch._run_all_platforms(
                ctx, args, ["p1"], "full", "condensed", ["sig"], "/tmp/out", MagicMock(), limiter
            )
        assert results[0]["status"] == "timeout"


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------

class TestMain:
    def test_main_delegates_to_cli(self):
        """main() imports and calls cli.main."""
        cli_mock = MagicMock()
        cli_mod = types.ModuleType("cli")
        cli_mod.main = cli_mock
        with patch.dict(sys.modules, {"cli": cli_mod}):
            orch.main()
        cli_mock.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: orchestrate — prefs file branch (exit_type != Normal)
# ---------------------------------------------------------------------------

class TestLaunchChromeDarwin:
    async def test_launch_chrome_darwin_osascript_on_connect(self):
        """On darwin non-headless, osascript is called after connect."""
        p = MagicMock()
        browser = MagicMock()
        context = MagicMock()
        browser.contexts = [context]
        p.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        args = _make_args(fresh=False, headless=False)

        with patch("sys.platform", "darwin"), \
             patch("orchestrator.subprocess.Popen") as mock_popen:
            b, c, proc = await orch._launch_chrome(p, args, "/tmp/pw-data", "/usr/bin/google-chrome")

        # osascript should have been called
        mock_popen.assert_called_once()
        assert "osascript" in mock_popen.call_args[0][0]

    async def test_launch_chrome_exited_prematurely(self):
        """Chrome process exits before CDP is ready — RuntimeError raised."""
        p = MagicMock()
        p.chromium.connect_over_cdp = AsyncMock(side_effect=OSError("no cdp"))
        args = _make_args(fresh=True, headless=True)

        mock_proc = MagicMock()
        mock_proc.pid = 55
        mock_proc.poll = MagicMock(return_value=1)  # process already exited
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.read = MagicMock(return_value=b"crash output")

        with patch("orchestrator.subprocess.Popen", return_value=mock_proc), \
             patch("orchestrator.asyncio.sleep", new=AsyncMock()), \
             patch("urllib.request.urlopen", side_effect=OSError("refused")), \
             patch("sys.platform", "linux"), \
             pytest.raises(RuntimeError, match="Chrome exited prematurely"):
            await orch._launch_chrome(p, args, "/tmp/pw-data", "/usr/bin/chrome")

    async def test_launch_chrome_cdp_timeout(self):
        """Chrome doesn't start CDP within 60 attempts — RuntimeError raised."""
        p = MagicMock()
        p.chromium.connect_over_cdp = AsyncMock(side_effect=OSError("no cdp"))
        args = _make_args(fresh=True, headless=True)

        mock_proc = MagicMock()
        mock_proc.pid = 66
        mock_proc.poll = MagicMock(return_value=None)  # process still running
        mock_proc.stderr = MagicMock()

        with patch("orchestrator.subprocess.Popen", return_value=mock_proc), \
             patch("orchestrator.asyncio.sleep", new=AsyncMock()), \
             patch("urllib.request.urlopen", side_effect=OSError("refused")), \
             patch("sys.platform", "linux"), \
             pytest.raises(RuntimeError, match="Chrome did not start"):
            await orch._launch_chrome(p, args, "/tmp/pw-data", "/usr/bin/chrome")

    async def test_launch_chrome_darwin_osascript_after_launch(self):
        """On darwin non-headless, osascript called after new Chrome launch."""
        p = MagicMock()
        browser = MagicMock()
        context = MagicMock()
        browser.contexts = [context]
        p.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        args = _make_args(fresh=True, headless=False)

        mock_proc = MagicMock()
        mock_proc.pid = 77
        mock_proc.poll = MagicMock(return_value=None)
        mock_proc.stderr = MagicMock()

        popen_calls = []

        def _popen(cmd, **kw):
            popen_calls.append(cmd)
            return mock_proc

        with patch("orchestrator.subprocess.Popen", side_effect=_popen), \
             patch("orchestrator.asyncio.sleep", new=AsyncMock()), \
             patch("urllib.request.urlopen"), \
             patch("sys.platform", "darwin"):
            b, c, proc = await orch._launch_chrome(p, args, "/tmp/pw-data", "/usr/bin/chrome")

        # Two Popen calls: chrome launch + osascript
        assert len(popen_calls) == 2
        assert "osascript" in popen_calls[1]


class TestGatherWithTimeoutCancelledError:
    async def test_gather_cancelled_error_in_result(self):
        """CancelledError in task.result() is appended as exception."""
        async def raise_cancelled():
            raise asyncio.CancelledError()

        task = asyncio.create_task(raise_cancelled())
        await asyncio.sleep(0)  # let it run

        results = await orch._gather_with_timeout([task], global_timeout=5, launched_names=["c"])
        # The cancelled task result should be a CancelledError
        assert len(results) == 1
        assert isinstance(results[0], (asyncio.CancelledError, Exception))

    async def test_gather_timeout_cancels_stuck_task(self):
        """After timeout, a still-running task is cancelled and gets TimeoutError result."""
        barrier = asyncio.Event()

        async def stuck():
            await barrier.wait()  # never fires
            return "nope"

        task = asyncio.create_task(stuck())
        # Don't set barrier — task stays stuck
        results = await orch._gather_with_timeout([task], global_timeout=0.01, launched_names=["s"])
        assert len(results) == 1
        assert isinstance(results[0], asyncio.TimeoutError)

    async def test_gather_timeout_done_task_raises_exception(self):
        """After timeout, a task that is done but raised an exception — exc is collected."""
        async def raise_runtime():
            raise RuntimeError("task error")

        task = asyncio.create_task(raise_runtime())
        # Let task complete (it raises) before we run gather_with_timeout
        await asyncio.sleep(0.05)

        # Now run with a non-zero timeout — the task is already done with exception
        # We mock wait_for to raise TimeoutError so we enter the except branch
        original_wait_for = asyncio.wait_for

        async def _fake_wait_for(coro, timeout):
            # Cancel the coro without awaiting it
            try:
                coro.close()
            except Exception:
                pass
            raise asyncio.TimeoutError()

        with patch.object(asyncio, "wait_for", _fake_wait_for):
            results = await orch._gather_with_timeout([task], global_timeout=5, launched_names=["r"])

        # task is done and raised RuntimeError, so exc is appended
        assert len(results) == 1
        assert isinstance(results[0], RuntimeError)


class TestRunAllPlatformsExistingTabs:
    async def test_run_all_platforms_with_existing_tab(self):
        """_find_existing_tab returns page — it's used and saved."""
        ctx = MagicMock()
        existing_page = MagicMock()
        existing_page.url = "https://claude.ai/chat"

        # First call: finding existing tabs, subsequent calls: saving tab state
        call_count = [0]

        async def _find_tab(context, name):
            call_count[0] += 1
            if call_count[0] <= 1:
                return existing_page
            return None

        cls = _make_platform_cls()
        limiter = _FakeRateLimiter()
        args = _make_args()

        with patch.object(orch, "ALL_PLATFORMS", {"claude_ai": cls}), \
             patch.object(orch, "_find_existing_tab", side_effect=_find_tab):
            results = await orch._run_all_platforms(
                ctx, args, ["claude_ai"], "full", "condensed", ["sig"],
                "/tmp/out", MagicMock(), limiter
            )
        assert len(results) == 1


class TestOrchestrateRateLimitWarning:
    async def test_orchestrate_rate_limit_warning_logged(self):
        """preflight_check returns allowed=False — warning is logged but continues."""
        all_platforms = {"claude_ai": _make_platform_cls()}
        args = _make_args(platforms="all", skip_rate_check=False)
        fake_results = [{"platform": "claude_ai", "status": "complete"}]
        browser_mock = MagicMock()
        browser_mock.close = AsyncMock()

        class _LimiterWithWarning(_FakeRateLimiter):
            def preflight_check(self, platform, mode):
                result = MagicMock()
                result.allowed = False
                result.reason = "Daily cap reached"
                return result

        with patch.object(orch, "ALL_PLATFORMS", all_platforms), \
             patch.object(orch, "RateLimiter", _LimiterWithWarning), \
             patch("orchestrator.async_playwright") as mock_apw, \
             patch("orchestrator.Path.mkdir"), \
             patch("orchestrator.Path.exists", return_value=False), \
             patch("orchestrator._launch_chrome", new=AsyncMock(return_value=(browser_mock, MagicMock(), None))), \
             patch("orchestrator._run_all_platforms", new=AsyncMock(return_value=fake_results)):
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=MagicMock())
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_apw.return_value = cm
            results = await orch.orchestrate(args, "/tmp/test-out")

        assert isinstance(results, list)


class TestOrchestrateBrowserCloseTimeout:
    async def test_orchestrate_browser_close_timeout_ignored(self):
        """browser.close() timing out is silently ignored."""
        all_platforms = {"claude_ai": _make_platform_cls()}
        args = _make_args(platforms="all")
        fake_results = [{"platform": "claude_ai", "status": "complete"}]
        browser_mock = MagicMock()
        browser_mock.close = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch.object(orch, "ALL_PLATFORMS", all_platforms), \
             patch("orchestrator.async_playwright") as mock_apw, \
             patch("orchestrator.Path.mkdir"), \
             patch("orchestrator.Path.exists", return_value=False), \
             patch("orchestrator._launch_chrome", new=AsyncMock(return_value=(browser_mock, MagicMock(), None))), \
             patch("orchestrator._run_all_platforms", new=AsyncMock(return_value=fake_results)):
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=MagicMock())
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_apw.return_value = cm
            # Should not raise
            results = await orch.orchestrate(args, "/tmp/test-out")

        assert isinstance(results, list)


class TestOrchestratePrefs:
    async def test_orchestrate_fixes_exit_type(self, tmp_path):
        """When Preferences file has exit_type != Normal, it's fixed."""
        import json as _json
        # Create a profile dir with a Preferences file
        profile_dir = tmp_path / "MultAI"
        profile_dir.mkdir()
        prefs = {"profile": {"exit_type": "Crashed"}}
        prefs_path = profile_dir / "Preferences"
        prefs_path.write_text(_json.dumps(prefs))

        all_platforms = {"claude_ai": _make_platform_cls()}
        args = _make_args(platforms="all", chrome_profile="MultAI")
        fake_results = [{"platform": "claude_ai", "status": "complete"}]
        browser_mock = MagicMock()
        browser_mock.close = AsyncMock()

        with patch.object(orch, "ALL_PLATFORMS", all_platforms), \
             patch.object(orch, "detect_chrome_user_data_dir", return_value=str(tmp_path)), \
             patch.object(orch, "detect_chrome_executable", return_value="/usr/bin/google-chrome"), \
             patch("orchestrator.async_playwright") as mock_apw, \
             patch("orchestrator._launch_chrome", new=AsyncMock(return_value=(browser_mock, MagicMock(), None))), \
             patch("orchestrator._run_all_platforms", new=AsyncMock(return_value=fake_results)):
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=MagicMock())
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_apw.return_value = cm

            results = await orch.orchestrate(args, str(tmp_path / "out"))

        # Check that Preferences was updated
        updated = _json.loads(prefs_path.read_text())
        assert updated["profile"]["exit_type"] == "Normal"

    async def test_orchestrate_prefs_exception_ignored(self, tmp_path):
        """When Preferences file has invalid JSON, the exception is logged and ignored."""
        import json as _json
        profile_dir = tmp_path / "MultAI"
        profile_dir.mkdir()
        prefs_path = profile_dir / "Preferences"
        prefs_path.write_text("not valid json {{{")  # corrupt JSON

        all_platforms = {"claude_ai": _make_platform_cls()}
        args = _make_args(platforms="all", chrome_profile="MultAI")
        fake_results = [{"platform": "claude_ai", "status": "complete"}]
        browser_mock = MagicMock()
        browser_mock.close = AsyncMock()

        with patch.object(orch, "ALL_PLATFORMS", all_platforms), \
             patch.object(orch, "detect_chrome_user_data_dir", return_value=str(tmp_path)), \
             patch.object(orch, "detect_chrome_executable", return_value="/usr/bin/google-chrome"), \
             patch("orchestrator.async_playwright") as mock_apw, \
             patch("orchestrator._launch_chrome", new=AsyncMock(return_value=(browser_mock, MagicMock(), None))), \
             patch("orchestrator._run_all_platforms", new=AsyncMock(return_value=fake_results)):
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=MagicMock())
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_apw.return_value = cm
            # Should NOT raise despite bad JSON
            results = await orch.orchestrate(args, str(tmp_path / "out"))

        assert isinstance(results, list)
