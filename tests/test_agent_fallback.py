"""Unit tests for AgentFallbackManager (agent_fallback.py)."""

import asyncio
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.conftest import install_stubs

PLATFORM_NAME = "test_platform"
PLATFORM_URL = "https://test.com"


def _setup_browser_use_stub():
    """Install browser_use stub into sys.modules."""
    mock_bu = types.ModuleType("browser_use")
    mock_agent_cls = MagicMock()
    mock_bu.Agent = mock_agent_cls
    mock_bu.BrowserSession = MagicMock()
    sys.modules["browser_use"] = mock_bu
    return mock_bu


def _load():
    install_stubs(PLATFORM_NAME, PLATFORM_URL)
    _setup_browser_use_stub()

    # Extend config stub with agent model constants
    config = sys.modules["config"]
    config.AGENT_MODEL_ANTHROPIC = "claude-3-5-haiku-20241022"
    config.AGENT_MODEL_GOOGLE = "gemini-2.0-flash"

    for mod in list(sys.modules):
        if "agent_fallback" in mod and mod != "browser_use":
            del sys.modules[mod]

    import agent_fallback as af
    return af


class TestAgentFallbackManagerInit(unittest.IsolatedAsyncioTestCase):

    async def test_init_disabled_no_api_key(self):
        """enabled=False when neither ANTHROPIC_API_KEY nor GOOGLE_API_KEY set."""
        af = _load()
        with patch.dict(os.environ, {}, clear=True):
            # Remove the keys if present
            env = {k: v for k, v in os.environ.items()
                   if k not in ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY")}
            with patch.dict(os.environ, env, clear=True):
                mgr = af.AgentFallbackManager("http://localhost:9222", "/tmp/out")
        self.assertFalse(mgr.enabled)

    async def test_init_enabled_anthropic(self):
        """enabled=True and _llm_provider='anthropic' when ANTHROPIC_API_KEY set."""
        af = _load()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False):
            mgr = af.AgentFallbackManager("http://localhost:9222", "/tmp/out")
        self.assertTrue(mgr.enabled)
        self.assertEqual(mgr._llm_provider, "anthropic")

    async def test_init_enabled_google(self):
        """enabled=True and _llm_provider='google' when only GOOGLE_API_KEY set."""
        af = _load()
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env["GOOGLE_API_KEY"] = "google-key"
        with patch.dict(os.environ, env, clear=True):
            mgr = af.AgentFallbackManager("http://localhost:9222", "/tmp/out")
        self.assertTrue(mgr.enabled)
        self.assertEqual(mgr._llm_provider, "google")


class TestFallbackMethod(unittest.IsolatedAsyncioTestCase):

    def _make_mgr(self, enabled=True):
        af = _load()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"} if enabled else {}, clear=not enabled):
            if not enabled:
                env = {k: v for k, v in os.environ.items()
                       if k not in ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY")}
                with patch.dict(os.environ, env, clear=True):
                    mgr = af.AgentFallbackManager("http://localhost:9222", "/tmp/out")
            else:
                mgr = af.AgentFallbackManager("http://localhost:9222", "/tmp/out")
        self.af = af
        return mgr

    async def test_fallback_disabled_raises_original(self):
        """When disabled, fallback raises the original error."""
        mgr = self._make_mgr(enabled=False)
        page = MagicMock()
        original = RuntimeError("original error")
        step = self.af.FallbackStep.INJECT_PROMPT

        with self.assertRaises(RuntimeError) as ctx:
            await mgr.fallback(page, "test_platform", step, original, "task")
        self.assertIs(ctx.exception, original)

    async def test_fallback_success(self):
        """Agent.run returns history with final_result -> returns result text."""
        af = _load()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)

            page = MagicMock()
            page.bring_to_front = AsyncMock()

            mock_history = MagicMock()
            mock_history.final_result = MagicMock(return_value="agent result text")

            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=mock_history)

            mock_bu = sys.modules["browser_use"]
            mock_bu.Agent = MagicMock(return_value=mock_agent_instance)

            # Stub browser_use.llm submodules
            for submod in ["browser_use.llm", "browser_use.llm.anthropic",
                           "browser_use.llm.anthropic.chat"]:
                if submod not in sys.modules:
                    sys.modules[submod] = types.ModuleType(submod)
            chat_mod = sys.modules["browser_use.llm.anthropic.chat"]
            chat_mod.ChatAnthropic = MagicMock(return_value=MagicMock())

            result = await mgr.fallback(
                page, "test_platform", af.FallbackStep.INJECT_PROMPT,
                RuntimeError("selector failed"), "Find the input"
            )
        self.assertEqual(result, "agent result text")

    async def test_fallback_agent_fails_raises_original(self):
        """Agent raises -> re-raises the original_error (not agent error)."""
        af = _load()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)

            page = MagicMock()
            page.bring_to_front = AsyncMock()

            mock_bu = sys.modules["browser_use"]
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(side_effect=RuntimeError("agent error"))
            mock_bu.Agent = MagicMock(return_value=mock_agent_instance)

            for submod in ["browser_use.llm", "browser_use.llm.anthropic",
                           "browser_use.llm.anthropic.chat"]:
                if submod not in sys.modules:
                    sys.modules[submod] = types.ModuleType(submod)
            chat_mod = sys.modules["browser_use.llm.anthropic.chat"]
            chat_mod.ChatAnthropic = MagicMock(return_value=MagicMock())

            original = RuntimeError("original selector failed")
            with self.assertRaises(RuntimeError) as ctx:
                await mgr.fallback(
                    page, "test_platform", af.FallbackStep.CLICK_SEND,
                    original, "Click send button"
                )
        self.assertIs(ctx.exception, original)

    async def test_fallback_logs_event(self):
        """After successful fallback, one FallbackEvent is logged to _events."""
        af = _load()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)

            page = MagicMock()
            page.bring_to_front = AsyncMock()

            mock_history = MagicMock()
            mock_history.final_result = MagicMock(return_value="done")
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=mock_history)

            mock_bu = sys.modules["browser_use"]
            mock_bu.Agent = MagicMock(return_value=mock_agent_instance)

            for submod in ["browser_use.llm", "browser_use.llm.anthropic",
                           "browser_use.llm.anthropic.chat"]:
                if submod not in sys.modules:
                    sys.modules[submod] = types.ModuleType(submod)
            chat_mod = sys.modules["browser_use.llm.anthropic.chat"]
            chat_mod.ChatAnthropic = MagicMock(return_value=MagicMock())

            await mgr.fallback(
                page, "test_platform", af.FallbackStep.EXTRACT_RESPONSE,
                RuntimeError("extract failed"), "Extract text"
            )
        self.assertEqual(len(mgr._events), 1)
        self.assertEqual(mgr._events[0].platform, "test_platform")
        self.assertTrue(mgr._events[0].agent_success)


class TestFallbackGoogle(unittest.IsolatedAsyncioTestCase):

    async def test_fallback_google_provider(self):
        """With GOOGLE_API_KEY only, uses ChatGoogle llm."""
        af = _load()
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            env["GOOGLE_API_KEY"] = "google-key"
            with patch.dict(os.environ, env, clear=True):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)

            self.assertEqual(mgr._llm_provider, "google")

            page = MagicMock()
            page.bring_to_front = AsyncMock()

            mock_history = MagicMock()
            mock_history.final_result = MagicMock(return_value="google result")
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=mock_history)

            mock_bu = sys.modules["browser_use"]
            mock_bu.Agent = MagicMock(return_value=mock_agent_instance)

            for submod in ["browser_use.llm", "browser_use.llm.google",
                           "browser_use.llm.google.chat"]:
                if submod not in sys.modules:
                    sys.modules[submod] = types.ModuleType(submod)
            chat_mod = sys.modules["browser_use.llm.google.chat"]
            chat_mod.ChatGoogle = MagicMock(return_value=MagicMock())

            result = await mgr.fallback(
                page, "test_platform", af.FallbackStep.CONFIGURE_MODE,
                RuntimeError("config failed"), "Configure mode"
            )
        self.assertEqual(result, "google result")


class TestFullPlatformRun(unittest.IsolatedAsyncioTestCase):

    def _make_mgr(self, tmp, enabled=True):
        af = _load()
        self.af = af
        if enabled:
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)
        else:
            env = {k: v for k, v in os.environ.items()
                   if k not in ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY")}
            with patch.dict(os.environ, env, clear=True):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)
        return mgr

    async def test_full_platform_run_disabled(self):
        """Returns None when manager is disabled."""
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._make_mgr(tmp, enabled=False)
            result = await mgr.full_platform_run(
                "test", "https://test.com", "Test", "prompt", "REGULAR", tmp
            )
        self.assertIsNone(result)

    async def test_full_platform_run_no_url(self):
        """Returns None when platform_url is empty."""
        with tempfile.TemporaryDirectory() as tmp:
            mgr = self._make_mgr(tmp, enabled=True)
            result = await mgr.full_platform_run(
                "test", "", "Test", "prompt", "REGULAR", tmp
            )
        self.assertIsNone(result)

    async def test_full_platform_run_success(self):
        """Agent returns >200 chars -> result dict with status=complete."""
        af = _load()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)

            long_response = "A" * 300
            mock_history = MagicMock()
            mock_history.final_result = MagicMock(return_value=long_response)
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=mock_history)

            mock_bu = sys.modules["browser_use"]
            mock_bu.Agent = MagicMock(return_value=mock_agent_instance)

            for submod in ["browser_use.llm", "browser_use.llm.anthropic",
                           "browser_use.llm.anthropic.chat"]:
                if submod not in sys.modules:
                    sys.modules[submod] = types.ModuleType(submod)
            sys.modules["browser_use.llm.anthropic.chat"].ChatAnthropic = MagicMock(return_value=MagicMock())

            result = await mgr.full_platform_run(
                "test_platform", "https://test.com", "Test", "my prompt", "REGULAR", tmp
            )
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["chars"], 300)

    async def test_full_platform_run_needs_login(self):
        """Agent returns 'NEEDS_LOGIN' -> status=needs_login."""
        af = _load()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)

            mock_history = MagicMock()
            mock_history.final_result = MagicMock(return_value="NEEDS_LOGIN please log in")
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=mock_history)

            mock_bu = sys.modules["browser_use"]
            mock_bu.Agent = MagicMock(return_value=mock_agent_instance)

            for submod in ["browser_use.llm", "browser_use.llm.anthropic",
                           "browser_use.llm.anthropic.chat"]:
                if submod not in sys.modules:
                    sys.modules[submod] = types.ModuleType(submod)
            sys.modules["browser_use.llm.anthropic.chat"].ChatAnthropic = MagicMock(return_value=MagicMock())

            result = await mgr.full_platform_run(
                "test_platform", "https://test.com", "Test", "prompt", "REGULAR", tmp
            )
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "needs_login")

    async def test_full_platform_run_insufficient_content(self):
        """Agent returns <200 chars -> returns None."""
        af = _load()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)

            mock_history = MagicMock()
            mock_history.final_result = MagicMock(return_value="short")
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=mock_history)

            mock_bu = sys.modules["browser_use"]
            mock_bu.Agent = MagicMock(return_value=mock_agent_instance)

            for submod in ["browser_use.llm", "browser_use.llm.anthropic",
                           "browser_use.llm.anthropic.chat"]:
                if submod not in sys.modules:
                    sys.modules[submod] = types.ModuleType(submod)
            sys.modules["browser_use.llm.anthropic.chat"].ChatAnthropic = MagicMock(return_value=MagicMock())

            result = await mgr.full_platform_run(
                "test_platform", "https://test.com", "Test", "prompt", "REGULAR", tmp
            )
        self.assertIsNone(result)

    async def test_full_platform_run_prompt_truncation(self):
        """Prompt >3000 chars triggers truncation log warning."""
        af = _load()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)

            long_prompt = "X" * 3100
            mock_history = MagicMock()
            mock_history.final_result = MagicMock(return_value="A" * 300)
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=mock_history)

            mock_bu = sys.modules["browser_use"]
            mock_bu.Agent = MagicMock(return_value=mock_agent_instance)

            for submod in ["browser_use.llm", "browser_use.llm.anthropic",
                           "browser_use.llm.anthropic.chat"]:
                if submod not in sys.modules:
                    sys.modules[submod] = types.ModuleType(submod)
            sys.modules["browser_use.llm.anthropic.chat"].ChatAnthropic = MagicMock(return_value=MagicMock())

            import logging
            with self.assertLogs(level=logging.WARNING):
                result = await mgr.full_platform_run(
                    "test_platform", "https://test.com", "Test",
                    long_prompt, "REGULAR", tmp
                )
        self.assertIsNotNone(result)

    async def test_full_platform_run_deep_mode_max_steps(self):
        """DEEP mode uses max_steps=25."""
        af = _load()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)

            mock_history = MagicMock()
            mock_history.final_result = MagicMock(return_value="A" * 300)
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=mock_history)

            mock_bu = sys.modules["browser_use"]
            agent_cls = MagicMock(return_value=mock_agent_instance)
            mock_bu.Agent = agent_cls

            for submod in ["browser_use.llm", "browser_use.llm.anthropic",
                           "browser_use.llm.anthropic.chat"]:
                if submod not in sys.modules:
                    sys.modules[submod] = types.ModuleType(submod)
            sys.modules["browser_use.llm.anthropic.chat"].ChatAnthropic = MagicMock(return_value=MagicMock())

            await mgr.full_platform_run(
                "test_platform", "https://test.com", "Test", "prompt", "DEEP", tmp
            )
        call_kwargs = agent_cls.call_args[1]
        self.assertEqual(call_kwargs.get("max_steps"), 25)

    async def test_full_platform_run_exception_returns_none(self):
        """Agent.run raises -> returns None (exception swallowed)."""
        af = _load()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)

            mock_bu = sys.modules["browser_use"]
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(side_effect=RuntimeError("agent crashed"))
            mock_bu.Agent = MagicMock(return_value=mock_agent_instance)

            for submod in ["browser_use.llm", "browser_use.llm.anthropic",
                           "browser_use.llm.anthropic.chat"]:
                if submod not in sys.modules:
                    sys.modules[submod] = types.ModuleType(submod)
            sys.modules["browser_use.llm.anthropic.chat"].ChatAnthropic = MagicMock(return_value=MagicMock())

            result = await mgr.full_platform_run(
                "test_platform", "https://test.com", "Test", "prompt", "REGULAR", tmp
            )
        self.assertIsNone(result)


class TestFullPlatformRunGoogle(unittest.IsolatedAsyncioTestCase):

    async def test_full_platform_run_google_provider(self):
        """full_platform_run with GOOGLE_API_KEY uses ChatGoogle llm."""
        af = _load()
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            env["GOOGLE_API_KEY"] = "google-key"
            with patch.dict(os.environ, env, clear=True):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)

            self.assertEqual(mgr._llm_provider, "google")

            mock_history = MagicMock()
            mock_history.final_result = MagicMock(return_value="A" * 300)
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=mock_history)

            mock_bu = sys.modules["browser_use"]
            mock_bu.Agent = MagicMock(return_value=mock_agent_instance)

            for submod in ["browser_use.llm", "browser_use.llm.google",
                           "browser_use.llm.google.chat"]:
                if submod not in sys.modules:
                    sys.modules[submod] = types.ModuleType(submod)
            sys.modules["browser_use.llm.google.chat"].ChatGoogle = MagicMock(return_value=MagicMock())

            result = await mgr.full_platform_run(
                "test_platform", "https://test.com", "Test", "prompt", "REGULAR", tmp
            )
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "complete")


class TestSaveLog(unittest.IsolatedAsyncioTestCase):

    async def test_save_log_writes_json(self):
        """_save_log writes events to agent-fallback-log.json."""
        af = _load()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                mgr = af.AgentFallbackManager("http://localhost:9222", tmp)

            mgr._events.append(af.FallbackEvent(
                timestamp="2024-01-01T00:00:00",
                platform="test",
                step="inject_prompt",
                original_error="err",
                agent_task="task",
                agent_result="result",
                agent_success=True,
                duration_s=1.0,
            ))
            mgr._save_log()

            log_path = Path(tmp) / "agent-fallback-log.json"
            self.assertTrue(log_path.exists())
            data = json.loads(log_path.read_text())
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["platform"], "test")


if __name__ == "__main__":
    unittest.main()
