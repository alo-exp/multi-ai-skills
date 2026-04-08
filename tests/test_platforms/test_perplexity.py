"""Unit tests for Perplexity platform driver."""

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

from platforms.perplexity import Perplexity  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(url="https://perplexity.ai/search/abc"):
    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.evaluate = AsyncMock(return_value="body text")
    page.url = url

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

    def _gbt(text, **kw):
        return _locator(text)

    def _gbr(role, **kw):
        return _locator(role)

    page.get_by_text = MagicMock(side_effect=_gbt)
    page.get_by_role = MagicMock(side_effect=_gbr)
    return page


def _visible_locator(inner_text="content"):
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


class TestPerplexityCheckRateLimit:
    async def test_no_limit(self):
        page = _make_page()
        g = Perplexity()
        assert await g.check_rate_limit(page) is None

    async def test_visible_pattern(self):
        page = _make_page()
        page.get_by_text = MagicMock(return_value=_visible_locator())
        g = Perplexity()
        result = await g.check_rate_limit(page)
        assert result == "Pro search limit"

    async def test_exception_swallowed(self):
        page = _make_page()
        page.get_by_text = MagicMock(side_effect=Exception("boom"))
        g = Perplexity()
        assert await g.check_rate_limit(page) is None


# ---------------------------------------------------------------------------
# configure_mode
# ---------------------------------------------------------------------------


class TestPerplexityConfigureMode:
    async def test_regular_mode_no_model_btn(self):
        page = _make_page()
        g = Perplexity()
        result = await g.configure_mode(page, "REGULAR")
        assert "Sonar (default)" in result

    async def test_model_selection_sonar_pro(self):
        """Model btn found, SonarPro selected."""
        page = _make_page()

        model_btn = _visible_locator()

        sonar_pro = MagicMock()
        sonar_pro.count = AsyncMock(return_value=1)
        opt = MagicMock()
        opt.is_visible = AsyncMock(return_value=True)
        opt.inner_text = AsyncMock(return_value="Sonar Pro")
        opt.click = AsyncMock()
        sonar_pro.nth = MagicMock(return_value=opt)

        call_texts = []

        def _locator(sel):
            if "model-selector" in str(sel) or "Model" in str(sel):
                return model_btn
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            loc.count = AsyncMock(return_value=0)
            return loc

        def _gbt(text, **kw):
            if "Sonar Pro" in str(text):
                return sonar_pro
            loc = MagicMock()
            loc.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        page.get_by_text = MagicMock(side_effect=_gbt)
        g = Perplexity()
        result = await g.configure_mode(page, "REGULAR")
        assert "Sonar" in result

    async def test_model_skips_computer_option(self):
        """Option containing 'computer' is skipped."""
        page = _make_page()

        model_btn = _visible_locator()

        sonar_computer = MagicMock()
        sonar_computer.count = AsyncMock(return_value=1)
        opt = MagicMock()
        opt.is_visible = AsyncMock(return_value=True)
        opt.inner_text = AsyncMock(return_value="Sonar Computer")
        opt.click = AsyncMock()
        sonar_computer.nth = MagicMock(return_value=opt)

        def _locator(sel):
            if "model-selector" in str(sel) or "Model" in str(sel):
                return model_btn
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            loc.count = AsyncMock(return_value=0)
            return loc

        def _gbt(text, **kw):
            if "Sonar" in str(text):
                return sonar_computer
            loc = MagicMock()
            loc.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        page.get_by_text = MagicMock(side_effect=_gbt)
        g = Perplexity()
        result = await g.configure_mode(page, "REGULAR")
        # Falls back to escape + default
        assert "Sonar" in result

    async def test_model_exception_falls_to_default(self):
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("boom"))
        g = Perplexity()
        result = await g.configure_mode(page, "REGULAR")
        assert "Sonar (default)" in result

    async def test_deep_mode_research_toggle(self):
        """DEEP mode: Research toggle found and clicked."""
        page = _make_page()

        research_tog = MagicMock()
        research_tog.count = AsyncMock(return_value=1)
        tog_item = MagicMock()
        tog_item.is_visible = AsyncMock(return_value=True)
        tog_item.inner_text = AsyncMock(return_value="Deep Research")
        tog_item.click = AsyncMock()
        research_tog.nth = MagicMock(return_value=tog_item)

        def _gbt(text, **kw):
            if "Deep Research" in str(text) or "Research" in str(text):
                return research_tog
            loc = MagicMock()
            loc.count = AsyncMock(return_value=0)
            return loc

        page.get_by_text = MagicMock(side_effect=_gbt)
        g = Perplexity()
        result = await g.configure_mode(page, "DEEP")
        assert "+ Research" in result

    async def test_deep_mode_skips_computer_toggle(self):
        """DEEP mode: research toggle with 'computer' is skipped."""
        page = _make_page()

        research_computer = MagicMock()
        research_computer.count = AsyncMock(return_value=1)
        tog_item = MagicMock()
        tog_item.is_visible = AsyncMock(return_value=True)
        tog_item.inner_text = AsyncMock(return_value="Research Computer")
        tog_item.click = AsyncMock()
        research_computer.nth = MagicMock(return_value=tog_item)

        def _gbt(text, **kw):
            if "Research" in str(text):
                return research_computer
            loc = MagicMock()
            loc.count = AsyncMock(return_value=0)
            return loc

        page.get_by_text = MagicMock(side_effect=_gbt)
        g = Perplexity()
        result = await g.configure_mode(page, "DEEP")
        assert "+ Research" in result  # label still added even if not found

    async def test_deep_mode_research_exception_non_fatal(self):
        """DEEP mode: research toggle exception → non-fatal, proceeds."""
        page = _make_page()
        call_num = [0]

        def _gbt(text, **kw):
            call_num[0] += 1
            if "Research" in str(text):
                raise Exception("research boom")
            loc = MagicMock()
            loc.count = AsyncMock(return_value=0)
            return loc

        page.get_by_text = MagicMock(side_effect=_gbt)
        g = Perplexity()
        result = await g.configure_mode(page, "DEEP")
        assert "+ Research" in result


# ---------------------------------------------------------------------------
# inject_prompt
# ---------------------------------------------------------------------------


class TestPerplexityInjectPrompt:
    async def test_textarea_fill(self):
        page = _make_page()

        ta_loc = MagicMock()
        ta_loc.first = MagicMock()
        ta_loc.first.count = AsyncMock(return_value=1)
        ta_loc.first.is_visible = AsyncMock(return_value=True)
        ta_loc.first.click = AsyncMock()
        ta_loc.first.fill = AsyncMock()
        ta_loc.first.dispatch_event = AsyncMock()

        def _locator(sel):
            if "textarea" in str(sel) or "Ask" in str(sel):
                return ta_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        await g.inject_prompt(page, "test prompt")
        ta_loc.first.fill.assert_called_once_with("test prompt")

    async def test_contenteditable_fallback(self):
        """No textarea → contenteditable fallback."""
        page = _make_page()
        page.wait_for_selector = AsyncMock()

        ce_loc = MagicMock()
        ce_loc.first = MagicMock()
        ce_loc.first.count = AsyncMock(return_value=1)
        ce_loc.first.is_visible = AsyncMock(return_value=True)
        ce_loc.first.click = AsyncMock()

        def _locator(sel):
            if "contenteditable" in str(sel):
                return ce_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        g._inject_exec_command = AsyncMock(return_value=20)
        await g.inject_prompt(page, "hello")
        g._inject_exec_command.assert_called_once()

    async def test_no_input_raises(self):
        page = _make_page()
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
        g = Perplexity()
        with pytest.raises(RuntimeError, match="No input element"):
            await g.inject_prompt(page, "prompt")


# ---------------------------------------------------------------------------
# click_send
# ---------------------------------------------------------------------------


class TestPerplexityClickSend:
    async def test_aria_label_button(self):
        page = _make_page()
        btn = _visible_locator()

        def _locator(sel):
            if "Submit" in str(sel) or "Send" in str(sel) or "Search" in str(sel) or "Ask" in str(sel):
                return btn
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        await g.click_send(page)
        btn.first.click.assert_called()

    async def test_role_button_fallback(self):
        page = _make_page()
        btn = _visible_locator()

        page.get_by_role = MagicMock(return_value=btn)
        g = Perplexity()
        await g.click_send(page)
        btn.first.click.assert_called()

    async def test_enter_fallback(self):
        """All buttons fail → press Enter."""
        page = _make_page()
        g = Perplexity()
        g._agent_fallback = AsyncMock(side_effect=Exception("no agent"))
        await g.click_send(page)
        page.keyboard.press.assert_called_with("Enter")


# ---------------------------------------------------------------------------
# completion_check
# ---------------------------------------------------------------------------


class TestPerplexityCompletionCheck:
    async def test_stop_button_visible_returns_false(self):
        page = _make_page()
        stop_loc = _visible_locator()

        def _locator(sel):
            if "Stop" in str(sel) or "Cancel" in str(sel):
                return stop_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        assert await g.completion_check(page) is False
        assert g._no_stop_polls == 0

    async def test_page_growing_returns_false(self):
        page = _make_page()
        page.evaluate = AsyncMock(return_value=5000)

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        g._last_page_len = 1000  # smaller than current → growing
        assert await g.completion_check(page) is False

    async def test_sources_and_prose_returns_true(self):
        """Sources >= 2 + prose > 3000 on conversation page → complete."""
        page = _make_page(url="https://perplexity.ai/search/xyz")
        page.evaluate = AsyncMock(return_value=12000)

        src_loc = MagicMock()
        src_loc.count = AsyncMock(return_value=3)

        prose_loc = MagicMock()
        prose_item = MagicMock()
        prose_item.count = AsyncMock(return_value=1)
        prose_item.evaluate = AsyncMock(return_value=5000)
        prose_loc.first = prose_item
        prose_loc.count = AsyncMock(return_value=1)

        def _locator(sel):
            if "source" in str(sel) or "citation" in str(sel):
                return src_loc
            if "prose" in str(sel):
                return prose_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        g._last_page_len = 12000
        g._no_stop_polls = 1
        assert await g.completion_check(page) is True

    async def test_stable_state_6_polls(self):
        page = _make_page(url="https://perplexity.ai/search/xyz")
        page.evaluate = AsyncMock(return_value=15000)

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            loc.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        g._no_stop_polls = 6
        g._last_page_len = 15000
        assert await g.completion_check(page) is True

    async def test_extended_stable_12_polls(self):
        page = _make_page(url="https://perplexity.ai/")
        page.evaluate = AsyncMock(return_value=100)

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            loc.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        g._no_stop_polls = 12
        g._last_page_len = 100
        assert await g.completion_check(page) is True

    async def test_sources_prose_short_waits(self):
        """Sources found but prose too short → still waiting."""
        page = _make_page(url="https://perplexity.ai/search/xyz")
        page.evaluate = AsyncMock(return_value=2000)

        src_loc = MagicMock()
        src_loc.count = AsyncMock(return_value=3)

        prose_loc = MagicMock()
        prose_item = MagicMock()
        prose_item.count = AsyncMock(return_value=1)
        prose_item.evaluate = AsyncMock(return_value=500)
        prose_loc.first = prose_item
        prose_loc.count = AsyncMock(return_value=1)

        def _locator(sel):
            if "source" in str(sel) or "citation" in str(sel):
                return src_loc
            if "prose" in str(sel):
                return prose_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        g._no_stop_polls = 1
        g._last_page_len = 2000
        result = await g.completion_check(page)
        assert result is False


# ---------------------------------------------------------------------------
# extract_response
# ---------------------------------------------------------------------------


class TestPerplexityExtractResponse:
    async def test_prose_elements_joined(self):
        page = _make_page()

        prose_loc = MagicMock()
        prose_loc.count = AsyncMock(return_value=2)
        item1 = MagicMock()
        item1.inner_text = AsyncMock(return_value="Part one " * 50)
        item2 = MagicMock()
        item2.inner_text = AsyncMock(return_value="Part two " * 50)
        prose_loc.nth = MagicMock(side_effect=lambda i: [item1, item2][i])

        page.locator = MagicMock(return_value=prose_loc)
        g = Perplexity()
        result = await g.extract_response(page)
        assert "Part one" in result and "Part two" in result

    async def test_prose_short_falls_to_class_prose(self):
        """Primary .prose short → [class*=prose] fallback."""
        page = _make_page()

        short_prose = MagicMock()
        short_prose.count = AsyncMock(return_value=1)
        short_item = MagicMock()
        short_item.inner_text = AsyncMock(return_value="short")
        short_prose.nth = MagicMock(return_value=short_item)

        long_prose = MagicMock()
        long_prose.count = AsyncMock(return_value=1)
        long_item = MagicMock()
        long_item.inner_text = AsyncMock(return_value="long content " * 50)
        long_prose.nth = MagicMock(return_value=long_item)

        call_num = [0]

        def _locator(sel):
            call_num[0] += 1
            if call_num[0] == 1:
                return short_prose
            return long_prose

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        result = await g.extract_response(page)
        assert "long content" in result

    async def test_main_container_fallback(self):
        """All prose fails → main container JS."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("no prose"))

        async def _eval(script):
            if "main" in str(script):
                return "main content " * 30
            return "body"

        page.evaluate = AsyncMock(side_effect=_eval)
        g = Perplexity()
        result = await g.extract_response(page)
        assert "main content" in result

    async def test_body_fallback_with_prompt_echo(self):
        """Last resort: body.innerText even if prompt echo."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("no prose"))

        call_num = [0]

        async def _eval(script):
            call_num[0] += 1
            if call_num[0] == 1:
                return ""  # main container empty
            return "body fallback text"

        page.evaluate = AsyncMock(side_effect=_eval)
        g = Perplexity()
        g.prompt_sigs = ["body fallback text"]  # make it look like prompt echo
        result = await g.extract_response(page)
        assert result == "body fallback text"

    async def test_prose_exception_falls_through(self):
        """Exception in prose extraction → falls to alt prose."""
        page = _make_page()

        call_num = [0]

        def _locator(sel):
            call_num[0] += 1
            if call_num[0] == 1:
                raise Exception("prose error")
            loc = MagicMock()
            loc.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)

        async def _eval(script):
            return "body content " * 50

        page.evaluate = AsyncMock(side_effect=_eval)
        g = Perplexity()
        g.prompt_sigs = []
        result = await g.extract_response(page)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Additional coverage tests for exception handlers and edge branches
# ---------------------------------------------------------------------------


class TestPerplexityConfigureModeEdgeCases:
    async def test_model_option_not_visible_skipped(self):
        """Model option not visible → skipped via continue."""
        page = _make_page()

        model_btn = _visible_locator()

        sonar = MagicMock()
        sonar.count = AsyncMock(return_value=1)
        opt = MagicMock()
        opt.is_visible = AsyncMock(return_value=False)  # not visible → continue
        opt.inner_text = AsyncMock(return_value="Sonar")
        opt.click = AsyncMock()
        sonar.nth = MagicMock(return_value=opt)

        def _locator(sel):
            if "model-selector" in str(sel) or "Model" in str(sel):
                return model_btn
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            loc.count = AsyncMock(return_value=0)
            return loc

        def _gbt(text, **kw):
            if "Sonar" in str(text):
                return sonar
            loc = MagicMock()
            loc.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        page.get_by_text = MagicMock(side_effect=_gbt)
        g = Perplexity()
        result = await g.configure_mode(page, "REGULAR")
        # Not visible → skipped → default used
        assert "Sonar (default)" in result

    async def test_research_toggle_not_visible_skipped(self):
        """Research toggle not visible → skipped via continue."""
        page = _make_page()

        research = MagicMock()
        research.count = AsyncMock(return_value=1)
        tog = MagicMock()
        tog.is_visible = AsyncMock(return_value=False)  # not visible → continue
        tog.inner_text = AsyncMock(return_value="Research")
        tog.click = AsyncMock()
        research.nth = MagicMock(return_value=tog)

        def _gbt(text, **kw):
            if "Research" in str(text):
                return research
            loc = MagicMock()
            loc.count = AsyncMock(return_value=0)
            return loc

        page.get_by_text = MagicMock(side_effect=_gbt)
        g = Perplexity()
        result = await g.configure_mode(page, "DEEP")
        assert "+ Research" in result


class TestPerplexityClickSendEdgeCases:
    async def test_agent_fallback_returns_value(self):
        """_agent_fallback returns value → click_send returns without pressing Enter."""
        page = _make_page()
        g = Perplexity()
        g._agent_fallback = AsyncMock(return_value="clicked")
        await g.click_send(page)
        page.keyboard.press.assert_not_called()


class TestPerplexityCompletionCheckEdgeCases:
    async def test_stop_locator_exception_swallowed(self):
        """locator for Stop raises → exception swallowed."""
        page = _make_page(url="https://perplexity.ai/search/abc")
        page.evaluate = AsyncMock(return_value=15000)

        def _locator(sel):
            raise Exception("locator boom")

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        g._no_stop_polls = 6
        g._last_page_len = 15000
        result = await g.completion_check(page)
        assert result is True

    async def test_page_evaluate_exception_swallowed(self):
        """page.evaluate raises in growth check → exception swallowed."""
        page = _make_page(url="https://perplexity.ai/search/abc")
        page.evaluate = AsyncMock(side_effect=Exception("eval boom"))

        def _locator(sel):
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.first.is_visible = AsyncMock(return_value=False)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        g._no_stop_polls = 12
        g._last_page_len = 0
        result = await g.completion_check(page)
        assert result is True

    async def test_sources_locator_exception_swallowed(self):
        """sources locator raises → exception swallowed."""
        page = _make_page(url="https://perplexity.ai/search/abc")
        page.evaluate = AsyncMock(return_value=2000)

        call_num = [0]

        def _locator(sel):
            call_num[0] += 1
            if call_num[0] == 1:
                raise Exception("sources boom")
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        g._no_stop_polls = 1
        g._last_page_len = 2000
        result = await g.completion_check(page)
        assert result is False

    async def test_prose_evaluate_exception_swallowed(self):
        """prose evaluate raises → exception swallowed."""
        page = _make_page(url="https://perplexity.ai/search/abc")
        page.evaluate = AsyncMock(return_value=5000)

        src_loc = MagicMock()
        src_loc.count = AsyncMock(return_value=3)

        prose_loc = MagicMock()
        prose_item = MagicMock()
        prose_item.count = AsyncMock(return_value=1)
        prose_item.evaluate = AsyncMock(side_effect=Exception("prose eval boom"))
        prose_loc.first = prose_item
        prose_loc.count = AsyncMock(return_value=1)

        def _locator(sel):
            if "source" in str(sel) or "citation" in str(sel):
                return src_loc
            if "prose" in str(sel):
                return prose_loc
            loc = MagicMock()
            loc.first = MagicMock()
            loc.first.count = AsyncMock(return_value=0)
            loc.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        g = Perplexity()
        g._no_stop_polls = 1
        g._last_page_len = 5000
        result = await g.completion_check(page)
        assert result is False


class TestPerplexityExtractResponseEdgeCases:
    async def test_prose_item_exception_skipped(self):
        """Exception in prose item inner_text → item skipped."""
        page = _make_page()

        prose_loc = MagicMock()
        prose_loc.count = AsyncMock(return_value=2)
        good_item = MagicMock()
        good_item.inner_text = AsyncMock(return_value="good content " * 50)
        bad_item = MagicMock()
        bad_item.inner_text = AsyncMock(side_effect=Exception("inner_text boom"))

        def _nth(i):
            return bad_item if i == 0 else good_item

        prose_loc.nth = MagicMock(side_effect=_nth)

        page.locator = MagicMock(return_value=prose_loc)
        g = Perplexity()
        result = await g.extract_response(page)
        assert "good content" in result

    async def test_alt_prose_item_exception_skipped(self):
        """Exception in [class*=prose] item → item skipped, falls to main."""
        page = _make_page()

        short_prose = MagicMock()
        short_prose.count = AsyncMock(return_value=1)
        short_item = MagicMock()
        short_item.inner_text = AsyncMock(return_value="short")
        short_prose.nth = MagicMock(return_value=short_item)

        alt_prose = MagicMock()
        alt_prose.count = AsyncMock(return_value=1)
        bad_item = MagicMock()
        bad_item.inner_text = AsyncMock(side_effect=Exception("alt boom"))
        alt_prose.nth = MagicMock(return_value=bad_item)

        call_num = [0]

        def _locator(sel):
            call_num[0] += 1
            if call_num[0] == 1:
                return short_prose
            if call_num[0] == 2:
                return alt_prose
            # Subsequent calls for main container
            loc = MagicMock()
            loc.count = AsyncMock(return_value=0)
            return loc

        page.locator = MagicMock(side_effect=_locator)
        page.evaluate = AsyncMock(return_value="main result " * 30)
        g = Perplexity()
        result = await g.extract_response(page)
        assert len(result) > 0

    async def test_main_container_exception_falls_to_body(self):
        """Main container evaluate raises → falls to body.innerText."""
        page = _make_page()
        page.locator = MagicMock(side_effect=Exception("no prose"))

        call_num = [0]

        async def _eval(script):
            call_num[0] += 1
            if call_num[0] == 1:
                raise Exception("main eval boom")
            return "body fallback " * 10

        page.evaluate = AsyncMock(side_effect=_eval)
        g = Perplexity()
        g.prompt_sigs = []
        result = await g.extract_response(page)
        assert "body fallback" in result
