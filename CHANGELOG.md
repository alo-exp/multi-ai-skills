# Changelog

All notable changes to MultAI are documented in this file.

Versioning scheme: `Major.Minor.YYMMDDX Phase` — see [CI/CD Strategy](docs/CICD-Strategy-and-Plan.md) Section 7.1.

---

## 0.2.26040604 Alpha — DEEP Mode Early Completion Fix, Perplexity Old-Content Fix, Chrome Focus Steal Fix

**Date:** 2026-04-06

### Fixes

- **ChatGPT DEEP mode premature completion**: `chatgpt.py` `completion_check` now tracks `_seen_stop`
  so stable-state detection requires research to have actually started. In DEEP mode, body-text
  threshold raised 15k → 50k (echoed prompt alone exceeded 15k), article check skipped (DR lives
  in iframe), stable-state extended from 3 → 12 polls after stop seen / 20 polls overall. Also
  detects "Stop researching", "Searching the web", "Reading", "Analyzing", "Researching" as
  in-progress signals.

- **Gemini DEEP mode premature completion via body text**: `gemini.py` `completion_check` body-text
  `> 15000` guard now requires `_seen_stop` (research started). Previously, the echoed prompt +
  Thinking phase text triggered this check during the plan phase (before "Start research" is
  clicked), causing extraction of plan/echo content instead of the completed research report.

- **Perplexity old-content extraction**: `perplexity.py` `extract_response` now uses the **last**
  `.prose` element instead of `.first` so old conversation content from a reused tab is not
  returned when the new response is appended after it. Also, the "sources + prose > 3000"
  completion check in `completion_check` now requires `is_on_conversation` (URL must contain
  `/search` or `/p/`) to prevent premature completion on a reused tab that already has sources
  and prose loaded from a prior session.

- **Chrome focus stealing**: `orchestrator.py` now minimizes Chrome windows via AppleScript
  (`set miniaturized of every window to true`) immediately after both fresh launches and CDP
  reuse on macOS. Playwright interacts via CDP and does not need Chrome in the foreground.

---

## 0.2.26040603 Alpha — ChatGPT Echo Detection Fix, Gemini Cancel Button, Perplexity Stable-State Guard

**Date:** 2026-04-06

### Fixes

- **ChatGPT false-positive echo rejection**: `chatgpt.py` `extract_response` article and main-
  container selectors now allow long responses (> 3 000 chars) even when they contain the
  prompt's section-header phrases (e.g. "SECTION A", "SECTION B"). Previously, prompts that
  explicitly instructed the AI to use those headers caused `is_prompt_echo` to return True on
  the actual response, resulting in 0 chars extracted for the CMF research prompt.  Also
  changed the DEEP-mode body-fallback guard from `len<15000 OR echo` to `len<15000 AND echo`.

- **Gemini Deep Research cancel/thinking detection**: `gemini.py` `completion_check` now checks
  for `button:has-text("Cancel")` and `button[aria-label*="Cancel"]` in addition to "Stop",
  and detects the Deep Research "Thinking" progress indicator as a "still running" signal.
  Raised the no-signal fallback from 12 → 40 polls (6.7 min) so complex research prompts are
  not prematurely declared complete.  Also bumped `post_send` plan-wait from 10s → 20s and
  extended the post-click stop/cancel verification timeout from 3s → 5s.

- **Perplexity premature stable-state completion**: `perplexity.py` `completion_check` increased
  the primary stable-state guard from 3 polls (30s) to 6 polls (60s) + requires > 10 000 chars
  + requires the page URL to be a conversation URL (not the plain homepage). Extended the
  fallback from 6 polls to 12 polls (120s). This prevents old-session tab content from
  triggering premature completion when a reused tab has prior response data.

---

## 0.2.26040602 Alpha — Gemini & DeepSeek Response Extraction Fixes

**Date:** 2026-04-06

### Fixes

- **Gemini completion_check scoped selectors**: `gemini.py` `completion_check` now restricts
  the Copy/Share button signal to response-container-scoped selectors
  (`[class*="model-response"]`, `[class*="message-content"]`, `.markdown-main-panel`,
  `[class*="response-container"]`) and requires `body.innerText.length > 3000` before
  evaluating them. Previously, Gemini's persistent page-header Copy/Share buttons triggered
  false completion at 7–17 seconds, returning truncated responses (~340 chars).

- **DeepSeek extract_response leaf-block JS extraction**: `deepseek.py` `extract_response` now
  uses a JS-based approach that (a) selects only **leaf** markdown blocks (elements with no
  matching `.markdown-body` / `[class*="ds-markdown"]` descendants) to prevent parent/child
  duplication, and (b) excludes blocks inside any ancestor with class names containing `think`,
  `reasoning`, or `chain-of-thought` to strip the DeepThink chain-of-thought from the output.
  Previously, extraction returned only the last block (conclusion paragraph, ~343 chars) or,
  after a prior fix, included the thinking chain verbatim causing duplication (~988 chars).
  Now returns the clean structured response (~4500 chars).

---

## 0.2.26040601 Alpha — SKILL Auto-Invoke Fix, Non-Interactive Mode, Rate Limiter Cap

**Date:** 2026-04-06

### Fixes

- **SKILL auto-invoke (critical)**: `SKILL.md` description now includes `"DEEP"` and `"REGULAR"` as
  explicit trigger keywords, and adds "any substantive research/analysis prompt while MultAI plugin
  is loaded" as a trigger. Previously, `claude -p "DEEP\n..."` caused Claude to answer directly
  without invoking the skill. Now the skill is invoked correctly for all research prompts.

- **Non-interactive mode auto-confirm**: Phase 0 confirmation dialog now auto-confirms when running
  via `claude -p` / `--dangerously-skip-permissions` / piped input where no interactive response
  is possible. Previously the skill would deadlock waiting for user confirmation.

- **DEEP/REGULAR prefix stripping (Phase 1)**: SKILL.md Phase 1 now explicitly instructs Claude to
  detect a leading `DEEP` or `REGULAR` word in the prompt, extract it as the mode flag, and strip
  it from the prompt text before writing the temp file. Previously `DEEP\n\n[content]` was sent
  verbatim to all 7 platforms.

- **Rate limiter backoff cap**: `rate_limiter.py` exponential backoff is now capped at 3600 seconds
  (1 hour). The previous uncapped `cooldown × 2^4` formula could produce 16-hour lockouts for
  Gemini (base cooldown 3600s × 16 = ~16 hours).

- **Gemini free REGULAR cap corrected**: `config.py` `max_requests` for `gemini.free.REGULAR`
  corrected from `4` to `5` to match the documented `5/day` budget.

- **Collate markdown escape map extended**: `collate_responses.py` header escape map now also
  escapes backticks, tildes, and pipes to prevent malformed archive headers.

- **Collate silent status.json failure fixed**: `collate_responses.py` now prints a warning when
  `status.json` is malformed rather than silently discarding the metadata.

- **Rate limiter mode validation**: `rate_limiter.py` `record_usage()` now validates that `mode`
  is `"DEEP"` or `"REGULAR"` and logs a warning + falls back to `"REGULAR"` if not.

---

## 0.2.26040304 Alpha — Report Viewer Polish, CI Fix, Gitignore Cleanup

**Date:** 2026-04-02

### Features

- **Report Viewer — generic Landscape Report viewer**: `reports/preview.html` decoupled from
  hardcoded Platform Engineering data via `chart-data.json` sidecar pattern. Each report directory
  carries its own data file; viewer falls back to built-in defaults when absent.
- **Report Viewer — empty state**: polished hero card with icon, heading, subtitle, and styled
  launch command code block.
- **Report Viewer — export buttons**: Copy, PDF, Compare buttons now have visible `border` for
  clear affordance.
- **Report Viewer — orphan lines removed**: `#stats:empty { display:none }`, `#sidebarFooter`
  border-top, and `#solutionNav` border-bottom removed to eliminate bare lines in empty state.
- **Silver Bullet enforcement**: `.silver-bullet.json` and `docs/workflows/full-dev-cycle.md`
  initialised for the project.
- **`chart-data.json` skeleton generation**: `launch_report.py` now creates a skeleton sidecar
  alongside each new report, pre-populated with domain-aware placeholder titles and empty data arrays.

### Fixes

- **8 issues from MULTAI-ISSUE-REPORT-2026-04-02**: chart data reset on each `loadFile()` call,
  per-report title override, configurable chart titles/anchors, vendor pill fallback for table-based
  reports, `collectVendorNames` tier-heading guard, `addPills` scroll fallback.
- **Preview server**: switched to Homebrew Python 3.13 + `PORT`-aware `serve.py`; system Python 3.9
  failed with `PermissionError` on `--directory` flag in sandboxed environment.
- **`launch_report.py` CI fix**: `mkdir(parents=True, exist_ok=True)` before writing
  `chart-data.json` — directory may not exist in test contexts.
- **`setup.sh`**: added `git pull --rebase` so reinstall always fetches latest source.
- **Docs sync**: restored 6 remote doc files that Silver Bullet scaffold had replaced with
  incorrect stubs (`SRS.md`, `CICD-Strategy-and-Plan.md`, `Test-Strategy-and-Plan.md`,
  `Architecture-and-Design.md`, `CNAME`, `index.html`).

### Chores

- **Gitignore**: `reports/*/` — all generated MultAI output (raw AI responses, CIRs, landscape
  reports, comparison matrices) excluded from tracking. SENTINEL audit files remain tracked.
- **Version sync**: `CONTRIBUTOR-GUIDE.md` and `USER-GUIDE.md` stamped to current version.

---

## 0.2.26040303 Alpha — SENTINEL Security Audit: XSS Fix, CDN Hardening, Temp File Cleanup

**Date:** 2026-04-03

Full SENTINEL v2.3 adversarial security audit performed across all 30+ plugin files. Audit report
saved to `SENTINEL-audit-multai.md`. Two HIGH findings remediated, one MEDIUM improved.

### Security Fix: XSS via unsanitized AI responses in report viewer (FINDING-9, HIGH)

`preview.html` rendered AI platform responses via `marked.parse()` → `innerHTML` without
sanitization. A malicious AI response containing `<img onerror="...">` or `<script>` would
execute JavaScript in the user's browser when viewing the report.

**Fix:** Added [DOMPurify 3.2.4](https://github.com/cure53/DOMPurify) as a CDN dependency.
All markdown-to-HTML output is now sanitized via `DOMPurify.sanitize(marked.parse(md))` before
`innerHTML` assignment.

### Security Fix: Unpinned CDN dependency + missing SRI hashes (FINDING-7, MEDIUM)

The `marked` library was loaded from CDN without a version pin (`npm/marked/marked.min.js`),
meaning a CDN compromise could inject malicious JavaScript into every report viewer. Combined
with the lack of sanitization (FINDING-9), this created a HIGH-risk vulnerability chain (VC-3).

**Fix:**
- `marked` pinned to `@15.0.7`
- All four CDN scripts (`marked`, `DOMPurify`, `chart.js`, `chartjs-plugin-datalabels`) now include
  `integrity="sha384-..."` SRI hashes and `crossorigin="anonymous"` attributes

### Security Fix: Temp prompt files left on disk (FINDING-8 sub-finding)

Prompts written to `/tmp/orchestrator-prompt.md` (and similar) persisted after the engine run,
leaving potentially sensitive prompt content readable by other processes.

**Fix:** `orchestrator.py` now deletes `/tmp/` prompt files after collation completes (best-effort
cleanup — failures are non-fatal).

### Audit Summary

| Severity | Count | Action |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 2 | Both fixed (FINDING-8 by-design + consent, FINDING-9 XSS) |
| MEDIUM | 4 | FINDING-7 fixed; others have adequate existing mitigations |
| LOW | 2 | Adequate existing mitigations |

**Deployment recommendation:** Deploy with monitoring (upgraded from "Deploy with mitigations"
after applying fixes).

---

## 0.2.26040302 Alpha — Hardened Release: Security Fixes, Code Review Pass

**Date:** 2026-04-03

Three-iteration code review pass across the entire plugin. All Critical, Important, and
Suggestion findings addressed — zero remaining issues.

### Security

- **XSS fix** in `reports/preview.html`: error handler now uses `textContent` + `createElement`
  instead of `innerHTML` interpolation with unsanitised error objects.

### Fix: `is_chat_ready()` false-positive detection

The readiness check previously scanned **all visible page text** for patterns like "404", which
triggered false positives on normal AI responses mentioning HTTP status codes. Now checks
`document.title` only — far more reliable. Added `502 Bad Gateway` pattern.

### Fix: `dismiss_popups()` scoped to overlay containers

Broad selectors like `button:has-text("OK")` could accidentally click legitimate chat UI buttons.
All selectors are now scoped to `[role="dialog"]`, `[aria-modal="true"]`, or `[class*="modal"]`
containers. Consent/cookie selectors scoped to `[class*="cookie"]`, `[class*="consent"]`,
`[class*="banner"]`, `[id*="cookie"]`, `[id*="consent"]` containers. Handles layered popups
(up to 3 per call) instead of stopping after the first dismissal.

### Fix: Dialog handler idempotency

Follow-up mode reuses the same `Page` object, which previously caused duplicate dialog handler
registration. Now uses a class-level `WeakSet` to track registered pages — safe for garbage
collection, no monkey-patching of Playwright objects.

### Fix: Duplicate sign-in notifications

Previously three separate notifications for the same sign-in event. Consolidated to one real-time
print in `BasePlatform.run()` plus the existing 90s countdown block.

### Fix: Installation verification reliability

- `setup.sh` Chromium verification now has a 30s timeout (portable `perl alarm` for macOS).
- `_verify_playwright()` caches results via a `.playwright-verified` stamp file keyed by
  Playwright version — eliminates 5-10s headless launch on every subsequent run.
- `importlib.metadata` imported cleanly at module level (removed `__import__` hack).

### Fix: Compare badge visibility

`compareBadge` was invisible (white-on-white) after the button restyling. Now uses
`var(--color-accent-primary)` background with white text.

### Fix: `full_platform_run` prompt truncation

Documented that prompts > 3000 chars are truncated for the browser-use agent fallback path.
The truncation suffix now honestly states `[truncated]` instead of the misleading
`[prompt continues — type all of it]`. A `log.warning` is emitted when truncation occurs.

---

## 0.2.26040301 Alpha — Orchestrator: Popup Dismissal, Readiness Check, Real-Time Sign-In, Verified Install

**Date:** 2026-04-03

### Enhancement: Auto-dismiss browser dialogs and CSS overlay popups

- **Browser dialogs** (`alert()`, `confirm()`, `prompt()`): a `page.on("dialog")` handler is
  registered once per page at the start of `run()`. Any dialog that fires is accepted immediately,
  preventing the page from hanging indefinitely while waiting for user interaction.
- **CSS overlay popups** (cookie banners, GDPR notices, sign-up modals, toasts): a new
  `dismiss_popups()` static method on `BasePlatform` tries 20+ common selectors (close buttons,
  "Accept all", "Got it", "Dismiss", modal/overlay close patterns). It is called at three points:
  - After navigation + initial page wait (before any interaction)
  - After `configure_mode` (catches upsell modals that appear after model selection)
  - After `click_send` (catches share/sign-up prompts that appear after sending)

### Enhancement: Chat readiness check → Browser-Use takeover on unexpected UI

- New `is_chat_ready(page)` method on `BasePlatform` (subclasses can override). Called between
  the rate limit check and `configure_mode`. Checks for sign-in redirect, blank/error pages, and
  HTTP error text (404, 500, 503).
- If not ready and the browser-use agent is available, it triggers an agent fallback to navigate
  back to the chat UI, dismiss any blocking overlays, and confirm the input area is visible.
- If not ready and no agent is available, it logs a warning and continues — `configure_mode` may
  still recover.

### Enhancement: Real-time sign-in notifications

Previously the sign-in prompt was printed only after **all** parallel platforms completed (at the
90-second countdown block). Now sign-in is surfaced at two earlier points:

1. **Immediately in `BasePlatform.run()`** when `is_sign_in_page()` first detects a login wall —
   prints the platform name and URL to stdout so the user can act right away.
2. **Immediately in `_staggered_run()`** when a platform returns `STATUS_NEEDS_LOGIN` — prints a
   second notice reminding the user a retry will run automatically.

The existing 90-second countdown + retry block is preserved unchanged.

### Enhancement: Playwright and browser-use installation verification

Both `setup.sh` and `_ensure_dependencies()` now verify that installed packages actually work,
not just that `pip install` exited 0:

**`setup.sh`** (run via `bash setup.sh`):
- After installing Playwright: imports `async_playwright` and prints a warning if import fails.
- After installing Chromium: runs a headless `page.goto("about:blank")` smoke test; warns if launch fails.
- After installing browser-use (with `--with-fallback`): imports `Agent` and warns if import fails.

**`_ensure_dependencies()`** (auto-run on every `orchestrator.py` invocation):
- Calls `_verify_playwright()`: subprocess import check + headless launch check. Prints a warning
  (does not exit) if either fails, so the error is visible before hitting a cryptic runtime crash.
- Calls `_verify_browser_use()` (only when a new browser-use install occurred): subprocess import
  check. Prints a warning if import fails.

---

## 0.2.26040203 Alpha — Report Viewer: Ālo Design System Redesign

**Date:** 2026-04-02

### Enhancement: `reports/preview.html` redesigned with Ālo Design System

The landscape report viewer UI has been thoroughly redesigned using the Ālo Design System:

- **Light mode default** (previously dark-only sidebar + light body) with persistent dark mode toggle
  stored in `localStorage`. Toggle is in the sidebar with ☀️/🌙 icon.
- **Inter font** (Google Fonts) replaces system UI stack across all UI chrome
- **Indigo/violet/pink accent palette** (`#4f46e5`, `#7c3aed`, `#db2777`) replaces GitHub blue
  throughout: headings, sidebar links, nav pills, progress bar, buttons, callouts, vendor cards
- **Gradient brand** (`linear-gradient(135deg, #4f46e5, #7c3aed, #db2777)`) applied to:
  export/compare buttons, reading progress bar, and card top-border reveal on hover
- **Vendor cards** and **trend cards** now use a silver-bullet-style gradient top-border hover
  effect (`::before` pseudo-element, `opacity: 0 → 1` on hover)
- **Token-based CSS custom properties** inlined in the file: all colors, shadows, radii, and
  transitions reference `var(--color-*)` tokens that flip between light/dark themes
- **Chart colors** updated to match the brand palette: indigo/green/pink/violet for quadrant
  categories; brighter pastel series colors for the value curve
- **Section color coding** (8 `sec-color-N` classes) now uses the brand palette instead of
  GitHub greens/blues/reds
- **Callout boxes** use brand-color accent fills (indigo insight, amber signal, red risk, green stat)
- **Filter bar pills** and **nav pills** use pill-radius, gradient active state, and
  token-aware borders
- **Toast notifications** and **comparison drawer** use `--color-surface` / `--color-border` tokens

All JavaScript logic (chart rendering, vendor cards, TOC, breadcrumb, comparison drawer,
filter bar, PDF export, Google Docs copy) is preserved exactly — only styling was changed.

---

## 0.2.26040202 Alpha — Orchestrator: Login Retry, Perplexity Fix, Platform-Level Fallback

**Date:** 2026-04-02

### Fix: Login-needed platforms are now retried, not skipped

Previously, if a platform returned `needs_login` (sign-in page detected), it was
permanently skipped for that run. Now:
- After all 7 platforms complete in parallel, the engine prints a clear sign-in prompt
  for each `needs_login` platform (with URL) and waits 90 seconds
- The user signs in to those platforms in Chrome during the countdown
- The platforms are retried automatically after the countdown
- All other platforms' results are already collected — only the login-needed ones wait

### Fix: Perplexity — "Computer" feature no longer triggered

`configure_mode` was inadvertently activating "Perplexity Computer" (a paid, credit-based
computer-use feature) instead of a standard Sonar model or Research mode. Fixed:
- All model picker options containing "computer" (case-insensitive) are explicitly skipped
- Research toggle selection has the same guard
- Model selection falls back gracefully if no safe Sonar option is found (uses page default)
- `inject_prompt` updated to prefer textarea (new Perplexity UI) over contenteditable

### Feature: Platform-level browser-use fallback

When a platform returns `STATUS_FAILED` (all Playwright steps failed), and
`ANTHROPIC_API_KEY` or `GOOGLE_API_KEY` is set, a full browser-use agent session
now retries the entire platform interaction (navigate → type → send → wait → extract).
Uses up to 25 agent steps in DEEP mode, 15 in REGULAR mode. Results are saved in
the same format as normal platform output.

This is additive — existing per-step fallbacks are unchanged.

### Files changed

- `skills/orchestrator/engine/orchestrator.py` — login retry loop + platform-level fallback call
- `skills/orchestrator/engine/agent_fallback.py` — `full_platform_run()` method added
- `skills/orchestrator/engine/platforms/perplexity.py` — `configure_mode` Computer guard, `inject_prompt` textarea-first
- `skills/orchestrator/SKILL.md` — Phase 1 browser-use docs, Phase 3 login-retry docs

---

## 0.2.26040201 Alpha — `/consolidator` Redesigned as Standalone Skill

**Date:** 2026-04-02

### Feature: `/consolidator` exposed as a user-facing skill

`/consolidator` is now a first-class skill that can synthesize content from any set of
input sources — documents, transcripts, meeting notes, URLs, pasted text, or AI platform
responses — into a unified, structured report. No prior MultAI research run required.

- **Renamed:** skill name changed from `multi-ai-consolidator` → `consolidator` (fixes
  display name in Claude Desktop skills list)
- **Generic mode (new):** when invoked directly by the user with arbitrary sources, detects
  content type (research papers, interview transcripts, meeting notes, feedback, etc.) and
  auto-derives an appropriate report structure; announces structure and confirms before writing
- **AI-Responses mode (preserved):** when invoked with a raw AI responses archive (from
  orchestrator, landscape-researcher, or solution-researcher), produces a CIR with platform
  reliability weighting exactly as before — no behavioral change for the MultAI workflow
- **Mode detection (Phase 0):** automatically identifies which mode applies based on input
  signals; announces mode to user before proceeding
- **Consolidation guide authority preserved:** when a guide is provided (either mode), it
  remains the sole structural authority — unchanged from prior behavior
- **Source attribution:** all synthesized claims are attributed to specific sources by name;
  conflicts between sources are surfaced explicitly rather than silently resolved
- **Phase numbering updated:** 5 → 7 phases (Phase 0 mode detection, Phase 3 structure
  determination, Phase 7 self-improve)
- **README updated:** `/consolidator` documented as a user-facing skill alongside `/multai`
  and `/comparator`

---

## 0.2.26040105 Alpha — `/comparator` Redesigned as Standalone Skill

**Date:** 2026-04-02

### Feature: `/comparator` exposed as a user-facing skill

`/comparator` is now a first-class skill that can compare any two (or more) solutions
with no prior MultAI research run required. Seven design gaps were addressed:

- **Capability discovery (Gap 1):** New Phase 2 derives a capability framework (categories
  and features) from whatever evidence is available — CIRs, working-folder documents, or
  LLM knowledge. Framework is confirmed with the user before scoring begins.
- **Auto build.json (Gap 2):** `build.json` is now auto-constructed from available evidence
  in Phase 5. Users never interact with the JSON schema.
- **Priority assignment phase (Gap 3):** New optional Phase 3 — interactive priority review
  (say `auto` to skip). Explains weights (Critical=5×, High=3×, Medium=2×, Low=1×) before
  asking. Allows per-feature or per-category adjustment.
- **CIR optional (Gap 4):** Phase 4 (formerly "Process CIR") generalised to handle CIR
  Variant A/B, non-CIR documents, and LLM knowledge — each tagged with a confidence level
  (`CIR-confirmed`, `doc-confirmed`, `inferred`, `user-confirmed`).
- **Compare from scratch (Gap 5):** `compare X vs Y` is now a first-class operation with
  its own end-to-end path through Phases 2→7.
- **Markdown summary (Gap 6):** Phase 7 always produces a readable summary: ranked weighted
  scores, per-category breakdown, key differentiators, shared capabilities, gaps, and
  evidence quality table.
- **Domain knowledge optional (Gap 7):** Phase 1 proceeds gracefully without a domain file.
  Phase 8 bootstraps it from scratch on the first run.

---

## 0.2.26040104 Alpha — Cowork Runtime Support (Claude-in-Chrome)

**Date:** 2026-04-02

### Feature: MultAI now runs in the Cowork tab

The Playwright engine cannot run inside the Cowork Ubuntu sandbox (no system Chrome, no
CDP access, no macOS Keychain auth). This release adds a full Cowork execution path via
the Claude-in-Chrome MCP, which operates the user's real signed-in Mac Chrome directly.

- **Runtime detection (Phase 0a):** Auto-detects Code tab vs Cowork at startup via a
  3-tier check: `sys.platform`, `shutil.which("google-chrome")`, CDP port 9222. No user
  configuration needed.
- **Cowork path (Phase 2-Cowork):** Sequential Claude-in-Chrome execution — tab navigation,
  JS prompt injection (contenteditable and textarea variants), response polling, and
  login-signal detection per platform.
- **User messaging:** Clear guidance when Claude-in-Chrome is not connected, with Code tab
  as the recommended fallback.
- **`chrome_selectors.py`:** New file — canonical CSS selectors for all 7 platforms (input,
  submit, login signals, URL) for the Claude-in-Chrome path.
- **Playwright engine unchanged** — remains the primary, full-featured Code tab path with
  parallel execution.

| | Code tab | Cowork tab |
|---|---|---|
| Engine | Playwright + CDP | Claude-in-Chrome MCP |
| Execution | Parallel (all 7 at once) | Sequential (one at a time) |
| Auth | Mac Chrome profile | Real Chrome (already signed in) |
| Setup | `bash setup.sh` | Zero |

---

## 0.2.26040102 Alpha — SENTINEL Security Audit Remediations

**Date:** 2026-04-01

### Security: 9 Findings Addressed (SENTINEL v2.3 Audit)

- **[Critical] F-4.1** — Removed `Login Data` (saved passwords) from Chrome profile copy; restricted `~/.chrome-playwright/` to owner-only permissions (0700)
- **[High] F-5.1** — Removed broad `Bash(python3:*)` wildcard permission from `settings.json`; specific script allowlist entries cover all legitimate use cases
- **[High] F-1.1** — Wrapped all platform responses in `<untrusted_platform_response>` XML tags in collated archive; added trust boundary preamble to consolidator skill to prevent indirect prompt injection
- **[Medium] F-5.2** — Added path traversal guard: `--output-dir` is now validated to be within the project root
- **[Medium] F-3.1** — CDP debug port now explicitly bound to `127.0.0.1` via `--remote-debugging-host`
- **[Medium] F-8.1** — Added explicit user consent gate in orchestrator Phase 0 listing all 7 external AI services before transmitting any prompt
- **[Medium] F-7.1** — Pinned all dependencies to exact versions in `setup.sh` and `orchestrator.py`; added `requirements.txt`; fixed `browser-use` version inconsistency between `setup.sh` and `orchestrator.py`
- **[Medium] F-1.2** — Added 500 KB size limit check for `--prompt-file` input
- **[Low] F-9.1** — Markdown structural characters now escaped in `task_name` used in archive header

---

## 0.2.26040101 Alpha — Rename orchestrator skill to `/multai`

**Date:** 2026-04-01

### UX: Skill Renamed

Renamed the primary entry-point skill from `multi-ai-orchestrator` to `multai` — shorter, consistent with the project brand, and unambiguous. Users invoke it as `/multai`. Sub-skills (landscape-researcher, solution-researcher, comparator, consolidator) remain available internally for routing but are no longer surfaced directly.

---

## 0.2.260331A Alpha — Orchestration Reliability & Tab Reuse

**Date:** 2026-03-31

### Engine: 7 Reliability Fixes

#### 1 — Explicit Playwright-Only Enforcement (SKILL.md)
Added a prominent `CRITICAL` banner to `skills/orchestrator/SKILL.md` explicitly banning Claude-in-Chrome MCP tools, computer-use tools, and any manual browser automation from being used in place of the Python Playwright engine. Prevents the host AI from attempting to do browser automation itself instead of invoking the script.

#### 2 — Sign-In Page Detection
New `is_sign_in_page()` method on `BasePlatform` detects login/sign-in pages via URL pattern matching (`/login`, `/signin`, `accounts.google.com`, etc.) and password-field presence. When detected, the engine attempts agent fallback to navigate past the page; if still on a login screen, returns a clear `STATUS_NEEDS_LOGIN` (🔑) result rather than silently failing or hanging.

New status code `STATUS_NEEDS_LOGIN = "needs_login"` added to `config.py` with a 🔑 icon in `STATUS_ICONS`.

#### 3 — Broader Agent Fallback Coverage
Agent fallback is now triggered in additional code paths previously missing coverage:
- Navigation failure (`page.goto()` errors)
- `click_send()` errors (previously fell through to Enter key only)
- `configure_mode()` errors (previously re-raised without agent attempt)

#### 4 — Pre-Flight: Warn-Only, Never Skip
Pre-flight rate-limit checks changed from a hard gate to warnings only. All requested platforms now always proceed to the browser — a platform is excluded only if it:
- Shows a sign-in page (`needs_login`)
- Is network-unreachable (`failed`)
- Returns on-page quota exhaustion (`rate_limited`)

This eliminates the prior behaviour where platforms were silently skipped due to budget/cooldown state.

#### 5 — Dynamic Global Timeout
The global `asyncio.wait_for` ceiling is now calculated dynamically:

```
global_timeout = max(per_platform_timeouts) + (num_platforms − 1) × stagger_delay + 60s
```

This ensures the last staggered platform always gets its full per-platform wait time before the hard ceiling fires, preventing premature cancellation of slow-finishing platforms.

#### 6 — Follow-Up Mode (`--followup`)
New `--followup` CLI flag. When set, the engine finds each platform's existing open browser tab (matched by URL domain) and injects the new prompt directly into the current conversation — no navigation, no mode reconfiguration, no new tabs. Use this for follow-up questions on the same research topic.

#### 7 — Tab Reuse for New Topics
Default behaviour (without `--followup`): the engine still finds existing open tabs for each platform, but navigates to the new-conversation URL within the found tab rather than opening a new one. Tab URLs are persisted to `~/.chrome-playwright/tab-state.json` after each run.

New `PLATFORM_URL_DOMAINS` constant in `config.py` maps each platform to its hostname for tab matching.

### Tests
- `UT-OR-12`: `--followup` flag defaults to `False`, set to `True` when supplied
- `UT-CF-09`: `PLATFORM_URL_DOMAINS` has 7 entries matching `PLATFORM_URLS` keys
- `UT-CF-10`: `STATUS_NEEDS_LOGIN` defined and present in `STATUS_ICONS`
- Total: 96 → **98 tests**

### Website & Docs
- `docs/index.html`: dark mode now default on first visit
- `docs/index.html`: comparison table headings center-aligned
- `README.md`: rate limiting, agent fallback, and tab reuse sections updated
- All doc headers and version badge bumped to `0.2.260331A Alpha`

---

## 0.2.260318A Alpha — Release Pipeline & Doc Restructure

**Date:** 2026-03-18

### Versioning
- Adopted hybrid semver + CalVer scheme: `Major.Minor.YYMMDDX Phase`
- Previous internal versions (v2.0–v4.2) consolidated into `0.2.260318A Alpha`
- All doc headers, pyproject.toml, website, and git tags updated

### Engine Hardening (15 bugs fixed across 3 E2E test rounds)
- Rate limiter timezone fix: `_count_today()` now uses local midnight consistently
- Agent fallback model names extracted to `config.py` constants
- All 7 platform adapters hardened: multi-selector fallbacks, improved rate-limit detection, DEEP mode toggles

### Documentation Restructure
- `USER-GUIDE.md` → `CONTRIBUTOR-GUIDE.md` (technical contributor reference)
- New `USER-GUIDE.md` created (friendly end-user guide, 296 lines)
- Rebranded all docs from "Multi-AI Skills" to "MultAI"
- Report viewer: DOCS nav row in top bar + sidebar footer links

### CI/CD Pipeline
- `.github/workflows/ci.yml` — GitHub Actions (Python 3.11/3.12/3.13 matrix)
- Security scanning: pip-audit + secret detection + plugin manifest validation
- 96 automated tests (91 in CI + 5 local-only venv tests)
- Full CI/CD Strategy doc rewrite with branching model, rollback procedure, Phase 2/3 roadmap

---

## [4.1.0] — 2026-03-18 (Internal)

### Summary

Dependency bootstrap overhaul. Introduced `setup.sh` as the canonical one-time installer, refactored `install.sh` to a thin delegate, fixed the `SessionStart` plugin hook chain, added `requirements.txt` under the engine directory, added a venv existence check in the orchestrator Phase 1, and updated all documentation for v4.1.

---

### New Files

| File | Description |
|------|-------------|
| `setup.sh` | Canonical bootstrap script (Python 3.11+): creates `skills/orchestrator/engine/.venv`, installs `playwright>=1.40.0` and `openpyxl>=3.1.0`, runs `playwright install chromium`, creates `.env` template, runs smoke test. `--with-fallback` flag also installs `browser-use==0.12.2`, `anthropic>=0.76.0`, `fastmcp>=2.0.0`. Idempotent: reuses existing `.venv` on re-run without re-checking system Python version. |
| `skills/orchestrator/engine/requirements.txt` | Explicit requirements file listing `playwright>=1.40.0` and `openpyxl>=3.1.0`. |
| `tests/test_setup_bootstrap.py` | 17 new tests covering TC-SETUP-1/3, TC-VENV-1, TC-HOOK-1/2, TC-LAUNCH-1/2. Total test suite: 75 tests (was 58). Now 93 with v4.2 additions. |

---

### Updated Files

| File | Change |
|------|--------|
| `install.sh` | Refactored from full install logic to a single-line delegate: `exec bash setup.sh "$@"`. Called by the `SessionStart` hook. |
| `skills/orchestrator/SKILL.md` | Phase 1 now checks for `.venv` existence before invoking the engine. Shows `bash setup.sh` instructions if missing. |

---

### Plugin Hook Chain

```
SessionStart hook (hooks/hooks.json)
    └──► install.sh  (delegates to setup.sh)
              └──► setup.sh  (creates .venv, installs deps, writes .installed sentinel)
```

The `.installed` sentinel file prevents re-invocation on subsequent sessions.

---

### Installation Paths (v4.1)

| Path | How dependencies are installed |
|------|-------------------------------|
| Plugin install (`claude plugin install`) | Automatic on first session start via `SessionStart` hook → `install.sh` → `setup.sh` |
| skills.sh install (`npx skills add alo-exp/multai`) | Manual: user runs `bash setup.sh` after install. SKILL.md Phase 1 detects missing `.venv` and prompts. |
| Clone / dev | Manual: `git clone` then `bash setup.sh` |

---

### Documentation Updates

| File | Changes |
|------|---------|
| `README.md` | Quick Start updated: `bash install.sh` → `bash setup.sh`; plugin auto-install note; project structure updated; Python ≥3.11; Running Tests uses `.venv/bin/python` |
| `USER-GUIDE.md` | Section 3.2 replaced with `bash setup.sh`; Section 3.3 uses `bash setup.sh --with-fallback`; Section 4 structure updated; Prerequisites Python 3.11+; Section 13 notes venv activation; Appendix C v4.1 entry |
| `docs/SRS.md` | Version table v4.1; Section 1.1 v4.1 bullet; Section 1.3 new definitions; Section 3.11 new FRs (FR-SETUP-1–3, FR-HOOK-1–2, FR-VENV-1); NFR-05 Python 3.11+ |
| `docs/Test-Strategy-and-Plan.md` | Version table v4.1; Section 2.8 new test cases (TC-SETUP-1–3, TC-VENV-1, TC-HOOK-1–2); Section 3.1 Python 3.11+ |
| `docs/CICD-Strategy-and-Plan.md` | Version table v4.1; Stage 1 setup.sh note; Stage 2 bash syntax checks; Stage 4 smoke test; GitHub Actions syntax check step; Python 3.11+ |
| `docs/Architecture-and-Design.md` | Version table v4.1; Section 6.11 Dependency Bootstrap (plugin path, skills.sh path, venv locations, sentinel) |

---

## [4.0.0] — 2026-03-16

### Summary

Complete architectural restructure. Introduced the `landscape-researcher` skill, an intelligent routing layer in the orchestrator, self-improving skills with run logs, self-contained skill ownership of Python scripts, and a shared domain knowledge model enriched by both research skills.

---

### New Files

| File | Description |
|------|-------------|
| `skills/landscape-researcher/SKILL.md` | Full end-to-end landscape research skill (6 phases) |
| `skills/landscape-researcher/prompt-template.md` | Parametrized landscape research prompt (`[SOLUTION_CATEGORY]`, `[TARGET_AUDIENCE]`, `[SCOPE_MODIFIERS]`) |
| `skills/landscape-researcher/consolidation-guide.md` | 9-section Market Landscape Report structure (consolidator authority) |
| `skills/landscape-researcher/launch_report.py` | Stdlib-only HTTP server launcher; opens `preview.html?report=<url-encoded-path>` |
| `domains/devops-platforms.md` | Shared domain knowledge file (enriched by both landscape-researcher and solution-researcher) |
| `CHANGELOG.md` | This file |

---

### Topology Changes

| Before | After |
|--------|-------|
| No routing layer — skills invoked directly | Orchestrator Phase 0 is an intelligent router |
| Engine at `engine/` (project root) | Engine at `skills/orchestrator/engine/` (orchestrator-owned) |
| `matrix_ops.py` / `matrix_builder.py` at `engine/` | Moved to `skills/comparator/` (comparator-owned) |
| No landscape research skill | `skills/landscape-researcher/` (new) |
| Skills had no self-improvement mechanism | Every skill has Self-Improve phase + `## Run Log` |
| Domain knowledge enriched by solution-researcher only | Domain knowledge enriched by both landscape-researcher and solution-researcher |
| Preview HTML hardcoded to one report | `preview.html?report=<path>` — query-param driven |

---

### Updated Files

#### `skills/orchestrator/SKILL.md`
- Added **Phase 0 — Route Decision** (routing decision tree; announce route; accept user override)
- Routing targets: landscape intent → `landscape-researcher`; product URL + research intent → `solution-researcher`; matrix ops → `comparator`; everything else → direct multi-AI
- Updated all engine invocation paths to `skills/orchestrator/engine/orchestrator.py`
- Added **Phase 5** (direct path): invoke consolidator generically after direct multi-AI runs
- Added **Phase 6 — Self-Improve** with `## Run Log` section

#### `skills/consolidator/SKILL.md`
- Phase 2 clarified: "The consolidation guide is the sole structural authority for output format. Do not introduce task-type knowledge beyond what the guide specifies."
- Added **Phase 5 — Self-Improve** with `## Run Log` section

#### `skills/solution-researcher/SKILL.md`
- Engine path updated to `skills/orchestrator/engine/orchestrator.py`
- Phase 5b comparator reference updated to `skills/comparator/matrix_ops.py`
- Phase 5 (domain enrichment): explicitly specifies general domain knowledge additions (archetypes, terminology, trend signals, inference patterns) — not just product-specific data — so landscape-researcher runs also benefit
- Added **Phase 7 — Self-Improve** with `## Run Log` section

#### `skills/comparator/SKILL.md`
- All `python3 engine/matrix_ops.py` references → `python3 skills/comparator/matrix_ops.py`
- All `python3 engine/matrix_builder.py` references → `python3 skills/comparator/matrix_builder.py`
- Added **Phase 7 — Self-Improve** with `## Run Log` section

#### `reports/preview.html`
- Replaced hardcoded `loadFile(...)` call with query-param-driven loader:
  ```javascript
  (function() {
    const params = new URLSearchParams(window.location.search);
    const report = params.get('report');
    if (report) {
      loadFile(decodeURIComponent(report));
    } else {
      loadFile('market-landscape-20260315-2128/Platform Engineering Solutions - Market Landscape Report.md');
    }
  })();
  ```
- Both landscape reports and CIRs render correctly via the existing `injectCharts()` handler

---

### Documentation Updates

| File | Changes |
|------|---------|
| `docs/Architecture-and-Design.md` | Rewritten topology section; landscape research data flow; domain knowledge sharing model; self-improving skills pattern (§6.10); all engine/comparator path references updated |
| `docs/SRS.md` | Added FR-LR (landscape-researcher FRs), FR-NEW-1–7 (routing, landscape, domain enrichment, self-improve, query-param preview); updated engine/comparator paths; updated Top 10 → Top 20 throughout; added UC-06 (landscape research use case) |
| `docs/Test-Strategy-and-Plan.md` | Added §3.4 Orchestrator Routing Tests (IT-RT-01–04), §3.5 launch_report.py Tests (IT-LR-01–03), §3.6 preview.html Tests (IT-PV-01–03); updated all path references |
| `docs/CICD-Strategy-and-Plan.md` | Updated all `engine/` paths → `skills/orchestrator/engine/`; updated matrix script paths → `skills/comparator/`; added `launch_report.py` to lint gate; added landscape workflow smoke test; updated requirements.txt path |

---

### Design Principles (v4.0)

1. **Skill ownership of Python** — Each skill owns its support scripts. Orchestrator owns the Playwright/Browser-Use engine. Comparator owns XLSX ops scripts. Skills are portable, self-contained modules.

2. **Intelligent routing** — The orchestrator is the single entry point. It announces its routing decision before acting and accepts user overrides.

3. **Self-improving skills** — Every skill has a Self-Improve phase that appends a timestamped `## Run Log` entry to its own SKILL.md and updates its own templates/scripts after each successful run. Scope boundary: skills only modify files inside their own `skills/{skill-name}/` directory.

4. **Shared domain knowledge** — `domains/{domain}.md` is a living document enriched by both `landscape-researcher` (market-wide signals, archetypes, vendor movements) and `solution-researcher` (product terminology, inference patterns, feature equivalences). All additions are append-only, timestamped, and require user approval before writing.

5. **Query-param report viewer** — `preview.html?report=<url-encoded-path>` loads any report dynamically. `launch_report.py` constructs the correct URL and opens the browser.

---

### Migration from 260308A

This implementation is a clean restructure of `solution-research-skill-260308A/`. The original directory is unchanged. Key file movements:

| 260308A source | multi-ai-skills destination |
|---|---|
| `engine/` (minus matrix scripts) | `skills/orchestrator/engine/` |
| `engine/matrix_ops.py` | `skills/comparator/matrix_ops.py` |
| `engine/matrix_builder.py` | `skills/comparator/matrix_builder.py` |
| `references/market-landscape-prompt.md` | `skills/landscape-researcher/prompt-template.md` |
| `references/platform-setup.md` | `skills/orchestrator/platform-setup.md` |
| `references/prompt-template.md` | `skills/solution-researcher/prompt-template.md` |
| `skills/solution-researcher/consolidation-guide.md` | `skills/solution-researcher/consolidation-guide.md` |
| `skills/*/SKILL.md` | `skills/*/SKILL.md` (updated) |
| `domains/devops-platforms.md` | `domains/devops-platforms.md` |
| `docs/*.md` | `docs/*.md` (updated for v4.0) |
| `.claude/launch.json` | `.claude/launch.json` |
| `reports/preview.html` | `reports/preview.html` (query-param update) |
