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
        self._deep_mode: bool = False  # True when Deep Research mode is active
        self._dr_start_unconfirmed: bool = False  # True when "Start research" was clicked but Stop not yet confirmed

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

        # Extra wait — Gemini's Angular/Material UI can take a moment to render
        # the toolbar buttons after page load.  Also wait for the input area to be
        # visible before attempting to click any toolbar buttons.
        await page.wait_for_timeout(3000)
        try:
            await page.wait_for_selector(
                'div[contenteditable="true"], textarea[placeholder], [data-placeholder]',
                state="visible", timeout=10000,
            )
        except Exception:
            pass  # Input area check timed out — proceed anyway

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
                '[class*="model-switcher"] button',
                '[class*="bard-mode"] button',
            ]:
                btn = page.locator(selector).first
                if await btn.count() > 0 and await btn.is_visible():
                    model_btn = btn
                    break
            if model_btn is not None:
                await model_btn.click()
                await page.wait_for_timeout(800)

                thinking = page.get_by_text("Thinking", exact=False).first
                if await thinking.count() > 0:
                    await thinking.click()
                    await page.wait_for_timeout(500)
                    log.info("[Gemini] Selected Thinking model")
                    label_parts.append("Thinking")
        except Exception as exc:
            log.warning(f"[Gemini] Thinking model selection failed: {exc}")

        # DEEP mode: enable Deep Research.
        # Strategy 1: Direct "Deep research" button/link visible in the input area.
        # Strategy 2: Tools menu → "Deep research" menuitemcheckbox.
        if mode == "DEEP":
            dr_enabled = False
            try:
                # Strategy 1: direct Deep Research button (Gemini sometimes shows it
                # as a prominent button next to the input box, no Tools menu needed).
                for dr_direct_sel in [
                    'button:has-text("Deep research")',
                    '[aria-label*="Deep research"]',
                    '[data-testid*="deep-research"]',
                ]:
                    dr_btn = page.locator(dr_direct_sel).first
                    if await dr_btn.count() > 0 and await dr_btn.is_visible():
                        await dr_btn.click()
                        await page.wait_for_timeout(500)
                        log.info("[Gemini] Enabled Deep Research via direct button")
                        label_parts.append("Deep Research")
                        self._deep_mode = True
                        dr_enabled = True
                        break
            except Exception as exc:
                log.debug(f"[Gemini] Direct Deep Research button approach failed: {exc}")

            if not dr_enabled:
                try:
                    # Strategy 2: Tools menu.
                    # Use the input-area Tools button — it has visible text "Tools" but no aria-label.
                    # Scope to buttons WITHOUT aria-label to avoid the sidebar conversation-actions
                    # button (aria-label="More options for ... Tools").
                    tools_btn = page.locator("button:not([aria-label])").filter(has_text="Tools").first
                    if await tools_btn.count() == 0:
                        tools_btn = page.get_by_role("button", name="Tools", exact=True).first
                    if await tools_btn.count() == 0:
                        tools_btn = page.get_by_text("Tools", exact=True).first
                    if await tools_btn.count() == 0:
                        # Gemini /app page: Tools button may be inside the input toolbar
                        tools_btn = page.locator('[aria-label*="Tools"], [data-testid*="tools"]').first
                    if await tools_btn.count() == 0:
                        # Mat-icon-button or any element with "Tools" accessible name
                        tools_btn = page.get_by_role("button", name="Tools").first
                    if await tools_btn.count() > 0 and await tools_btn.is_visible():
                        await tools_btn.click()
                        await page.wait_for_timeout(800)

                        # Target the menuitemcheckbox inside the Tools action-list menu
                        dr = page.get_by_role("menuitemcheckbox", name="Deep research").first
                        if await dr.count() == 0:
                            dr = page.locator('[role="menu"] button').filter(has_text="Deep research").first
                        if await dr.count() == 0:
                            # Broader fallback: any visible element with "Deep research" text in a menu
                            dr = page.locator('[role="menuitem"], [role="option"]').filter(has_text="Deep research").first
                        if await dr.count() > 0 and await dr.is_visible():
                            # Check if DR is already enabled (aria-checked="true").
                            # If already on, clicking again would DISABLE it — don't click.
                            try:
                                is_checked = await dr.get_attribute("aria-checked")
                                if is_checked == "true":
                                    log.info("[Gemini] Deep Research already enabled (aria-checked=true) — skipping toggle")
                                    label_parts.append("Deep Research")
                                    self._deep_mode = True
                                    dr_enabled = True
                                else:
                                    await dr.click()
                                    await page.wait_for_timeout(500)
                                    log.info("[Gemini] Enabled Deep Research via Tools menu")
                                    label_parts.append("Deep Research")
                                    self._deep_mode = True
                                    dr_enabled = True
                            except Exception:
                                # Couldn't read aria-checked — click anyway
                                await dr.click()
                                await page.wait_for_timeout(500)
                                log.info("[Gemini] Enabled Deep Research via Tools menu (no aria-checked)")
                                label_parts.append("Deep Research")
                                self._deep_mode = True
                                dr_enabled = True
                        else:
                            log.warning("[Gemini] Deep Research menu item not found or not visible — skipping")
                    else:
                        log.warning("[Gemini] Tools button not found in input area")
                except Exception as exc:
                    log.warning(f"[Gemini] Deep Research enablement failed: {exc}")

            if dr_enabled:
                # Dismiss the Tools menu if still open
                try:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(300)
                except Exception:
                    pass

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

            # Look for "Start research" button (or variants used by different Gemini UI versions)
            try:
                start_btn = None
                for start_text in ["Start research", "Start deep research", "Begin research", "Start"]:
                    candidate = page.get_by_role("button", name=start_text, exact=False).first
                    if await candidate.count() > 0 and await candidate.is_visible():
                        start_btn = candidate
                        break
                if start_btn is None:
                    # Broader fallback: any visible button with "research" in text
                    start_btn = page.locator('button').filter(has_text="research").first
                    if await start_btn.count() == 0 or not await start_btn.is_visible():
                        start_btn = None
                if start_btn is not None:
                    # Bring tab to front so Gemini's Angular SPA renders the DR progress UI.
                    # In a 7-platform parallel run the tab is often backgrounded; without focus
                    # the Stop/Cancel button may not appear within the check window.
                    try:
                        await page.bring_to_front()
                        await page.wait_for_timeout(500)
                    except Exception:
                        pass

                    # Scroll into view first
                    await start_btn.scroll_into_view_if_needed()
                    await start_btn.click()
                    log.info("[Gemini] Clicked 'Start research' button")

                    # Verify crawl started — poll for stop OR cancel button for up to 60s.
                    # The 5-platform parallel run backgrounds Gemini's tab; Angular renders
                    # the Stop button lazily so a single 5s check misses it.
                    _stop_confirmed = False
                    for _check in range(12):  # 12 × 5s = 60s
                        await page.wait_for_timeout(5000)
                        for sel in ['button:has-text("Stop")', 'button[aria-label*="Stop"]',
                                    'button:has-text("Cancel")', 'button[aria-label*="Cancel"]']:
                            stop = page.locator(sel).first
                            if await stop.count() > 0 and await stop.is_visible():
                                log.info(f"[Gemini] Research crawl confirmed started (check {_check + 1})")
                                _stop_confirmed = True
                                break
                        if _stop_confirmed:
                            break
                    if not _stop_confirmed:
                        log.warning("[Gemini] Stop/Cancel not seen within 60s after 'Start research' click — "
                                    "marking _dr_start_unconfirmed; polling will not use quick-response fallback")
                        self._dr_start_unconfirmed = True
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

        # Also treat the Deep Research "Thinking" / "Searching" progress indicator as "still running"
        if not has_stop:
            try:
                # Gemini shows "Thinking", "Searching the web", "Reading" etc. while DR runs.
                # Avoid the model-selector toolbar button (a <button>) — scope to non-button elements.
                # Scoped selectors (most precise) first, then broad non-button fallbacks.
                thinking_el = page.locator(
                    '[class*="progress"] :text("Thinking"), '
                    '[class*="deep-research"] :text("Thinking"), '
                    'model-response :text("Thinking"), '
                    # Broader DR progress phrases — Gemini shows these during research phases
                    'div:has-text("Searching the web"), '
                    'div:has-text("Reading"), '
                    'span:has-text("Searching")'
                    # NOTE: broad 'div:text-is("Thinking")' and ':not(button):text-is("Thinking")'
                    # intentionally removed — these match the persistent "Thinking" mode selector
                    # button in the bottom input bar (visible even after DR completes), causing
                    # has_stop=True permanently and blocking completion detection.
                ).first
                if await thinking_el.count() > 0 and await thinking_el.is_visible():
                    has_stop = True
                    log.debug("[Gemini] DR progress indicator visible (Thinking/Searching/Reading)")
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
                # Gemini Deep Research report panel — "Share & Export" button appears
                # in the report panel header only when DR is complete. Distinct from
                # the page-level share icon (which has no text label).
                'button:has-text("Share & Export")',
            ]
            for sel in scoped_sels:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible():
                        log.info(f"[Gemini] Completion: scoped copy/share button found ({sel!r})")
                        return True
                except Exception:
                    pass

        # 3. Content-based: body text threshold.
        #    DR mode: require 50 000 chars (large prompt echo + Thinking text can push
        #    body to 15-25 k before research actually produces a substantial report).
        #    Non-DR: 15 000 chars is sufficient (page chrome ≈ 3-4 k).
        #    GUARD: require _seen_stop so this does not fire while the plan/prompt echo
        #    is still on screen before actual research begins.
        try:
            body_len = await page.evaluate("document.body.innerText.length")
            threshold = 50000 if self._deep_mode else 15000
            if body_len > threshold and self._seen_stop:
                log.info(f"[Gemini] Body text {body_len} > {threshold} after research started — declaring complete")
                return True
        except Exception:
            pass

        # 4. Stable-state: no stop/cancel/thinking for N consecutive polls.
        #    REQUIRES _seen_stop — i.e. the stop button was previously visible,
        #    meaning research actually started and finished.
        #    DR mode: 90 polls (15 min) — Gemini briefly hides progress indicators
        #    between research phases; a 5-min window (30 polls) fires too early.
        #    Only declare via this path if body text is substantial (> 30k) OR
        #    after a very long wait — the body > 50k check (#3) handles early completion.
        #    Non-DR mode: 3 polls (30s) is sufficient (regular responses finish quickly).
        stable_threshold = 90 if self._deep_mode else 3
        if self._no_stop_polls >= stable_threshold and self._seen_stop:
            log.info(f"[Gemini] No stop button for {stable_threshold} polls after research started — declaring complete")
            return True

        # 5a. Quick-response fallback: if _seen_stop was never set (no DR started) but body
        #     has substantial content, Gemini gave a regular response instead of DR
        #     (e.g. DR daily cap exhausted).  Don't waste 30 min — declare after 6 stable polls.
        #
        #     EXCEPTION: if _dr_start_unconfirmed is True, "Start research" was clicked but the
        #     Stop/Cancel button was not confirmed within 60s (likely because the tab was
        #     backgrounded in a parallel run and Angular hadn't rendered the DR progress UI yet).
        #     In that case, skip this fast-exit and allow the full no_stop_limit (180 polls)
        #     so that DR has time to surface.  Also bring the tab to front on early polls so
        #     Gemini's SPA can render the DR progress indicators.
        if not self._seen_stop and body_len_check > 5000 and self._no_stop_polls >= 6:
            if self._dr_start_unconfirmed:
                # Attempt to bring tab to front periodically so DR progress renders
                if self._no_stop_polls in (6, 12, 24, 48):
                    try:
                        await page.bring_to_front()
                        log.debug(f"[Gemini] _dr_start_unconfirmed — brought tab to front at poll {self._no_stop_polls}")
                    except Exception:
                        pass
                log.debug(f"[Gemini] _dr_start_unconfirmed — suppressing quick-response fallback at poll {self._no_stop_polls}")
            else:
                log.info(f"[Gemini] No DR indicators seen, body {body_len_check}c stable for 6 polls — quick/regular response, declaring complete")
                return True

        # 5. Extended fallback: if still no stop/cancel/thinking signal seen after
        #    N polls, something is wrong (post_send may have missed "Start research",
        #    or the DR UI changed).  Declare complete.
        #    DR mode: 180 polls (~30 min) — Gemini DR for complex prompts can take
        #    25-35 min; raised from 120 because research was being cut off mid-run.
        #    Non-DR mode: 40 polls (~6.7 min).
        no_stop_limit = 180 if self._deep_mode else 40
        if self._no_stop_polls >= no_stop_limit:
            log.warning(f"[Gemini] {no_stop_limit} polls with no stop/cancel/thinking ever seen — declaring complete.")
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
