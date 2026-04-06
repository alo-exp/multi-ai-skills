"""ChatGPT platform automation."""

from __future__ import annotations

import logging
import subprocess
import sys

from playwright.async_api import Page

from .base import BasePlatform
from prompt_echo import is_prompt_echo

log = logging.getLogger(__name__)


def _read_clipboard() -> str:
    """Read system clipboard content (cross-platform)."""
    try:
        if sys.platform == "darwin":
            result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            return result.stdout if result.returncode == 0 else ""
        elif sys.platform == "linux":
            for cmd in [
                ["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "--clipboard", "--output"],
                ["wl-paste"],
            ]:
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    if r.returncode == 0:
                        return r.stdout
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
        elif sys.platform == "win32":
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout if result.returncode == 0 else ""
    except Exception:
        pass
    return ""


class ChatGPT(BasePlatform):
    name = "chatgpt"

    def __init__(self):
        super().__init__()
        self._no_stop_polls: int = 0  # Consecutive polls with no stop button visible
        self._seen_stop: bool = False  # True once a stop/progress button was visible
        self._mode: str = ""          # Stored in configure_mode; used by extract_response
        self._conversation_id: str = ""  # Captured from page URL after prompt submit

    async def check_rate_limit(self, page: Page) -> str | None:
        """Check for ChatGPT-specific rate limit indicators.

        Covers both hard rate limits (usage cap) and Deep Research quota
        exhaustion ("lighter version of deep research" message), which
        causes DR to silently degrade without triggering a stop button.
        """
        patterns = [
            # Hard rate limits
            "You've reached the current usage cap",
            "usage cap",
            "limit reached",
            "too many messages",
            "come back later",
            # Deep Research quota exhaustion (account-level, not engine-level)
            "lighter version of deep research",
            "remaining queries are powered by",
            "full access resets on",
            "Your remaining queries",
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
        """Enable Deep Research (DEEP) or select reasoning model (REGULAR)."""
        self._mode = mode  # Store so extract_response knows the current mode
        if mode == "DEEP":
            try:
                # Click + button to open picker
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
            # REGULAR mode: try to select reasoning model (o3/o4-mini)
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
        """Install blob interceptor for DEEP mode extraction.

        Uses duck-typing (blob.size !== undefined) instead of instanceof Blob
        to handle File and MediaSource objects that also pass through
        createObjectURL.  Both the capture and the original call are wrapped
        in try-catch so a bad argument never breaks the interceptor itself.
        """
        if mode == "DEEP":
            try:
                await page.evaluate("""
                    (() => {
                        const origCreateObjectURL = URL.createObjectURL.bind(URL);
                        window.__capturedBlobs = [];
                        URL.createObjectURL = function(obj) {
                            // Duck-type check: Blob, File and MediaSource all have .size
                            try {
                                if (obj && typeof obj.size === 'number') {
                                    const reader = new FileReader();
                                    reader.onload = (e) => {
                                        window.__capturedBlobs.push({
                                            size: obj.size,
                                            type: obj.type || '',
                                            text: e.target.result
                                        });
                                    };
                                    reader.readAsText(obj);
                                }
                            } catch (captureErr) {
                                // Silently ignore capture errors — never break page behaviour
                            }
                            try {
                                return origCreateObjectURL(obj);
                            } catch (e) {
                                // Re-raise so the calling page code sees the original error
                                throw e;
                            }
                        };
                    })();
                """)
                log.info("[ChatGPT] Blob interceptor installed for Deep Research extraction")
            except Exception as exc:
                log.warning(f"[ChatGPT] Blob interceptor installation failed: {exc}")

        # Capture conversation ID from URL — ChatGPT navigates to /c/CONV_ID after submit.
        # Wait up to 15s for the URL to change (new conversation URL).
        for _ in range(15):
            await page.wait_for_timeout(1000)
            url = page.url
            if "/c/" in url:
                conv_id = url.split("/c/")[-1].split("?")[0].split("#")[0]
                if conv_id:
                    self._conversation_id = conv_id
                    log.info(f"[ChatGPT] Captured conversation ID: {conv_id}")
                    break

    async def _extract_deep_research_panel(self, page: Page) -> str:
        """
        Extract Deep Research content from the cross-origin iframe panel.
        Three-layer approach (most to least robust):
          A) frame.evaluate() — direct CDP text extraction, no interaction needed
          B) frame_locator selector-based button click → clipboard
          C) Coordinate-based click → clipboard (calibrated from Harness OSS run)

        Frames are iterated in REVERSE order (most-recently added first) so the
        current conversation's DR iframe is tried before any stale iframe from a
        previous conversation that may still be loaded in memory.

        If all methods return < 1000 chars (new DR iframe not yet populated),
        waits 10s and retries once before giving up.
        """
        # URL substrings known to appear in ChatGPT DR iframe src attributes.
        # Kept broad to survive ChatGPT URL scheme changes.
        _DR_PATTERNS = ["web-sandbox", "deep_research", "oaiusercontent.com", "blob:"]

        # Inner function: one extraction attempt across all three methods
        async def _try_extract() -> str:
            # --- A: Direct CDP frame text extraction (no clicks required) ---
            # Find the NEWEST DR iframe (last in page.frames list = most recently added).
            # Step 1: look for a frame matching known DR URL patterns.
            # Step 2 (fallback): look for any non-main frame with large non-echo content.
            newest_dr_frame = None
            for frame in reversed(page.frames):
                if frame.url.startswith("https://chatgpt.com") and frame.parent_frame is None:
                    continue  # skip main frame
                if any(pat in frame.url for pat in _DR_PATTERNS):
                    newest_dr_frame = frame
                    break
            if newest_dr_frame is None:
                # Fallback: scan all child/sub-frames for large non-echo content
                log.debug("[ChatGPT] No DR-pattern frame found — scanning all child frames")
                for frame in reversed(page.frames):
                    if frame.parent_frame is None:
                        continue  # skip main frame
                    if frame.url.startswith("https://chatgpt.com") or frame.url in ("", "about:blank"):
                        continue
                    try:
                        flen = await frame.evaluate("document.body.innerText.length")
                        if flen > 1000:
                            newest_dr_frame = frame
                            log.debug(f"[ChatGPT] Using child frame as DR: {frame.url[:80]} ({flen}c)")
                            break
                    except Exception:
                        pass

            if newest_dr_frame is not None:
                try:
                    text = await newest_dr_frame.evaluate("document.body.innerText")
                    if text and len(text) > 1000 and not is_prompt_echo(text, self.prompt_sigs):
                        log.info(f"[ChatGPT] Extracted {len(text)} chars via frame.evaluate() (frame: {newest_dr_frame.url[:60]})")
                        return text
                    log.debug(f"[ChatGPT] Newest DR frame has {len(text) if text else 0} chars ({newest_dr_frame.url[:60]})")
                    # Don't fall through to older DR frames — return "" so outer retry waits.
                    return ""
                except Exception as exc:
                    log.debug(f"[ChatGPT] frame.evaluate() failed ({newest_dr_frame.url[:60]}): {exc}")

            # --- B: frame_locator selector-based button click + clipboard ---
            # Use "last" iframe matching the pattern (most recent DR for this conversation).
            for url_pat in _DR_PATTERNS:
                try:
                    dr_frame = page.frame_locator(f'iframe[src*="{url_pat}"]').last
                    for dl_sel in [
                        '[aria-label*="Download"]',
                        '[aria-label*="Export"]',
                        '[title*="Download"]',
                        '[title*="Export"]',
                    ]:
                        dl_btn = dr_frame.locator(dl_sel).first
                        if await dl_btn.count() > 0:
                            await dl_btn.click()
                            await page.wait_for_timeout(500)
                            log.info(f"[ChatGPT] Clicked DR download button via frame_locator ({dl_sel})")
                            for copy_text in ["Copy contents", "Copy"]:
                                copy_item = dr_frame.get_by_text(copy_text, exact=False).first
                                if await copy_item.count() > 0:
                                    await copy_item.click()
                                    await page.wait_for_timeout(1000)
                                    text = _read_clipboard()
                                    if text and len(text) > 1000 and not is_prompt_echo(text, self.prompt_sigs):
                                        log.info(f"[ChatGPT] Extracted {len(text)} chars via frame_locator + clipboard")
                                        return text
                except Exception as exc:
                    log.debug(f"[ChatGPT] frame_locator method failed (pat={url_pat}): {exc}")

            # --- C: Coordinate-based fallback (proportional offsets relative to iframe) ---
            # Uses percentage-based offsets instead of hardcoded pixels so it adapts
            # to different window sizes and DR panel redesigns.  After clicking the
            # download-icon area, waits for a dropdown menu to appear before clicking
            # the "Copy contents" item (avoids blind second click).
            try:
                rect = await page.evaluate("""
                    (() => {
                        const iframe = document.querySelector('iframe[src*="web-sandbox"]')
                                     || document.querySelector('iframe[src*="deep_research"]')
                                     || document.querySelector('iframe[src*="openai"]');
                        if (!iframe) return null;
                        const r = iframe.getBoundingClientRect();
                        return { top: r.top, right: r.right, bottom: r.bottom,
                                 left: r.left, width: r.width, height: r.height };
                    })()
                """)
                if not rect:
                    log.debug("[ChatGPT] DR iframe not found for coordinate extraction")
                    return ""

                # Download icon: near top-right corner of the iframe header.
                # Use proportional offsets: ~95% of width from left, ~3% of height from top
                # (clamped to minimum 10px from edges).
                dl_x = rect["left"] + max(rect["width"] * 0.95, rect["width"] - 40)
                dl_y = rect["top"] + max(rect["height"] * 0.03, 10)
                await page.mouse.click(dl_x, dl_y)
                await page.wait_for_timeout(800)
                log.info(f"[ChatGPT] Clicked DR download icon at ({dl_x:.0f}, {dl_y:.0f}) [proportional coordinate]")

                # Wait for "Copy contents" / "Copy" text to appear in a dropdown menu
                # rather than blind-clicking a hardcoded offset.
                copied = False
                for copy_text in ["Copy contents", "Copy"]:
                    try:
                        copy_item = page.get_by_text(copy_text, exact=False).first
                        if await copy_item.count() > 0 and await copy_item.is_visible():
                            await copy_item.click()
                            await page.wait_for_timeout(1000)
                            log.info(f"[ChatGPT] Clicked '{copy_text}' via text selector after coordinate click")
                            copied = True
                            break
                    except Exception:
                        pass

                if not copied:
                    # Fallback: click below the download icon (menu didn't render with
                    # text-searchable elements, or it uses a canvas/shadow DOM).
                    copy_x = dl_x - min(rect["width"] * 0.08, 115)
                    copy_y = dl_y + min(rect["height"] * 0.06, 45)
                    await page.mouse.click(copy_x, copy_y)
                    await page.wait_for_timeout(1000)
                    log.info(f"[ChatGPT] Clicked 'Copy contents' at ({copy_x:.0f}, {copy_y:.0f}) [blind offset]")

                text = _read_clipboard()
                if text and len(text) > 1000 and not is_prompt_echo(text, self.prompt_sigs):
                    log.info(f"[ChatGPT] Extracted {len(text)} chars via coordinate fallback + clipboard")
                    return text

                log.debug(f"[ChatGPT] Coordinate fallback clipboard: {len(text) if text else 0} chars — insufficient")
                return ""
            except Exception as exc:
                log.debug(f"[ChatGPT] Coordinate fallback failed: {exc}")
                return ""

        # First extraction attempt
        result = await _try_extract()
        if result:
            return result

        # If all methods returned empty, the newest DR iframe is not yet populated.
        # Retry up to 12 times with 30s waits (6 min total) before giving up.
        # Rationale: completion_check fires ~2 min in (body>50k after stop gone 30s),
        # but ChatGPT DR typically takes 5-10 min to populate the report iframe.
        for attempt in range(12):
            wait_s = 30
            log.info(f"[ChatGPT] DR panel empty (attempt {attempt + 1}/12) — waiting {wait_s}s...")
            await page.wait_for_timeout(wait_s * 1000)
            result = await _try_extract()
            if result:
                return result
        log.warning("[ChatGPT] DR panel never populated after 12 retries (6 min) — giving up")
        return ""

    async def completion_check(self, page: Page) -> bool:
        """Check for completion — uses multi-signal approach.

        Core logic: if no stop/progress button is visible for 3 consecutive
        polls (~30s), the response is done.  For large responses (> 2000 chars
        in article, or > 15000 chars body text), complete immediately.

        DEEP mode exception: body_len threshold is raised to 50000 because
        the echoed user prompt alone can push body text well past 15000 chars
        before the actual research is done.  Also tracks _seen_stop so that
        stable-state detection does not fire prematurely before research starts.

        This handles both:
        - Real Deep Research reports (large content → instant detect)
        - Quota/error messages (short content → stable-state detect after 30s)
        - Mid-streaming (stop button visible → counter resets)
        """
        # 1. Check for stop/cancel/progress button (still generating)
        has_stop = False
        stop_selectors = [
            'button:has-text("Stop")',
            'button:has-text("Cancel")',
            'button[aria-label*="Stop"]',
            'button[aria-label*="stop"]',
            # DR-specific progress indicators
            'button:has-text("Stop researching")',
            'button[aria-label*="Stop researching"]',
            '[class*="deep-research"] button:has-text("Stop")',
            # Additional cancel-style buttons for DR
            'button[aria-label*="Cancel"]',
            'button[aria-label*="cancel"]',
            '[aria-label="Stop generating"]',
            '[data-testid*="stop"]',
        ]
        for sel in stop_selectors:
            try:
                stop = page.locator(sel).first
                if await stop.count() > 0 and await stop.is_visible():
                    has_stop = True
                    break
            except Exception:
                pass

        # Also check for DR progress text (research is running but stop button may be hidden)
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

        # No stop button — increment stable-state counter
        self._no_stop_polls += 1

        # 2. Response article with substantial content → immediate complete
        # (skip in DEEP mode — DR lives in an iframe, not an article element)
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

        # 3. Body text threshold → immediate complete.
        # Regular mode: 15000 chars is enough (page chrome ≈ 7-8k).
        # DEEP mode: NOT used for completion — see check #4.
        if self._mode != "DEEP":
            try:
                body_len = await page.evaluate("document.body.innerText.length")
                if body_len > 15000:
                    log.info(f"[ChatGPT] Body text {body_len} > 15000 — declaring complete")
                    return True
            except Exception:
                pass

        # 4. Stable-state / DR-complete detection.
        # Regular mode: 3 polls (~30s) regardless.
        # DEEP mode: only declare complete when the DR iframe is POPULATED (> 5000c).
        #   Rationale: completion_check fires early (~40s) due to ephemeral stop button
        #   + old DR content in page body. The actual DR report takes 5-15 min to appear
        #   in the iframe. Polling the iframe here defers completion until DR is ready.
        #   Fallback: 60 polls (~10 min) without ever seeing a populated iframe.
        if self._mode == "DEEP":
            # Check newest DR iframe content — mirrors _try_extract step 1 + 2
            _DR_PAT = ["web-sandbox", "deep_research", "oaiusercontent.com", "blob:"]
            dr_frame_len = 0
            for _frame in reversed(page.frames):
                if _frame.parent_frame is None:
                    continue
                if _frame.url.startswith("https://chatgpt.com") or _frame.url in ("", "about:blank"):
                    continue
                if any(pat in _frame.url for pat in _DR_PAT):
                    try:
                        dr_frame_len = await _frame.evaluate("document.body.innerText.length")
                    except Exception:
                        pass
                    break
            if dr_frame_len == 0:
                # fallback: any cross-origin child frame with content
                for _frame in reversed(page.frames):
                    if _frame.parent_frame is None:
                        continue
                    if _frame.url.startswith("https://chatgpt.com") or _frame.url in ("", "about:blank"):
                        continue
                    try:
                        l = await _frame.evaluate("document.body.innerText.length")
                        if l > 1000:
                            dr_frame_len = l
                            break
                    except Exception:
                        pass
            if dr_frame_len > 5000:
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

    # Phrases that indicate Deep Research quota exhaustion rather than real content.
    _DR_QUOTA_PHRASES = (
        "lighter version of deep research",
        "remaining queries are powered by",
        "full access resets on",
        "your remaining queries",
    )

    async def extract_response(self, page: Page) -> str:
        """
        DEEP mode: DR panel download → 'Copy contents' → clipboard (primary),
                   then blob interceptor fallback.
        REGULAR mode: article[1].innerText (article[0]=prompt, article[1]=response).

        Quota-exhaustion guard: if DEEP mode and extracted text is short AND
        contains quota-exhaustion phrases, return a [RATE LIMITED] marker
        instead of a spuriously-successful short response.
        """
        # DEEP mode primary: DR panel download icon → 'Copy contents' → clipboard.
        # The DR report lives in a cross-origin iframe; this is the only reliable path.
        if self._mode == "DEEP":
            text = await self._extract_deep_research_panel(page)
            if text:
                return text

        # Try blob interceptor (DEEP secondary / any-mode fallback) — check the last captured blob
        try:
            blob_text = await page.evaluate("""
                (() => {
                    const blobs = window.__capturedBlobs || [];
                    if (blobs.length === 0) return null;
                    // Return the largest captured blob text
                    const best = blobs.reduce((a, b) => (a.size > b.size ? a : b));
                    return best.text || null;
                })()
            """)
            if blob_text and len(blob_text) > 1000:
                log.info(f"[ChatGPT] Extracted {len(blob_text)} chars via blob interceptor")
                return blob_text
        except Exception:
            pass

        # Try Export to Markdown button (DEEP mode)
        try:
            export_btn = page.locator('button[aria-label*="Export"], button[aria-label*="Download"]').first
            if await export_btn.count() > 0 and await export_btn.is_visible():
                await export_btn.click()
                await page.wait_for_timeout(500)

                md_option = page.get_by_text("Export to Markdown", exact=False).first
                if await md_option.count() > 0:
                    await md_option.click()
                    await page.wait_for_timeout(3000)  # FileReader needs time

                    # Check blob interceptor again
                    blob_text = await page.evaluate("""
                        (() => {
                            const blobs = window.__capturedBlobs || [];
                            if (blobs.length === 0) return null;
                            const best = blobs.reduce((a, b) => (a.size > b.size ? a : b));
                            return best.text || null;
                        })()
                    """)
                    if blob_text and len(blob_text) > 1000:
                        log.info(f"[ChatGPT] Extracted {len(blob_text)} chars via Export to Markdown")
                        return blob_text
        except Exception:
            pass

        # REGULAR mode primary: article[1].innerText (last article = AI response)
        # DEEP mode note: ChatGPT echoes the user prompt in an article element.
        # Skip any article whose text is the echoed research prompt.
        try:
            text = await page.evaluate("""
                (() => {
                    const articles = document.querySelectorAll('article');
                    if (articles.length === 0) return '';
                    // Get the LAST article (AI response, not user prompt)
                    const resp = articles[articles.length - 1].innerText || '';
                    return resp;
                })()
            """)
            is_echo = is_prompt_echo(text, self.prompt_sigs)
            # Long responses (> 3 000 chars) are real AI answers even if they reuse
            # the prompt's section-header phrases (e.g. the CMF prompt explicitly
            # instructs "SECTION A", "SECTION B" — so the AI response legitimately
            # contains those strings).  Only reject if it's short AND is an echo.
            # DEEP mode exception: if DR panel extraction already failed, article
            # content with a prompt echo is just the echoed research prompt
            # (the real DR report lives in the iframe, not an article). Always
            # reject echoes in DEEP mode here; the final body fallback has its
            # own guard that will correctly suppress or allow.
            allow_echo = (len(text) > 3000) and (self._mode != "DEEP")
            if text and len(text) > 500 and (not is_echo or allow_echo):
                # Handle DOM duplication — slice at "End of Report."
                end_idx = text.find("End of Report.")
                if end_idx > 0:
                    text = text[:end_idx + len("End of Report.")]
                log.info(f"[ChatGPT] Extracted {len(text)} chars via article selector")
                return text
        except Exception:
            pass

        # Secondary: try main/conversation area (exclude sidebar)
        try:
            text = await page.evaluate("""
                (() => {
                    // ChatGPT's main chat area
                    const main = document.querySelector('main')
                               || document.querySelector('[role="main"]');
                    if (main) return main.innerText;
                    return '';
                })()
            """)
            is_echo_main = is_prompt_echo(text, self.prompt_sigs)
            allow_echo_main = (len(text) > 3000) and (self._mode != "DEEP")
            if text and len(text) > 200 and (not is_echo_main or allow_echo_main):
                # Guard: if DEEP mode and the main container text contains DR
                # quota-exhaustion phrases, tag as rate-limited.  No length
                # threshold — main.innerText includes UI chrome (buttons,
                # sidebar labels) that easily exceeds 1 000 chars even when
                # the actual response is a 381-char quota message.  In DEEP
                # mode, a real DR report is extracted via _extract_deep_
                # research_panel() / blob interceptor, NOT this main-container
                # fallback — reaching here already implies DR didn't produce
                # content, so flagging quota phrases is always correct.
                if self._mode == "DEEP":
                    text_lower = text.lower()
                    for phrase in self._DR_QUOTA_PHRASES:
                        if phrase in text_lower:
                            log.warning(
                                f"[ChatGPT] DR quota exhausted detected in main container "
                                f"({len(text)} chars). Returning rate-limited marker."
                            )
                            return f"[RATE LIMITED] ChatGPT Deep Research quota exhausted. {text[:300]}"
                log.info(f"[ChatGPT] Extracted {len(text)} chars via main container")
                return text
        except Exception:
            pass

        # Last resort: full body text
        text = await page.evaluate("document.body.innerText")

        # DEEP mode guard: ChatGPT's Deep Research report lives inside a
        # cross-origin iframe (connector_openai_deep_research.web-sandbox.oaiusercontent.com).
        # body.innerText only sees the main-page chrome (~7-8 k chars) plus the
        # echoed user prompt — it cannot reach the iframe content.
        # If we're in DEEP mode and got nothing better, return "" so that
        # base.py triggers the Agent fallback (vision-based interaction
        # with the DR panel's download / "Copy contents" flow).
        # Only bail out if body is short (UI chrome only) AND is an echo.
        # If body is short but NOT an echo, there might be a brief response — use it.
        # If body is long but contains prompt section headers, the AI was
        # instructed to use those headers — not a real echo.
        if self._mode == "DEEP" and len(text) < 15000 and is_prompt_echo(text, self.prompt_sigs):
            log.warning(
                f"[ChatGPT] DEEP mode: DR panel + blob interceptor both failed. "
                f"body {len(text)} chars is short + prompt echo — returning empty to trigger Agent fallback."
            )
            return ""

        # REGULAR mode guard: body.innerText includes the full page — "You said: [prompt]"
        # followed by "ChatGPT said: [response]". Strip the sent-prompt preamble so
        # the AI's answer is what gets saved and consolidated.
        if self._mode != "DEEP" and is_prompt_echo(text, self.prompt_sigs):
            for marker in ("\nChatGPT said:\n", "\nChatGPT said:", "ChatGPT said:\n", "ChatGPT said:"):
                idx = text.find(marker)
                if idx != -1:
                    trimmed = text[idx + len(marker):].strip()
                    if trimmed and len(trimmed) > 200:
                        log.info(f"[ChatGPT] Stripped sent-prompt preamble — {len(trimmed)} chars of AI response remain")
                        text = trimmed
                        break

        log.info(f"[ChatGPT] Extracted {len(text)} chars via body.innerText")
        return text
