"""ChatGPT platform automation."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from .base import BasePlatform
from .chatgpt_extractor import ChatGPTExtractorMixin

log = logging.getLogger(__name__)


class ChatGPT(ChatGPTExtractorMixin, BasePlatform):
    name = "chatgpt"

    def __init__(self):
        super().__init__()
        self._no_stop_polls: int = 0
        self._seen_stop: bool = False
        self._mode: str = ""
        self._conversation_id: str = ""
        self._force_full_reload: bool = True

    async def check_rate_limit(self, page: Page) -> str | None:
        """Check for ChatGPT-specific rate limit indicators (DOM + body text scan)."""
        patterns = [
            "You've reached the current usage cap", "You've reached your limit",
            "usage cap", "limit reached", "reached your limit", "too many messages",
            "come back later", "upgrade your plan", "You're out of",
            "lighter version of deep research", "remaining queries are powered by",
            "full access resets on", "Your remaining queries",
            "daily limit", "monthly limit", "research limit",
        ]
        for pattern in patterns:
            try:
                el = page.get_by_text(pattern, exact=False).first
                if await el.count() > 0 and await el.is_visible():
                    return pattern
            except Exception:
                pass
        try:
            body_text = await page.evaluate("document.body.innerText")
            body_lower = body_text.lower()
            for pattern in patterns:
                if pattern.lower() in body_lower:
                    return pattern
        except Exception:
            pass
        return None

    async def configure_mode(self, page: Page, mode: str) -> str:
        """Enable Deep Research (DEEP) or select reasoning model (REGULAR)."""
        self._mode = mode
        if mode == "DEEP":
            try:
                plus_btn = page.locator('button[aria-label*="Attach"]').first
                if await plus_btn.count() == 0:
                    plus_btn = page.locator('button[aria-label*="Add"]').first
                if await plus_btn.count() > 0 and await plus_btn.is_visible():
                    await plus_btn.click()
                    await page.wait_for_timeout(500)
                    dr = page.get_by_text("Deep research", exact=False).first
                    if await dr.count() > 0:
                        await dr.click()
                        await page.wait_for_timeout(500)
                        log.info("[ChatGPT] Enabled Deep Research")
                        return "Deep Research"
            except Exception as exc:
                log.warning(f"[ChatGPT] Deep Research enablement failed: {exc}")
            return "Default (Deep Research failed)"
        else:
            try:
                model_btn = page.locator('button[aria-haspopup="menu"]:has-text("GPT"), button[aria-haspopup="menu"]:has-text("o")').first
                if await model_btn.count() > 0 and await model_btn.is_visible():
                    await model_btn.click()
                    await page.wait_for_timeout(500)
                    for model_name in ["o3", "o4-mini", "o4", "o3-mini"]:
                        opt = page.get_by_text(model_name, exact=False).first
                        if await opt.count() > 0:
                            await opt.click()
                            await page.wait_for_timeout(500)
                            log.info(f"[ChatGPT] Selected {model_name} model")
                            return model_name
            except Exception as exc:
                log.warning(f"[ChatGPT] Model selection failed: {exc}")
            return "Default"

    async def post_send(self, page: Page, mode: str) -> None:
        """Install blob interceptor for DEEP mode; capture conversation ID."""
        if mode == "DEEP":
            try:
                await page.evaluate("""(() => {
                    const origCreateObjectURL = URL.createObjectURL.bind(URL);
                    window.__capturedBlobs = [];
                    URL.createObjectURL = function(obj) {
                        try {
                            if (obj && typeof obj.size === 'number') {
                                const reader = new FileReader();
                                reader.onload = (e) => {
                                    window.__capturedBlobs.push({size: obj.size, type: obj.type || '', text: e.target.result});
                                };
                                reader.readAsText(obj);
                            }
                        } catch (captureErr) {}
                        try { return origCreateObjectURL(obj); } catch (e) { throw e; }
                    };
                })();""")
                log.info("[ChatGPT] Blob interceptor installed for Deep Research extraction")
            except Exception as exc:
                log.warning(f"[ChatGPT] Blob interceptor installation failed: {exc}")

        for _ in range(15):
            await page.wait_for_timeout(1000)
            url = page.url
            if "/c/" in url:
                conv_id = url.split("/c/")[-1].split("?")[0].split("#")[0]
                if conv_id:
                    self._conversation_id = conv_id
                    log.info(f"[ChatGPT] Captured conversation ID: {conv_id}")
                    break

    async def completion_check(self, page: Page) -> bool:
        """Multi-signal completion detection for both REGULAR and DEEP modes."""
        has_stop = False
        stop_selectors = [
            'button:has-text("Stop")', 'button:has-text("Cancel")',
            'button[aria-label*="Stop"]', 'button[aria-label*="stop"]',
            'button:has-text("Stop researching")', 'button[aria-label*="Stop researching"]',
            '[class*="deep-research"] button:has-text("Stop")',
            'button[aria-label*="Cancel"]', 'button[aria-label*="cancel"]',
            '[aria-label="Stop generating"]', '[data-testid*="stop"]',
        ]
        for sel in stop_selectors:
            try:
                stop = page.locator(sel).first
                if await stop.count() > 0 and await stop.is_visible():
                    has_stop = True
                    break
            except Exception:
                pass

        if not has_stop and self._mode == "DEEP":
            try:
                for prog_text in ["Searching the web", "Reading", "Analyzing", "Researching"]:
                    prog = page.get_by_text(prog_text, exact=False).first
                    if await prog.count() > 0 and await prog.is_visible():
                        has_stop = True
                        break
            except Exception:
                pass

        if has_stop:
            self._no_stop_polls = 0
            self._seen_stop = True
            return False

        self._no_stop_polls += 1

        if self._mode != "DEEP":
            try:
                articles = page.locator("article")
                count = await articles.count()
                if count >= 2:
                    resp_len = await articles.nth(count - 1).evaluate("el => el.innerText.length")
                    if resp_len > 2000:
                        return True
            except Exception:
                pass
            try:
                body_len = await page.evaluate("document.body.innerText.length")
                if body_len > 15000:
                    log.info(f"[ChatGPT] Body text {body_len} > 15000 — declaring complete")
                    return True
            except Exception:
                pass

        if self._mode == "DEEP":
            _DR_PAT = ["web-sandbox", "deep_research", "oaiusercontent.com", "blob:"]
            dr_frame_len = 0
            for _frame in reversed(page.frames):
                if _frame == page.main_frame or _frame.url in ("", "about:blank"):
                    continue
                if any(pat in _frame.url for pat in _DR_PAT):
                    try:
                        dr_frame_len = await _frame.evaluate("document.body.innerText.length")
                    except Exception:
                        pass
                    break
            if dr_frame_len > 20000:
                log.info(f"[ChatGPT] DEEP: DR iframe has {dr_frame_len} chars — declaring complete")
                return True
            if self._no_stop_polls >= 60:
                log.warning("[ChatGPT] DEEP: 60 polls without populated DR iframe — declaring complete")
                return True
        else:
            if self._no_stop_polls >= 3:
                log.info("[ChatGPT] No stop button for 3 polls — declaring complete")
                return True

        return False
