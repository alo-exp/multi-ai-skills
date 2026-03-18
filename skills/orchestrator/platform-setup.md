# Platform Setup & Extraction Reference (Playwright edition)

This document provides platform-specific notes for the Python orchestrator. The orchestrator handles all browser automation via Playwright — this reference documents the **why** behind each platform's implementation choices.

> **Architecture change:** The Claude-in-Chrome MCP version used `find()`, `javascript_exec()`, `computer()`, `form_input()`, and `get_page_text()` tool calls orchestrated step-by-step by Claude Code. This version uses Playwright's native API (`page.goto()`, `page.locator()`, `page.evaluate()`, `page.type()`, `page.fill()`) called from Python — all running in parallel via `asyncio.gather()`.

---

## Section 1: Per-Platform Injection Methods

The critical distinction: **contenteditable divs** vs **React-managed textareas**.

| Platform | Input type | Injection method | Python API | Notes |
|----------|-----------|------------------|------------|-------|
| Claude.ai | `contenteditable` div | `document.execCommand('insertText')` | `page.evaluate()` | Standard JS injection |
| ChatGPT | `contenteditable` div | `document.execCommand('insertText')` | `page.evaluate()` | Standard JS injection |
| Copilot | `contenteditable` div | `document.execCommand('insertText')` | `page.evaluate()` | ⚠️ Avoid microphone button |
| Perplexity | `contenteditable` div | `document.execCommand('insertText')` | `page.evaluate()` | May also have textarea fallback |
| **Grok** | **React `<textarea>`** | **Physical typing** | **`page.type()`** | JS injection fails silently. Condensed prompt ≤900 chars. |
| **DeepSeek** | **React `<textarea>`** | **`page.fill()` + event dispatch** | **`page.fill()` + `dispatch_event()`** | `execCommand` fails; `fill()` triggers React state |
| Gemini | `contenteditable` div | `document.execCommand('insertText')` | `page.evaluate()` | ⚠️ Silently truncates long prompts — verify length |

---

## Section 2: Mode Configuration

### DEEP mode
| Platform | Steps |
|----------|-------|
| Claude.ai | Select Sonnet → Enable Research + Web search via + menu |
| ChatGPT | Enable Deep Research via + menu |
| Copilot | Hover mode selector → Think deeper → + menu → Start deep research |
| Perplexity | Select Sonar model → Deep Research toggle if visible |
| Grok | Enable DeepThink + Search toggles |
| DeepSeek | Enable DeepThink + Search toggles |
| Gemini | Select Thinking model → Tools menu → Deep Research → Click "Start research" when plan appears |

### REGULAR mode
| Platform | Steps |
|----------|-------|
| Claude.ai | Select Sonnet → Regular chat (no Research mode) |
| ChatGPT | Regular chat (reasoning model preferred: o3/o4-mini) |
| Copilot | Think deeper only (no deep research) |
| Perplexity | Sonar (no Deep Research) |
| Grok | DeepThink + Search (same as DEEP) |
| DeepSeek | DeepThink + Search (same as DEEP) |
| Gemini | Thinking (no Deep Research) |

---

## Section 3: Platform-Specific Hazards

### Claude.ai
- **NEVER use Opus** — always Sonnet. Opus depletes the shared usage quota.
- **Rate limit pre-check:** Check for "Usage limit reached" banner before any setup. Quota is shared with Claude Code.
- **DOCX artifact (REGULAR mode):** May produce a DOCX artifact instead of inline text. The inline chat text will be a short summary (~1,700 chars). Classify as ⚠️ Partial.
- **Research mode click-to-reveal (DEEP mode):** The report does not auto-display. The orchestrator polls by checking for Copy/Download buttons and clicking artifact cards.

### ChatGPT
- **Deep Research extraction:** Uses blob interceptor + "Export to Markdown" (PRIMARY — 100% success rate). The orchestrator installs the interceptor via `page.evaluate()` after sending.
- **REGULAR mode DOM duplication:** Response may appear twice in the DOM. The extractor slices at the first "End of Report." marker.
- **REGULAR mode extraction:** Uses `article[1].innerText` (article[0] = user prompt, article[1] = AI response).

### Microsoft Copilot
- **Voice mode hazard:** Microphone button near input area. If clicked, destroys in-progress deep research session. The orchestrator avoids this by using `aria-label` filtering on button selectors.
- **Post-send verification:** URL should change to `/chats/<id>`. If not, the prompt may need re-injection.
- **"Start research" button:** In DEEP mode, Copilot may show a research plan before starting. Must click "Start research".

### Perplexity
- **50K limit:** Deep Research can produce >50K chars. The orchestrator uses `.prose` CSS selector for extraction when needed.
- **Deep Research toggle:** May not be visible in the model picker — Sonar does multi-step research by default.

### Grok
- **Physical typing only:** React textarea. All JS injection methods fail silently. Uses `page.type()` with 5ms keystroke delay.
- **Condensed prompt:** ≤900 chars. Full prompt would take too long to type physically.
- **Rate limiting:** "Message limit reached" — mark as ❌ Rate Limited immediately.

### DeepSeek
- **`page.fill()` + event dispatch:** React textarea requires native input events. `execCommand` and `nativeInputValueSetter` both fail.
- **URL access failure:** May be unable to fetch the target URL. Tab title shows "URL Access Failure".
- **Homepage-only analysis:** Even when URL access succeeds, DeepThink R1 may only analyze the homepage.

### Google Gemini
- **Capacity errors:** Deep Research may fail with "at full capacity" error. Retry 3 times with 30s waits.
- **"Start research" click required (DEEP mode):** Gemini presents a research plan before crawling. Must click "Start research" to begin.
- **Silent prompt truncation:** Gemini may truncate long prompts without warning. Verify injected length.
- **Authenticated vs unauthenticated:** Deep Research + Thinking require Google sign-in.

---

## Section 4: Extraction Methods

All extraction uses Playwright's `page.evaluate()` for JavaScript execution and `page.inner_text()` / `page.locator().inner_text()` for DOM text extraction. No Claude-in-Chrome security filter applies — Playwright returns raw content without content filtering.

| Platform | Primary method | Fallback |
|----------|---------------|----------|
| Perplexity | `.prose` CSS selector → `inner_text()` | `body.innerText` via `page.evaluate()` |
| Grok | `body.innerText` via `page.evaluate()` | — |
| DeepSeek | `body.innerText` via `page.evaluate()` | — (check for URL access failure) |
| Copilot | `body.innerText` via `page.evaluate()` | — |
| Claude.ai | Artifact panel selector → `inner_text()` | Large div filter → `body.innerText` |
| ChatGPT (DEEP) | Blob interceptor → Export to Markdown | `article[1].innerText` |
| ChatGPT (REGULAR) | `article[1].innerText` | `body.innerText` |
| Gemini | `body.innerText` with boundary detection | Tree walker via `page.evaluate()` |

### Key advantage over Claude-in-Chrome
Playwright returns raw JavaScript values without any content security filter. This eliminates:
- The need for pre-cleaning pipelines (URL stripping, base64 removal, etc.)
- Chunk-based extraction (2000-char batches)
- Pre-flight filter testing
- The `[BLOCKED]` failure mode entirely

All extraction can happen in a single `page.evaluate()` call regardless of content size.

---

## Section 5: Completion Signals

| Platform | Still generating | Complete |
|----------|-----------------|----------|
| Claude.ai | Stop button visible | Copy + Download buttons in artifact header |
| ChatGPT | Stop/Cancel button visible | "N citations" text, no stop button |
| Copilot | Stop button visible | Response card complete with citations |
| Perplexity | Stop/Cancel button visible | Copy/Regenerate buttons visible |
| Grok | Stop button visible | No stop button, response fully rendered |
| DeepSeek | Stop button visible | Thinking block collapsed, response below |
| Gemini | Stop button visible | No stop button, full report visible |

The orchestrator polls every 30 seconds using `page.locator()` checks against these signals.

---

## Section 6: Typical Wait Times

### DEEP mode
| Platform | Typical | Maximum |
|----------|---------|---------|
| Perplexity, Grok, DeepSeek | 1–5 min | 10 min |
| Copilot (Think Deeper + Deep Research) | 15–40 min | 50 min |
| Gemini Deep Research | 5–15 min | 25 min |
| Claude.ai Research mode | 5–40 min | 50 min |
| ChatGPT Deep Research | 20–40 min | 50 min |

### REGULAR mode
| Platform | Typical | Maximum |
|----------|---------|---------|
| All non-Claude.ai platforms | 1–5 min | 10 min |
| Claude.ai (Sonnet regular) | 1–14 min | 15 min |
