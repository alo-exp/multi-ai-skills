"""Unit tests for ChatGPT.check_rate_limit()."""

import importlib
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.conftest import install_stubs


def _make_page_mock(visible_text=None, body_text=None):
    page = MagicMock()
    page.url = "https://chatgpt.com"

    def get_by_text(text, **kwargs):
        loc = MagicMock()
        hit = bool(visible_text and text.lower() in visible_text.lower())
        loc.count = AsyncMock(return_value=1 if hit else 0)
        loc.is_visible = AsyncMock(return_value=hit)
        loc.first = loc
        return loc
    page.get_by_text = get_by_text

    async def evaluate(expr, *args, **kwargs):
        return body_text or ""
    page.evaluate = evaluate
    return page


def _load_chatgpt():
    install_stubs("chatgpt", "https://chatgpt.com")
    for mod in list(sys.modules):
        if "chatgpt" in mod:
            del sys.modules[mod]
    from platforms import chatgpt as cg_mod
    return cg_mod.ChatGPT()


class TestChatGPTRateLimit(unittest.IsolatedAsyncioTestCase):

    async def test_detects_youve_reached_your_limit(self):
        """Detects 'You've reached your limit' via visible DOM element."""
        cg = _load_chatgpt()
        page = _make_page_mock(visible_text="You've reached your limit")
        result = await cg.check_rate_limit(page)
        self.assertIsNotNone(result, "Should detect rate limit via DOM element")
        self.assertIn("limit", result.lower())

    async def test_detects_daily_limit_in_body_text(self):
        """Detects 'daily limit' via body.innerText scan."""
        cg = _load_chatgpt()
        page = _make_page_mock(body_text="Your daily limit has been reached.")
        result = await cg.check_rate_limit(page)
        self.assertIsNotNone(result, "Should detect 'daily limit' in body text")

    async def test_detects_research_limit(self):
        """Detects 'research limit' pattern."""
        cg = _load_chatgpt()
        page = _make_page_mock(body_text="You have hit the research limit for this period.")
        result = await cg.check_rate_limit(page)
        self.assertIsNotNone(result, "Should detect 'research limit'")

    async def test_returns_none_when_no_rate_limit(self):
        """Returns None when no rate limit indicator is present."""
        cg = _load_chatgpt()
        page = _make_page_mock(
            visible_text="How can I help you today?",
            body_text="Welcome to ChatGPT. How can I help you today?",
        )
        result = await cg.check_rate_limit(page)
        self.assertIsNone(result, "Should return None when no rate limit present")


if __name__ == "__main__":
    unittest.main()
