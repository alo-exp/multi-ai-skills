"""Unit tests for DeepSeek.completion_check()."""

import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.conftest import install_stubs

# Conversation URL so in_conversation=True inside completion_check
_CONV_URL = "https://chat.deepseek.com/r/abc123"


def _make_page_mock(body_len=0, has_rect_button=False):
    """Return a mock Page with configurable SVG rect result and body text length."""
    page = MagicMock()
    # Must be a conversation URL so in_conversation=True
    page.url = _CONV_URL

    async def evaluate(expr, *args, **kwargs):
        # SVG rect JS (step 2): contains 'ds-icon-button' or 'svg rect'
        if "ds-icon-button" in expr or "svg rect" in expr:
            return has_rect_button
        # Body text length (step 4): contains 'innerText.length'
        if "innerText.length" in expr:
            return body_len
        return body_len
    page.evaluate = evaluate

    def locator(selector):
        loc = MagicMock()
        # No Copy/Regenerate/Stop text buttons visible — only SVG rect path matters
        loc.count = AsyncMock(return_value=0)
        loc.is_visible = AsyncMock(return_value=False)
        loc.first = loc
        return loc
    page.locator = locator

    def get_by_text(text, **kwargs):
        loc = MagicMock()
        loc.count = AsyncMock(return_value=0)
        loc.first = loc
        return loc
    page.get_by_text = get_by_text
    return page


def _load_deepseek():
    install_stubs("deepseek", "https://chat.deepseek.com")
    for mod in list(sys.modules):
        if "deepseek" in mod:
            del sys.modules[mod]
    from platforms import deepseek as ds_mod
    d = ds_mod.DeepSeek()
    d._prev_text_len = 0
    d._stable_text_polls = 0
    d._no_stop_polls = 0
    return d


class TestDeepSeekCompletionCheck(unittest.IsolatedAsyncioTestCase):

    async def test_svg_rect_button_means_stop(self):
        """SVG rect discriminator: button with <rect> → stop → still generating."""
        d = _load_deepseek()
        page = _make_page_mock(body_len=1000, has_rect_button=True)
        result = await d.completion_check(page)
        self.assertFalse(result, "Stop button (SVG rect) visible → not complete")

    async def test_svg_path_only_button_means_send(self):
        """Button with only <path> (no rect) + text stable 3 polls → complete."""
        d = _load_deepseek()
        # body_len same as _prev_text_len → stable this poll, making stable_polls=3
        page = _make_page_mock(body_len=1000, has_rect_button=False)
        d._prev_text_len = 1000   # same as body_len → stable
        d._stable_text_polls = 2  # will become 3 after this poll
        result = await d.completion_check(page)
        self.assertTrue(result, "No stop rect + 3 stable polls + >500c → complete")

    async def test_text_growth_tracking_stable_for_3_polls(self):
        """Text stable for 3 consecutive polls at >500c → complete."""
        d = _load_deepseek()
        page = _make_page_mock(body_len=800, has_rect_button=False)
        d._prev_text_len = 800   # same → stable
        d._stable_text_polls = 2  # becomes 3 after this poll
        result = await d.completion_check(page)
        self.assertTrue(result, "Text stable for 3 polls (≥500c) → complete")

    async def test_text_still_growing_not_complete(self):
        """Text still growing → not complete, stable counter resets to 0."""
        d = _load_deepseek()
        page = _make_page_mock(body_len=2000, has_rect_button=False)
        d._prev_text_len = 500   # smaller than 2000 → growing
        d._stable_text_polls = 5  # should reset to 0
        result = await d.completion_check(page)
        self.assertFalse(result, "Text still growing → not complete")
        self.assertEqual(d._stable_text_polls, 0, "stable_text_polls should reset on growth")


if __name__ == "__main__":
    unittest.main()
