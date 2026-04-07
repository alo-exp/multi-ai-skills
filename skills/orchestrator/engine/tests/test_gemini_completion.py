"""Unit tests for Gemini.completion_check()."""

import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, "/Users/shafqat/Documents/Projects/MultAI/skills/orchestrator/engine")
from tests.conftest import install_stubs


def _make_page_mock(body_len=0, stop_visible=False, share_export_visible=False):
    """Return a mock Page with configurable stop/share button visibility and body length."""
    page = MagicMock()
    page.url = "https://gemini.google.com/app"

    async def evaluate(expr, *args, **kwargs):
        return body_len
    page.evaluate = evaluate

    def get_by_text(text, **kwargs):
        loc = MagicMock()
        is_stop = any(kw in text for kw in ["Stop", "Cancel", "Thinking", "Searching", "Analyzing", "Reading"])
        is_share = "Share" in text or "Export" in text
        visible = (stop_visible and is_stop) or (share_export_visible and is_share)
        loc.count = AsyncMock(return_value=1 if visible else 0)
        loc.is_visible = AsyncMock(return_value=visible)
        loc.first = loc
        return loc
    page.get_by_text = get_by_text

    def locator(selector):
        loc = MagicMock()
        is_stop_sel = "Stop" in selector or "Cancel" in selector or "stop" in selector
        is_share_sel = "Share" in selector or "Export" in selector or "Copy" in selector
        visible = (stop_visible and is_stop_sel) or (share_export_visible and is_share_sel)
        loc.count = AsyncMock(return_value=1 if visible else 0)
        loc.is_visible = AsyncMock(return_value=visible)
        loc.first = loc
        return loc
    page.locator = locator

    page.bring_to_front = AsyncMock()
    return page


def _load_gemini():
    install_stubs("gemini", "https://gemini.google.com/app")
    for mod in list(sys.modules):
        if "gemini" in mod and "platforms" in mod:
            del sys.modules[mod]
    from platforms import gemini as gem_mod
    g = gem_mod.Gemini()
    g._deep_mode = True
    g._seen_stop = False
    g._no_stop_polls = 0
    g._dr_start_unconfirmed = False
    return g


class TestGeminiCompletionCheck(unittest.IsolatedAsyncioTestCase):

    async def test_quick_response_fires_at_poll_6_when_seen_stop_false_and_body_large(self):
        """Quick-response exit fires at poll 6 when _seen_stop=False and body > 5000c."""
        g = _load_gemini()
        page = _make_page_mock(body_len=6000)
        g._no_stop_polls = 5        # will become 6 inside completion_check
        g._seen_stop = False
        g._dr_start_unconfirmed = False
        result = await g.completion_check(page)
        self.assertTrue(result, "Should declare complete at poll 6 with body>5000 and _seen_stop=False")

    async def test_quick_response_suppressed_when_dr_start_unconfirmed(self):
        """Quick-response exit suppressed when _dr_start_unconfirmed=True."""
        g = _load_gemini()
        page = _make_page_mock(body_len=6000)
        g._no_stop_polls = 5
        g._seen_stop = False
        g._dr_start_unconfirmed = True
        result = await g.completion_check(page)
        self.assertFalse(result, "Should NOT declare complete when _dr_start_unconfirmed=True")

    async def test_seen_stop_set_when_stop_button_visible(self):
        """_seen_stop is set to True when a stop/cancel button is visible."""
        g = _load_gemini()
        page = _make_page_mock(body_len=100, stop_visible=True)
        g._seen_stop = False
        result = await g.completion_check(page)
        self.assertFalse(result, "Should return False (still generating) when stop visible")
        self.assertTrue(g._seen_stop, "_seen_stop should be True after stop button observed")

    async def test_stable_threshold_90_polls_fires_after_seen_stop(self):
        """Stable threshold (90 polls) declares complete in DEEP mode after _seen_stop=True."""
        g = _load_gemini()
        page = _make_page_mock(body_len=1000)
        g._no_stop_polls = 89       # will become 90 inside completion_check
        g._seen_stop = True
        g._deep_mode = True
        result = await g.completion_check(page)
        self.assertTrue(result, "Should declare complete after 90 stable polls with _seen_stop=True")

    async def test_share_export_button_triggers_completion(self):
        """Share & Export button triggers completion when body_len > 3000 and _seen_stop=True."""
        g = _load_gemini()
        # body_len must be > 3000 for the share/export check to be reached (line 369 guard)
        page = _make_page_mock(body_len=5000, share_export_visible=True)
        g._seen_stop = True
        g._no_stop_polls = 1
        result = await g.completion_check(page)
        self.assertTrue(result, "Share & Export button should trigger completion")


if __name__ == "__main__":
    unittest.main()
