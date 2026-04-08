"""Unit tests for Grok platform driver."""

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap
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

# Register platforms as a package so relative imports (.base, etc.) resolve
if "platforms" not in sys.modules:
    _platforms_mod = types.ModuleType("platforms")
    _platforms_mod.__path__ = [PLATFORMS_DIR]
    _platforms_mod.__package__ = "platforms"
    sys.modules["platforms"] = _platforms_mod

from platforms.grok import Grok  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page():
    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.evaluate = AsyncMock(return_value="body text")
    page.url = "https://x.ai/grok"

    def _locator(sel):
        loc = MagicMock()
        loc.first = MagicMock()
        loc.first.count = AsyncMock(return_value=0)
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.first.inner_text = AsyncMock(return_value="")
        loc.first.click = AsyncMock()
        loc.first.evaluate = AsyncMock(return_value=0)
        loc.count = AsyncMock(return_value=0)
        loc.nth = MagicMock(return_value=loc.first)
        loc.filter = MagicMock(return_value=loc)
        return loc

    page.locator = MagicMock(side_effect=_locator)

    def _get_by_text(text, **kw):
        return _locator(text)

    page.get_by_text = MagicMock(side_effect=_get_by_text)
    return page


def _visible_locator(inner_text="response"):
    loc = MagicMock()
    loc.first = MagicMock()
    loc.first.count = AsyncMock(return_value=1)
    loc.first.is_visible = AsyncMock(return_value=True)
    loc.first.inner_text = AsyncMock(return_value=inner_text)
    loc.first.click = AsyncMock()
    loc.count = AsyncMock(return_value=1)
    loc.nth = MagicMock(return_value=loc.first)
    loc.filter = MagicMock(return_value=loc)
    return loc


# ---------------------------------------------------------------------------
# check_rate_limit
# ---------------------------------------------------------------------------


class TestGrokCheckRateLimit:
    async def test_no_limit_returns_none(self):
        page = _make_page()
        g = Grok()
        assert await g.check_rate_limit(page) is None

    async def test_visible_pattern_returned(self):
        page = _make_page()
        page.get_by_text = MagicMock(return_value=_visible_locator())
        g = Grok()
        result = await g.check_rate_limit(page)
        assert result == "Message limit reached"

    async def test_exception_swallowed(self):
        page = _make_page()
        page.get_by_text = MagicMock(side_effect=RuntimeError("boom"))
        g = Grok()
        assert await g.check_rate_limit(page) is None


# ---------------------------------------------------------------------------
# configure_mode
# ---------------------------------------------------------------------------


class TestGrokConfigureMode:
    async def test_deepthink_enabled_via_text(self):
        page = _make_page()
        dt_loc = _visible_locator()
        page.get_by_text = MagicMock(return_value=dt_loc)
        g = Grok()
        result = await g.configure_mode(page, "DEEP")
        assert result == "DeepThink + Search"

    async def test_deepthink_via_aria_label(self):
        """DeepThink text not found → tries aria-label button."""
        page = _make_page()

        aria_loc = MagicMock()
        aria_loc.first = MagicMock()
        aria_loc.first.count = AsyncMock(return_value=1)
        aria_loc.first.click = AsyncMock()

        call_num = [0]

        def _get_by_text_side(text, **kw):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        def _locator(sel):
            if "DeepThink" in str(sel) or "Think" in str(sel):
                return aria_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_text = MagicMock(side_effect=_get_by_text_side)
        page.locator = MagicMock(side_effect=_locator)
        g = Grok()
        result = await g.configure_mode(page, "DEEP")
        assert result == "DeepThink + Search"

    async def test_deepthink_exception_logged(self):
        page = _make_page()
        page.get_by_text = MagicMock(side_effect=Exception("boom"))
        g = Grok()
        result = await g.configure_mode(page, "DEEP")
        assert result == "DeepThink + Search"

    async def test_search_via_aria_label(self):
        """Search text not found → tries aria-label button."""
        page = _make_page()

        dt_loc = _visible_locator()  # DeepThink found
        search_aria = MagicMock()
        search_aria.first = MagicMock()
        search_aria.first.count = AsyncMock(return_value=1)
        search_aria.first.click = AsyncMock()

        call_texts = []

        def _get_by_text(text, **kw):
            call_texts.append(text)
            if text == "DeepThink":
                return dt_loc
            # Search: not visible
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        def _locator(sel):
            if "Search" in str(sel) or "search" in str(sel):
                return search_aria
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        page.get_by_text = MagicMock(side_effect=_get_by_text)
        page.locator = MagicMock(side_effect=_locator)
        g = Grok()
        result = await g.configure_mode(page, "DEEP")
        assert result == "DeepThink + Search"

    async def test_search_exception_logged(self):
        page = _make_page()
        # DeepThink OK, Search raises
        dt_loc = _visible_locator()

        def _get_by_text(text, **kw):
            if text == "DeepThink":
                return dt_loc
            raise Exception("search boom")

        page.get_by_text = MagicMock(side_effect=_get_by_text)
        g = Grok()
        result = await g.configure_mode(page, "DEEP")
        assert result == "DeepThink + Search"


# ---------------------------------------------------------------------------
# inject_prompt
# ---------------------------------------------------------------------------


class TestGrokInjectPrompt:
    async def test_contenteditable_uses_exec_command(self):
        page = _make_page()
        ce_loc = _visible_locator()
        page.locator = MagicMock(return_value=ce_loc)
        g = Grok()
        g._inject_exec_command = AsyncMock(return_value=50)
        await g.inject_prompt(page, "test prompt")
        g._inject_exec_command.assert_called_once()

    async def test_textarea_fallback(self):
        """No contenteditable → textarea fallback."""
        page = _make_page()

        call_num = [0]

        def _locator(sel):
            call_num[0] += 1
            loc = MagicMock()
            loc.first = MagicMock()
            if "contenteditable" in str(sel):
                loc.first.count = AsyncMock(return_value=0)
                loc.first.is_visible = AsyncMock(return_value=False)
            elif "textarea" in str(sel):
                loc.first.count = AsyncMock(return_value=1)
                loc.first.is_visible = AsyncMock(return_value=True)
                loc.first.click = AsyncMock()
                loc.first.type = AsyncMock()
            else:
                loc.first.count = AsyncMock(return_value=0)
                loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Grok()
        g._inject_exec_command = AsyncMock(return_value=50)
        await g.inject_prompt(page, "hello")

    async def test_no_input_raises(self):
        page = _make_page()
        # All locators return empty
        g = Grok()
        with pytest.raises(RuntimeError, match="No visible input element"):
            await g.inject_prompt(page, "prompt")


# ---------------------------------------------------------------------------
# completion_check
# ---------------------------------------------------------------------------


class TestGrokCompletionCheck:
    async def test_stop_visible_returns_false(self):
        page = _make_page()
        stop_loc = _visible_locator()

        def _locator(sel):
            if "Stop" in str(sel):
                return stop_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Grok()
        assert await g.completion_check(page) is False
        assert g._no_stop_polls == 0

    async def test_message_count_and_content(self):
        """2+ messages with last > 200 chars → complete."""
        page = _make_page()

        msg_loc = MagicMock()
        msg_loc.count = AsyncMock(return_value=2)
        last_msg = MagicMock()
        last_msg.evaluate = AsyncMock(return_value=300)
        msg_loc.nth = MagicMock(return_value=last_msg)

        def _locator(sel):
            if "message" in str(sel):
                return msg_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Grok()
        assert await g.completion_check(page) is True

    async def test_stable_state_3_polls(self):
        page = _make_page()

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            loc.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Grok()
        g._no_stop_polls = 3
        assert await g.completion_check(page) is True

    async def test_message_eval_exception_falls_through(self):
        """Message content eval fails → falls to stable-state check."""
        page = _make_page()

        msg_loc = MagicMock()
        msg_loc.count = AsyncMock(return_value=2)
        last_msg = MagicMock()
        last_msg.evaluate = AsyncMock(side_effect=Exception("eval err"))
        msg_loc.nth = MagicMock(return_value=last_msg)

        def _locator(sel):
            if "message" in str(sel):
                return msg_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Grok()
        # _no_stop_polls is incremented inside completion_check, so set to 1 → becomes 2 < 3
        g._no_stop_polls = 1
        result = await g.completion_check(page)
        assert result is False


# ---------------------------------------------------------------------------
# extract_response
# ---------------------------------------------------------------------------


class TestGrokExtractResponse:
    async def test_rate_limit_message_returned(self):
        page = _make_page()
        rate_loc = _visible_locator()
        page.get_by_text = MagicMock(return_value=rate_loc)
        g = Grok()
        result = await g.extract_response(page)
        assert "[RATE LIMITED]" in result

    async def test_message_container_extraction(self):
        """Message container with > 200 chars returned."""
        page = _make_page()

        # No rate limit
        def _get_by_text(text, **kw):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_text = MagicMock(side_effect=_get_by_text)

        text = "response text " * 20
        msg_loc = MagicMock()
        msg_loc.count = AsyncMock(return_value=1)
        last_item = MagicMock()
        last_item.inner_text = AsyncMock(return_value=text)
        msg_loc.nth = MagicMock(return_value=last_item)

        page.locator = MagicMock(return_value=msg_loc)
        g = Grok()
        g.prompt_sigs = []
        result = await g.extract_response(page)
        assert result == text

    async def test_body_marker_extraction(self):
        """Body with markdown marker → extracts from marker."""
        page = _make_page()

        def _get_by_text(text, **kw):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_text = MagicMock(side_effect=_get_by_text)
        page.locator = MagicMock(side_effect=Exception("no container"))

        # Use "# " marker (not "## ") — code scans "# " first and finds it within "## "
        body = "# Section Heading\n" + "content " * 100
        page.evaluate = AsyncMock(return_value=body)

        g = Grok()
        g.prompt_sigs = []
        result = await g.extract_response(page)
        assert "# Section Heading" in result

    async def test_main_container_fallback(self):
        """Body < 500 chars → main container JS fallback."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("no container"))
        page.get_by_text = MagicMock(side_effect=Exception("no rate"))

        call_num = [0]

        async def _eval(script):
            call_num[0] += 1
            if call_num[0] == 1:
                return "short"  # body short
            return "main content " * 30  # main container

        page.evaluate = AsyncMock(side_effect=_eval)

        g = Grok()
        g.prompt_sigs = []
        result = await g.extract_response(page)
        assert "main content" in result

    async def test_last_resort_body_text(self):
        """All else fails → body.innerText as last resort."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("no container"))
        page.get_by_text = MagicMock(side_effect=Exception("no rate"))

        async def _eval(script):
            return "final body text"

        page.evaluate = AsyncMock(side_effect=_eval)

        g = Grok()
        g.prompt_sigs = []
        result = await g.extract_response(page)
        assert result == "final body text"


# ---------------------------------------------------------------------------
# Additional coverage tests for exception handlers
# ---------------------------------------------------------------------------


class TestGrokCompletionCheckEdgeCases:
    async def test_stop_locator_exception_swallowed(self):
        """locator for Stop raises → exception swallowed."""
        page = _make_page()

        def _locator(sel):
            raise Exception("locator boom")

        page.locator = MagicMock(side_effect=_locator)
        g = Grok()
        g._no_stop_polls = 2
        result = await g.completion_check(page)
        # Stable at 3 polls after increment
        assert result is True

    async def test_messages_locator_exception_swallowed(self):
        """messages locator raises → exception swallowed, stable-state check."""
        page = _make_page()

        call_num = [0]

        def _locator(sel):
            call_num[0] += 1
            if call_num[0] <= 2:  # Stop/Cancel
                loc = MagicMock()
                loc.first = MagicMock()
                loc.first.count = AsyncMock(return_value=0)
                loc.first.is_visible = AsyncMock(return_value=False)
                return loc
            raise Exception("messages locator boom")

        page.locator = MagicMock(side_effect=_locator)
        g = Grok()
        g._no_stop_polls = 2
        result = await g.completion_check(page)
        assert result is True


class TestGrokExtractResponseEdgeCases:
    async def test_marker_extraction_prompt_echo_skipped(self):
        """Body marker candidate is prompt echo → skipped."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("no container"))

        def _get_by_text(text, **kw):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_text = MagicMock(side_effect=_get_by_text)

        # First "# " section is a prompt echo, second is real content
        body = "# Intro\nprompt sig " * 30 + "\n# Real Section\n" + "real content " * 50
        page.evaluate = AsyncMock(return_value=body)

        g = Grok()
        g.prompt_sigs = ["prompt sig"]
        result = await g.extract_response(page)
        assert len(result) > 200

    async def test_marker_extraction_exception_falls_to_main(self):
        """Exception in body evaluate → falls to main container."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("no container"))

        def _get_by_text(text, **kw):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_text = MagicMock(side_effect=_get_by_text)

        call_num = [0]

        async def _eval(script):
            call_num[0] += 1
            if call_num[0] == 1:
                raise Exception("body eval error")
            return "main content " * 30

        page.evaluate = AsyncMock(side_effect=_eval)

        g = Grok()
        g.prompt_sigs = []
        result = await g.extract_response(page)
        assert "main content" in result

    async def test_main_container_is_prompt_echo_falls_to_body(self):
        """Main container text is prompt echo → falls to body.innerText."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("no container"))

        def _get_by_text(text, **kw):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_text = MagicMock(side_effect=_get_by_text)

        call_num = [0]

        async def _eval(script):
            call_num[0] += 1
            # body for marker scan (short → skip marker check)
            if call_num[0] == 1:
                return "short"
            # main container returns prompt echo
            if call_num[0] == 2:
                return "prompt echo content " * 20
            # body.innerText last resort
            return "final body"

        page.evaluate = AsyncMock(side_effect=_eval)

        g = Grok()
        g.prompt_sigs = ["prompt echo content"]
        result = await g.extract_response(page)
        assert result == "final body"

    async def test_main_container_exception_falls_to_body(self):
        """Main container evaluate raises → falls to body.innerText."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("no container"))

        def _get_by_text(text, **kw):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.get_by_text = MagicMock(side_effect=_get_by_text)

        call_num = [0]

        async def _eval(script):
            call_num[0] += 1
            if call_num[0] == 1:
                return "short"  # body for marker (skip)
            if call_num[0] == 2:
                raise Exception("main eval error")
            return "final body"

        page.evaluate = AsyncMock(side_effect=_eval)

        g = Grok()
        g.prompt_sigs = []
        result = await g.extract_response(page)
        assert result == "final body"


class TestGrokMissingLines:
    """Cover lines 192-193 (prompt echo skip in marker loop) and 220 (last resort body echo)."""

    async def test_marker_candidate_prompt_echo_skipped_continues(self):
        """In marker loop, last marker candidate is prompt echo → log.debug + continue (lines 192-193);
        earlier candidate (real content) then returned."""
        page = _make_page()

        sig = "prompt echo sig"
        real = "real content " * 60  # 780 chars, no sig

        # Body structure: REAL at first "# " position, ECHO at second (last) "# " position.
        # reversed() iterates last first → echo hit → lines 192-193 → continue.
        # Then real content at earlier position → returned.
        # Total must be > 500 chars.
        body = f"# Real\n{real}\n# Echo\n{sig * 30}"

        def _locator(sel):
            loc = MagicMock()
            loc.count = AsyncMock(return_value=0)
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        def _get_by_text(text, **kw):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        page.get_by_text = MagicMock(side_effect=_get_by_text)
        page.evaluate = AsyncMock(return_value=body)

        g = Grok()
        g.prompt_sigs = [sig]

        with patch("platforms.grok.log") as mock_log:
            result = await g.extract_response(page)

        # Should have skipped the echo and returned the real content
        assert "real content" in result
        debug_calls = [str(c) for c in mock_log.debug.call_args_list]
        assert any("prompt echo" in c for c in debug_calls)

    async def test_last_resort_body_is_prompt_echo_warning(self):
        """body.innerText is prompt echo at last resort → warning logged (line 220)."""
        page = _make_page()

        sig = "prompt echo sig"
        echo_body = sig * 100  # > 200 chars but is prompt echo

        call_num = [0]

        async def _eval(script):
            call_num[0] += 1
            if call_num[0] == 1:
                # Secondary: body scan — short so marker block skipped
                return "short"
            if call_num[0] == 2:
                # Tertiary: main container JS → raise so falls to last resort
                raise Exception("main container error")
            # Last resort: document.body.innerText → echo body
            return echo_body

        page.evaluate = AsyncMock(side_effect=_eval)

        # Message container: locator returns count=0 so primary is skipped
        def _locator(sel):
            loc = MagicMock()
            loc.count = AsyncMock(return_value=0)
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        def _get_by_text(text, **kw):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        page.get_by_text = MagicMock(side_effect=_get_by_text)

        g = Grok()
        g.prompt_sigs = [sig]

        with patch("platforms.grok.log") as mock_log:
            result = await g.extract_response(page)

        # Warning about prompt echo at line 220
        warning_calls = [str(c) for c in mock_log.warning.call_args_list]
        assert any("prompt echo" in w for w in warning_calls)
        assert result == echo_body
