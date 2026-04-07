"""ChatGPT response extraction mixin — Deep Research panel and regular mode."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from prompt_echo import is_prompt_echo

log = logging.getLogger(__name__)

_DR_PATTERNS = ["web-sandbox", "deep_research", "oaiusercontent.com", "blob:"]


def _read_clipboard() -> str:
    """Read system clipboard content (cross-platform)."""
    import subprocess, sys
    try:
        if sys.platform == "darwin":
            r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            return r.stdout if r.returncode == 0 else ""
        elif sys.platform == "linux":
            for cmd in [["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"], ["wl-paste"]]:
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    if r.returncode == 0:
                        return r.stdout
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
        elif sys.platform == "win32":
            r = subprocess.run(["powershell", "-command", "Get-Clipboard"], capture_output=True, text=True, timeout=5)
            return r.stdout if r.returncode == 0 else ""
    except Exception:
        pass
    return ""


class ChatGPTExtractorMixin:
    """Mixin providing Deep Research panel extraction and extract_response for ChatGPT."""

    # Phrases that indicate Deep Research quota exhaustion.
    _DR_QUOTA_PHRASES = (
        "lighter version of deep research", "remaining queries are powered by",
        "full access resets on", "your remaining queries",
        "you've reached the current usage cap", "you've reached your limit",
        "usage cap", "reached your limit", "you're out of",
        "daily limit", "monthly limit", "research limit",
    )

    async def _extract_deep_research_panel(self, page: Page) -> str:
        """Extract Deep Research content from the cross-origin iframe panel (3-layer approach)."""
        async def _try_extract() -> str:
            # Layer A: Direct CDP frame.evaluate()
            newest_dr_frame = None
            for frame in reversed(page.frames):
                if frame.url.startswith("https://chatgpt.com") and frame.parent_frame is None:
                    continue
                if any(pat in frame.url for pat in _DR_PATTERNS):
                    newest_dr_frame = frame
                    break
            if newest_dr_frame is None:
                all_info = []
                for frame in page.frames:
                    if frame != page.main_frame:
                        try:
                            flen = await frame.evaluate("document.body.innerText.length")
                            all_info.append(f"{frame.url[:80]}({flen}c)")
                        except Exception:
                            all_info.append(f"{frame.url[:80]}(err)")
                log.info(f"[ChatGPT] Non-main frames: {' | '.join(all_info)}" if all_info else "[ChatGPT] No non-main frames found")
                for frame in reversed(page.frames):
                    if frame == page.main_frame:
                        continue
                    try:
                        flen = await frame.evaluate("document.body.innerText.length")
                        if flen > 2000:
                            newest_dr_frame = frame
                            log.info(f"[ChatGPT] Using non-main frame as DR fallback: {frame.url[:80]} ({flen}c)")
                            break
                    except Exception:
                        pass

            if newest_dr_frame is not None:
                try:
                    text = await newest_dr_frame.evaluate("document.body.innerText")
                    allow_echo = len(text) > 20000
                    if text and len(text) > 1000 and (not is_prompt_echo(text, self.prompt_sigs) or allow_echo):
                        log.info(f"[ChatGPT] Extracted {len(text)} chars via frame.evaluate()")
                        return text
                    return ""
                except Exception as exc:
                    log.debug(f"[ChatGPT] frame.evaluate() failed: {exc}")

            # Layer B: frame_locator + clipboard
            for url_pat in _DR_PATTERNS:
                try:
                    dr_frame = page.frame_locator(f'iframe[src*="{url_pat}"]').last
                    for dl_sel in ['[aria-label*="Download"]', '[aria-label*="Export"]',
                                   '[title*="Download"]', '[title*="Export"]']:
                        dl_btn = dr_frame.locator(dl_sel).first
                        if await dl_btn.count() > 0:
                            await dl_btn.click()
                            await page.wait_for_timeout(500)
                            for copy_text in ["Copy contents", "Copy"]:
                                copy_item = dr_frame.get_by_text(copy_text, exact=False).first
                                if await copy_item.count() > 0:
                                    await copy_item.click()
                                    await page.wait_for_timeout(1000)
                                    text = _read_clipboard()
                                    if text and len(text) > 1000 and not is_prompt_echo(text, self.prompt_sigs):
                                        log.info(f"[ChatGPT] Extracted {len(text)} chars via frame_locator+clipboard")
                                        return text
                except Exception as exc:
                    log.debug(f"[ChatGPT] frame_locator method failed (pat={url_pat}): {exc}")

            # Layer C: coordinate-based fallback
            try:
                rect = await page.evaluate("""(() => {
                    const iframe = document.querySelector('iframe[src*="web-sandbox"]')
                                 || document.querySelector('iframe[src*="deep_research"]')
                                 || document.querySelector('iframe[src*="openai"]');
                    if (!iframe) return null;
                    const r = iframe.getBoundingClientRect();
                    return {top:r.top,right:r.right,bottom:r.bottom,left:r.left,width:r.width,height:r.height};
                })()""")
                if not rect:
                    return ""
                dl_x = rect["left"] + max(rect["width"] * 0.95, rect["width"] - 40)
                dl_y = rect["top"] + max(rect["height"] * 0.03, 10)
                await page.mouse.click(dl_x, dl_y)
                await page.wait_for_timeout(800)
                copied = False
                for copy_text in ["Copy contents", "Copy"]:
                    try:
                        copy_item = page.get_by_text(copy_text, exact=False).first
                        if await copy_item.count() > 0 and await copy_item.is_visible():
                            await copy_item.click()
                            await page.wait_for_timeout(1000)
                            copied = True
                            break
                    except Exception:
                        pass
                if not copied:
                    copy_x = dl_x - min(rect["width"] * 0.08, 115)
                    copy_y = dl_y + min(rect["height"] * 0.06, 45)
                    await page.mouse.click(copy_x, copy_y)
                    await page.wait_for_timeout(1000)
                text = _read_clipboard()
                if text and len(text) > 1000 and not is_prompt_echo(text, self.prompt_sigs):
                    log.info(f"[ChatGPT] Extracted {len(text)} chars via coordinate fallback")
                    return text
                return ""
            except Exception as exc:
                log.debug(f"[ChatGPT] Coordinate fallback failed: {exc}")
                return ""

        result = await _try_extract()
        if result:
            return result

        for attempt in range(12):
            rate_msg = await self.check_rate_limit(page)
            if rate_msg:
                log.warning(f"[ChatGPT] Rate limit in DR retry loop (attempt {attempt+1}/12): {rate_msg!r}")
                return f"[RATE LIMITED] ChatGPT Deep Research quota exhausted. {rate_msg}"
            log.info(f"[ChatGPT] DR panel empty (attempt {attempt+1}/12) — waiting 30s...")
            await page.wait_for_timeout(30000)
            result = await _try_extract()
            if result:
                return result
        log.warning("[ChatGPT] DR panel never populated after 12 retries — giving up")
        return ""

    async def extract_response(self, page: Page) -> str:
        """Extract response: DR panel (DEEP) or article selector (REGULAR)."""
        if self._mode == "DEEP":
            try:
                body_quick = await page.evaluate("document.body.innerText")
                for phrase in self._DR_QUOTA_PHRASES:
                    if phrase in body_quick.lower():
                        log.warning(f"[ChatGPT] DR quota detected at extraction start: {phrase!r}")
                        return f"[RATE LIMITED] ChatGPT Deep Research quota exhausted. {body_quick[:500]}"
            except Exception:
                pass
            text = await self._extract_deep_research_panel(page)
            if text:
                return text

        # Blob interceptor fallback
        try:
            blob_text = await page.evaluate("""(() => {
                const blobs = window.__capturedBlobs || [];
                if (!blobs.length) return null;
                const best = blobs.reduce((a, b) => a.size > b.size ? a : b);
                return best.text || null;
            })()""")
            if blob_text and len(blob_text) > 1000:
                log.info(f"[ChatGPT] Extracted {len(blob_text)} chars via blob interceptor")
                return blob_text
        except Exception:
            pass

        # Article selector
        try:
            text = await page.evaluate("""(() => {
                const articles = document.querySelectorAll('article');
                if (!articles.length) return '';
                return articles[articles.length - 1].innerText || '';
            })()""")
            allow_echo = len(text) > 20000 if self._mode == "DEEP" else len(text) > 3000
            if text and len(text) > 500 and (not is_prompt_echo(text, self.prompt_sigs) or allow_echo):
                end_idx = text.find("End of Report.")
                if end_idx > 0:
                    text = text[:end_idx + len("End of Report.")]
                log.info(f"[ChatGPT] Extracted {len(text)} chars via article selector")
                return text
        except Exception:
            pass

        # Main container
        try:
            text = await page.evaluate("""(() => {
                const main = document.querySelector('main') || document.querySelector('[role="main"]');
                return main ? main.innerText : '';
            })()""")
            allow_echo = len(text) > 20000 if self._mode == "DEEP" else len(text) > 3000
            if text and len(text) > 200 and (not is_prompt_echo(text, self.prompt_sigs) or allow_echo):
                if self._mode == "DEEP":
                    for phrase in self._DR_QUOTA_PHRASES:
                        if phrase in text.lower():
                            return f"[RATE LIMITED] ChatGPT Deep Research quota exhausted. {text[:300]}"
                log.info(f"[ChatGPT] Extracted {len(text)} chars via main container")
                return text
        except Exception:
            pass

        # Last resort: body.innerText
        text = await page.evaluate("document.body.innerText")
        if self._mode != "DEEP" and is_prompt_echo(text, self.prompt_sigs):
            for marker in ("\nChatGPT said:\n", "\nChatGPT said:", "ChatGPT said:\n", "ChatGPT said:"):
                idx = text.find(marker)
                if idx != -1:
                    trimmed = text[idx + len(marker):].strip()
                    if trimmed and len(trimmed) > 200:
                        text = trimmed
                        break
        log.info(f"[ChatGPT] Extracted {len(text)} chars via body.innerText")
        return text
