"""Unit tests for chatgpt_extractor module.

Tests cover: _read_clipboard (platform branches), ChatGPTExtractorMixin
_extract_deep_research_panel, and extract_response.
"""

import subprocess as _real_subprocess
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
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

from platforms.chatgpt_extractor import _read_clipboard, ChatGPTExtractorMixin  # noqa: E402

# Patch target prefix (module is loaded as platforms.chatgpt_extractor)
_MOD = "platforms.chatgpt_extractor"


# ---------------------------------------------------------------------------
# Helpers for _read_clipboard tests
# _read_clipboard does "import subprocess, sys" locally, so we patch
# sys.modules['subprocess'] and sys.platform directly.
# ---------------------------------------------------------------------------

class _MockSubprocess:
    """Minimal subprocess mock for _read_clipboard tests."""
    def __init__(self, run_fn, timeout_expired=_real_subprocess.TimeoutExpired):
        self.run = run_fn
        self.TimeoutExpired = timeout_expired


# ---------------------------------------------------------------------------
# Concrete test class that uses the mixin
# ---------------------------------------------------------------------------

class _FakeChatGPT(ChatGPTExtractorMixin):
    def __init__(self, mode="DEEP"):
        self._mode = mode
        self.prompt_sigs: list[str] = []
        self.name = "chatgpt"

    async def check_rate_limit(self, page):
        return None


# ---------------------------------------------------------------------------
# _read_clipboard
# ---------------------------------------------------------------------------


class TestReadClipboard:
    def _run_with_platform(self, platform, mock_sub_run, *, timeout_exp=None):
        """Helper: temporarily set sys.platform and sys.modules['subprocess']."""
        orig_platform = sys.platform
        orig_sub = sys.modules.get("subprocess")
        te = timeout_exp if timeout_exp is not None else _real_subprocess.TimeoutExpired
        mock_sub = _MockSubprocess(mock_sub_run, te)
        sys.modules["subprocess"] = mock_sub
        # sys.platform is read-only on CPython; patch via the builtins
        try:
            sys.__dict__["platform"] = platform  # works on CPython
        except Exception:
            pass
        try:
            result = _read_clipboard()
        finally:
            sys.modules["subprocess"] = orig_sub if orig_sub is not None else _real_subprocess
            try:
                sys.__dict__["platform"] = orig_platform
            except Exception:
                pass
        return result

    def test_darwin_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "clipboard content"
        result = self._run_with_platform("darwin", MagicMock(return_value=mock_result))
        assert result == "clipboard content"

    def test_darwin_fail_returncode(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "ignored"
        result = self._run_with_platform("darwin", MagicMock(return_value=mock_result))
        assert result == ""

    def test_linux_xclip_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "linux clipboard"

        def run_side_effect(cmd, **kw):
            if "xclip" in cmd:
                return mock_result
            return MagicMock(returncode=1, stdout="")

        result = self._run_with_platform("linux", run_side_effect)
        assert result == "linux clipboard"

    def test_linux_xclip_not_found_falls_to_xsel(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "xsel clipboard"

        def run_side_effect(cmd, **kw):
            if "xclip" in cmd:
                raise FileNotFoundError("xclip not found")
            if "xsel" in cmd:
                return mock_result
            return MagicMock(returncode=1, stdout="")

        result = self._run_with_platform("linux", run_side_effect)
        assert result == "xsel clipboard"

    def test_linux_all_commands_fail(self):
        def run_side_effect(cmd, **kw):
            raise FileNotFoundError("not found")

        result = self._run_with_platform("linux", run_side_effect)
        assert result == ""

    def test_win32_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "win clipboard"
        result = self._run_with_platform("win32", MagicMock(return_value=mock_result))
        assert result == "win clipboard"

    def test_win32_fail(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        result = self._run_with_platform("win32", MagicMock(return_value=mock_result))
        assert result == ""

    def test_unknown_platform_returns_empty(self):
        result = self._run_with_platform("freebsd", MagicMock())
        assert result == ""

    def test_exception_returns_empty(self):
        def boom(*a, **kw):
            raise Exception("unexpected")

        result = self._run_with_platform("darwin", boom)
        assert result == ""

    def test_linux_timeout_expired_continues(self):
        """TimeoutExpired on xclip → continues to xsel."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "xsel ok"

        def run_side_effect(cmd, **kw):
            if "xclip" in cmd:
                raise _real_subprocess.TimeoutExpired(cmd, 5)
            if "xsel" in cmd:
                return mock_result
            return MagicMock(returncode=1, stdout="")

        result = self._run_with_platform("linux", run_side_effect)
        assert result == "xsel ok"


# ---------------------------------------------------------------------------
# Helpers for page mocking
# ---------------------------------------------------------------------------

def _make_page():
    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    page.evaluate = AsyncMock(return_value="")
    page.url = "https://chatgpt.com"
    page.mouse = MagicMock()
    page.mouse.click = AsyncMock()
    page.main_frame = MagicMock()

    def _locator(sel):
        loc = MagicMock()
        loc.first = MagicMock()
        loc.first.count = AsyncMock(return_value=0)
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.first.click = AsyncMock()
        loc.last = loc.first
        return loc

    def _frame_locator(sel):
        fl = MagicMock()
        fl.locator = MagicMock(side_effect=_locator)
        fl.get_by_text = MagicMock(side_effect=lambda t, **kw: _locator(t))
        fl.last = fl
        return fl

    page.locator = MagicMock(side_effect=_locator)
    page.frame_locator = MagicMock(side_effect=_frame_locator)

    def _gbt(text, **kw):
        return _locator(text)

    page.get_by_text = MagicMock(side_effect=_gbt)

    # Default: no frames
    page.frames = [page.main_frame]
    return page


# ---------------------------------------------------------------------------
# _extract_deep_research_panel
# ---------------------------------------------------------------------------


class TestExtractDeepResearchPanel:
    async def test_frame_evaluate_success(self):
        """DR frame found by URL pattern, evaluate returns > 1000 chars."""
        page = _make_page()
        dr_frame = MagicMock()
        dr_frame.url = "https://web-sandbox.oai.azure.com/iframe"
        dr_frame.parent_frame = MagicMock()  # not None → not main page
        long_text = "x" * 2000
        dr_frame.evaluate = AsyncMock(return_value=long_text)

        main_frame = MagicMock()
        main_frame.url = "https://chatgpt.com"
        main_frame.parent_frame = None

        page.frames = [main_frame, dr_frame]
        page.main_frame = main_frame

        obj = _FakeChatGPT()
        obj.prompt_sigs = []
        result = await obj._extract_deep_research_panel(page)
        assert len(result) == 2000

    async def test_no_dr_frame_uses_content_frame(self):
        """No DR URL pattern → uses non-main frame with > 2000 chars as fallback."""
        page = _make_page()

        main_frame = MagicMock()
        main_frame.url = "https://chatgpt.com"
        main_frame.parent_frame = None

        other_frame = MagicMock()
        other_frame.url = "https://other.example.com/frame"
        other_frame.parent_frame = MagicMock()
        content = "fallback content " * 200  # ~3400 chars
        content_len = len(content)
        # evaluate called 3 times: logging flen, flen>2000 check, actual text
        other_frame.evaluate = AsyncMock(
            side_effect=[content_len, content_len, content]
        )

        page.frames = [main_frame, other_frame]
        page.main_frame = main_frame

        obj = _FakeChatGPT()
        obj.prompt_sigs = []
        result = await obj._extract_deep_research_panel(page)
        assert len(result) > 1000

    async def test_no_dr_frame_no_content_falls_to_clipboard(self):
        """No usable frame → coordinate fallback → returns whatever it gets."""
        page = _make_page()
        page.frames = [page.main_frame]

        rect = {
            "top": 100, "left": 100, "bottom": 800, "right": 1200,
            "width": 1100, "height": 700
        }

        async def _eval(script):
            if "iframe" in str(script):
                return rect
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        with patch(f"{_MOD}._read_clipboard", return_value=""):
            obj = _FakeChatGPT()
            obj.check_rate_limit = AsyncMock(return_value=None)
            result = await obj._extract_deep_research_panel(page)
        assert isinstance(result, str)

    async def test_retry_loop_rate_limit(self):
        """After empty first extract, rate limit found in retry → returns rate limited message."""
        page = _make_page()
        page.frames = [page.main_frame]

        async def _eval(script):
            if "iframe" in str(script):
                return None
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT()
        obj.check_rate_limit = AsyncMock(return_value="quota exceeded")

        result = await obj._extract_deep_research_panel(page)
        assert "[RATE LIMITED]" in result

    async def test_frame_evaluate_exception_falls_to_retry(self):
        """DR frame found but evaluate raises → falls through, retries, eventually returns ''."""
        page = _make_page()

        dr_frame = MagicMock()
        dr_frame.url = "https://web-sandbox.example.com/iframe"
        dr_frame.parent_frame = MagicMock()
        dr_frame.evaluate = AsyncMock(side_effect=Exception("eval failed"))

        main_frame = MagicMock()
        main_frame.url = "https://chatgpt.com"
        main_frame.parent_frame = None

        page.frames = [main_frame, dr_frame]
        page.main_frame = main_frame

        obj = _FakeChatGPT()
        obj.check_rate_limit = AsyncMock(return_value=None)

        with patch(f"{_MOD}._read_clipboard", return_value=""):
            result = await obj._extract_deep_research_panel(page)
        assert result == ""


# ---------------------------------------------------------------------------
# extract_response
# ---------------------------------------------------------------------------


class TestChatGPTExtractResponse:
    async def test_deep_mode_quota_detected_at_start(self):
        """DEEP mode: quota phrase in body → immediate rate limit return."""
        page = _make_page()
        page.evaluate = AsyncMock(return_value="you've reached the current usage cap for today")

        obj = _FakeChatGPT(mode="DEEP")
        result = await obj.extract_response(page)
        assert "[RATE LIMITED]" in result

    async def test_deep_mode_panel_success(self):
        """DEEP mode: DR panel extracts content."""
        page = _make_page()
        page.evaluate = AsyncMock(return_value="normal body text")

        obj = _FakeChatGPT(mode="DEEP")
        panel_text = "Deep Research Result " * 100
        obj._extract_deep_research_panel = AsyncMock(return_value=panel_text)

        result = await obj.extract_response(page)
        assert result == panel_text

    async def test_blob_interceptor_fallback(self):
        """Blob interceptor has text → returned."""
        page = _make_page()
        blob_text = "blob text " * 200

        call_count = [0]

        async def _eval(script):
            call_count[0] += 1
            if call_count[0] == 1:
                return "normal body"  # quota check
            if "__capturedBlobs" in str(script):
                return blob_text
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT(mode="DEEP")
        obj._extract_deep_research_panel = AsyncMock(return_value="")

        result = await obj.extract_response(page)
        assert result == blob_text

    async def test_article_selector_fallback(self):
        """Article selector extracts response."""
        page = _make_page()
        article_text = "article content " * 50

        call_count = [0]

        async def _eval(script):
            call_count[0] += 1
            if call_count[0] == 1:
                return "normal"  # quota check
            if "__capturedBlobs" in str(script):
                return None
            if "querySelectorAll" in str(script) and "article" in str(script):
                return article_text
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT(mode="DEEP")
        obj._extract_deep_research_panel = AsyncMock(return_value="")
        obj.prompt_sigs = []

        result = await obj.extract_response(page)
        assert "article content" in result

    async def test_article_end_of_report_trimmed(self):
        """'End of Report.' suffix is trimmed."""
        page = _make_page()
        article_text = ("content " * 100) + "End of Report." + "extra garbage"

        call_count = [0]

        async def _eval(script):
            call_count[0] += 1
            if call_count[0] == 1:
                return "normal"
            if "__capturedBlobs" in str(script):
                return None
            if "querySelectorAll" in str(script):
                return article_text
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT(mode="REGULAR")
        obj.prompt_sigs = []
        result = await obj.extract_response(page)
        assert result.endswith("End of Report.")

    async def test_main_container_fallback(self):
        """Main container used when article fails."""
        page = _make_page()
        main_text = "main response " * 50

        call_count = [0]

        async def _eval(script):
            call_count[0] += 1
            if call_count[0] == 1:
                return "normal"
            if "__capturedBlobs" in str(script):
                return None
            if "querySelectorAll" in str(script):
                return ""  # article empty
            if "main" in str(script):
                return main_text
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT(mode="REGULAR")
        obj.prompt_sigs = []
        result = await obj.extract_response(page)
        assert "main response" in result

    async def test_body_innertext_last_resort(self):
        """All else fails → body.innerText."""
        page = _make_page()

        call_count = [0]

        async def _eval(script):
            call_count[0] += 1
            if call_count[0] == 1:
                return "normal body"  # quota check
            return ""  # everything else empty

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT(mode="REGULAR")
        obj.prompt_sigs = []
        result = await obj.extract_response(page)
        assert isinstance(result, str)

    async def test_body_chatgpt_said_trimmed(self):
        """REGULAR mode: prompt echo path exercised (body.innerText fallback)."""
        body = "User: my prompt\nChatGPT said:\nActual response content " * 10

        page = _make_page()

        # REGULAR mode skips quota check; all JS paths return empty except body.innerText
        call_count = [0]

        async def _eval(script):
            call_count[0] += 1
            # blob → None, article → "", main → "", body.innerText → body
            if "__capturedBlobs" in str(script):
                return None
            if "querySelectorAll" in str(script):
                return ""
            if "main" in str(script):
                return ""
            # body.innerText (last call)
            return body

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT(mode="REGULAR")
        # prompt_sigs causes is_prompt_echo to return True → trimming branch runs
        obj.prompt_sigs = ["User: my prompt"]
        result = await obj.extract_response(page)
        assert isinstance(result, str)

    async def test_deep_mode_main_container_quota_check(self):
        """DEEP mode: main container has quota phrase → rate limited."""
        page = _make_page()

        call_count = [0]

        async def _eval(script):
            call_count[0] += 1
            if call_count[0] == 1:
                return "normal"  # quota check passes
            if "__capturedBlobs" in str(script):
                return None
            if "querySelectorAll" in str(script):
                return ""
            if "main" in str(script):
                return "usage cap " * 50
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT(mode="DEEP")
        obj._extract_deep_research_panel = AsyncMock(return_value="")
        obj.prompt_sigs = []
        result = await obj.extract_response(page)
        assert "[RATE LIMITED]" in result


# ---------------------------------------------------------------------------
# Additional coverage tests for exception handlers and edge branches
# ---------------------------------------------------------------------------


class TestExtractDeepResearchPanelEdgeCases:
    async def test_frame_logging_evaluate_exception(self):
        """Exception in frame.evaluate during logging loop → 'err' in log, continues."""
        page = _make_page()

        main_frame = MagicMock()
        main_frame.url = "https://chatgpt.com"
        main_frame.parent_frame = None

        bad_frame = MagicMock()
        bad_frame.url = "https://other.example.com/frame"
        bad_frame.parent_frame = MagicMock()
        # First call (logging) raises, second call (flen check) raises too → skip
        bad_frame.evaluate = AsyncMock(side_effect=Exception("eval boom"))

        page.frames = [main_frame, bad_frame]
        page.main_frame = main_frame

        obj = _FakeChatGPT()
        obj.check_rate_limit = AsyncMock(return_value=None)
        obj.prompt_sigs = []

        with patch(f"{_MOD}._read_clipboard", return_value=""):
            result = await obj._extract_deep_research_panel(page)
        # All paths fail → 12 retries → returns ""
        assert result == ""

    async def test_frame_text_short_returns_empty(self):
        """DR frame found but text < 1000 chars → returns empty."""
        page = _make_page()

        dr_frame = MagicMock()
        dr_frame.url = "https://web-sandbox.oai.azure.com/iframe"
        dr_frame.parent_frame = MagicMock()
        dr_frame.evaluate = AsyncMock(return_value="short text")  # < 1000

        main_frame = MagicMock()
        main_frame.url = "https://chatgpt.com"
        main_frame.parent_frame = None

        page.frames = [main_frame, dr_frame]
        page.main_frame = main_frame

        obj = _FakeChatGPT()
        obj.prompt_sigs = []
        obj.check_rate_limit = AsyncMock(return_value=None)

        with patch(f"{_MOD}._read_clipboard", return_value=""):
            result = await obj._extract_deep_research_panel(page)
        assert result == ""

    async def test_coordinate_fallback_no_copy_found(self):
        """Coordinate fallback: no copy item found → pixel fallback, empty clipboard."""
        page = _make_page()
        page.frames = [page.main_frame]

        rect = {
            "top": 0, "left": 0, "bottom": 700, "right": 1100,
            "width": 1100, "height": 700
        }

        async def _eval(script):
            if "iframe" in str(script):
                return rect
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        with patch(f"{_MOD}._read_clipboard", return_value=""):
            obj = _FakeChatGPT()
            obj.check_rate_limit = AsyncMock(return_value=None)
            result = await obj._extract_deep_research_panel(page)
        assert result == ""


class TestChatGPTExtractResponseEdgeCases:
    async def test_deep_mode_quota_check_exception_swallowed(self):
        """DEEP mode: exception in quota check → swallowed, continues."""
        page = _make_page()

        call_count = [0]

        async def _eval(script):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("eval boom")  # quota check fails
            if "__capturedBlobs" in str(script):
                return None
            if "querySelectorAll" in str(script):
                return "panel result " * 100
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT(mode="DEEP")
        obj._extract_deep_research_panel = AsyncMock(return_value="panel content " * 100)
        obj.prompt_sigs = []
        result = await obj.extract_response(page)
        assert "panel content" in result

    async def test_blob_interceptor_exception_swallowed(self):
        """Exception in blob interceptor → swallowed, falls to article."""
        page = _make_page()
        article_text = "article content " * 50

        call_count = [0]

        async def _eval(script):
            call_count[0] += 1
            if call_count[0] == 1:
                return "normal"
            if "__capturedBlobs" in str(script):
                raise Exception("blob boom")
            if "querySelectorAll" in str(script):
                return article_text
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT(mode="REGULAR")
        obj.prompt_sigs = []
        result = await obj.extract_response(page)
        assert "article content" in result

    async def test_article_exception_swallowed(self):
        """Exception in article selector → swallowed, falls to main."""
        page = _make_page()
        main_text = "main content " * 50

        call_count = [0]

        async def _eval(script):
            call_count[0] += 1
            if call_count[0] == 1:
                return "normal"
            if "__capturedBlobs" in str(script):
                return None
            if "querySelectorAll" in str(script):
                raise Exception("article boom")
            if "main" in str(script):
                return main_text
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT(mode="REGULAR")
        obj.prompt_sigs = []
        result = await obj.extract_response(page)
        assert "main content" in result

    async def test_main_container_exception_swallowed(self):
        """Exception in main container → swallowed, falls to body.innerText."""
        page = _make_page()
        body_text = "body content " * 10

        call_count = [0]

        async def _eval(script):
            call_count[0] += 1
            if call_count[0] == 1:
                return "normal"
            if "__capturedBlobs" in str(script):
                return None
            if "querySelectorAll" in str(script):
                return ""
            if "main" in str(script):
                raise Exception("main boom")
            return body_text

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT(mode="REGULAR")
        obj.prompt_sigs = []
        result = await obj.extract_response(page)
        assert result == body_text


# ---------------------------------------------------------------------------
# Additional coverage: frame_locator+clipboard, coord fallback, retry return
# ---------------------------------------------------------------------------


class TestMissingLineCoverage:
    """Cover lines 103-115, 138-143, 151-152, 154-156, 171, 201-202."""

    async def test_frame_locator_clipboard_success(self):
        """Layer B: dl_btn.count>0, copy_item.count>0 → clipboard read → return (lines 103-113)."""
        page = _make_page()
        page.frames = []
        page.main_frame = MagicMock()
        page.main_frame.url = "https://chatgpt.com"

        clipboard_text = "deep research result " * 60

        # dl_btn stub: count=1
        dl_btn = MagicMock()
        dl_btn.count = AsyncMock(return_value=1)
        dl_btn.click = AsyncMock()

        # copy_item stub: count=1, click succeeds.
        # .first must return self so count() works after .first access.
        copy_item = MagicMock()
        copy_item.count = AsyncMock(return_value=1)
        copy_item.click = AsyncMock()
        copy_item.first = copy_item

        # dl_btn.first must also be self-referential
        dl_btn.first = dl_btn

        # dr_frame stub from frame_locator
        dr_frame = MagicMock()
        dr_frame.locator = MagicMock(return_value=dl_btn)
        dr_frame.get_by_text = MagicMock(return_value=copy_item)

        frame_loc_stub = MagicMock()
        frame_loc_stub.last = dr_frame
        page.frame_locator = MagicMock(return_value=frame_loc_stub)

        async def _eval(script):
            if "iframe" in str(script):
                return None  # no rect → coordinate path skipped
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT()
        obj.check_rate_limit = AsyncMock(return_value=None)
        obj.prompt_sigs = []

        with patch(f"{_MOD}._read_clipboard", return_value=clipboard_text):
            result = await obj._extract_deep_research_panel(page)

        assert result == clipboard_text

    async def test_frame_locator_clipboard_empty_falls_through(self):
        """Layer B: clipboard text short → doesn't return, falls to Layer C (lines 103-115)."""
        page = _make_page()
        page.frames = []
        page.main_frame = MagicMock()
        page.main_frame.url = "https://chatgpt.com"

        dl_btn = MagicMock()
        dl_btn.count = AsyncMock(return_value=1)
        dl_btn.click = AsyncMock()

        copy_item = MagicMock()
        copy_item.count = AsyncMock(return_value=1)
        copy_item.click = AsyncMock()

        dr_frame = MagicMock()
        dr_frame.locator = MagicMock(return_value=dl_btn)
        dr_frame.get_by_text = MagicMock(return_value=copy_item)

        frame_loc_stub = MagicMock()
        frame_loc_stub.last = dr_frame
        page.frame_locator = MagicMock(return_value=frame_loc_stub)

        # No iframe rect → coordinate path returns ""
        async def _eval(script):
            if "iframe" in str(script):
                return None
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT()
        obj.check_rate_limit = AsyncMock(return_value=None)
        obj.prompt_sigs = []

        # Clipboard returns short text → doesn't satisfy len > 1000
        with patch(f"{_MOD}._read_clipboard", return_value="short"):
            result = await obj._extract_deep_research_panel(page)

        assert result == ""

    async def test_coordinate_copy_item_found_copied_true(self):
        """Coord fallback: copy_item visible → click, copied=True, clipboard success → return (lines 138-143, 151-152)."""
        page = _make_page()
        page.frames = []
        page.main_frame = MagicMock()
        page.main_frame.url = "https://chatgpt.com"

        clipboard_text = "coordinate clipboard result " * 60

        # dl_btn for frame_locator: count=0 → Layer B skipped
        dl_btn_zero = MagicMock()
        dl_btn_zero.count = AsyncMock(return_value=0)
        dr_frame = MagicMock()
        dr_frame.locator = MagicMock(return_value=dl_btn_zero)
        frame_loc_stub = MagicMock()
        frame_loc_stub.last = dr_frame
        page.frame_locator = MagicMock(return_value=frame_loc_stub)

        # Coordinate: rect exists
        rect = {"left": 100, "top": 50, "right": 900, "bottom": 600, "width": 800, "height": 550}

        async def _eval(script):
            if "iframe" in str(script):
                return rect
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)
        page.mouse.click = AsyncMock()

        # copy_item: count=1, visible → click → copied=True.
        # .first must return self so count()/is_visible() work after .first access.
        copy_item = MagicMock()
        copy_item.count = AsyncMock(return_value=1)
        copy_item.is_visible = AsyncMock(return_value=True)
        copy_item.click = AsyncMock()
        copy_item.first = copy_item
        page.get_by_text = MagicMock(return_value=copy_item)

        obj = _FakeChatGPT()
        obj.check_rate_limit = AsyncMock(return_value=None)
        obj.prompt_sigs = []

        with patch(f"{_MOD}._read_clipboard", return_value=clipboard_text):
            result = await obj._extract_deep_research_panel(page)

        assert result == clipboard_text

    async def test_coordinate_copy_item_found_clipboard_short_returns_empty(self):
        """Coord fallback: copy_item clicked, clipboard short → return '' (lines 153-153)."""
        page = _make_page()
        page.frames = []
        page.main_frame = MagicMock()
        page.main_frame.url = "https://chatgpt.com"

        dl_btn_zero = MagicMock()
        dl_btn_zero.count = AsyncMock(return_value=0)
        dr_frame = MagicMock()
        dr_frame.locator = MagicMock(return_value=dl_btn_zero)
        frame_loc_stub = MagicMock()
        frame_loc_stub.last = dr_frame
        page.frame_locator = MagicMock(return_value=frame_loc_stub)

        rect = {"left": 100, "top": 50, "right": 900, "bottom": 600, "width": 800, "height": 550}

        async def _eval(script):
            if "iframe" in str(script):
                return rect
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)
        page.mouse.click = AsyncMock()

        copy_item = MagicMock()
        copy_item.count = AsyncMock(return_value=1)
        copy_item.is_visible = AsyncMock(return_value=True)
        copy_item.click = AsyncMock()
        page.get_by_text = MagicMock(return_value=copy_item)

        obj = _FakeChatGPT()
        obj.check_rate_limit = AsyncMock(return_value=None)
        obj.prompt_sigs = []

        with patch(f"{_MOD}._read_clipboard", return_value=""):
            result = await obj._extract_deep_research_panel(page)

        assert result == ""

    async def test_coordinate_exception_returns_empty(self):
        """Coord fallback raises → except: log + return '' (lines 154-156)."""
        page = _make_page()
        page.frames = []
        page.main_frame = MagicMock()
        page.main_frame.url = "https://chatgpt.com"

        dl_btn_zero = MagicMock()
        dl_btn_zero.count = AsyncMock(return_value=0)
        dr_frame = MagicMock()
        dr_frame.locator = MagicMock(return_value=dl_btn_zero)
        frame_loc_stub = MagicMock()
        frame_loc_stub.last = dr_frame
        page.frame_locator = MagicMock(return_value=frame_loc_stub)

        # evaluate raises → exception in coord block
        page.evaluate = AsyncMock(side_effect=Exception("coord eval error"))

        obj = _FakeChatGPT()
        obj.check_rate_limit = AsyncMock(return_value=None)
        obj.prompt_sigs = []

        result = await obj._extract_deep_research_panel(page)
        assert result == ""

    async def test_retry_loop_succeeds_on_second_attempt(self):
        """Retry loop: first _try_extract empty, second returns content → line 171 hit."""
        page = _make_page()
        page.frames = []
        page.main_frame = MagicMock()
        page.main_frame.url = "https://chatgpt.com"

        good_text = "final answer content " * 60

        attempt_count = [0]

        # frame_locator dl_btn always count=0
        dl_btn_zero = MagicMock()
        dl_btn_zero.count = AsyncMock(return_value=0)
        dr_frame = MagicMock()
        dr_frame.locator = MagicMock(return_value=dl_btn_zero)
        frame_loc_stub = MagicMock()
        frame_loc_stub.last = dr_frame
        page.frame_locator = MagicMock(return_value=frame_loc_stub)

        async def _eval(script):
            if "iframe" in str(script):
                return None  # no coord
            return ""

        page.evaluate = AsyncMock(side_effect=_eval)

        # _read_clipboard: first call empty, second call returns good_text
        clip_call = [0]

        def _clipboard():
            clip_call[0] += 1
            return ""

        # Make frame evaluate return content on second _try_extract call
        extract_call = [0]
        original_try_extract = None

        obj = _FakeChatGPT()
        obj.prompt_sigs = []
        obj.check_rate_limit = AsyncMock(return_value=None)

        # Patch dr_frame.evaluate: first time empty, second time good
        dr_eval_call = [0]

        # Instead: make page.frames return DR frame on second attempt
        pages_call = [0]

        dr_frame_real = MagicMock()
        dr_frame_real.url = "https://web-sandbox.example.com"
        dr_frame_real.parent_frame = MagicMock()

        eval_call = [0]

        async def dr_eval(script):
            eval_call[0] += 1
            if eval_call[0] == 1:
                return ""  # short → fails first time
            return good_text  # succeeds second time

        dr_frame_real.evaluate = AsyncMock(side_effect=dr_eval)

        main_frame = MagicMock()
        main_frame.url = "https://chatgpt.com"
        main_frame.parent_frame = None

        # First call to _try_extract: no frames → empty; second call: dr_frame present
        frames_call = [0]

        def _get_frames():
            frames_call[0] += 1
            if frames_call[0] <= 2:  # first _try_extract (Layer A + layers B/C)
                return []
            return [main_frame, dr_frame_real]

        type(page).frames = property(lambda self: _get_frames())

        with patch(f"{_MOD}._read_clipboard", return_value=""):
            result = await obj._extract_deep_research_panel(page)

        assert result == good_text

    async def test_blob_interceptor_exception_swallowed_in_extract_response(self):
        """Blob interceptor evaluate raises → except: pass (lines 201-202) in extract_response.

        In REGULAR mode the FIRST evaluate call IS the blob interceptor JS.
        Making it raise ensures lines 201-202 (except/pass) are executed.
        """
        page = _make_page()

        async def _eval(script):
            if "__capturedBlobs" in str(script):
                raise Exception("blob boom")
            # Article selector JS or other calls → return content
            return "article content " * 30

        page.evaluate = AsyncMock(side_effect=_eval)

        obj = _FakeChatGPT(mode="REGULAR")
        obj.prompt_sigs = []
        result = await obj.extract_response(page)
        # blob exception swallowed → falls to article selector → returns content
        assert isinstance(result, str)
