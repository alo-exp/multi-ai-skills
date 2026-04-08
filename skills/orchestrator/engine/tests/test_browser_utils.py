"""Unit tests for BrowserMixin (browser_utils.py)."""

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
    # Reload browser_utils fresh
    for mod in list(sys.modules):
        if "browser_utils" in mod:
            del sys.modules[mod]
    from platforms.browser_utils import BrowserMixin, _SignInRequired, _RateLimited
    return BrowserMixin, _SignInRequired, _RateLimited


def _make_page(url="https://test.com", title="Test"):
    page = MagicMock()
    page.url = url
    page.title = AsyncMock(return_value=title)
    page.on = MagicMock()
    page.wait_for_timeout = AsyncMock()
    page.goto = AsyncMock()

    def locator(sel):
        loc = MagicMock()
        loc.first = loc
        loc.count = AsyncMock(return_value=0)
        loc.is_visible = AsyncMock(return_value=False)
        loc.click = AsyncMock()
        return loc
    page.locator = locator

    def get_by_role(role, **kwargs):
        btn = MagicMock()
        btn.first = btn
        btn.count = AsyncMock(return_value=0)
        btn.is_visible = AsyncMock(return_value=False)
        btn.click = AsyncMock()
        return btn
    page.get_by_role = get_by_role
    return page


class ConcreteMixin:
    """Concrete subclass of BrowserMixin for testing."""
    display_name = "Test"
    url = PLATFORM_URL
    name = PLATFORM_NAME

    async def _agent_fallback(self, page, step, error, task):
        raise error

    async def check_rate_limit(self, page):
        return None

    async def configure_mode(self, page, mode):
        return "REGULAR"


class TestSetupDialogHandler(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BrowserMixin, _SignInRequired, _RateLimited = _load()
        # Clear registered pages to isolate tests
        BrowserMixin._dialog_registered_pages.clear()
        self.BrowserMixin = BrowserMixin

        class Mixin(ConcreteMixin, BrowserMixin):
            pass
        self.mixin = Mixin()

    async def test_setup_dialog_handler_registers_once(self):
        """Calling _setup_dialog_handler twice on same page calls page.on only once."""
        page = _make_page()
        self.mixin._setup_dialog_handler(page)
        self.mixin._setup_dialog_handler(page)
        page.on.assert_called_once_with("dialog", unittest.mock.ANY)

    async def test_setup_dialog_handler_second_page(self):
        """Calling _setup_dialog_handler on different pages calls page.on for each."""
        page1 = _make_page()
        page2 = _make_page()
        self.mixin._setup_dialog_handler(page1)
        self.mixin._setup_dialog_handler(page2)
        page1.on.assert_called_once()
        page2.on.assert_called_once()


class TestDialogHandler(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BrowserMixin, _SignInRequired, _RateLimited = _load()
        BrowserMixin._dialog_registered_pages.clear()
        self.BrowserMixin = BrowserMixin

        class Mixin(ConcreteMixin, BrowserMixin):
            pass
        self.mixin = Mixin()

    async def test_dialog_accept_callback_invoked(self):
        """The _accept_dialog callback actually calls dialog.accept()."""
        page = _make_page()
        captured_handler = {}

        def _on(event, handler):
            captured_handler["handler"] = handler
        page.on = _on

        self.mixin._setup_dialog_handler(page)
        self.assertIn("handler", captured_handler)

        dialog = MagicMock()
        dialog.type = "alert"
        dialog.message = "test message"
        dialog.accept = AsyncMock()
        await captured_handler["handler"](dialog)
        dialog.accept.assert_awaited_once()

    async def test_dialog_accept_exception_swallowed(self):
        """The _accept_dialog callback swallows exceptions from dialog.accept()."""
        page = _make_page()
        captured_handler = {}

        def _on(event, handler):
            captured_handler["handler"] = handler
        page.on = _on

        self.mixin._setup_dialog_handler(page)
        dialog = MagicMock()
        dialog.type = "confirm"
        dialog.message = None
        dialog.accept = AsyncMock(side_effect=RuntimeError("dialog error"))
        # Should not raise
        await captured_handler["handler"](dialog)


class TestDismissPopups(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BrowserMixin, _SignInRequired, _RateLimited = _load()
        BrowserMixin._dialog_registered_pages.clear()
        self.BrowserMixin = BrowserMixin

        class Mixin(ConcreteMixin, BrowserMixin):
            pass
        self.mixin = Mixin()

    async def test_dismiss_popups_clicks_visible(self):
        """dismiss_popups clicks a visible popup button."""
        page = _make_page()
        visible_loc = MagicMock()
        visible_loc.first = visible_loc
        visible_loc.count = AsyncMock(return_value=1)
        visible_loc.is_visible = AsyncMock(return_value=True)
        visible_loc.click = AsyncMock()
        page.locator = MagicMock(return_value=visible_loc)
        page.wait_for_timeout = AsyncMock()
        await self.mixin.dismiss_popups(page)
        visible_loc.click.assert_called()

    async def test_dismiss_popups_skips_invisible(self):
        """dismiss_popups skips when count is 0."""
        page = _make_page()
        invisible_loc = MagicMock()
        invisible_loc.first = invisible_loc
        invisible_loc.count = AsyncMock(return_value=0)
        invisible_loc.is_visible = AsyncMock(return_value=False)
        invisible_loc.click = AsyncMock()
        page.locator = MagicMock(return_value=invisible_loc)
        await self.mixin.dismiss_popups(page)
        invisible_loc.click.assert_not_called()

    async def test_dismiss_popups_max_three(self):
        """dismiss_popups stops after dismissing 3 popups."""
        page = _make_page()
        click_count = {"n": 0}

        visible_loc = MagicMock()
        visible_loc.first = visible_loc
        visible_loc.count = AsyncMock(return_value=1)
        visible_loc.is_visible = AsyncMock(return_value=True)

        async def _click(**kwargs):
            click_count["n"] += 1
        visible_loc.click = _click
        page.locator = MagicMock(return_value=visible_loc)
        page.wait_for_timeout = AsyncMock()
        await self.mixin.dismiss_popups(page)
        self.assertEqual(click_count["n"], 3)

    async def test_dismiss_popups_exception_handled(self):
        """dismiss_popups swallows exceptions from locator interaction."""
        page = _make_page()
        bad_loc = MagicMock()
        bad_loc.first = bad_loc
        bad_loc.count = AsyncMock(side_effect=RuntimeError("locator error"))
        page.locator = MagicMock(return_value=bad_loc)
        # Should not raise
        await self.mixin.dismiss_popups(page)


class TestIsChatReady(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BrowserMixin, _SignInRequired, _RateLimited = _load()
        BrowserMixin._dialog_registered_pages.clear()

        class Mixin(ConcreteMixin, BrowserMixin):
            pass
        self.mixin = Mixin()

    async def test_is_chat_ready_returns_true(self):
        """Returns True for a valid non-sign-in URL with no error title."""
        page = _make_page(url="https://chatgpt.com", title="ChatGPT")

        def locator(sel):
            loc = MagicMock()
            loc.first = loc
            loc.count = AsyncMock(return_value=0)
            loc.is_visible = AsyncMock(return_value=False)
            return loc
        page.locator = locator
        result = await self.mixin.is_chat_ready(page)
        self.assertTrue(result)

    async def test_is_chat_ready_false_sign_in(self):
        """Returns False when URL has /login."""
        page = _make_page(url="https://chatgpt.com/login")

        def locator(sel):
            loc = MagicMock()
            loc.first = loc
            loc.count = AsyncMock(return_value=0)
            loc.is_visible = AsyncMock(return_value=False)
            return loc
        page.locator = locator
        result = await self.mixin.is_chat_ready(page)
        self.assertFalse(result)

    async def test_is_chat_ready_false_blank(self):
        """Returns False for about:blank."""
        page = _make_page(url="about:blank", title="")

        def locator(sel):
            loc = MagicMock()
            loc.first = loc
            loc.count = AsyncMock(return_value=0)
            loc.is_visible = AsyncMock(return_value=False)
            return loc
        page.locator = locator
        result = await self.mixin.is_chat_ready(page)
        self.assertFalse(result)

    async def test_is_chat_ready_false_error_title(self):
        """Returns False when page title contains error pattern."""
        page = _make_page(url="https://test.com", title="404 Not Found")

        def locator(sel):
            loc = MagicMock()
            loc.first = loc
            loc.count = AsyncMock(return_value=0)
            loc.is_visible = AsyncMock(return_value=False)
            return loc
        page.locator = locator
        result = await self.mixin.is_chat_ready(page)
        self.assertFalse(result)


class TestIsSignInPage(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BrowserMixin, _SignInRequired, _RateLimited = _load()
        BrowserMixin._dialog_registered_pages.clear()

        class Mixin(ConcreteMixin, BrowserMixin):
            pass
        self.mixin = Mixin()

    async def test_is_sign_in_page_url_match(self):
        """Returns True when URL contains /signin."""
        page = _make_page(url="https://example.com/signin")
        result = await self.mixin.is_sign_in_page(page)
        self.assertTrue(result)

    async def test_is_sign_in_page_password_field(self):
        """Returns True when password input is visible."""
        page = _make_page(url="https://test.com/chat")
        pw_loc = MagicMock()
        pw_loc.first = pw_loc
        pw_loc.count = AsyncMock(return_value=1)
        pw_loc.is_visible = AsyncMock(return_value=True)
        page.locator = MagicMock(return_value=pw_loc)
        result = await self.mixin.is_sign_in_page(page)
        self.assertTrue(result)

    async def test_is_sign_in_page_false(self):
        """Returns False when URL is normal and no password field."""
        page = _make_page(url="https://test.com/chat")
        no_pw = MagicMock()
        no_pw.first = no_pw
        no_pw.count = AsyncMock(return_value=0)
        no_pw.is_visible = AsyncMock(return_value=False)
        page.locator = MagicMock(return_value=no_pw)
        result = await self.mixin.is_sign_in_page(page)
        self.assertFalse(result)


class TestNavigateAndConfigure(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BrowserMixin, self._SignInRequired, self._RateLimited = _load()
        BrowserMixin._dialog_registered_pages.clear()
        self.BrowserMixin = BrowserMixin

    def _make_mixin(self, sign_in=False, rate_msg=None, chat_ready=True, configure_ok=True):
        BrowserMixin = self.BrowserMixin

        class Mixin(ConcreteMixin, BrowserMixin):
            async def check_rate_limit(self, page):
                return rate_msg

            async def configure_mode(self, page, mode):
                if configure_ok:
                    return "REGULAR"
                raise RuntimeError("configure_mode failed")

        mixin = Mixin()
        # Patch is_sign_in_page and is_chat_ready on the instance
        async def _is_sign_in(p):
            return sign_in
        async def _is_chat_ready(p):
            return chat_ready
        mixin.is_sign_in_page = _is_sign_in
        mixin.is_chat_ready = _is_chat_ready
        return mixin

    async def test_navigate_and_configure_success(self):
        """Happy path: returns mode_label from configure_mode."""
        mixin = self._make_mixin()
        page = _make_page()

        # Make dismiss_popups a no-op
        async def _dismiss(p):
            pass
        mixin.dismiss_popups = _dismiss

        result = await mixin._navigate_and_configure(page, "REGULAR")
        self.assertEqual(result, "REGULAR")

    async def test_navigate_and_configure_sign_in_raises(self):
        """Raises _SignInRequired when is_sign_in_page returns True."""
        _SignInRequired = self._SignInRequired
        mixin = self._make_mixin(sign_in=True)
        page = _make_page()

        async def _dismiss(p):
            pass
        mixin.dismiss_popups = _dismiss

        with self.assertRaises(_SignInRequired):
            await mixin._navigate_and_configure(page, "REGULAR")

    async def test_navigate_and_configure_rate_limited(self):
        """Raises _RateLimited when check_rate_limit returns a message."""
        _RateLimited = self._RateLimited
        mixin = self._make_mixin(rate_msg="rate limit reached")
        page = _make_page()

        async def _dismiss(p):
            pass
        mixin.dismiss_popups = _dismiss

        with self.assertRaises(_RateLimited):
            await mixin._navigate_and_configure(page, "REGULAR")

    async def test_navigate_and_configure_nav_retry(self):
        """First goto raises, second succeeds; no error propagated."""
        mixin = self._make_mixin()
        page = _make_page()
        call_count = {"n": 0}

        async def _goto(url, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("nav failed")
        page.goto = _goto

        async def _dismiss(p):
            pass
        mixin.dismiss_popups = _dismiss

        result = await mixin._navigate_and_configure(page, "REGULAR")
        self.assertEqual(result, "REGULAR")
        self.assertEqual(call_count["n"], 2)

    async def test_navigate_and_configure_chat_not_ready_agent_fallback(self):
        """When is_chat_ready returns False, agent fallback is triggered (swallowed)."""
        mixin = self._make_mixin(chat_ready=False)
        page = _make_page()
        fallback_called = {"v": False}

        async def _agent_fallback(p, step, error, task):
            fallback_called["v"] = True
            raise error
        mixin._agent_fallback = _agent_fallback

        async def _dismiss(p):
            pass
        mixin.dismiss_popups = _dismiss

        # Should not raise even though agent fallback raises
        result = await mixin._navigate_and_configure(page, "REGULAR")
        self.assertTrue(fallback_called["v"])
        self.assertEqual(result, "REGULAR")

    async def test_navigate_and_configure_configure_mode_fails(self):
        """configure_mode failure uses agent fallback, falls back to 'Agent-configured'."""
        mixin = self._make_mixin(configure_ok=False)
        page = _make_page()

        async def _agent_fallback(p, step, error, task):
            raise error
        mixin._agent_fallback = _agent_fallback

        async def _dismiss(p):
            pass
        mixin.dismiss_popups = _dismiss

        result = await mixin._navigate_and_configure(page, "REGULAR")
        self.assertEqual(result, "Agent-configured")

    async def test_navigate_both_retries_fail_then_agent_fallback_raises(self):
        """Both nav attempts fail, agent fallback also fails -> RuntimeError raised."""
        mixin = self._make_mixin()
        page = _make_page()

        async def _goto(url, **kwargs):
            raise RuntimeError("nav error")
        page.goto = _goto

        async def _agent_fallback(p, step, error, task):
            raise error
        mixin._agent_fallback = _agent_fallback

        async def _dismiss(p):
            pass
        mixin.dismiss_popups = _dismiss

        with self.assertRaises(RuntimeError):
            await mixin._navigate_and_configure(page, "REGULAR")

    async def test_navigate_sign_in_agent_fallback_succeeds(self):
        """is_sign_in_page True but agent fallback recovers (second check returns False)."""
        BrowserMixin = self.BrowserMixin
        call_count = {"n": 0}

        class Mixin(ConcreteMixin, BrowserMixin):
            async def check_rate_limit(self, page):
                return None

            async def configure_mode(self, page, mode):
                return "REGULAR"

        mixin = Mixin()

        async def _is_sign_in(p):
            call_count["n"] += 1
            # First call True (triggers agent), second call False (recovered)
            return call_count["n"] == 1
        mixin.is_sign_in_page = _is_sign_in

        async def _is_chat_ready(p):
            return True
        mixin.is_chat_ready = _is_chat_ready

        async def _agent_fallback(p, step, error, task):
            pass  # Agent succeeds (no raise)
        mixin._agent_fallback = _agent_fallback

        async def _dismiss(p):
            pass
        mixin.dismiss_popups = _dismiss

        result = await mixin._navigate_and_configure(page=_make_page(), mode="REGULAR")
        self.assertEqual(result, "REGULAR")

    async def test_navigate_chat_not_ready_agent_succeeds(self):
        """chat not ready but agent fallback succeeds (no error raised)."""
        BrowserMixin = self.BrowserMixin

        class Mixin(ConcreteMixin, BrowserMixin):
            async def check_rate_limit(self, page):
                return None

            async def configure_mode(self, page, mode):
                return "REGULAR"

        mixin = Mixin()

        async def _is_sign_in(p):
            return False
        mixin.is_sign_in_page = _is_sign_in

        async def _is_chat_ready(p):
            return False
        mixin.is_chat_ready = _is_chat_ready

        fallback_called = {"v": False}

        async def _agent_fallback(p, step, error, task):
            fallback_called["v"] = True
            # Succeed silently
        mixin._agent_fallback = _agent_fallback

        async def _dismiss(p):
            pass
        mixin.dismiss_popups = _dismiss

        result = await mixin._navigate_and_configure(page=_make_page(), mode="REGULAR")
        self.assertTrue(fallback_called["v"])
        self.assertEqual(result, "REGULAR")


class TestIsChatReadyTitleException(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BrowserMixin, _SignInRequired, _RateLimited = _load()
        BrowserMixin._dialog_registered_pages.clear()

        class Mixin(ConcreteMixin, BrowserMixin):
            pass
        self.mixin = Mixin()

    async def test_is_chat_ready_title_exception_ignored(self):
        """page.title() raising is swallowed — still returns True for valid URL."""
        page = _make_page(url="https://test.com/chat")
        page.title = AsyncMock(side_effect=RuntimeError("no title"))

        def locator(sel):
            loc = MagicMock()
            loc.first = loc
            loc.count = AsyncMock(return_value=0)
            loc.is_visible = AsyncMock(return_value=False)
            return loc
        page.locator = locator

        result = await self.mixin.is_chat_ready(page)
        self.assertTrue(result)


class TestIsSignInPageException(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BrowserMixin, _SignInRequired, _RateLimited = _load()
        BrowserMixin._dialog_registered_pages.clear()

        class Mixin(ConcreteMixin, BrowserMixin):
            pass
        self.mixin = Mixin()

    async def test_is_sign_in_page_locator_exception(self):
        """Exception from locator is swallowed, returns False."""
        page = _make_page(url="https://test.com/chat")
        bad_loc = MagicMock()
        bad_loc.first = bad_loc
        bad_loc.count = AsyncMock(side_effect=RuntimeError("locator error"))
        page.locator = MagicMock(return_value=bad_loc)
        result = await self.mixin.is_sign_in_page(page)
        self.assertFalse(result)


class TestForceFullReload(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        BrowserMixin, _SignInRequired, _RateLimited = _load()
        BrowserMixin._dialog_registered_pages.clear()

        class Mixin(ConcreteMixin, BrowserMixin):
            _force_full_reload = True

            async def check_rate_limit(self, page):
                return None

            async def configure_mode(self, page, mode):
                return "REGULAR"

        self.Mixin = Mixin

    async def test_force_full_reload_navigates_blank_first(self):
        """When _force_full_reload=True, first navigates to about:blank."""
        mixin = self.Mixin()

        async def _is_sign_in(p):
            return False
        mixin.is_sign_in_page = _is_sign_in

        async def _is_chat_ready(p):
            return True
        mixin.is_chat_ready = _is_chat_ready

        async def _dismiss(p):
            pass
        mixin.dismiss_popups = _dismiss

        goto_urls = []

        async def _goto(url, **kwargs):
            goto_urls.append(url)
        page = _make_page()
        page.goto = _goto

        await mixin._navigate_and_configure(page, "REGULAR")
        self.assertIn("about:blank", goto_urls)

    async def test_force_full_reload_blank_nav_exception_swallowed(self):
        """about:blank navigation exception is swallowed in _force_full_reload path."""
        mixin = self.Mixin()

        async def _is_sign_in(p):
            return False
        mixin.is_sign_in_page = _is_sign_in

        async def _is_chat_ready(p):
            return True
        mixin.is_chat_ready = _is_chat_ready

        async def _dismiss(p):
            pass
        mixin.dismiss_popups = _dismiss

        call_count = {"n": 0}

        async def _goto(url, **kwargs):
            call_count["n"] += 1
            if url == "about:blank":
                raise RuntimeError("blank nav failed")
        page = _make_page()
        page.goto = _goto

        # Should not raise
        result = await mixin._navigate_and_configure(page, "REGULAR")
        self.assertEqual(result, "REGULAR")


if __name__ == "__main__":
    unittest.main()
