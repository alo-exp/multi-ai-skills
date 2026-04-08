"""Unit tests for Gemini platform driver.

Tests cover check_rate_limit, configure_mode, inject_prompt, post_send,
completion_check, and extract_response — all branches to 100% coverage.
"""

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap — inject stubs before importing driver
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.parent
ENGINE_DIR = str(PROJECT_ROOT / "skills" / "orchestrator" / "engine")
PLATFORMS_DIR = str(PROJECT_ROOT / "skills" / "orchestrator" / "engine" / "platforms")

for _mod in ("playwright", "playwright.async_api", "browser_use", "anthropic"):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

# playwright.async_api needs Page attribute
_pw_async = sys.modules["playwright.async_api"]
if not hasattr(_pw_async, "Page"):
    _pw_async.Page = MagicMock

_mock_es = types.ModuleType("engine_setup")
_mock_es._load_dotenv = lambda: None
_mock_es._ensure_venv = lambda: None
_mock_es._ensure_dependencies = lambda: None
sys.modules["engine_setup"] = _mock_es

if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

# Import via the package so relative imports (.base, etc.) resolve correctly
import importlib
import importlib.util

# Ensure the platforms package is importable as "platforms"
_platforms_spec = importlib.util.spec_from_file_location(
    "platforms",
    str(PROJECT_ROOT / "skills" / "orchestrator" / "engine" / "platforms" / "__init__.py"),
    submodule_search_locations=[PLATFORMS_DIR],
)
if "platforms" not in sys.modules:
    _platforms_mod = importlib.util.module_from_spec(_platforms_spec)
    sys.modules["platforms"] = _platforms_mod
    # Don't exec the __init__ (it imports all platforms); just register the package
    _platforms_mod.__path__ = [PLATFORMS_DIR]
    _platforms_mod.__package__ = "platforms"

from platforms.gemini import Gemini  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(**kwargs):
    """Return a MagicMock page with sensible async defaults."""
    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.bring_to_front = AsyncMock()
    page.mouse = MagicMock()
    page.mouse.click = AsyncMock()
    page.url = "https://gemini.google.com/"

    # Default: page.evaluate returns 0 for body length
    page.evaluate = AsyncMock(return_value=kwargs.get("body_len", 0))

    # Default locator — count=0, not visible
    def _locator(sel):
        loc = MagicMock()
        loc.first = MagicMock()
        loc.first.count = AsyncMock(return_value=0)
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.first.inner_text = AsyncMock(return_value="")
        loc.first.get_attribute = AsyncMock(return_value=None)
        loc.first.click = AsyncMock()
        loc.first.scroll_into_view_if_needed = AsyncMock()
        loc.first.evaluate = AsyncMock(return_value=0)
        loc.count = AsyncMock(return_value=0)
        loc.nth = MagicMock(return_value=loc.first)
        loc.filter = MagicMock(return_value=loc)
        return loc

    page.locator = MagicMock(side_effect=_locator)

    def _get_by_text(text, **kw):
        return _locator(text)

    def _get_by_role(role, **kw):
        return _locator(role)

    page.get_by_text = MagicMock(side_effect=_get_by_text)
    page.get_by_role = MagicMock(side_effect=_get_by_role)

    for k, v in kwargs.items():
        if k != "body_len":
            setattr(page, k, v)

    return page


def _visible_locator(text="response text"):
    """Return a locator mock that is visible with content."""
    loc = MagicMock()
    loc.first = MagicMock()
    loc.first.count = AsyncMock(return_value=1)
    loc.first.is_visible = AsyncMock(return_value=True)
    loc.first.inner_text = AsyncMock(return_value=text)
    loc.first.click = AsyncMock()
    loc.first.scroll_into_view_if_needed = AsyncMock()
    loc.first.get_attribute = AsyncMock(return_value=None)
    loc.count = AsyncMock(return_value=1)
    loc.nth = MagicMock(return_value=loc.first)
    loc.filter = MagicMock(return_value=loc)
    return loc


# ---------------------------------------------------------------------------
# check_rate_limit
# ---------------------------------------------------------------------------


class TestGeminiCheckRateLimit:
    async def test_returns_none_when_no_patterns(self):
        page = _make_page()
        g = Gemini()
        result = await g.check_rate_limit(page)
        assert result is None

    async def test_returns_pattern_when_visible(self):
        page = _make_page()
        visible = _visible_locator()
        page.get_by_text = MagicMock(return_value=visible)
        g = Gemini()
        result = await g.check_rate_limit(page)
        assert result == "at full capacity"

    async def test_swallows_exception(self):
        page = _make_page()

        def boom(*a, **kw):
            raise RuntimeError("boom")

        page.get_by_text = MagicMock(side_effect=boom)
        g = Gemini()
        result = await g.check_rate_limit(page)
        assert result is None

    async def test_flash_downgrade_detected(self):
        page = _make_page()
        call_count = [0]
        n_patterns = 13  # number of patterns before flash check

        def get_by_text_side_effect(text, **kw):
            call_count[0] += 1
            loc = MagicMock()
            loc.first = MagicMock()
            if text == "switched to Flash":
                loc.first.count = AsyncMock(return_value=1)
                loc.first.is_visible = AsyncMock(return_value=True)
            else:
                loc.first.count = AsyncMock(return_value=0)
                loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_text = MagicMock(side_effect=get_by_text_side_effect)
        g = Gemini()
        result = await g.check_rate_limit(page)
        assert result == "Model downgraded to Flash (Pro quota exceeded)"

    async def test_flash_downgrade_exception_swallowed(self):
        """Exception in flash check is swallowed → returns None."""
        page = _make_page()
        call_count = [0]

        def get_by_text_side_effect(text, **kw):
            call_count[0] += 1
            if text == "switched to Flash":
                raise RuntimeError("flash error")
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_text = MagicMock(side_effect=get_by_text_side_effect)
        g = Gemini()
        result = await g.check_rate_limit(page)
        assert result is None


# ---------------------------------------------------------------------------
# configure_mode
# ---------------------------------------------------------------------------


class TestGeminiConfigureMode:
    async def test_default_mode_no_buttons_found(self):
        """No model btn found → returns 'Default'."""
        page = _make_page()
        g = Gemini()
        result = await g.configure_mode(page, "REGULAR")
        assert result == "Default"

    async def test_thinking_model_selected(self):
        """Model button found + Thinking option found → label includes Thinking."""
        page = _make_page()

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            # First selector ('button:has-text("Fast")') returns visible
            if "Fast" in str(sel) or "model" in str(sel):
                loc.first.count = AsyncMock(return_value=1)
                loc.first.is_visible = AsyncMock(return_value=True)
            else:
                loc.first.count = AsyncMock(return_value=0)
                loc.first.is_visible = AsyncMock(return_value=False)
            loc.first.click = AsyncMock()
            loc.count = AsyncMock(return_value=0)
            loc.filter = MagicMock(return_value=loc)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        page.wait_for_selector = AsyncMock()
        page.wait_for_timeout = AsyncMock()

        thinking_loc = MagicMock()
        thinking_loc.first = MagicMock()
        thinking_loc.first.count = AsyncMock(return_value=1)
        thinking_loc.first.click = AsyncMock()
        page.get_by_text = MagicMock(return_value=thinking_loc)

        g = Gemini()
        result = await g.configure_mode(page, "REGULAR")
        assert "Thinking" in result

    async def test_thinking_selection_exception_logged(self):
        """Exception during model selection is caught and logged."""
        page = _make_page()

        def _locator_boom(sel):
            raise RuntimeError("boom")

        page.locator = MagicMock(side_effect=_locator_boom)
        g = Gemini()
        result = await g.configure_mode(page, "REGULAR")
        assert result == "Default"

    async def test_wait_for_selector_exception_swallowed(self):
        """wait_for_selector timeout exception is swallowed."""
        page = _make_page()
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
        g = Gemini()
        result = await g.configure_mode(page, "REGULAR")
        assert result == "Default"

    async def test_deep_mode_direct_button(self):
        """DEEP mode: direct DR button found and clicked."""
        page = _make_page()

        call_counts = {"locator_call": 0}

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            # Make 'button:has-text("Deep research")' visible
            if "Deep research" in str(sel):
                loc.first.count = AsyncMock(return_value=1)
                loc.first.is_visible = AsyncMock(return_value=True)
            else:
                loc.first.count = AsyncMock(return_value=0)
                loc.first.is_visible = AsyncMock(return_value=False)
            loc.first.click = AsyncMock()
            loc.count = AsyncMock(return_value=0)
            loc.filter = MagicMock(return_value=loc)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        result = await g.configure_mode(page, "DEEP")
        assert "Deep Research" in result
        assert g._deep_mode is True

    async def test_deep_mode_tools_menu_aria_checked_true(self):
        """DEEP mode: Tools menu → DR item aria-checked=true (already enabled)."""
        page = _make_page()

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            loc.first.click = AsyncMock()
            loc.count = AsyncMock(return_value=0)
            loc.filter = MagicMock(return_value=loc)
            return loc

        # Tools button: found by filter
        tools_loc = MagicMock()
        tools_loc.first = MagicMock()
        tools_loc.first.count = AsyncMock(return_value=1)
        tools_loc.first.is_visible = AsyncMock(return_value=True)
        tools_loc.first.click = AsyncMock()
        tools_loc.count = AsyncMock(return_value=1)
        tools_loc.filter = MagicMock(return_value=tools_loc)

        # DR menu item
        dr_loc = MagicMock()
        dr_loc.first = MagicMock()
        dr_loc.first.count = AsyncMock(return_value=1)
        dr_loc.first.is_visible = AsyncMock(return_value=True)
        dr_loc.first.click = AsyncMock()
        dr_loc.first.get_attribute = AsyncMock(return_value="true")

        def _get_by_role(role, **kw):
            name = kw.get("name", "")
            if role == "menuitemcheckbox" and "Deep research" in str(name):
                return dr_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_role = MagicMock(side_effect=_get_by_role)

        def _locator(sel):
            # Make not([aria-label]) filter(has_text=Tools) return tools_loc
            if "not" in str(sel).lower() or "aria-label" in str(sel):
                lc = MagicMock()
                lc.first = MagicMock()
                lc.first.count = AsyncMock(return_value=1)
                lc.first.is_visible = AsyncMock(return_value=True)
                lc.first.click = AsyncMock()
                lc.count = AsyncMock(return_value=1)
                lf = MagicMock()
                lf.first = tools_loc.first
                lf.count = AsyncMock(return_value=1)
                lf.filter = MagicMock(return_value=lf)
                lc.filter = MagicMock(return_value=lf)
                return lc
            return _locator_default(sel)

        def _locator_default(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            loc.first.click = AsyncMock()
            loc.count = AsyncMock(return_value=0)
            loc.filter = MagicMock(return_value=loc)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        page.keyboard.press = AsyncMock()

        g = Gemini()
        result = await g.configure_mode(page, "DEEP")
        # aria-checked=true branch → deep research marked enabled
        assert g._deep_mode is True

    async def test_deep_mode_tools_menu_no_aria_checked(self):
        """DEEP mode: DR item found but no aria-checked attr → click anyway."""
        page = _make_page()

        dr_loc = MagicMock()
        dr_loc.first = MagicMock()
        dr_loc.first.count = AsyncMock(return_value=1)
        dr_loc.first.is_visible = AsyncMock(return_value=True)
        dr_loc.first.click = AsyncMock()
        # get_attribute raises to exercise the except branch
        dr_loc.first.get_attribute = AsyncMock(side_effect=Exception("no attr"))

        tools_loc = MagicMock()
        tools_loc.first = MagicMock()
        tools_loc.first.count = AsyncMock(return_value=1)
        tools_loc.first.is_visible = AsyncMock(return_value=True)
        tools_loc.first.click = AsyncMock()
        tools_loc.count = AsyncMock(return_value=1)

        def _get_by_role(role, **kw):
            name = kw.get("name", "")
            if role == "menuitemcheckbox" and "Deep research" in str(name):
                return dr_loc
            if role == "button" and str(name) == "Tools":
                return tools_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_role = MagicMock(side_effect=_get_by_role)

        def _locator(sel):
            lc = MagicMock()
            lc.first = MagicMock()
            lc.first.count = AsyncMock(return_value=1)
            lc.first.is_visible = AsyncMock(return_value=True)
            lc.first.click = AsyncMock()
            lc.count = AsyncMock(return_value=1)
            inner = MagicMock()
            inner.first = tools_loc.first
            inner.count = AsyncMock(return_value=1)
            inner.filter = MagicMock(return_value=inner)
            lc.filter = MagicMock(return_value=inner)
            return lc

        page.locator = MagicMock(side_effect=_locator)
        page.keyboard.press = AsyncMock()
        g = Gemini()
        result = await g.configure_mode(page, "DEEP")
        assert g._deep_mode is True

    async def test_deep_mode_tools_exception_logged(self):
        """DEEP mode: Tools menu entirely throws → warning logged, returns Default."""
        page = _make_page()

        def _locator(sel):
            raise RuntimeError("tools boom")

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        result = await g.configure_mode(page, "DEEP")
        assert result == "Default"


# ---------------------------------------------------------------------------
# inject_prompt
# ---------------------------------------------------------------------------


class TestGeminiInjectPrompt:
    async def test_inject_calls_exec_command(self):
        page = _make_page()
        g = Gemini()
        g._inject_exec_command = AsyncMock(return_value=100)
        await g.inject_prompt(page, "hello world")
        g._inject_exec_command.assert_called_once()

    async def test_truncation_warning_logged(self):
        page = _make_page()
        g = Gemini()
        # Return a length that is much shorter than prompt → triggers warning
        g._inject_exec_command = AsyncMock(return_value=5)
        with patch("platforms.gemini.log") as mock_log:
            await g.inject_prompt(page, "x" * 100)
            assert mock_log.warning.called


# ---------------------------------------------------------------------------
# post_send
# ---------------------------------------------------------------------------


class TestGeminiPostSend:
    async def test_regular_mode_noop(self):
        """REGULAR mode: post_send returns immediately."""
        page = _make_page()
        g = Gemini()
        await g.post_send(page, "REGULAR")
        page.bring_to_front.assert_not_called()

    async def test_deep_start_research_clicked(self):
        """DEEP mode: Start research button found and clicked."""
        page = _make_page()

        start_loc = MagicMock()
        start_loc.first = MagicMock()
        start_loc.first.count = AsyncMock(return_value=1)
        start_loc.first.is_visible = AsyncMock(return_value=True)
        start_loc.first.scroll_into_view_if_needed = AsyncMock()
        start_loc.first.click = AsyncMock()

        def _get_by_role(role, **kw):
            if role == "button" and "Start research" in str(kw.get("name", "")):
                return start_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_role = MagicMock(side_effect=_get_by_role)

        # Stop button visible after click
        stop_loc = MagicMock()
        stop_loc.first = MagicMock()
        stop_loc.first.count = AsyncMock(return_value=1)

        def _locator(sel):
            if "Stop" in str(sel):
                return stop_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)

        g = Gemini()
        await g.post_send(page, "DEEP")
        start_loc.first.click.assert_called()

    async def test_deep_no_start_btn_auto_start(self):
        """DEEP mode: No plan appeared but stop/cancel already visible → auto-start."""
        page = _make_page()
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))

        stop_loc = MagicMock()
        stop_loc.first = MagicMock()
        stop_loc.first.count = AsyncMock(return_value=1)

        def _locator(sel):
            if "Stop" in str(sel):
                return stop_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)

        g = Gemini()
        await g.post_send(page, "DEEP")  # Should not raise

    async def test_deep_capacity_error_raised(self):
        """DEEP mode: 'at full capacity' found → RuntimeError raised."""
        page = _make_page()
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))

        capacity_loc = MagicMock()
        capacity_loc.first = MagicMock()
        capacity_loc.first.count = AsyncMock(return_value=1)
        capacity_loc.first.is_visible = AsyncMock(return_value=True)

        def _get_by_text(text, **kw):
            if "at full capacity" in str(text):
                return capacity_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_text = MagicMock(side_effect=_get_by_text)

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)

        g = Gemini()
        with pytest.raises(RuntimeError, match="at full capacity"):
            await g.post_send(page, "DEEP")

    async def test_deep_no_start_no_stop_no_capacity_warning(self):
        """DEEP mode: nothing found → warning logged but no exception."""
        page = _make_page()
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)

        g = Gemini()
        await g.post_send(page, "DEEP")  # Should not raise

    async def test_deep_start_btn_click_exception(self):
        """DEEP mode: Start research click raises → warning logged."""
        page = _make_page()

        start_loc = MagicMock()
        start_loc.first = MagicMock()
        start_loc.first.count = AsyncMock(return_value=1)
        start_loc.first.is_visible = AsyncMock(return_value=True)
        start_loc.first.scroll_into_view_if_needed = AsyncMock()
        start_loc.first.click = AsyncMock(side_effect=Exception("click failed"))

        def _get_by_role(role, **kw):
            if role == "button":
                return start_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        page.get_by_role = MagicMock(side_effect=_get_by_role)

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)

        g = Gemini()
        await g.post_send(page, "DEEP")  # Exception swallowed


# ---------------------------------------------------------------------------
# completion_check
# ---------------------------------------------------------------------------


class TestGeminiCompletionCheck:
    async def test_stop_button_visible_returns_false(self):
        page = _make_page()

        stop_loc = MagicMock()
        stop_loc.first = MagicMock()
        stop_loc.first.count = AsyncMock(return_value=1)
        stop_loc.first.is_visible = AsyncMock(return_value=True)

        def _locator(sel):
            if "Stop" in str(sel) or "Cancel" in str(sel):
                return stop_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        result = await g.completion_check(page)
        assert result is False
        assert g._no_stop_polls == 0

    async def test_thinking_indicator_visible_returns_false(self):
        """Progress indicator (Thinking/Searching) visible → still running."""
        page = _make_page()

        thinking_loc = MagicMock()
        thinking_loc.first = MagicMock()
        thinking_loc.first.count = AsyncMock(return_value=1)
        thinking_loc.first.is_visible = AsyncMock(return_value=True)

        call_num = [0]

        def _locator(sel):
            call_num[0] += 1
            # First calls are for Stop/Cancel
            if "Stop" in str(sel) or "Cancel" in str(sel):
                loc = MagicMock()
                loc.first = MagicMock()
                loc.first.count = AsyncMock(return_value=0)
                loc.first.is_visible = AsyncMock(return_value=False)
                return loc
            # Progress indicator selector
            if "Thinking" in str(sel) or "Searching" in str(sel) or "progress" in str(sel):
                return thinking_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        page.evaluate = AsyncMock(return_value=0)
        g = Gemini()
        result = await g.completion_check(page)
        assert result is False

    async def test_scoped_copy_button_returns_true(self):
        """Scoped copy button found + body > 3000 → complete."""
        page = _make_page(body_len=5000)
        page.evaluate = AsyncMock(return_value=5000)

        copy_loc = MagicMock()
        copy_loc.first = MagicMock()
        copy_loc.first.count = AsyncMock(return_value=1)
        copy_loc.first.is_visible = AsyncMock(return_value=True)

        def _locator(sel):
            # Stop/Cancel must return empty so has_stop stays False
            if sel in ('button:has-text("Stop")', 'button[aria-label*="Stop"]',
                       'button:has-text("Cancel")', 'button[aria-label*="Cancel"]'):
                loc = MagicMock()
                loc.first = MagicMock()
                loc.first.count = AsyncMock(return_value=0)
                loc.first.is_visible = AsyncMock(return_value=False)
                return loc
            # Progress indicator must also return empty
            if "Thinking" in str(sel) or "Searching" in str(sel) or "progress" in str(sel):
                loc = MagicMock()
                loc.first = MagicMock()
                loc.first.count = AsyncMock(return_value=0)
                loc.first.is_visible = AsyncMock(return_value=False)
                return loc
            # Copy/Share/model-response → return visible copy button
            return copy_loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        g._seen_stop = False
        result = await g.completion_check(page)
        assert result is True

    async def test_body_threshold_non_dr(self):
        """Body > 15000 + _seen_stop → complete for non-DR mode."""
        page = _make_page()
        page.evaluate = AsyncMock(return_value=20000)

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        g._seen_stop = True
        g._deep_mode = False
        result = await g.completion_check(page)
        assert result is True

    async def test_stable_threshold_non_dr(self):
        """3 polls without stop → complete for non-DR mode."""
        page = _make_page()
        page.evaluate = AsyncMock(return_value=0)

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        g._seen_stop = True
        g._no_stop_polls = 3
        g._deep_mode = False
        result = await g.completion_check(page)
        assert result is True

    async def test_quick_response_fallback(self):
        """No DR indicators, body > 5000, 6 stable polls → quick response complete."""
        page = _make_page()
        page.evaluate = AsyncMock(return_value=6000)

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        g._seen_stop = False
        g._no_stop_polls = 6
        g._dr_start_unconfirmed = False
        result = await g.completion_check(page)
        assert result is True

    async def test_quick_response_suppressed_when_unconfirmed(self):
        """_dr_start_unconfirmed=True suppresses quick fallback."""
        page = _make_page()
        page.evaluate = AsyncMock(return_value=6000)

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        g._seen_stop = False
        g._no_stop_polls = 6
        g._dr_start_unconfirmed = True
        result = await g.completion_check(page)
        assert result is False  # suppressed

    async def test_no_stop_limit_extended_fallback(self):
        """40+ polls without stop in non-DR mode → extended fallback complete."""
        page = _make_page()
        page.evaluate = AsyncMock(return_value=0)

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        g._seen_stop = False
        g._no_stop_polls = 40
        g._deep_mode = False
        result = await g.completion_check(page)
        assert result is True

    async def test_dr_start_unconfirmed_bring_to_front(self):
        """bring_to_front called at specific poll counts when _dr_start_unconfirmed."""
        page = _make_page()
        page.evaluate = AsyncMock(return_value=6000)

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        g._seen_stop = False
        # _no_stop_polls is incremented before the check, so set to 11 so it becomes 12
        g._no_stop_polls = 11
        g._dr_start_unconfirmed = True
        result = await g.completion_check(page)
        page.bring_to_front.assert_called()


# ---------------------------------------------------------------------------
# extract_response
# ---------------------------------------------------------------------------


class TestGeminiExtractResponse:
    async def test_primary_container_extraction(self):
        """Response container with > 500 chars returned directly."""
        page = _make_page()

        text = "x" * 600
        container_loc = MagicMock()
        container_loc.count = AsyncMock(return_value=1)
        last_item = MagicMock()
        last_item.inner_text = AsyncMock(return_value=text)
        container_loc.nth = MagicMock(return_value=last_item)

        page.locator = MagicMock(return_value=container_loc)
        g = Gemini()
        result = await g.extract_response(page)
        assert result == text

    async def test_primary_container_short_falls_through(self):
        """Container found but text < 500 chars → falls to secondary."""
        page = _make_page()

        container_loc = MagicMock()
        container_loc.count = AsyncMock(return_value=1)
        last_item = MagicMock()
        last_item.inner_text = AsyncMock(return_value="short")
        container_loc.nth = MagicMock(return_value=last_item)

        page.locator = MagicMock(return_value=container_loc)

        body = "## Report\n" + "content " * 700
        page.evaluate = AsyncMock(return_value=body)

        g = Gemini()
        g.prompt_sigs = []
        result = await g.extract_response(page)
        assert len(result) > 500

    async def test_container_exception_falls_to_body(self):
        """Exception in container extraction → body fallback."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("locator error"))

        body = "# heading\n" + "content " * 700
        page.evaluate = AsyncMock(return_value=body)

        g = Gemini()
        g.prompt_sigs = []
        result = await g.extract_response(page)
        assert len(result) > 200

    async def test_full_body_no_marker(self):
        """Body > 3000 but no markers → returns full body."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("err"))

        body = "plain content without headings " * 200
        page.evaluate = AsyncMock(return_value=body)

        g = Gemini()
        g.prompt_sigs = []
        result = await g.extract_response(page)
        assert len(result) > 200

    async def test_tertiary_main_container(self):
        """Primary and secondary fail → tertiary main container."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("err"))

        call_count = [0]

        async def _eval(script):
            call_count[0] += 1
            if call_count[0] == 1:
                return ""  # body.innerText short → skip secondary
            return "main content " * 20  # tertiary returns content

        page.evaluate = AsyncMock(side_effect=_eval)
        g = Gemini()
        g.prompt_sigs = []
        result = await g.extract_response(page)
        assert "main content" in result

    async def test_all_fail_returns_empty(self):
        """All extraction methods raise → returns empty string."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("err"))
        page.evaluate = AsyncMock(side_effect=Exception("eval error"))
        g = Gemini()
        g.prompt_sigs = []
        result = await g.extract_response(page)
        assert result == ""

    async def test_body_marker_is_prompt_echo_skipped(self):
        """Body marker candidate is prompt echo → skipped, full body returned if not echo."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("err"))

        body = "# Intro\n" + "prompt sig text " * 50 + "\n# Real Section\n" + "real content " * 50
        page.evaluate = AsyncMock(return_value=body)

        g = Gemini()
        # Make the first candidate match prompt echo, second does not
        g.prompt_sigs = ["prompt sig text"]
        result = await g.extract_response(page)
        assert len(result) > 200

    async def test_full_body_is_prompt_echo_warning(self):
        """Full body is prompt echo → warning logged, skip."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("err"))

        body = "# Section\nprompt echo content " * 100
        # All sections are prompt echoes → full body also prompt echo
        page.evaluate = AsyncMock(return_value=body)

        g = Gemini()
        g.prompt_sigs = ["prompt echo content"]  # matches everything → prompt echo

        with patch("platforms.gemini.log") as mock_log:
            # Main container fallback
            result = await g.extract_response(page)
        # Should fall through to tertiary; we just verify it doesn't crash
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Additional coverage tests for exception handlers and edge branches
# ---------------------------------------------------------------------------


class TestGeminiConfigureModeEdgeCases:
    async def test_tools_btn_found_dr_item_not_visible(self):
        """DR menu item found but not visible → warning logged."""
        page = _make_page()

        # Tools button visible via first locator
        tools_loc = MagicMock()
        tools_loc.first = MagicMock()
        tools_loc.first.count = AsyncMock(return_value=1)
        tools_loc.first.is_visible = AsyncMock(return_value=True)
        tools_loc.first.click = AsyncMock()
        tools_loc.count = AsyncMock(return_value=1)

        # DR item not visible
        dr_loc = MagicMock()
        dr_loc.first = MagicMock()
        dr_loc.first.count = AsyncMock(return_value=1)
        dr_loc.first.is_visible = AsyncMock(return_value=False)
        dr_loc.count = AsyncMock(return_value=0)  # initial count=0 triggers fallbacks
        dr_loc.filter = MagicMock(return_value=dr_loc)

        def _get_by_role(role, **kw):
            if role == "menuitemcheckbox":
                return dr_loc
            if role == "button":
                return tools_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_role = MagicMock(side_effect=_get_by_role)

        def _locator(sel):
            inner = MagicMock()
            inner.first = tools_loc.first
            inner.count = AsyncMock(return_value=1)
            inner.filter = MagicMock(return_value=inner)
            lc = MagicMock()
            lc.first = MagicMock()
            lc.first.count = AsyncMock(return_value=1)
            lc.first.is_visible = AsyncMock(return_value=True)
            lc.count = AsyncMock(return_value=1)
            lc.filter = MagicMock(return_value=inner)
            # For DR selectors, return dr_loc
            if "menu" in str(sel) or "Deep research" in str(sel) or "option" in str(sel):
                return dr_loc
            return lc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        result = await g.configure_mode(page, "DEEP")
        # DR not visible → warning, deep_mode stays False
        assert g._deep_mode is False

    async def test_tools_btn_not_found_warning(self):
        """Tools button has count=0 everywhere → warning 'not found'."""
        page = _make_page()

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            loc.count = AsyncMock(return_value=0)
            loc.filter = MagicMock(return_value=loc)
            return loc

        def _get_by_role(role, **kw):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        def _get_by_text(text, **kw):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        page.get_by_role = MagicMock(side_effect=_get_by_role)
        page.get_by_text = MagicMock(side_effect=_get_by_text)

        g = Gemini()
        result = await g.configure_mode(page, "DEEP")
        assert g._deep_mode is False

    async def test_escape_exception_swallowed(self):
        """keyboard.press(Escape) raises → exception swallowed, dr_enabled remains True."""
        page = _make_page()
        page.keyboard.press = AsyncMock(side_effect=Exception("kbd error"))

        # Direct DR button visible
        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            if "Deep research" in str(sel):
                loc.first.count = AsyncMock(return_value=1)
                loc.first.is_visible = AsyncMock(return_value=True)
            else:
                loc.first.count = AsyncMock(return_value=0)
                loc.first.is_visible = AsyncMock(return_value=False)
            loc.first.click = AsyncMock()
            loc.count = AsyncMock(return_value=0)
            loc.filter = MagicMock(return_value=loc)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        result = await g.configure_mode(page, "DEEP")
        # Should complete without raising
        assert g._deep_mode is True


class TestGeminiPostSendEdgeCases:
    async def test_bring_to_front_exception_swallowed(self):
        """bring_to_front raises → swallowed, execution continues."""
        page = _make_page()
        page.bring_to_front = AsyncMock(side_effect=Exception("focus error"))

        # wait_for_selector times out, no start button, no stop button
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        await g.post_send(page, "DEEP")  # Should not raise

    async def test_start_btn_last_resort_fallback(self):
        """get_by_role returns empty for start texts → research-plan last-resort."""
        page = _make_page()

        plan_btn = MagicMock()
        plan_btn.count = AsyncMock(return_value=1)
        plan_btn.is_visible = AsyncMock(return_value=True)
        plan_btn.scroll_into_view_if_needed = AsyncMock()
        plan_btn.click = AsyncMock()

        stop_loc = MagicMock()
        stop_loc.first = MagicMock()
        stop_loc.first.count = AsyncMock(return_value=0)

        def _locator(sel):
            if "research-plan" in str(sel) or "plan" in str(sel):
                return plan_btn
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)

        def _get_by_role(role, **kw):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_role = MagicMock(side_effect=_get_by_role)
        g = Gemini()
        await g.post_send(page, "DEEP")

    async def test_capacity_check_generic_exception_swallowed(self):
        """Generic exception in capacity check → swallowed (not re-raised)."""
        page = _make_page()
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))

        def _get_by_text(text, **kw):
            if "at full capacity" in str(text):
                raise Exception("unexpected error")  # non-RuntimeError
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_text = MagicMock(side_effect=_get_by_text)

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        await g.post_send(page, "DEEP")  # Should not raise


class TestGeminiCompletionCheckEdgeCases:
    async def test_stop_locator_exception_swallowed(self):
        """locator() for Stop raises → exception swallowed, has_stop stays False."""
        page = _make_page()
        page.evaluate = AsyncMock(return_value=0)

        def _locator(sel):
            raise Exception("locator error")

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        g._seen_stop = False
        g._no_stop_polls = 0
        result = await g.completion_check(page)
        # No stop → _no_stop_polls incremented, no threshold → False
        assert result is False

    async def test_thinking_locator_exception_swallowed(self):
        """locator() for thinking indicator raises → swallowed."""
        page = _make_page()
        page.evaluate = AsyncMock(return_value=0)

        call_num = [0]

        def _locator(sel):
            call_num[0] += 1
            if call_num[0] <= 4:  # Stop/Cancel selectors
                loc = MagicMock()
                loc.first = MagicMock()
                loc.first.count = AsyncMock(return_value=0)
                loc.first.is_visible = AsyncMock(return_value=False)
                return loc
            raise Exception("thinking locator error")

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        g._seen_stop = False
        result = await g.completion_check(page)
        assert result is False

    async def test_evaluate_exception_sets_body_len_zero(self):
        """page.evaluate raises → body_len_check = 0, no copy button check."""
        page = _make_page()
        page.evaluate = AsyncMock(side_effect=Exception("eval err"))

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        g._seen_stop = False
        g._no_stop_polls = 0
        result = await g.completion_check(page)
        assert result is False

    async def test_copy_button_locator_exception_swallowed(self):
        """Exception in scoped copy button locator → swallowed."""
        page = _make_page()
        page.evaluate = AsyncMock(return_value=5000)

        call_num = [0]

        def _locator(sel):
            call_num[0] += 1
            if call_num[0] <= 4:  # Stop/Cancel
                loc = MagicMock()
                loc.first = MagicMock()
                loc.first.count = AsyncMock(return_value=0)
                loc.first.is_visible = AsyncMock(return_value=False)
                return loc
            if "progress" in str(sel) or "Thinking" in str(sel):
                loc = MagicMock()
                loc.first = MagicMock()
                loc.first.count = AsyncMock(return_value=0)
                loc.first.is_visible = AsyncMock(return_value=False)
                return loc
            # Copy button locators raise
            raise Exception("copy locator error")

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        g._seen_stop = False
        g._no_stop_polls = 0
        result = await g.completion_check(page)
        # No copy button → no other threshold met → False
        assert result is False

    async def test_bring_to_front_exception_in_completion_check(self):
        """bring_to_front raises inside _dr_start_unconfirmed path → swallowed."""
        page = _make_page()
        page.evaluate = AsyncMock(return_value=6000)
        page.bring_to_front = AsyncMock(side_effect=Exception("focus error"))

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Gemini()
        g._seen_stop = False
        g._no_stop_polls = 5  # → becomes 6 after increment
        g._dr_start_unconfirmed = True
        result = await g.completion_check(page)
        # Exception swallowed, suppression still active → False
        assert result is False


# ---------------------------------------------------------------------------
# Additional coverage: DR locator fallback chain + aria-checked + body checks
# ---------------------------------------------------------------------------


class TestGeminiDRLocatorFallbacks:
    """Cover lines 162, 165, 169-190, 404-405, 501-502, 511."""

    def _make_dr_loc(self, count_val, visible=True, attr_val="false"):
        """Helper: make a DR locator stub."""
        loc = MagicMock()
        loc.count = AsyncMock(return_value=count_val)
        loc.is_visible = AsyncMock(return_value=visible)
        loc.get_attribute = AsyncMock(return_value=attr_val)
        loc.click = AsyncMock()
        loc.filter = MagicMock(return_value=loc)
        loc.first = loc  # .first returns self so count() still works
        return loc

    async def test_dr_second_locator_fallback_aria_checked_true(self):
        """menuitemcheckbox count=0, [role=menu] button count>0, aria-checked=true → skip click (line 162, 169-175)."""
        page = _make_page()

        # tools button visible
        tools_loc = MagicMock()
        tools_loc.first = MagicMock()
        tools_loc.first.count = AsyncMock(return_value=1)
        tools_loc.first.is_visible = AsyncMock(return_value=True)
        tools_loc.first.click = AsyncMock()

        # menuitemcheckbox count=0 → triggers line 162
        dr_mnu = self._make_dr_loc(count_val=0)
        # [role=menu] button fallback count=1, visible, aria-checked=true → lines 162, 170-175
        dr_fallback1 = self._make_dr_loc(count_val=1, visible=True, attr_val="true")

        def _locator(sel):
            if '[role="menu"]' in str(sel):
                return dr_fallback1
            if "option" in str(sel) or "menuitem" in str(sel):
                return dr_mnu
            loc = MagicMock()
            loc.first = MagicMock()
            # count=0 so model/direct-DR buttons are skipped; click not reached
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            loc.first.click = AsyncMock()
            loc.count = AsyncMock(return_value=0)
            loc.filter = MagicMock(return_value=loc)
            return loc

        def _get_by_role(role, **kw):
            if role == "menuitemcheckbox":
                return dr_mnu
            if role == "button":
                return tools_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.click = AsyncMock()
            return loc

        page.locator = MagicMock(side_effect=_locator)
        page.get_by_role = MagicMock(side_effect=_get_by_role)
        page.keyboard.press = AsyncMock()

        g = Gemini()
        await g.configure_mode(page, "DEEP")
        # aria-checked=true → deep_mode should be True (already enabled)
        assert g._deep_mode is True
        # click should NOT have been called (already enabled)
        dr_fallback1.click.assert_not_called()

    async def test_dr_third_locator_fallback_aria_checked_false(self):
        """menuitemcheckbox=0, [role=menu]=0, [role=menuitem/option]=1, aria-checked=false → click (lines 162, 165, 176-182)."""
        page = _make_page()

        tools_loc = MagicMock()
        tools_loc.first = MagicMock()
        tools_loc.first.count = AsyncMock(return_value=1)
        tools_loc.first.is_visible = AsyncMock(return_value=True)
        tools_loc.first.click = AsyncMock()

        # menuitemcheckbox count=0
        dr_zero = self._make_dr_loc(count_val=0)
        # [role=menu] button count=0
        dr_menu_zero = self._make_dr_loc(count_val=0)
        # [role=menuitem, option] count=1, aria-checked=false → click (lines 165, 176-182)
        dr_option = self._make_dr_loc(count_val=1, visible=True, attr_val="false")

        def _locator(sel):
            if '[role="menu"]' in str(sel) and "option" not in str(sel):
                return dr_menu_zero
            if "option" in str(sel) or "menuitem" in str(sel):
                return dr_option
            # All other locators: count=0 so model/direct-DR buttons not triggered
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            loc.first.click = AsyncMock()
            loc.count = AsyncMock(return_value=0)
            loc.filter = MagicMock(return_value=loc)
            return loc

        def _get_by_role(role, **kw):
            if role == "menuitemcheckbox":
                return dr_zero
            if role == "button":
                return tools_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.click = AsyncMock()
            return loc

        page.locator = MagicMock(side_effect=_locator)
        page.get_by_role = MagicMock(side_effect=_get_by_role)
        page.keyboard.press = AsyncMock()

        g = Gemini()
        await g.configure_mode(page, "DEEP")
        assert g._deep_mode is True
        dr_option.click.assert_called_once()

    async def test_dr_get_attribute_exception_clicks_anyway(self):
        """get_attribute raises → except block: click anyway (lines 183-190)."""
        page = _make_page()

        tools_loc = MagicMock()
        tools_loc.first = MagicMock()
        tools_loc.first.count = AsyncMock(return_value=1)
        tools_loc.first.is_visible = AsyncMock(return_value=True)
        tools_loc.first.click = AsyncMock()

        # DR item found, visible, but get_attribute raises
        dr_exc = MagicMock()
        dr_exc.count = AsyncMock(return_value=1)
        dr_exc.is_visible = AsyncMock(return_value=True)
        dr_exc.get_attribute = AsyncMock(side_effect=Exception("attr error"))
        dr_exc.click = AsyncMock()
        dr_exc.filter = MagicMock(return_value=dr_exc)
        dr_exc.first = dr_exc

        def _get_by_role(role, **kw):
            if role == "menuitemcheckbox":
                return dr_exc
            if role == "button":
                return tools_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.count = AsyncMock(return_value=0)
            loc.filter = MagicMock(return_value=loc)
            return loc

        page.get_by_role = MagicMock(side_effect=_get_by_role)
        page.locator = MagicMock(side_effect=_locator)
        page.keyboard.press = AsyncMock()

        g = Gemini()
        await g.configure_mode(page, "DEEP")
        # Exception path → still clicked
        assert g._deep_mode is True
        dr_exc.click.assert_called_once()

    async def test_body_threshold_exception_swallowed(self):
        """Exception inside threshold block → except: pass (lines 404-405).

        Achieved by patching log.info to raise inside the try block when the
        body threshold condition is met (body_len_check > threshold and _seen_stop).
        The exception is caught at lines 404-405 and execution continues.
        """
        page = _make_page()

        # evaluate returns large int so body_len_check > threshold (50000) is True
        page.evaluate = AsyncMock(return_value=60000)

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)

        g = Gemini()
        g._seen_stop = True
        g._deep_mode = True
        g._no_stop_polls = 0

        log_calls = [0]

        def _log_info_raise(msg, *a, **kw):
            log_calls[0] += 1
            # Raise on the body-threshold log call (contains "Body text")
            if "Body text" in str(msg):
                raise RuntimeError("log boom to cover except block")

        with patch("platforms.gemini.log") as mock_log:
            mock_log.info.side_effect = _log_info_raise
            # Exception from log.info inside try at 399 is caught at 404-405
            result = await g.completion_check(page)

        assert result is False  # exception swallowed, no other path returns True

    async def test_extract_marker_candidate_is_prompt_echo_skipped(self):
        """Marker candidate is prompt echo → skipped (lines 501-502); next candidate used."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("no container"))

        # Body has two '#' markers: first candidate = prompt echo, second = real content.
        # Body must be > 3000 chars to enter the marker scan block.
        sig = "prompt echo sig"
        real = "real answer content " * 100
        body = f"# Intro\n{sig * 200}\n# Answer\n{real}"

        page.evaluate = AsyncMock(return_value=body)

        g = Gemini()
        g.prompt_sigs = [sig]

        with patch("platforms.gemini.log"):
            result = await g.extract_response(page)
        # Second candidate is NOT prompt echo → returned
        assert "real answer content" in result

    async def test_extract_full_body_is_prompt_echo_warning_logged(self):
        """No clean marker, full body is prompt echo → warning at line 511."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("no container"))

        sig = "prompt echo sig"
        # All sections are prompt echoes; full body also matches.
        # Body must be > 3000 chars to enter the marker scan block.
        body = f"# Section\n{sig * 200}\n# Section2\n{sig * 200}"
        page.evaluate = AsyncMock(return_value=body)

        g = Gemini()
        g.prompt_sigs = [sig]

        with patch("platforms.gemini.log") as mock_log:
            result = await g.extract_response(page)

        # Warning should have been logged at line 511
        warning_calls = [str(c) for c in mock_log.warning.call_args_list]
        assert any("prompt echo" in w for w in warning_calls)
