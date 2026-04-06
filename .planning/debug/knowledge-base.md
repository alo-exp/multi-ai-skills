# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## deepseek-premature-completion — DeepSeek stable-state fallback fires at 51s while still generating
- **Date:** 2026-04-06
- **Error patterns:** premature completion, stable-state fallback, no stop button, ds-icon-button, SVG icon button, completion_check, _no_stop_polls, DeepThink, truncated response
- **Root cause:** DeepSeek's stop button is a ds-icon-button (div[role="button"] with class ds-icon-button) containing only an SVG icon — no text and no aria-label="Stop". All stop-detection selectors used text matching or aria-label substring which fail against a text-free SVG icon button. The stable-state threshold of 6 polls (60s) is also too low for DEEP mode responses (3-5 minutes).
- **Fix:** (1) JS DOM walk from textarea to find ds-icon-button in input container for stop detection. (2) Stable-state threshold scaled to max(6, max(60, max_wait_s // 2) // POLL_INTERVAL) — DEEP mode gets 30 polls (300s). (3) base.py stores max_wait_s as self._current_max_wait_s for subclass access.
- **Files changed:** skills/orchestrator/engine/platforms/deepseek.py, skills/orchestrator/engine/platforms/base.py
---

## deepseek-stop-detection-false-positive — DeepSeek SEND button mistaken for STOP button causes 600s timeout
- **Date:** 2026-04-06
- **Error patterns:** timed out after 600s, has_stop always True, ds-icon-button, completion_check, send button, stop button, false positive, DOM walk, input container
- **Root cause:** The JS DOM walk added in cd2a6a4 matched any visible ds-icon-button in the input container — but the SEND button has the same class and is always visible after generation ends. No DOM difference exists between SEND and STOP using class/visibility alone. has_stop was always True, so completion was never declared.
- **Fix:** Replace generic ds-icon-button JS walk with SVG-shape discriminator: stop button SVG contains a rect element (square icon), send button contains only path elements (arrow). JS checks btn.querySelector('svg rect') — only true during generation. Added text-growth tracking (3 stable polls + >500 chars) as secondary completion signal.
- **Files changed:** skills/orchestrator/engine/platforms/deepseek.py
---
