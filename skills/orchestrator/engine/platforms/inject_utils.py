"""Injection helper mixin — low-level prompt-injection strategies."""

from __future__ import annotations

import logging
import subprocess
import sys

from playwright.async_api import Page

log = logging.getLogger(__name__)


class InjectMixin:
    """Mixin providing prompt-injection helpers for BasePlatform subclasses."""

    async def _inject_exec_command(self, page: Page, prompt: str) -> int:
        """Inject into a contenteditable div via document.execCommand.

        Returns verified char count. If execCommand silently fails (deprecated
        API), automatically falls back to clipboard-paste injection.
        """
        success = await page.evaluate("""(prompt) => {
            const el = document.querySelector('div[contenteditable="true"]')
                      || document.querySelector('[contenteditable="true"]');
            if (!el) throw new Error('No contenteditable element found');
            el.focus();
            document.execCommand('selectAll', false, null);
            const ok = document.execCommand('insertText', false, prompt);
            return ok;
        }""", prompt)

        length = await page.evaluate("""
            (document.querySelector('div[contenteditable="true"]')
             || document.querySelector('[contenteditable="true"]')).textContent.length
        """)

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

        # SECURITY NOTE: This method temporarily writes the full prompt to the OS clipboard.
        # Clipboard-history tools running concurrently may capture the content.
        # This injection method is a last resort — prefer _inject_exec_command.
        # Clipboard is restored to its prior content after paste where supported.
        """
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=prompt.encode("utf-8"), timeout=5, check=True)
        elif sys.platform == "linux":
            for cmd in [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["wl-copy"]]:
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
        await textarea.type(prompt, delay=5)
        log.info(f"[{self.display_name}] Typed {len(prompt)} chars physically")

    async def _inject_fill(self, page: Page, prompt: str) -> None:
        """Fill a React textarea using Playwright's fill() (triggers React state)."""
        textarea = page.locator("textarea").first
        await textarea.click()
        await page.wait_for_timeout(300)
        await textarea.fill(prompt)
        await textarea.dispatch_event("input")
        log.info(f"[{self.display_name}] Filled textarea with {len(prompt)} chars")
