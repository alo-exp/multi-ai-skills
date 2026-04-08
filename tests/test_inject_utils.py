"""Unit tests for InjectMixin (inject_utils.py)."""

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.conftest import install_stubs

PLATFORM_NAME = "test_platform"
PLATFORM_URL = "https://test.com"


def _load():
    install_stubs(PLATFORM_NAME, PLATFORM_URL)
    for mod in list(sys.modules):
        if "inject_utils" in mod:
            del sys.modules[mod]
    from platforms.inject_utils import InjectMixin
    return InjectMixin


def _make_page():
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=0)
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.wait_for_timeout = AsyncMock()

    def locator(sel):
        loc = MagicMock()
        loc.first = loc
        loc.click = AsyncMock()
        loc.type = AsyncMock()
        loc.fill = AsyncMock()
        loc.dispatch_event = AsyncMock()
        return loc
    page.locator = locator
    return page


class ConcreteInject:
    display_name = "Test"
    name = PLATFORM_NAME


class TestInjectExecCommand(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        InjectMixin = _load()

        class Mixin(ConcreteInject, InjectMixin):
            pass
        self.mixin = Mixin()

    async def test_inject_exec_command_success(self):
        """page.evaluate returns True then length >= 50% of prompt; returns length."""
        page = _make_page()
        prompt = "Hello World"
        expected_len = len(prompt)

        call_count = {"n": 0}

        async def _evaluate(expr, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return True   # execCommand succeeded
            return expected_len  # textContent.length
        page.evaluate = _evaluate

        result = await self.mixin._inject_exec_command(page, prompt)
        self.assertEqual(result, expected_len)

    async def test_inject_exec_command_fallback_to_clipboard_on_false(self):
        """page.evaluate returns False -> calls _inject_clipboard_paste."""
        page = _make_page()
        prompt = "test prompt"

        call_count = {"n": 0}

        async def _evaluate(expr, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return False   # execCommand failed
            return len(prompt)  # textContent.length
        page.evaluate = _evaluate

        clipboard_called = {"v": False}

        async def _clipboard(p, pr):
            clipboard_called["v"] = True
            return len(pr)
        self.mixin._inject_clipboard_paste = _clipboard

        result = await self.mixin._inject_exec_command(page, prompt)
        self.assertTrue(clipboard_called["v"])
        self.assertEqual(result, len(prompt))

    async def test_inject_exec_command_short_content_fallback(self):
        """page.evaluate returns True but length < 50% of prompt; clipboard fallback."""
        page = _make_page()
        prompt = "A" * 100

        call_count = {"n": 0}

        async def _evaluate(expr, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return True   # execCommand says OK
            return 10         # but only 10 chars injected (< 50% of 100)
        page.evaluate = _evaluate

        clipboard_called = {"v": False}

        async def _clipboard(p, pr):
            clipboard_called["v"] = True
            return len(pr)
        self.mixin._inject_clipboard_paste = _clipboard

        await self.mixin._inject_exec_command(page, prompt)
        self.assertTrue(clipboard_called["v"])


class TestInjectClipboardPaste(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        InjectMixin = _load()

        class Mixin(ConcreteInject, InjectMixin):
            pass
        self.mixin = Mixin()

    async def test_inject_clipboard_paste_darwin(self):
        """On darwin: uses pbcopy and clears clipboard after paste."""
        page = _make_page()
        page.evaluate = AsyncMock(return_value=None)
        page.keyboard.press = AsyncMock()
        page.wait_for_timeout = AsyncMock()

        async def _evaluate(expr, *args, **kwargs):
            return 50
        page.evaluate = _evaluate

        with patch("sys.platform", "darwin"), \
             patch("subprocess.run") as mock_run:
            result = await self.mixin._inject_clipboard_paste(page, "hello")
        # pbcopy for paste + pbcopy for clear
        calls = mock_run.call_args_list
        pbcopy_calls = [c for c in calls if c.args[0] == ["pbcopy"]]
        self.assertGreaterEqual(len(pbcopy_calls), 1)

    async def test_inject_clipboard_paste_linux(self):
        """On linux: uses xclip (first available) and clears clipboard."""
        page = _make_page()

        async def _evaluate(expr, *args, **kwargs):
            return 20
        page.evaluate = _evaluate

        with patch("sys.platform", "linux"), \
             patch("subprocess.run") as mock_run:
            result = await self.mixin._inject_clipboard_paste(page, "hello")
        calls = [c.args[0] for c in mock_run.call_args_list]
        xclip_calls = [c for c in calls if c and c[0] == "xclip"]
        self.assertTrue(len(xclip_calls) >= 1)

    async def test_inject_clipboard_paste_linux_no_tool(self):
        """On linux with all tools raising FileNotFoundError -> RuntimeError."""
        page = _make_page()

        import subprocess

        with patch("sys.platform", "linux"), \
             patch("subprocess.run", side_effect=FileNotFoundError("not found")):
            with self.assertRaises(RuntimeError):
                await self.mixin._inject_clipboard_paste(page, "hello")

    async def test_inject_clipboard_paste_win32(self):
        """On win32: uses clip with utf-16-le encoding."""
        page = _make_page()

        async def _evaluate(expr, *args, **kwargs):
            return 5
        page.evaluate = _evaluate

        with patch("sys.platform", "win32"), \
             patch("subprocess.run") as mock_run:
            result = await self.mixin._inject_clipboard_paste(page, "hello")
        calls = [c.args[0] for c in mock_run.call_args_list]
        clip_calls = [c for c in calls if c and c[0] == "clip"]
        self.assertTrue(len(clip_calls) >= 1)

    async def test_inject_clipboard_paste_linux_fallback_tools(self):
        """On linux, xclip fails but xsel succeeds."""
        page = _make_page()

        async def _evaluate(expr, *args, **kwargs):
            return 5
        page.evaluate = _evaluate

        import subprocess

        call_count = {"n": 0}

        def _run(cmd, **kwargs):
            call_count["n"] += 1
            if cmd[0] == "xclip":
                raise FileNotFoundError("xclip not found")
            return MagicMock()

        with patch("sys.platform", "linux"), \
             patch("subprocess.run", side_effect=_run):
            result = await self.mixin._inject_clipboard_paste(page, "hello")
        self.assertEqual(result, 5)

    async def test_inject_clipboard_paste_clear_exception_swallowed(self):
        """Exception during clipboard clear try block is swallowed (non-fatal)."""
        page = _make_page()

        async def _evaluate(expr, *args, **kwargs):
            return 5
        page.evaluate = _evaluate

        call_count = {"n": 0}

        def _run(cmd, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return MagicMock()   # paste succeeds
            raise RuntimeError("clear failed")  # clear raises

        with patch("sys.platform", "darwin"), \
             patch("subprocess.run", side_effect=_run):
            # Should not raise despite the clear failure
            result = await self.mixin._inject_clipboard_paste(page, "hello")
        self.assertEqual(result, 5)


class TestInjectPhysicalType(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        InjectMixin = _load()

        class Mixin(ConcreteInject, InjectMixin):
            pass
        self.mixin = Mixin()

    async def test_inject_physical_type(self):
        """Calls textarea.click() then textarea.type()."""
        page = _make_page()
        textarea = MagicMock()
        textarea.first = textarea
        textarea.click = AsyncMock()
        textarea.type = AsyncMock()
        page.locator = MagicMock(return_value=textarea)
        page.wait_for_timeout = AsyncMock()

        await self.mixin._inject_physical_type(page, "test prompt")
        textarea.click.assert_awaited_once()
        textarea.type.assert_awaited_once_with("test prompt", delay=5)


class TestInjectFill(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        InjectMixin = _load()

        class Mixin(ConcreteInject, InjectMixin):
            pass
        self.mixin = Mixin()

    async def test_inject_fill(self):
        """Calls textarea.fill() then dispatch_event('input')."""
        page = _make_page()
        textarea = MagicMock()
        textarea.first = textarea
        textarea.click = AsyncMock()
        textarea.fill = AsyncMock()
        textarea.dispatch_event = AsyncMock()
        page.locator = MagicMock(return_value=textarea)
        page.wait_for_timeout = AsyncMock()

        await self.mixin._inject_fill(page, "fill prompt")
        textarea.fill.assert_awaited_once_with("fill prompt")
        textarea.dispatch_event.assert_awaited_once_with("input")


if __name__ == "__main__":
    unittest.main()
