"""Google Gemini platform automation."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from .base import BasePlatform
from prompt_echo import is_prompt_echo

log = logging.getLogger(__name__)


class Gemini(BasePlatform):
    name = "gemini"

    def __init__(self):
        super().__init__()
        self._no_stop_polls: int = 0   # Consecutive polls with no stop button visible
        self._seen_stop: bool = False  # True once a stop button has been observed (research actually started)

    async def check_rate_limit(self, page: Page) -> str | None:
        """Check for Gemini-specific rate limit indicators.

        Extended to cover additional real-world rate-limit/quota UI patterns
        observed in the March 2026 test round.
        """
        patterns = [
            "at full capacity",
            "limit reached",
            "quota exceeded",
            "too many requests",
            "try again in",
            # Additional patterns from live testing
            "daily limit exceeded",
            "usage limit reached",
            "You've reached your usage limit",
            "unavailable right now",
            "is currently unavailable",
            "temporarily unavailable",
            "Gemini 1.5 Pro is not available",
            "2.0 Flash Thinking Experimental is limited",
        ]
        for pattern in patterns:
            try:
                el = page.get_by_text(pattern, exact=False).first
                if await el.count() > 0 and await el.is_visible():
                    return pattern
            except Exception:
                pass
        # Check for model fallback (Gemini falls to Flash when Pro quota exhausted)
        try:
            flash = page.get_by_text("switched to Flash", exact=False).first
            if await flash.count() > 0 and await flash.is_visible():
                return "Model downgraded to Flash (Pro quota exceeded)"
        except Exception:
            pass
        return None

    async def configure_mode(self, page: Page, mode: str) -> str:
        """
        Select Thinking model; enable Deep Research via Tools menu (DEEP).
        Verify Deep Research badge before injecting prompt.
        """
        label_parts = []

        # Select Thinking model.
        # Gemini's default model is "Flash" (shown as "Fast" in the toolbar button).
        # Try specific selectors before falling back to generic "Gemini" text.
        try:
            model_btn = None
            for selector in [
                '[aria-label*="model"]',
                '[data-testid*="model"]',
                'button:has-text("Fast")',    # Gemini Flash labeled "Fast" in toolbar
                'button:has-text("Flash")',   # Alternative Flash label
                'button:has-text("Gemini")',  # Generic fallback
            ]:
                btn = page.locator(selector).first
                if await btn.count() > 0 and await btn.is_visible():
                    model_btn = btn
                    break
            if model_btn is not None:
                await model_btn.click()
                await page.wait_for_timeout(500)

                thinking = page.get_by_text("Thinking", exact=False).first
                if await thinking.count() > 0:
                    await thinking.click()
                    await page.wait_for_timeout(500)
                    log.info("[Gemini] Selected Thinking model")
                    label_parts.append("Thinking")
        except Exception as exc:
            log.warning(f"[Gemini] Thinking model selection failed: {exc}")

        # DEEP mode: enable Deep Research via Tools menu
        # Gemini toolbar has a "Tools" button (no aria-label) that opens a MAT-ACTION-LIST
        # menu. The "Deep research" option is a button[role="menuitemcheckbox"] inside it.
        if mode == "DEEP":
            try:
                # Use the input-area Tools button — it has visible text "Tools" but no aria-label.
                # Scope to buttons WITHOUT aria-label to avoid the sidebar conversation-actions button
                # which has aria-label="More options for ... Tools".
                tools_btn = page.locator("button:not([aria-label])").filter(has_text="Tools").first
                if await tools_btn.count() == 0:
                    tools_btn = page.get_by_text("Tools", exact=True).first
                if await tools_btn.count() > 0 and await tools_btn.is_visible():
                    await tools_btn.click()
                    await page.wait_for_timeout(500)

                    # Target the menuitemcheckbox inside the Tools action-list menu
                    dr = page.get_by_role("menuitemcheckbox", name="Deep research").first
                    if await dr.count() == 0:
                        # Fallback: any button in the menu containing "deep research"
                        dr = page.locator('[role="menu"] button').filter(has_text="Deep research").first
                    if await dr.count() > 0 and await dr.is_visible():
                        await dr.click()
                        await page.wait_for_timeout(500)
                        log.info("[Gemini] Enabled Deep Research")
                        label_parts.append("Deep Research")
                    else:
                        log.warning("[Gemini] Deep Research menu item not found or not visible — skipping")

                    # Verify badge is visible (badge text uses lowercase "r")
                    badge = page.locator('[role="menu"] button').filter(has_text="Deep research").first
                    if await badge.count() > 0 and await badge.is_visible():
                        log.info("[Gemini] Deep Research badge confirmed")
                    else:
                        log.warning("[Gemini] Deep Research badge NOT visible — may not be enabled")
            except Exception as exc:
                log.warning(f"[Gemini] Deep Research enablement failed: {exc}")

        return " + ".join(label_parts) if label_parts else "Default"

    async def inject_prompt(self, page: Page, prompt: str) -> None:
        """Inject via execCommand, then verify length (Gemini silently truncates)."""
        length = await self._inject_exec_command(page, prompt)

        # Check for truncation (Gemini-specific hazard)
        if length < len(prompt) * 0.9:  # Allow 10% tolerance
            log.warning(f"[Gemini] Prompt may be truncated: injected {length} of {len(prompt)} chars")

    async def post_send(self, page: Page, mode: str) -> None:
        """
        DEEP mode: Must click 'Start research' when the plan appears.
        Gemini presents a research plan BEFORE starting actual web crawling.
        Handle capacity errors with 3 retries.
        """
        if mode != "DEEP":
            return

        retries = 0
        max_retries = 3

        for attempt in range(max_retries + 1):
            await page.wait_for_timeout(20000)  # Wait for plan to appear (complex prompts take longer)

            # Check for capacity error
            try:
                capacity_err = page.get_by_text("at full capacity", exact=False).first
                if await capacity_err.count() > 0 and await capacity_err.is_visible():
                    retries += 1
                    if retries >= max_retries:
                        raise RuntimeError("Gemini capacity error persisted after 3 retries")
                    log.warning(f"[Gemini] Capacity error — retry {retries}/{max_retries}")
                    await page.wait_for_timeout(30000)  # Wait 30s before retry
                    continue
            except RuntimeError:
                raise
            except Exception:
                pass

            # Look for "Start research" button
            try:
                start_btn = page.get_by_text("Start research", exact=False).first
                if await start_btn.count() > 0 and await start_btn.is_visible():
                    # Scroll into view first
                    await start_btn.scroll_into_view_if_needed()
                    await start_btn.click()
                    log.info("[Gemini] Clicked 'Start research' button")

                    # Verify crawl started — look for stop OR cancel button
                    await page.wait_for_timeout(5000)
                    for sel in ['button:has-text("Stop")', 'button[aria-label*="Stop"]',
                                'button:has-text("Cancel")', 'button[aria-label*="Cancel"]']:
                        stop = page.locator(sel).first
                        if await stop.count() > 0:
                            log.info("[Gemini] Research crawl started")
                            return
                    return
            except Exception as exc:
                log.debug(f"[Gemini] Start research button not found yet: {exc}")

            # If no plan appeared and no error, Gemini may have started automatically
            for sel in ['button:has-text("Stop")', 'button[aria-label*="Stop"]',
                        'button:has-text("Cancel")', 'button[aria-label*="Cancel"]']:
                stop = page.locator(sel).first
                if await stop.count() > 0:
                    log.info("[Gemini] Research started automatically (no plan step)")
                    return

        log.warning("[Gemini] 'Start research' button not found and no auto-start detected — Deep Research may not have started")

    async def completion_check(self, page: Page) -> bool:
        """Check for completion — multi-signal with stable-state fallback."""
        # 1. Check for stop/cancel button.
        # In Deep Research mode Gemini uses "Cancel" (not "Stop") while research
        # is running.  Check both labels so _seen_stop is correctly set and the
        # early-12-poll bail-out is never triggered prematurely.
        has_stop = False
        for sel in [
            'button:has-text("Stop")',
            'button[aria-label*="Stop"]',
            'button:has-text("Cancel")',
            'button[aria-label*="Cancel"]',
        ]:
            try:
                stop = page.locator(sel).first
                if await stop.count() > 0 and await stop.is_visible():
                    has_stop = True
                    break
            except Exception:
                pass

        # Also treat the Deep Research "Thinking" progress indicator as "still running"
        if not has_stop:
            try:
                # Gemini shows a "Thinking" label while Deep Research is in progress.
                # Scope to the response/progress area to avoid false matches in
                # other visible text.
                thinking_el = page.locator(
                    '[class*="progress"] :text("Thinking"), '
                    '[class*="deep-research"] :text("Thinking"), '
                    'model-response :text("Thinking")'
                ).first
                if await thinking_el.count() > 0 and await thinking_el.is_visible():
                    has_stop = True
            except Exception:
                pass

        if has_stop:
            self._no_stop_polls = 0
            self._seen_stop = True  # Research started — stop/cancel/thinking was visible
            return False

        self._no_stop_polls += 1

        # 2. UI completion signals — scoped to the response container only.
        # Gemini's page header always shows Share/Export/Copy buttons, causing
        # false positives. Only count these signals when:
        #   (a) the button is inside a model-response / message-content container, OR
        #   (b) the button's aria-label specifically mentions "response" or "message", AND
        #   (c) body text is already substantial (> 3000 chars), confirming real content.
        try:
            body_len_check = await page.evaluate("document.body.innerText.length")
        except Exception:
            body_len_check = 0

        if body_len_check > 3000:
            # Try response-scoped copy/share first (most reliable)
            scoped_sels = [
                '[class*="model-response"] button[aria-label*="Copy"]',
                '[class*="model-response"] button[aria-label*="copy"]',
                '[class*="message-content"] button[aria-label*="Copy"]',
                '.markdown-main-panel button[aria-label*="Copy"]',
                # Gemini response actions row (typically below the completed message)
                '[class*="response-container"] button:has-text("Copy")',
                '[class*="response-container"] button:has-text("Share")',
            ]
            for sel in scoped_sels:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible():
                        log.info(f"[Gemini] Completion: scoped copy/share button found ({sel!r})")
                        return True
                except Exception:
                    pass

        # 3. Content-based: body text > 15 000 chars.
        #    Threshold raised from 10 000 (Harness OSS: plan-phase page chrome was ~3-4 k;
        #    research-complete reports are 15 000+).
        #    GUARD: require _seen_stop so this does not fire while the plan/prompt echo
        #    is still on screen (the echoed prompt + Thinking text can easily exceed 15 k
        #    before actual research begins).
        try:
            body_len = await page.evaluate("document.body.innerText.length")
            if body_len > 15000 and self._seen_stop:
                log.info(f"[Gemini] Body text {body_len} > 15000 after research started — declaring complete")
                return True
        except Exception:
            pass

        # 4. Stable-state: no stop button for 3 consecutive polls (~30s).
        #    REQUIRES _seen_stop — i.e. the stop button was previously visible,
        #    meaning research actually started and finished.
        #    Without this guard, the check fires prematurely during the plan phase
        #    (before "Start research" is clicked) because the plan UI has no stop button.
        if self._no_stop_polls >= 3 and self._seen_stop:
            log.info("[Gemini] No stop button for 3 polls after research started — declaring complete")
            return True

        # 5. Extended fallback: if still no stop/cancel/thinking signal seen after
        #    40 polls (~6.7 min), something is wrong (post_send may have missed
        #    "Start research", or the DR UI changed).  Declare complete.
        #    Raised from 12 → 40 because Deep Research for complex prompts takes
        #    5–30 min; the old 2-min limit was triggering prematurely.
        if self._no_stop_polls >= 40:
            log.warning("[Gemini] 40 polls with no stop/cancel/thinking ever seen — declaring complete.")
            return True

        return False

    async def extract_response(self, page: Page) -> str:
        """
        Extract via inner text. NEVER use JS chunk extraction for Gemini
        (security filter blocks inline URLs in Deep Research reports).
        """
        # Primary: try specific Gemini response container selectors
        try:
            # Gemini uses model-response containers or message-content divs
            resp_containers = page.locator(
                '[class*="model-response"], [class*="response-container"], '
                '[class*="message-content"], .markdown-main-panel'
            )
            count = await resp_containers.count()
            if count > 0:
                last_resp = resp_containers.nth(count - 1)
                text = await last_resp.inner_text()
                if len(text) > 500:
                    log.info(f"[Gemini] Extracted {len(text)} chars via response container")
                    return text
        except Exception as exc:
            log.debug(f"[Gemini] Response container extraction failed: {exc}")

        # Secondary: find the report content area within body text
        # Guard: Gemini shows the full conversation including the echoed user prompt.
        # Scan ALL occurrences of each generic heading marker and pick the LAST one
        # that is not a prompt echo (verified via self.prompt_sigs).
        try:
            body = await page.evaluate("document.body.innerText")
            if len(body) > 3000:
                for marker in ["# ", "## "]:
                    # Collect all positions of this marker
                    positions = []
                    start = 0
                    while True:
                        idx = body.find(marker, start)
                        if idx < 0:
                            break
                        positions.append(idx)
                        start = idx + 1

                    # Pick the last occurrence that is not a prompt echo
                    for idx in reversed(positions):
                        candidate = body[idx:]
                        if is_prompt_echo(candidate, self.prompt_sigs):
                            log.debug(f"[Gemini] Skipping prompt echo at marker '{marker}' pos {idx}")
                            continue
                        if len(candidate) > 500:
                            log.info(f"[Gemini] Extracted {len(candidate)} chars (marker '{marker}' at {idx})")
                            return candidate

                # No clean marker found — return full body only if it's not a prompt echo
                if not is_prompt_echo(body, self.prompt_sigs):
                    log.info(f"[Gemini] Extracted {len(body)} chars (full body, no marker)")
                    return body
                log.warning("[Gemini] Body text appears to be a prompt echo — skipping full-body fallback")
        except Exception as exc:
            log.error(f"[Gemini] body.innerText extraction failed: {exc}")

        # Tertiary: try main content area
        try:
            text = await page.evaluate("""
                (() => {
                    const main = document.querySelector('main')
                               || document.querySelector('[role="main"]');
                    if (main) return main.innerText;
                    return document.body.innerText;
                })()
            """)
            if text and len(text) > 200:
                log.info(f"[Gemini] Extracted {len(text)} chars via main container")
                return text
        except Exception as exc:
            log.error(f"[Gemini] All extraction methods failed: {exc}")
            return ""
