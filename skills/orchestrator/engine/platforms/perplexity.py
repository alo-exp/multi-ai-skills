"""Perplexity AI platform automation."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from .base import BasePlatform
from prompt_echo import is_prompt_echo

log = logging.getLogger(__name__)


class Perplexity(BasePlatform):
    name = "perplexity"

    def __init__(self):
        super().__init__()
        self._no_stop_polls: int = 0  # Consecutive polls with no stop button visible
        self._last_page_len: int = 0  # Track page text length between polls for growth detection

    async def check_rate_limit(self, page: Page) -> str | None:
        """Check for Perplexity-specific rate limit indicators.

        Covers both Pro search quota exhaustion and free-tier limits.
        """
        patterns = [
            "Pro search limit",
            "limit reached",
            "upgrade to Pro",
            "daily limit",
            "out of Pro searches",
            # Additional patterns observed in testing
            "out of searches",
            "searches remaining",
            "free searches",
            "You've used all",
            "You've reached your",
            "search limit",
        ]
        for pattern in patterns:
            try:
                el = page.get_by_text(pattern, exact=False).first
                if await el.count() > 0 and await el.is_visible():
                    return pattern
            except Exception:
                pass
        return None

    async def configure_mode(self, page: Page, mode: str) -> str:
        """Select Sonar model; optionally enable Research toggle.

        Guards strictly against accidentally selecting the "Perplexity Computer"
        feature — that is a paid/credit feature unrelated to chat responses.
        """
        model_selected = ""

        # --- Model selection (optional — skip if picker unavailable) ---
        try:
            # Try known model selector entry points
            model_btn = None
            for sel in [
                'button[data-testid="model-selector"]',
                'button:has-text("Model")',
                '[aria-label*="model" i]',
            ]:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible(timeout=2000):
                    model_btn = btn
                    break

            if model_btn is not None:
                await model_btn.click()
                await page.wait_for_timeout(600)

                # Find all visible model options and pick the safest Sonar variant.
                # CRITICAL: skip any option containing "computer" (case-insensitive) —
                # that is the "Perplexity Computer" paid feature, not a chat model.
                chosen = False
                for candidate_text in ["Sonar Pro", "Sonar"]:
                    options = page.get_by_text(candidate_text, exact=False)
                    count = await options.count()
                    for i in range(count):
                        opt = options.nth(i)
                        if not await opt.is_visible(timeout=1000):
                            continue
                        label = (await opt.inner_text()).strip().lower()
                        if "computer" in label:
                            log.warning(f"[Perplexity] Skipping option '{label}' — contains 'computer'")
                            continue
                        await opt.click()
                        model_selected = candidate_text
                        log.info(f"[Perplexity] Selected model: {candidate_text}")
                        chosen = True
                        break
                    if chosen:
                        break

                if not chosen:
                    # Close picker without selecting; proceed with page default
                    await page.keyboard.press("Escape")
                    log.info("[Perplexity] No safe Sonar option found — using page default")

                await page.wait_for_timeout(500)

        except Exception as exc:
            log.warning(f"[Perplexity] Model selection failed: {exc} — proceeding with default")

        # --- DEEP mode: try to enable Research toggle ---
        # Guard: only click an option that clearly refers to Research and NOT Computer.
        if mode == "DEEP":
            try:
                research_enabled = False
                for candidate_text in ["Deep Research", "Research"]:
                    toggles = page.get_by_text(candidate_text, exact=False)
                    count = await toggles.count()
                    for i in range(count):
                        tog = toggles.nth(i)
                        if not await tog.is_visible(timeout=1000):
                            continue
                        label = (await tog.inner_text()).strip().lower()
                        if "computer" in label:
                            log.warning(f"[Perplexity] Skipping research toggle '{label}' — contains 'computer'")
                            continue
                        await tog.click()
                        log.info(f"[Perplexity] Enabled: {label}")
                        research_enabled = True
                        break
                    if research_enabled:
                        break
                if not research_enabled:
                    log.info("[Perplexity] Research toggle not found — proceeding without")
            except Exception as exc:
                log.info(f"[Perplexity] Research toggle error (non-fatal): {exc}")

        label = model_selected or "Sonar (default)"
        return label + (" + Research" if mode == "DEEP" else "")

    async def inject_prompt(self, page: Page, prompt: str) -> None:
        """Inject prompt into Perplexity input.

        Newer Perplexity UI uses a textarea at the bottom of the page.
        Try textarea first (preferred for new UI), then fall back to contenteditable.
        """
        # Wait for input area to be ready — fresh page loads can be slow
        try:
            await page.wait_for_selector(
                'textarea, div[contenteditable="true"]',
                state="visible", timeout=10000,
            )
        except Exception:
            pass

        # Primary: textarea (new Perplexity UI — home page and conversation page)
        for ta_sel in [
            'textarea[placeholder*="Ask"]',
            'textarea[placeholder*="Search"]',
            'textarea[placeholder*="Message"]',
            'textarea',
        ]:
            ta = page.locator(ta_sel).first
            if await ta.count() > 0 and await ta.is_visible(timeout=2000):
                await ta.click()
                await page.wait_for_timeout(200)
                await ta.fill(prompt)
                # Dispatch input event so React state updates
                await ta.dispatch_event("input")
                log.info(f"[Perplexity] Filled textarea ({ta_sel}) with {len(prompt)} chars")
                return

        # Fallback: contenteditable (older Perplexity UI variant)
        ce = page.locator('div[contenteditable="true"]').first
        if await ce.count() > 0 and await ce.is_visible(timeout=2000):
            await self._inject_exec_command(page, prompt)
            return

        raise RuntimeError("No input element found on Perplexity")

    async def click_send(self, page: Page) -> None:
        """Click send button or press Enter."""
        # Try finding send/search button
        for selector in [
            'button[aria-label*="Submit"]',
            'button[aria-label*="Send"]',
            'button[aria-label*="Search"]',
            'button[aria-label*="Ask"]',
        ]:
            btn = page.locator(selector).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                return

        # Fallback: find by role
        for text in ["Submit", "Send", "Search", "Ask"]:
            btn = page.get_by_role("button", name=text).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
                return

        # Agent fallback: vision-based button finding before Enter
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

        # Last resort: press Enter (Perplexity submits on Enter)
        await page.keyboard.press("Enter")

    async def completion_check(self, page: Page) -> bool:
        """Check if response is complete — growth-based detection.

        Perplexity shows the prompt text on the page immediately, so we
        cannot use static length thresholds. Instead we track whether page
        text is still growing between polls.
        """
        # 1. Look for stop/cancel button (indicates still generating)
        has_stop = False
        for sel in ['button:has-text("Stop")', 'button:has-text("Cancel")']:
            try:
                stop = page.locator(sel).first
                if await stop.count() > 0 and await stop.is_visible():
                    has_stop = True
                    break
            except Exception:
                pass

        if has_stop:
            self._no_stop_polls = 0
            return False

        self._no_stop_polls += 1

        # 2. Track page text growth — if still growing, still generating
        try:
            page_len = await page.evaluate("document.body.innerText.length")
            if page_len > self._last_page_len:
                log.debug(f"[Perplexity] Page text growing: {self._last_page_len} → {page_len}")
                self._last_page_len = page_len
                self._no_stop_polls = 0
                return False
        except Exception:
            pass

        # Need current URL for checks 3 and 4 — compute once here
        current_url = page.url
        is_on_conversation = (
            "perplexity.ai/search" in current_url
            or "perplexity.ai/p/" in current_url
        )

        # 3. Check for "Sources" section + substantial prose content
        # Citations can appear while Perplexity is still generating — require
        # both citations AND substantial .prose content (> 3000 chars).
        # ALSO require is_on_conversation to avoid firing on a reused tab
        # that has old conversation content loaded (citations + prose already > 3000).
        try:
            sources = page.locator('[class*="source"], [class*="citation"]')
            source_count = await sources.count()
            if source_count >= 2 and is_on_conversation:
                prose_len = 0
                try:
                    prose = page.locator('.prose, [class*="prose"]').first
                    if await prose.count() > 0:
                        prose_len = await prose.evaluate("el => el.innerText.length")
                except Exception:
                    pass
                if prose_len > 3000:
                    log.info(f"[Perplexity] {source_count} citations + {prose_len} chars prose — declaring complete")
                    return True
                else:
                    log.debug(f"[Perplexity] {source_count} citations but prose only {prose_len} chars — waiting")
        except Exception:
            pass

        # 4. Stable-state: page text stopped growing for 6 consecutive polls (~60s).
        #    Require a larger threshold (> 10 000 chars) so pre-loaded old-session
        #    content (from a reused tab) does not trigger premature completion.
        #    Also verify the page URL is NOT the plain homepage — if we're still on
        #    the root URL the query may not have been submitted yet.
        if self._no_stop_polls >= 6 and self._last_page_len > 10000 and is_on_conversation:
            log.info(f"[Perplexity] Page text stable at {self._last_page_len} chars for 6 polls on conversation page — declaring complete")
            return True

        # Extended stable-state: 12 polls (~120s) regardless of page length
        if self._no_stop_polls >= 12:
            log.info("[Perplexity] No activity for 12 polls — declaring complete")
            return True

        return False

    async def extract_response(self, page: Page) -> str:
        """Extract from .prose container or full page text."""
        # Primary: .prose selector — join ALL prose divs (response can span multiple).
        # A single response is split across many .prose elements; taking only the last
        # one discards most of the content (seen in iters 19-20: 1k instead of 80k+).
        try:
            prose_els = page.locator('.prose')
            count = await prose_els.count()
            if count > 0:
                parts = []
                for i in range(count):
                    try:
                        t = await prose_els.nth(i).inner_text()
                        if t.strip():
                            parts.append(t)
                    except Exception:
                        pass
                text = "\n\n".join(parts)
                if len(text) > 500:
                    log.info(f"[Perplexity] Extracted {len(text)} chars via .prose (all {count} divs joined)")
                    return text
        except Exception as exc:
            log.warning(f"[Perplexity] .prose extraction failed: {exc}")

        # Fallback: try [class*="prose"] — join all elements
        try:
            prose_alt_els = page.locator('[class*="prose"]')
            alt_count = await prose_alt_els.count()
            if alt_count > 0:
                parts = []
                for i in range(alt_count):
                    try:
                        t = await prose_alt_els.nth(i).inner_text()
                        if t.strip():
                            parts.append(t)
                    except Exception:
                        pass
                text = "\n\n".join(parts)
                if len(text) > 500:
                    log.info(f"[Perplexity] Extracted {len(text)} chars via [class*=prose] (all {alt_count} divs joined)")
                    return text
        except Exception:
            pass

        # Tertiary: try main content area (exclude sidebar/history)
        try:
            text = await page.evaluate("""
                (() => {
                    const main = document.querySelector('main')
                               || document.querySelector('[class*="answer"]')
                               || document.querySelector('[class*="result"]');
                    if (main) return main.innerText;
                    return '';
                })()
            """)
            if text and len(text) > 200:
                log.info(f"[Perplexity] Extracted {len(text)} chars via main container")
                return text
        except Exception:
            pass

        # Last resort: full page inner text (with prompt-echo guard)
        text = await page.evaluate("document.body.innerText")
        if is_prompt_echo(text, self.prompt_sigs):
            log.warning("[Perplexity] body.innerText appears to be a prompt echo — returning as-is (no better option)")
        log.info(f"[Perplexity] Extracted {len(text)} chars via body.innerText")
        return text
