"""Browser utility mixin — popup dismissal, chat-ready, sign-in detection, navigation."""

from __future__ import annotations

import logging
from weakref import WeakSet

from playwright.async_api import Page

log = logging.getLogger(__name__)


class _SignInRequired(Exception):
    pass


class _RateLimited(Exception):
    pass


class BrowserMixin:
    """Mixin providing browser-state helpers for BasePlatform subclasses."""

    _dialog_registered_pages: WeakSet = WeakSet()

    def _setup_dialog_handler(self, page: Page) -> None:
        """Register a one-time-per-page handler that auto-accepts browser dialogs."""
        if page in BrowserMixin._dialog_registered_pages:
            return
        BrowserMixin._dialog_registered_pages.add(page)

        async def _accept_dialog(dialog) -> None:
            try:
                log.debug(f"[{self.display_name}] Auto-accepting dialog ({dialog.type}): {dialog.message[:80] if dialog.message else ''}")
                await dialog.accept()
            except Exception:
                pass

        page.on("dialog", _accept_dialog)

    @staticmethod
    async def dismiss_popups(page: Page) -> None:
        """Attempt to dismiss common CSS overlay popups."""
        scoped_selectors = [
            '[role="dialog"] button[aria-label*="Close"]', '[role="dialog"] button[aria-label*="close"]',
            '[role="dialog"] button[aria-label*="Dismiss"]', '[role="dialog"] button[aria-label*="dismiss"]',
            '[aria-modal="true"] button[aria-label*="Close"]', '[aria-modal="true"] button[aria-label*="close"]',
            '[aria-modal="true"] button[aria-label*="Dismiss"]', '[aria-modal="true"] button[aria-label*="dismiss"]',
            '[data-testid="close-button"]', '[data-testid="modal-close"]',
            '[class*="modal"] [class*="close"]', '[class*="dialog"] [class*="close"]',
            '[class*="overlay"] [class*="close"]', '[class*="popup"] [class*="close"]',
            '[class*="toast"] [class*="close"]',
        ]
        consent_selectors = [
            '[class*="cookie"] button:has-text("Accept")', '[class*="cookie"] button:has-text("OK")',
            '[class*="consent"] button:has-text("Accept")', '[class*="consent"] button:has-text("Agree")',
            '[class*="consent"] button:has-text("Got it")', '[class*="banner"] button:has-text("Accept")',
            '[class*="banner"] button:has-text("Got it")', '[class*="banner"] button:has-text("Dismiss")',
            '[class*="banner"] [class*="close"]', '[id*="cookie"] button', '[id*="consent"] button',
        ]
        dismissed_count = 0
        for selector in scoped_selectors + consent_selectors:
            if dismissed_count >= 3:
                break
            try:
                el = page.locator(selector).first
                if await el.count() > 0 and await el.is_visible(timeout=500):
                    await el.click(timeout=1000)
                    await page.wait_for_timeout(300)
                    log.debug(f"Dismissed popup via: {selector}")
                    dismissed_count += 1
            except Exception:
                pass

    async def is_chat_ready(self, page: Page) -> bool:
        """Return True if the chat UI is in the expected ready state."""
        if await self.is_sign_in_page(page):
            return False
        url = page.url.lower()
        if url in ("about:blank", "chrome://newtab/", ""):
            return False
        try:
            title = (await page.title()).lower()
            error_patterns = ["404", "not found", "500", "internal server error",
                              "502", "bad gateway", "503", "service unavailable", "access denied", "forbidden"]
            if any(p in title for p in error_patterns):
                return False
        except Exception:
            pass
        return True

    async def is_sign_in_page(self, page: Page) -> bool:
        """Return True if the current page is a sign-in / login page."""
        url = page.url.lower()
        if any(f in url for f in ["/login", "/signin", "/sign-in", "/auth",
                                   "accounts.google.com", "login.microsoftonline.com", "auth.openai.com"]):
            return True
        try:
            pw = page.locator('input[type="password"]').first
            if await pw.count() > 0 and await pw.is_visible(timeout=2000):
                return True
        except Exception:
            pass
        return False

    async def _navigate_and_configure(self, page: Page, mode: str) -> str:
        """Navigate to the platform URL, dismiss popups, check state, configure mode."""
        log.info(f"[{self.display_name}] Navigating to {self.url}")
        if getattr(self, "_force_full_reload", False):
            try:
                await page.goto("about:blank", wait_until="commit", timeout=5000)
                await page.wait_for_timeout(300)
            except Exception:
                pass

        nav_exc: Exception | None = None
        for attempt in range(2):
            try:
                await page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
                nav_exc = None
                break
            except Exception as exc:
                nav_exc = exc
                if attempt == 0:
                    log.warning(f"[{self.display_name}] Navigation attempt 1 failed, retrying in 3s")
                    await page.wait_for_timeout(3000)
        if nav_exc is not None:
            try:
                await self._agent_fallback(page, "navigate", nav_exc,
                    f"Navigate to {self.url} and wait for {self.display_name} to load.")
            except Exception:
                raise RuntimeError(f"Navigation failed: {nav_exc}") from nav_exc
        await page.wait_for_timeout(3000)
        await self.dismiss_popups(page)

        if await self.is_sign_in_page(page):
            print(f"\n  [{self.display_name}] Sign-in required — please log in at: {self.url}", flush=True)
            try:
                await self._agent_fallback(page, "navigate", RuntimeError("Sign-in page visible"),
                    f"On {self.display_name}: navigate to {self.url} and confirm the chat UI is visible.")
                await page.wait_for_timeout(2000)
            except Exception:
                pass
            if await self.is_sign_in_page(page):
                raise _SignInRequired("Sign-in required")

        rate_msg = await self.check_rate_limit(page)
        if rate_msg:
            raise _RateLimited(rate_msg)

        if not await self.is_chat_ready(page):
            log.warning(f"[{self.display_name}] Chat UI not ready — triggering agent takeover")
            try:
                await self._agent_fallback(page, "navigate", RuntimeError("Chat UI not ready"),
                    f"On {self.display_name}: navigate to {self.url}, dismiss popups, confirm chat input visible.")
                await page.wait_for_timeout(2000)
                await self.dismiss_popups(page)
            except Exception as exc:
                log.warning(f"[{self.display_name}] Agent could not recover UI: {exc}")

        log.info(f"[{self.display_name}] Configuring mode: {mode}")
        try:
            mode_label = await self.configure_mode(page, mode)
        except Exception as exc:
            try:
                await self._agent_fallback(page, "configure_mode", exc,
                    f"On {self.display_name}: configure the AI model for {mode} mode.")
            except Exception:
                log.warning(f"[{self.display_name}] configure_mode failed, continuing: {exc}")
            mode_label = "Agent-configured"
        await self.dismiss_popups(page)
        return mode_label
