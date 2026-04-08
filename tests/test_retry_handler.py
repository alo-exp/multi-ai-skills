"""Unit tests for retry_handler.py (handle_login_retries, handle_agent_fallbacks)."""

import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.conftest import install_stubs

PLATFORM_NAME = "test_platform"
PLATFORM_URL = "https://test.com"


def _load():
    install_stubs(PLATFORM_NAME, PLATFORM_URL)

    # Extend config stub with PLATFORM_URLS and PLATFORM_DISPLAY_NAMES
    config = sys.modules["config"]
    config.PLATFORM_URLS = {PLATFORM_NAME: PLATFORM_URL, "other": "https://other.com"}
    config.PLATFORM_DISPLAY_NAMES = {PLATFORM_NAME: "Test Platform"}
    config.STATUS_FAILED = "failed"
    config.STATUS_NEEDS_LOGIN = "needs_login"

    for mod in list(sys.modules):
        if "retry_handler" in mod:
            del sys.modules[mod]

    import retry_handler as rh
    return rh


def _make_args(mode="REGULAR"):
    args = MagicMock()
    args.mode = mode
    return args


def _make_limiter():
    limiter = MagicMock()
    limiter.record_usage = MagicMock()
    return limiter


def _make_agent_mgr(enabled=True):
    mgr = MagicMock()
    mgr.enabled = enabled
    mgr.full_platform_run = AsyncMock(return_value=None)
    return mgr


class TestHandleLoginRetries(unittest.IsolatedAsyncioTestCase):

    async def test_handle_login_retries_no_pending(self):
        """No NEEDS_LOGIN results — returns immediately without sleep or retry."""
        rh = _load()
        results = [
            {"platform": PLATFORM_NAME, "display_name": "Test", "status": "complete"},
        ]
        run_fn = AsyncMock(return_value={"platform": PLATFORM_NAME, "display_name": "Test",
                                          "status": "complete", "duration_s": 1.0})
        with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await rh.handle_login_retries(
                results, MagicMock(), "prompt", "short", [], _make_args(),
                "/tmp/out", _make_agent_mgr(), _make_limiter(), run_fn,
            )
        mock_sleep.assert_not_called()
        run_fn.assert_not_called()

    async def test_handle_login_retries_retries_login(self):
        """NEEDS_LOGIN result triggers countdown sleep + run_fn call."""
        rh = _load()
        results = [
            {"platform": PLATFORM_NAME, "display_name": "Test Platform",
             "status": "needs_login", "duration_s": 0.0},
        ]
        retry_result = {"platform": PLATFORM_NAME, "display_name": "Test Platform",
                        "status": "complete", "duration_s": 2.0}
        run_fn = AsyncMock(return_value=retry_result)
        limiter = _make_limiter()

        with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await rh.handle_login_retries(
                results, MagicMock(), "prompt", "short", [], _make_args(),
                "/tmp/out", _make_agent_mgr(), limiter, run_fn,
            )

        # sleep should be called 9 times (for remaining in range(90, 0, -10))
        self.assertEqual(mock_sleep.call_count, 9)
        run_fn.assert_called_once()
        # result should be updated in-place
        self.assertEqual(results[0]["status"], "complete")
        limiter.record_usage.assert_called_once()


class TestHandleAgentFallbacks(unittest.IsolatedAsyncioTestCase):

    async def test_handle_agent_fallbacks_disabled(self):
        """When agent_mgr.enabled=False, no fallback attempted."""
        rh = _load()
        results = [
            {"platform": PLATFORM_NAME, "display_name": "Test", "status": "failed"},
        ]
        agent_mgr = _make_agent_mgr(enabled=False)
        await rh.handle_agent_fallbacks(results, agent_mgr, "prompt", _make_args(), "/tmp/out")
        agent_mgr.full_platform_run.assert_not_called()

    async def test_handle_agent_fallbacks_failed_platform(self):
        """FAILED result with URL triggers full_platform_run, updates result."""
        rh = _load()
        results = [
            {"platform": PLATFORM_NAME, "display_name": "Test", "status": "failed"},
        ]
        fallback_result = {"platform": PLATFORM_NAME, "display_name": "Test",
                           "status": "complete", "chars": 300}
        agent_mgr = _make_agent_mgr(enabled=True)
        agent_mgr.full_platform_run = AsyncMock(return_value=fallback_result)

        await rh.handle_agent_fallbacks(results, agent_mgr, "prompt", _make_args(), "/tmp/out")

        agent_mgr.full_platform_run.assert_called_once()
        self.assertEqual(results[0]["status"], "complete")

    async def test_handle_agent_fallbacks_no_url(self):
        """Platform with no URL in PLATFORM_URLS is skipped."""
        rh = _load()
        results = [
            {"platform": "unknown_platform", "display_name": "Unknown", "status": "failed"},
        ]
        agent_mgr = _make_agent_mgr(enabled=True)
        await rh.handle_agent_fallbacks(results, agent_mgr, "prompt", _make_args(), "/tmp/out")
        agent_mgr.full_platform_run.assert_not_called()

    async def test_handle_agent_fallbacks_fallback_returns_none(self):
        """full_platform_run returns None -> original result unchanged."""
        rh = _load()
        original_result = {"platform": PLATFORM_NAME, "display_name": "Test",
                           "status": "failed", "chars": 0}
        results = [dict(original_result)]
        agent_mgr = _make_agent_mgr(enabled=True)
        agent_mgr.full_platform_run = AsyncMock(return_value=None)

        await rh.handle_agent_fallbacks(results, agent_mgr, "prompt", _make_args(), "/tmp/out")

        self.assertEqual(results[0]["status"], "failed")

    async def test_handle_agent_fallbacks_no_failed(self):
        """No FAILED results -> full_platform_run not called."""
        rh = _load()
        results = [
            {"platform": PLATFORM_NAME, "display_name": "Test", "status": "complete"},
        ]
        agent_mgr = _make_agent_mgr(enabled=True)
        await rh.handle_agent_fallbacks(results, agent_mgr, "prompt", _make_args(), "/tmp/out")
        agent_mgr.full_platform_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
