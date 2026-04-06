---
status: resolved
trigger: "deepseek-stop-detection-false-positive"
created: 2026-04-06T00:00:00Z
updated: 2026-04-06T00:00:00Z
---

## Current Focus

hypothesis: The DS icon-button JS DOM walk (cd2a6a4) cannot distinguish the SEND button from the STOP button — both are ds-icon-button in the input container. The send button is always visible after generation ends, so has_stop is always True, preventing completion.
test: Read completion_check() in deepseek.py — confirmed the JS walk returns true for any visible ds-icon-button in input container, including the permanently-present send button.
expecting: Fix by removing the ds-icon-button JS walk and instead using: (1) Copy/Regenerate first (already done), (2) text-growth tracking as secondary, (3) stable-state fallback.
next_action: Apply fix — remove JS DOM walk from Step 2, add text-growth tracking.

## Symptoms

expected: completion_check() returns True when DeepSeek finishes generating.
actual: completion_check() returns False for the entire 600s timeout — SEND button (ds-icon-button) is always visible in input container after generation ends.
errors: "WARNING [DeepSeek] Timed out after 600s" despite complete 5568-char response.
reproduction: Run orchestrator DEEP mode targeting DeepSeek after it finishes generating.
started: Introduced by cd2a6a4 (v0.2.26040629).

## Eliminated

- hypothesis: Text-based Stop selectors would work
  evidence: DeepSeek uses SVG-only buttons with no text/aria-label for stop
  timestamp: 2026-04-06

## Evidence

- timestamp: 2026-04-06
  checked: completion_check() lines 200-222
  found: JS walk traverses up to 6 levels from textarea, returns true for ANY visible ds-icon-button — this includes the send button which is always present after generation
  implication: has_stop is always True after generation ends; completion never declared

- timestamp: 2026-04-06
  checked: Step 1 (lines 176-186)
  found: Copy/Regenerate button check is already first — correct. But it uses :has-text() which should work for visible text buttons.
  implication: Step 1 may be failing too if DeepSeek's buttons don't match these selectors

## Resolution

root_cause: The JS DOM walk in Step 2 matches the always-present SEND button (ds-icon-button class, visible, in input container) identically to the STOP button. There is no reliable DOM difference between them using class/visibility alone.
fix: |
  1. Removed the "any visible ds-icon-button in input container" check that caused the false-positive.
  2. Replaced with SVG-shape check: stop button SVG contains a <rect> element (square icon), send button SVG contains only <path> (arrow). The JS now checks btn.querySelector('svg rect') — only true during generation.
  3. Added text-growth tracking (Step 4): tracks body.innerText.length between polls. If stable for 3 consecutive polls and >500 chars, declares complete. Resets on any growth.
  4. Added _prev_text_len and _stable_text_polls instance vars.
  5. Stable-state fallback (Step 5) retained as last-resort safeguard.
verification: confirmed by user — fix committed as v0.2.26040630; SVG rect discriminator verified correct
files_changed: [skills/orchestrator/engine/platforms/deepseek.py]
