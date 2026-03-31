---
name: multai
description: >
  Intelligent Multi-AI Router & Orchestrator. Submits prompts to 7 AI platforms
  simultaneously (or sequentially in Cowork) and synthesizes results.

  Supports two runtimes automatically detected at startup:
    • Code tab (Mac): Playwright/Browser-Use engine — parallel, full-featured
    • Cowork tab (Linux sandbox): Claude-in-Chrome MCP — sequential, zero-setup auth

  This skill is the PRIMARY ENTRY POINT for all research and multi-AI tasks.
  It reads the user's intent and routes to the correct specialist skill:

  - "landscape" / "market map" / "ecosystem" / "vendor landscape" / "market
    overview" / "competitive landscape" / "category survey" / "industry
    landscape" / "Gartner-style" → landscape-researcher skill

  - Product URL + research intent, specific product name + evaluate/benchmark/
    research/analyze, "competitive intelligence", "capabilities report" →
    solution-researcher skill

  - "comparison matrix" / "add platform" / "update matrix" / "combo column" /
    "verify ticks" / "reorder matrix" → comparator skill

  - Any other multi-AI task, arbitrary prompt, or general question →
    direct multi-AI (this skill runs the engine and consolidates generically)

  USE THIS SKILL proactively whenever the user asks to run something across
  multiple AIs, compare AI outputs, get multi-source perspectives, or whenever
  a specialist skill (landscape-researcher, solution-researcher, comparator)
  would be appropriate. When in doubt, activate this skill — it will route
  correctly.
---

# Multi-AI Orchestrator Skill

This skill is the entry point for all research and multi-AI workflows. It routes
to the right specialist skill or, for arbitrary tasks, runs the engine directly
and consolidates generically. Follow the phases below.

---

> **RUNTIME RULES — READ BEFORE ACTING**
>
> This skill operates in two modes depending on where it runs:
>
> **Code tab (Mac — Darwin):** Use ONLY the Playwright engine (Phase 2). NEVER use
> Claude-in-Chrome MCP tools, computer-use tools, or any manual browser tools.
> They conflict with the engine and defeat parallel execution.
>
> **Cowork tab (Linux sandbox):** The Playwright engine cannot run here. Use ONLY
> the Claude-in-Chrome MCP path (Phase 2-Cowork). The engine Python script will
> fail or produce empty sessions in this environment.
>
> Phase 0a below detects the runtime. Follow its output to determine which path to take.

---

## Phase 0a — Runtime Detection

Run this before anything else to determine which execution path to use:

```bash
python3 - <<'EOF'
import sys, shutil, socket
runtime = "cowork"
if sys.platform != "linux":
    runtime = "code-tab"
elif shutil.which("google-chrome") or shutil.which("chromium"):
    runtime = "code-tab"
else:
    try:
        s = socket.create_connection(("localhost", 9222), timeout=1)
        s.close()
        runtime = "code-tab"
    except OSError:
        pass
print(f"RUNTIME: {runtime}")
EOF
```

- **`RUNTIME: code-tab`** → continue to Phase 0, then follow the **Code Tab path** (Phases 1–2)
- **`RUNTIME: cowork`** → continue to Phase 0, then follow the **Cowork path** (Phase 2-Cowork)

Tell the user which runtime was detected before proceeding.

---

## Phase 0 — Route Decision

Identify the user's intent and announce your routing decision **before acting**.

```
Routing decision tree:

"landscape" / "market map" / "ecosystem" / "vendor landscape" / "market overview"
"competitive landscape" / "category survey" / "industry landscape" / "Gartner-style"
  → ROUTE: landscape-researcher skill (invoke its Phase 0 onward)

Product URL + research intent
  OR specific product name + evaluate / benchmark / research / analyze
  OR "competitive intelligence" / "capabilities report"
  → ROUTE: solution-researcher skill (invoke its Phase 0 onward)

"comparison matrix" / "add platform" / "update matrix" / "combo column"
"verify ticks" / "reorder matrix"
  → ROUTE: comparator skill (invoke its Phase 0 onward)

Everything else (arbitrary prompt, general question, multi-source analysis
without a specific product or landscape intent)
  → Direct multi-AI (continue to Phase 1 below)
```

**Follow-up detection:**
- If the user's message refers to the previous research ("follow up", "also ask",
  "additionally ask them", "what did they say about X", "ask the same AIs"):
  → add `--followup` to the Phase 2 command (reuses open conversations)
- If the topic is clearly new/different:
  → omit `--followup` (engine will start new conversations in the same tabs)

Tell the user which route you've selected: *"Routing to [skill name] — [brief reason]."*
Accept a user override: if they say "no, do X instead", re-route accordingly.

**Before proceeding to Phase 1 / the specialist skill**, confirm with the user:

> "Your prompt will be sent to these external AI services: **Claude.ai, ChatGPT,
> Microsoft Copilot, Perplexity, Grok, DeepSeek, Google Gemini**. Each service
> will receive the full prompt text and may retain it per their own data policies.
> Do not proceed if the prompt contains confidential or sensitive information.
> **Confirm to proceed, or say 'cancel' to abort.**"

Wait for explicit confirmation before continuing. If the user says 'cancel', stop.

---

## Phase 1 — Setup (Code Tab · Direct Multi-AI Path)

*Skip this phase if you've routed to a specialist skill, or if runtime is Cowork (go to Phase 2-Cowork).*

### Accept inputs:
- **Prompt** — the full prompt text, or a path to a prompt file (required)
- **Mode** — `DEEP` or `REGULAR` (default: REGULAR)
- **Condensed prompt** *(optional)* — shorter version for constrained platforms
- **Topic label** *(optional)* — used for naming the output archive

If the prompt is inline text, write it to a temp file:
```bash
cat > /tmp/orchestrator-prompt.md << 'PROMPT_EOF'
[PROMPT TEXT HERE]
PROMPT_EOF
```

### Verify environment:

Check that the engine's virtual environment exists and is bootstrapped:

```bash
ls skills/orchestrator/engine/.venv/bin/python 2>/dev/null && echo "venv OK" || echo "venv MISSING"
```

**If the output is `venv MISSING`**, stop and tell the user:

> "The MultAI engine environment is not set up yet. Please run the one-time bootstrap from the repo root:
>
> ```bash
> bash setup.sh
> ```
>
> This installs Playwright, Chromium, and openpyxl into an isolated virtual environment. Run `bash setup.sh --with-fallback` to also install the browser-use agent. Once complete, re-invoke this skill."

Do not proceed to Phase 2 until the venv exists.

---

## Phase 2 — Run the Engine (Code Tab)

```bash
cd <workspace-root>

python3 skills/orchestrator/engine/orchestrator.py \
    --prompt-file <PROMPT_FILE_PATH> \
    --mode [DEEP|REGULAR] \
    --task-name "<Short Task Name>"
```

Output goes to `reports/<Short Task Name>/`.
The engine auto-collates all responses into `reports/<task-name>/<task-name> - Raw AI Responses.md`.

**CLI options:**
| Flag | Required | Description |
|------|----------|-------------|
| `--prompt-file` | Yes* | Path to prompt file |
| `--prompt` | Yes* | Literal prompt text (*mutually exclusive with --prompt-file*) |
| `--task-name` | **Recommended** | Short run label — output saved to `reports/{task-name}/` |
| `--condensed-prompt` | No | Condensed prompt text for constrained platforms |
| `--condensed-prompt-file` | No | Path to condensed prompt file (alternative to `--condensed-prompt`) |
| `--mode` | No | `DEEP` or `REGULAR` (default: REGULAR) |
| `--output-dir` | No | Override output directory (ignored if `--task-name` is set) |
| `--platforms` | No | Comma-separated platform names, or `all` (default: `all`) |
| `--chrome-profile` | No | Chrome profile name (default: `Default`) |
| `--headless` | No | Run headlessly (not recommended) |
| `--fresh` | No | Force launch new Chrome instance |
| `--tier` | No | Subscription tier: `free` or `paid` (default: `free`) |
| `--skip-rate-check` | No | Bypass rate limit pre-flight checks |
| `--budget` | No | Show rate limit budget summary and exit |
| `--stagger-delay` | No | Seconds between platform launches (default: `5`) |
| `--followup` | No | Reuse existing conversations (same topic follow-up). Omit for new topics. |

**Timeouts:**
- REGULAR mode: 15-minute global ceiling → set Bash timeout to 20 min
- DEEP mode: 50-minute global ceiling → set Bash timeout to 60 min

### Rate Limiting

The engine tracks usage per platform and enforces conservative rate limits.

1. **Pre-flight check**: platforms over budget are skipped with `rate_limited` status
2. **Staggered launch**: platforms launch 5 seconds apart (configurable)
3. **Cooldown enforcement**: minimum time between consecutive runs per platform
4. **Usage persistence**: state saved to `~/.chrome-playwright/rate-limit-state.json`
5. **Runtime detection**: all 7 platforms check for rate-limit banners

Check budget before running:
```bash
python3 skills/orchestrator/engine/orchestrator.py --prompt "test" --budget --tier free
```

---

## Phase 2-Cowork — Cowork Path (Claude-in-Chrome)

*Only follow this phase if Phase 0a detected `RUNTIME: cowork`. Skip if Code tab.*

The Playwright engine cannot run in the Cowork sandbox. Use the Claude-in-Chrome MCP
path instead: Claude controls the user's real Mac Chrome directly, where sessions are
already authenticated.

### Step 1 — Check Claude-in-Chrome connection

```
mcp__Claude_in_Chrome__tabs_context_mcp(createIfEmpty=False)
```

**If the result contains "not connected" or similar failure:**

> MultAI requires Claude-in-Chrome to run in Cowork.
>
> To continue:
> - **Option A (Cowork):** Open Chrome → ensure the Claude-in-Chrome extension is
>   installed and signed in → retry this skill
> - **Option B (Code tab):** Switch to the Code tab where MultAI runs natively
>   with full parallel execution across all 7 platforms simultaneously
>
> The Code tab is recommended for best performance.

Stop here. Do not attempt the Playwright engine.

**If connected:** proceed to Step 2 and inform the user:

> Running in Cowork mode — using Claude-in-Chrome path.
> Platforms will be queried sequentially (one at a time) rather than in parallel.
> Make sure you are signed into the AI platforms in Chrome.

---

### Step 2 — Sequential platform execution

Query each platform in order: **Gemini → Claude.ai → ChatGPT → Copilot → Perplexity → Grok → DeepSeek**

For each platform, use this pattern (adapt selectors from the table below):

**a. Open or reuse a tab:**
```
mcp__Claude_in_Chrome__tabs_create_mcp()        # get tabId
mcp__Claude_in_Chrome__navigate(url=PLATFORM_URL, tabId=tabId)
```
Wait ~3s for page load.

**b. Check if signed in:**
```
mcp__Claude_in_Chrome__get_page_text(tabId=tabId)
```
If the page text contains a login signal (see table below), skip this platform and note `needs_login`.

**c. Inject the prompt:**

For `contenteditable` inputs:
```
mcp__Claude_in_Chrome__javascript_tool(action="javascript_exec", tabId=tabId, text="""
    const el = document.querySelector('INPUT_SEL');
    el.focus();
    document.execCommand('selectAll');
    document.execCommand('insertText', false, PROMPT_TEXT);
    el.dispatchEvent(new Event('input', {bubbles: true}));
""")
```

For `textarea` inputs:
```
mcp__Claude_in_Chrome__javascript_tool(action="javascript_exec", tabId=tabId, text="""
    const el = document.querySelector('INPUT_SEL');
    const nativeInput = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    nativeInput.call(el, PROMPT_TEXT);
    el.dispatchEvent(new Event('input', {bubbles: true}));
""")
```

**d. Submit:**
```
mcp__Claude_in_Chrome__javascript_tool(action="javascript_exec", tabId=tabId, text="""
    document.querySelector('SUBMIT_SEL').click();
""")
```
Or use `mcp__Claude_in_Chrome__find` + `mcp__Claude_in_Chrome__form_input` as fallbacks.

**e. Wait and extract:**
Poll every 15s up to 10 minutes (REGULAR) / 20 minutes (DEEP):
```
mcp__Claude_in_Chrome__get_page_text(tabId=tabId)
```
Declare complete when the page text has not grown for 2 consecutive polls.

---

### Platform selectors reference

| Platform | URL | Input selector | Input type | Submit selector | Login signals |
|---|---|---|---|---|---|
| Google Gemini | https://gemini.google.com | `rich-textarea .ql-editor, div[contenteditable='true'][role='textbox']` | contenteditable | `button[aria-label='Send message']` | "Sign in", "Log in" |
| Claude.ai | https://claude.ai/new | `div[contenteditable='true']` | contenteditable | `button[aria-label*='Send']` | "Sign in", "Continue with Google" |
| ChatGPT | https://chat.openai.com | `#prompt-textarea` | contenteditable | `button[data-testid='send-button']` | "Log in", "Sign up" |
| Copilot | https://copilot.microsoft.com | `textarea[placeholder*='Message']` | textarea | `button[aria-label*='Submit']` | "Sign in", "Microsoft account" |
| Perplexity | https://www.perplexity.ai | `textarea[placeholder*='Ask'], div[contenteditable='true']` | contenteditable | `button[type='submit']` | "Log in", "Sign up" |
| Grok | https://grok.com | `div[contenteditable='true'].ProseMirror, div[contenteditable='true']` | contenteditable | `button[aria-label*='Send']` | "Log in", "Sign in" |
| DeepSeek | https://chat.deepseek.com | `textarea#chat-input, textarea` | textarea | `button[aria-label*='Send']` | "Log in", "Sign in" |

Canonical selectors are also maintained in `skills/orchestrator/engine/platforms/chrome_selectors.py`.

---

### Step 3 — Collect results

After all platforms complete (or are skipped), write each response to:
`reports/<task-name>/<Platform>-raw-response.md`

Then run collation manually:
```bash
python3 skills/orchestrator/engine/collate_responses.py reports/<task-name>/ "<Task Name>"
```

Proceed to Phase 5 (Invoke Consolidator) using the collated archive.

---

## Phase 3 — Read Results

After the engine completes, outputs are in `reports/<task-name>/`:

| File | Description |
|------|-------------|
| `status.json` | Per-platform terminal status and metadata |
| `{Platform}-raw-response.md` | Individual raw response per platform |
| `{task-name} - Raw AI Responses.md` | **Auto-generated archive** — all responses collated |

Platform statuses: `complete` / `partial` / `failed` / `timeout` / `rate_limited`

---

## Phase 4 — Auto-Collation

The engine automatically runs `collate_responses.py` at end of each run.
To re-run collation manually on an existing output dir:
```bash
python3 skills/orchestrator/engine/collate_responses.py reports/<task-name>/ "<Task Name>"
```

---

## Phase 5 — Invoke Consolidator (Direct Multi-AI Path)

*Skip this phase if you've routed to a specialist skill — they invoke the consolidator themselves.*

Invoke the consolidator skill with:
- **Raw responses archive:** `reports/{task-name}/{task-name} - Raw AI Responses.md`
- **No consolidation guide** (generic synthesis — the consolidator applies its default structure)
- **No domain knowledge file** (unless the user specified a domain)

The consolidator will produce a generic synthesis covering: summary, consensus areas,
disagreements, unique insights, gaps, and source reliability.

---

## Phase 6 — Self-Improve

After each successful direct multi-AI run, append a run log entry and note any
observations about the engine, rate limiting, or routing logic.

**Scope boundary:** Only update files inside `skills/orchestrator/`. Never modify
other skills' files or the domain files.

---

## Run Log

<!-- Append new entries at the top of this section after each run -->

### 2026-03-18 — Platform Resilience Code Review + Improvements (2 rounds)
- Trigger: Post 3-run test round gap resolution, quality review, and pre-existing weakness resolution
- Files changed: `platforms/chatgpt.py`, `platforms/claude_ai.py`, `platforms/copilot.py`, `platforms/grok.py`, `platforms/gemini.py`, `platforms/perplexity.py`, `platforms/deepseek.py`, `platforms/base.py` (8 files)
- Round 1 fixes (9 bugs): ChatGPT DR quota detection (check_rate_limit + extract_response guard); blob interceptor robustness (bind+duck-typing+try-catch); Claude.ai stable-state fallback (12-poll); Copilot/Grok/Perplexity/DeepSeek prompt-echo import added; Grok premature-completion guard; expanded rate-limit patterns in Gemini (8 new), Perplexity (6 new), DeepSeek (5 new)
- Round 2 fixes (2 bugs): ChatGPT quota guard threshold removed (was `< 1000`, masked by UI chrome); DeepSeek marker scan echo-guard added (replaced blind rfind with full-scan + is_prompt_echo)
- Pre-existing fixes (3 items): Copilot `check_rate_limit` false-positive patterns tightened ("too many"→"too many requests", "try again"→"try again later"); `_inject_exec_command` deprecation-proofed (return-value check + `_inject_clipboard_paste` auto-fallback); ChatGPT DR coordinate extraction rewritten with proportional iframe offsets + text-selector verification for Copy menu
- Docs updated: Architecture-and-Design.md v4.2, Test-Strategy-and-Plan.md v4.3
- Test result: `make check` 93/93 PASS after all rounds

### 2026-03-18 — E2E Platform Regression (REGULAR + DEEP modes)
- Platforms tested: ChatGPT, Gemini, Claude.ai, Copilot, Grok, DeepSeek, Perplexity (all 7)
- Modes: REGULAR (all 7) + DEEP (ChatGPT, Gemini, Copilot, Grok, Perplexity)
- E2E-01 ChatGPT REGULAR: PASS — response extracted, correct routing
- E2E-02 Gemini REGULAR: PASS — Thinking model selected, response extracted
- E2E-03 Claude.ai REGULAR: PASS — tool-use limit noted mid-long response (acceptable)
- E2E-04 Copilot REGULAR: PASS — 21,627 chars extracted
- E2E-05 Solution-researcher pipeline: PASS — full Northflank CIR produced via 4/6 platforms
- E2E-06 Grok DEEP: PASS — 12,208 chars extracted
- E2E-07 ChatGPT DEEP: BLOCKED — DR quota exhausted; "lighter version" message returned (~381 chars); quota resets 2026-03-28
- E2E-08 DeepSeek REGULAR: PASS — 22,111 chars extracted (DOM chrome noted in content)
- E2E-09 Agent fallback: PASS — fallback path verified via code inspection
- E2E-10 Perplexity REGULAR: PASS — 1 request incremented (state: 3/50 budget)
- E2E-11 Rate-limit detection: PASS — mock HTML tests verified ChatGPT + Gemini check_rate_limit() detection
- E2E-12 Rate-limit state persistence: PASS — rate_limit_state.json persists across runs; Perplexity 2→3 confirmed
- Engine observations: CDP reuse stable; staggered_run scheduling working; post_send Gemini "Start research" click path stable
- Known issue: E2E-07 ChatGPT DR extraction cannot be verified until 2026-03-28 quota reset
