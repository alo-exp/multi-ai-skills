"""Unit tests for BasePlatform (base.py) lifecycle methods."""

import asyncio
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


def _setup():
    config = install_stubs(PLATFORM_NAME, PLATFORM_URL)
    config.INJECTION_METHODS = {PLATFORM_NAME: "execCommand"}
    config.TIMEOUTS = {}
    # TimeoutConfig stub
    config.TimeoutConfig = type("TimeoutConfig", (), {"regular": 1, "deep": 2})

    # agent_fallback module stub
    af_mod = types.ModuleType("agent_fallback")

    class FallbackStep(str):
        """Enum-like stub: supports FallbackStep(value) construction."""
        CONFIGURE_MODE = "configure_mode"
        INJECT_PROMPT = "inject_prompt"
        CLICK_SEND = "click_send"
        POST_SEND = "post_send"
        COMPLETION_CHECK = "completion_check"
        EXTRACT_RESPONSE = "extract_response"

        def __new__(cls, value=""):
            return str.__new__(cls, value)

        @property
        def value(self):
            return str(self)

    af_mod.FallbackStep = FallbackStep
    sys.modules["agent_fallback"] = af_mod

    for mod in list(sys.modules):
        if any(x in mod for x in ("platforms.base", "platforms.browser_utils",
                                   "platforms.inject_utils")):
            if mod not in ("platforms",):
                del sys.modules[mod]

    from platforms.base import BasePlatform, PlatformResult
    from platforms.browser_utils import _SignInRequired, _RateLimited
    return BasePlatform, PlatformResult, _SignInRequired, _RateLimited


def _make_page(url="https://test.com"):
    page = MagicMock()
    page.url = url
    page.title = AsyncMock(return_value="Test")
    page.on = MagicMock()
    page.goto = AsyncMock()
    page.bring_to_front = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.evaluate = AsyncMock(return_value=0)

    def locator(sel):
        loc = MagicMock()
        loc.first = loc
        loc.count = AsyncMock(return_value=0)
        loc.is_visible = AsyncMock(return_value=False)
        loc.click = AsyncMock()
        return loc
    page.locator = locator

    def get_by_text(text, **kwargs):
        loc = MagicMock()
        loc.first = loc
        loc.count = AsyncMock(return_value=0)
        loc.is_visible = AsyncMock(return_value=False)
        return loc
    page.get_by_text = get_by_text

    def get_by_role(role, **kwargs):
        btn = MagicMock()
        btn.first = btn
        btn.count = AsyncMock(return_value=0)
        btn.is_visible = AsyncMock(return_value=False)
        btn.click = AsyncMock()
        return btn
    page.get_by_role = get_by_role

    return page


class TestPlatformFactory:
    """Creates a concrete TestPlatform subclass."""

    @staticmethod
    def make(BasePlatform, response="A" * 500, completion=True,
             configure_mode="REGULAR", configure_exc=None,
             check_rate_limit=None):
        class TestPlatform(BasePlatform):
            name = PLATFORM_NAME
            url = PLATFORM_URL
            display_name = "Test Platform"

            async def configure_mode(self, page, mode):
                if configure_exc:
                    raise configure_exc
                return configure_mode

            async def completion_check(self, page):
                if isinstance(completion, Exception):
                    raise completion
                return completion

            async def extract_response(self, page):
                if isinstance(response, Exception):
                    raise response
                return response

            async def check_rate_limit(self, page):
                return check_rate_limit

        return TestPlatform()


class TestRunLifecycle(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BasePlatform, PlatformResult, _SignInRequired, _RateLimited = _setup()
        # Stub inject_prompt on BasePlatform to avoid real clipboard/subprocess
        # calls on CI (Linux has no pbpaste/xclip). Injection is tested separately
        # in TestInjectPrompt which patches the lower-level helpers.
        BasePlatform.inject_prompt = AsyncMock()
        self.BasePlatform = BasePlatform
        self.PlatformResult = PlatformResult
        self._SignInRequired = _SignInRequired
        self._RateLimited = _RateLimited

    async def test_run_success_complete(self):
        """Happy path: returns PlatformResult with status=complete, file written."""
        platform = TestPlatformFactory.make(self.BasePlatform)
        page = _make_page()

        async def _navigate(p, mode):
            return "REGULAR"
        platform._navigate_and_configure = _navigate
        platform._setup_dialog_handler = MagicMock()

        async def _dismiss(p):
            pass
        platform.dismiss_popups = _dismiss

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "test prompt", "REGULAR", tmp)

        self.assertEqual(result.status, "complete")
        self.assertGreater(result.chars, 0)
        self.assertTrue(result.file)

    async def test_run_followup_skips_navigation(self):
        """followup=True: goto NOT called, bring_to_front called."""
        platform = TestPlatformFactory.make(self.BasePlatform)
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        async def _dismiss(p):
            pass
        platform.dismiss_popups = _dismiss

        nav_called = {"v": False}

        async def _navigate(p, mode):
            nav_called["v"] = True
            return "REGULAR"
        platform._navigate_and_configure = _navigate

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "prompt", "REGULAR", tmp, followup=True)

        self.assertFalse(nav_called["v"])
        page.bring_to_front.assert_awaited()
        self.assertEqual(result.status, "complete")

    async def test_run_sign_in_required(self):
        """_navigate_and_configure raises _SignInRequired -> status=NEEDS_LOGIN."""
        _SignInRequired = self._SignInRequired
        platform = TestPlatformFactory.make(self.BasePlatform)
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        async def _navigate(p, mode):
            raise _SignInRequired("sign in")
        platform._navigate_and_configure = _navigate

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "prompt", "REGULAR", tmp)
        self.assertEqual(result.status, "needs_login")

    async def test_run_rate_limited(self):
        """_navigate_and_configure raises _RateLimited -> status=RATE_LIMITED."""
        _RateLimited = self._RateLimited
        platform = TestPlatformFactory.make(self.BasePlatform)
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        async def _navigate(p, mode):
            raise _RateLimited("rate limited")
        platform._navigate_and_configure = _navigate

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "prompt", "REGULAR", tmp)
        self.assertEqual(result.status, "rate_limited")

    async def test_run_inject_prompt_exception_no_agent(self):
        """inject_prompt raises, no agent_manager -> _agent_fallback raises -> status=failed."""
        platform = TestPlatformFactory.make(self.BasePlatform)
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()
        platform.agent_manager = None

        async def _navigate(p, mode):
            return "REGULAR"
        platform._navigate_and_configure = _navigate

        async def _inject(p, prompt):
            raise RuntimeError("inject failed")
        platform.inject_prompt = _inject

        async def _dismiss(p):
            pass
        platform.dismiss_popups = _dismiss

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "test prompt", "REGULAR", tmp)
        # Without agent, inject failure propagates to outer except -> FAILED
        self.assertEqual(result.status, "failed")

    async def test_run_inject_prompt_exception_agent_fallback_succeeds(self):
        """inject_prompt raises, agent_fallback succeeds -> keyboard.type called."""
        BasePlatform = self.BasePlatform
        platform = TestPlatformFactory.make(BasePlatform)
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        mock_agent_mgr = MagicMock()
        mock_agent_mgr.enabled = True
        platform.agent_manager = mock_agent_mgr

        async def _navigate(p, mode):
            return "REGULAR"
        platform._navigate_and_configure = _navigate

        async def _inject(p, prompt):
            raise RuntimeError("inject failed")
        platform.inject_prompt = _inject

        async def _agent_fb(p, step, error, task):
            pass  # agent succeeds — no raise
        platform._agent_fallback = _agent_fb

        async def _dismiss(p):
            pass
        platform.dismiss_popups = _dismiss

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "test prompt", "REGULAR", tmp)
        # Agent succeeded -> keyboard.type used as fallback typing method
        page.keyboard.type.assert_awaited()
        self.assertEqual(result.status, "complete")

    async def test_run_click_send_exception_falls_to_enter(self):
        """click_send raises, agent_fallback also raises -> keyboard.press('Enter')."""
        platform = TestPlatformFactory.make(self.BasePlatform)
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        async def _navigate(p, mode):
            return "REGULAR"
        platform._navigate_and_configure = _navigate

        async def _click(p):
            raise RuntimeError("no send button")
        platform.click_send = _click

        async def _agent_fb(p, step, error, task):
            raise error
        platform._agent_fallback = _agent_fb

        async def _dismiss(p):
            pass
        platform.dismiss_popups = _dismiss

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "prompt", "REGULAR", tmp)
        page.keyboard.press.assert_awaited_with("Enter")

    async def test_run_timeout_with_partial(self):
        """Polling times out, extract_response returns >500 chars -> status=PARTIAL."""
        platform = TestPlatformFactory.make(self.BasePlatform, response="A" * 600, completion=False)
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        async def _navigate(p, mode):
            return "REGULAR"
        platform._navigate_and_configure = _navigate

        async def _dismiss(p):
            pass
        platform.dismiss_popups = _dismiss

        # Make _poll_completion return False immediately by patching time
        async def _poll(p, max_wait):
            return False
        platform._poll_completion = _poll

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "prompt", "REGULAR", tmp)
        self.assertEqual(result.status, "partial")

    async def test_run_timeout_no_partial(self):
        """Polling times out, extract_response returns <500 chars -> status=TIMEOUT."""
        platform = TestPlatformFactory.make(self.BasePlatform, response="short", completion=False)
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        async def _navigate(p, mode):
            return "REGULAR"
        platform._navigate_and_configure = _navigate

        async def _dismiss(p):
            pass
        platform.dismiss_popups = _dismiss

        async def _poll(p, max_wait):
            return False
        platform._poll_completion = _poll

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "prompt", "REGULAR", tmp)
        self.assertEqual(result.status, "timeout")

    async def test_run_timeout_extract_raises(self):
        """Polling times out, extract_response raises -> status=TIMEOUT."""
        platform = TestPlatformFactory.make(
            self.BasePlatform,
            response=RuntimeError("extract failed"),
            completion=False
        )
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        async def _navigate(p, mode):
            return "REGULAR"
        platform._navigate_and_configure = _navigate

        async def _dismiss(p):
            pass
        platform.dismiss_popups = _dismiss

        async def _poll(p, max_wait):
            return False
        platform._poll_completion = _poll

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "prompt", "REGULAR", tmp)
        self.assertEqual(result.status, "timeout")

    async def test_run_extraction_too_short(self):
        """extract_response returns <200 chars -> status=FAILED."""
        platform = TestPlatformFactory.make(self.BasePlatform, response="short response")
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        async def _navigate(p, mode):
            return "REGULAR"
        platform._navigate_and_configure = _navigate

        async def _dismiss(p):
            pass
        platform.dismiss_popups = _dismiss

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "prompt", "REGULAR", tmp)
        self.assertEqual(result.status, "failed")

    async def test_run_poll_rate_limit(self):
        """During _poll_completion, rate limit detected -> status=RATE_LIMITED."""
        platform = TestPlatformFactory.make(self.BasePlatform)
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        async def _navigate(p, mode):
            return "REGULAR"
        platform._navigate_and_configure = _navigate

        async def _dismiss(p):
            pass
        platform.dismiss_popups = _dismiss

        async def _poll(p, max_wait):
            platform._poll_rate_limit_msg = "rate limited during poll"
            return True
        platform._poll_completion = _poll

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "prompt", "REGULAR", tmp)
        self.assertEqual(result.status, "rate_limited")

    async def test_run_exception_returns_failed(self):
        """Unexpected exception in run body -> status=FAILED."""
        platform = TestPlatformFactory.make(self.BasePlatform)
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        async def _navigate(p, mode):
            raise RuntimeError("unexpected crash")
        platform._navigate_and_configure = _navigate

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "prompt", "REGULAR", tmp)
        self.assertEqual(result.status, "failed")

    async def test_run_deep_mode_uses_deep_timeout(self):
        """DEEP mode uses timeout.deep instead of timeout.regular."""
        platform = TestPlatformFactory.make(self.BasePlatform)
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        async def _navigate(p, mode):
            return "DEEP"
        platform._navigate_and_configure = _navigate

        async def _dismiss(p):
            pass
        platform.dismiss_popups = _dismiss

        poll_max_wait = {}

        async def _poll(p, max_wait):
            poll_max_wait["v"] = max_wait
            return True
        platform._poll_completion = _poll

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "prompt", "DEEP", tmp)
        # deep timeout = 2 (from TimeoutConfig stub)
        self.assertEqual(poll_max_wait.get("v"), 2)

    async def test_run_post_send_exception_with_agent(self):
        """post_send raises, agent fallback also raises -> non-fatal, continues."""
        platform = TestPlatformFactory.make(self.BasePlatform)
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        async def _navigate(p, mode):
            return "REGULAR"
        platform._navigate_and_configure = _navigate

        async def _post_send(p, mode):
            raise RuntimeError("post_send failed")
        platform.post_send = _post_send

        async def _agent_fb(p, step, error, task):
            raise error
        platform._agent_fallback = _agent_fb

        async def _dismiss(p):
            pass
        platform.dismiss_popups = _dismiss

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "prompt", "REGULAR", tmp)
        # post_send failure is non-fatal, should still complete
        self.assertEqual(result.status, "complete")

    async def test_run_rate_limited_token_in_response(self):
        """Response containing '[RATE LIMITED]' passes the length check."""
        platform = TestPlatformFactory.make(self.BasePlatform, response="[RATE LIMITED]")
        page = _make_page()
        platform._setup_dialog_handler = MagicMock()

        async def _navigate(p, mode):
            return "REGULAR"
        platform._navigate_and_configure = _navigate

        async def _dismiss(p):
            pass
        platform.dismiss_popups = _dismiss

        with tempfile.TemporaryDirectory() as tmp:
            result = await platform.run(page, "prompt", "REGULAR", tmp)
        # [RATE LIMITED] is treated as a valid response (not FAILED)
        self.assertNotEqual(result.status, "failed")


class TestPollCompletion(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BasePlatform, PlatformResult, _SignInRequired, _RateLimited = _setup()
        self.platform = TestPlatformFactory.make(BasePlatform)

    async def test_poll_completion_immediate_true(self):
        """completion_check returns True immediately -> returns True."""
        self.platform.completion_check = AsyncMock(return_value=True)
        self.platform.check_rate_limit = AsyncMock(return_value=None)

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await self.platform._poll_completion(MagicMock(), max_wait_s=60)
        self.assertTrue(result)

    async def test_poll_completion_rate_limit_during_poll(self):
        """check_rate_limit returns message -> returns True with _poll_rate_limit_msg set."""
        self.platform.completion_check = AsyncMock(return_value=False)
        self.platform.check_rate_limit = AsyncMock(return_value="rate limit hit")

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await self.platform._poll_completion(MagicMock(), max_wait_s=60)
        self.assertTrue(result)
        self.assertEqual(self.platform._poll_rate_limit_msg, "rate limit hit")

    async def test_poll_completion_timeout(self):
        """Polling exceeds max_wait -> returns False."""
        self.platform.completion_check = AsyncMock(return_value=False)
        self.platform.check_rate_limit = AsyncMock(return_value=None)

        import time
        call_count = {"n": 0}
        original_monotonic = time.monotonic

        def fake_monotonic():
            call_count["n"] += 1
            # After first call (start), always return start + 100 so we exceed max_wait
            if call_count["n"] <= 1:
                return original_monotonic()
            return original_monotonic() + 100
        with patch("time.monotonic", side_effect=fake_monotonic), \
             patch("asyncio.sleep", new=AsyncMock()):
            result = await self.platform._poll_completion(MagicMock(), max_wait_s=1)
        self.assertFalse(result)

    async def test_poll_completion_errors_trigger_agent_after_5(self):
        """completion_check raises 5 times -> agent_fallback called."""
        exc = RuntimeError("completion error")
        self.platform.completion_check = AsyncMock(side_effect=exc)
        self.platform.check_rate_limit = AsyncMock(return_value=None)

        fallback_called = {"v": False}

        async def _agent_fb(p, step, error, task):
            fallback_called["v"] = True
            return "yes done"
        self.platform._agent_fallback = _agent_fb

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await self.platform._poll_completion(MagicMock(), max_wait_s=60)
        self.assertTrue(fallback_called["v"])
        self.assertTrue(result)

    async def test_poll_completion_errors_agent_raises(self):
        """completion_check raises 5x, agent also raises -> re-raises."""
        exc = RuntimeError("completion error")
        self.platform.completion_check = AsyncMock(side_effect=exc)
        self.platform.check_rate_limit = AsyncMock(return_value=None)

        async def _agent_fb(p, step, error, task):
            raise error
        self.platform._agent_fallback = _agent_fb

        with patch("asyncio.sleep", new=AsyncMock()):
            with self.assertRaises(RuntimeError):
                await self.platform._poll_completion(MagicMock(), max_wait_s=60)

    async def test_poll_completion_check_rate_limit_exception(self):
        """check_rate_limit raising is swallowed, polling continues."""
        self.platform.check_rate_limit = AsyncMock(side_effect=RuntimeError("rl check error"))
        call_count = {"n": 0}

        async def _completion(page):
            call_count["n"] += 1
            return call_count["n"] >= 1
        self.platform.completion_check = _completion

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await self.platform._poll_completion(MagicMock(), max_wait_s=60)
        self.assertTrue(result)

    async def test_poll_completion_agent_returns_no(self):
        """Agent fallback returns non-'yes' -> consecutive_errors resets, poll continues."""
        exc = RuntimeError("completion error")
        call_count = {"n": 0}

        async def _completion(page):
            call_count["n"] += 1
            if call_count["n"] <= 5:
                raise exc
            return True  # eventually succeeds
        self.platform.completion_check = _completion
        self.platform.check_rate_limit = AsyncMock(return_value=None)

        async def _agent_fb(p, step, error, task):
            return "no, not done yet"
        self.platform._agent_fallback = _agent_fb

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await self.platform._poll_completion(MagicMock(), max_wait_s=60)
        self.assertTrue(result)


class TestClickSend(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BasePlatform, PlatformResult, _SignInRequired, _RateLimited = _setup()
        self.platform = TestPlatformFactory.make(BasePlatform)

    async def test_click_send_first_selector_match(self):
        """First selector with visible button is clicked."""
        page = _make_page()
        visible_btn = MagicMock()
        visible_btn.first = visible_btn
        visible_btn.count = AsyncMock(return_value=1)
        visible_btn.is_visible = AsyncMock(return_value=True)
        visible_btn.click = AsyncMock()
        page.locator = MagicMock(return_value=visible_btn)

        await self.platform.click_send(page)
        visible_btn.click.assert_awaited_once()

    async def test_click_send_text_button_match(self):
        """No selector match, but get_by_role finds 'Send' button."""
        page = _make_page()
        no_btn = MagicMock()
        no_btn.first = no_btn
        no_btn.count = AsyncMock(return_value=0)
        no_btn.is_visible = AsyncMock(return_value=False)
        page.locator = MagicMock(return_value=no_btn)

        send_btn = MagicMock()
        send_btn.first = send_btn
        send_btn.count = AsyncMock(return_value=1)
        send_btn.is_visible = AsyncMock(return_value=True)
        send_btn.click = AsyncMock()

        no_role_btn = MagicMock()
        no_role_btn.first = no_role_btn
        no_role_btn.count = AsyncMock(return_value=0)
        no_role_btn.is_visible = AsyncMock(return_value=False)

        def _get_by_role(role, **kwargs):
            name = kwargs.get("name", "")
            if name == "Send":
                return send_btn
            return no_role_btn
        page.get_by_role = _get_by_role

        await self.platform.click_send(page)
        send_btn.click.assert_awaited_once()

    async def test_click_send_no_button_falls_to_enter(self):
        """No matches at all -> keyboard.press('Enter') called."""
        page = _make_page()
        no_btn = MagicMock()
        no_btn.first = no_btn
        no_btn.count = AsyncMock(return_value=0)
        no_btn.is_visible = AsyncMock(return_value=False)
        page.locator = MagicMock(return_value=no_btn)

        no_role_btn = MagicMock()
        no_role_btn.first = no_role_btn
        no_role_btn.count = AsyncMock(return_value=0)
        no_role_btn.is_visible = AsyncMock(return_value=False)
        page.get_by_role = MagicMock(return_value=no_role_btn)

        async def _agent_fb(p, step, error, task):
            raise error
        self.platform._agent_fallback = _agent_fb

        await self.platform.click_send(page)
        page.keyboard.press.assert_awaited_with("Enter")

    async def test_click_send_agent_fallback_succeeds(self):
        """No selectors match but agent fallback succeeds -> returns without Enter."""
        page = _make_page()
        no_btn = MagicMock()
        no_btn.first = no_btn
        no_btn.count = AsyncMock(return_value=0)
        no_btn.is_visible = AsyncMock(return_value=False)
        page.locator = MagicMock(return_value=no_btn)

        no_role_btn = MagicMock()
        no_role_btn.first = no_role_btn
        no_role_btn.count = AsyncMock(return_value=0)
        no_role_btn.is_visible = AsyncMock(return_value=False)
        page.get_by_role = MagicMock(return_value=no_role_btn)

        async def _agent_fb(p, step, error, task):
            pass  # Agent succeeds
        self.platform._agent_fallback = _agent_fb

        await self.platform.click_send(page)
        page.keyboard.press.assert_not_awaited()


class TestInjectPrompt(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BasePlatform, PlatformResult, _SignInRequired, _RateLimited = _setup()
        self.platform = TestPlatformFactory.make(BasePlatform)

    async def test_inject_prompt_exec_command(self):
        """INJECTION_METHODS=execCommand -> _inject_exec_command called."""
        import platforms.base as base_mod
        page = _make_page()
        called = {"v": False}

        async def _exec(p, prompt):
            called["v"] = True
            return len(prompt)
        self.platform._inject_exec_command = _exec

        orig = base_mod.INJECTION_METHODS
        base_mod.INJECTION_METHODS = {PLATFORM_NAME: "execCommand"}
        try:
            await self.platform.inject_prompt(page, "hello")
        finally:
            base_mod.INJECTION_METHODS = orig
        self.assertTrue(called["v"])

    async def test_inject_prompt_physical_type(self):
        """INJECTION_METHODS=physical_type -> _inject_physical_type called."""
        import platforms.base as base_mod
        page = _make_page()
        called = {"v": False}

        async def _phys(p, prompt):
            called["v"] = True
        self.platform._inject_physical_type = _phys

        orig = base_mod.INJECTION_METHODS
        base_mod.INJECTION_METHODS = {PLATFORM_NAME: "physical_type"}
        try:
            await self.platform.inject_prompt(page, "hello")
        finally:
            base_mod.INJECTION_METHODS = orig
        self.assertTrue(called["v"])

    async def test_inject_prompt_fill(self):
        """INJECTION_METHODS=fill -> _inject_fill called."""
        import platforms.base as base_mod
        page = _make_page()
        called = {"v": False}

        async def _fill(p, prompt):
            called["v"] = True
        self.platform._inject_fill = _fill

        orig = base_mod.INJECTION_METHODS
        base_mod.INJECTION_METHODS = {PLATFORM_NAME: "fill"}
        try:
            await self.platform.inject_prompt(page, "hello")
        finally:
            base_mod.INJECTION_METHODS = orig
        self.assertTrue(called["v"])

    async def test_inject_prompt_unknown_raises(self):
        """Unknown injection method -> NotImplementedError."""
        import platforms.base as base_mod
        page = _make_page()

        orig = base_mod.INJECTION_METHODS
        base_mod.INJECTION_METHODS = {PLATFORM_NAME: "unknown_method"}
        try:
            with self.assertRaises(NotImplementedError):
                await self.platform.inject_prompt(page, "hello")
        finally:
            base_mod.INJECTION_METHODS = orig


class TestExtractWithFallback(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BasePlatform, PlatformResult, _SignInRequired, _RateLimited = _setup()
        self.platform = TestPlatformFactory.make(BasePlatform)

    async def test_extract_with_fallback_success(self):
        """extract_response returns >200 chars -> returned as-is."""
        self.platform.extract_response = AsyncMock(return_value="A" * 300)
        async def _agent_fb(p, step, error, task):
            raise error
        self.platform._agent_fallback = _agent_fb

        result = await self.platform._extract_with_fallback(MagicMock())
        self.assertEqual(result, "A" * 300)

    async def test_extract_with_fallback_exception_uses_agent(self):
        """extract_response raises -> agent returns text."""
        self.platform.extract_response = AsyncMock(side_effect=RuntimeError("extract failed"))

        async def _agent_fb(p, step, error, task):
            return "A" * 300
        self.platform._agent_fallback = _agent_fb

        result = await self.platform._extract_with_fallback(MagicMock())
        self.assertEqual(result, "A" * 300)

    async def test_extract_with_fallback_short_triggers_agent(self):
        """extract_response returns <200 chars -> agent returns longer text."""
        self.platform.extract_response = AsyncMock(return_value="short")

        async def _agent_fb(p, step, error, task):
            return "A" * 300
        self.platform._agent_fallback = _agent_fb

        result = await self.platform._extract_with_fallback(MagicMock())
        self.assertEqual(result, "A" * 300)

    async def test_extract_with_fallback_short_agent_also_short(self):
        """extract_response <200 chars, agent returns <50 chars -> original kept."""
        self.platform.extract_response = AsyncMock(return_value="original short")

        async def _agent_fb(p, step, error, task):
            return "tiny"  # < 50 chars
        self.platform._agent_fallback = _agent_fb

        result = await self.platform._extract_with_fallback(MagicMock())
        self.assertEqual(result, "original short")

    async def test_extract_with_fallback_short_agent_raises(self):
        """extract_response <200 chars, agent raises -> original kept."""
        self.platform.extract_response = AsyncMock(return_value="original short")

        async def _agent_fb(p, step, error, task):
            raise RuntimeError("agent failed")
        self.platform._agent_fallback = _agent_fb

        result = await self.platform._extract_with_fallback(MagicMock())
        self.assertEqual(result, "original short")

    async def test_extract_with_fallback_rate_limited_token_skips_agent(self):
        """Response with '[RATE LIMITED]' token skips agent fallback check."""
        self.platform.extract_response = AsyncMock(return_value="[RATE LIMITED]")
        agent_called = {"v": False}

        async def _agent_fb(p, step, error, task):
            agent_called["v"] = True
            return "agent result"
        self.platform._agent_fallback = _agent_fb

        result = await self.platform._extract_with_fallback(MagicMock())
        self.assertFalse(agent_called["v"])
        self.assertEqual(result, "[RATE LIMITED]")

    async def test_extract_with_fallback_exception_agent_returns_none(self):
        """extract_response raises, agent returns None -> response is empty string."""
        self.platform.extract_response = AsyncMock(side_effect=RuntimeError("extract failed"))

        async def _agent_fb(p, step, error, task):
            return None
        self.platform._agent_fallback = _agent_fb

        result = await self.platform._extract_with_fallback(MagicMock())
        self.assertEqual(result, "")


class TestSaveAndResult(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BasePlatform, PlatformResult, _SignInRequired, _RateLimited = _setup()
        self.platform = TestPlatformFactory.make(BasePlatform)
        self.PlatformResult = PlatformResult

    def test_save_and_result_creates_file(self):
        """_save_and_result creates file and returns correct PlatformResult."""
        import time
        with tempfile.TemporaryDirectory() as tmp:
            t0 = time.monotonic()
            response = "Response text " * 20
            result = self.platform._save_and_result(response, tmp, "REGULAR", t0, "complete")

        self.assertEqual(result.status, "complete")
        self.assertEqual(result.chars, len(response))
        self.assertEqual(result.platform, PLATFORM_NAME)
        self.assertEqual(result.mode_used, "REGULAR")
        self.assertTrue(Path(result.file).name.endswith(".md"))


class TestCheckRateLimit(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BasePlatform, PlatformResult, _SignInRequired, _RateLimited = _setup()
        self.platform = TestPlatformFactory.make(BasePlatform)

    async def test_check_rate_limit_detects_pattern(self):
        """Default check_rate_limit finds 'rate limit' text in page."""
        BasePlatform, _, _, _ = _setup()

        class DefaultPlatform(BasePlatform):
            name = PLATFORM_NAME
            url = PLATFORM_URL
            display_name = "Test Platform"

            async def configure_mode(self, page, mode):
                return "REGULAR"

            async def completion_check(self, page):
                return True

            async def extract_response(self, page):
                return "A" * 300

        platform = DefaultPlatform()
        page = _make_page()

        visible_el = MagicMock()
        visible_el.first = visible_el
        visible_el.count = AsyncMock(return_value=1)
        visible_el.is_visible = AsyncMock(return_value=True)
        page.get_by_text = MagicMock(return_value=visible_el)

        result = await platform.check_rate_limit(page)
        self.assertIsNotNone(result)

    async def test_check_rate_limit_returns_none_when_no_pattern(self):
        """Default check_rate_limit returns None when nothing matches."""
        BasePlatform, _, _, _ = _setup()

        class DefaultPlatform(BasePlatform):
            name = PLATFORM_NAME
            url = PLATFORM_URL
            display_name = "Test Platform"

            async def configure_mode(self, page, mode):
                return "REGULAR"

            async def completion_check(self, page):
                return True

            async def extract_response(self, page):
                return "A" * 300

        platform = DefaultPlatform()
        page = _make_page()

        invisible_el = MagicMock()
        invisible_el.first = invisible_el
        invisible_el.count = AsyncMock(return_value=0)
        invisible_el.is_visible = AsyncMock(return_value=False)
        page.get_by_text = MagicMock(return_value=invisible_el)

        result = await platform.check_rate_limit(page)
        self.assertIsNone(result)

    async def test_check_rate_limit_exception_swallowed(self):
        """Exception in rate limit check is swallowed, returns None."""
        BasePlatform, _, _, _ = _setup()

        class DefaultPlatform(BasePlatform):
            name = PLATFORM_NAME
            url = PLATFORM_URL
            display_name = "Test Platform"

            async def configure_mode(self, page, mode):
                return "REGULAR"

            async def completion_check(self, page):
                return True

            async def extract_response(self, page):
                return "A" * 300

        platform = DefaultPlatform()
        page = _make_page()
        page.get_by_text = MagicMock(side_effect=RuntimeError("locator error"))

        result = await platform.check_rate_limit(page)
        self.assertIsNone(result)


class TestAgentFallbackMethod(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BasePlatform, PlatformResult, _SignInRequired, _RateLimited = _setup()
        self.platform = TestPlatformFactory.make(BasePlatform)

    async def test_agent_fallback_no_manager_raises(self):
        """No agent_manager -> raises original error."""
        self.platform.agent_manager = None
        error = RuntimeError("original")
        with self.assertRaises(RuntimeError) as ctx:
            await self.platform._agent_fallback(MagicMock(), "step", error, "task")
        self.assertIs(ctx.exception, error)

    async def test_agent_fallback_disabled_raises(self):
        """agent_manager.enabled=False -> raises original error."""
        mgr = MagicMock()
        mgr.enabled = False
        self.platform.agent_manager = mgr
        error = RuntimeError("original")
        with self.assertRaises(RuntimeError) as ctx:
            await self.platform._agent_fallback(MagicMock(), "step", error, "task")
        self.assertIs(ctx.exception, error)

    async def test_agent_fallback_enabled_calls_manager(self):
        """agent_manager enabled -> calls manager.fallback."""
        mgr = MagicMock()
        mgr.enabled = True
        mgr.fallback = AsyncMock(return_value="fallback result")
        self.platform.agent_manager = mgr

        from agent_fallback import FallbackStep
        result = await self.platform._agent_fallback(
            MagicMock(), "inject_prompt", RuntimeError("err"), "task"
        )
        mgr.fallback.assert_awaited_once()
        self.assertEqual(result, "fallback result")


class TestAbstractMethods(unittest.IsolatedAsyncioTestCase):
    """Tests that exercise the abstract method stubs in BasePlatform."""

    def setUp(self):
        BasePlatform, PlatformResult, _SignInRequired, _RateLimited = _setup()
        self.BasePlatform = BasePlatform

    async def test_configure_mode_raises_not_implemented(self):
        """BasePlatform.configure_mode raises NotImplementedError."""
        class Bare(self.BasePlatform):
            name = PLATFORM_NAME
            url = PLATFORM_URL
            display_name = "Bare"

            async def completion_check(self, page):
                return True

            async def extract_response(self, page):
                return "x" * 300

        b = Bare()
        with self.assertRaises(NotImplementedError):
            await b.configure_mode(MagicMock(), "REGULAR")

    async def test_completion_check_raises_not_implemented(self):
        """BasePlatform.completion_check raises NotImplementedError."""
        class Bare(self.BasePlatform):
            name = PLATFORM_NAME
            url = PLATFORM_URL
            display_name = "Bare"

            async def configure_mode(self, page, mode):
                return "REGULAR"

            async def extract_response(self, page):
                return "x" * 300

        b = Bare()
        with self.assertRaises(NotImplementedError):
            await b.completion_check(MagicMock())

    async def test_extract_response_raises_not_implemented(self):
        """BasePlatform.extract_response raises NotImplementedError."""
        class Bare(self.BasePlatform):
            name = PLATFORM_NAME
            url = PLATFORM_URL
            display_name = "Bare"

            async def configure_mode(self, page, mode):
                return "REGULAR"

            async def completion_check(self, page):
                return True

        b = Bare()
        with self.assertRaises(NotImplementedError):
            await b.extract_response(MagicMock())


class TestPollCompletionFalseResets(unittest.IsolatedAsyncioTestCase):
    """Tests that consecutive_errors resets when completion_check returns False."""

    def setUp(self):
        BasePlatform, PlatformResult, _SignInRequired, _RateLimited = _setup()
        self.platform = TestPlatformFactory.make(BasePlatform)

    async def test_poll_completion_false_then_true_resets_errors(self):
        """completion_check returns False (no error) then True -> consecutive_errors reset."""
        self.platform.check_rate_limit = AsyncMock(return_value=None)
        call_count = {"n": 0}

        async def _completion(page):
            call_count["n"] += 1
            if call_count["n"] < 3:
                return False  # not done yet (covers line 267 - consecutive_errors = 0)
            return True
        self.platform.completion_check = _completion

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await self.platform._poll_completion(MagicMock(), max_wait_s=60)
        self.assertTrue(result)
        self.assertGreaterEqual(call_count["n"], 3)


if __name__ == "__main__":
    unittest.main()
