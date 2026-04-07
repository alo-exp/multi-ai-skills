"""Base class for all platform automation modules."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import Page

from config import (
    INJECTION_METHODS, PLATFORM_DISPLAY_NAMES, PLATFORM_URLS,
    POLL_INTERVAL, STATUS_COMPLETE, STATUS_FAILED, STATUS_NEEDS_LOGIN,
    STATUS_PARTIAL, STATUS_RATE_LIMITED, STATUS_TIMEOUT, TIMEOUTS,
)
from .browser_utils import BrowserMixin, _SignInRequired, _RateLimited
from .inject_utils import InjectMixin

log = logging.getLogger(__name__)


@dataclass
class PlatformResult:
    """Result returned by each platform run."""
    platform: str
    display_name: str
    status: str
    chars: int = 0
    file: str = ""
    mode_used: str = ""
    error: str = ""
    duration_s: float = 0.0


class BasePlatform(InjectMixin, BrowserMixin):
    """Base class for platform automation. Subclasses must implement configure_mode,
    completion_check, and extract_response."""

    name: str = ""
    url: str = ""
    display_name: str = ""

    def __init__(self):
        self.url = PLATFORM_URLS.get(self.name, "")
        self.display_name = PLATFORM_DISPLAY_NAMES.get(self.name, self.name)
        self.agent_manager = None
        self.prompt_sigs: list[str] = []

    async def run(self, page: Page, prompt: str, mode: str, output_dir: str, followup: bool = False) -> PlatformResult:
        """Execute the full platform lifecycle."""
        t0 = time.monotonic()
        timeout = TIMEOUTS.get(self.name)
        if timeout is None:
            from config import TimeoutConfig
            timeout = TimeoutConfig()
        max_wait = timeout.deep if mode == "DEEP" else timeout.regular

        try:
            self._setup_dialog_handler(page)

            if followup:
                log.info(f"[{self.display_name}] Follow-up mode: continuing existing conversation")
                await page.bring_to_front()
                await page.wait_for_timeout(1000)
                mode_label = f"{mode}-followup"
            else:
                try:
                    mode_label = await self._navigate_and_configure(page, mode)
                except _SignInRequired:
                    return PlatformResult(platform=self.name, display_name=self.display_name,
                                          status=STATUS_NEEDS_LOGIN, mode_used="",
                                          error="Sign-in required — please log in to this platform in Chrome first",
                                          duration_s=time.monotonic() - t0)
                except _RateLimited as exc:
                    return PlatformResult(platform=self.name, display_name=self.display_name,
                                          status=STATUS_RATE_LIMITED, mode_used="",
                                          error=f"Rate limited: {exc}", duration_s=time.monotonic() - t0)

            # Inject prompt
            log.info(f"[{self.display_name}] Injecting prompt ({len(prompt)} chars)")
            try:
                await self.inject_prompt(page, prompt)
            except Exception as exc:
                try:
                    await self._agent_fallback(page, "inject_prompt", exc,
                        f"On {self.display_name}: find and click/focus the main text input. Do NOT type.")
                except Exception:
                    raise
                await page.keyboard.type(prompt, delay=1)
            await page.wait_for_timeout(500)

            # Send
            log.info(f"[{self.display_name}] Sending prompt")
            try:
                await self.click_send(page)
            except Exception as exc:
                try:
                    await self._agent_fallback(page, "click_send", exc,
                        f"On {self.display_name}: find and click the send/submit button.")
                except Exception:
                    log.warning(f"[{self.display_name}] click_send failed, pressing Enter: {exc}")
                    await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)
            await self.dismiss_popups(page)

            # Post-send hook
            if not followup:
                try:
                    await self.post_send(page, mode)
                except Exception as exc:
                    try:
                        await self._agent_fallback(page, "post_send", exc,
                            f"On {self.display_name}: look for any 'Start research' button and click if present.")
                    except Exception:
                        log.warning(f"[{self.display_name}] post_send failed (non-fatal): {exc}")

            # Poll
            log.info(f"[{self.display_name}] Waiting for response (max {max_wait}s)")
            completed = await self._poll_completion(page, max_wait)
            if not completed:
                log.warning(f"[{self.display_name}] Timed out after {max_wait}s")
                try:
                    response = await self.extract_response(page)
                    if response and len(response) > 500:
                        return self._save_and_result(response, output_dir, mode_label, t0, STATUS_PARTIAL,
                                                     error="Timed out but partial content extracted")
                except Exception:
                    pass
                return PlatformResult(platform=self.name, display_name=self.display_name,
                                      status=STATUS_TIMEOUT, mode_used=mode_label,
                                      error=f"Timed out after {max_wait}s", duration_s=time.monotonic() - t0)

            if getattr(self, "_poll_rate_limit_msg", None):
                return PlatformResult(platform=self.name, display_name=self.display_name,
                                      status=STATUS_RATE_LIMITED, mode_used=mode_label,
                                      error=f"Rate limited: {self._poll_rate_limit_msg}",
                                      duration_s=time.monotonic() - t0)

            # Extract
            log.info(f"[{self.display_name}] Extracting response")
            response = await self._extract_with_fallback(page)
            if not response or (len(response) < 200 and not any(t in response for t in ("[RATE LIMITED]", "[FAILED]"))):
                return PlatformResult(platform=self.name, display_name=self.display_name,
                                      status=STATUS_FAILED, mode_used=mode_label,
                                      error=f"Extraction returned only {len(response) if response else 0} chars",
                                      duration_s=time.monotonic() - t0)
            return self._save_and_result(response, output_dir, mode_label, t0, STATUS_COMPLETE)

        except Exception as exc:
            log.exception(f"[{self.display_name}] Failed: {exc}")
            return PlatformResult(platform=self.name, display_name=self.display_name,
                                  status=STATUS_FAILED, mode_used="", error=str(exc),
                                  duration_s=time.monotonic() - t0)

    async def _extract_with_fallback(self, page: Page) -> str:
        """Extract response with agent fallback if result is too short."""
        try:
            response = await self.extract_response(page)
        except Exception as exc:
            result = await self._agent_fallback(page, "extract_response", exc,
                f"On {self.display_name}: extract the complete AI-generated response text.")
            response = result if result else ""

        _is_status = response and any(t in response for t in ("[RATE LIMITED]", "[FAILED]"))
        if not _is_status and (not response or len(response) < 200):
            try:
                result = await self._agent_fallback(page, "extract_response",
                    RuntimeError(f"Only {len(response) if response else 0} chars"),
                    f"On {self.display_name}: scroll through the entire response and capture all text.")
                if result and len(result) >= 50:
                    response = result
            except Exception:
                pass
        return response

    # Methods subclasses MUST override

    async def configure_mode(self, page: Page, mode: str) -> str:
        raise NotImplementedError

    async def completion_check(self, page: Page) -> bool:
        raise NotImplementedError

    async def extract_response(self, page: Page) -> str:
        raise NotImplementedError

    # Rate limit detection (subclasses SHOULD override)

    async def check_rate_limit(self, page: Page) -> str | None:
        for pattern in ["rate limit", "too many requests", "limit reached", "try again later", "quota exceeded"]:
            try:
                el = page.get_by_text(pattern, exact=False).first
                if await el.count() > 0 and await el.is_visible():
                    return pattern
            except Exception:
                pass
        return None

    # Methods subclasses CAN override

    async def inject_prompt(self, page: Page, prompt: str) -> None:
        method = INJECTION_METHODS.get(self.name, "execCommand")
        if method == "execCommand":
            await self._inject_exec_command(page, prompt)
        elif method == "physical_type":
            await self._inject_physical_type(page, prompt)
        elif method == "fill":
            await self._inject_fill(page, prompt)
        else:
            raise NotImplementedError(f"Unknown injection method: {method}")

    async def click_send(self, page: Page) -> None:
        for selector in ['button[aria-label*="Send"]', 'button[aria-label*="send"]',
                         'button[aria-label*="Submit"]', 'button[data-testid*="send"]', 'button[type="submit"]']:
            btn = page.locator(selector).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                return
        for text in ["Send", "Submit", "Search", "Ask"]:
            btn = page.get_by_role("button", name=text).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                return
        try:
            await self._agent_fallback(page, "click_send", RuntimeError("No send button found"),
                f"On {self.display_name}: find and click the send/submit button.")
            return
        except Exception:
            pass
        log.warning(f"[{self.display_name}] No send button found, pressing Enter")
        await page.keyboard.press("Enter")

    async def post_send(self, page: Page, mode: str) -> None:
        pass

    # Agent fallback

    async def _agent_fallback(self, page: Page, step: str, error: Exception, task_description: str):
        if self.agent_manager is None or not self.agent_manager.enabled:
            raise error
        from agent_fallback import FallbackStep
        return await self.agent_manager.fallback(page, self.name, FallbackStep(step), error, task_description)

    # Polling

    async def _poll_completion(self, page: Page, max_wait_s: int) -> bool:
        self._current_max_wait_s = max_wait_s
        self._poll_rate_limit_msg: str | None = None
        start = time.monotonic()
        consecutive_errors = 0

        while time.monotonic() - start < max_wait_s:
            try:
                rate_msg = await self.check_rate_limit(page)
                if rate_msg:
                    log.warning(f"[{self.display_name}] Rate limited during polling: {rate_msg}")
                    self._poll_rate_limit_msg = rate_msg
                    return True
            except Exception:
                pass
            try:
                if await self.completion_check(page):
                    log.info(f"[{self.display_name}] Response complete ({time.monotonic() - start:.0f}s)")
                    return True
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    try:
                        result = await self._agent_fallback(page, "completion_check", exc,
                            f"On {self.display_name}: check if AI finished. Answer 'yes' if complete.")
                        if result and "yes" in result.lower():
                            return True
                        consecutive_errors = 0
                        continue
                    except Exception:
                        log.error(f"[{self.display_name}] {consecutive_errors} consecutive poll errors: {exc}")
                        raise
                log.debug(f"[{self.display_name}] Poll error ({consecutive_errors}/5): {exc}")
            await asyncio.sleep(POLL_INTERVAL)
        return False

    # Save helper

    def _save_and_result(self, response: str, output_dir: str, mode_label: str,
                         t0: float, status: str, error: str = "") -> PlatformResult:
        filename = f"{self.display_name.replace(' ', '-')}-raw-response.md"
        filepath = Path(output_dir) / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(response, encoding="utf-8")
        log.info(f"[{self.display_name}] Saved {len(response)} chars to {filepath}")
        return PlatformResult(
            platform=self.name, display_name=self.display_name, status=status,
            chars=len(response), file=str(filepath), mode_used=mode_label,
            error=error, duration_s=time.monotonic() - t0,
        )
