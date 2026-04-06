"""Base class for all platform automation modules."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from weakref import WeakSet

from playwright.async_api import Page

from config import (
    INJECTION_METHODS,
    PLATFORM_DISPLAY_NAMES,
    PLATFORM_URLS,
    POLL_INTERVAL,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_NEEDS_LOGIN,
    STATUS_PARTIAL,
    STATUS_RATE_LIMITED,
    STATUS_TIMEOUT,
    TIMEOUTS,
)

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


class BasePlatform:
    """
    Base class for platform automation.

    Subclasses must implement:
        - configure_mode(page, mode)
        - completion_check(page) -> bool
        - extract_response(page) -> str

    Optional overrides:
        - inject_prompt(page, prompt)   — default uses INJECTION_METHODS config
        - click_send(page)              — default finds send button by text
        - post_send(page)               — hook for actions after send (e.g., Gemini "Start research")
    """

    name: str = ""                 # e.g. "perplexity"
    url: str = ""                  # e.g. "https://www.perplexity.ai"
    display_name: str = ""         # e.g. "Perplexity"
    _dialog_registered_pages: WeakSet = WeakSet()  # Track pages with dialog handlers

    def __init__(self):
        self.url = PLATFORM_URLS.get(self.name, "")
        self.display_name = PLATFORM_DISPLAY_NAMES.get(self.name, self.name)
        self.agent_manager = None           # Set by orchestrator to AgentFallbackManager instance
        self.prompt_sigs: list[str] = []    # Set by orchestrator for prompt-echo detection

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        page: Page,
        prompt: str,
        mode: str,
        output_dir: str,
        followup: bool = False,
    ) -> PlatformResult:
        """Execute the full platform lifecycle: navigate → configure → inject → send → poll → extract → save.

        Args:
            followup: If True, reuse the existing conversation in this tab (skip navigation
                      and mode configuration). Use for follow-up questions on the same topic.
        """
        t0 = time.monotonic()
        timeout = TIMEOUTS.get(self.name)
        if timeout is None:
            log.warning(f"[{self.display_name}] No timeout config found, using defaults")
            from config import TimeoutConfig
            timeout = TimeoutConfig()
        max_wait = timeout.deep if mode == "DEEP" else timeout.regular

        try:
            # Register dialog handler once per page — auto-accepts browser alert()/confirm()/prompt()
            # dialogs that would otherwise block indefinitely.
            self._setup_dialog_handler(page)

            if followup:
                # Follow-up mode: reuse existing conversation — skip navigation and mode config
                log.info(f"[{self.display_name}] Follow-up mode: continuing existing conversation")
                await page.bring_to_front()
                await page.wait_for_timeout(1000)
                mode_label = f"{mode}-followup"
            else:
                # 1. Navigate to new conversation — retry once on transient errors
                # (e.g. ERR_ABORTED from in-flight Chrome window operations)
                log.info(f"[{self.display_name}] Navigating to {self.url}")
                # Some SPA platforms (ChatGPT) accumulate stale iframes across client-
                # side navigations.  Navigating to about:blank first forces a full page
                # unload and reload, clearing all old sub-frames.
                if getattr(self, "_force_full_reload", False):
                    try:
                        await page.goto("about:blank", wait_until="commit", timeout=5000)
                        await page.wait_for_timeout(300)
                    except Exception:
                        pass  # Non-critical; proceed with main navigation
                nav_exc: Exception | None = None
                for nav_attempt in range(2):
                    try:
                        await page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
                        nav_exc = None
                        break
                    except Exception as exc:
                        nav_exc = exc
                        if nav_attempt == 0:
                            log.warning(f"[{self.display_name}] Navigation attempt 1 failed ({type(exc).__name__}), retrying in 3s")
                            await page.wait_for_timeout(3000)
                if nav_exc is not None:
                    # Both attempts failed — try agent fallback
                    try:
                        await self._agent_fallback(
                            page, "navigate", nav_exc,
                            f"Navigate to {self.url} and wait for the {self.display_name} "
                            f"chat interface to load. Confirm when the page is ready.",
                        )
                    except Exception:
                        raise RuntimeError(f"Navigation failed: {nav_exc}") from nav_exc
                await page.wait_for_timeout(3000)  # Let JS frameworks initialise

                # 1b. Dismiss any overlay popups (cookie banners, GDPR notices, modals)
                await self.dismiss_popups(page)

                # 1c. Sign-in detection — catches the case where the user isn't logged in
                if await self.is_sign_in_page(page):
                    # Notify immediately so the user can act without waiting for all platforms
                    print(
                        f"\n  🔑  [{self.display_name}] Sign-in required — "
                        f"please log in at: {self.url}",
                        flush=True,
                    )
                    log.warning(f"[{self.display_name}] Sign-in page detected — attempting agent recovery")
                    try:
                        await self._agent_fallback(
                            page, "navigate",
                            RuntimeError("Sign-in page visible"),
                            f"On {self.display_name}: a sign-in / login page is currently showing. "
                            f"The user is already authenticated — try navigating to the main chat "
                            f"interface directly without entering any credentials. "
                            f"Navigate to {self.url} and confirm the chat UI is now visible.",
                        )
                        await page.wait_for_timeout(2000)
                    except Exception:
                        pass
                    # Re-check after agent attempt
                    if await self.is_sign_in_page(page):
                        return PlatformResult(
                            platform=self.name, display_name=self.display_name,
                            status=STATUS_NEEDS_LOGIN, mode_used="",
                            error="Sign-in required — please log in to this platform in Chrome first",
                            duration_s=time.monotonic() - t0,
                        )

                # 1d. Rate limit pre-check (before any interaction)
                rate_msg = await self.check_rate_limit(page)
                if rate_msg:
                    log.warning(f"[{self.display_name}] Rate limited on page load: {rate_msg}")
                    return PlatformResult(
                        platform=self.name, display_name=self.display_name,
                        status=STATUS_RATE_LIMITED, mode_used="",
                        error=f"Rate limited: {rate_msg}",
                        duration_s=time.monotonic() - t0,
                    )

                # 1e. Unexpected UI check — if the chat interface is not in a ready state,
                # hand control to browser-use which can visually navigate to the right UI.
                if not await self.is_chat_ready(page):
                    log.warning(
                        f"[{self.display_name}] Chat UI not in expected state — "
                        f"triggering browser-use agent takeover"
                    )
                    try:
                        await self._agent_fallback(
                            page, "navigate",
                            RuntimeError("Chat UI not in expected ready state"),
                            f"On {self.display_name}: the chat interface is not showing correctly. "
                            f"Navigate to {self.url}, dismiss any popups or modals, and confirm "
                            f"that the main chat input area is visible and ready.",
                        )
                        await page.wait_for_timeout(2000)
                        await self.dismiss_popups(page)
                    except Exception as exc:
                        log.warning(
                            f"[{self.display_name}] Agent could not recover unexpected UI: {exc}"
                        )
                        # Continue — configure_mode may still succeed

                # 2. Configure mode
                log.info(f"[{self.display_name}] Configuring mode: {mode}")
                try:
                    mode_label = await self.configure_mode(page, mode)
                except Exception as exc:
                    try:
                        await self._agent_fallback(
                            page, "configure_mode", exc,
                            f"On {self.display_name}: configure the AI model for {mode} mode. "
                            f"Select the appropriate model and enable required features.",
                        )
                    except Exception:
                        log.warning(f"[{self.display_name}] configure_mode failed, continuing: {exc}")
                    mode_label = "Agent-configured"

                # Dismiss any popups that appeared after mode selection (e.g. upsell modals)
                await self.dismiss_popups(page)

            # 3. Inject prompt
            log.info(f"[{self.display_name}] Injecting prompt ({len(prompt)} chars)")
            try:
                await self.inject_prompt(page, prompt)
            except Exception as exc:
                # Agent finds and focuses input, then Playwright retries via keyboard
                try:
                    await self._agent_fallback(
                        page, "inject_prompt", exc,
                        f"On {self.display_name}: find and click/focus the main text input "
                        f"field where messages are typed. Do NOT type any text — just click on it.",
                    )
                except Exception:
                    raise
                await page.keyboard.type(prompt, delay=1)
            await page.wait_for_timeout(500)

            # 4. Send
            log.info(f"[{self.display_name}] Sending prompt")
            try:
                await self.click_send(page)
            except Exception as exc:
                try:
                    await self._agent_fallback(
                        page, "click_send", exc,
                        f"On {self.display_name}: find and click the send/submit button.",
                    )
                except Exception:
                    log.warning(f"[{self.display_name}] click_send failed, pressing Enter: {exc}")
                    await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)

            # Dismiss any post-send popups (share prompts, sign-up overlays, etc.)
            await self.dismiss_popups(page)

            # 5. Post-send hook (skip for follow-ups — research mode already active)
            if not followup:
                try:
                    await self.post_send(page, mode)
                except Exception as exc:
                    try:
                        await self._agent_fallback(
                            page, "post_send", exc,
                            f"On {self.display_name}: look for any 'Start research' or "
                            f"similar confirmation button and click it if present.",
                        )
                    except Exception:
                        log.warning(f"[{self.display_name}] post_send failed (non-fatal): {exc}")

            # 6. Poll for completion
            log.info(f"[{self.display_name}] Waiting for response (max {max_wait}s)")
            completed = await self._poll_completion(page, max_wait)

            if not completed:
                log.warning(f"[{self.display_name}] Timed out after {max_wait}s")
                # Try to extract whatever is available
                try:
                    response = await self.extract_response(page)
                    if response and len(response) > 500:
                        return self._save_and_result(
                            response, output_dir, mode_label, t0, STATUS_PARTIAL,
                            error="Timed out but partial content extracted"
                        )
                except Exception:
                    pass
                return PlatformResult(
                    platform=self.name, display_name=self.display_name,
                    status=STATUS_TIMEOUT, mode_used=mode_label,
                    error=f"Timed out after {max_wait}s",
                    duration_s=time.monotonic() - t0,
                )

            # 7. Extract response
            log.info(f"[{self.display_name}] Extracting response")
            try:
                response = await self.extract_response(page)
            except Exception as exc:
                result = await self._agent_fallback(
                    page, "extract_response", exc,
                    f"On {self.display_name}: extract the complete AI-generated response "
                    f"text from the page. Copy ALL the text from the AI's reply.",
                )
                response = result if result else ""

            # Skip Agent fallback if response is a known error/status message
            _is_status_msg = response and any(
                tag in response for tag in ("[RATE LIMITED]", "[FAILED]")
            )
            if not _is_status_msg and (not response or len(response) < 200):
                # Try Agent fallback if extraction returned too little content
                try:
                    result = await self._agent_fallback(
                        page, "extract_response",
                        RuntimeError(f"Extraction returned only {len(response) if response else 0} chars"),
                        f"On {self.display_name}: extract the complete AI response text. "
                        f"Scroll through the entire response and capture all visible text.",
                    )
                    # Use agent result if it returned any meaningful content
                    # (even if shorter than the raw body.innerText — the agent
                    # targets the actual AI response, not the whole page)
                    if result and len(result) >= 50:
                        response = result
                except Exception:
                    pass

            if not response or len(response) < 200:
                # Preserve status message text for rate-limited/failed responses
                if _is_status_msg:
                    status = STATUS_RATE_LIMITED if "[RATE LIMITED]" in response else STATUS_FAILED
                    return PlatformResult(
                        platform=self.name, display_name=self.display_name,
                        status=status, mode_used=mode_label,
                        error=response,
                        duration_s=time.monotonic() - t0,
                    )
                return PlatformResult(
                    platform=self.name, display_name=self.display_name,
                    status=STATUS_FAILED, mode_used=mode_label,
                    error=f"Extraction returned only {len(response) if response else 0} chars",
                    duration_s=time.monotonic() - t0,
                )

            # 8. Save
            return self._save_and_result(response, output_dir, mode_label, t0, STATUS_COMPLETE)

        except Exception as exc:
            log.exception(f"[{self.display_name}] Failed: {exc}")
            return PlatformResult(
                platform=self.name, display_name=self.display_name,
                status=STATUS_FAILED, mode_used="",
                error=str(exc),
                duration_s=time.monotonic() - t0,
            )

    # ------------------------------------------------------------------
    # Methods subclasses MUST override
    # ------------------------------------------------------------------

    async def configure_mode(self, page: Page, mode: str) -> str:
        """Configure the platform's model/mode. Return a label like 'Sonnet + Research'."""
        raise NotImplementedError

    async def completion_check(self, page: Page) -> bool:
        """Return True if the platform has finished generating."""
        raise NotImplementedError

    async def extract_response(self, page: Page) -> str:
        """Extract the full response text from the page."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Rate limit detection (subclasses SHOULD override)
    # ------------------------------------------------------------------

    async def check_rate_limit(self, page: Page) -> str | None:
        """Check for platform-specific rate limit indicators on the page.

        Returns:
            A descriptive string if rate-limited (e.g., "Usage limit reached"),
            or None if no rate limit detected.

        Subclasses should override this with platform-specific selectors.
        Default implementation checks common patterns.
        """
        common_patterns = [
            "rate limit",
            "too many requests",
            "limit reached",
            "try again later",
            "quota exceeded",
        ]
        try:
            for pattern in common_patterns:
                el = page.get_by_text(pattern, exact=False).first
                if await el.count() > 0 and await el.is_visible():
                    return pattern
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Sign-in detection (subclasses CAN override for platform-specific patterns)
    # ------------------------------------------------------------------

    async def is_sign_in_page(self, page: Page) -> bool:
        """Return True if the current page is a sign-in / login page.

        Checks URL patterns first (fast), then DOM indicators (slower).
        Subclasses can override for platform-specific login page structures.
        """
        url = page.url.lower()
        # URL-based detection — most reliable
        login_url_fragments = [
            "/login", "/signin", "/sign-in", "/auth",
            "accounts.google.com",
            "login.microsoftonline.com",
            "auth.openai.com",
        ]
        if any(fragment in url for fragment in login_url_fragments):
            return True

        # Password field is a strong DOM indicator
        try:
            pw = page.locator('input[type="password"]').first
            if await pw.count() > 0 and await pw.is_visible(timeout=2000):
                return True
        except Exception:
            pass

        return False

    # ------------------------------------------------------------------
    # Methods subclasses CAN override
    # ------------------------------------------------------------------

    async def inject_prompt(self, page: Page, prompt: str) -> None:
        """Inject the research prompt into the platform's input field."""
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
        """Click the send/submit button."""
        # Try common send button selectors
        for selector in [
            'button[aria-label*="Send"]',
            'button[aria-label*="send"]',
            'button[aria-label*="Submit"]',
            'button[data-testid*="send"]',
            'button[type="submit"]',
        ]:
            btn = page.locator(selector).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                return

        # Fallback: find button with send-like text
        for text in ["Send", "Submit", "Search", "Ask"]:
            btn = page.get_by_role("button", name=text).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                return

        # Agent fallback: try vision-based button finding before Enter
        try:
            await self._agent_fallback(
                page, "click_send",
                RuntimeError("No send button found via selectors"),
                f"On {self.display_name}: find and click the send/submit button "
                f"to send the message.",
            )
            return
        except Exception:
            pass

        # Last resort: press Enter
        log.warning(f"[{self.display_name}] No send button found, pressing Enter")
        await page.keyboard.press("Enter")

    async def post_send(self, page: Page, mode: str) -> None:
        """Hook for actions after sending (e.g., Gemini 'Start research' click)."""
        pass

    # ------------------------------------------------------------------
    # Dialog and popup handling
    # ------------------------------------------------------------------

    def _setup_dialog_handler(self, page: Page) -> None:
        """Register a one-time-per-page handler that auto-accepts browser dialogs.

        Playwright raises an error and the page hangs if a dialog (alert, confirm, prompt)
        fires and no handler is attached. This handler accepts all dialogs immediately so
        that overlays created by alert() / confirm() never block automation.

        Safe for follow-up mode: uses a class-level WeakSet to track pages that
        already have handlers, avoiding duplicate registration when the same Page
        object is reused across multiple run() calls.
        """
        # Guard: don't register duplicate handlers on the same page (follow-up mode)
        if page in BasePlatform._dialog_registered_pages:
            return
        BasePlatform._dialog_registered_pages.add(page)

        async def _accept_dialog(dialog) -> None:
            try:
                log.debug(
                    f"[{self.display_name}] Auto-accepting browser dialog "
                    f"({dialog.type}): {dialog.message[:80] if dialog.message else ''}"
                )
                await dialog.accept()
            except Exception:
                pass  # Dialog may have already been dismissed

        page.on("dialog", _accept_dialog)

    @staticmethod
    async def dismiss_popups(page: Page) -> None:
        """Attempt to dismiss common CSS overlay popups.

        Covers cookie banners, GDPR notices, sign-up modals, and other overlays
        that can block interaction with the underlying chat UI. Failures are silent
        — if no popup is present the selectors simply find nothing.
        """
        # --- Phase 1: Scoped selectors inside modal/dialog containers ---
        # These are safe — they only target buttons within overlay containers,
        # so they won't accidentally click a chat UI button.
        scoped_selectors = [
            # Buttons inside modal / dialog / overlay containers
            '[role="dialog"] button[aria-label*="Close"]',
            '[role="dialog"] button[aria-label*="close"]',
            '[role="dialog"] button[aria-label*="Dismiss"]',
            '[role="dialog"] button[aria-label*="dismiss"]',
            '[aria-modal="true"] button[aria-label*="Close"]',
            '[aria-modal="true"] button[aria-label*="close"]',
            '[aria-modal="true"] button[aria-label*="Dismiss"]',
            '[aria-modal="true"] button[aria-label*="dismiss"]',
            '[data-testid="close-button"]',
            '[data-testid="modal-close"]',
            '[class*="modal"] [class*="close"]',
            '[class*="dialog"] [class*="close"]',
            '[class*="overlay"] [class*="close"]',
            '[class*="popup"] [class*="close"]',
            '[class*="toast"] [class*="close"]',
        ]
        # --- Phase 2: Cookie / GDPR / consent banners ---
        # Scoped to cookie/consent/banner containers to avoid misclicks.
        consent_selectors = [
            '[class*="cookie"] button:has-text("Accept")',
            '[class*="cookie"] button:has-text("OK")',
            '[class*="consent"] button:has-text("Accept")',
            '[class*="consent"] button:has-text("Agree")',
            '[class*="consent"] button:has-text("Got it")',
            '[class*="banner"] button:has-text("Accept")',
            '[class*="banner"] button:has-text("Got it")',
            '[class*="banner"] button:has-text("Dismiss")',
            '[class*="banner"] [class*="close"]',
            '[id*="cookie"] button',
            '[id*="consent"] button',
        ]
        # Try all phases; continue after each successful dismiss to catch layered popups
        dismissed_count = 0
        max_dismissals = 3  # Safety cap to prevent infinite loops
        for selector in scoped_selectors + consent_selectors:
            if dismissed_count >= max_dismissals:
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

    # ------------------------------------------------------------------
    # Chat readiness check (subclasses CAN override)
    # ------------------------------------------------------------------

    async def is_chat_ready(self, page: Page) -> bool:
        """Return True if the chat UI is in the expected ready state.

        The default checks that we are not on a sign-in page, not on a blank or
        error page. Subclasses can override to add platform-specific checks
        (e.g. verifying that the message textarea is present).

        Called just before configure_mode so that unexpected UI states (redirect
        to a billing page, an interstitial, a 404) are caught early and handed
        off to the browser-use agent for recovery.
        """
        # Already on a sign-in page — not ready
        if await self.is_sign_in_page(page):
            return False
        # Blank or empty tab
        url = page.url.lower()
        if url in ("about:blank", "chrome://newtab/", ""):
            return False
        # Check page title for HTTP error patterns (title is far less likely
        # to contain false positives than scanning all visible text).
        try:
            title = (await page.title()).lower()
            error_title_patterns = [
                "404", "not found", "page not found",
                "500", "internal server error",
                "502", "bad gateway",
                "503", "service unavailable",
                "access denied", "forbidden",
            ]
            if any(pattern in title for pattern in error_title_patterns):
                log.debug(f"[is_chat_ready] Error title detected: '{title}'")
                return False
        except Exception:
            pass
        return True

    # ------------------------------------------------------------------
    # Agent fallback
    # ------------------------------------------------------------------

    async def _agent_fallback(
        self, page: Page, step: str, error: Exception, task_description: str,
    ):
        """Invoke browser-use Agent fallback. Re-raises original error if disabled or fails."""
        if self.agent_manager is None or not self.agent_manager.enabled:
            raise error
        from agent_fallback import FallbackStep
        return await self.agent_manager.fallback(
            page, self.name, FallbackStep(step), error, task_description,
        )

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _poll_completion(self, page: Page, max_wait_s: int) -> bool:
        """Poll until completion_check returns True or timeout."""
        # Store max_wait_s on instance so completion_check() overrides can read it
        # for mode-aware thresholds (e.g. DEEP mode needs a longer stable-state window).
        self._current_max_wait_s = max_wait_s
        start = time.monotonic()
        consecutive_errors = 0
        max_consecutive_errors = 5

        while time.monotonic() - start < max_wait_s:
            # Check for rate limiting during polling
            try:
                rate_msg = await self.check_rate_limit(page)
                if rate_msg:
                    log.warning(f"[{self.display_name}] Rate limited during polling: {rate_msg}")
                    return True  # Exit poll; extract_response will detect the rate limit
            except Exception:
                pass  # Non-fatal — continue polling

            try:
                if await self.completion_check(page):
                    log.info(f"[{self.display_name}] Response complete ({time.monotonic() - start:.0f}s)")
                    return True
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    # Try Agent fallback before aborting
                    try:
                        result = await self._agent_fallback(
                            page, "completion_check", exc,
                            f"On {self.display_name}: check if the AI has finished generating. "
                            f"Look for: no stop/cancel button, copy/share buttons visible, "
                            f"or fully rendered response. Answer 'yes' if complete, 'no' if still generating.",
                        )
                        if result and "yes" in result.lower():
                            return True
                        consecutive_errors = 0  # Agent worked; reset counter
                        continue
                    except Exception:
                        log.error(f"[{self.display_name}] {consecutive_errors} consecutive poll errors, aborting: {exc}")
                        raise
                log.debug(f"[{self.display_name}] Poll check error ({consecutive_errors}/{max_consecutive_errors}): {exc}")

            await asyncio.sleep(POLL_INTERVAL)
        return False

    # ------------------------------------------------------------------
    # Injection helpers
    # ------------------------------------------------------------------

    async def _inject_exec_command(self, page: Page, prompt: str) -> int:
        """Inject into a contenteditable div via document.execCommand.

        Returns verified char count.  If execCommand silently fails (returns
        false — it is a deprecated API and Chrome may drop it), automatically
        falls back to clipboard-paste injection before raising.
        """
        success = await page.evaluate("""(prompt) => {
            const el = document.querySelector('div[contenteditable="true"]')
                      || document.querySelector('[contenteditable="true"]');
            if (!el) throw new Error('No contenteditable element found');
            el.focus();
            document.execCommand('selectAll', false, null);
            // execCommand returns false when the command is unsupported/disabled
            const ok = document.execCommand('insertText', false, prompt);
            return ok;
        }""", prompt)

        # Verify injection — read back what's actually in the field
        length = await page.evaluate("""
            (document.querySelector('div[contenteditable="true"]')
             || document.querySelector('[contenteditable="true"]')).textContent.length
        """)

        # If execCommand reported failure or the field has < 50% of the prompt,
        # fall back to clipboard-paste injection before giving up.
        if not success or length < len(prompt) * 0.5:
            log.warning(
                f"[{self.display_name}] execCommand returned {success} "
                f"(field has {length}/{len(prompt)} chars) — trying clipboard-paste fallback"
            )
            length = await self._inject_clipboard_paste(page, prompt)

        log.info(f"[{self.display_name}] Injected {length} chars via execCommand")
        return length

    async def _inject_clipboard_paste(self, page: Page, prompt: str) -> int:
        """Fallback injection via system clipboard + paste keystroke.

        Used when execCommand('insertText') fails (deprecated API).
        Writes the prompt to the OS clipboard, focuses the contenteditable
        element, and triggers Cmd+V / Ctrl+V.
        """
        import subprocess
        import sys

        # Write prompt to system clipboard
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=prompt.encode("utf-8"), timeout=5, check=True)
        elif sys.platform == "linux":
            for cmd in [
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
                ["wl-copy"],
            ]:
                try:
                    subprocess.run(cmd, input=prompt.encode("utf-8"), timeout=5, check=True)
                    break
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
            else:
                raise RuntimeError("No clipboard tool available (install xclip, xsel, or wl-copy)")
        elif sys.platform == "win32":
            subprocess.run(["clip"], input=prompt.encode("utf-16-le"), timeout=5, check=True)
        else:
            raise RuntimeError(f"Unsupported platform for clipboard paste: {sys.platform}")

        # Focus + select-all in the contenteditable, then paste
        await page.evaluate("""
            (() => {
                const el = document.querySelector('div[contenteditable="true"]')
                          || document.querySelector('[contenteditable="true"]');
                if (!el) throw new Error('No contenteditable element found');
                el.focus();
                document.execCommand('selectAll', false, null);
            })()
        """)
        modifier = "Meta" if sys.platform == "darwin" else "Control"
        await page.keyboard.press(f"{modifier}+KeyV")
        await page.wait_for_timeout(500)

        # Verify
        length = await page.evaluate("""
            (document.querySelector('div[contenteditable="true"]')
             || document.querySelector('[contenteditable="true"]')).textContent.length
        """)
        log.info(f"[{self.display_name}] Injected {length} chars via clipboard paste fallback")
        return length

    async def _inject_physical_type(self, page: Page, prompt: str) -> None:
        """Physical keyboard typing for React textareas (e.g., Grok)."""
        textarea = page.locator("textarea").first
        await textarea.click()
        await page.wait_for_timeout(300)
        await textarea.type(prompt, delay=5)  # 5ms between keystrokes
        log.info(f"[{self.display_name}] Typed {len(prompt)} chars physically")

    async def _inject_fill(self, page: Page, prompt: str) -> None:
        """Fill a React textarea using Playwright's fill() (triggers React state)."""
        textarea = page.locator("textarea").first
        await textarea.click()
        await page.wait_for_timeout(300)
        await textarea.fill(prompt)
        # Dispatch input event to trigger React state update
        await textarea.dispatch_event("input")
        log.info(f"[{self.display_name}] Filled textarea with {len(prompt)} chars")

    # ------------------------------------------------------------------
    # Save helpers
    # ------------------------------------------------------------------

    def _save_and_result(
        self,
        response: str,
        output_dir: str,
        mode_label: str,
        t0: float,
        status: str,
        error: str = "",
    ) -> PlatformResult:
        """Save response to file and return PlatformResult."""
        filename = f"{self.display_name.replace(' ', '-')}-raw-response.md"
        filepath = Path(output_dir) / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(response, encoding="utf-8")
        log.info(f"[{self.display_name}] Saved {len(response)} chars to {filepath}")
        return PlatformResult(
            platform=self.name,
            display_name=self.display_name,
            status=status,
            chars=len(response),
            file=str(filepath),
            mode_used=mode_label,
            error=error,
            duration_s=time.monotonic() - t0,
        )
